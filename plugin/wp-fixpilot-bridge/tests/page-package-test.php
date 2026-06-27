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
    public string $post_content = 'template';
    public string $post_excerpt = '';
    public int $post_parent = 0;
    public int $menu_order = 0;
}

define('WPSEO_VERSION', 'test');
$GLOBALS['wpfixpilot_posts'] = [];
$GLOBALS['wpfixpilot_meta'] = [];
$GLOBALS['wpfixpilot_insert_count'] = 0;
$GLOBALS['wpfixpilot_acf_fields'] = [];
$GLOBALS['wpfixpilot_updated_fields'] = [];

function sanitize_text_field(string $value): string { return trim($value); }
function sanitize_key(string $value): string { return preg_replace('/[^a-z0-9_\-]/', '', strtolower($value)); }
function sanitize_title(string $value): string { return trim(strtolower(str_replace(' ', '-', $value)), '-'); }
function esc_html(string $value): string { return htmlspecialchars($value, ENT_QUOTES); }
function esc_url(string $value): string { return $value; }
function wp_kses_post(string $value): string { return $value; }
function maybe_unserialize(mixed $value): mixed { return $value; }
function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function get_page_template_slug(int $postId): string { return 'templates/service.php'; }
function get_edit_post_link(int $postId, string $context): string { return 'https://example.com/wp-admin/post.php?post=' . $postId; }
function get_posts(array $args): array
{
    foreach ($GLOBALS['wpfixpilot_meta'] as $postId => $meta) {
        if (($meta['_wp_fixpilot_idempotency_key'] ?? null) === $args['meta_value']) {
            return [$postId];
        }
    }
    return [];
}
function get_post(int $postId): ?WP_Post
{
    if ($postId === 10) {
        $post = new WP_Post();
        $post->ID = 10;
        return $post;
    }
    return $GLOBALS['wpfixpilot_posts'][$postId] ?? null;
}
function wp_insert_post(array $postData, bool $wpError = false): int
{
    assert($postData['post_status'] === 'draft');
    $post = new WP_Post();
    $post->ID = 20;
    $post->post_status = 'draft';
    $post->post_content = $postData['post_content'];
    $GLOBALS['wpfixpilot_posts'][20] = $post;
    $GLOBALS['wpfixpilot_insert_count']++;
    return 20;
}
function wp_update_post(array $postData, bool $wpError = false): int
{
    $post = $GLOBALS['wpfixpilot_posts'][(int) $postData['ID']];
    $post->post_status = (string) ($postData['post_status'] ?? $post->post_status);
    return $post->ID;
}
function wp_delete_post(int $postId, bool $force): void { unset($GLOBALS['wpfixpilot_posts'][$postId]); }
function get_post_meta(int $postId, string $key = '', bool $single = false): mixed
{
    if ($key === '') return $GLOBALS['wpfixpilot_meta'][$postId] ?? [];
    return $GLOBALS['wpfixpilot_meta'][$postId][$key] ?? ($single ? '' : []);
}
function update_post_meta(int $postId, string $key, mixed $value): void { $GLOBALS['wpfixpilot_meta'][$postId][$key] = $value; }
function add_post_meta(int $postId, string $key, mixed $value): void { $GLOBALS['wpfixpilot_meta'][$postId][$key] = $value; }
function get_field_objects(int $postId): array { return $GLOBALS['wpfixpilot_acf_fields'][$postId] ?? []; }
function update_field(string $fieldKey, mixed $value, int $postId): bool
{
    $GLOBALS['wpfixpilot_updated_fields'][$postId][$fieldKey] = $value;
    return true;
}
function wp_json_encode(mixed $value): string { return (string) json_encode($value); }
function wp_strip_all_tags(string $value): string { return strip_tags($value); }

require_once __DIR__ . '/../includes/builder-adapters/interface-builder-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-gutenberg-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-elementor-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-bricks-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-wpbakery-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-acf-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/interface-seo-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-adapter-changes.php';
require_once __DIR__ . '/../includes/seo-adapters/class-yoast-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-rank-math-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-aioseo-adapter.php';
require_once __DIR__ . '/../includes/class-page-package-controller.php';

$adapters = [
    new WPFixPilot_Gutenberg_Adapter(),
    new WPFixPilot_Elementor_Adapter(),
    new WPFixPilot_Bricks_Adapter(),
    new WPFixPilot_WPBakery_Adapter(),
    new WPFixPilot_ACF_Adapter(),
];

$keys = array_map(
    static fn (WPFixPilot_Builder_Adapter $adapter): string => $adapter->key(),
    $adapters
);

assert($keys === ['gutenberg', 'elementor', 'bricks', 'wpbakery', 'acf']);
assert(count(array_unique($keys)) === 5);

