<?php

declare(strict_types=1);

final class WPFixPilot_Page_Package_Controller
{
    /** @return array<int, WPFixPilot_Builder_Adapter> */
    public function adapters(): array
    {
        return [
            new WPFixPilot_Gutenberg_Adapter(),
            new WPFixPilot_Elementor_Adapter(),
            new WPFixPilot_Bricks_Adapter(),
            new WPFixPilot_WPBakery_Adapter(),
            new WPFixPilot_ACF_Adapter(),
        ];
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
}
