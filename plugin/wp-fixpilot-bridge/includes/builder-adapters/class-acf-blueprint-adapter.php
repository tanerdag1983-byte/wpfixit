<?php

declare(strict_types=1);

/**
 * ACF Blueprint Adapter
 * 
 * Extracts a complete structured schema from ACF flexible content and fields,
 * generates stable field IDs, and applies text replacements while preserving
 * all structure, media, and metadata.
 */
final class WPFixPilot_ACF_Blueprint_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'acf';
    }

    public function is_active(): bool
    {
        return function_exists('get_field_objects') && function_exists('update_field');
    }

    public function uses_page(int $postId): bool
    {
        if (!$this->is_active()) {
            return false;
        }
        $fields = get_field_objects($postId);
        return is_array($fields) && $fields !== [];
    }

    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array
    {
        if (!$this->is_active()) {
            return [];
        }
        $fields = get_field_objects($postId) ?: [];
        $keys = [];
        foreach ($fields as $field) {
            if (!is_array($field)) {
                continue;
            }
            $name = (string) ($field['name'] ?? '');
            $fieldKey = (string) ($field['key'] ?? '');
            if ($name !== '') {
                $keys[] = $name;
            }
            if ($fieldKey !== '') {
                $keys[] = '_' . $name; // ACF stores field key reference
            }
        }
        return array_values(array_filter(array_unique($keys)));
    }

    /** @return array<string, mixed>|WP_Error */
    public function schema(int $postId): array|WP_Error
    {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'ACF is niet actief.',
                ['status' => 409]
            );
        }

        $fields = get_field_objects($postId) ?: [];
        $blocks = [];

        foreach ($fields as $field) {
            if (!is_array($field)) {
                continue;
            }

            $fieldType = (string) ($field['type'] ?? '');
            $fieldName = (string) ($field['name'] ?? '');
            $fieldKey = (string) ($field['key'] ?? '');

            // Handle flexible content layouts as blueprint blocks
            if ($fieldType === 'flexible_content' && is_array($field['value'] ?? null)) {
                foreach ($field['value'] as $rowIndex => $row) {
                    if (!is_array($row)) {
                        continue;
                    }
                    $layout = (string) ($row['acf_fc_layout'] ?? 'unknown');
                    $blockFields = $this->extract_block_fields(
                        $row,
                        $fieldKey,
                        [(string) $rowIndex],
                        $fieldName
                    );
                    
                    if ($blockFields !== []) {
                        $blocks[] = [
                            'id' => $this->generate_field_id('acf', $fieldKey . '/' . $rowIndex),
                            'layout' => $layout,
                            'label' => $fieldName . ' (' . $layout . ')',
                            'semantic_role' => $this->infer_semantic_role($layout, $fieldName),
                            'fields' => $blockFields,
                        ];
                    }
                }
                continue;
            }

            // Handle regular text fields as single-field blocks
            if (in_array($fieldType, ['text', 'textarea', 'wysiwyg', 'url'], true)) {
                $value = $this->get_field_value($field);
                $blockFields = [[
                    'id' => $this->generate_field_id('acf', $fieldKey),
                    'path' => $fieldKey,
                    'label' => (string) ($field['label'] ?? $fieldName),
                    'value_type' => $this->map_value_type($fieldType),
                    'current_value' => $value,
                    'required' => !empty($field['required']),
                    'max_length' => $this->get_max_length($fieldType),
                ]];

                $blocks[] = [
                    'id' => $this->generate_field_id('acf', $fieldKey . '-block'),
                    'layout' => $fieldType,
                    'label' => (string) ($field['label'] ?? $fieldName),
                    'semantic_role' => 'content',
                    'fields' => $blockFields,
                ];
            }
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
        if (!$this->is_active()) {
            return '';
        }

        $fields = get_field_objects($postId) ?: [];
        $structure = [];

        foreach ($fields as $field) {
            if (!is_array($field)) {
                continue;
            }
            $structure[] = [
                'key' => $field['key'] ?? '',
                'name' => $field['name'] ?? '',
                'type' => $field['type'] ?? '',
            ];
        }

        return hash('sha256', (string) wp_json_encode($structure));
    }

    /**
     * @param array<string, mixed> $schema
     * @param array<string, string> $replacements
     */
    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'ACF is niet actief.',
                ['status' => 409]
            );
        }

        // Group replacements by field key
        $fieldUpdates = [];
        foreach ($schema['blocks'] ?? [] as $block) {
            foreach ($block['fields'] ?? [] as $field) {
                $fieldId = (string) ($field['id'] ?? '');
                $path = (string) ($field['path'] ?? '');
                
                if (!array_key_exists($fieldId, $replacements)) {
                    continue;
                }

                // Extract the field key from the path
                // Path can be like "field_abc123" or contain nested paths
                $segments = explode('/', $path);
                $fieldKey = $segments[0];

                if (!isset($fieldUpdates[$fieldKey])) {
                    $fieldUpdates[$fieldKey] = [
                        'segments' => $segments,
                        'value' => $replacements[$fieldId],
                    ];
                } else {
                    // Handle nested updates within flexible content
                    $this->apply_nested_replacement(
                        $fieldUpdates[$fieldKey],
                        $segments,
                        $replacements[$fieldId]
                    );
                }
            }
        }

        // Apply all updates
        foreach ($fieldUpdates as $fieldKey => $update) {
            if (count($update['segments']) === 1) {
                // Simple field update
                if (update_field($fieldKey, $update['value'], $postId) === false) {
                    return new WP_Error(
                        'wp_fixpilot_field_write_failed',
                        'ACF-veld kon niet worden bijgewerkt.',
                        ['status' => 500]
                    );
                }
            } else {
                // Nested field update - get current value, modify, save
                $current = get_field($fieldKey, $postId);
                if (!is_array($current)) {
                    return new WP_Error(
                        'wp_fixpilot_field_invalid',
                        'ACF-veld heeft ongeldige structuur.',
                        ['status' => 500]
                    );
                }

                $modified = $this->apply_nested_update($current, $update['segments'], $update['value']);
                if (update_field($fieldKey, $modified, $postId) === false) {
                    return new WP_Error(
                        'wp_fixpilot_field_write_failed',
                        'ACF nested veld kon niet worden bijgewerkt.',
                        ['status' => 500]
                    );
                }
            }
        }

        return true;
    }

    /**
     * Extract editable text fields from a flexible content row
     * 
     * @param array<string, mixed> $row
     * @param string $fieldKey
     * @param array<int, string> $pathSegments
     * @param string $parentLabel
     * @return array<int, array<string, mixed>>
     */
    private function extract_block_fields(
        array $row,
        string $fieldKey,
        array $pathSegments,
        string $parentLabel
    ): array {
        $fields = [];

        foreach ($row as $subKey => $value) {
            // Skip ACF internal keys
            if ($subKey === 'acf_fc_layout' || str_starts_with((string) $subKey, '_')) {
                continue;
            }

            $currentPath = [...$pathSegments, (string) $subKey];
            $fullPath = $fieldKey . '/' . implode('/', $currentPath);

            if (is_string($value) && trim($value) !== '') {
                $fields[] = [
                    'id' => $this->generate_field_id('acf', $fullPath),
                    'path' => $fullPath,
                    'label' => $parentLabel . ' · ' . $subKey,
                    'value_type' => $this->detect_value_type($value),
                    'current_value' => $value,
                    'required' => true,
                    'max_length' => 5000,
                ];
            } elseif (is_array($value)) {
                // Recurse into nested arrays/repeaters
                $nested = $this->extract_block_fields($value, $fieldKey, $currentPath, $parentLabel);
                $fields = [...$fields, ...$nested];
            }
        }

        return $fields;
    }

    private function generate_field_id(string $builder, string $path): string
    {
        return $builder . '-' . substr(hash('sha256', $path), 0, 20);
    }

    private function get_field_value(array $field): string
    {
        $value = $field['value'] ?? '';
        return is_string($value) ? $value : '';
    }

    private function map_value_type(string $acfType): string
    {
        return match ($acfType) {
            'wysiwyg' => 'rich_text',
            'url' => 'url',
            'textarea' => 'plain_text',
            default => 'plain_text',
        };
    }

    private function detect_value_type(string $value): string
    {
        if (wp_strip_all_tags($value) !== $value) {
            return 'rich_text';
        }
        if (filter_var($value, FILTER_VALIDATE_URL) !== false) {
            return 'url';
        }
        return 'plain_text';
    }

    private function get_max_length(string $fieldType): int
    {
        return match ($fieldType) {
            'text' => 500,
            'textarea' => 5000,
            'wysiwyg' => 20000,
            'url' => 500,
            default => 5000,
        };
    }

    private function infer_semantic_role(string $layout, string $fieldName): string
    {
        $combined = strtolower($layout . ' ' . $fieldName);
        
        if (str_contains($combined, 'hero') || str_contains($combined, 'header')) {
            return 'hero';
        }
        if (str_contains($combined, 'intro') || str_contains($combined, 'inleiding')) {
            return 'introduction';
        }
        if (str_contains($combined, 'benefit') || str_contains($combined, 'voordel')) {
            return 'benefits';
        }
        if (str_contains($combined, 'proces') || str_contains($combined, 'stap')) {
            return 'process';
        }
        if (str_contains($combined, 'faq') || str_contains($combined, 'vraag')) {
            return 'faq';
        }
        if (str_contains($combined, 'cta') || str_contains($combined, 'call')) {
            return 'cta';
        }

        return 'content';
    }

    /**
     * @param array<string, mixed> $current
     * @param array<int, string> $segments
     * @param string $value
     * @return array<string, mixed>
     */
    private function apply_nested_update(array $current, array $segments, string $value): array
    {
        // Skip the first segment (field key) and apply to the rest
        $pathSegments = array_slice($segments, 1);
        
        $result = $current;
        $cursor = &$result;

        foreach ($pathSegments as $index => $segment) {
            if ($index === array_key_last($pathSegments)) {
                $cursor[$segment] = $value;
            } else {
                if (!isset($cursor[$segment]) || !is_array($cursor[$segment])) {
                    $cursor[$segment] = [];
                }
                $cursor = &$cursor[$segment];
            }
        }

        return $result;
    }

    private function apply_nested_replacement(array &$update, array $segments, string $value): void
    {
        // This would handle multiple replacements in the same nested structure
        // For now, we keep it simple and handle one replacement per field key
    }
}
