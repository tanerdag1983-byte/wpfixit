<?php

declare(strict_types=1);

final class WP_Error
{
    public function __construct(
        public string $code,
        public string $message,
        public array $data = []
    ) {}
}

final class WP_Post
{
    public int $ID;
    public string $post_type = 'page';
    public string $post_status = 'draft';
    public string $post_title = '';
    public string $post_name = '';
    public string $post_content = '';
    public string $post_excerpt = '';
    public int $post_parent = 0;
    public int $menu_order = 0;
}

if (!defined('ELEMENTOR_VERSION')) {
    define('ELEMENTOR_VERSION', 'test');
}
if (!defined('WPB_VC_VERSION')) {
    define('WPB_VC_VERSION', 'test');
}
if (!defined('BRICKS_VERSION')) {
    define('BRICKS_VERSION', 'test');
}
if (!defined('WPSEO_VERSION')) {
    define('WPSEO_VERSION', 'test');
}

$GLOBALS['wpfixpilot_posts'] = [];
$GLOBALS['wpfixpilot_meta'] = [];
$GLOBALS['wpfixpilot_update_post_meta_failures'] = [];
$GLOBALS['wpfixpilot_update_post_meta_calls'] = [];
$GLOBALS['wpfixpilot_wp_update_post_results'] = [];
$GLOBALS['wpfixpilot_acf_fields'] = [];
$GLOBALS['wpfixpilot_acf_runtime'] = [];
$GLOBALS['wpfixpilot_acf_aliases'] = [];
$GLOBALS['wpfixpilot_update_field_calls'] = [];
$GLOBALS['wpfixpilot_update_field_failures'] = [];
$GLOBALS['wpfixpilot_update_field_normalizers'] = [];

function sanitize_text_field(string $value): string
{
    return trim(strip_tags($value));
}

function sanitize_key(string $value): string
{
    return (string) preg_replace('/[^a-z0-9_\-]/', '', strtolower($value));
}

function sanitize_title(string $value): string
{
    return trim(strtolower(str_replace(' ', '-', $value)), '-');
}

function esc_html(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES);
}

function esc_url(string $value): string
{
    return $value;
}

function esc_url_raw(string $value): string
{
    return $value;
}

function wp_kses_post(string $value): string
{
    return (string) preg_replace('#<script\b[^>]*>.*?</script>#is', '', $value);
}

function maybe_unserialize(mixed $value): mixed
{
    return $value;
}

function is_wp_error(mixed $value): bool
{
    return $value instanceof WP_Error;
}

function wp_json_encode(mixed $value): string
{
    return (string) json_encode($value);
}

function wp_strip_all_tags(string $value): string
{
    return strip_tags($value);
}

function wp_slash(string $value): string
{
    return $value;
}

if (!function_exists('mb_substr')) {
    function mb_substr(string $string, int $start, ?int $length = null): string
    {
        return $length === null
            ? substr($string, $start)
            : substr($string, $start, $length);
    }
}

function get_post(int $postId): ?WP_Post
{
    return $GLOBALS['wpfixpilot_posts'][$postId] ?? null;
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
    $GLOBALS['wpfixpilot_update_post_meta_calls'][] = [$postId, $key, $value];
    if (($GLOBALS['wpfixpilot_update_post_meta_failures'][$postId][$key] ?? false) === true) {
        return false;
    }
    if (($GLOBALS['wpfixpilot_meta'][$postId][$key][0] ?? null) === $value) {
        return false;
    }

    $GLOBALS['wpfixpilot_meta'][$postId][$key] = [$value];

    return true;
}

function add_post_meta(int $postId, string $key, mixed $value): bool
{
    $GLOBALS['wpfixpilot_meta'][$postId][$key] ??= [];
    $GLOBALS['wpfixpilot_meta'][$postId][$key][] = $value;

    return true;
}

function wp_update_post(array $postData, bool $wpError = false): int|WP_Error
{
    $postId = (int) ($postData['ID'] ?? 0);
    $result = $GLOBALS['wpfixpilot_wp_update_post_results'][$postId] ?? null;
    if ($result instanceof WP_Error || $result === 0) {
        return $result;
    }

    $post = get_post($postId);
    if (!$post instanceof WP_Post) {
        return new WP_Error('missing_post', 'Post missing.');
    }

    foreach (['post_status', 'post_title', 'post_name', 'post_content', 'post_excerpt'] as $field) {
        if (array_key_exists($field, $postData)) {
            $post->{$field} = (string) $postData[$field];
        }
    }

    return $postId;
}

function get_edit_post_link(int $postId, string $context): string
{
    return 'https://example.test/wp-admin/post.php?post=' . $postId;
}

function get_option(string $key, mixed $default = false): mixed
{
    return $key === 'wp_fixpilot_secret' ? 'test-secret' : $default;
}

function get_transient(string $key): mixed
{
    return false;
}

function set_transient(string $key, mixed $value, int $expiration): void
{
}

function register_rest_route(string $namespace, string $route, array $args): void
{
}

function get_field_objects(int $postId): array|false
{
    return $GLOBALS['wpfixpilot_acf_fields'][$postId] ?? false;
}

function get_field(string $selector, int $postId, bool $formatValue = true): mixed
{
    $GLOBALS['wpfixpilot_get_field_calls'][] = [$postId, $selector, $formatValue];
    return $GLOBALS['wpfixpilot_acf_runtime'][$postId][$selector] ?? null;
}

