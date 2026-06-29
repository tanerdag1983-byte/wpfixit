<?php

declare(strict_types=1);

final class WP_Error
{
    public function __construct(public string $code, public string $message, public array $data = []) {}
}

final class WP_Post
{
    public int $ID;
    public string $post_type = 'page';
    public string $post_status = 'publish';
    public string $post_title = '';
    public string $post_name = '';
    public string $post_content = '';
    public string $post_excerpt = '';
    public int $post_parent = 0;
    public int $menu_order = 0;
}

final class WP_REST_Server
{
    public const READABLE = 'GET';
    public const CREATABLE = 'POST';
    public const DELETABLE = 'DELETE';
}

final class WP_REST_Response
{
    public function __construct(public array $data, public int $status = 200) {}

    public function get_data(): array
    {
        return $this->data;
    }
}

final class WP_REST_Request
{
    /** @param array<string, mixed> $params */
    public function __construct(
        private string $method = 'GET',
        private string $route = '',
        private array $params = [],
        private array $headers = [],
        private string $body = ''
    ) {}

    public function get_method(): string
    {
        return $this->method;
    }

    public function get_route(): string
    {
        return $this->route;
    }

    public function get_param(string $key): mixed
    {
        return $this->params[$key] ?? null;
    }

    /** @return array<string, mixed> */
    public function get_json_params(): array
    {
        return $this->params;
    }

    public function get_header(string $key): string
    {
        return (string) ($this->headers[$key] ?? '');
    }

    public function get_body(): string
    {
        return $this->body;
    }
}

final class WP_Query
{
    /** @var array<int, WP_Post> */
    public array $posts = [];

    public function __construct(array $args)
    {
        foreach ($GLOBALS['wpfixpilot_posts'] as $post) {
            if (!in_array($post->post_type, (array) ($args['post_type'] ?? []), true)) {
                continue;
            }
            if (!in_array($post->post_status, (array) ($args['post_status'] ?? []), true)) {
                continue;
            }
            $this->posts[] = $post;
        }
    }
}

define('WPSEO_VERSION', 'test');

$GLOBALS['wpfixpilot_posts'] = [];
$GLOBALS['wpfixpilot_meta'] = [];
$GLOBALS['wpfixpilot_routes'] = [];
$GLOBALS['wpfixpilot_deleted_posts'] = [];
$GLOBALS['wpfixpilot_next_post_id'] = 200;
$GLOBALS['wpfixpilot_source_page_template'] = 'algemeen-productdetail.php';
$GLOBALS['wpfixpilot_update_post_meta_failures'] = [];
$GLOBALS['wpfixpilot_update_post_meta_results'] = [];
$GLOBALS['wpfixpilot_add_post_meta_results'] = [];
$GLOBALS['wpfixpilot_get_posts_calls'] = [];

function sanitize_text_field(string $value): string { return trim(strip_tags($value)); }
function sanitize_key(string $value): string { return preg_replace('/[^a-z0-9_\-]/', '', strtolower($value)); }
function sanitize_title(string $value): string { return trim(strtolower(str_replace(' ', '-', $value)), '-'); }
function esc_html(string $value): string { return htmlspecialchars($value, ENT_QUOTES); }
function esc_url(string $value): string { return $value; }
function esc_url_raw(string $value): string { return $value; }
function wp_kses_post(string $value): string { return $value; }
function maybe_unserialize(mixed $value): mixed { return $value; }
function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function wp_json_encode(mixed $value): string { return (string) json_encode($value); }
function wp_strip_all_tags(string $value): string { return strip_tags($value); }
function get_site_url(): string { return 'https://example.test'; }
function get_bloginfo(string $show): string { return $show === 'version' ? '6.6.1' : ''; }
function get_the_title(WP_Post $post): string { return $post->post_title; }
function get_permalink(WP_Post $post): string { return 'https://example.test/?p=' . $post->ID; }
function get_post_modified_time(string $format, bool $gmt, WP_Post $post): string { return '2026-06-28T10:00:00+00:00'; }
function get_edit_post_link(int $postId, string $context): string { return 'https://example.test/wp-admin/post.php?post=' . $postId; }
function get_option(string $key, mixed $default = false): mixed { return $key === 'wp_fixpilot_secret' ? 'test-secret' : $default; }
function set_transient(string $key, mixed $value, int $expiration): void {}
function get_transient(string $key): mixed { return false; }
function clean_post_cache(int $postId): void {}
function register_rest_route(string $namespace, string $route, array $args): void
{
    $GLOBALS['wpfixpilot_routes'][] = [
        'namespace' => $namespace,
        'route' => $route,
        'args' => $args,
    ];
}
function get_posts(array $args): array
{
    $GLOBALS['wpfixpilot_get_posts_calls'][] = $args;
    $metaKey = (string) ($args['meta_key'] ?? '');
    $metaValue = (string) ($args['meta_value'] ?? '');
    $matches = [];
    foreach ($GLOBALS['wpfixpilot_meta'] as $postId => $meta) {
        $value = $meta[$metaKey][0] ?? null;
        if ((string) $value === $metaValue) {
            $matches[] = $args['fields'] === 'ids' ? $postId : get_post((int) $postId);
        }
    }
    return $matches;
}
function get_post(int $postId): ?WP_Post
{
    return $GLOBALS['wpfixpilot_posts'][$postId] ?? null;
}
function wp_insert_post(array $postData, bool $wpError = false): int
{
    $post = new WP_Post();
    $post->ID = $GLOBALS['wpfixpilot_next_post_id']++;
    $post->post_type = (string) ($postData['post_type'] ?? 'page');
    $post->post_status = (string) ($postData['post_status'] ?? 'draft');
    $post->post_title = (string) ($postData['post_title'] ?? '');
    $post->post_name = (string) ($postData['post_name'] ?? '');
    $post->post_content = (string) ($postData['post_content'] ?? '');
    $post->post_excerpt = (string) ($postData['post_excerpt'] ?? '');
    $post->post_parent = (int) ($postData['post_parent'] ?? 0);
    $post->menu_order = (int) ($postData['menu_order'] ?? 0);
    $GLOBALS['wpfixpilot_posts'][$post->ID] = $post;
    return $post->ID;
}
function wp_update_post(array $postData, bool $wpError = false): int
{
    $post = $GLOBALS['wpfixpilot_posts'][(int) $postData['ID']];
    foreach (['post_status', 'post_title', 'post_name', 'post_content', 'post_excerpt'] as $field) {
        if (array_key_exists($field, $postData)) {
            $post->{$field} = (string) $postData[$field];
        }
    }
    return $post->ID;
}
function wp_delete_post(int $postId, bool $force): void
{
    $GLOBALS['wpfixpilot_deleted_posts'][] = $postId;
    unset($GLOBALS['wpfixpilot_posts'][$postId], $GLOBALS['wpfixpilot_meta'][$postId]);
}
function get_post_meta(int $postId, string $key = '', bool $single = false): mixed
{
    $meta = $GLOBALS['wpfixpilot_meta'][$postId] ?? [];
    if ($key === '') {
        return $meta;
    }
    if (!array_key_exists($key, $meta)) {
        return $single ? '' : [];
    }
    return $single ? ($meta[$key][0] ?? '') : $meta[$key];
}
function update_post_meta(int $postId, string $key, mixed $value): mixed
{
    if (isset($GLOBALS['wpfixpilot_update_post_meta_failures'][$postId][$key])) {
        throw $GLOBALS['wpfixpilot_update_post_meta_failures'][$postId][$key];
    }
    $result = $GLOBALS['wpfixpilot_update_post_meta_results'][$postId][$key] ?? null;
    if ($result === false) {
        return false;
    }
    $GLOBALS['wpfixpilot_meta'][$postId][$key] = [$value];

    return $result;
}
function add_post_meta(int $postId, string $key, mixed $value): mixed
{
    $result = $GLOBALS['wpfixpilot_add_post_meta_results'][$postId][$key] ?? null;
    if ($result === false) {
        return false;
    }
    $GLOBALS['wpfixpilot_meta'][$postId][$key] ??= [];
    $GLOBALS['wpfixpilot_meta'][$postId][$key][] = $value;

    return $result;
}

