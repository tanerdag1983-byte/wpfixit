<?php

declare(strict_types=1);

final class WPFixPilot_Post_Cloner
{
    private const EXCLUDED_META = [
        '_edit_lock',
        '_edit_last',
        '_wp_old_slug',
        '_wp_fixpilot_idempotency_key',
        '_wp_fixpilot_source_template',
        '_wp_fixpilot_source_blueprint_id',
        '_wp_fixpilot_blueprint',
        '_wp_fixpilot_blueprint_builder',
        '_wp_fixpilot_blueprint_version',
        '_wp_fixpilot_blueprint_page_type',
        '_wp_fixpilot_content_schema',
        '_wp_fixpilot_structure_hash',
        '_wp_fixpilot_seo_plugin',
    ];

    /**
     * @param array<int, string> $allowedMetaKeys
     */
    public function clone_page(
        int $sourceId,
        string $title,
        bool $asBlueprint,
        array $allowedMetaKeys
    ): int|WP_Error {
        $source = get_post($sourceId);
        if (!$source instanceof WP_Post || $source->post_type !== 'page') {
            return new WP_Error(
                'wp_fixpilot_source_missing',
                'Bronpagina niet gevonden.',
                ['status' => 404]
            );
        }

        $newId = wp_insert_post([
            'post_type' => 'page',
            'post_status' => 'draft',
            'post_title' => $title,
            'post_content' => (string) $source->post_content,
            'post_excerpt' => (string) $source->post_excerpt,
            'post_parent' => (int) $source->post_parent,
            'menu_order' => (int) $source->menu_order,
        ], true);
        if (is_wp_error($newId)) {
            return $newId;
        }

        $allowed = array_unique(array_merge(
            ['_thumbnail_id', '_wp_page_template'],
            array_map('strval', $allowedMetaKeys)
        ));

        foreach ((array) get_post_meta($sourceId) as $key => $values) {
            if (
                in_array((string) $key, self::EXCLUDED_META, true)
                || !in_array((string) $key, $allowed, true)
            ) {
                continue;
            }
            foreach ((array) $values as $value) {
                $metaWrite = add_post_meta(
                    (int) $newId,
                    (string) $key,
                    maybe_unserialize($value)
                );
                if ($metaWrite === false) {
                    return $this->failed_clone_error((int) $newId);
                }
            }
        }

        if (
            $asBlueprint
            && update_post_meta((int) $newId, '_wp_fixpilot_blueprint', '1') === false
        ) {
            return $this->failed_clone_error((int) $newId);
        }

        return (int) $newId;
    }

    private function failed_clone_error(int $cloneId): WP_Error
    {
        wp_delete_post($cloneId, true);
        if (get_post($cloneId) instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_clone_cleanup_failed',
                'De onvolledige kloon kon niet worden verwijderd.',
                ['status' => 500]
            );
        }

        return new WP_Error(
            'wp_fixpilot_clone_failed',
            'De pagina kon niet volledig worden gekloond.',
            ['status' => 500]
        );
    }
}
