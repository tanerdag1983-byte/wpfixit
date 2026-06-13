<?php

declare(strict_types=1);

final class WPFixPilot_Change_Controller
{
    /** @return array<string, mixed>|WP_Error */
    public function current_state(int $postId): array|WP_Error
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_not_found',
                'WordPress-object niet gevonden.',
                ['status' => 404]
            );
        }
        return $this->state($post);
    }

    /** @return array<string, mixed>|WP_Error */
    public function apply(int $postId, array $payload): array|WP_Error
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_not_found',
                'WordPress-object niet gevonden.',
                ['status' => 404]
            );
        }
        $current = $this->state($post);
        $expected = (string) ($payload['expected_content_hash'] ?? '');
        if ($expected === '' || !hash_equals($current['content_hash'], $expected)) {
            return new WP_Error(
                'wp_fixpilot_conflict',
                'De pagina is gewijzigd sinds het voorstel is gemaakt.',
                ['status' => 409]
            );
        }
        try {
            $changes = $this->adapter()->build_change_set(
                (string) ($payload['change_type'] ?? ''),
                $payload['value'] ?? null
            );
        } catch (InvalidArgumentException $error) {
            return new WP_Error(
                'wp_fixpilot_invalid_change',
                $error->getMessage(),
                ['status' => 400]
            );
        }
        if (isset($changes['post'])) {
            $result = wp_update_post(
                array_merge(['ID' => $postId], $changes['post']),
                true
            );
            if (is_wp_error($result)) {
                return $result;
            }
        }
        foreach (($changes['meta'] ?? []) as $key => $value) {
            update_post_meta($postId, (string) $key, $value);
        }
        if (isset($changes['redirect'])) {
            update_post_meta(
                $postId,
                '_wp_fixpilot_redirect_to',
                esc_url_raw((string) $changes['redirect'])
            );
        }
        clean_post_cache($postId);
        $updated = get_post($postId);
        return $updated instanceof WP_Post
            ? $this->state($updated)
            : new WP_Error('wp_fixpilot_update_failed', 'Update mislukt.');
    }

    /** @return array<string, mixed> */
    private function state(WP_Post $post): array
    {
        $keys = [
            '_yoast_wpseo_title',
            '_yoast_wpseo_metadesc',
            '_yoast_wpseo_canonical',
            '_yoast_wpseo_meta-robots-noindex',
            'rank_math_title',
            'rank_math_description',
            'rank_math_canonical_url',
            'rank_math_robots',
            '_aioseo_title',
            '_aioseo_description',
            '_aioseo_canonical_url',
            '_aioseo_robots_noindex',
            '_wp_fixpilot_redirect_to',
        ];
        $values = ['content' => (string) $post->post_content];
        foreach ($keys as $key) {
            $values[$key] = get_post_meta((int) $post->ID, $key, true);
        }
        return [
            'id' => (int) $post->ID,
            'content_hash' => hash(
                'sha256',
                (string) wp_json_encode($values)
            ),
            'values' => $this->semantic_values($values),
        ];
    }

    /**
     * @param array<string, mixed> $values
     * @return array<string, mixed>
     */
    private function semantic_values(array $values): array
    {
        if (defined('RANK_MATH_VERSION')) {
            $keys = [
                'seo_title' => 'rank_math_title',
                'meta_description' => 'rank_math_description',
                'canonical' => 'rank_math_canonical_url',
                'noindex' => 'rank_math_robots',
            ];
        } elseif (defined('AIOSEO_VERSION')) {
            $keys = [
                'seo_title' => '_aioseo_title',
                'meta_description' => '_aioseo_description',
                'canonical' => '_aioseo_canonical_url',
                'noindex' => '_aioseo_robots_noindex',
            ];
        } else {
            $keys = [
                'seo_title' => '_yoast_wpseo_title',
                'meta_description' => '_yoast_wpseo_metadesc',
                'canonical' => '_yoast_wpseo_canonical',
                'noindex' => '_yoast_wpseo_meta-robots-noindex',
            ];
        }
        $noindex = $values[$keys['noindex']] ?? false;
        if (is_array($noindex)) {
            $noindex = in_array('noindex', $noindex, true);
        } elseif (is_string($noindex)) {
            $noindex = in_array($noindex, ['1', 'true'], true);
        }
        return [
            'seo_title' => $values[$keys['seo_title']] ?? '',
            'meta_description' => $values[$keys['meta_description']] ?? '',
            'canonical' => $values[$keys['canonical']] ?? '',
            'noindex' => (bool) $noindex,
            'content' => $values['content'],
            'internal_links' => $values['content'],
            'redirect' => $values['_wp_fixpilot_redirect_to'] ?? '',
        ];
    }

    private function adapter(): WPFixPilot_SEO_Adapter
    {
        if (defined('RANK_MATH_VERSION')) {
            return new WPFixPilot_Rank_Math_Adapter();
        }
        if (defined('AIOSEO_VERSION')) {
            return new WPFixPilot_AIOSEO_Adapter();
        }
        return new WPFixPilot_Yoast_Adapter();
    }
}