/** @param Closure(): mixed $callback */
function capture_without_php_warnings(Closure $callback): mixed
{
    set_error_handler(
        static function (int $severity, string $message, string $file, int $line): never {
            throw new RuntimeException(
                sprintf('%s in %s:%d', $message, $file, $line)
            );
        }
    );

    try {
        return $callback();
    } finally {
        restore_error_handler();
    }
}

function seed_source_page(
    int $postId,
    string $title = 'Transmissie onderhoud',
    string $fieldTitle = 'Bestaande titel',
    string $fieldBody = '<p>Bestaande inhoud</p>'
): void {
    $source = new WP_Post();
    $source->ID = $postId;
    $source->post_title = $title;
    $source->post_content = '<section>Originele content</section>';
    $source->post_excerpt = 'Originele samenvatting';
    $source->post_parent = 3;
    $source->menu_order = 2;
    $GLOBALS['wpfixpilot_posts'][$postId] = $source;
    $GLOBALS['wpfixpilot_meta'][$postId] = [
        '_wp_page_template' => ['algemeen-productdetail.php'],
        '_thumbnail_id' => [77],
        'fake_blueprint_tree' => [[[
            'field-title' => $fieldTitle,
            'field-body' => $fieldBody,
        ]]],
        'analytics_state' => ['skip-me'],
        '_edit_lock' => ['1700000000:1'],
        '_wp_fixpilot_idempotency_key' => ['proposal-legacy'],
    ];
}

seed_source_page(19);
seed_source_page(20, 'Schema failure bron');
seed_source_page(21, 'Replacement failure bron');
seed_source_page(22, 'SEO failure bron');
$unsupportedSource = new WP_Post();
$unsupportedSource->ID = 23;
$unsupportedSource->post_type = 'post';
$unsupportedSource->post_status = 'trash';
$unsupportedSource->post_title = 'Verkeerd post type';
$GLOBALS['wpfixpilot_posts'][23] = $unsupportedSource;

require_once __DIR__ . '/../includes/builder-adapters/interface-blueprint-adapter.php';

class Test_Blueprint_Adapter implements WPFixPilot_Blueprint_Adapter
{
    /** @param array<int, int> $sourcePageIds */
    public function __construct(private array $sourcePageIds = [19]) {}

    public function key(): string
    {
        return 'acf';
    }

    public function is_active(): bool
    {
        return true;
    }

    public function uses_page(int $postId): bool
    {
        return in_array($postId, $this->sourcePageIds, true) || $postId >= 200;
    }

    public function clone_meta_keys(int $postId): array
    {
        return ['fake_blueprint_tree'];
    }

    public function schema(int $postId): array|WP_Error
    {
        if (!get_post($postId) instanceof WP_Post) {
            return new WP_Error('missing', 'Ontbrekende blueprint.');
        }

        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => [
                [
                    'id' => 'block-hero',
                    'layout' => 'hero',
                    'label' => 'Hero',
                    'semantic_role' => 'hero',
                    'fields' => [
                        [
                            'id' => 'field-title',
                            'path' => 'fake_blueprint_tree/0/field-title',
                            'label' => 'Titel',
                            'value_type' => 'heading',
                            'current_value' => (string) get_post_meta($postId, 'fake_blueprint_tree', true)[0]['field-title'],
                            'required' => true,
                            'max_length' => 180,
                        ],
                        [
                            'id' => 'field-body',
                            'path' => 'fake_blueprint_tree/0/field-body',
                            'label' => 'Introductie',
                            'value_type' => 'rich_text',
                            'current_value' => (string) get_post_meta($postId, 'fake_blueprint_tree', true)[0]['field-body'],
                            'required' => true,
                            'max_length' => 5000,
                        ],
                    ],
                ],
            ],
        ];
    }

    public function structure_hash(int $postId): string
    {
        return hash('sha256', wp_json_encode(get_post_meta($postId, 'fake_blueprint_tree', true)));
    }

    public function apply_replacements(int $postId, array $schema, array $replacements): bool|WP_Error
    {
        $tree = get_post_meta($postId, 'fake_blueprint_tree', true);
        if (!is_array($tree) || !isset($tree[0])) {
            return new WP_Error('wp_fixpilot_blueprint_missing', 'Blueprint-structuur ontbreekt.');
        }
        foreach ($replacements as $fieldId => $value) {
            if (!in_array($fieldId, ['field-title', 'field-body'], true)) {
                return new WP_Error('wp_fixpilot_blueprint_field_unknown', 'Onbekend blueprint-veld.', ['status' => 400]);
            }
            $tree[0][$fieldId] = (string) $value;
        }
        update_post_meta($postId, 'fake_blueprint_tree', $tree);
        return true;
    }
}

final class Schema_Failing_Blueprint_Adapter extends Test_Blueprint_Adapter
{
    public function schema(int $postId): array|WP_Error
    {
        if ($postId >= 200) {
            return new WP_Error(
                'wp_fixpilot_schema_failed',
                'Schema extractie mislukt.',
                ['status' => 500]
            );
        }

        return parent::schema($postId);
    }
}

final class Apply_Failing_Blueprint_Adapter extends Test_Blueprint_Adapter
{
    public function apply_replacements(int $postId, array $schema, array $replacements): bool|WP_Error
    {
        return new WP_Error(
            'wp_fixpilot_replacements_failed',
            'Replacement write mislukt.',
            ['status' => 500]
        );
    }
}

final class Schema_Contract_Blueprint_Adapter extends Test_Blueprint_Adapter
{
    /** @param array<int, int> $sourcePageIds */
    public function __construct(
        array $sourcePageIds,
        private array|WP_Error $configuredSchema,
        private ?string $configuredHash = null
    ) {
        parent::__construct($sourcePageIds);
    }

    public function schema(int $postId): array|WP_Error
    {
        return $this->configuredSchema;
    }

    public function structure_hash(int $postId): string
    {
        return $this->configuredHash ?? parent::structure_hash($postId);
    }
}

final class Tracking_Blueprint_Adapter extends Test_Blueprint_Adapter
{
    /** @var array<int, int> */
    public array $usesPageCalls = [];

