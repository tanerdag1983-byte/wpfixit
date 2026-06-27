<?php

declare(strict_types=1);

final class WPFixPilot_Elementor_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string
    {
        return 'elementor';
    }

    public function is_active(): bool
    {
        return defined('ELEMENTOR_VERSION');
    }

    public function inspect(int $postId): array
    {
        $document = json_decode((string) get_post_meta($postId, '_elementor_data', true), true);
        if (!is_array($document)) {
            return [];
        }
        $slots = [];
        $this->walk($document, $slots);
        return $slots;
    }

    public function template_hash(int $postId): string
    {
        return hash('sha256', (string) get_post_meta($postId, '_elementor_data', true));
    }

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        $document = json_decode((string) get_post_meta($postId, '_elementor_data', true), true);
        if (!is_array($document)) {
            return new WP_Error('wp_fixpilot_builder_data_missing', 'Elementor-data ontbreekt.');
        }
        foreach ($mapping as $semantic => $path) {
            $parts = explode(':', $path);
            if (count($parts) !== 4 || $parts[0] !== 'element' || $parts[2] !== 'settings' || !isset($values[$semantic])) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige Elementor-mapping.');
            }
            if (!$this->replace_setting($document, $parts[1], $parts[3], (string) $values[$semantic])) {
                return new WP_Error('wp_fixpilot_slot_missing', 'Elementor-element niet gevonden.');
            }
        }
        update_post_meta($postId, '_elementor_data', wp_slash(wp_json_encode($document)));
        return true;
    }

    private function replace_setting(array &$elements, string $id, string $key, string $value): bool
    {
        foreach ($elements as &$element) {
            if ((string) ($element['id'] ?? '') === $id && isset($element['settings'][$key])) {
                $element['settings'][$key] = $value;
                return true;
            }
            if (isset($element['elements']) && is_array($element['elements']) && $this->replace_setting($element['elements'], $id, $key, $value)) {
                return true;
            }
        }
        return false;
    }

    /** @param array<int, array<string, mixed>> $elements */
    private function walk(array $elements, array &$slots): void
    {
        $supported = ['title', 'text', 'editor', 'content', 'button_text', 'description'];
        foreach ($elements as $element) {
            $id = (string) ($element['id'] ?? '');
            $settings = $element['settings'] ?? [];
            if ($id !== '' && is_array($settings)) {
                foreach ($supported as $key) {
                    if (!isset($settings[$key]) || !is_string($settings[$key])) {
                        continue;
                    }
                    $preview = trim(wp_strip_all_tags($settings[$key]));
                    $slots[] = [
                        'path' => 'element:' . $id . ':settings:' . $key,
                        'label' => ($preview !== '' ? mb_substr($preview, 0, 80) : $key),
                        'value_type' => in_array($key, ['editor', 'content'], true) ? 'html' : 'text',
                    ];
                }
            }
            $children = $element['elements'] ?? [];
            if (is_array($children) && $children !== []) {
                $this->walk($children, $slots);
            }
        }
    }
}
