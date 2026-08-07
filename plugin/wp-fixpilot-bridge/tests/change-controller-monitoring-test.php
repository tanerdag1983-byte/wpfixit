<?php

declare(strict_types=1);

final class WP_Post
{
    public int $ID = 10;
    public string $post_title = 'Transmissie revisie';
    public string $post_name = 'transmissie-revisie';
    public string $post_content = '<h1>Transmissie revisie</h1>';
}

final class WP_Error {}

function get_post(int $postId): ?WP_Post { return $postId === 10 ? new WP_Post() : null; }
function get_post_thumbnail_id(int $postId): int { return $postId === 10 ? 42 : 0; }
function get_permalink(WP_Post $post): string { return 'https://example.test/transmissie-revisie'; }
/** @return mixed */
function get_post_meta(int $postId, string $key = '', bool $single = false): mixed
{
    if ($key === '_wp_attachment_image_alt') {
        return match ($postId) {
            42 => 'Revisie in uitvoering',
            99 => 'Elementor transmissie',
            321 => 'ACF werkplaats',
            654 => 'Bricks diagnose',
            default => '',
        };
    }
    if ($postId === 10) {
        return match ($key) {
            '_elementor_data' => '[{"widgetType":"image","settings":{"image":{"id":99,"url":"https://example.test/builder.jpg"}}}]',
            '_bricks_page_content_2' => [[
                'name' => 'image',
                'settings' => ['image' => ['id' => 654, 'url' => 'https://example.test/bricks.jpg']],
            ]],
            'hero_visual' => 321,
            '' => [
                '_elementor_data' => [''],
                '_bricks_page_content_2' => [''],
                'hero_visual' => [''],
            ],
            default => '',
        };
    }
    return '';
}
function wp_json_encode(mixed $value): string { return json_encode($value, JSON_THROW_ON_ERROR); }

final class Monitoring_Test_Adapter
{
    public function __construct(
        private string $adapterKey,
        private string $metaKey,
        private string $visibleContent,
        private array $analysisImages = [],
        private bool $schemaError = false
    ) {}
    public function key(): string { return $this->adapterKey; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool { return $postId === 10; }
    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array { return [$this->metaKey]; }
    public function structure_hash(int $postId): string { return 'stable-' . $this->adapterKey . '-hash'; }
    /** @return array<string, mixed> */
    public function schema(int $postId): array|WP_Error
    {
        if ($this->schemaError) {
            return new WP_Error();
        }
        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => [[
                'fields' => [[
                    'value_type' => 'html',
                    'current_value' => $this->visibleContent,
                ]],
            ]],
        ];
    }
    /** @return array<int, mixed> */
    public function analysis_images(int $postId): array { return $this->analysisImages; }
}

require_once __DIR__ . '/../includes/class-change-controller.php';

$controller = new WPFixPilot_Change_Controller([
    new Monitoring_Test_Adapter('elementor', '_elementor_data', '<h2>Visible heading</h2>'),
    new Monitoring_Test_Adapter('bricks', '_bricks_page_content_2', '<a href="/contact">Visible contact</a>'),
    new Monitoring_Test_Adapter('acf', 'hero_visual', '', [
        321,
        ['id' => 321, 'alt' => 'ACF maatwerk'],
    ], true),
]);
$state = $controller->current_state(10, 'yoast');
assert(is_array($state));
assert($state['values']['featured_image_id'] === 42);
assert($state['values']['featured_image_alt'] === 'Revisie in uitvoering');
assert($state['values']['builders']['elementor']['structure_hash'] === 'stable-elementor-hash');
assert(str_contains($state['values']['builders']['elementor']['meta']['_elementor_data'], 'builder.jpg'));
assert($state['values']['builders']['bricks']['meta']['_bricks_page_content_2'][0]['settings']['image']['id'] === 654);
assert($state['values']['builders']['acf']['meta']['hero_visual'] === 321);
assert($state['values']['visible_builder_content'] === [
    '<h2>Visible heading</h2>',
    '<a href="/contact">Visible contact</a>',
    '<img alt="Elementor transmissie">',
    '<img alt="Bricks diagnose">',
    '<img alt="ACF maatwerk">',
]);
assert($controller->current_state(10, 'yoast')['content_hash'] === $state['content_hash']);

echo "change controller monitoring tests passed\n";