    public function uses_page(int $postId): bool
    {
        $this->usesPageCalls[] = $postId;

        return parent::uses_page($postId);
    }
}

/** @return array<string, mixed> */
function valid_test_blueprint_schema(int $postId): array
{
    $schema = (new Test_Blueprint_Adapter([$postId]))->schema($postId);
    assert(is_array($schema));

    return $schema;
}

require_once __DIR__ . '/../includes/class-auth.php';
require_once __DIR__ . '/../includes/seo-adapters/interface-seo-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-adapter-changes.php';
require_once __DIR__ . '/../includes/seo-adapters/class-yoast-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-rank-math-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-aioseo-adapter.php';
require_once __DIR__ . '/../includes/class-change-controller.php';
require_once __DIR__ . '/../includes/class-post-cloner.php';
require_once __DIR__ . '/../includes/class-page-package-controller.php';
require_once __DIR__ . '/../includes/class-blueprint-controller.php';
require_once __DIR__ . '/../includes/class-rest-controller.php';

$cloner = new WPFixPilot_Post_Cloner();
$metaWriteFailureCloneId = $GLOBALS['wpfixpilot_next_post_id'];
$GLOBALS['wpfixpilot_add_post_meta_results'][$metaWriteFailureCloneId] = [
    'fake_blueprint_tree' => false,
];
$metaWriteFailure = $cloner->clone_page(
    19,
    'Allowlisted meta write failure',
    false,
    ['fake_blueprint_tree']
);
assert(is_wp_error($metaWriteFailure));
assert($metaWriteFailure->code === 'wp_fixpilot_clone_failed');
assert(($metaWriteFailure->data['status'] ?? null) === 500);
assert(get_post($metaWriteFailureCloneId) === null);
assert(in_array($metaWriteFailureCloneId, $GLOBALS['wpfixpilot_deleted_posts'], true));
assert(get_post(19) instanceof WP_Post);
assert(!in_array(19, $GLOBALS['wpfixpilot_deleted_posts'], true));
unset($GLOBALS['wpfixpilot_add_post_meta_results'][$metaWriteFailureCloneId]);

$markerWriteFailureCloneId = $GLOBALS['wpfixpilot_next_post_id'];
$GLOBALS['wpfixpilot_update_post_meta_results'][$markerWriteFailureCloneId] = [
    '_wp_fixpilot_blueprint' => false,
];
$markerWriteFailure = $cloner->clone_page(
    19,
    'Blueprint marker write failure',
    true,
    ['fake_blueprint_tree']
);
assert(is_wp_error($markerWriteFailure));
assert($markerWriteFailure->code === 'wp_fixpilot_clone_failed');
assert(($markerWriteFailure->data['status'] ?? null) === 500);
assert(get_post($markerWriteFailureCloneId) === null);
assert(in_array($markerWriteFailureCloneId, $GLOBALS['wpfixpilot_deleted_posts'], true));
assert(get_post(19) instanceof WP_Post);
assert(!in_array(19, $GLOBALS['wpfixpilot_deleted_posts'], true));
unset($GLOBALS['wpfixpilot_update_post_meta_results'][$markerWriteFailureCloneId]);
$GLOBALS['wpfixpilot_next_post_id'] = 200;

$controller = new WPFixPilot_Blueprint_Controller([
    new Test_Blueprint_Adapter([19, 20, 22]),
]);

$invalidSourcePageIdCases = [
    ['label' => 'mixed source page id', 'value' => '19abc'],
    ['label' => 'zero source page id', 'value' => 0],
    ['label' => 'negative source page id', 'value' => -19],
    ['label' => 'float source page id', 'value' => 19.5],
    ['label' => 'whitespace source page id', 'value' => '   '],
];

foreach ($invalidSourcePageIdCases as $invalidSourcePageIdCase) {
    $trackingAdapter = new Tracking_Blueprint_Adapter([19]);
    $invalidSourceIdController = new WPFixPilot_Blueprint_Controller([$trackingAdapter]);
    $invalidSourceIdBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
    $invalidSourceId = $invalidSourceIdController->capture([
        'source_page_id' => $invalidSourcePageIdCase['value'],
        'name' => 'Dienstpagina',
        'page_type' => 'service',
        'builder' => 'acf',
        'version' => 1,
    ]);
    assert(is_wp_error($invalidSourceId), $invalidSourcePageIdCase['label']);
    assert($invalidSourceId->code === 'wp_fixpilot_blueprint_invalid', $invalidSourcePageIdCase['label']);
    assert(($invalidSourceId->data['status'] ?? null) === 400, $invalidSourcePageIdCase['label']);
    assert($trackingAdapter->usesPageCalls === [], $invalidSourcePageIdCase['label']);
    assert(get_post($invalidSourceIdBlueprintId) === null, $invalidSourcePageIdCase['label']);
}

