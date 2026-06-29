<?php

declare(strict_types=1);

final class WPFixPilot_Blueprint_Controller
{
    /** @var array<int, WPFixPilot_Blueprint_Adapter>|null */
    private ?array $configuredAdapters;

    private ?WPFixPilot_Post_Cloner $configuredCloner;

    /** @param array<int, WPFixPilot_Blueprint_Adapter>|null $adapters */
    public function __construct(
        ?array $adapters = null,
        ?WPFixPilot_Post_Cloner $cloner = null
    ) {
        $this->configuredAdapters = $adapters;
        $this->configuredCloner = $cloner;
    }

    /** @return array<int, WPFixPilot_Blueprint_Adapter> */
    public function adapters(): array
    {
        return $this->configuredAdapters ?? [];
    }

    /** @return array<string, mixed>|WP_Error */
    public function capture(array $payload): array|WP_Error
    {
        $required = ['source_page_id', 'name', 'page_type', 'builder', 'version'];
        foreach ($required as $key) {
            if (!isset($payload[$key]) || $payload[$key] === '') {
                return new WP_Error(
                    'wp_fixpilot_blueprint_invalid',
                    'De blueprint-aanvraag is niet compleet.',
                    ['status' => 400]
                );
            }
        }

        $sourceId = (int) $payload['source_page_id'];
        $name = sanitize_text_field((string) $payload['name']);
        $pageType = sanitize_key((string) $payload['page_type']);
        $version = (int) $payload['version'];

        $adapter = $this->adapter((string) $payload['builder']);
        if (is_wp_error($adapter)) {
            return $adapter;
        }
        if (!$adapter->uses_page($sourceId)) {
            return new WP_Error(
                'wp_fixpilot_blueprint_builder_mismatch',
                'De gekozen builder hoort niet bij deze pagina.',
                ['status' => 409]
            );
        }

        $blueprintId = $this->cloner()->clone_page(
            $sourceId,
            $name,
            true,
            $adapter->clone_meta_keys($sourceId)
        );
        if (is_wp_error($blueprintId)) {
            return $blueprintId;
        }
        $blueprintId = (int) $blueprintId;

        try {
            $schema = $adapter->schema($blueprintId);
            if (is_wp_error($schema)) {
                wp_delete_post($blueprintId, true);
                return $schema;
            }
            $structureHash = $adapter->structure_hash($blueprintId);

            update_post_meta($blueprintId, '_wp_fixpilot_source_page_id', $sourceId);
            update_post_meta($blueprintId, '_wp_fixpilot_blueprint_builder', $adapter->key());
            update_post_meta($blueprintId, '_wp_fixpilot_blueprint_version', $version);
            update_post_meta($blueprintId, '_wp_fixpilot_blueprint_page_type', $pageType);
            update_post_meta($blueprintId, '_wp_fixpilot_structure_hash', $structureHash);
            update_post_meta($blueprintId, '_wp_fixpilot_content_schema', $schema);
            if ($this->seo_plugin() !== null) {
                update_post_meta(
                    $blueprintId,
                    '_wp_fixpilot_seo_plugin',
                    (string) $this->seo_plugin()
                );
            }

            return $this->blueprint_response($blueprintId, $schema, $structureHash);
        } catch (Throwable $error) {
            wp_delete_post($blueprintId, true);
            return new WP_Error(
                'wp_fixpilot_blueprint_failed',
                'De blueprint kon niet volledig worden vastgelegd.',
                ['status' => 500]
            );
        }
    }

    /** @return array<string, mixed>|WP_Error */
    public function read(int $blueprintId): array|WP_Error
    {
        $blueprint = $this->blueprint($blueprintId);
        if (is_wp_error($blueprint)) {
            return $blueprint;
        }

        $snapshot = $this->current_blueprint_snapshot($blueprintId);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }

