<?php

declare(strict_types=1);

final class WPFixPilot_Page_Package_Controller
{
    /** @var array<int, WPFixPilot_Builder_Adapter>|null */
    private ?array $configuredAdapters;

    /** @param array<int, WPFixPilot_Builder_Adapter>|null $adapters */
    public function __construct(?array $adapters = null)
    {
        $this->configuredAdapters = $adapters;
    }

    /** @return array<int, WPFixPilot_Builder_Adapter> */
    public function adapters(): array
    {
        return $this->configuredAdapters ?? [
            new WPFixPilot_Gutenberg_Adapter(),
            new WPFixPilot_Elementor_Adapter(),
            new WPFixPilot_Bricks_Adapter(),
            new WPFixPilot_WPBakery_Adapter(),
            new WPFixPilot_ACF_Adapter(),
        ];
    }

    /** @return array<string, mixed>|WP_Error */
    public function create_draft(array $payload): array|WP_Error
    {
        $required = [
            'template_id', 'expected_template_hash', 'builder', 'mapping',
            'seo_plugin', 'idempotency_key', 'package',
        ];
        foreach ($required as $key) {
            if (!isset($payload[$key]) || $payload[$key] === '') {
                return new WP_Error(
                    'wp_fixpilot_page_package_invalid',
                    'Het paginapakket is niet compleet.',
                    ['status' => 400]
                );
            }
        }
        $idempotencyKey = sanitize_text_field((string) $payload['idempotency_key']);
        $existing = get_posts([
            'post_type' => 'page',
            'post_status' => 'any',
            'meta_key' => '_wp_fixpilot_idempotency_key',
            'meta_value' => $idempotencyKey,
            'posts_per_page' => 1,
            'fields' => 'ids',
        ]);
        if ($existing !== []) {
            return $this->draft_response((int) $existing[0]);
        }

        $templateId = (int) $payload['template_id'];
        $template = get_post($templateId);
        if (!$template instanceof WP_Post || $template->post_type !== 'page') {
            return new WP_Error(
                'wp_fixpilot_template_not_found',
                'Templatepagina niet gevonden.',
                ['status' => 404]
            );
        }
        $adapter = $this->adapter((string) $payload['builder']);
        if ($adapter instanceof WP_Error) {
            return $adapter;
        }
        if (!hash_equals(
            (string) $payload['expected_template_hash'],
            $adapter->template_hash($templateId)
        )) {
            return new WP_Error(
                'wp_fixpilot_template_conflict',
                'De template is gewijzigd. Valideer het paginapakket opnieuw.',
                ['status' => 409]
            );
        }
        if ($this->seo_plugin() !== sanitize_key((string) $payload['seo_plugin'])) {
            return new WP_Error(
                'wp_fixpilot_seo_plugin_conflict',
                'De actieve SEO-plugin komt niet overeen met het paginapakket.',
                ['status' => 409]
            );
        }
        $package = (array) $payload['package'];
        foreach (['title', 'slug', 'seo_title', 'meta_description', 'focus_keyword', 'hero_title', 'introduction_html', 'sections', 'faq', 'cta'] as $key) {
            if (!isset($package[$key])) {
                return new WP_Error('wp_fixpilot_page_package_invalid', 'Pagina-inhoud ontbreekt.', ['status' => 400]);
            }
        }

        $draftId = wp_insert_post([
            'post_type' => 'page',
            'post_status' => 'draft',
            'post_title' => sanitize_text_field((string) $package['title']),
            'post_name' => sanitize_title((string) $package['slug']),
            'post_content' => (string) $template->post_content,
            'post_excerpt' => (string) $template->post_excerpt,
            'post_parent' => (int) $template->post_parent,
            'menu_order' => (int) $template->menu_order,
            'page_template' => get_page_template_slug($templateId),
        ], true);
        if (is_wp_error($draftId)) {
            return $draftId;
        }
        $draftId = (int) $draftId;
        try {
            $this->copy_template_meta($templateId, $draftId);
            update_post_meta($draftId, '_wp_fixpilot_idempotency_key', $idempotencyKey);
            update_post_meta($draftId, '_wp_fixpilot_source_template', $templateId);
            $write = $adapter->write(
                $draftId,
                (array) $payload['mapping'],
                $this->slot_values($package)
            );
            if (is_wp_error($write)) {
                wp_delete_post($draftId, true);
                return $write;
            }
            $seoWrite = $this->write_seo(
                $draftId,
                (string) $payload['seo_plugin'],
                $package
            );
            if (is_wp_error($seoWrite)) {
                wp_delete_post($draftId, true);
                return $seoWrite;
            }
            wp_update_post(['ID' => $draftId, 'post_status' => 'draft']);
            return $this->draft_response($draftId, $adapter->template_hash($draftId));
        } catch (Throwable $error) {
            wp_delete_post($draftId, true);
            return new WP_Error(
                'wp_fixpilot_draft_failed',
                'Het WordPress-concept kon niet volledig worden aangemaakt.',
                ['status' => 500]
            );
        }
    }

    /** @return array<string, mixed> */
    public function builders(): array
    {
        return [
            'builders' => array_values(array_map(
                static fn (WPFixPilot_Builder_Adapter $adapter): string => $adapter->key(),
                array_filter(
                    $this->adapters(),
                    static fn (WPFixPilot_Builder_Adapter $adapter): bool => $adapter->is_active()
                )
            )),
            'seo_plugin' => $this->seo_plugin(),
        ];
    }