$missingSourceAdapter = new Tracking_Blueprint_Adapter([19]);
$missingSourceController = new WPFixPilot_Blueprint_Controller([$missingSourceAdapter]);
$missingSourceBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
$missingSource = $missingSourceController->capture([
    'source_page_id' => 999,
    'name' => 'Ontbrekende bronpagina',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(is_wp_error($missingSource));
assert($missingSource->code === 'wp_fixpilot_source_missing');
assert(($missingSource->data['status'] ?? null) === 404);
assert($missingSourceAdapter->usesPageCalls === []);
assert(get_post($missingSourceBlueprintId) === null);

$wrongTypeSourceAdapter = new Tracking_Blueprint_Adapter([19]);
$wrongTypeSourceController = new WPFixPilot_Blueprint_Controller([$wrongTypeSourceAdapter]);
$wrongTypeSourceBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
$wrongTypeSource = $wrongTypeSourceController->capture([
    'source_page_id' => 23,
    'name' => 'Verkeerde bronpagina',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(is_wp_error($wrongTypeSource));
assert($wrongTypeSource->code === 'wp_fixpilot_source_missing');
assert(($wrongTypeSource->data['status'] ?? null) === 404);
assert($wrongTypeSourceAdapter->usesPageCalls === []);
assert(get_post($wrongTypeSourceBlueprintId) === null);

$invalidCaptureCases = [
    [
        'label' => 'whitespace name',
        'payload' => [
            'source_page_id' => 19,
            'name' => '   ',
            'page_type' => 'service',
            'builder' => 'acf',
            'version' => 1,
        ],
    ],
    [
        'label' => 'unsupported page type',
        'payload' => [
            'source_page_id' => 19,
            'name' => 'Dienstpagina',
            'page_type' => 'landing page',
            'builder' => 'acf',
            'version' => 1,
        ],
    ],
    [
        'label' => 'non-positive version',
        'payload' => [
            'source_page_id' => 19,
            'name' => 'Dienstpagina',
            'page_type' => 'service',
            'builder' => 'acf',
            'version' => 0,
        ],
    ],
    [
        'label' => 'empty builder after sanitize',
        'payload' => [
            'source_page_id' => 19,
            'name' => 'Dienstpagina',
            'page_type' => 'service',
            'builder' => '   ',
            'version' => 1,
        ],
    ],
];

foreach ($invalidCaptureCases as $invalidCaptureCase) {
    $invalidCaptureBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
    $invalidCapture = $controller->capture($invalidCaptureCase['payload']);
    assert(is_wp_error($invalidCapture), $invalidCaptureCase['label']);
    assert($invalidCapture->code === 'wp_fixpilot_blueprint_invalid', $invalidCaptureCase['label']);
    assert(($invalidCapture->data['status'] ?? null) === 400, $invalidCaptureCase['label']);
    assert(get_post($invalidCaptureBlueprintId) === null, $invalidCaptureCase['label']);
}

$captured = $controller->capture([
    'source_page_id' => '19',
    'name' => 'Dienstpagina',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);

assert($captured['status'] === 'ready');
assert($captured['source_page_id'] === 19);
assert($captured['wordpress_blueprint_id'] === 200);
assert(get_post(200)->post_type === 'page');
assert(get_post(200)->post_status === 'draft');
assert(get_post_meta(200, '_wp_fixpilot_blueprint', true) === '1');
assert(get_post_meta(200, '_wp_page_template', true) === 'algemeen-productdetail.php');
assert(get_post_meta(200, 'analytics_state', true) === '');
assert(get_post_meta(200, '_wp_fixpilot_idempotency_key', true) === '');
assert(get_post_meta(19, '_wp_fixpilot_blueprint', true) === '');
assert($captured['created'] === true);

$read = $controller->read(200);
assert($read['content_schema']['schema_version'] === 'blueprint-v1');
assert($read['structure_hash'] === $captured['structure_hash']);

$invalidDraftPayloadCases = [
    [
        'label' => 'expected version numeric prefix string',
        'payload' => [
            'expected_version' => '1abc',
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-invalid-version',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
    [
        'label' => 'expected structure hash array',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => ['not-a-string'],
            'idempotency_key' => 'proposal-invalid-hash',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
    [
        'label' => 'nested replacement array',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-nested-replacement',
            'replacements' => ['field-title' => ['nested']],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
    [
        'label' => 'required replacement empty string',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-empty-replacement',
            'replacements' => ['field-title' => '   '],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
    [
        'label' => 'replacement exceeds max length',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-long-replacement',
            'replacements' => ['field-title' => str_repeat('x', 181)],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
    [
        'label' => 'seo payload list',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-seo-list',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => ['SEO titel'],
        ],
    ],
    [
        'label' => 'seo payload missing keyword',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-seo-missing',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
            ],
        ],
    ],
    [
        'label' => 'seo payload extra key',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-seo-extra',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => [
                'title' => 'SEO titel',
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
                'extra' => 'nee',
            ],
        ],
    ],
    [
        'label' => 'seo object field',
        'payload' => [
            'expected_version' => 1,
            'expected_structure_hash' => $captured['structure_hash'],
            'idempotency_key' => 'proposal-seo-object-field',
            'replacements' => ['field-title' => 'Nieuwe titel'],
            'seo' => [
                'title' => ['nested'],
                'description' => 'SEO omschrijving',
                'keyword' => 'dsg revisie',
            ],
        ],
    ],
];

foreach ($invalidDraftPayloadCases as $invalidDraftPayloadCase) {
    $invalidDraftId = $GLOBALS['wpfixpilot_next_post_id'];
    $lookupCount = count($GLOBALS['wpfixpilot_get_posts_calls']);
    $invalidDraft = capture_without_php_warnings(
        static fn () => $controller->create_draft(
            200,
            $invalidDraftPayloadCase['payload']
        )
    );
    assert(is_wp_error($invalidDraft), $invalidDraftPayloadCase['label']);
    assert($invalidDraft->code === 'wp_fixpilot_blueprint_invalid', $invalidDraftPayloadCase['label']);
    assert(($invalidDraft->data['status'] ?? null) === 400, $invalidDraftPayloadCase['label']);
    assert(count($GLOBALS['wpfixpilot_get_posts_calls']) === $lookupCount, $invalidDraftPayloadCase['label']);
    assert(get_post($invalidDraftId) === null, $invalidDraftPayloadCase['label']);
}

$draft = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Nieuwe titel'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);

assert($draft['status'] === 'draft');
assert($draft['created'] === true);
assert(get_post($draft['wordpress_object_id'])->post_type === 'page');
assert(get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint', true) === '');
assert(get_post_meta($draft['wordpress_object_id'], '_yoast_wpseo_title', true) === 'SEO titel');
assert(get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_source_blueprint_id', true) === 200);
assert((int) get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint_version', true) === 1);
assert(
    (string) get_post_meta(
        $draft['wordpress_object_id'],
        '_wp_fixpilot_blueprint_structure_hash',
        true
    ) === $captured['structure_hash']
);
assert(get_post_meta($draft['wordpress_object_id'], 'fake_blueprint_tree', true)[0]['field-title'] === 'Nieuwe titel');

$repeated = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Andere titel'],
    'seo' => [
        'title' => 'Tweede SEO titel',
        'description' => 'Andere omschrijving',
        'keyword' => 'andere zoekterm',
    ],
]);
assert($repeated['wordpress_object_id'] === $draft['wordpress_object_id']);
assert($repeated['created'] === false);

get_post($draft['wordpress_object_id'])->post_status = 'publish';
$publishedReuse = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Andere titel'],
    'seo' => [
        'title' => 'Tweede SEO titel',
        'description' => 'Andere omschrijving',
        'keyword' => 'andere zoekterm',
    ],
]);
assert($publishedReuse['wordpress_object_id'] === $draft['wordpress_object_id']);
assert($publishedReuse['status'] === 'publish');
assert($publishedReuse['created'] === false);
assert($GLOBALS['wpfixpilot_next_post_id'] === 202);

update_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint_version', 99);
$sameKeyStoredVersionMismatch = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Andere titel'],
    'seo' => [
        'title' => 'Tweede SEO titel',
        'description' => 'Andere omschrijving',
        'keyword' => 'andere zoekterm',
    ],
]);
assert(is_wp_error($sameKeyStoredVersionMismatch));
assert($sameKeyStoredVersionMismatch->code === 'wp_fixpilot_blueprint_conflict');
assert(($sameKeyStoredVersionMismatch->data['status'] ?? null) === 409);
update_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint_version', 1);

update_post_meta(
    $draft['wordpress_object_id'],
    '_wp_fixpilot_blueprint_structure_hash',
    'legacy-structure-hash'
);
$sameKeyStoredHashMismatch = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Andere titel'],
    'seo' => [
        'title' => 'Tweede SEO titel',
        'description' => 'Andere omschrijving',
        'keyword' => 'andere zoekterm',
    ],
]);
assert(is_wp_error($sameKeyStoredHashMismatch));
assert($sameKeyStoredHashMismatch->code === 'wp_fixpilot_blueprint_conflict');
assert(($sameKeyStoredHashMismatch->data['status'] ?? null) === 409);
update_post_meta(
    $draft['wordpress_object_id'],
    '_wp_fixpilot_blueprint_structure_hash',
    $captured['structure_hash']
);

$mismatchedVersionRetry = $controller->create_draft(200, [
    'expected_version' => 2,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Andere titel'],
    'seo' => [
        'title' => 'Tweede SEO titel',
        'description' => 'Andere omschrijving',
        'keyword' => 'andere zoekterm',
    ],
]);
assert(is_wp_error($mismatchedVersionRetry));
assert($mismatchedVersionRetry->code === 'wp_fixpilot_blueprint_conflict');
assert(($mismatchedVersionRetry->data['status'] ?? null) === 409);

$sameKeyUnknownField = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-unknown' => 'Nee'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($sameKeyUnknownField));
assert($sameKeyUnknownField->code === 'wp_fixpilot_blueprint_field_unknown');

$unknownField = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-456',
    'replacements' => ['field-unknown' => 'Nee'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($unknownField));
assert($unknownField->code === 'wp_fixpilot_blueprint_field_unknown');
assert(!isset($GLOBALS['wpfixpilot_posts'][202]));

$emptyIdempotencyKeyDraftId = $GLOBALS['wpfixpilot_next_post_id'];
$emptyIdempotencyKey = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => '   ',
    'replacements' => ['field-title' => 'Mag niet lukken'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($emptyIdempotencyKey));
assert($emptyIdempotencyKey->code === 'wp_fixpilot_blueprint_invalid');
assert(($emptyIdempotencyKey->data['status'] ?? null) === 400);
assert(get_post($emptyIdempotencyKeyDraftId) === null);

$sanitizedEmptyIdempotencyKeyDraftId = $GLOBALS['wpfixpilot_next_post_id'];
$sanitizedEmptyIdempotencyKey = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => '<b> </b>',
    'replacements' => ['field-title' => 'Mag niet lukken'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($sanitizedEmptyIdempotencyKey));
assert($sanitizedEmptyIdempotencyKey->code === 'wp_fixpilot_blueprint_invalid');
assert(($sanitizedEmptyIdempotencyKey->data['status'] ?? null) === 400);
assert(get_post($sanitizedEmptyIdempotencyKeyDraftId) === null);

$liveBlueprintTree = get_post_meta(200, 'fake_blueprint_tree', true);
$liveBlueprintTree[0]['field-title'] = 'Handmatig aangepaste titel';
$liveBlueprintTree[0]['field-body'] = '<p>Handmatig aangepaste inhoud</p>';
update_post_meta(200, 'fake_blueprint_tree', $liveBlueprintTree);

$staleRead = $controller->read(200);
assert($staleRead['structure_hash'] !== $captured['structure_hash']);
assert(
    $staleRead['content_schema']['blocks'][0]['fields'][0]['current_value']
    === 'Handmatig aangepaste titel'
);
assert((string) get_post_meta(200, '_wp_fixpilot_structure_hash', true) === $captured['structure_hash']);
assert(
    get_post_meta(200, '_wp_fixpilot_content_schema', true)['blocks'][0]['fields'][0]['current_value']
    === 'Bestaande titel'
);

$staleDraft = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-stale',
    'replacements' => ['field-title' => 'Mag niet lukken'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($staleDraft));
assert($staleDraft->code === 'wp_fixpilot_blueprint_conflict');
assert(($staleDraft->data['status'] ?? null) === 409);
assert(!isset($GLOBALS['wpfixpilot_posts'][202]));

$sameKeyStaleRetry = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Nog steeds niet'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($sameKeyStaleRetry));
assert($sameKeyStaleRetry->code === 'wp_fixpilot_blueprint_conflict');
assert(($sameKeyStaleRetry->data['status'] ?? null) === 409);

$secondBlueprint = $controller->capture([
    'source_page_id' => 22,
    'name' => 'Tweede dienstpagina',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(!is_wp_error($secondBlueprint));

$crossBlueprintKeyReuse = $controller->create_draft(
    (int) $secondBlueprint['wordpress_blueprint_id'],
    [
        'expected_version' => 1,
        'expected_structure_hash' => $secondBlueprint['structure_hash'],
        'idempotency_key' => 'proposal-123',
        'replacements' => ['field-title' => 'Mag niet lukken'],
        'seo' => [
            'title' => 'SEO titel',
            'description' => 'SEO omschrijving',
            'keyword' => 'dsg revisie',
        ],
    ]
);
assert(is_wp_error($crossBlueprintKeyReuse));
assert($crossBlueprintKeyReuse->code === 'wp_fixpilot_blueprint_conflict');
assert(($crossBlueprintKeyReuse->data['status'] ?? null) === 409);

$publishedBlueprintId = (int) $secondBlueprint['wordpress_blueprint_id'];
get_post($publishedBlueprintId)->post_status = 'publish';

$publishedBlueprintRead = $controller->read($publishedBlueprintId);
assert(is_wp_error($publishedBlueprintRead));
assert($publishedBlueprintRead->code === 'wp_fixpilot_blueprint_not_draft');
assert(($publishedBlueprintRead->data['status'] ?? null) === 409);

$publishedBlueprintDraft = $controller->create_draft($publishedBlueprintId, [
    'expected_version' => 1,
    'expected_structure_hash' => $secondBlueprint['structure_hash'],
    'idempotency_key' => 'proposal-published-blueprint',
    'replacements' => ['field-title' => 'Mag niet lukken'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($publishedBlueprintDraft));
assert($publishedBlueprintDraft->code === 'wp_fixpilot_blueprint_not_draft');
assert(($publishedBlueprintDraft->data['status'] ?? null) === 409);

$publishedBlueprintDelete = $controller->delete($publishedBlueprintId);
assert(is_wp_error($publishedBlueprintDelete));
assert($publishedBlueprintDelete->code === 'wp_fixpilot_blueprint_not_draft');
assert(($publishedBlueprintDelete->data['status'] ?? null) === 409);
assert(get_post($publishedBlueprintId) instanceof WP_Post);

$noneSeoController = new WPFixPilot_Blueprint_Controller(
    [new Test_Blueprint_Adapter([21])],
    null,
    static fn (): ?string => null
);
$noneSeoBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
$noneSeoCapture = $noneSeoController->capture([
    'source_page_id' => 21,
    'name' => 'No SEO plugin blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(is_wp_error($noneSeoCapture));
assert($noneSeoCapture->code === 'wp_fixpilot_seo_plugin_unsupported');
assert(($noneSeoCapture->data['status'] ?? null) === 409);
assert(get_post($noneSeoBlueprintId) === null);

$capturedSeoPlugins = ['yoast', 'rank_math'];
$capturedSeoController = new WPFixPilot_Blueprint_Controller(
    [new Test_Blueprint_Adapter([22])],
    null,
    static function () use (&$capturedSeoPlugins): ?string {
        return array_shift($capturedSeoPlugins);
    }
);
$capturedSeoBlueprint = $capturedSeoController->capture([
    'source_page_id' => 22,
    'name' => 'Captured SEO plugin blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(!is_wp_error($capturedSeoBlueprint));
$capturedSeoBlueprintId = (int) $capturedSeoBlueprint['wordpress_blueprint_id'];
assert($capturedSeoBlueprint['seo_plugin'] === 'yoast');
assert((string) get_post_meta($capturedSeoBlueprintId, '_wp_fixpilot_seo_plugin', true) === 'yoast');
$capturedSeoRead = $capturedSeoController->read($capturedSeoBlueprintId);
assert($capturedSeoRead['seo_plugin'] === 'yoast');

$pluginDriftController = new WPFixPilot_Blueprint_Controller(
    [new Test_Blueprint_Adapter([22])],
    null,
    static fn (): ?string => 'rank_math'
);
$pluginDriftDraftId = $GLOBALS['wpfixpilot_next_post_id'];
$pluginDrift = $pluginDriftController->create_draft($capturedSeoBlueprintId, [
    'expected_version' => 1,
    'expected_structure_hash' => $capturedSeoBlueprint['structure_hash'],
    'idempotency_key' => 'proposal-plugin-drift',
    'replacements' => ['field-title' => 'Mag niet lukken'],
    'seo' => [
        'title' => 'SEO titel',
        'description' => 'SEO omschrijving',
        'keyword' => 'dsg revisie',
    ],
]);
assert(is_wp_error($pluginDrift));
assert($pluginDrift->code === 'wp_fixpilot_blueprint_conflict');
assert(($pluginDrift->data['status'] ?? null) === 409);
assert(get_post($pluginDriftDraftId) === null);

$validSchema = valid_test_blueprint_schema(20);
$invalidSchemaCases = [
    [
        'label' => 'schema version mismatch',
        'schema' => array_replace($validSchema, ['schema_version' => 'blueprint-v2']),
    ],
    [
        'label' => 'extra top-level key',
        'schema' => array_replace($validSchema, ['unexpected' => 'value']),
    ],
    [
        'label' => 'missing block semantic role',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            unset($schema['blocks'][0]['semantic_role']);

            return $schema;
        })(),
    ],
    [
        'label' => 'invalid block semantic role',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['semantic_role'] = 'footer';

            return $schema;
        })(),
    ],
    [
        'label' => 'extra block key',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['unexpected'] = 'value';

            return $schema;
        })(),
    ],
    [
        'label' => 'missing required field flag',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            unset($schema['blocks'][0]['fields'][0]['required']);

            return $schema;
        })(),
    ],
    [
        'label' => 'invalid field value type',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['fields'][0]['value_type'] = 'image';

            return $schema;
        })(),
    ],
    [
        'label' => 'non-string current value',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['fields'][0]['current_value'] = ['not-a-string'];

            return $schema;
        })(),
    ],
    [
        'label' => 'invalid max length',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['fields'][0]['max_length'] = 0;

            return $schema;
        })(),
    ],
    [
        'label' => 'extra field key',
        'schema' => (static function () use ($validSchema): array {
            $schema = $validSchema;
            $schema['blocks'][0]['fields'][0]['unexpected'] = 'value';

            return $schema;
        })(),
    ],
    [
        'label' => 'empty structure hash',
        'schema' => $validSchema,
        'structure_hash' => '',
    ],
];