function update_field(string $selector, mixed $value, int $postId): bool
{
    $GLOBALS['wpfixpilot_update_field_calls'][] = [$postId, $selector, $value];
    if (($GLOBALS['wpfixpilot_update_field_failures'][$postId][$selector] ?? false) === true) {
        return false;
    }

    if (isset($GLOBALS['wpfixpilot_update_field_normalizers'][$postId][$selector])) {
        $value = $GLOBALS['wpfixpilot_update_field_normalizers'][$postId][$selector]($value);
    }
    $GLOBALS['wpfixpilot_acf_runtime'][$postId][$selector] = $value;
    if (isset($GLOBALS['wpfixpilot_acf_aliases'][$postId][$selector])) {
        $alias = $GLOBALS['wpfixpilot_acf_aliases'][$postId][$selector];
        $GLOBALS['wpfixpilot_acf_runtime'][$postId][$alias] = $value;
    }

    if (($GLOBALS['wpfixpilot_update_field_false_after_write'][$postId][$selector] ?? false) === true) {
        return false;
    }

    return true;
}

function parse_blocks(string $content): array
{
    $decoded = json_decode($content, true);
    if (is_array($decoded)) {
        return $decoded;
    }

    if ($content !== '') {
        return [[
            'blockName' => null,
            'attrs' => [],
            'innerBlocks' => [],
            'innerHTML' => $content,
            'innerContent' => [$content],
        ]];
    }

    return [];
}

function serialize_blocks(array $blocks): string
{
    return (string) json_encode($blocks);
}

/** @param array<string, mixed> $post */
function seed_post(int $postId, array $post): void
{
    $instance = new WP_Post();
    $instance->ID = $postId;
    $instance->post_type = (string) ($post['post_type'] ?? 'page');
    $instance->post_status = (string) ($post['post_status'] ?? 'draft');
    $instance->post_title = (string) ($post['post_title'] ?? 'Fixture ' . $postId);
    $instance->post_name = (string) ($post['post_name'] ?? 'fixture-' . $postId);
    $instance->post_content = (string) ($post['post_content'] ?? '');
    $instance->post_excerpt = (string) ($post['post_excerpt'] ?? '');
    $instance->post_parent = (int) ($post['post_parent'] ?? 0);
    $instance->menu_order = (int) ($post['menu_order'] ?? 0);
    $GLOBALS['wpfixpilot_posts'][$postId] = $instance;
}

/** @param array<string, mixed> $meta */
function seed_meta(int $postId, array $meta): void
{
    foreach ($meta as $key => $value) {
        $GLOBALS['wpfixpilot_meta'][$postId][(string) $key] = [$value];
    }
}

/**
 * @param array<int, array<string, mixed>> $fields
 */
function seed_acf_fixture(int $postId, array $fields, array $meta = []): void
{
    $GLOBALS['wpfixpilot_acf_fields'][$postId] = $fields;
    foreach ($fields as $field) {
        if (!is_array($field)) {
            continue;
        }
        $key = (string) ($field['key'] ?? '');
        $name = (string) ($field['name'] ?? '');
        if ($key === '' || $name === '') {
            continue;
        }
        $value = $field['value'] ?? null;
        $GLOBALS['wpfixpilot_acf_runtime'][$postId][$key] = $value;
        $GLOBALS['wpfixpilot_acf_runtime'][$postId][$name] = $value;
        $GLOBALS['wpfixpilot_acf_aliases'][$postId][$key] = $name;
    }

    seed_meta($postId, $meta);
}

seed_post(101, [
    'post_title' => 'ACF Fixture',
]);

$acfFlexibleValue = [
    [
        'acf_fc_layout' => 'hero',
        'heading' => 'Original hero heading',
        'copy' => '<p>Original hero copy</p>',
        'cta' => [
            'label' => 'Plan nu',
            'url' => '',
            'style' => 'primary',
        ],
        'points' => [
            [
                'text' => 'Snelle diagnose',
                'icon' => 501,
            ],
            [
                'text' => 'Heldere offerte',
                'icon' => 502,
            ],
        ],
    ],
    [
        'acf_fc_layout' => 'faq',
        'question' => 'Wat kost het?',
        'answer' => '<p>Bel voor een prijsindicatie</p>',
    ],
];

$acfLayouts = [
    [
        'name' => 'hero',
        'label' => 'Hero',
        'sub_fields' => [
            [
                'key' => 'field_hero_heading',
                'name' => 'heading',
                'label' => 'Heading',
                'type' => 'text',
                'required' => 1,
            ],
            [
                'key' => 'field_hero_copy',
                'name' => 'copy',
                'label' => 'Copy',
                'type' => 'wysiwyg',
            ],
            [
                'key' => 'field_hero_cta',
                'name' => 'cta',
                'label' => 'CTA',
                'type' => 'group',
                'sub_fields' => [
                    [
                        'key' => 'field_hero_cta_label',
                        'name' => 'label',
                        'label' => 'Label',
                        'type' => 'text',
                    ],
                    [
                        'key' => 'field_hero_cta_url',
                        'name' => 'url',
                        'label' => 'URL',
                        'type' => 'url',
                    ],
                    [
                        'key' => 'field_hero_cta_style',
                        'name' => 'style',
                        'label' => 'Style',
                        'type' => 'select',
                    ],
                ],
            ],
            [
                'key' => 'field_hero_points',
                'name' => 'points',
                'label' => 'Points',
                'type' => 'repeater',
                'sub_fields' => [
                    [
                        'key' => 'field_point_text',
                        'name' => 'text',
                        'label' => 'Point text',
                        'type' => 'text',
                    ],
                    [
                        'key' => 'field_point_icon',
                        'name' => 'icon',
                        'label' => 'Point icon',
                        'type' => 'image',
                    ],
                ],
            ],
        ],
    ],
    [
        'name' => 'faq',
        'label' => 'FAQ',
        'sub_fields' => [
            [
                'key' => 'field_faq_question',
                'name' => 'question',
                'label' => 'Question',
                'type' => 'text',
            ],
            [
                'key' => 'field_faq_answer',
                'name' => 'answer',
                'label' => 'Answer',
                'type' => 'wysiwyg',
            ],
        ],
    ],
];