        return $this->blueprint_response(
            $blueprintId,
            $snapshot['schema'],
            $snapshot['structure_hash']
        );
    }

    /** @return array<string, mixed>|WP_Error */
    public function create_draft(int $blueprintId, array $payload): array|WP_Error
    {
        $required = [
            'expected_version',
            'expected_structure_hash',
            'idempotency_key',
            'replacements',
            'seo',
        ];
        foreach ($required as $key) {
            if (!isset($payload[$key]) || $payload[$key] === '') {
                return new WP_Error(
                    'wp_fixpilot_blueprint_invalid',
                    'De blueprint-aanvraag is niet compleet.',
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

        $blueprint = $this->blueprint($blueprintId);
        if (is_wp_error($blueprint)) {
            return $blueprint;
        }

        $storedVersion = (int) get_post_meta(
            $blueprintId,
            '_wp_fixpilot_blueprint_version',
            true
        );
        if ($storedVersion !== (int) $payload['expected_version']) {
            return new WP_Error(
                'wp_fixpilot_blueprint_conflict',
                'De blueprint-versie is gewijzigd. Vernieuw eerst de gegevens.',
                ['status' => 409]
            );
        }

        $snapshot = $this->current_blueprint_snapshot($blueprintId);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }

        $currentHash = $snapshot['structure_hash'];
        if (
            $currentHash === ''
            || !hash_equals((string) $payload['expected_structure_hash'], $currentHash)
        ) {
            return new WP_Error(
                'wp_fixpilot_blueprint_conflict',
                'De blueprint-structuur is gewijzigd. Vernieuw eerst de gegevens.',
                ['status' => 409]
            );
        }

        $schema = $snapshot['schema'];
        $replacements = (array) $payload['replacements'];
        $fieldIds = $this->field_ids($schema);
        foreach (array_keys($replacements) as $fieldId) {
            if (!in_array((string) $fieldId, $fieldIds, true)) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_field_unknown',
                    'Onbekend blueprint-veld.',
                    ['status' => 400]
                );
            }
        }

        $adapter = $snapshot['adapter'];

        $draftId = $this->cloner()->clone_page(
            $blueprintId,
            (string) $blueprint->post_title,
            false,
            $adapter->clone_meta_keys($blueprintId)
        );
        if (is_wp_error($draftId)) {
            return $draftId;
        }
        $draftId = (int) $draftId;

        try {
            update_post_meta($draftId, '_wp_fixpilot_idempotency_key', $idempotencyKey);
            update_post_meta($draftId, '_wp_fixpilot_source_blueprint_id', $blueprintId);
            update_post_meta($draftId, '_wp_fixpilot_blueprint_version', $storedVersion);

            $write = $adapter->apply_replacements($draftId, $schema, $replacements);
            if (is_wp_error($write)) {
                wp_delete_post($draftId, true);
                return $write;
            }

            $seoWrite = $this->write_seo($draftId, (array) $payload['seo']);
            if (is_wp_error($seoWrite)) {
                wp_delete_post($draftId, true);
                return $seoWrite;
            }

            wp_update_post(['ID' => $draftId, 'post_status' => 'draft']);

            return $this->draft_response($draftId, $currentHash);
        } catch (Throwable $error) {
            wp_delete_post($draftId, true);
            return new WP_Error(
                'wp_fixpilot_draft_failed',
                'Het WordPress-concept kon niet volledig worden aangemaakt.',
                ['status' => 500]
            );
        }
    }

    /** @return array<string, mixed>|WP_Error */
    public function delete(int $blueprintId): array|WP_Error
    {
        $blueprint = $this->blueprint($blueprintId);
        if (is_wp_error($blueprint)) {
            return $blueprint;
        }

        wp_delete_post($blueprintId, true);

        return [
            'status' => 'deleted',
            'wordpress_blueprint_id' => $blueprintId,
        ];
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

    private function cloner(): WPFixPilot_Post_Cloner
    {
        return $this->configuredCloner ?? new WPFixPilot_Post_Cloner();
    }

    private function adapter(string $builder): WPFixPilot_Blueprint_Adapter|WP_Error
    {
        foreach ($this->adapters() as $adapter) {
            if ($adapter->key() !== sanitize_key($builder)) {
                continue;
            }
            if (!$adapter->is_active()) {
                return new WP_Error(
                    'wp_fixpilot_builder_inactive',
                    'De gekozen builder is niet actief.',
                    ['status' => 409]
                );
            }
            return $adapter;
        }

        return new WP_Error(
            'wp_fixpilot_builder_unsupported',
            'De gekozen builder wordt nog niet ondersteund.',
            ['status' => 400]
        );
    }

    private function blueprint(int $blueprintId): WP_Post|WP_Error
    {
        $post = get_post($blueprintId);
        if (
            !$post instanceof WP_Post
            || $post->post_type !== 'page'
            || get_post_meta($blueprintId, '_wp_fixpilot_blueprint', true) !== '1'
        ) {
            return new WP_Error(
                'wp_fixpilot_blueprint_not_found',
                'Blueprintpagina niet gevonden.',
                ['status' => 404]
            );
        }

        return $post;
    }

    /** @return array{adapter: WPFixPilot_Blueprint_Adapter, schema: array<string, mixed>, structure_hash: string}|WP_Error */
    private function current_blueprint_snapshot(int $blueprintId): array|WP_Error
    {
        $builder = (string) get_post_meta(
            $blueprintId,
            '_wp_fixpilot_blueprint_builder',
            true
        );
        $adapter = $this->adapter($builder);
        if (is_wp_error($adapter)) {
            return $adapter;
        }

        $schema = $adapter->schema($blueprintId);
        if (is_wp_error($schema)) {
            return $schema;
        }
        if (!is_array($schema) || !isset($schema['schema_version'], $schema['blocks'])) {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-inhoud is ongeldig.',
                ['status' => 500]
            );
        }

        return [
            'adapter' => $adapter,
            'schema' => $schema,
            'structure_hash' => $adapter->structure_hash($blueprintId),
        ];
    }

    /**
     * @param array<string, mixed> $schema
     * @return array<int, string>
     */
    private function field_ids(array $schema): array
    {
        $fieldIds = [];
        foreach ((array) ($schema['blocks'] ?? []) as $block) {
            foreach ((array) ($block['fields'] ?? []) as $field) {
                if (isset($field['id']) && $field['id'] !== '') {
                    $fieldIds[] = (string) $field['id'];
                }
            }
        }
        return $fieldIds;
    }

    /** @return array<string, mixed> */
    private function blueprint_response(
        int $blueprintId,
        array $schema,
        string $structureHash
    ): array {
        return [
            'status' => 'ready',
            'source_page_id' => (int) get_post_meta(
                $blueprintId,
                '_wp_fixpilot_source_page_id',
                true
            ),
            'wordpress_blueprint_id' => $blueprintId,
            'builder' => (string) get_post_meta(
                $blueprintId,
                '_wp_fixpilot_blueprint_builder',
                true
            ),
            'page_type' => (string) get_post_meta(
                $blueprintId,
                '_wp_fixpilot_blueprint_page_type',
                true
            ),
            'version' => (int) get_post_meta(
                $blueprintId,
                '_wp_fixpilot_blueprint_version',
                true
            ),
            'structure_hash' => $structureHash,
            'content_schema' => $schema,
            'seo_plugin' => (string) get_post_meta(
                $blueprintId,
                '_wp_fixpilot_seo_plugin',
                true
            ),
        ];
    }

    /** @return array<string, mixed> */
    private function draft_response(int $postId, string $structureHash = ''): array
    {
        return [
            'wordpress_object_id' => $postId,
            'edit_url' => get_edit_post_link($postId, 'raw'),
            'status' => 'draft',
            'content_hash' => $structureHash,
        ];
    }

    private function write_seo(int $postId, array $seo): bool|WP_Error
    {
        $plugin = $this->seo_plugin();
        $adapters = [
            'yoast' => new WPFixPilot_Yoast_Adapter(),
            'rank_math' => new WPFixPilot_Rank_Math_Adapter(),
            'aioseo' => new WPFixPilot_AIOSEO_Adapter(),
        ];
        if ($plugin === null || !isset($adapters[$plugin])) {
            return new WP_Error(
                'wp_fixpilot_seo_plugin_unsupported',
                'SEO-plugin wordt niet ondersteund.',
                ['status' => 409]
            );
        }

        $changes = [
            'seo_title' => (string) ($seo['title'] ?? ''),
            'meta_description' => (string) ($seo['description'] ?? ''),
            'focus_keyword' => (string) ($seo['keyword'] ?? ''),
        ];
        foreach ($changes as $type => $value) {
            if ($value === '') {
                continue;
            }
            $change = $adapters[$plugin]->build_change_set($type, $value);
            foreach ((array) ($change['meta'] ?? []) as $key => $metaValue) {
                update_post_meta($postId, (string) $key, $metaValue);
            }
        }

        return true;
    }
}
