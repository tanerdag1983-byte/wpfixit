<?php

declare(strict_types=1);

final class WPFixPilot_Template_Snapshot_Store
{
    public const POST_TYPE = 'wpfixpilot_snapshot';

    public function register(): void
    {
        register_post_type(self::POST_TYPE, [
            'label' => 'WP FixPilot snapshots',
            'public' => false,
            'publicly_queryable' => false,
            'show_ui' => false,
            'show_in_rest' => false,
            'exclude_from_search' => true,
            'rewrite' => false,
            'query_var' => false,
            'supports' => ['title', 'editor', 'excerpt', 'custom-fields'],
        ]);
    }

    public function is_snapshot(int $postId): bool
    {
        $post = get_post($postId);

        return $post instanceof WP_Post && $post->post_type === self::POST_TYPE;
    }

    public function assert_snapshot(int $postId): WP_Post|WP_Error
    {
        $post = get_post($postId);
        if ($post instanceof WP_Post && $post->post_type === self::POST_TYPE) {
            return $post;
        }

        return new WP_Error(
            'wp_fixpilot_blueprint_not_found',
            'Blueprintpagina niet gevonden.',
            ['status' => 404]
        );
    }
}