$acfFields = [
    [
        'key' => 'field_page_sections',
        'name' => 'page_sections',
        'label' => 'Page sections',
        'type' => 'flexible_content',
        'layouts' => $acfLayouts,
        'value' => $acfFlexibleValue,
    ],
    [
        'key' => 'field_contact_group',
        'name' => 'contact_group',
        'label' => 'Contact group',
        'type' => 'group',
        'sub_fields' => [
            [
                'key' => 'field_contact_title',
                'name' => 'title',
                'label' => 'Title',
                'type' => 'text',
            ],
            [
                'key' => 'field_contact_url',
                'name' => 'url',
                'label' => 'URL',
                'type' => 'url',
            ],
            [
                'key' => 'field_contact_visible',
                'name' => 'visible',
                'label' => 'Visible',
                'type' => 'true_false',
            ],
        ],
        'value' => [
            'title' => 'Neem contact op',
            'url' => 'https://example.test/contact',
            'visible' => true,
        ],
    ],
];

seed_acf_fixture(101, $acfFields, [
    'page_sections' => 2,
    '_page_sections' => 'field_page_sections',
    'page_sections_0_heading' => 'Original hero heading',
    '_page_sections_0_heading' => 'field_hero_heading',
    'page_sections_0_copy' => '<p>Original hero copy</p>',
    '_page_sections_0_copy' => 'field_hero_copy',
    'page_sections_0_cta_label' => 'Plan nu',
    '_page_sections_0_cta_label' => 'field_hero_cta_label',
    'page_sections_0_cta_url' => '',
    '_page_sections_0_cta_url' => 'field_hero_cta_url',
    'page_sections_0_cta_style' => 'primary',
    '_page_sections_0_cta_style' => 'field_hero_cta_style',
    'page_sections_0_points' => 2,
    '_page_sections_0_points' => 'field_hero_points',
    'page_sections_0_points_0_text' => 'Snelle diagnose',
    '_page_sections_0_points_0_text' => 'field_point_text',
    'page_sections_0_points_0_icon' => 501,
    '_page_sections_0_points_0_icon' => 'field_point_icon',
    'page_sections_0_points_1_text' => 'Heldere offerte',
    '_page_sections_0_points_1_text' => 'field_point_text',
    'page_sections_0_points_1_icon' => 502,
    '_page_sections_0_points_1_icon' => 'field_point_icon',
    'page_sections_1_question' => 'Wat kost het?',
    '_page_sections_1_question' => 'field_faq_question',
    'page_sections_1_answer' => '<p>Bel voor een prijsindicatie</p>',
    '_page_sections_1_answer' => 'field_faq_answer',
    'contact_group_title' => 'Neem contact op',
    '_contact_group_title' => 'field_contact_title',
    'contact_group_url' => 'https://example.test/contact',
    '_contact_group_url' => 'field_contact_url',
    'contact_group_visible' => true,
    '_contact_group_visible' => 'field_contact_visible',
    'unrelated_meta_key' => 'leave me out',
]);

$acfTextOnlyFields = $acfFields;
$acfTextOnlyFields[0]['value'][0]['heading'] = 'Changed heading only';
$acfTextOnlyFields[0]['value'][0]['copy'] = '<p>Changed text only</p>';
$acfTextOnlyFields[1]['value']['title'] = 'Changed contact title';
seed_post(106, ['post_title' => 'ACF Text Change Fixture']);
seed_acf_fixture(106, $acfTextOnlyFields);

$acfReorderedFields = $acfFields;
$acfReorderedFields[0]['value'] = [
    $acfFlexibleValue[1],
    $acfFlexibleValue[0],
];
seed_post(107, ['post_title' => 'ACF Reordered Fixture']);
seed_acf_fixture(107, $acfReorderedFields);

$acfValueOnlyFields = [[
    'key' => 'field_page_sections',
    'name' => 'page_sections',
    'label' => 'Page sections',
    'type' => 'flexible_content',
    'value' => [[
        'acf_fc_layout' => 'hero',
        'label' => 'Origineel label',
    ]],
]];
seed_post(109, ['post_title' => 'ACF Value Only Fixture']);
seed_acf_fixture(109, $acfValueOnlyFields, [
    'page_sections' => 1,
    '_page_sections' => 'field_page_sections',
    'page_sections_0_label' => 'Origineel label',
    '_page_sections_0_label' => 'field_value_only_label',
]);
seed_post(110, ['post_title' => 'ACF Value Only No Reference Fixture']);
seed_acf_fixture(110, $acfValueOnlyFields, [
    'page_sections' => 1,
    '_page_sections' => 'field_page_sections',
    'page_sections_0_label' => 'Origineel label zonder referentie',
]);

$acfInsertedFields = $acfFields;
$acfInsertedFields[0]['value'][] = [
    'acf_fc_layout' => 'hero',
    'heading' => 'Extra row',
    'copy' => '<p>Another row</p>',
    'cta' => [
        'label' => 'Meer weten',
        'url' => 'https://example.test/meer',
        'style' => 'secondary',
    ],
    'points' => [],
];
seed_post(108, ['post_title' => 'ACF Inserted Fixture']);
seed_acf_fixture(108, $acfInsertedFields);

seed_post(201, ['post_title' => 'Elementor Fixture']);
seed_meta(201, [
    '_elementor_data' => wp_json_encode([
        [
            'id' => 'section-1',
            'elType' => 'section',
            'settings' => [
                'background_background' => 'classic',
            ],
            'elements' => [
                [
                    'id' => 'widget-heading',
                    'elType' => 'widget',
                    'widgetType' => 'heading',
                    'settings' => [
                        'title' => 'Original hero heading',
                        'size' => 'xl',
                    ],
                    'elements' => [],
                ],
                [
                    'id' => 'widget-text',
                    'elType' => 'widget',
                    'widgetType' => 'text-editor',
                    'settings' => [
                        'editor' => '<p>Original intro copy</p>',
                        'text_color' => '#ffffff',
                    ],
                    'elements' => [],
                ],
                [
                    'id' => 'widget-button',
                    'elType' => 'widget',
                    'widgetType' => 'button',
                    'settings' => [
                        'text' => 'Neem contact op',
                        'link' => [
                            'url' => 'https://example.test/contact',
                            'is_external' => '',
                        ],
                        'background_color' => '#101010',
                        'image' => [
                            'id' => 901,
                            'url' => 'https://example.test/media.jpg',
                        ],
                    ],
                    'elements' => [],
                ],
            ],
        ],
    ]),
    '_elementor_edit_mode' => 'builder',
    '_elementor_version' => '3.20.0',
]);

