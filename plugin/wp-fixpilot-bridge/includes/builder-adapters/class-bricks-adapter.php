<?php

declare(strict_types=1);

final class WPFixPilot_Bricks_Adapter implements
    WPFixPilot_Builder_Adapter,
    WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'bricks';
    }

    public function is_active(): bool
    {
        return defined('BRICKS_VERSION');
    }

    public function uses_page(int $postId): bool
    {
        $elements = get_post_meta($postId, '_bricks_page_content_2', true);

        return is_array($elements) && $elements !== [];
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
            (string) wp_json_encode(get_post_meta($postId, '_bricks_page_content_2', true))
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
                    'Ongeldige Bricks-mapping.'
                );
            }

            $fieldId = $this->field_id_for_path($schema, (string) $path);
            if ($fieldId === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Bricks-element niet gevonden.'
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
            if (str_starts_with($metaKey, '_bricks_')) {
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
                'Bricks is niet actief.',
                ['status' => 409]
            );
        }

        $elements = get_post_meta($postId, '_bricks_page_content_2', true);
        if (!is_array($elements)) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Bricks-data ontbreekt.',
                ['status' => 500]
            );
        }

        $blocks = [];
        foreach ($elements as $element) {
            if (!is_array($element)) {
                continue;
            }
            $elementId = (string) ($element['id'] ?? '');
            $settings = $element['settings'] ?? [];
            if ($elementId === '' || !is_array($settings)) {
                continue;
            }

            $fields = $this->collect_setting_fields($element, $settings, []);
            if ($fields === []) {
                continue;
            }

            $blocks[] = [
                'id' => wpfixpilot_field_id('bricks', 'block/' . $elementId),
                'layout' => (string) ($element['name'] ?? 'element'),
                'label' => (string) ($element['name'] ?? 'element'),
                'semantic_role' => $this->infer_semantic_role((string) ($element['name'] ?? '')),
                'fields' => $fields,
            ];
        }

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
        $elements = get_post_meta($postId, '_bricks_page_content_2', true);
        if (!is_array($elements)) {
            return '';
        }

        return hash('sha256', (string) wp_json_encode($this->normalize_elements($elements)));
    }

    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        $elements = get_post_meta($postId, '_bricks_page_content_2', true);
        if (!is_array($elements)) {
            return new WP_Error(
                'wp_fixpilot_builder_data_missing',
                'Bricks-data ontbreekt.',
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
                    'Ongeldige Bricks-mapping.',
                    ['status' => 500]
                );
            }

            if (
                !$this->replace_setting_value(
                    $elements,
                    $target['element_id'],
                    $target['segments'],
                    (string) $value
                )
            ) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'Bricks-element niet gevonden.',
                    ['status' => 500]
                );
            }
        }

        if (update_post_meta($postId, '_bricks_page_content_2', $elements) === false) {
            return new WP_Error(
                'wp_fixpilot_field_write_failed',
                'Bricks-data kon niet worden bijgewerkt.',
                ['status' => 500]
            );
        }

        return true;
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
                    'bricks',
                    implode('/', array_merge(
                        [(string) ($element['id'] ?? ''), 'settings'],
                        $segments
                    ))
                ),
                'path' => 'element:' . (string) ($element['id'] ?? '') . ':settings:' . implode(
                    '/',
                    array_map('rawurlencode', $segments)
                ),
                'label' => (string) ($element['name'] ?? 'element') . ' · ' . $this->humanize_label((string) end($segments)),
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

            $normalizedElement = $element;
            if (isset($normalizedElement['settings']) && is_array($normalizedElement['settings'])) {
                $normalizedElement['settings'] = $this->normalize_settings(
                    $element,
                    $normalizedElement['settings'],
                    []
                );
            }
            $normalized[] = $normalizedElement;
        }

        return $normalized;
    }

    /**
     * @param array<string, mixed> $element
     * @param array<int|string, mixed> $settings
     * @param array<int, string> $pathSegments
     * @return array<int|string, mixed>
     */
    private function normalize_settings(
        array $element,
        array $settings,
        array $pathSegments
    ): array {
        $normalized = [];
        foreach ($settings as $key => $value) {
            $segments = [...$pathSegments, (string) $key];
            if (is_array($value)) {
                $normalized[$key] = $this->normalize_settings(
                    $element,
                    $value,
                    $segments
                );
                continue;
            }

            if (!is_string($value)) {
                $normalized[$key] = $value;
                continue;
            }

            $valueType = $this->editable_setting_type($element, $segments, $value);
            $normalized[$key] = $valueType === null
                ? $value
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

            if ((string) ($element['id'] ?? '') !== $elementId) {
                continue;
            }

            if (
                !isset($element['settings'])
                || !is_array($element['settings'])
            ) {
                return false;
            }

            return $this->set_nested_value($element['settings'], $segments, $replacement);
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
        $name = strtolower((string) ($element['name'] ?? ''));

        if ($last === 'url' && in_array($parent, ['link', 'button_link'], true)) {
            return 'url';
        }
        if ($last === 'text' && str_contains($name, 'button')) {
            return 'button_text';
        }
        if ($last === 'title') {
            return 'heading';
        }
        if (in_array($last, ['text', 'content', 'label'], true)) {
            return wp_strip_all_tags($value) !== $value
                ? 'rich_text'
                : 'plain_text';
        }

        return null;
    }

    private function infer_semantic_role(string $name): string
    {
        $name = strtolower($name);
        if (str_contains($name, 'heading') || str_contains($name, 'hero')) {
            return 'hero';
        }
        if (str_contains($name, 'button') || str_contains($name, 'cta')) {
            return 'cta';
        }

        return 'content';
    }

    private function humanize_label(string $value): string
    {
        $value = str_replace(['_', '-'], ' ', $value);

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
}
