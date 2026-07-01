<?php

declare(strict_types=1);

final class WPFixPilot_WPBakery_Adapter implements
    WPFixPilot_Builder_Adapter,
    WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'wpbakery';
    }

    public function is_active(): bool
    {
        return defined('WPB_VC_VERSION');
    }

    public function uses_page(int $postId): bool
    {
        $post = get_post($postId);

        return $post instanceof WP_Post
            && str_contains((string) $post->post_content, '[vc_');
    }

    /** @return array<int, array{path: string, label: string, value_type: string}> */
    public function inspect(int $postId): array
    {
        $schema = $this->schema($postId);
        if (is_wp_error($schema)) {
            return [];
        }

        $slots = [];
        foreach ($this->schema_fields($schema) as $field) {
            $slots[] = [
                'path' => (string) $field['path'],
                'label' => (string) $field['label'],
                'value_type' => $this->slot_value_type((string) $field['value_type']),
            ];
        }

        return $slots;
    }

    public function template_hash(int $postId): string
    {
        $post = get_post($postId);

        return hash(
            'sha256',
            $post instanceof WP_Post ? (string) $post->post_content : ''
        );
    }

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        $schema = $this->schema($postId);
        if (is_wp_error($schema)) {
            return $schema;
        }

        $replacements = [];
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic])) {
                return new WP_Error(
                    'wp_fixpilot_slot_invalid',
                    'Ongeldige WPBakery-mapping.'
                );
            }

            $fieldId = $this->field_id_for_path($schema, (string) $path);
            if ($fieldId === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'WPBakery-element niet gevonden.'
                );
            }

            $replacements[$fieldId] = (string) $values[$semantic];
        }

        return $this->apply_replacements($postId, $schema, $replacements);
    }

    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array
    {
        $keys = [];
        foreach (array_keys((array) get_post_meta($postId)) as $metaKey) {
            $metaKey = (string) $metaKey;
            if (
                str_starts_with($metaKey, '_wpb_')
                || str_starts_with($metaKey, '_vc_')
                || str_starts_with($metaKey, 'wpb_')
                || str_starts_with($metaKey, 'vc_')
            ) {
                $keys[] = $metaKey;
            }
        }

        $keys = array_values(array_unique($keys));
        sort($keys);

        return $keys;
    }

    /** @return array<string, mixed>|WP_Error */
    public function schema(int $postId): array|WP_Error
    {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'WPBakery is niet actief.',
                ['status' => 409]
            );
        }

        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_draft_missing',
                'Conceptpagina niet gevonden.',
                ['status' => 404]
            );
        }

        $nodes = $this->parse_document((string) $post->post_content);
        if (is_wp_error($nodes)) {
            return $nodes;
        }

        $blocks = $this->collect_blocks($nodes, []);
        if ($blocks === []) {
            return new WP_Error(
                'wp_fixpilot_no_editable_content',
                'Geen bewerkbare tekstinhoud gevonden.',
                ['status' => 400]
            );
        }

        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => $blocks,
        ];
    }

    public function structure_hash(int $postId): string
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return '';
        }

        $nodes = $this->parse_document((string) $post->post_content);
        if (is_wp_error($nodes)) {
            return '';
        }

        return hash('sha256', (string) wp_json_encode($this->normalize_nodes($nodes)));
    }

    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_draft_missing',
                'Conceptpagina niet gevonden.',
                ['status' => 404]
            );
        }

        $nodes = $this->parse_document((string) $post->post_content);
        if (is_wp_error($nodes)) {
            return $nodes;
        }

        $fields = $this->schema_fields($schema);
        foreach ($replacements as $fieldId => $value) {
            if (!isset($fields[$fieldId])) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_field_unknown',
                    'Onbekend blueprint-veld.',
                    ['status' => 400]
                );
            }

            $target = $this->parse_path((string) $fields[$fieldId]['path']);
            if ($target === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_invalid',
                    'Ongeldige WPBakery-mapping.',
                    ['status' => 500]
                );
            }

            if (
                !$this->apply_to_path(
                    $nodes,
                    $target['segments'],
                    $target['kind'],
                    $target['key'],
                    $target['sub_key'],
                    (string) $value
                )
            ) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'WPBakery-element niet gevonden.',
                    ['status' => 500]
                );
            }
        }

        $result = wp_update_post([
            'ID' => $postId,
            'post_content' => $this->serialize_nodes($nodes),
            'post_status' => 'draft',
        ], true);

        return is_wp_error($result)
            ? $result
            : true;
    }

    /** @return array<int, string|array<string, mixed>>|WP_Error */
    private function parse_document(string $content): array|WP_Error
    {
        $pattern = '/\[(\/?)([a-zA-Z0-9_]+)\b([^\]]*?)(\/?)\]/s';
        preg_match_all($pattern, $content, $matches, PREG_OFFSET_CAPTURE);

        if (($matches[0] ?? []) === []) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'WPBakery-structuur ontbreekt.',
                ['status' => 500]
            );
        }

        $root = [
            'tag' => '__root__',
            'attrs' => [],
            'children' => [],
            'self_closing' => false,
        ];
        $stack = [];
        $stack[] = &$root;
        $offset = 0;

        foreach ($matches[0] as $index => $tokenMatch) {
            $token = (string) $tokenMatch[0];
            $position = (int) $tokenMatch[1];
            $text = substr($content, $offset, $position - $offset);
            if ($text !== '') {
                $stack[count($stack) - 1]['children'][] = $text;
            }

            $isClosing = (string) $matches[1][$index][0] === '/';
            $tag = (string) $matches[2][$index][0];
            $attrs = $this->parse_attributes((string) $matches[3][$index][0]);
            $tokenSelfClosing = (string) $matches[4][$index][0] === '/';
            $selfClosing = $tokenSelfClosing || $this->is_standalone_shortcode($tag);

            if ($isClosing) {
                if (
                    count($stack) === 1
                    || (string) $stack[count($stack) - 1]['tag'] !== $tag
                ) {
                    return new WP_Error(
                        'wp_fixpilot_builder_data_missing',
                        'WPBakery-structuur ontbreekt.',
                        ['status' => 500]
                    );
                }

                array_pop($stack);
            } else {
                $currentIndex = count($stack) - 1;
                $stack[$currentIndex]['children'][] = [
                    'tag' => $tag,
                    'attrs' => $attrs,
                    'children' => [],
                    'self_closing' => $selfClosing,
                    'self_closing_slash' => $tokenSelfClosing,
                ];
                $childIndex = array_key_last($stack[$currentIndex]['children']);
                if (!$selfClosing) {
                    $stack[] = &$stack[$currentIndex]['children'][$childIndex];
                }
            }

            $offset = $position + strlen($token);
        }

        $trailing = substr($content, $offset);
        if ($trailing !== '') {
            $stack[count($stack) - 1]['children'][] = $trailing;
        }

        if (count($stack) !== 1) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'WPBakery-structuur ontbreekt.',
                ['status' => 500]
            );
        }

        return $root['children'];
    }

    /** @return array<string, string> */
    private function parse_attributes(string $raw): array
    {
        $attributes = [];
        preg_match_all(
            '/([a-zA-Z0-9_\-:]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s\]]+))/',
            $raw,
            $matches,
            PREG_SET_ORDER
        );
        foreach ($matches as $match) {
            $attributes[(string) $match[1]] = (string) (
                $match[2] !== ''
                    ? $match[2]
                    : ($match[3] !== '' ? $match[3] : $match[4])
            );
        }

        return $attributes;
    }

    /**
     * @param array<int, string|array<string, mixed>> $nodes
     * @param array<int, string> $pathSegments
     * @return array<int, array<string, mixed>>
     */
    private function collect_blocks(array $nodes, array $pathSegments): array
    {
        $blocks = [];
        $shortcodeIndex = -1;
        foreach ($nodes as $node) {
            if (!is_array($node) || !isset($node['tag'])) {
                continue;
            }

            $shortcodeIndex++;
            $currentPath = [...$pathSegments, (string) $shortcodeIndex];
            $fields = $this->fields_from_node($node, $currentPath);
            if ($fields !== []) {
                $tag = (string) ($node['tag'] ?? 'shortcode');
                $blocks[] = [
                    'id' => wpfixpilot_field_id('wpbakery', 'block/' . implode('.', $currentPath)),
                    'layout' => $tag,
                    'label' => $tag,
                    'semantic_role' => $this->infer_semantic_role($tag),
                    'fields' => $fields,
                ];
            }

            $blocks = array_merge(
                $blocks,
                $this->collect_blocks(
                    (array) ($node['children'] ?? []),
                    $currentPath
                )
            );
        }

        return $blocks;
    }

    /**
     * @param array<int, string> $pathSegments
     * @return array<int, array<string, mixed>>
     */
    private function fields_from_node(array $node, array $pathSegments): array
    {
        $fields = [];
        $tag = (string) ($node['tag'] ?? 'shortcode');
        foreach ((array) ($node['attrs'] ?? []) as $key => $value) {
            if (!is_string($value)) {
                continue;
            }

            $valueType = $this->editable_attribute_type($tag, (string) $key, $value);
            if ($valueType === null) {
                continue;
            }

            $path = 'shortcode:' . implode('.', $pathSegments) . ':attr:' . $key;
            $currentValue = $value;
            if ((string) $key === 'link') {
                $path .= ':url';
                $currentValue = $this->link_url($value) ?? '';
            }
            $fields[] = [
                'id' => wpfixpilot_field_id('wpbakery', $path),
                'path' => $path,
                'label' => $tag . ' · ' . $key,
                'value_type' => $valueType,
                'current_value' => $currentValue,
                'required' => true,
                'max_length' => $this->max_length($valueType),
            ];
        }

        $content = $this->node_content((array) ($node['children'] ?? []));
        if ($content !== null) {
            $valueType = $this->content_value_type($tag, $content);
            if ($valueType !== null) {
                $fields[] = [
                    'id' => wpfixpilot_field_id(
                        'wpbakery',
                        'shortcode:' . implode('.', $pathSegments) . ':content'
                    ),
                    'path' => 'shortcode:' . implode('.', $pathSegments) . ':content',
                    'label' => $tag . ' · content',
                    'value_type' => $valueType,
                    'current_value' => $content,
                    'required' => true,
                    'max_length' => $this->max_length($valueType),
                ];
            }
        }

        return $fields;
    }

    /** @param array<int, string|array<string, mixed>> $nodes */
    private function normalize_nodes(array $nodes): array
    {
        $normalized = [];
        foreach ($nodes as $node) {
            if (!is_array($node) || !isset($node['tag'])) {
                $normalized[] = $node;
                continue;
            }

            $tag = (string) ($node['tag'] ?? 'shortcode');
            $normalizedNode = $node;
            foreach ((array) ($normalizedNode['attrs'] ?? []) as $key => $value) {
                if (!is_string($value)) {
                    continue;
                }
                $valueType = $this->editable_attribute_type($tag, (string) $key, $value);
                if ($valueType === null) {
                    continue;
                }
                if ((string) $key === 'link') {
                    $normalizedNode['attrs'][$key] = $this->replace_link_url(
                        $value,
                        '__url__'
                    );
                    continue;
                }
                $normalizedNode['attrs'][$key] = '__' . $valueType . '__';
            }

            $content = $this->node_content((array) ($normalizedNode['children'] ?? []));
            if ($content !== null && $this->content_value_type($tag, $content) !== null) {
                $normalizedNode['children'] = ['__content__'];
            } else {
                $normalizedNode['children'] = $this->normalize_nodes(
                    (array) ($normalizedNode['children'] ?? [])
                );
            }

            $normalized[] = $normalizedNode;
        }

        return $normalized;
    }

    /** @return array<string, int|string|null>|null */
    private function parse_path(string $path): ?array
    {
        if (
            preg_match(
                '/^shortcode:([0-9]+(?:\.[0-9]+)*):content$/',
                $path,
                $matches
            ) === 1
        ) {
            return [
                'segments' => array_map('intval', explode('.', $matches[1])),
                'kind' => 'content',
                'key' => null,
                'sub_key' => null,
            ];
        }

        if (
            preg_match(
                '/^shortcode:([0-9]+(?:\.[0-9]+)*):attr:([^:]+)(?::([^:]+))?$/',
                $path,
                $matches
            ) === 1
        ) {
            return [
                'segments' => array_map('intval', explode('.', $matches[1])),
                'kind' => 'attr',
                'key' => $matches[2],
                'sub_key' => $matches[3] ?? null,
            ];
        }

        return null;
    }

    /**
     * @param array<int, string|array<string, mixed>> $nodes
     * @param array<int, int> $segments
     */
    private function apply_to_path(
        array &$nodes,
        array $segments,
        string $kind,
        ?string $key,
        ?string $subKey,
        string $replacement
    ): bool {
        $targetIndex = array_shift($segments);
        if ($targetIndex === null) {
            return false;
        }

        $shortcodeIndex = -1;
        foreach ($nodes as &$node) {
            if (!is_array($node) || !isset($node['tag'])) {
                continue;
            }

            $shortcodeIndex++;
            if ($shortcodeIndex !== $targetIndex) {
                continue;
            }

            if ($segments !== []) {
                return $this->apply_to_path(
                    $node['children'],
                    $segments,
                    $kind,
                    $key,
                    $subKey,
                    $replacement
                );
            }

            if ($kind === 'content') {
                $node['children'] = [$replacement];

                return true;
            }

            if (
                !isset($node['attrs'])
                || !is_array($node['attrs'])
                || $key === null
                || !array_key_exists($key, $node['attrs'])
                || !is_string($node['attrs'][$key])
            ) {
                return false;
            }

            if ($subKey === 'url') {
                $node['attrs'][$key] = $this->replace_link_url(
                    $node['attrs'][$key],
                    $replacement
                );

                return true;
            }

            $node['attrs'][$key] = $replacement;

            return true;
        }

        return false;
    }

    private function serialize_nodes(array $nodes): string
    {
        $output = '';
        foreach ($nodes as $node) {
            if (is_string($node)) {
                $output .= $node;
                continue;
            }
            if (!is_array($node)) {
                continue;
            }

            $tag = (string) ($node['tag'] ?? '');
            if ($tag === '') {
                continue;
            }

            $output .= '[' . $tag . $this->serialize_attributes((array) ($node['attrs'] ?? []));
            if ($node['self_closing'] ?? false) {
                $output .= ($node['self_closing_slash'] ?? false) ? ' /]' : ']';
                continue;
            }

            $output .= ']';
            $output .= $this->serialize_nodes((array) ($node['children'] ?? []));
            $output .= '[/' . $tag . ']';
        }

        return $output;
    }

    /** @param array<string, string> $attributes */
    private function serialize_attributes(array $attributes): string
    {
        if ($attributes === []) {
            return '';
        }

        $parts = [];
        foreach ($attributes as $key => $value) {
            $parts[] = $key . '="' . str_replace('"', '\"', $value) . '"';
        }

        return ' ' . implode(' ', $parts);
    }

    /** @param array<int, string|array<string, mixed>> $children */
    private function node_content(array $children): ?string
    {
        foreach ($children as $child) {
            if (!is_string($child)) {
                return null;
            }
        }

        return $children === [] ? null : implode('', $children);
    }

    private function editable_attribute_type(
        string $tag,
        string $key,
        string $value
    ): ?string {
        if ($key === 'link' && $this->link_url($value) !== null) {
            return 'url';
        }
        if ($key === 'text') {
            return str_contains($tag, 'heading') ? 'heading' : 'plain_text';
        }
        if ($key === 'title') {
            return str_contains($tag, 'btn') ? 'button_text' : 'heading';
        }
        if (in_array($key, ['button_text', 'label'], true)) {
            return 'button_text';
        }

        return null;
    }

    private function content_value_type(string $tag, string $content): ?string
    {
        if (
            str_contains($tag, 'column_text')
            || str_contains($tag, 'raw_html')
            || wp_strip_all_tags($content) !== $content
        ) {
            return 'rich_text';
        }
        if (trim($content) !== '') {
            return 'plain_text';
        }

        return null;
    }

    private function infer_semantic_role(string $tag): string
    {
        $tag = strtolower($tag);
        if (str_contains($tag, 'heading')) {
            return 'hero';
        }
        if (str_contains($tag, 'btn')) {
            return 'cta';
        }

        return 'content';
    }

    private function link_url(string $link): ?string
    {
        if (preg_match('/(?:^|\|)url:([^|]*)/', $link, $matches) !== 1) {
            return null;
        }

        return $matches[1];
    }

    private function replace_link_url(string $link, string $replacement): string
    {
        if (preg_match('/(?:^|\|)url:([^|]*)/', $link) !== 1) {
            return 'url:' . $replacement;
        }

        return (string) preg_replace_callback(
            '/(^|\|)url:[^|]*/',
            static fn (array $matches): string => $matches[1] . 'url:' . $replacement,
            $link,
            1
        );
    }

    private function is_standalone_shortcode(string $tag): bool
    {
        return in_array($tag, [
            'vc_empty_space',
            'vc_separator',
            'vc_zigzag',
            'vc_single_image',
            'vc_icon',
            'vc_line_chart',
            'vc_pie',
            'vc_round_chart',
        ], true);
    }

    /** @return array<string, array<string, mixed>> */
    private function schema_fields(array $schema): array
    {
        $fields = [];
        foreach ((array) ($schema['blocks'] ?? []) as $block) {
            foreach ((array) ($block['fields'] ?? []) as $field) {
                if (
                    is_array($field)
                    && isset($field['id'])
                    && is_string($field['id'])
                ) {
                    $fields[$field['id']] = $field;
                }
            }
        }

        return $fields;
    }

    private function field_id_for_path(array $schema, string $path): ?string
    {
        foreach ($this->schema_fields($schema) as $fieldId => $field) {
            if (($field['path'] ?? null) === $path) {
                return $fieldId;
            }
        }

        return null;
    }

    private function max_length(string $valueType): int
    {
        return match ($valueType) {
            'heading', 'button_text', 'plain_text' => 500,
            'rich_text' => 20000,
            'url' => 2000,
            default => 5000,
        };
    }

    private function slot_value_type(string $valueType): string
    {
        return $valueType === 'rich_text' ? 'html' : 'text';
    }
}