seed_post(202, ['post_title' => 'Broken Elementor Fixture']);
seed_meta(202, [
    '_elementor_data' => '{broken-json',
    '_elementor_edit_mode' => 'builder',
]);

seed_post(203, [
    'post_title' => 'WPBakery Fixture',
    'post_content' => '[vc_row][vc_column][vc_empty_space height="20px"][vc_separator color="grey" /][vc_custom_heading text="Original hero heading"][/vc_custom_heading][vc_column_text]<p>Original intro copy</p>[/vc_column_text][vc_raw_html]<div class="raw-block">Original raw HTML</div>[/vc_raw_html][vc_btn title="Plan nu" link="title:Contact|url:https://example.test/contact|target:_self"][/vc_btn][/vc_column][/vc_row]',
]);
seed_meta(203, [
    '_wpb_shortcodes_custom_css' => '.hero{color:red;}',
]);

seed_post(204, [
    'post_title' => 'Broken WPBakery Fixture',
    'post_content' => '[vc_row][vc_column][vc_custom_heading text="Broken"',
]);

seed_post(205, ['post_title' => 'Bricks Fixture']);
seed_meta(205, [
    '_bricks_page_content_2' => [
        [
            'id' => 'hero-heading',
            'name' => 'heading',
            'parent' => 0,
            'settings' => [
                'text' => 'Original hero heading',
                'tag' => 'h1',
            ],
        ],
        [
            'id' => 'hero-copy',
            'name' => 'text-basic',
            'parent' => 0,
            'settings' => [
                'text' => '<p>Original intro copy</p>',
                'typography' => [
                    'fontSize' => 18,
                ],
            ],
        ],
        [
            'id' => 'hero-button',
            'name' => 'button',
            'parent' => 0,
            'settings' => [
                'text' => 'Plan nu',
                'link' => [
                    'url' => 'https://example.test/contact',
                ],
                'style' => [
                    'background' => '#101010',
                ],
                'image' => 700,
            ],
        ],
    ],
    '_bricks_page_settings' => [
        'template' => 'service',
    ],
]);

seed_post(206, ['post_title' => 'Broken Bricks Fixture']);
seed_meta(206, [
    '_bricks_page_content_2' => 'not-an-array',
]);

$gutenbergBlocks = [
    [
        'blockName' => 'core/group',
        'attrs' => [
            'layout' => ['type' => 'constrained'],
        ],
        'innerBlocks' => [
            [
                'blockName' => 'core/heading',
                'attrs' => [
                    'content' => 'Original hero heading',
                    'level' => 1,
                ],
                'innerBlocks' => [],
                'innerHTML' => '<h1 class="wp-block-heading alignwide">Original hero heading</h1>',
                'innerContent' => ['<h1 class="wp-block-heading alignwide">Original hero heading</h1>'],
            ],
            [
                'blockName' => 'core/paragraph',
                'attrs' => [],
                'innerBlocks' => [],
                'innerHTML' => '<p>Original intro copy</p>',
                'innerContent' => ['<p>Original intro copy</p>'],
            ],
            [
                'blockName' => 'core/button',
                'attrs' => [
                    'text' => 'Plan nu',
                    'url' => 'https://example.test/contact',
                    'backgroundColor' => 'black',
                ],
                'innerBlocks' => [],
                'innerHTML' => '<div class="wp-block-button is-style-fill"><a class="wp-block-button__link has-black-background-color" href="https://example.test/contact">Plan nu</a></div>',
                'innerContent' => ['<div class="wp-block-button is-style-fill"><a class="wp-block-button__link has-black-background-color" href="https://example.test/contact">Plan nu</a></div>'],
            ],
        ],
        'innerHTML' => '',
        'innerContent' => [],
    ],
    [
        'blockName' => 'core/image',
        'attrs' => [
            'id' => 501,
            'url' => 'https://example.test/image.jpg',
        ],
        'innerBlocks' => [],
        'innerHTML' => '',
        'innerContent' => [],
    ],
];

seed_post(207, [
    'post_title' => 'Gutenberg Fixture',
    'post_content' => serialize_blocks($gutenbergBlocks),
]);

seed_post(208, [
    'post_title' => 'Broken Gutenberg Fixture',
    'post_content' => '',
]);

seed_post(209, [
    'post_type' => 'post',
    'post_title' => 'Classic Editor Blog Fixture',
    'post_content' => '<h2>Vakantiecheck</h2><p>Controleer uw auto voor vertrek.</p>',
]);

require_once __DIR__ . '/../includes/builder-adapters/interface-builder-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/interface-blueprint-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-gutenberg-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-elementor-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-bricks-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-wpbakery-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-acf-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-acf-blueprint-adapter.php';
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

$adapters = [
    'acf' => new WPFixPilot_ACF_Adapter(),
    'elementor' => new WPFixPilot_Elementor_Adapter(),
    'wpbakery' => new WPFixPilot_WPBakery_Adapter(),
    'bricks' => new WPFixPilot_Bricks_Adapter(),
    'gutenberg' => new WPFixPilot_Gutenberg_Adapter(),
];

assert(
    $adapters['gutenberg']->uses_page(203) === false,
    'WPBakery shortcode content is not a Gutenberg page'
);

