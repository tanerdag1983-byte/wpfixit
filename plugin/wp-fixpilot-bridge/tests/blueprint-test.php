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

function sanitize_text_field(string $value): string { return trim($value); }
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
function update_post_meta(int $postId, string $key, mixed $value): void
{
    $GLOBALS['wpfixpilot_meta'][$postId][$key] = [$value];
}
function add_post_meta(int $postId, string $key, mixed $value): void
{
    $GLOBALS['wpfixpilot_meta'][$postId][$key] ??= [];
    $GLOBALS['wpfixpilot_meta'][$postId][$key][] = $value;
}

$source = new WP_Post();
$source->ID = 19;
$source->post_title = 'Transmissie onderhoud';
$source->post_content = '<section>Originele content</section>';
$source->post_excerpt = 'Originele samenvatting';
$source->post_parent = 3;
$source->menu_order = 2;
$GLOBALS['wpfixpilot_posts'][19] = $source;
$GLOBALS['wpfixpilot_meta'][19] = [
    '_wp_page_template' => ['algemeen-productdetail.php'],
    '_thumbnail_id' => [77],
    'fake_blueprint_tree' => [[[
        'field-title' => 'Bestaande titel',
        'field-body' => '<p>Bestaande inhoud</p>',
    ]]],
    'analytics_state' => ['skip-me'],
    '_edit_lock' => ['1700000000:1'],
    '_wp_fixpilot_idempotency_key' => ['proposal-legacy'],
];

require_once __DIR__ . '/../includes/builder-adapters/interface-blueprint-adapter.php';

final class Test_Blueprint_Adapter implements WPFixPilot_Blueprint_Adapter
{
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
        return $postId === 19 || $postId >= 200;
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

$controller = new WPFixPilot_Blueprint_Controller([
    new Test_Blueprint_Adapter(),
]);

$captured = $controller->capture([
    'source_page_id' => 19,
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

$read = $controller->read(200);
assert($read['content_schema']['schema_version'] === 'blueprint-v1');
assert($read['structure_hash'] === $captured['structure_hash']);

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
assert(get_post($draft['wordpress_object_id'])->post_type === 'page');
assert(get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint', true) === '');
assert(get_post_meta($draft['wordpress_object_id'], '_yoast_wpseo_title', true) === 'SEO titel');
assert(get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_source_blueprint_id', true) === 200);
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

$restController = new WPFixPilot_REST_Controller();
$restController->register_routes();

$registeredRoutes = array_map(
    static fn (array $route): string => $route['route'],
    $GLOBALS['wpfixpilot_routes']
);
assert(in_array('/draft-pages', $registeredRoutes, true));
assert(in_array('/blueprints', $registeredRoutes, true));
assert(in_array('/blueprints/(?P<id>\d+)', $registeredRoutes, true));
assert(in_array('/blueprints/(?P<id>\d+)/drafts', $registeredRoutes, true));

$inventory = $restController->inventory()->get_data();
assert($inventory['count'] === 2);
assert(array_column($inventory['items'], 'id') === [19, 201]);

$health = $restController->health()->get_data();
assert($health['plugin_version'] === '0.3.0');

echo "blueprint lifecycle tests passed\n";