foreach ($invalidSchemaCases as $invalidSchemaCase) {
    $invalidSchemaController = new WPFixPilot_Blueprint_Controller([
        new Schema_Contract_Blueprint_Adapter(
            [20],
            $invalidSchemaCase['schema'],
            $invalidSchemaCase['structure_hash'] ?? null
        ),
    ]);
    $invalidSchemaBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
    $invalidSchemaCapture = $invalidSchemaController->capture([
        'source_page_id' => 20,
        'name' => 'Invalid schema blueprint ' . $invalidSchemaCase['label'],
        'page_type' => 'service',
        'builder' => 'acf',
        'version' => 1,
    ]);
    assert(is_wp_error($invalidSchemaCapture), $invalidSchemaCase['label']);
    assert($invalidSchemaCapture->code === 'wp_fixpilot_blueprint_invalid', $invalidSchemaCase['label']);
    assert(($invalidSchemaCapture->data['status'] ?? null) === 500, $invalidSchemaCase['label']);
    assert(get_post($invalidSchemaBlueprintId) === null, $invalidSchemaCase['label']);
}

$schemaFailureController = new WPFixPilot_Blueprint_Controller([
    new Schema_Failing_Blueprint_Adapter([20]),
]);
$schemaFailureBlueprintId = $GLOBALS['wpfixpilot_next_post_id'];
$schemaFailure = $schemaFailureController->capture([
    'source_page_id' => 20,
    'name' => 'Schema failure blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(is_wp_error($schemaFailure));
assert($schemaFailure->code === 'wp_fixpilot_schema_failed');
assert(get_post($schemaFailureBlueprintId) === null);

$replacementFailureController = new WPFixPilot_Blueprint_Controller([
    new Apply_Failing_Blueprint_Adapter([21]),
]);
$replacementFailureCapture = $replacementFailureController->capture([
    'source_page_id' => 21,
    'name' => 'Replacement failure blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(!is_wp_error($replacementFailureCapture));
$replacementFailureDraftId = $GLOBALS['wpfixpilot_next_post_id'];
$replacementFailure = $replacementFailureController->create_draft(
    (int) $replacementFailureCapture['wordpress_blueprint_id'],
    [
        'expected_version' => 1,
        'expected_structure_hash' => $replacementFailureCapture['structure_hash'],
        'idempotency_key' => 'proposal-replacement-failure',
        'replacements' => ['field-title' => 'Nieuwe titel'],
        'seo' => [
            'title' => 'SEO titel',
            'description' => 'SEO omschrijving',
            'keyword' => 'dsg revisie',
        ],
    ]
);
assert(is_wp_error($replacementFailure));
assert($replacementFailure->code === 'wp_fixpilot_replacements_failed');
assert(get_post($replacementFailureDraftId) === null);

$seoFailureController = new WPFixPilot_Blueprint_Controller([
    new Test_Blueprint_Adapter([22]),
]);
$seoFailureCapture = $seoFailureController->capture([
    'source_page_id' => 22,
    'name' => 'SEO failure blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);
assert(!is_wp_error($seoFailureCapture));
$seoFailureDraftId = $GLOBALS['wpfixpilot_next_post_id'];
$GLOBALS['wpfixpilot_update_post_meta_failures'][$seoFailureDraftId] = [
    '_yoast_wpseo_title' => new RuntimeException('SEO meta write mislukt.'),
];
$seoFailure = $seoFailureController->create_draft(
    (int) $seoFailureCapture['wordpress_blueprint_id'],
    [
        'expected_version' => 1,
        'expected_structure_hash' => $seoFailureCapture['structure_hash'],
        'idempotency_key' => 'proposal-seo-failure',
        'replacements' => ['field-title' => 'Nieuwe titel'],
        'seo' => [
            'title' => 'SEO titel',
            'description' => 'SEO omschrijving',
            'keyword' => 'dsg revisie',
        ],
    ]
);
assert(is_wp_error($seoFailure));
assert($seoFailure->code === 'wp_fixpilot_draft_failed');
assert(get_post($seoFailureDraftId) === null);

$restAuth = new WPFixPilot_Auth(
    'test-secret',
    static fn (): int => 1710000000,
    300
);
$restController = new WPFixPilot_REST_Controller(
    null,
    new WPFixPilot_Blueprint_Controller([
        new Test_Blueprint_Adapter([19, 20, 22]),
    ]),
    $restAuth
);
$restController->register_routes();

$registeredRoutes = array_map(
    static fn (array $route): string => $route['route'],
    $GLOBALS['wpfixpilot_routes']
);
assert(in_array('/draft-pages', $registeredRoutes, true));
assert(in_array('/blueprints', $registeredRoutes, true));
assert(in_array('/blueprints/(?P<id>\d+)', $registeredRoutes, true));
assert(in_array('/blueprints/(?P<id>\d+)/drafts', $registeredRoutes, true));

$captureRoute = null;
foreach ($GLOBALS['wpfixpilot_routes'] as $route) {
    if ($route['route'] === '/blueprints') {
        $captureRoute = $route;
        break;
    }
}
assert(is_array($captureRoute));
assert($captureRoute['args']['permission_callback'] === [$restController, 'authorize']);

$restCapturePayload = [
    'source_page_id' => 20,
    'name' => 'REST blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restCaptureBody = wp_json_encode($restCapturePayload);
$restCaptureRoute = '/wpfixpilot/v1/blueprints';
$restCaptureTimestamp = '1710000000';
$restCaptureNonce = 'rest-blueprint-capture';
$restCaptureSignature = WPFixPilot_Auth::sign(
    'test-secret',
    'POST',
    $restCaptureRoute,
    $restCaptureTimestamp,
    $restCaptureNonce,
    $restCaptureBody
);
$authorizedCaptureRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restCapturePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => $restCaptureNonce,
        'x-wp-fixpilot-signature' => $restCaptureSignature,
    ],
    $restCaptureBody
);
assert(($captureRoute['args']['permission_callback'])($authorizedCaptureRequest) === true);
$captureResponse = ($captureRoute['args']['callback'])($authorizedCaptureRequest);
assert($captureResponse instanceof WP_REST_Response);
assert($captureResponse->status === 201);
assert($captureResponse->get_data()['status'] === 'ready');
assert($captureResponse->get_data()['created'] === true);

$restInvalidNamePayload = [
    'source_page_id' => 20,
    'name' => '   ',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restInvalidNameBody = wp_json_encode($restInvalidNamePayload);
$restInvalidNameRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restInvalidNamePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-invalid-name',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restCaptureRoute,
            $restCaptureTimestamp,
            'rest-blueprint-capture-invalid-name',
            $restInvalidNameBody
        ),
    ],
    $restInvalidNameBody
);
$restInvalidName = ($captureRoute['args']['callback'])($restInvalidNameRequest);
assert(is_wp_error($restInvalidName));
assert($restInvalidName->code === 'wp_fixpilot_blueprint_invalid');
assert(($restInvalidName->data['status'] ?? null) === 400);

$restInvalidPageTypePayload = [
    'source_page_id' => 20,
    'name' => 'REST blueprint',
    'page_type' => 'landing page',
    'builder' => 'acf',
    'version' => 1,
];
$restInvalidPageTypeBody = wp_json_encode($restInvalidPageTypePayload);
$restInvalidPageTypeRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restInvalidPageTypePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-invalid-page-type',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restCaptureRoute,
            $restCaptureTimestamp,
            'rest-blueprint-capture-invalid-page-type',
            $restInvalidPageTypeBody
        ),
    ],
    $restInvalidPageTypeBody
);
$restInvalidPageType = ($captureRoute['args']['callback'])($restInvalidPageTypeRequest);
assert(is_wp_error($restInvalidPageType));
assert($restInvalidPageType->code === 'wp_fixpilot_blueprint_invalid');
assert(($restInvalidPageType->data['status'] ?? null) === 400);