assert(
    $adapters['gutenberg']->uses_page(209) === true,
    'classic editor HTML is handled as Gutenberg freeform content'
);
$classicSchema = $adapters['gutenberg']->schema(209);
assert(!is_wp_error($classicSchema), 'classic editor schema should succeed');
assert(count($classicSchema['blocks']) === 1, 'classic editor has one freeform block');
assert(
    $classicSchema['blocks'][0]['layout'] === 'core/freeform',
    'classic editor uses the freeform layout'
);
assert(
    $classicSchema['blocks'][0]['fields'][0]['value_type'] === 'rich_text',
    'classic editor HTML remains rich text'
);
$classicFieldId = $classicSchema['blocks'][0]['fields'][0]['id'];
assert(
    $adapters['gutenberg']->apply_replacements(
        209,
        $classicSchema,
        [$classicFieldId => '<h2>Nieuwe vakantiecheck</h2><p>Plan onderhoud.</p>']
    ) === true,
    'classic editor replacement succeeds'
);
$classicBlocks = parse_blocks((string) get_post(209)?->post_content);
assert(
    $classicBlocks[0]['innerHTML']
    === '<h2>Nieuwe vakantiecheck</h2><p>Plan onderhoud.</p>',
    'classic editor replacement preserves the approved HTML'
);

$fixtures = [
    'acf' => [
        'post_id' => 101,
        'block_count' => 3,
        'read_first_text' => static fn (): string =>
            (string) get_field('field_page_sections', 101)[0]['heading'],
        'read_structure' => static fn () => $adapters['acf']->structure_hash(101),
    ],
    'elementor' => [
        'post_id' => 201,
        'block_count' => 3,
        'read_first_text' => static function (): string {
            $document = json_decode((string) get_post_meta(201, '_elementor_data', true), true);

            return (string) $document[0]['elements'][0]['settings']['title'];
        },
        'read_structure' => static fn () => $adapters['elementor']->structure_hash(201),
    ],
    'wpbakery' => [
        'post_id' => 203,
        'block_count' => 4,
        'read_first_text' => static fn (): string =>
            (preg_match('/text="([^"]+)"/', (string) get_post(203)?->post_content, $match) === 1)
                ? (string) $match[1]
                : '',
        'read_structure' => static fn () => $adapters['wpbakery']->structure_hash(203),
    ],
    'bricks' => [
        'post_id' => 205,
        'block_count' => 3,
        'read_first_text' => static fn (): string =>
            (string) get_post_meta(205, '_bricks_page_content_2', true)[0]['settings']['text'],
        'read_structure' => static fn () => $adapters['bricks']->structure_hash(205),
    ],
    'gutenberg' => [
        'post_id' => 207,
        'block_count' => 3,
        'read_first_text' => static function (): string {
            $blocks = parse_blocks((string) get_post(207)?->post_content);

            return (string) $blocks[0]['innerBlocks'][0]['attrs']['content'];
        },
        'read_structure' => static fn () => $adapters['gutenberg']->structure_hash(207),
    ],
];

foreach ($fixtures as $builder => &$fixture) {
    $fixture['expected_structure'] = $adapters[$builder]->structure_hash($fixture['post_id']);
}
unset($fixture);

echo "Running blueprint adapter contract tests...\n";

foreach ($fixtures as $builder => $fixture) {
    $adapter = $adapters[$builder];
    assert($adapter->uses_page($fixture['post_id']) === true, $builder . ' uses_page');
    $schema = $adapter->schema($fixture['post_id']);
    assert(!is_wp_error($schema), $builder . ' schema should succeed');
    assert($schema['schema_version'] === 'blueprint-v1', $builder . ' schema version');
    assert(count($schema['blocks']) === $fixture['block_count'], $builder . ' block count');
    assert($schema['blocks'][0]['fields'][0]['id'] !== '', $builder . ' field id');

    $fieldIds = [];
    foreach ($schema['blocks'] as $block) {
        foreach ($block['fields'] as $field) {
            $fieldIds[] = $field['id'];
        }
    }
    assert(count($fieldIds) === count(array_unique($fieldIds)), $builder . ' duplicate field ids');

    assert($adapter->apply_replacements(
        $fixture['post_id'],
        $schema,
        [$schema['blocks'][0]['fields'][0]['id'] => 'Nieuwe tekst']
    ) === true, $builder . ' apply_replacements');

    assert($fixture['read_first_text']() === 'Nieuwe tekst', $builder . ' replacement readback');
    assert(
        $fixture['read_structure']() === $fixture['expected_structure'],
        $builder . ' structure preserved'
    );

    $unknownReplacement = $adapter->apply_replacements(
        $fixture['post_id'],
        $schema,
        ['unknown-field-id' => 'Geen idee']
    );
    assert(is_wp_error($unknownReplacement), $builder . ' should reject unknown ids');
}

$acfSchema = $adapters['acf']->schema(101);
assert(!is_wp_error($acfSchema), 'acf schema regression');

$acfEmptyUrlField = null;
$acfHeroHeadingField = null;
$acfHeroCopyField = null;
foreach ($acfSchema['blocks'] as $block) {
    foreach ($block['fields'] as $field) {
        if ($field['path'] === 'acf:field_page_sections/page_sections/0/cta/url') {
            $acfEmptyUrlField = $field;
        }
        if ($field['path'] === 'acf:field_page_sections/page_sections/0/heading') {
            $acfHeroHeadingField = $field;
        }
        if ($field['path'] === 'acf:field_page_sections/page_sections/0/copy') {
            $acfHeroCopyField = $field;
        }
    }
}
assert(is_array($acfEmptyUrlField), 'acf empty editable url should exist');
assert($acfEmptyUrlField['current_value'] === '', 'acf empty editable url current value');
assert(is_array($acfHeroHeadingField), 'acf heading field found');
assert(is_array($acfHeroCopyField), 'acf copy field found');