$GLOBALS['wpfixpilot_acf_fields'][10] = [
    'page_blocks' => [
        'key' => 'field_page_blocks',
        'name' => 'page_blocks',
        'label' => 'Paginablokken',
        'type' => 'flexible_content',
        'value' => [
            [
                'acf_fc_layout' => 'hero',
                'title' => 'Transmissie onderhoud Schiedam',
                'description' => '<p>Voorkom dure reparaties met tijdig onderhoud.</p>',
            ],
            [
                'acf_fc_layout' => 'content',
                'heading' => 'Zo werkt transmissie onderhoud',
                'body' => '<p>Onze specialisten controleren olie en slijtage.</p>',
            ],
            [
                'acf_fc_layout' => 'faq',
                'heading' => 'Veelgestelde vragen',
                'body' => '<p>Lees de antwoorden over onderhoud.</p>',
            ],
        ],
    ],
];
$acfAdapter = new WPFixPilot_ACF_Adapter();
$acfSlots = $acfAdapter->inspect(10);
assert(count($acfSlots) === 6);
assert($acfSlots[0]['path'] === 'acf-value:field_page_blocks:0/title');
assert($acfSlots[0]['label'] === 'Paginablokken · Transmissie onderhoud Schiedam');
assert($acfSlots[1]['value_type'] === 'html');
$acfWrite = $acfAdapter->write(
    10,
    [
        'hero_title' => 'acf-value:field_page_blocks:0/title',
        'introduction' => 'acf-value:field_page_blocks:0/description',
    ],
    [
        'hero_title' => 'Nieuwe hero',
        'introduction' => '<p>Nieuwe introductie.</p>',
    ]
);
assert($acfWrite === true);
assert(
    $GLOBALS['wpfixpilot_updated_fields'][10]['field_page_blocks'][0]['title']
    === 'Nieuwe hero'
);
assert(
    $GLOBALS['wpfixpilot_updated_fields'][10]['field_page_blocks'][0]['description']
    === '<p>Nieuwe introductie.</p>'
);

final class Test_Page_Package_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string { return 'gutenberg'; }
    public function is_active(): bool { return true; }
    public function inspect(int $postId): array { return []; }
    public function template_hash(int $postId): string { return $postId === 10 ? 'template-hash' : 'draft-hash'; }
    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        assert($postId === 20);
        assert($values['hero_title'] === 'DSG revisie');
        return true;
    }
}

$payload = [
    'template_id' => 10,
    'expected_template_hash' => 'template-hash',
    'builder' => 'gutenberg',
    'mapping' => [
        'hero_title' => 'block:0',
        'introduction' => 'block:1',
        'main_content' => 'block:2',
        'faq' => 'block:3',
        'cta_title' => 'block:4',
        'cta_text' => 'block:5',
    ],
    'seo_plugin' => 'yoast',
    'idempotency_key' => 'proposal-1',
    'package' => [
        'title' => 'DSG revisie pagina',
        'slug' => 'dsg-revisie',
        'seo_title' => 'DSG revisie door een specialist',
        'meta_description' => 'Laat uw DSG deskundig onderzoeken en reviseren.',
        'focus_keyword' => 'dsg revisie',
        'hero_title' => 'DSG revisie',
        'introduction_html' => '<p>Introductie</p>',
        'sections' => [['heading' => 'Werkwijze', 'body_html' => '<p>Diagnose</p>']],
        'faq' => [['question' => 'Hoe werkt het?', 'answer_html' => '<p>Na diagnose.</p>']],
        'cta' => ['title' => 'Afspraak', 'body_html' => '<p>Neem contact op.</p>', 'button_label' => 'Contact', 'button_url' => '/contact/'],
        'internal_links' => [['anchor' => 'Contact', 'url' => '/contact/']],
    ],
];
$controller = new WPFixPilot_Page_Package_Controller([new Test_Page_Package_Adapter()]);
$created = $controller->create_draft($payload);
$repeated = $controller->create_draft($payload);
assert(!is_wp_error($created));
assert($created['status'] === 'draft');
assert($created['wordpress_object_id'] === 20);
assert($repeated['wordpress_object_id'] === 20);
assert($GLOBALS['wpfixpilot_insert_count'] === 1);

$conflictPayload = $payload;
$conflictPayload['idempotency_key'] = 'proposal-2';
$conflictPayload['expected_template_hash'] = 'stale-hash';
$conflict = $controller->create_draft($conflictPayload);
assert(is_wp_error($conflict));
assert($conflict->code === 'wp_fixpilot_template_conflict');
assert($GLOBALS['wpfixpilot_insert_count'] === 1);

echo "page package adapter tests passed\n";