$restInvalidSourcePageIdPayload = [
    'source_page_id' => '20abc',
    'name' => 'REST blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restInvalidSourcePageIdBody = wp_json_encode($restInvalidSourcePageIdPayload);
$restInvalidSourcePageIdRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restInvalidSourcePageIdPayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-invalid-source',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restCaptureRoute,
            $restCaptureTimestamp,
            'rest-blueprint-capture-invalid-source',
            $restInvalidSourcePageIdBody
        ),
    ],
    $restInvalidSourcePageIdBody
);
$restInvalidSourcePageId = ($captureRoute['args']['callback'])($restInvalidSourcePageIdRequest);
assert(is_wp_error($restInvalidSourcePageId));
assert($restInvalidSourcePageId->code === 'wp_fixpilot_blueprint_invalid');
assert(($restInvalidSourcePageId->data['status'] ?? null) === 400);

$restMissingSourcePayload = [
    'source_page_id' => 999,
    'name' => 'REST missing source blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restMissingSourceBody = wp_json_encode($restMissingSourcePayload);
$restMissingSourceRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restMissingSourcePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-missing-source',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restCaptureRoute,
            $restCaptureTimestamp,
            'rest-blueprint-capture-missing-source',
            $restMissingSourceBody
        ),
    ],
    $restMissingSourceBody
);
$restMissingSource = ($captureRoute['args']['callback'])($restMissingSourceRequest);
assert(is_wp_error($restMissingSource));
assert($restMissingSource->code === 'wp_fixpilot_source_missing');
assert(($restMissingSource->data['status'] ?? null) === 404);

