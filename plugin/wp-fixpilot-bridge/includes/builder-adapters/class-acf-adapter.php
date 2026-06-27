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
            if (!is_array($field) || !in_array($field['type'] ?? '', ['text', 'textarea', 'wysiwyg', 'url'], true)) {
                continue;
            }
            $slots[] = [
                'path' => 'acf:' . (string) ($field['key'] ?? ''),
                'label' => (string) ($field['label'] ?? $field['name'] ?? 'ACF field'),
                'value_type' => ($field['type'] ?? '') === 'wysiwyg' ? 'html' : 'text',
            ];
        }
        return array_values(array_filter($slots, static fn (array $slot): bool => $slot['path'] !== 'acf:'));
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
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic]) || !str_starts_with($path, 'acf:')) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige ACF-mapping.');
            }
            $fieldKey = substr($path, 4);
            if ($fieldKey === '') {
                return new WP_Error('wp_fixpilot_slot_missing', 'ACF-veld kon niet worden bijgewerkt.');
            }
            update_field($fieldKey, (string) $values[$semantic], $postId);
        }
        return true;
    }
}
