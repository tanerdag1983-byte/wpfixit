<?php

declare(strict_types=1);

final class WPFixPilot_Gutenberg_Adapter implements
    WPFixPilot_Builder_Adapter,
    WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'gutenberg';
    }

    public function is_active(): bool
    {
        return function_exists('parse_blocks') && function_exists('serialize_blocks');
    }

    public function uses_page(int $postId): bool
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return false;
        }

        $blocks = parse_blocks((string) $post->post_content);

        return is_array($blocks) && $blocks !== [];
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
        return $this->structure_hash($postId);
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
                    'Ongeldige Gutenberg-blokmapping.'
                );
            }

            $fieldId = $this->field_id_for_path($schema, (string) $path);
            if ($fieldId === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Gutenberg-blok niet gevonden.'
                );
            }

            $replacements[$fieldId] = (string) $values[$semantic];
        }

        return $this->apply_replacements($postId, $schema, $replacements);
    }

    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array
    {
        return [];
    }

    /** @return array<string, mixed>|WP_Error */
    public function schema(int $postId): array|WP_Error
    {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'Gutenberg is niet actief.',
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

        $blocks = parse_blocks((string) $post->post_content);
        if (!is_array($blocks) || $blocks === []) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Gutenberg-structuur ontbreekt.',
                ['status' => 500]
            );
        }

        $schemaBlocks = $this->schema_blocks($blocks, []);
        if ($schemaBlocks === []) {
            return new WP_Error(
                'wp_fixpilot_no_editable_content',
                'Geen bewerkbare tekstinhoud gevonden.',
                ['status' => 400]
            );
        }

        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => $schemaBlocks,
        ];
    }

    public function structure_hash(int $postId): string
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return '';
        }

        $blocks = parse_blocks((string) $post->post_content);
        if (!is_array($blocks) || $blocks === []) {
            return '';
        }

        return hash('sha256', (string) wp_json_encode($this->normalize_blocks($blocks)));
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

        $blocks = parse_blocks((string) $post->post_content);
        if (!is_array($blocks) || $blocks === []) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Gutenberg-structuur ontbreekt.',
                ['status' => 500]
            );
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
                    'Ongeldige Gutenberg-blokmapping.',
                    ['status' => 500]
                );
            }

            if (
                !$this->replace_block_value(
                    $blocks,
                    $target['segments'],
                    $target['kind'],
                    $target['key'],
                    (string) $value
                )
            ) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Gutenberg-blok niet gevonden.',
                    ['status' => 500]
                );
            }
        }

        $result = wp_update_post([
            'ID' => $postId,
            'post_content' => serialize_blocks($blocks),
            'post_status' => 'draft',
        ], true);

        return is_wp_error($result)
            ? $result
            : true;
    }

    /**
     * @param array<int, array<string, mixed>> $blocks
     * @param array<int, string> $pathSegments
     * @return array<int, array<string, mixed>>
     */
    private function schema_blocks(array $blocks, array $pathSegments): array
    {
        $schemaBlocks = [];
        foreach ($blocks as $index => $block) {
            if (!is_array($block)) {
                continue;
            }

            $currentPath = [...$pathSegments, (string) $index];
            $fields = $this->fields_from_block($block, $currentPath);
            if ($fields !== []) {
                $blockName = (string) ($block['blockName'] ?? 'core/block');
                $schemaBlocks[] = [
                    'id' => wpfixpilot_field_id(
                        'gutenberg',
                        'block/' . implode('.', $currentPath)
                    ),
                    'layout' => $blockName,
                    'label' => $this->block_label($blockName),
                    'semantic_role' => $this->infer_semantic_role($blockName),
                    'fields' => $fields,
                ];
            }

            $innerBlocks = $block['innerBlocks'] ?? [];
            if (is_array($innerBlocks) && $innerBlocks !== []) {
                $schemaBlocks = array_merge(
                    $schemaBlocks,
                    $this->schema_blocks($innerBlocks, $currentPath)
                );
            }
        }

        return $schemaBlocks;
    }

    /**
     * @param array<string, mixed> $block
     * @param array<int, string> $pathSegments
     * @return array<int, array<string, mixed>>
     */
    private function fields_from_block(array $block, array $pathSegments): array
    {
        $blockName = (string) ($block['blockName'] ?? '');
        $fields = [];

        foreach ((array) ($block['attrs'] ?? []) as $key => $value) {
            if (!is_string($value)) {
                continue;
            }

            $valueType = $this->editable_attribute_type($blockName, (string) $key);
            if ($valueType === null) {
                continue;
            }

            $path = 'block:' . implode('.', $pathSegments) . ':attr:' . $key;
            $fields[] = [
                'id' => wpfixpilot_field_id('gutenberg', $path),
                'path' => $path,
                'label' => $this->block_label($blockName) . ' · ' . $this->humanize_label((string) $key),
                'value_type' => $valueType,
                'current_value' => $value,
                'required' => true,
                'max_length' => $this->max_length($valueType),
            ];
        }

        if ($fields === [] && $this->editable_inner_html_type($blockName) !== null) {
            $currentValue = trim(wp_strip_all_tags((string) ($block['innerHTML'] ?? '')));
            if ($currentValue !== '') {
                $valueType = $this->editable_inner_html_type($blockName) ?? 'plain_text';
                $path = 'block:' . implode('.', $pathSegments) . ':innerHTML';
                $fields[] = [
                    'id' => wpfixpilot_field_id('gutenberg', $path),
                    'path' => $path,
                    'label' => $this->block_label($blockName) . ' · content',
                    'value_type' => $valueType,
                    'current_value' => $valueType === 'rich_text'
                        ? (string) ($block['innerHTML'] ?? '')
                        : $currentValue,
                    'required' => true,
                    'max_length' => $this->max_length($valueType),
                ];
            }
        }

        return $fields;
    }

    /** @param array<int, array<string, mixed>> $blocks */
    private function normalize_blocks(array $blocks): array
    {
        $normalized = [];
        foreach ($blocks as $block) {
            if (!is_array($block)) {
                continue;
            }

            $normalized[] = $this->normalize_block($block);
        }

        return $normalized;
    }

    /** @return array<string, mixed> */
    private function normalize_block(array $block): array
    {
        $normalized = $block;
        $blockName = (string) ($block['blockName'] ?? '');
        $hasEditableAttribute = false;
        foreach ((array) ($normalized['attrs'] ?? []) as $key => $value) {
            if (
                is_string($value)
                && $this->editable_attribute_type($blockName, (string) $key) !== null
            ) {
                $normalized['attrs'][$key] = '__editable__';
                $hasEditableAttribute = true;
            }
        }

        if ($hasEditableAttribute || $this->editable_inner_html_type($blockName) !== null) {
            $normalized['innerHTML'] = '__editable__';
            $normalized['innerContent'] = ['__editable__'];
        }

        if (isset($normalized['innerBlocks']) && is_array($normalized['innerBlocks'])) {
            $normalized['innerBlocks'] = $this->normalize_blocks($normalized['innerBlocks']);
        }

        return $normalized;
    }

    /** @return array<string, mixed>|null */
    private function parse_path(string $path): ?array
    {
        if (
            preg_match(
                '/^block:([0-9]+(?:\.[0-9]+)*):(attr:([^:]+)|innerHTML)$/',
                $path,
                $matches
            ) !== 1
        ) {
            return null;
        }

        return [
            'segments' => array_map('intval', explode('.', $matches[1])),
            'kind' => str_starts_with($matches[2], 'attr:') ? 'attr' : 'innerHTML',
            'key' => $matches[3] ?? null,
        ];
    }

    /**
     * @param array<int, array<string, mixed>> $blocks
     * @param array<int, int> $segments
     */
    private function replace_block_value(
        array &$blocks,
        array $segments,
        string $kind,
        ?string $key,
        string $replacement
    ): bool {
        $index = array_shift($segments);
        if ($index === null || !isset($blocks[$index]) || !is_array($blocks[$index])) {
            return false;
        }

        if ($segments !== []) {
            if (
                !isset($blocks[$index]['innerBlocks'])
                || !is_array($blocks[$index]['innerBlocks'])
            ) {
                return false;
            }

            return $this->replace_block_value(
                $blocks[$index]['innerBlocks'],
                $segments,
                $kind,
                $key,
                $replacement
            );
        }

        if ($kind === 'attr') {
            if (
                $key === null
                || !isset($blocks[$index]['attrs'])
                || !is_array($blocks[$index]['attrs'])
                || !array_key_exists($key, $blocks[$index]['attrs'])
            ) {
                return false;
            }
            $blocks[$index]['attrs'][$key] = $replacement;
            $this->sync_inner_html_from_attrs($blocks[$index], $key);

            return true;
        }

        $blocks[$index]['innerHTML'] = $this->replace_wrapped_text(
            (string) ($blocks[$index]['innerHTML'] ?? ''),
            $replacement
        );
        $blocks[$index]['innerContent'] = [$blocks[$index]['innerHTML']];

        return true;
    }

    /** @param array<string, mixed> $block */
    private function sync_inner_html_from_attrs(array &$block, string $changedKey): void
    {
        $blockName = (string) ($block['blockName'] ?? '');
        if ($blockName === 'core/heading' && isset($block['attrs']['content'])) {
            $block['innerHTML'] = $this->replace_wrapped_text(
                (string) ($block['innerHTML'] ?? ''),
                (string) $block['attrs']['content']
            );
            $block['innerContent'] = [$block['innerHTML']];

            return;
        }

        if ($blockName === 'core/button') {
            if ($changedKey === 'url' && isset($block['attrs']['url'])) {
                $block['innerHTML'] = $this->replace_anchor_href(
                    (string) ($block['innerHTML'] ?? ''),
                    (string) $block['attrs']['url']
                );
            } elseif ($changedKey === 'text' && isset($block['attrs']['text'])) {
                $block['innerHTML'] = $this->replace_anchor_text(
                    (string) ($block['innerHTML'] ?? ''),
                    (string) $block['attrs']['text']
                );
            }
            $block['innerContent'] = [$block['innerHTML']];
        }
    }

    private function replace_wrapped_text(string $current, string $replacement): string
    {
        if (preg_match('/^(<[^>]+>).*?(<\/[^>]+>)$/s', $current, $parts) === 1) {
            return $parts[1] . $replacement . $parts[2];
        }

        return $replacement;
    }

    private function replace_anchor_href(string $current, string $replacement): string
    {
        if (preg_match('/<a\b[^>]*\shref=(["\'])[^"\']*\1/i', $current) !== 1) {
            return $current;
        }

        return (string) preg_replace_callback(
            '/(<a\b[^>]*\shref=)(["\'])([^"\']*)(\2)/i',
            static fn (array $matches): string => $matches[1] . $matches[2] . $replacement . $matches[4],
            $current,
            1
        );
    }

    private function replace_anchor_text(string $current, string $replacement): string
    {
        if (preg_match('/(<a\b[^>]*>).*?(<\/a>)/is', $current) !== 1) {
            return $current;
        }

        return (string) preg_replace(
            '/(<a\b[^>]*>).*?(<\/a>)/is',
            '$1' . $replacement . '$2',
            $current,
            1
        );
    }

    private function editable_attribute_type(string $blockName, string $key): ?string
    {
        if ($blockName === 'core/heading' && $key === 'content') {
            return 'heading';
        }
        if ($blockName === 'core/button' && $key === 'text') {
            return 'button_text';
        }
        if ($blockName === 'core/button' && $key === 'url') {
            return 'url';
        }

        return null;
    }

    private function editable_inner_html_type(string $blockName): ?string
    {
        if (in_array($blockName, ['core/paragraph', 'core/html', 'core/list'], true)) {
            return 'rich_text';
        }

        return null;
    }

    private function infer_semantic_role(string $blockName): string
    {
        if ($blockName === 'core/heading') {
            return 'hero';
        }
        if ($blockName === 'core/button') {
            return 'cta';
        }

        return 'content';
    }

    private function block_label(string $blockName): string
    {
        $name = str_replace('core/', '', $blockName);

        return $name !== '' ? $this->humanize_label($name) : 'Gutenberg block';
    }

    private function humanize_label(string $value): string
    {
        $value = str_replace(['_', '-', '/'], ' ', $value);

        return ucfirst($value);
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
