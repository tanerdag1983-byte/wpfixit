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

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error('wp_fixpilot_draft_missing', 'Conceptpagina niet gevonden.');
        }
        $replacements = [];
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic]) || !preg_match('/^shortcode:(\d+):content$/', $path, $match)) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige WPBakery-mapping.');
            }
            $replacements[(int) $match[1]] = (string) $values[$semantic];
        }
        $index = -1;
        $content = preg_replace_callback(
            '/\[(vc_(?:column_text|custom_heading|btn))\b([^\]]*)\](.*?)\[\/\1\]/s',
            static function (array $match) use (&$index, $replacements): string {
                $index++;
                $value = $replacements[$index] ?? $match[3];
                return '[' . $match[1] . $match[2] . ']' . $value . '[/' . $match[1] . ']';
            },
            (string) $post->post_content
        );
        if (!is_string($content) || count(array_filter(array_keys($replacements), static fn (int $key): bool => $key > $index)) > 0) {
            return new WP_Error('wp_fixpilot_slot_missing', 'WPBakery-element niet gevonden.');
        }
        $result = wp_update_post(['ID' => $postId, 'post_content' => $content, 'post_status' => 'draft'], true);
        return is_wp_error($result) ? $result : true;
    }
}