$GLOBALS['wpfixpilot_update_field_calls'] = [];
$acfMultiResult = $adapters['acf']->apply_replacements(
    101,
    $acfSchema,
    [
        $acfHeroHeadingField['id'] => 'Nieuwe hero heading',
        $acfHeroCopyField['id'] => '<p>Nieuwe hero copy</p>',
        $acfEmptyUrlField['id'] => 'https://example.test/cta',
    ]
);
assert($acfMultiResult === true, 'acf multiple same-tree replacements');
assert(
    in_array([101, 'field_page_sections', false], $GLOBALS['wpfixpilot_get_field_calls'], true),
    'acf replacement reads raw field values'
);
assert(get_field('field_page_sections', 101)[0]['heading'] === 'Nieuwe hero heading', 'acf heading write');
assert(get_field('field_page_sections', 101)[0]['copy'] === '<p>Nieuwe hero copy</p>', 'acf copy write');
assert(get_field('field_page_sections', 101)[0]['cta']['url'] === 'https://example.test/cta', 'acf url write');
assert(count($GLOBALS['wpfixpilot_update_field_calls']) === 1, 'acf updates one top-level field once');
assert($GLOBALS['wpfixpilot_update_field_calls'][0][1] === 'field_page_sections', 'acf update selector');

$acfCloneKeys = $adapters['acf']->clone_meta_keys(101);
sort($acfCloneKeys);
$expectedAcfCloneKeys = [
    '_contact_group',
    '_contact_group_title',
    '_contact_group_url',
    '_contact_group_visible',
    '_page_sections',
    '_page_sections_0_copy',
    '_page_sections_0_cta_label',
    '_page_sections_0_cta_style',
    '_page_sections_0_cta_url',
    '_page_sections_0_heading',
    '_page_sections_0_points',
    '_page_sections_0_points_0_icon',
    '_page_sections_0_points_0_text',
    '_page_sections_0_points_1_icon',
    '_page_sections_0_points_1_text',
    '_page_sections_1_answer',
    '_page_sections_1_question',
    'contact_group',
    'contact_group_title',
    'contact_group_url',
    'contact_group_visible',
    'page_sections',
    'page_sections_0_copy',
    'page_sections_0_cta_label',
    'page_sections_0_cta_style',
    'page_sections_0_cta_url',
    'page_sections_0_heading',
    'page_sections_0_points',
    'page_sections_0_points_0_icon',
    'page_sections_0_points_0_text',
    'page_sections_0_points_1_icon',
    'page_sections_0_points_1_text',
    'page_sections_1_answer',
    'page_sections_1_question',
];
sort($expectedAcfCloneKeys);
assert($acfCloneKeys === $expectedAcfCloneKeys, 'acf clone_meta_keys should discover complete tree');

assert(
    $adapters['acf']->structure_hash(101) === $adapters['acf']->structure_hash(106),
    'acf text-only hash stability'
);
assert(
    $adapters['acf']->structure_hash(101) !== $adapters['acf']->structure_hash(107),
    'acf row reorder should change hash'
);
assert(
    $adapters['acf']->structure_hash(101) !== $adapters['acf']->structure_hash(108),
    'acf row insert should change hash'
);

$wpbakeryPostContent = (string) get_post(203)?->post_content;
assert(
    str_contains($wpbakeryPostContent, '[vc_empty_space height="20px"]'),
    'wpbakery standalone shortcode without slash should be preserved'
);
assert(
    str_contains($wpbakeryPostContent, '[vc_separator color="grey" /]'),
    'wpbakery slash self-closing shortcode should be preserved'
);
assert(
    str_contains(
        $wpbakeryPostContent,
        'link="title:Contact|url:https://example.test/contact|target:_self"'
    ),
    'wpbakery link attribute segments should remain intact'
);

$wpbakeryButtonUrlField = null;
foreach ($adapters['wpbakery']->schema(203)['blocks'] as $block) {
    foreach ($block['fields'] as $field) {
        if (($field['value_type'] ?? null) === 'url') {
            $wpbakeryButtonUrlField = $field;
        }
    }
}
assert(is_array($wpbakeryButtonUrlField), 'wpbakery url field found');
$wpbakeryUrlResult = $adapters['wpbakery']->apply_replacements(
    203,
    $adapters['wpbakery']->schema(203),
    [$wpbakeryButtonUrlField['id'] => 'https://example.test/nieuwe-url']
);
assert($wpbakeryUrlResult === true, 'wpbakery url replacement succeeds');
assert(
    str_contains(
        (string) get_post(203)?->post_content,
        'link="title:Contact|url:https://example.test/nieuwe-url|target:_self"'
    ),
    'wpbakery url replacement should preserve neighboring link metadata'
);

$gutenbergBlocksAfterHeading = parse_blocks((string) get_post(207)?->post_content);
assert(
    $gutenbergBlocksAfterHeading[0]['innerBlocks'][0]['innerHTML']
    === '<h1 class="wp-block-heading alignwide">Nieuwe tekst</h1>',
    'gutenberg heading wrapper should be preserved'
);

$gutenbergSchemaForUrl = $adapters['gutenberg']->schema(207);
$gutenbergButtonUrlField = null;
foreach ($gutenbergSchemaForUrl['blocks'] as $block) {
    foreach ($block['fields'] as $field) {
        if (($field['path'] ?? '') === 'block:0.2:attr:url') {
            $gutenbergButtonUrlField = $field;
        }
    }
}
assert(is_array($gutenbergButtonUrlField), 'gutenberg button url field found');
$gutenbergUrlResult = $adapters['gutenberg']->apply_replacements(
    207,
    $gutenbergSchemaForUrl,
    [$gutenbergButtonUrlField['id'] => 'https://example.test/nieuwe-url']
);
assert($gutenbergUrlResult === true, 'gutenberg url replacement succeeds');
$gutenbergBlocksAfterUrl = parse_blocks((string) get_post(207)?->post_content);
assert(
    $gutenbergBlocksAfterUrl[0]['innerBlocks'][2]['innerHTML']
    === '<div class="wp-block-button is-style-fill"><a class="wp-block-button__link has-black-background-color" href="https://example.test/nieuwe-url">Plan nu</a></div>',
    'gutenberg button wrapper should be preserved'
);

