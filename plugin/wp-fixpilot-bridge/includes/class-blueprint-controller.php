<?php

declare(strict_types=1);

final class WPFixPilot_Blueprint_Controller
{
    private const ALLOWED_PAGE_TYPES = [
        'service',
        'brand',
        'location',
        'blog',
        'generic',
    ];

    private const ALLOWED_SEMANTIC_ROLES = [
        'hero',
        'introduction',
        'benefits',
        'process',
        'faq',
        'cta',
        'content',
    ];

    private const ALLOWED_VALUE_TYPES = [
        'plain_text',
        'rich_text',
        'heading',
        'button_text',
        'url',
    ];

    /** @var array<int, WPFixPilot_Blueprint_Adapter>|null */
    private ?array $configuredAdapters;

    private ?WPFixPilot_Post_Cloner $configuredCloner;

    private ?Closure $configuredSeoPluginDetector;

    /** @param array<int, WPFixPilot_Blueprint_Adapter>|null $adapters */
    public function __construct(
        ?array $adapters = null,
        ?WPFixPilot_Post_Cloner $cloner = null,
        ?Closure $seoPluginDetector = null
    ) {
        $this->configuredAdapters = $adapters;
        $this->configuredCloner = $cloner;
        $this->configuredSeoPluginDetector = $seoPluginDetector;
    }

    /** @return array<int, WPFixPilot_Blueprint_Adapter> */
    public function adapters(): array
    {
        return $this->configuredAdapters ?? [];
    }

    /** @return array<string, mixed>|WP_Error */
    public function capture(array $payload): array|WP_Error
    {
        $required = ['source_page_id', 'name', 'page_type', 'version'];
        if (!$this->has_exact_keys($payload, $required)) {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }
        foreach ($required as $key) {
            if (!isset($payload[$key]) || $payload[$key] === '') {
                return new WP_Error(
                    'wp_fixpilot_blueprint_invalid',
                    'De blueprint-aanvraag is niet compleet.',
                    ['status' => 400]
                );
            }
        }

        $sourceId = $this->source_page_id($payload['source_page_id']);
        if (is_wp_error($sourceId)) {
            return $sourceId;
        }
        $name = sanitize_text_field((string) $payload['name']);
        if ($name === '') {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }

        $pageType = sanitize_key((string) $payload['page_type']);
        if (!in_array($pageType, self::ALLOWED_PAGE_TYPES, true)) {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }

        $version = filter_var(
            $payload['version'],
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );
        if ($version === false) {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }

        $source = $this->source_page($sourceId);
        if (is_wp_error($source)) {
            return $source;
        }

        $adapter = $this->detect_adapter($sourceId);
        if (is_wp_error($adapter)) {
            return $adapter;
        }

        $capturedSeoPlugin = $this->detected_seo_plugin_snapshot();
        if ($capturedSeoPlugin === '') {
            return new WP_Error(
                'wp_fixpilot_seo_plugin_unsupported',
                'SEO-plugin wordt niet ondersteund.',
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
                $cleanup = $this->cleanup_blueprint($blueprintId);
                if (is_wp_error($cleanup)) {
                    return $cleanup;
                }
                return $schema;
            }
            $structureHash = $adapter->structure_hash($blueprintId);
            $snapshotValidation = $this->validate_snapshot_contract(
                $schema,
                $structureHash
            );
            if (is_wp_error($snapshotValidation)) {
                $cleanup = $this->cleanup_blueprint($blueprintId);
                if (is_wp_error($cleanup)) {
                    return $cleanup;
                }
                return $snapshotValidation;
            }

            $captureMeta = [
                '_wp_fixpilot_source_page_id' => $sourceId,
                '_wp_fixpilot_blueprint_builder' => $adapter->key(),
                '_wp_fixpilot_blueprint_version' => $version,
                '_wp_fixpilot_blueprint_page_type' => $pageType,
                '_wp_fixpilot_structure_hash' => $structureHash,
                '_wp_fixpilot_content_schema' => $schema,
                '_wp_fixpilot_seo_plugin' => $capturedSeoPlugin,
            ];
            foreach ($captureMeta as $key => $value) {
                if (!$this->verified_update_post_meta($blueprintId, $key, $value)) {
                    $cleanup = $this->cleanup_blueprint($blueprintId);
                    if (is_wp_error($cleanup)) {
                        return $cleanup;
                    }

                    return $this->blueprint_failed_error();
                }
            }

            return $this->blueprint_response($blueprintId, $schema, $structureHash, true);
        } catch (Throwable $error) {
            $cleanup = $this->cleanup_blueprint($blueprintId);
            if (is_wp_error($cleanup)) {
                return $cleanup;
            }

            return $this->blueprint_failed_error();
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
            $snapshot['structure_hash'],
            false
        );
    }

