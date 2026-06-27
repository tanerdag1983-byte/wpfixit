<?php

declare(strict_types=1);

final class WPFixPilot_ACF_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string
    {
        return 'acf';
    }

    public function is_active(): bool
    {
        return function_exists('get_field_objects');
    }

    public function inspect(int $postId): array
    {
        if (!function_exists('get_field_objects')) {
            return [];
        }
        $fields = get_field_objects($postId) ?: [];
        $slots = [];
        foreach ($fields as $field) {
            if (!is_array($field)) {
                continue;
            }
            $fieldKey = (string) ($field['key'] ?? '');
            $label = (string) ($field['label'] ?? $field['name'] ?? 'ACF field');
            if (in_array($field['type'] ?? '', ['text', 'textarea', 'wysiwyg', 'url'], true)) {
                $slots[] = [
                    'path' => 'acf:' . $fieldKey,
                    'label' => $label,
                    'value_type' => ($field['type'] ?? '') === 'wysiwyg' ? 'html' : 'text',
                ];
                continue;
            }
            if ($fieldKey !== '' && is_array($field['value'] ?? null)) {
                $this->nested_slots(
                    $field['value'],
                    $fieldKey,
                    [],
                    $label,
                    $slots
                );
            }
        }
        return array_values(array_filter(
            $slots,
            static fn (array $slot): bool => $slot['path'] !== 'acf:'
        ));
    }

    public function template_hash(int $postId): string
    {
        $fields = function_exists('get_field_objects') ? (get_field_objects($postId) ?: []) : [];
        return hash('sha256', (string) wp_json_encode($fields));
    }

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        if (!function_exists('update_field')) {
            return new WP_Error('wp_fixpilot_builder_inactive', 'ACF is niet actief.');
        }
        $fields = get_field_objects($postId) ?: [];
        $nestedUpdates = [];
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic])) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige ACF-mapping.');
            }
            if (str_starts_with($path, 'acf-value:')) {
                if (!preg_match('/^acf-value:([^:]+):(.+)$/', $path, $match)) {
                    return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige ACF-mapping.');
                }
                $fieldKey = (string) $match[1];
                if (!array_key_exists($fieldKey, $nestedUpdates)) {
                    $field = $this->field_by_key($fields, $fieldKey);
                    if ($field === null || !is_array($field['value'] ?? null)) {
                        return new WP_Error('wp_fixpilot_slot_missing', 'ACF-veld kon niet worden bijgewerkt.');
                    }
                    $nestedUpdates[$fieldKey] = $field['value'];
                }
                $segments = array_map('rawurldecode', explode('/', (string) $match[2]));
                if (!$this->replace_nested_value(
                    $nestedUpdates[$fieldKey],
                    $segments,
                    (string) $values[$semantic]
                )) {
                    return new WP_Error('wp_fixpilot_slot_missing', 'ACF-veld kon niet worden bijgewerkt.');
                }
                continue;
            }
            if (!str_starts_with($path, 'acf:')) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige ACF-mapping.');
            }
            $fieldKey = substr($path, 4);
            if ($fieldKey === '' || update_field($fieldKey, (string) $values[$semantic], $postId) === false) {
                return new WP_Error('wp_fixpilot_slot_missing', 'ACF-veld kon niet worden bijgewerkt.');
            }
        }
        foreach ($nestedUpdates as $fieldKey => $value) {
            if (update_field((string) $fieldKey, $value, $postId) === false) {
                return new WP_Error('wp_fixpilot_slot_missing', 'ACF-veld kon niet worden bijgewerkt.');
            }
        }
        return true;
    }

    private function nested_slots(
        mixed $value,
        string $fieldKey,
        array $segments,
        string $label,
        array &$slots
    ): void {
        if (is_array($value)) {
            foreach ($value as $key => $child) {
                if ($key === 'acf_fc_layout' || str_starts_with((string) $key, '_')) {
                    continue;
                }
                $this->nested_slots(
                    $child,
                    $fieldKey,
                    [...$segments, (string) $key],
                    $label,
                    $slots
                );
            }
            return;
        }
        if (!is_string($value) || trim($value) === '') {
            return;
        }
        $preview = trim(wp_strip_all_tags($value));
        if ($preview === '') {
            $preview = (string) end($segments);
        }
        $slots[] = [
            'path' => 'acf-value:' . $fieldKey . ':' . implode(
                '/',
                array_map('rawurlencode', $segments)
            ),
            'label' => $label . ' · ' . mb_substr($preview, 0, 80),
            'value_type' => wp_strip_all_tags($value) !== $value ? 'html' : 'text',
        ];
    }

    private function field_by_key(array $fields, string $fieldKey): ?array
    {
        foreach ($fields as $field) {
            if (is_array($field) && ($field['key'] ?? null) === $fieldKey) {
                return $field;
            }
        }
        return null;
    }

    private function replace_nested_value(
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
