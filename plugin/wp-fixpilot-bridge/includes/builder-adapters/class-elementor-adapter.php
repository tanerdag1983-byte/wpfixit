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