    /** @return array<string, mixed>|WP_Error */
    public function create_draft(int $blueprintId, array $payload): array|WP_Error
    {
        $validatedPayload = $this->validate_create_draft_payload($payload);
        if (is_wp_error($validatedPayload)) {
            return $validatedPayload;
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
        if ($storedVersion !== $validatedPayload['expected_version']) {
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
            || !hash_equals($validatedPayload['expected_structure_hash'], $currentHash)
        ) {
            return new WP_Error(
                'wp_fixpilot_blueprint_conflict',
                'De blueprint-structuur is gewijzigd. Vernieuw eerst de gegevens.',
                ['status' => 409]
            );
        }

        $schema = $snapshot['schema'];
        $replacements = $this->validate_replacements_against_schema(
            $validatedPayload['replacements'],
            $schema,
            $validatedPayload['approved_urls']
        );
        if (is_wp_error($replacements)) {
            return $replacements;
        }
        $requestHash = $this->request_hash(
            $replacements,
            $validatedPayload['seo'],
            $validatedPayload['approved_urls']
        );
        $capturedSeoPlugin = $this->captured_seo_plugin($blueprintId);
        if (
            !hash_equals(
                $capturedSeoPlugin,
                $this->detected_seo_plugin_snapshot()
            )
        ) {
            return new WP_Error(
                'wp_fixpilot_blueprint_conflict',
                'De actieve SEO-plugin is gewijzigd. Vernieuw eerst de blueprint.',
                ['status' => 409]
            );
        }

        $idempotencyKey = $validatedPayload['idempotency_key'];
        $existing = get_posts([
            'post_type' => 'page',
            'post_status' => 'any',
            'meta_key' => '_wp_fixpilot_idempotency_key',
            'meta_value' => $idempotencyKey,
            'posts_per_page' => 1,
            'fields' => 'ids',
        ]);
        if ($existing !== []) {
            $existingDraftId = (int) $existing[0];
            $existingBlueprintId = (int) get_post_meta(
                $existingDraftId,
                '_wp_fixpilot_source_blueprint_id',
                true
            );
            $existingVersion = (int) get_post_meta(
                $existingDraftId,
                '_wp_fixpilot_blueprint_version',
                true
            );
            $existingStructureHash = (string) get_post_meta(
                $existingDraftId,
                '_wp_fixpilot_blueprint_structure_hash',
                true
            );
            $existingRequestHash = (string) get_post_meta(
                $existingDraftId,
                '_wp_fixpilot_request_hash',
                true
            );
            if (
                $existingBlueprintId !== $blueprintId
                || $existingVersion !== $storedVersion
                || $existingStructureHash === ''
                || !hash_equals($currentHash, $existingStructureHash)
                || $existingRequestHash === ''
                || !hash_equals($requestHash, $existingRequestHash)
            ) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_conflict',
                    'De idempotency-sleutel hoort bij een andere blueprint- of payload-snapshot.',
                    ['status' => 409]
                );
            }

            if (!$this->is_page_draft(get_post($existingDraftId))) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_conflict',
                    'Het bestaande WordPress-concept is geen concept meer.',
                    ['status' => 409]
                );
            }

            return $this->draft_response($existingDraftId, $currentHash, false);
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
            $draftMeta = [
                '_wp_fixpilot_idempotency_key' => $idempotencyKey,
                '_wp_fixpilot_request_hash' => $requestHash,
                '_wp_fixpilot_source_blueprint_id' => $blueprintId,
                '_wp_fixpilot_blueprint_version' => $storedVersion,
                '_wp_fixpilot_blueprint_structure_hash' => $currentHash,
            ];
            foreach ($draftMeta as $key => $value) {
                if (!$this->verified_update_post_meta($draftId, $key, $value)) {
                    $cleanup = $this->cleanup_draft($draftId);
                    if (is_wp_error($cleanup)) {
                        return $cleanup;
                    }

                    return $this->draft_failed_error();
                }
            }

            $write = $adapter->apply_replacements($draftId, $schema, $replacements);
            if (is_wp_error($write)) {
                $cleanup = $this->cleanup_draft($draftId);
                if (is_wp_error($cleanup)) {
                    return $cleanup;
                }
                return $write;
            }

            $seoWrite = $this->write_seo(
                $draftId,
                $validatedPayload['seo'],
                $capturedSeoPlugin
            );
            if (is_wp_error($seoWrite)) {
                $cleanup = $this->cleanup_draft($draftId);
                if (is_wp_error($cleanup)) {
                    return $cleanup;
                }
                return $seoWrite;
            }

            $draftStatusResult = wp_update_post(
                ['ID' => $draftId, 'post_status' => 'draft'],
                true
            );
            if (
                is_wp_error($draftStatusResult)
                || $draftStatusResult === 0
                || !$this->is_page_draft(get_post($draftId))
            ) {
                $cleanup = $this->cleanup_draft($draftId);
                if (is_wp_error($cleanup)) {
                    return $cleanup;
                }

                return $this->draft_failed_error();
            }

            return $this->draft_response($draftId, $currentHash, true);
        } catch (Throwable $error) {
            $cleanup = $this->cleanup_draft($draftId);
            if (is_wp_error($cleanup)) {
                return $cleanup;
            }

            return $this->draft_failed_error();
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
        if (get_post($blueprintId) instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_blueprint_delete_failed',
                'De blueprintpagina kon niet volledig worden verwijderd.',
                ['status' => 500]
            );
        }

        return [
            'status' => 'deleted',
            'wordpress_blueprint_id' => $blueprintId,
        ];
    }

    public function seo_plugin(): ?string
    {
        if ($this->configuredSeoPluginDetector instanceof Closure) {
            return $this->normalize_seo_plugin(
                ($this->configuredSeoPluginDetector)()
            );
        }
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

    private function detect_adapter(int $sourceId): WPFixPilot_Blueprint_Adapter|WP_Error
    {
        $matches = [];
        foreach ($this->adapters() as $adapter) {
            if (!$adapter->is_active() || !$adapter->uses_page($sourceId)) {
                continue;
            }
            $matches[] = $adapter;
        }

        if ($matches === []) {
            return new WP_Error(
                'wp_fixpilot_blueprint_builder_unsupported',
                'Geen ondersteunde actieve builder gevonden voor deze pagina.',
                ['status' => 400]
            );
        }
        $highestPriority = max(array_map(
            fn (WPFixPilot_Blueprint_Adapter $adapter): int => $this->adapter_priority(
                $adapter->key()
            ),
            $matches
        ));
        $matches = array_values(array_filter(
            $matches,
            fn (WPFixPilot_Blueprint_Adapter $adapter): bool => $this->adapter_priority(
                $adapter->key()
            ) === $highestPriority
        ));
        if (count($matches) !== 1) {
            return new WP_Error(
                'wp_fixpilot_blueprint_builder_ambiguous',
                'Meerdere builders gevonden voor deze pagina.',
                ['status' => 409]
            );
        }

        return $matches[0];
    }

    private function adapter_priority(string $builder): int
    {
        return match ($builder) {
            'elementor', 'bricks', 'wpbakery' => 30,
            'acf' => 20,
            'gutenberg' => 10,
            default => 0,
        };
    }

    private function source_page_id(mixed $sourcePageId): int|WP_Error
    {
        if (is_int($sourcePageId)) {
            $normalized = $sourcePageId;
        } elseif (
            is_string($sourcePageId)
            && preg_match('/^[1-9][0-9]*$/', $sourcePageId) === 1
        ) {
            $normalized = (int) $sourcePageId;
        } else {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }

        if ($normalized < 1) {
            return new WP_Error(
                'wp_fixpilot_blueprint_invalid',
                'De blueprint-aanvraag is niet compleet.',
                ['status' => 400]
            );
        }

        return $normalized;
    }

    /** @return array{expected_version: int, expected_structure_hash: string, idempotency_key: string, replacements: array<string, string>, approved_urls: array<int, string>, seo: array{title: string, description: string, keyword: string}}|WP_Error */
    private function validate_create_draft_payload(array $payload): array|WP_Error
    {
        $required = [
            'expected_version',
            'expected_structure_hash',
            'idempotency_key',
            'replacements',
            'seo',
        ];
        $allowed = array_merge($required, ['approved_urls']);
        if (
            array_diff(array_keys($payload), $allowed) !== []
            || array_diff($required, array_keys($payload)) !== []
        ) {
            return $this->invalid_request_error();
        }

        $expectedVersion = $this->positive_integer_value(
            $payload['expected_version']
        );
        if (is_wp_error($expectedVersion)) {
            return $expectedVersion;
        }

        if (
            !is_string($payload['expected_structure_hash'])
            || $payload['expected_structure_hash'] === ''
        ) {
            return $this->invalid_request_error();
        }

        if (!is_string($payload['idempotency_key'])) {
            return $this->invalid_request_error();
        }
        $idempotencyKey = sanitize_text_field($payload['idempotency_key']);
        if ($idempotencyKey === '') {
            return $this->invalid_request_error();
        }

        $replacements = $this->validate_replacements_payload(
            $payload['replacements']
        );
        if (is_wp_error($replacements)) {
            return $replacements;
        }

        $approvedUrls = $this->validate_approved_urls(
            $payload['approved_urls'] ?? []
        );
        if (is_wp_error($approvedUrls)) {
            return $approvedUrls;
        }

        $seo = $this->validate_seo_payload($payload['seo']);
        if (is_wp_error($seo)) {
            return $seo;
        }

        return [
            'expected_version' => $expectedVersion,
            'expected_structure_hash' => $payload['expected_structure_hash'],
            'idempotency_key' => $idempotencyKey,
            'replacements' => $replacements,
            'approved_urls' => $approvedUrls,
            'seo' => $seo,
        ];
    }

    private function source_page(int $sourceId): WP_Post|WP_Error
    {
        $source = get_post($sourceId);
        if (!$source instanceof WP_Post || $source->post_type !== 'page') {
            return new WP_Error(
                'wp_fixpilot_source_missing',
                'Bronpagina niet gevonden.',
                ['status' => 404]
            );
        }

        return $source;
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
        if ($post->post_status !== 'draft') {
            return new WP_Error(
                'wp_fixpilot_blueprint_not_draft',
                'Blueprintpagina is geen concept meer.',
                ['status' => 409]
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
        $structureHash = $adapter->structure_hash($blueprintId);
        $snapshotValidation = $this->validate_snapshot_contract(
            $schema,
            $structureHash
        );
        if (is_wp_error($snapshotValidation)) {
            return $snapshotValidation;
        }

        return [
            'adapter' => $adapter,
            'schema' => $schema,
            'structure_hash' => $structureHash,
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

    /** @return array<string, string>|WP_Error */
    private function validate_replacements_payload(mixed $replacements): array|WP_Error
    {
        if (!is_array($replacements)) {
            return $this->invalid_request_error();
        }

        $normalized = [];
        foreach ($replacements as $fieldId => $value) {
            if (!is_string($fieldId) || !is_string($value)) {
                return $this->invalid_request_error();
            }

            $normalized[$fieldId] = $value;
        }

        return $normalized;
    }

    /**
     * @param array<string, string> $replacements
     * @param array<string, mixed> $schema
     * @param array<int, string> $approvedUrls
     * @return array<string, string>|WP_Error
     */
    private function validate_replacements_against_schema(
        array $replacements,
        array $schema,
        array $approvedUrls
    ): array|WP_Error {
        $fields = $this->schema_fields($schema);
        foreach ($fields as $fieldId => $field) {
            if (!empty($field['required']) && !array_key_exists($fieldId, $replacements)) {
                return $this->invalid_request_error();
            }
        }

        foreach ($replacements as $fieldId => $value) {
            if (!isset($fields[$fieldId])) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_field_unknown',
                    'Onbekend blueprint-veld.',
                    ['status' => 400]
                );
            }

            $field = $fields[$fieldId];
            if (
                !empty($field['required'])
                && trim(wp_strip_all_tags($value)) === ''
            ) {
                return $this->invalid_request_error();
            }

            if (strlen($value) > (int) $field['max_length']) {
                return $this->invalid_request_error();
            }

            $valueType = (string) ($field['value_type'] ?? '');
            if (
                in_array($valueType, ['plain_text', 'heading', 'button_text'], true)
                && $this->contains_html_markup($value)
            ) {
                return $this->invalid_request_error();
            }

            if (
                $valueType === 'rich_text'
                && $value !== wp_kses_post($value)
            ) {
                return $this->invalid_request_error();
            }

            if (
                $valueType === 'url'
                && !$this->is_allowed_url_replacement($value, $field, $approvedUrls)
            ) {
                return $this->invalid_request_error();
            }
        }

        return $replacements;
    }

    /** @param array<string, mixed> $schema
     *  @return array<string, array<string, mixed>>
     */
    private function schema_fields(array $schema): array
    {
        $fields = [];
        foreach ((array) ($schema['blocks'] ?? []) as $block) {
            foreach ((array) ($block['fields'] ?? []) as $field) {
                if (
                    is_array($field)
                    && isset($field['id'])
                    && is_string($field['id'])
                ) {
                    $fields[$field['id']] = $field;
                }
            }
        }

        return $fields;
    }

    /** @return array{title: string, description: string, keyword: string}|WP_Error */
    private function validate_seo_payload(mixed $seo): array|WP_Error
    {
        if (
            !is_array($seo)
            || !$this->has_exact_keys($seo, ['title', 'description', 'keyword'])
            || !is_string($seo['title'] ?? null)
            || !is_string($seo['description'] ?? null)
            || !is_string($seo['keyword'] ?? null)
        ) {
            return $this->invalid_request_error();
        }

        return [
            'title' => $seo['title'],
            'description' => $seo['description'],
            'keyword' => $seo['keyword'],
        ];
    }

    private function positive_integer_value(mixed $value): int|WP_Error
    {
        if (is_int($value)) {
            $normalized = $value;
        } elseif (
            is_string($value)
            && preg_match('/^[1-9][0-9]*$/', $value) === 1
        ) {
            $normalized = (int) $value;
        } else {
            return $this->invalid_request_error();
        }

        if ($normalized < 1) {
            return $this->invalid_request_error();
        }

        return $normalized;
    }

    /** @return array<string, mixed> */
    private function blueprint_response(
        int $blueprintId,
        array $schema,
        string $structureHash,
        bool $created
    ): array {
        return [
            'status' => 'ready',
            'created' => $created,
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
    private function draft_response(
        int $postId,
        string $structureHash = '',
        bool $created = false
    ): array
    {
        $post = get_post($postId);

        return [
            'wordpress_object_id' => $postId,
            'created' => $created,
            'edit_url' => get_edit_post_link($postId, 'raw'),
            'status' => $post instanceof WP_Post && $post->post_status !== ''
                ? $post->post_status
                : 'draft',
            'content_hash' => $structureHash,
        ];
    }

    /** @param array<string, mixed> $schema */
    private function validate_snapshot_contract(
        array $schema,
        string $structureHash
    ): true|WP_Error {
        if (
            !$this->has_exact_keys($schema, ['schema_version', 'blocks'])
            || $schema['schema_version'] !== 'blueprint-v1'
            || !is_array($schema['blocks'])
            || $schema['blocks'] === []
        ) {
            return $this->invalid_snapshot_error();
        }

        foreach ($schema['blocks'] as $block) {
            if (
                !$this->is_valid_block($block)
            ) {
                return $this->invalid_snapshot_error();
            }
        }

        $fieldIds = $this->field_ids($schema);
        if (count($fieldIds) !== count(array_unique($fieldIds))) {
            return $this->invalid_snapshot_error();
        }

        if ($structureHash === '') {
            return $this->invalid_snapshot_error();
        }

        return true;
    }

    private function write_seo(
        int $postId,
        array $seo,
        string $plugin
    ): bool|WP_Error
    {
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
                if (
                    !$this->verified_update_post_meta(
                        $postId,
                        (string) $key,
                        $metaValue
                    )
                ) {
                    return $this->draft_failed_error();
                }
            }
        }

        return true;
    }

    private function verified_update_post_meta(
        int $postId,
        string $key,
        mixed $value
    ): bool {
        $result = update_post_meta($postId, $key, $value);
        if ($result !== false) {
            return true;
        }

        return $this->meta_value_matches(
            get_post_meta($postId, $key, true),
            $value
        );
    }

    private function meta_value_matches(mixed $actual, mixed $expected): bool
    {
        if (is_array($expected)) {
            return $actual === $expected;
        }

        if (is_bool($expected) || $expected === null) {
            return $actual === $expected;
        }

        return is_scalar($actual) && (string) $actual === (string) $expected;
    }

    /**
     * @param array<string, string> $replacements
     * @param array{title: string, description: string, keyword: string} $seo
     * @param array<int, string> $approvedUrls
     */
    private function request_hash(
        array $replacements,
        array $seo,
        array $approvedUrls
    ): string
    {
        $canonicalPayload = $this->canonicalize_value([
            'replacements' => $replacements,
            'approved_urls' => $approvedUrls,
            'seo' => $seo,
        ]);
        $encoded = json_encode(
            $canonicalPayload,
            JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
        );

        return hash('sha256', $encoded === false ? '' : $encoded);
    }

    private function canonicalize_value(mixed $value): mixed
    {
        if (!is_array($value)) {
            return $value;
        }

        if ($this->is_indexed_array($value)) {
            foreach ($value as $index => $item) {
                $value[$index] = $this->canonicalize_value($item);
            }

            return $value;
        }

        ksort($value);
        foreach ($value as $key => $item) {
            $value[$key] = $this->canonicalize_value($item);
        }

        return $value;
    }

    /** @param array<mixed> $value */
    private function is_indexed_array(array $value): bool
    {
        $expectedIndex = 0;
        foreach (array_keys($value) as $key) {
            if ($key !== $expectedIndex) {
                return false;
            }

            $expectedIndex++;
        }

        return true;
    }

    private function cleanup_blueprint(int $blueprintId): true|WP_Error
    {
        wp_delete_post($blueprintId, true);
        if (get_post($blueprintId) instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_blueprint_cleanup_failed',
                'De onvolledige blueprint kon niet worden verwijderd.',
                ['status' => 500]
            );
        }

        return true;
    }

    private function cleanup_draft(int $draftId): true|WP_Error
    {
        wp_delete_post($draftId, true);
        if (get_post($draftId) instanceof WP_Post) {
            return new WP_Error(
                'wp_fixpilot_draft_cleanup_failed',
                'Het onvolledige WordPress-concept kon niet worden verwijderd.',
                ['status' => 500]
            );
        }

        return true;
    }

    private function blueprint_failed_error(): WP_Error
    {
        return new WP_Error(
            'wp_fixpilot_blueprint_failed',
            'De blueprint kon niet volledig worden vastgelegd.',
            ['status' => 500]
        );
    }

    private function draft_failed_error(): WP_Error
    {
        return new WP_Error(
            'wp_fixpilot_draft_failed',
            'Het WordPress-concept kon niet volledig worden aangemaakt.',
            ['status' => 500]
        );
    }

    private function detected_seo_plugin_snapshot(): string
    {
        return (string) ($this->seo_plugin() ?? '');
    }

    private function captured_seo_plugin(int $blueprintId): string
    {
        return (string) get_post_meta(
            $blueprintId,
            '_wp_fixpilot_seo_plugin',
            true
        );
    }

    private function normalize_seo_plugin(mixed $plugin): ?string
    {
        $normalized = sanitize_key((string) $plugin);

        return in_array($normalized, ['yoast', 'rank_math', 'aioseo'], true)
            ? $normalized
            : null;
    }

    /** @param array<string, mixed> $value */
    private function has_exact_keys(array $value, array $expectedKeys): bool
    {
        $actualKeys = array_keys($value);

        return array_diff($actualKeys, $expectedKeys) === []
            && array_diff($expectedKeys, $actualKeys) === [];
    }

    private function is_valid_block(mixed $block): bool
    {
        if (
            !is_array($block)
            || !$this->has_exact_keys(
                $block,
                ['id', 'layout', 'label', 'semantic_role', 'fields']
            )
            || !$this->is_non_empty_string($block['id'] ?? null)
            || !$this->is_non_empty_string($block['layout'] ?? null)
            || !$this->is_non_empty_string($block['label'] ?? null)
            || !is_string($block['semantic_role'] ?? null)
            || !in_array(
                $block['semantic_role'],
                self::ALLOWED_SEMANTIC_ROLES,
                true
            )
            || !is_array($block['fields'])
            || $block['fields'] === []
        ) {
            return false;
        }

        foreach ($block['fields'] as $field) {
            if (!$this->is_valid_field($field)) {
                return false;
            }
        }

        return true;
    }

    private function is_valid_field(mixed $field): bool
    {
        return is_array($field)
            && $this->has_exact_keys(
                $field,
                [
                    'id',
                    'path',
                    'label',
                    'value_type',
                    'current_value',
                    'required',
                    'max_length',
                ]
            )
            && $this->is_non_empty_string($field['id'] ?? null)
            && $this->is_non_empty_string($field['path'] ?? null)
            && $this->is_non_empty_string($field['label'] ?? null)
            && is_string($field['value_type'] ?? null)
            && in_array($field['value_type'], self::ALLOWED_VALUE_TYPES, true)
            && is_string($field['current_value'] ?? null)
            && is_bool($field['required'] ?? null)
            && is_int($field['max_length'] ?? null)
            && $field['max_length'] >= 1
            && $field['max_length'] <= 20000;
    }

    private function is_non_empty_string(mixed $value): bool
    {
        return is_string($value) && $value !== '';
    }

    private function invalid_snapshot_error(): WP_Error
    {
        return new WP_Error(
            'wp_fixpilot_blueprint_invalid',
            'De blueprint-inhoud is ongeldig.',
            ['status' => 500]
        );
    }

    private function invalid_request_error(): WP_Error
    {
        return new WP_Error(
            'wp_fixpilot_blueprint_invalid',
            'De blueprint-aanvraag is niet compleet.',
            ['status' => 400]
        );
    }

    /** @return array<int, string>|WP_Error */
    private function validate_approved_urls(mixed $approvedUrls): array|WP_Error
    {
        if (!is_array($approvedUrls)) {
            return $this->invalid_request_error();
        }

        $normalized = [];
        foreach ($approvedUrls as $approvedUrl) {
            if (!is_string($approvedUrl)) {
                return $this->invalid_request_error();
            }

            $safeUrl = $this->safe_url_string($approvedUrl);
            if ($safeUrl === null) {
                return $this->invalid_request_error();
            }

            $normalized[] = $safeUrl;
        }

        $normalized = array_values(array_unique($normalized));
        sort($normalized, SORT_STRING);

        return $normalized;
    }

    private function contains_html_markup(string $value): bool
    {
        return preg_match('/<[^>]+>/', $value) === 1;
    }

    /** @param array<string, mixed> $field */
    private function is_allowed_url_replacement(
        string $value,
        array $field,
        array $approvedUrls
    ): bool {
        if (
            isset($field['current_value'])
            && is_string($field['current_value'])
            && $value === $field['current_value']
        ) {
            return true;
        }

        $safeUrl = $this->safe_url_string($value);
        if ($safeUrl === null) {
            return false;
        }

        return in_array($safeUrl, $approvedUrls, true);
    }

    private function safe_url_string(string $value): ?string
    {
        $sanitized = esc_url_raw($value);
        if ($sanitized === '' || $sanitized !== $value) {
            return null;
        }

        if (preg_match('/\s/u', $value) === 1) {
            return null;
        }

        if (preg_match('#^/(?!/)[^\s]*$#u', $value) === 1) {
            return $value;
        }

        $scheme = parse_url($value, PHP_URL_SCHEME);
        if (!is_string($scheme) || !in_array(strtolower($scheme), ['http', 'https'], true)) {
            return null;
        }

        return filter_var($value, FILTER_VALIDATE_URL) === false
            ? null
            : $value;
    }

    private function is_page_draft(mixed $post): bool
    {
        return $post instanceof WP_Post
            && $post->post_type === 'page'
            && $post->post_status === 'draft';
    }
}
