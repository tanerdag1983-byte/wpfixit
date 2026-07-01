<?php

declare(strict_types=1);

final class WPFixPilot_Elementor_Adapter implements
    WPFixPilot_Builder_Adapter,
    WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'elementor';
    }

    public function is_active(): bool
    {
        return defined('ELEMENTOR_VERSION');
    }

    public function uses_page(int $postId): bool
    {
        $document = $this->document($postId);

        return is_array($document) && $document !== [];
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
        return hash(
            'sha256',
            (string) get_post_meta($postId, '_elementor_data', true)
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
                    'Ongeldige Elementor-mapping.'
                );
            }

            $fieldId = $this->field_id_for_path($schema, (string) $path);
            if ($fieldId === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Elementor-element niet gevonden.'
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
            if (str_starts_with($metaKey, '_elementor_')) {
                $keys[] = $metaKey;
            }
        }

        if ((string) get_post_meta($postId, '_elementor_data', true) !== '') {
            $keys[] = '_elementor_data';
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
                'Elementor is niet actief.',
                ['status' => 409]
            );
        }

        $document = $this->document($postId);
        if (!is_array($document)) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Elementor-data ontbreekt.',
                ['status' => 500]
            );
        }

        $blocks = $this->schema_blocks($document);
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
        $document = $this->document($postId);
        if (!is_array($document)) {
            return '';
        }

        return hash('sha256', (string) wp_json_encode($this->normalize_elements($document)));
    }

    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        $document = $this->document($postId);
        if (!is_array($document)) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Elementor-data ontbreekt.',
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
                    'Ongeldige Elementor-mapping.',
                    ['status' => 500]
                );
            }

            if (
                !$this->replace_setting_value(
                    $document,
                    $target['element_id'],
                    $target['segments'],
                    (string) $value
                )
            ) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Elementor-element niet gevonden.',
                    ['status' => 500]
                );
            }
        }

        if (
            update_post_meta(
                $postId,
                '_elementor_data',
                wp_slash(wp_json_encode($document))
            ) === false
        ) {
            return new WP_Error(
                'wp_fixpilot_field_write_failed',
                'Elementor-data kon niet worden bijgewerkt.',
                ['status' => 500]
            );
        }

        return true;
    }

    /** @return array<int, array<string, mixed>>|WP_Error */
    private function document(int $postId): array|WP_Error
    {
        $raw = get_post_meta($postId, '_elementor_data', true);
        if (!is_string($raw) || trim($raw) === '') {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Elementor-data ontbreekt.',
                ['status' => 500]
            );
        }

        $document = json_decode($raw, true);
        if (!is_array($document)) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Elementor-data ontbreekt.',
                ['status' => 500]
            );
        }

        return $document;
    }

    /** @param array<int, array<string, mixed>> $elements */
    private function schema_blocks(array $elements): array
    {
        $blocks = [];
        foreach ($elements as $element) {
            if (!is_array($element)) {
                continue;
            }
            $blocks = array_merge($blocks, $this->blocks_from_element($element));
        }

        return $blocks;
    }

    /** @return array<int, array<string, mixed>> */
    private function blocks_from_element(array $element): array
    {
        $blocks = [];
        $elementId = (string) ($element['id'] ?? '');
        $settings = $element['settings'] ?? [];
        if ($elementId !== '' && is_array($settings)) {
            $fields = $this->collect_setting_fields($element, $settings, []);
            if ($fields !== []) {
                $blocks[] = [
                    'id' => wpfixpilot_field_id('elementor', 'block/' . $elementId),
                    'layout' => (string) ($element['widgetType'] ?? $element['elType'] ?? 'element'),
                    'label' => $this->element_label($element),
                    'semantic_role' => $this->infer_semantic_role($element),
                    'fields' => $fields,
                ];
            }
        }

        foreach ((array) ($element['elements'] ?? []) as $child) {
            if (!is_array($child)) {
                continue;
            }
            $blocks = array_merge($blocks, $this->blocks_from_element($child));
        }

        return $blocks;
    }

    /**
     * @param array<string, mixed> $element
     * @param array<int|string, mixed> $settings
     * @param array<int, string> $pathSegments
     * @return array<int, array<string, mixed>>
     */
    private function collect_setting_fields(
        array $element,
        array $settings,
        array $pathSegments
    ): array {
        $fields = [];
        foreach ($settings as $key => $value) {
            $segments = [...$pathSegments, (string) $key];
            if (is_array($value)) {
                $fields = array_merge(
                    $fields,
                    $this->collect_setting_fields($element, $value, $segments)
                );
                continue;
            }

            if (!is_string($value)) {
                continue;
            }

            $valueType = $this->editable_setting_type($element, $segments, $value);
            if ($valueType === null) {
                continue;
            }

            $fields[] = [
                'id' => wpfixpilot_field_id(
                    'elementor',
                    implode('/', array_merge(
                        [(string) ($element['id'] ?? ''), 'settings'],
                        $segments
                    ))
                ),
                'path' => 'element:' . (string) ($element['id'] ?? '') . ':settings:' . implode(
                    '/',
                    array_map('rawurlencode', $segments)
                ),
                'label' => $this->element_label($element) . ' · ' . $this->humanize_label((string) end($segments)),
                'value_type' => $valueType,
                'current_value' => $value,
                'required' => true,
                'max_length' => $this->max_length($valueType),
            ];
        }

        return $fields;
    }

    /** @param array<int, array<string, mixed>> $elements */
    private function normalize_elements(array $elements): array
    {
        $normalized = [];
        foreach ($elements as $element) {
            if (!is_array($element)) {
                continue;
            }
            $normalized[] = $this->normalize_element($element);
        }

        return $normalized;
    }

    /** @return array<string, mixed> */
    private function normalize_element(array $element): array
    {
        $normalized = $element;
        if (isset($normalized['settings']) && is_array($normalized['settings'])) {
            $normalized['settings'] = $this->normalize_setting_value(
                $element,
                $normalized['settings'],
                []
            );
        }
        if (isset($normalized['elements']) && is_array($normalized['elements'])) {
            $normalized['elements'] = $this->normalize_elements($normalized['elements']);
        }

        return $normalized;
    }

    /**
     * @param array<string, mixed> $element
     * @param array<int|string, mixed> $value
     * @param array<int, string> $pathSegments
     * @return array<int|string, mixed>
     */
    private function normalize_setting_value(
        array $element,
        array $value,
        array $pathSegments
    ): array {
        $normalized = [];
        foreach ($value as $key => $child) {
            $segments = [...$pathSegments, (string) $key];
            if (is_array($child)) {
                $normalized[$key] = $this->normalize_setting_value(
                    $element,
                    $child,
                    $segments
                );
                continue;
            }

            if (!is_string($child)) {
                $normalized[$key] = $child;
                continue;
            }

            $valueType = $this->editable_setting_type($element, $segments, $child);
            $normalized[$key] = $valueType === null
                ? $child
                : '__' . $valueType . '__';
        }

        return $normalized;
    }

    /**
     * @param array<int, array<string, mixed>> $elements
     * @param array<int, string> $segments
     */
    private function replace_setting_value(
        array &$elements,
        string $elementId,
        array $segments,
        string $replacement
    ): bool {
        foreach ($elements as &$element) {
            if (!is_array($element)) {
                continue;
            }

            if ((string) ($element['id'] ?? '') === $elementId) {
                if (
                    isset($element['settings'])
                    && is_array($element['settings'])
                    && $this->set_nested_value($element['settings'], $segments, $replacement)
                ) {
                    return true;
                }
            }

            if (
                isset($element['elements'])
                && is_array($element['elements'])
                && $this->replace_setting_value(
                    $element['elements'],
                    $elementId,
                    $segments,
                    $replacement
                )
            ) {
                return true;
            }
        }

        return false;
    }

    /** @return array<string, string>|null */
    private function parse_path(string $path): ?array
    {
        if (
            preg_match('/^element:([^:]+):settings:(.+)$/', $path, $matches) !== 1
        ) {
            return null;
        }

        return [
            'element_id' => $matches[1],
            'segments' => array_map('rawurldecode', explode('/', $matches[2])),
        ];
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

    /**
     * @param array<int, string> $segments
     */
    private function editable_setting_type(
        array $element,
        array $segments,
        string $value
    ): ?string {
        $last = strtolower((string) end($segments));
        $parent = strtolower((string) ($segments[count($segments) - 2] ?? ''));
        $widgetType = strtolower((string) ($element['widgetType'] ?? ''));

        if (
            $last === 'url'
            && in_array($parent, ['link', 'cta_link', 'button_link'], true)
        ) {
            return 'url';
        }

        if (in_array($last, ['editor', 'content', 'html'], true)) {
            return 'rich_text';
        }

        if (in_array($last, ['title', 'heading'], true)) {
            return 'heading';
        }

        if ($last === 'text' && str_contains($widgetType, 'button')) {
            return 'button_text';
        }

        if (in_array($last, ['text', 'description', 'caption', 'label'], true)) {
            return $this->contains_html_markup($value)
                ? 'rich_text'
                : 'plain_text';
        }

        return null;
    }

    private function element_label(array $element): string
    {
        $widgetType = (string) ($element['widgetType'] ?? '');
        if ($widgetType !== '') {
            return $widgetType;
        }

        $elementType = (string) ($element['elType'] ?? '');
        if ($elementType !== '') {
            return $elementType;
        }

        return 'element';
    }

    private function infer_semantic_role(array $element): string
    {
        $combined = strtolower($this->element_label($element));
        if (str_contains($combined, 'hero') || str_contains($combined, 'heading')) {
            return 'hero';
        }
        if (str_contains($combined, 'faq')) {
            return 'faq';
        }
        if (str_contains($combined, 'button') || str_contains($combined, 'cta')) {
            return 'cta';
        }

        return 'content';
    }

    private function humanize_label(string $value): string
    {
        $value = str_replace(['_', '-'], ' ', $value);

        return ucfirst($value);
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

    /**
     * @param array<int|string, mixed> $value
     * @param array<int, string> $segments
     */
    private function set_nested_value(
        array &$value,
        array $segments,
        string $replacement
    ): bool {
        if ($segments === []) {
            return false;
        }

        $cursor = &$value;
        foreach ($segments as $index => $segment) {
            if (!is_array($cursor) || !array_key_exists($segment, $cursor)) {
                return false;
            }
            if ($index === array_key_last($segments)) {
                $cursor[$segment] = $replacement;

                return true;
            }
            $cursor = &$cursor[$segment];
        }

        return false;
    }

    private function contains_html_markup(string $value): bool
    {
        return wp_strip_all_tags($value) !== $value;
    }
}