$restDraftCapturePayload = [
    'source_page_id' => 22,
    'name' => 'REST draft blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restDraftCaptureBody = wp_json_encode($restDraftCapturePayload);
$restDraftCaptureTimestamp = '1710000003';
$restDraftCaptureNonce = 'rest-blueprint-draft-capture';
$restDraftCaptureSignature = WPFixPilot_Auth::sign(
    'test-secret',
    'POST',
    $restCaptureRoute,
    $restDraftCaptureTimestamp,
    $restDraftCaptureNonce,
    $restDraftCaptureBody
);
$restDraftCaptureRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restDraftCapturePayload,
    [
        'x-wp-fixpilot-timestamp' => $restDraftCaptureTimestamp,
        'x-wp-fixpilot-nonce' => $restDraftCaptureNonce,
        'x-wp-fixpilot-signature' => $restDraftCaptureSignature,
    ],
    $restDraftCaptureBody
);
$restDraftCaptureResponse = ($captureRoute['args']['callback'])($restDraftCaptureRequest);
assert($restDraftCaptureResponse instanceof WP_REST_Response);
assert($restDraftCaptureResponse->status === 201);
assert($restDraftCaptureResponse->get_data()['created'] === true);

$draftRoute = null;
foreach ($GLOBALS['wpfixpilot_routes'] as $route) {
    if ($route['route'] === '/blueprints/(?P<id>\d+)/drafts') {
        $draftRoute = $route;
        break;
    }
}
assert(is_array($draftRoute));

