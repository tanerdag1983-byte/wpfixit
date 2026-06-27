<?php

declare(strict_types=1);

final class WPFixPilot_WPBakery_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string
    {
        return 'wpbakery';
    }

    public function is_active(): bool
    {
        return defined('WPB_VC_VERSION');
    }

    public function inspect(int $postId): array
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return [];
        }
        preg_match_all(
            '/\[(vc_(?:column_text|custom_heading|btn))\b[^\]]*\](.*?)\[\/\1\]/s',
            (string) $post->post_content,
            $matches,
            PREG_SET_ORDER
        );
        $slots = [];
        foreach ($matches as $index => $match) {
            $preview = trim(wp_strip_all_tags((string) ($match[2] ?? '')));
            $slots[] = [
                'path' => 'shortcode:' . $index . ':content',
                'label' => ($preview !== '' ? mb_substr($preview, 0, 80) : (string) $match[1]),
                'value_type' => $match[1] === 'vc_custom_heading' ? 'text' : 'html',
            ];
        }
        return $slots;
    }

    public function template_hash(int $postId): string
    {
        $post = get_post($postId);
        return hash('sha256', $post instanceof WP_Post ? (string) $post->post_content : '');
    }
}
