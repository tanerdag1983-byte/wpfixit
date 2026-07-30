<?php

declare(strict_types=1);

final class WPFixPilot_Template_Snapshot_Store
{
    public const POST_TYPE = 'wpfixpilot_snapshot';
    private const OPTIMIZATION_META = [
        'job_id' => '_wp_fixpilot_snapshot_job_id',
        'snapshot_kind' => '_wp_fixpilot_snapshot_kind',
        'source_post_id' => '_wp_fixpilot_source_page_id',
        'source_url' => '_wp_fixpilot_source_url',
        'source_content_hash' => '_wp_fixpilot_source_content_hash',
        'captured_at' => '_wp_fixpilot_captured_at',
    ];

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

    /** @param array<string, mixed> $capture */
    public function save_optimization_capture(int $postId, array $capture): bool
    {
        if (!$this->is_snapshot($postId)) {
            return false;
        }
        foreach (self::OPTIMIZATION_META as $field => $metaKey) {
            if (!array_key_exists($field, $capture)) {
                return false;
            }
            update_post_meta($postId, $metaKey, $capture[$field]);
            if (
                (string) get_post_meta($postId, $metaKey, true)
                !== (string) $capture[$field]
            ) {
                return false;
            }
        }

        return true;
    }

    public function find_for_job(string $jobId): ?int
    {
        if ($jobId === '') {
            return null;
        }
        $matches = get_posts([
            'post_type' => self::POST_TYPE,
            'post_status' => 'private',
            'fields' => 'ids',
            'numberposts' => 1,
            'suppress_filters' => true,
            'meta_query' => [[
                'key' => self::OPTIMIZATION_META['job_id'],
                'value' => $jobId,
            ]],
        ]);

        return isset($matches[0]) ? (int) $matches[0] : null;
    }

    /** @return array<string, mixed>|WP_Error */
    public function load(int $postId): array|WP_Error
    {
        $snapshot = $this->assert_snapshot($postId);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $schema = get_post_meta(
            $postId,
            '_wp_fixpilot_content_schema',
            true
        );

        return [
            'snapshot_id' => $postId,
            'snapshot_version' => (int) get_post_meta(
                $postId,
                '_wp_fixpilot_snapshot_version',
                true
            ),
            'structure_hash' => (string) get_post_meta(
                $postId,
                '_wp_fixpilot_structure_hash',
                true
            ),
            'schema_version' => (string) get_post_meta(
                $postId,
                '_wp_fixpilot_snapshot_schema_version',
                true
            ),
            'schema' => is_array($schema) ? $schema : [],
            'snapshot_kind' => (string) get_post_meta(
                $postId,
                self::OPTIMIZATION_META['snapshot_kind'],
                true
            ),
            'source_post_id' => (int) get_post_meta(
                $postId,
                self::OPTIMIZATION_META['source_post_id'],
                true
            ),
            'source_url' => (string) get_post_meta(
                $postId,
                self::OPTIMIZATION_META['source_url'],
                true
            ),
            'source_content_hash' => (string) get_post_meta(
                $postId,
                self::OPTIMIZATION_META['source_content_hash'],
                true
            ),
            'captured_at' => (string) get_post_meta(
                $postId,
                self::OPTIMIZATION_META['captured_at'],
                true
            ),
        ];
    }
}