    /** @return array<string, mixed>|WP_Error */
    public function inspect(int $postId, string $builder): array|WP_Error
    {
        if (!get_post($postId) instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_template_not_found',
                'Templatepagina niet gevonden.',
                ['status' => 404]
            );
        }
        foreach ($this->adapters() as $adapter) {
            if ($adapter->key() !== $builder) {
                continue;
            }
            if (!$adapter->is_active()) {
                return new WP_Error(
                    'wp_fixpilot_builder_inactive',
                    'De gekozen builder is niet actief.',
                    ['status' => 409]
                );
            }
            return [
                'builder' => $adapter->key(),
                'seo_plugin' => $this->seo_plugin(),
                'template_hash' => $adapter->template_hash($postId),
                'slots' => $adapter->inspect($postId),
            ];
        }
        return new WP_Error(
            'wp_fixpilot_builder_unsupported',
            'De gekozen builder wordt niet ondersteund.',
            ['status' => 400]
        );
    }

    public function seo_plugin(): ?string
    {
        if (defined('WPSEO_VERSION')) {
            return 'yoast';
        }
        if (defined('RANK_MATH_VERSION')) {
            return 'rank_math';
        }
        if (defined('AIOSEO_VERSION')) {
            return 'aioseo';
        }
        return null;
    }

    private function adapter(string $builder): WPFixPilot_Builder_Adapter|WP_Error
    {
        foreach ($this->adapters() as $adapter) {
            if ($adapter->key() === sanitize_key($builder)) {
                if (!$adapter->is_active()) {
                    return new WP_Error('wp_fixpilot_builder_inactive', 'De gekozen builder is niet actief.', ['status' => 409]);
                }
                return $adapter;
            }
        }
        return new WP_Error('wp_fixpilot_builder_unsupported', 'De gekozen builder wordt niet ondersteund.', ['status' => 400]);
    }

    /** @return array<string, string> */
    private function slot_values(array $package): array
    {
        $sectionHtml = '';
        foreach ((array) $package['sections'] as $section) {
            $section = (array) $section;
            $sectionHtml .= '<section><h2>' . esc_html((string) ($section['heading'] ?? '')) . '</h2>'
                . wp_kses_post((string) ($section['body_html'] ?? '')) . '</section>';
        }
        $links = '';
        foreach ((array) ($package['internal_links'] ?? []) as $link) {
            $link = (array) $link;
            $links .= '<li><a href="' . esc_url((string) ($link['url'] ?? '')) . '">'
                . esc_html((string) ($link['anchor'] ?? '')) . '</a></li>';
        }
        if ($links !== '') {
            $sectionHtml .= '<nav aria-label="Gerelateerde pagina’s"><ul>' . $links . '</ul></nav>';
        }
        $faqHtml = '';
        foreach ((array) $package['faq'] as $faq) {
            $faq = (array) $faq;
            $faqHtml .= '<details><summary>' . esc_html((string) ($faq['question'] ?? ''))
                . '</summary>' . wp_kses_post((string) ($faq['answer_html'] ?? '')) . '</details>';
        }
        $cta = (array) $package['cta'];
        return [
            'hero_title' => esc_html((string) $package['hero_title']),
            'introduction' => wp_kses_post((string) $package['introduction_html']),
            'main_content' => $sectionHtml,
            'faq' => $faqHtml,
            'cta_title' => esc_html((string) ($cta['title'] ?? '')),
            'cta_text' => wp_kses_post((string) ($cta['body_html'] ?? ''))
                . '<p><a href="' . esc_url((string) ($cta['button_url'] ?? '')) . '">'
                . esc_html((string) ($cta['button_label'] ?? '')) . '</a></p>',
        ];
    }

    private function copy_template_meta(int $templateId, int $draftId): void
    {
        $excluded = ['_edit_lock', '_edit_last', '_wp_old_slug'];
        foreach ((array) get_post_meta($templateId) as $key => $values) {
            if (in_array((string) $key, $excluded, true) || str_starts_with((string) $key, '_yoast_wpseo_') || str_starts_with((string) $key, 'rank_math_') || str_starts_with((string) $key, '_aioseo_')) {
                continue;
            }
            foreach ((array) $values as $value) {
                add_post_meta($draftId, (string) $key, maybe_unserialize($value));
            }
        }
    }

    private function write_seo(int $postId, string $plugin, array $package): bool|WP_Error
    {
        $adapters = [
            'yoast' => new WPFixPilot_Yoast_Adapter(),
            'rank_math' => new WPFixPilot_Rank_Math_Adapter(),
            'aioseo' => new WPFixPilot_AIOSEO_Adapter(),
        ];
        if (!isset($adapters[$plugin])) {
            return new WP_Error('wp_fixpilot_seo_plugin_unsupported', 'SEO-plugin wordt niet ondersteund.');
        }
        foreach ([
            'seo_title' => (string) $package['seo_title'],
            'meta_description' => (string) $package['meta_description'],
            'focus_keyword' => (string) $package['focus_keyword'],
        ] as $type => $value) {
            $change = $adapters[$plugin]->build_change_set($type, $value);
            foreach ((array) ($change['meta'] ?? []) as $key => $metaValue) {
                update_post_meta($postId, (string) $key, $metaValue);
            }
        }
        return true;
    }

    /** @return array<string, mixed> */
    private function draft_response(int $postId, string $contentHash = ''): array
    {
        return [
            'wordpress_object_id' => $postId,
            'edit_url' => get_edit_post_link($postId, 'raw'),
            'status' => 'draft',
            'content_hash' => $contentHash,
        ];
    }
}
