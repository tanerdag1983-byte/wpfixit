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

final class WP_Post_Type
{
    public bool $public;
    public bool $publicly_queryable;
    public bool $show_ui;
    public bool $exclude_from_search;

    public function __construct(array $args)
    {
        $this->public = (bool) ($args['public'] ?? false);
        $this->publicly_queryable = (bool) ($args['publicly_queryable'] ?? false);
        $this->show_ui = (bool) ($args['show_ui'] ?? false);
        $this->exclude_from_search = (bool) ($args['exclude_from_search'] ?? false);
    }
}

$GLOBALS['wpfixpilot_posts'] = [];
$GLOBALS['wpfixpilot_meta'] = [];
$GLOBALS['wpfixpilot_post_types'] = [];
$GLOBALS['wpfixpilot_next_post_id'] = 100;

function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function sanitize_text_field(string $value): string { return trim(strip_tags($value)); }
function sanitize_key(string $value): string { return preg_replace('/[^a-z0-9_\-]/', '', strtolower($value)); }
function sanitize_title(string $value): string { return trim(strtolower(str_replace(' ', '-', $value)), '-'); }
function maybe_unserialize(mixed $value): mixed { return $value; }
function wp_json_encode(mixed $value): string { return (string) json_encode($value); }
function wp_strip_all_tags(string $value): string { return strip_tags($value); }
function wp_kses_post(string $value): string { return $value; }
function esc_url_raw(string $value): string { return $value; }
function get_post(int $postId): ?WP_Post { return $GLOBALS['wpfixpilot_posts'][$postId] ?? null; }
function get_post_meta(int $postId, string $key = '', bool $single = false): mixed
{
    $meta = $GLOBALS['wpfixpilot_meta'][$postId] ?? [];
    if ($key === '') {
        return $meta;
    }
    if (!array_key_exists($key, $meta)) {
        return $single ? '' : [];
    }

    return $single ? $meta[$key][0] : $meta[$key];
}
function update_post_meta(int $postId, string $key, mixed $value): bool
{
    $GLOBALS['wpfixpilot_meta'][$postId][$key] = [$value];

    return true;
}
function add_post_meta(int $postId, string $key, mixed $value): bool
{
    $GLOBALS['wpfixpilot_meta'][$postId][$key] ??= [];
    $GLOBALS['wpfixpilot_meta'][$postId][$key][] = $value;

    return true;
}
function wp_insert_post(array $postData, bool $wpError = false): int
{
    $post = new WP_Post();
    $post->ID = $GLOBALS['wpfixpilot_next_post_id']++;
    foreach (['post_type', 'post_status', 'post_title', 'post_name', 'post_content', 'post_excerpt', 'post_parent', 'menu_order'] as $field) {
        if (array_key_exists($field, $postData)) {
            $post->{$field} = $postData[$field];
        }
    }
    $GLOBALS['wpfixpilot_posts'][$post->ID] = $post;

    return $post->ID;
}
function wp_delete_post(int $postId, bool $force): void
{
    unset($GLOBALS['wpfixpilot_posts'][$postId], $GLOBALS['wpfixpilot_meta'][$postId]);
}
function register_post_type(string $postType, array $args): void
{
    $GLOBALS['wpfixpilot_post_types'][$postType] = new WP_Post_Type($args);
}
function get_post_type_object(string $postType): ?WP_Post_Type
{
    return $GLOBALS['wpfixpilot_post_types'][$postType] ?? null;
}

require_once __DIR__ . '/../includes/builder-adapters/interface-blueprint-adapter.php';
require_once __DIR__ . '/../includes/class-template-snapshot-store.php';
require_once __DIR__ . '/../includes/class-post-cloner.php';
require_once __DIR__ . '/../includes/class-blueprint-controller.php';

final class Snapshot_Test_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string { return 'snapshot-test'; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool { return $postId === 41; }
    public function clone_meta_keys(int $postId): array { return ['snapshot_test_tree']; }

    public function schema(int $postId): array|WP_Error
    {
        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => [[
                'id' => 'copy',
                'layout' => 'content',
                'label' => 'Content',
                'semantic_role' => 'content',
                'fields' => [[
                    'id' => 'copy:title',
                    'path' => 'snapshot_test_tree/title',
                    'label' => 'Titel',
                    'value_type' => 'heading',
                    'current_value' => (string) get_post_meta($postId, 'snapshot_test_tree', true)['title'],
                    'required' => true,
                    'max_length' => 180,
                ]],
            ]],
        ];
    }

    public function structure_hash(int $postId): string
    {
        return hash('sha256', wp_json_encode(get_post_meta($postId, 'snapshot_test_tree', true)));
    }

    public function apply_replacements(int $postId, array $schema, array $replacements): bool|WP_Error
    {
        return true;
    }
}

function seed_snapshot_source(): void
{
    $post = new WP_Post();
    $post->ID = 41;
    $post->post_title = 'Bronpagina';
    $post->post_name = 'bronpagina';
    $post->post_content = '<section>Broninhoud</section>';
    $GLOBALS['wpfixpilot_posts'][41] = $post;
    $GLOBALS['wpfixpilot_meta'][41] = ['snapshot_test_tree' => [['title' => 'Bronpagina']]];
}

function blueprint_controller(): WPFixPilot_Blueprint_Controller
{
    return new WPFixPilot_Blueprint_Controller(
        [new Snapshot_Test_Adapter()],
        null,
        static fn (): ?string => 'yoast'
    );
}

function test_snapshot_post_type_is_private(): void
{
    $store = new WPFixPilot_Template_Snapshot_Store();
    $store->register();
    $object = get_post_type_object(WPFixPilot_Template_Snapshot_Store::POST_TYPE);

    assert($object instanceof WP_Post_Type);
    assert($object->public === false);
    assert($object->publicly_queryable === false);
    assert($object->show_ui === false);
    assert($object->exclude_from_search === true);
}

function test_capture_creates_snapshot_without_mutating_source(): void
{
    seed_snapshot_source();
    $sourceBefore = clone get_post(41);
    $result = blueprint_controller()->capture([
        'source_page_id' => 41,
        'name' => 'Dienstpagina',
        'page_type' => 'service',
        'version' => 1,
    ]);

    assert(!is_wp_error($result));
    assert($result['wordpress_snapshot_id'] === $result['wordpress_blueprint_id']);
    assert($result['snapshot_version'] === 1);
    assert($result['schema_version'] === 'snapshot-text-v1');
    assert(get_post($result['wordpress_snapshot_id'])->post_type === 'wpfixpilot_snapshot');
    assert(get_post($result['wordpress_snapshot_id'])->post_status === 'private');
    assert((new WPFixPilot_Template_Snapshot_Store())->assert_snapshot(
        $result['wordpress_snapshot_id']
    ) instanceof WP_Post);
    assert(is_wp_error((new WPFixPilot_Template_Snapshot_Store())->assert_snapshot(41)));
    assert(get_post(41) == $sourceBefore);
}

test_snapshot_post_type_is_private();
test_capture_creates_snapshot_without_mutating_source();

echo "template snapshot tests passed\n";
