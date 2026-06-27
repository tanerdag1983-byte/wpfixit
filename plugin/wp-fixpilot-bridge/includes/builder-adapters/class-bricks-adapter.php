<?php

declare(strict_types=1);

final class WPFixPilot_Bricks_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string
    {
        return 'bricks';
    }

    public function is_active(): bool
    {
        return defined('BRICKS_VERSION');
    }

    public function inspect(int $postId): array
    {
        $elements = get_post_meta($postId, '_bricks_page_content_2', true);
        if (!is_array($elements)) {
            return [];
        }
        $slots = [];
        $supported = ['text', 'content', 'title', 'buttonText'];
        foreach ($elements as $element) {
            $id = (string) ($element['id'] ?? '');
            $settings = $element['settings'] ?? [];
            if ($id === '' || !is_array($settings)) {
                continue;
            }
            foreach ($supported as $key) {
                if (!isset($settings[$key]) || !is_string($settings[$key])) {
                    continue;
                }
                $preview = trim(wp_strip_all_tags($settings[$key]));
                $slots[] = [
                    'path' => 'element:' . $id . ':settings:' . $key,
                    'label' => ($preview !== '' ? mb_substr($preview, 0, 80) : $key),
                    'value_type' => in_array($key, ['text', 'content'], true) ? 'html' : 'text',
                ];
            }
        }
        return $slots;
    }

    public function template_hash(int $postId): string
    {
        return hash('sha256', (string) wp_json_encode(get_post_meta($postId, '_bricks_page_content_2', true)));
    }
}
