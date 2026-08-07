<?php

declare(strict_types=1);

final class WPFixPilot_Change_Controller
{
    /** @var array<int, WPFixPilot_Blueprint_Adapter>|null */
    private ?array $configuredAdapters;

    /** @param array<int, WPFixPilot_Blueprint_Adapter>|null $adapters */
    public function __construct(?array $adapters = null)
    {
        $this->configuredAdapters = $adapters;
    }

    /** @return array<string, mixed>|WP_Error */
    public function current_state(
        int $postId,
        ?string $seoPlugin = null
    ): array|WP_Error
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_not_found',
                'WordPress-object niet gevonden.',
                ['status' => 404]
            );
        }
        return $this->state($post, $seoPlugin);
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

    /** @return array<int, string> */
    public function seo_meta_keys(string $plugin): array
    {
        return match ($plugin) {
            'yoast' => [
                '_yoast_wpseo_title',
                '_yoast_wpseo_metadesc',
                '_yoast_wpseo_focuskw',
                '_yoast_wpseo_canonical',
                '_yoast_wpseo_meta-robots-noindex',
            ],
            'rank_math' => [
                'rank_math_title',
                'rank_math_description',
                'rank_math_focus_keyword',
                'rank_math_canonical_url',
                'rank_math_robots',
            ],
            'aioseo' => [
                '_aioseo_title',
                '_aioseo_description',
                '_aioseo_keyphrases',
                '_aioseo_canonical_url',
                '_aioseo_robots_noindex',
            ],
            default => [],
        };
    }

    /** @return array<string, mixed> */
    private function state(
        WP_Post $post,
        ?string $seoPlugin = null
    ): array
    {
        $keys = array_merge(
            $this->seo_meta_keys('yoast'),
            $this->seo_meta_keys('rank_math'),
            $this->seo_meta_keys('aioseo'),
            ['_wp_fixpilot_redirect_to']
        );
        $postId = (int) $post->ID;
        $featuredImageId = function_exists('get_post_thumbnail_id')
            ? (int) get_post_thumbnail_id($postId)
            : (int) get_post_meta($postId, '_thumbnail_id', true);
        $values = [
            'title' => (string) $post->post_title,
            'slug' => (string) $post->post_name,
            'url' => function_exists('get_permalink')
                ? (string) get_permalink($post)
                : '',
            'content' => (string) $post->post_content,
            'page_template' => get_post_meta(
                $postId,
                '_wp_page_template',
                true
            ),
            'featured_image_id' => $featuredImageId,
            'featured_image_alt' => $featuredImageId > 0
                ? (string) get_post_meta(
                    $featuredImageId,
                    '_wp_attachment_image_alt',
                    true
                )
                : null,
            'builders' => $this->builder_values($postId),
        ];
        foreach ($keys as $key) {
            $values[$key] = get_post_meta($postId, $key, true);
        }
        return [
            'id' => $postId,
            'content_hash' => hash(
                'sha256',
                (string) wp_json_encode($values)
            ),
            'values' => $this->semantic_values(
                $values,
                $seoPlugin ?? $this->detected_seo_plugin(),
                $postId
            ),
        ];
    }

    /**
     * @param array<string, mixed> $values
     * @return array<string, mixed>
     */
    private function semantic_values(
        array $values,
        string $seoPlugin,
        int $postId
    ): array
    {
        if ($seoPlugin === 'rank_math') {
            $keys = [
                'seo_title' => 'rank_math_title',
                'meta_description' => 'rank_math_description',
                'focus_keyword' => 'rank_math_focus_keyword',
                'canonical' => 'rank_math_canonical_url',
                'noindex' => 'rank_math_robots',
            ];
        } elseif ($seoPlugin === 'aioseo') {
            $keys = [
                'seo_title' => '_aioseo_title',
                'meta_description' => '_aioseo_description',
                'focus_keyword' => '_aioseo_keyphrases',
                'canonical' => '_aioseo_canonical_url',
                'noindex' => '_aioseo_robots_noindex',
            ];
        } else {
            $keys = [
                'seo_title' => '_yoast_wpseo_title',
                'meta_description' => '_yoast_wpseo_metadesc',
                'focus_keyword' => '_yoast_wpseo_focuskw',
                'canonical' => '_yoast_wpseo_canonical',
                'noindex' => '_yoast_wpseo_meta-robots-noindex',
            ];
        }
        $focusKeyword = $values[$keys['focus_keyword']] ?? '';
        if ($seoPlugin === 'aioseo') {
            $keyphrases = is_string($focusKeyword)
                ? json_decode($focusKeyword, true)
                : $focusKeyword;
            $focusKeyword = is_array($keyphrases)
                ? (string) ($keyphrases['focus']['keyphrase'] ?? '')
                : '';
        }
        $noindex = $values[$keys['noindex']] ?? false;
        if (is_array($noindex)) {
            $noindex = in_array('noindex', $noindex, true);
        } elseif (is_string($noindex)) {
            $noindex = in_array($noindex, ['1', 'true'], true);
        }
        return [
            'title' => $values['title'],
            'seo_title' => $values[$keys['seo_title']] ?? '',
            'meta_description' => $values[$keys['meta_description']] ?? '',
            'focus_keyword' => $focusKeyword,
            'canonical' => $values[$keys['canonical']] ?? '',
            'noindex' => (bool) $noindex,
            'content' => $values['content'],
            'internal_links' => $values['content'],
            'redirect' => $values['_wp_fixpilot_redirect_to'] ?? '',
            'featured_image_id' => $values['featured_image_id'],
            'featured_image_alt' => $values['featured_image_alt'],
            'builders' => $values['builders'],
            'visible_builder_content' => $this->visible_builder_content(
                $postId,
                $values['builders']
            ),
        ];
    }

    /**
     * @param array<string, mixed> $builders
     * @return array<int, string>
     */
    private function visible_builder_content(int $postId, array $builders): array
    {
        $content = [];
        foreach ($this->builder_adapters() as $adapter) {
            if (!isset($builders[$adapter->key()])) {
                continue;
            }
            $schema = $adapter->schema($postId);
            if ($schema instanceof WP_Error) {
                continue;
            }
            foreach ((array) ($schema['blocks'] ?? []) as $block) {
                foreach ((array) ($block['fields'] ?? []) as $field) {
                    $value = $field['current_value'] ?? null;
                    if (!is_string($value) || trim($value) === '') {
                        continue;
                    }
                    $type = (string) ($field['value_type'] ?? '');
                    if ($type === 'heading') {
                        $value = '<h2>' . htmlspecialchars($value, ENT_QUOTES) . '</h2>';
                    } elseif ($type === 'url') {
                        $value = '<a href="' . htmlspecialchars($value, ENT_QUOTES) . '"></a>';
                    } elseif (!in_array($type, ['html', 'rich_text', 'plain_text'], true)) {
                        continue;
                    }
                    $content[] = $value;
                }
            }
        }
        if ($this->has_builder_image($builders)) {
            $content[] = '<img alt="">';
        }

        return $content;
    }

    private function has_builder_image(mixed $value, string $key = ''): bool
    {
        if (is_string($value) && in_array(substr(trim($value), 0, 1), ['[', '{'], true)) {
            $decoded = json_decode($value, true);
            if (is_array($decoded)) {
                return $this->has_builder_image($decoded, $key);
            }
        }
        if (!is_array($value)) {
            return false;
        }
        foreach ($value as $childKey => $child) {
            $childKey = strtolower((string) $childKey);
            if (
                preg_match('/(^|_)(image|photo|picture|thumbnail)($|_)/', $childKey) === 1
                && $this->is_image_value($child)
            ) {
                return true;
            }
            if ($this->has_builder_image($child, $childKey)) {
                return true;
            }
        }

        return false;
    }

    private function is_image_value(mixed $value): bool
    {
        if (is_int($value) || (is_string($value) && ctype_digit($value))) {
            return (int) $value > 0;
        }
        if (is_string($value)) {
            return str_contains(strtolower($value), '<img')
                || preg_match('/\.(jpe?g|png|gif|webp|avif|svg)(?:[?#]|$)/i', $value) === 1;
        }
        if (!is_array($value)) {
            return false;
        }

        return (isset($value['id']) && (int) $value['id'] > 0)
            || (isset($value['url']) && $this->is_image_value($value['url']))
            || (isset($value['source_url']) && $this->is_image_value($value['source_url']));
    }

    /** @return array<string, mixed> */
    private function builder_values(int $postId): array
    {
        $values = [];
        foreach ($this->builder_adapters() as $adapter) {
            if (!$adapter->is_active() || !$adapter->uses_page($postId)) {
                continue;
            }
            $meta = [];
            foreach ($adapter->clone_meta_keys($postId) as $key) {
                $meta[$key] = get_post_meta($postId, $key, true);
            }
            ksort($meta);
            $values[$adapter->key()] = [
                'structure_hash' => $adapter->structure_hash($postId),
                'meta' => $meta,
            ];
        }
        ksort($values);

        return $values;
    }

    /** @return array<int, WPFixPilot_Blueprint_Adapter> */
    private function builder_adapters(): array
    {
        if ($this->configuredAdapters !== null) {
            return $this->configuredAdapters;
        }
        $adapters = [];
        foreach ([
            'WPFixPilot_ACF_Adapter',
            'WPFixPilot_Elementor_Adapter',
            'WPFixPilot_WPBakery_Adapter',
            'WPFixPilot_Bricks_Adapter',
            'WPFixPilot_Gutenberg_Adapter',
        ] as $className) {
            if (class_exists($className)) {
                $adapters[] = new $className();
            }
        }

        return $adapters;
    }

    private function detected_seo_plugin(): string
    {
        if (defined('RANK_MATH_VERSION')) {
            return 'rank_math';
        }
        if (defined('AIOSEO_VERSION')) {
            return 'aioseo';
        }

        return 'yoast';
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