$acfFailureSchema = $adapters['acf']->schema(101);
assert(!is_wp_error($acfFailureSchema), 'acf failure schema');
$GLOBALS['wpfixpilot_update_field_false_after_write'][101]['field_page_sections'] = true;
$acfPersistedFalseResult = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [$acfHeroHeadingField['id'] => 'Wel opgeslagen ondanks false']
);
assert($acfPersistedFalseResult === true, 'acf persisted false result succeeds');
unset($GLOBALS['wpfixpilot_update_field_false_after_write'][101]['field_page_sections']);
$GLOBALS['wpfixpilot_update_field_normalizers'][101]['field_page_sections'] = static function (mixed $value): mixed {
    assert(is_array($value));
    $value[1]['acf_normalized_default'] = 'added by acf';
    return $value;
};
$GLOBALS['wpfixpilot_update_field_normalizers'][101]['page_sections'] =
    $GLOBALS['wpfixpilot_update_field_normalizers'][101]['field_page_sections'];
$acfNormalizedPersistedResult = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [$acfHeroHeadingField['id'] => 'Opgeslagen met ACF-normalisatie']
);
assert($acfNormalizedPersistedResult === true, 'acf normalized full field write succeeds');
assert(
    get_field('field_page_sections', 101)[0]['heading'] === 'Opgeslagen met ACF-normalisatie',
    'acf normalized write persisted target path'
);
unset($GLOBALS['wpfixpilot_update_field_normalizers'][101]['field_page_sections']);
unset($GLOBALS['wpfixpilot_update_field_normalizers'][101]['page_sections']);
$GLOBALS['wpfixpilot_update_field_failures'][101]['field_page_sections'] = true;
$GLOBALS['wpfixpilot_update_field_failures'][101]['page_sections'] = true;
$acfNameFallbackResult = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [$acfHeroHeadingField['id'] => 'Opgeslagen via leaf meta']
);
assert($acfNameFallbackResult === true, 'acf leaf meta fallback succeeds');
assert(
    get_post_meta(101, 'page_sections_0_heading', true) === 'Opgeslagen via leaf meta',
    'acf leaf meta fallback writes value meta'
);
assert(
    get_post_meta(101, '_page_sections_0_heading', true) === 'field_hero_heading',
    'acf leaf meta fallback writes reference meta'
);
$acfNoChangeResult = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [
        $acfHeroHeadingField['id'] => 'Opgeslagen via leaf meta',
        $acfHeroCopyField['id'] => '<p>Opgeslagen naast ongewijzigd veld</p>',
    ]
);
assert($acfNoChangeResult === true, 'acf leaf meta fallback accepts unchanged meta writes');
assert(
    get_post_meta(101, 'page_sections_0_copy', true) === '<p>Opgeslagen naast ongewijzigd veld</p>',
    'acf leaf meta fallback continues after unchanged meta write'
);
$acfWriteFailure = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [$acfHeroHeadingField['id'] => 'Echte schrijffout']
);
assert($acfWriteFailure === true, 'acf leaf meta fallback covers top-level write failure');
$GLOBALS['wpfixpilot_update_post_meta_failures'][101]['page_sections_0_heading'] = true;
$acfWriteFailure = $adapters['acf']->apply_replacements(
    101,
    $acfFailureSchema,
    [$acfHeroHeadingField['id'] => 'Schrijffout']
);
assert(is_wp_error($acfWriteFailure), 'acf write failure error');
assert(
    str_contains($acfWriteFailure->message, 'field_page_sections'),
    'acf write failure includes selector diagnostic'
);
unset($GLOBALS['wpfixpilot_update_field_failures'][101]['field_page_sections']);
unset($GLOBALS['wpfixpilot_update_field_failures'][101]['page_sections']);
unset($GLOBALS['wpfixpilot_update_post_meta_failures'][101]['page_sections_0_heading']);

$acfValueOnlySchema = $adapters['acf']->schema(109);
assert(!is_wp_error($acfValueOnlySchema), 'acf value-only schema');
$acfValueOnlyLabelField = null;
foreach ($acfValueOnlySchema['blocks'] as $block) {
    foreach ($block['fields'] as $field) {
        if ($field['path'] === 'acf:field_page_sections/page_sections/0/label') {
            $acfValueOnlyLabelField = $field;
        }
    }
}
assert(is_array($acfValueOnlyLabelField), 'acf value-only label field exists');
$GLOBALS['wpfixpilot_update_field_failures'][109]['field_page_sections'] = true;
$GLOBALS['wpfixpilot_update_field_failures'][109]['page_sections'] = true;
$acfValueOnlyFallback = $adapters['acf']->apply_replacements(
    109,
    $acfValueOnlySchema,
    [$acfValueOnlyLabelField['id'] => 'Nieuw value-only label']
);
assert($acfValueOnlyFallback === true, 'acf value-only leaf meta fallback succeeds');
assert(
    get_post_meta(109, 'page_sections_0_label', true) === 'Nieuw value-only label',
    'acf value-only fallback writes value meta'
);
assert(
    get_post_meta(109, '_page_sections_0_label', true) === 'field_value_only_label',
    'acf value-only fallback preserves reference meta'
);
unset($GLOBALS['wpfixpilot_update_field_failures'][109]['field_page_sections']);
unset($GLOBALS['wpfixpilot_update_field_failures'][109]['page_sections']);