$restDraftPayload = [
    'expected_version' => 1,
    'expected_structure_hash' => $restDraftCaptureResponse->get_data()['structure_hash'],
    'idempotency_key' => 'rest-blueprint-draft-1',
    'replacements' => ['field-title' => 'REST titel'],
    'seo' => [
        'title' => 'REST SEO titel',
        'description' => 'REST SEO omschrijving',
        'keyword' => 'rest zoekterm',
    ],
];
$restDraftBody = wp_json_encode($restDraftPayload);
$restDraftBlueprintId = (int) $restDraftCaptureResponse->get_data()['wordpress_blueprint_id'];
$restDraftRoute = '/wpfixpilot/v1/blueprints/' . $restDraftBlueprintId . '/drafts';
$restDraftPostsBefore = count($GLOBALS['wpfixpilot_posts']);
$restDraftTimestamp = '1710000001';
$restDraftNonce = 'rest-blueprint-draft-first';
$restDraftSignature = WPFixPilot_Auth::sign(
    'test-secret',
    'POST',
    $restDraftRoute,
    $restDraftTimestamp,
    $restDraftNonce,
    $restDraftBody
);
$restDraftRequest = new WP_REST_Request(
    'POST',
    $restDraftRoute,
    array_merge(['id' => $restDraftBlueprintId], $restDraftPayload),
    [
        'x-wp-fixpilot-timestamp' => $restDraftTimestamp,
        'x-wp-fixpilot-nonce' => $restDraftNonce,
        'x-wp-fixpilot-signature' => $restDraftSignature,
    ],
    $restDraftBody
);
$restDraftFirst = ($draftRoute['args']['callback'])($restDraftRequest);
assert($restDraftFirst->status === 201);
assert($restDraftFirst->get_data()['created'] === true);
assert(count($GLOBALS['wpfixpilot_posts']) === $restDraftPostsBefore + 1);

$restDraftReplayPayload = $restDraftPayload;
$restDraftReplayBody = wp_json_encode($restDraftReplayPayload);
$restDraftReplayTimestamp = '1710000002';
$restDraftReplayNonce = 'rest-blueprint-draft-replay';
$restDraftReplaySignature = WPFixPilot_Auth::sign(
    'test-secret',
    'POST',
    $restDraftRoute,
    $restDraftReplayTimestamp,
    $restDraftReplayNonce,
    $restDraftReplayBody
);
$restDraftReplayRequest = new WP_REST_Request(
    'POST',
    $restDraftRoute,
    array_merge(['id' => $restDraftBlueprintId], $restDraftReplayPayload),
    [
        'x-wp-fixpilot-timestamp' => $restDraftReplayTimestamp,
        'x-wp-fixpilot-nonce' => $restDraftReplayNonce,
        'x-wp-fixpilot-signature' => $restDraftReplaySignature,
    ],
    $restDraftReplayBody
);
$restDraftReplay = ($draftRoute['args']['callback'])($restDraftReplayRequest);
assert($restDraftReplay instanceof WP_REST_Response);
assert($restDraftReplay->status === 200);
assert($restDraftReplay->get_data()['wordpress_object_id'] === $restDraftFirst->get_data()['wordpress_object_id']);
assert($restDraftReplay->get_data()['created'] === false);
assert(count($GLOBALS['wpfixpilot_posts']) === $restDraftPostsBefore + 1);

$restWhitespaceIdempotencyPayload = $restDraftPayload;
$restWhitespaceIdempotencyPayload['idempotency_key'] = '   ';
$restWhitespaceIdempotencyBody = wp_json_encode($restWhitespaceIdempotencyPayload);
$restWhitespaceIdempotencyRequest = new WP_REST_Request(
    'POST',
    $restDraftRoute,
    array_merge(['id' => $restDraftBlueprintId], $restWhitespaceIdempotencyPayload),
    [
        'x-wp-fixpilot-timestamp' => '1710000004',
        'x-wp-fixpilot-nonce' => 'rest-blueprint-draft-empty-key',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restDraftRoute,
            '1710000004',
            'rest-blueprint-draft-empty-key',
            $restWhitespaceIdempotencyBody
        ),
    ],
    $restWhitespaceIdempotencyBody
);
$restWhitespaceIdempotency = ($draftRoute['args']['callback'])($restWhitespaceIdempotencyRequest);
assert(is_wp_error($restWhitespaceIdempotency));
assert($restWhitespaceIdempotency->code === 'wp_fixpilot_blueprint_invalid');
assert(($restWhitespaceIdempotency->data['status'] ?? null) === 400);
assert(count($GLOBALS['wpfixpilot_posts']) === $restDraftPostsBefore + 1);

$restNoSeoController = new WPFixPilot_REST_Controller(
    null,
    new WPFixPilot_Blueprint_Controller(
        [new Test_Blueprint_Adapter([21])],
        null,
        static fn (): ?string => null
    ),
    $restAuth
);
$restNoSeoPayload = [
    'source_page_id' => 21,
    'name' => 'REST no SEO blueprint',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
];
$restNoSeoBody = wp_json_encode($restNoSeoPayload);
$restNoSeoRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restNoSeoPayload,
    [
        'x-wp-fixpilot-timestamp' => '1710000005',
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-no-seo',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            $restCaptureRoute,
            '1710000005',
            'rest-blueprint-capture-no-seo',
            $restNoSeoBody
        ),
    ],
    $restNoSeoBody
);
$restNoSeo = $restNoSeoController->capture_blueprint($restNoSeoRequest);
assert(is_wp_error($restNoSeo));
assert($restNoSeo->code === 'wp_fixpilot_seo_plugin_unsupported');
assert(($restNoSeo->data['status'] ?? null) === 409);

$wrongRouteSignatureRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restCapturePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-wrong-route',
        'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
            'test-secret',
            'POST',
            '/wp-json/wpfixpilot/v1/blueprints',
            $restCaptureTimestamp,
            'rest-blueprint-capture-wrong-route',
            $restCaptureBody
        ),
    ],
    $restCaptureBody
);
$wrongRouteSignature = ($captureRoute['args']['permission_callback'])($wrongRouteSignatureRequest);
assert(is_wp_error($wrongRouteSignature));
assert($wrongRouteSignature->code === 'wp_fixpilot_forbidden');
assert(($wrongRouteSignature->data['status'] ?? null) === 403);

$forbiddenCaptureRequest = new WP_REST_Request(
    'POST',
    $restCaptureRoute,
    $restCapturePayload,
    [
        'x-wp-fixpilot-timestamp' => $restCaptureTimestamp,
        'x-wp-fixpilot-nonce' => 'rest-blueprint-capture-invalid',
        'x-wp-fixpilot-signature' => 'not-a-valid-signature',
    ],
    $restCaptureBody
);
$forbidden = ($captureRoute['args']['permission_callback'])($forbiddenCaptureRequest);
assert(is_wp_error($forbidden));
assert($forbidden->code === 'wp_fixpilot_forbidden');
assert(($forbidden->data['status'] ?? null) === 403);

$replayedNonce = ($captureRoute['args']['permission_callback'])($authorizedCaptureRequest);
assert(is_wp_error($replayedNonce));
assert($replayedNonce->code === 'wp_fixpilot_forbidden');
assert(($replayedNonce->data['status'] ?? null) === 403);

$inventory = $restController->inventory()->get_data();
assert($inventory['count'] === 6);
assert(array_column($inventory['items'], 'id') === [19, 20, 21, 22, 201, 222]);

$health = $restController->health()->get_data();
assert($health['plugin_version'] === '0.3.0');

echo "blueprint lifecycle tests passed\n";