$acfValueOnlyNoReferenceSchema = $adapters['acf']->schema(110);
assert(!is_wp_error($acfValueOnlyNoReferenceSchema), 'acf value-only no-reference schema');
$acfValueOnlyNoReferenceLabelField = null;
foreach ($acfValueOnlyNoReferenceSchema['blocks'] as $block) {
    foreach ($block['fields'] as $field) {
        if ($field['path'] === 'acf:field_page_sections/page_sections/0/label') {
            $acfValueOnlyNoReferenceLabelField = $field;
        }
    }
}
assert(is_array($acfValueOnlyNoReferenceLabelField), 'acf value-only no-reference label field exists');
$GLOBALS['wpfixpilot_update_field_failures'][110]['field_page_sections'] = true;
$GLOBALS['wpfixpilot_update_field_failures'][110]['page_sections'] = true;
$acfValueOnlyNoReferenceFallback = $adapters['acf']->apply_replacements(
    110,
    $acfValueOnlyNoReferenceSchema,
    [$acfValueOnlyNoReferenceLabelField['id'] => 'Nieuw label zonder referentie']
);
assert($acfValueOnlyNoReferenceFallback === true, 'acf value-only fallback without reference succeeds');
assert(
    get_post_meta(110, 'page_sections_0_label', true) === 'Nieuw label zonder referentie',
    'acf value-only fallback without reference writes value meta'
);
assert(
    get_post_meta(110, '_page_sections_0_label', true) === '',
    'acf value-only fallback without reference leaves missing reference empty'
);
unset($GLOBALS['wpfixpilot_update_field_failures'][110]['field_page_sections']);
unset($GLOBALS['wpfixpilot_update_field_failures'][110]['page_sections']);

$elementorBroken = $adapters['elementor']->schema(202);
assert(is_wp_error($elementorBroken), 'elementor malformed data should error');

$elementorSchema = $adapters['elementor']->schema(201);
assert(!is_wp_error($elementorSchema), 'elementor schema');
$elementorFirstFieldId = $elementorSchema['blocks'][0]['fields'][0]['id'];
$GLOBALS['wpfixpilot_update_post_meta_failures'][201]['_elementor_data'] = true;
$elementorWriteFailure = $adapters['elementor']->apply_replacements(
    201,
    $elementorSchema,
    [$elementorFirstFieldId => 'Niet opslaan']
);
assert(is_wp_error($elementorWriteFailure), 'elementor write failure');
unset($GLOBALS['wpfixpilot_update_post_meta_failures'][201]['_elementor_data']);

$wpbakeryBroken = $adapters['wpbakery']->schema(204);
assert(is_wp_error($wpbakeryBroken), 'wpbakery malformed data should error');

$wpbakerySchema = $adapters['wpbakery']->schema(203);
assert(!is_wp_error($wpbakerySchema), 'wpbakery schema');
$wpbakeryFirstFieldId = $wpbakerySchema['blocks'][0]['fields'][0]['id'];
$GLOBALS['wpfixpilot_wp_update_post_results'][203] = new WP_Error('write_failed', 'failed');
$wpbakeryWriteFailure = $adapters['wpbakery']->apply_replacements(
    203,
    $wpbakerySchema,
    [$wpbakeryFirstFieldId => 'Niet opslaan']
);
assert(is_wp_error($wpbakeryWriteFailure), 'wpbakery write failure');
unset($GLOBALS['wpfixpilot_wp_update_post_results'][203]);

$bricksBroken = $adapters['bricks']->schema(206);
assert(is_wp_error($bricksBroken), 'bricks malformed data should error');

$bricksSchema = $adapters['bricks']->schema(205);
assert(!is_wp_error($bricksSchema), 'bricks schema');
$bricksFirstFieldId = $bricksSchema['blocks'][0]['fields'][0]['id'];
$GLOBALS['wpfixpilot_update_post_meta_failures'][205]['_bricks_page_content_2'] = true;
$bricksWriteFailure = $adapters['bricks']->apply_replacements(
    205,
    $bricksSchema,
    [$bricksFirstFieldId => 'Niet opslaan']
);
assert(is_wp_error($bricksWriteFailure), 'bricks write failure');
unset($GLOBALS['wpfixpilot_update_post_meta_failures'][205]['_bricks_page_content_2']);

$gutenbergBroken = $adapters['gutenberg']->schema(208);
assert(is_wp_error($gutenbergBroken), 'missing Gutenberg data should error');

$gutenbergSchema = $adapters['gutenberg']->schema(207);
assert(!is_wp_error($gutenbergSchema), 'gutenberg schema');
$gutenbergFirstFieldId = $gutenbergSchema['blocks'][0]['fields'][0]['id'];
$GLOBALS['wpfixpilot_wp_update_post_results'][207] = new WP_Error('write_failed', 'failed');
$gutenbergWriteFailure = $adapters['gutenberg']->apply_replacements(
    207,
    $gutenbergSchema,
    [$gutenbergFirstFieldId => 'Niet opslaan']
);
assert(is_wp_error($gutenbergWriteFailure), 'gutenberg write failure');
unset($GLOBALS['wpfixpilot_wp_update_post_results'][207]);

$restControllerReflection = new ReflectionClass(WPFixPilot_REST_Controller::class);
$restControllerInstance = $restControllerReflection->newInstanceWithoutConstructor();
$registeredAdapters = Closure::bind(
    fn (): array => $this->default_blueprint_adapters(),
    $restControllerInstance,
    WPFixPilot_REST_Controller::class
)();
$registeredKeys = array_map(
    static fn (WPFixPilot_Blueprint_Adapter $adapter): string => $adapter->key(),
    $registeredAdapters
);
sort($registeredKeys);
assert(
    $registeredKeys === ['acf', 'bricks', 'elementor', 'gutenberg', 'wpbakery'],
    'production blueprint adapters should all be registered'
);

echo "blueprint adapter tests passed\n";
