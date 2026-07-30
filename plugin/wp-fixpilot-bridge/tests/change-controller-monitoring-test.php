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
function get_post_meta(int $postId, string $key, bool $single): string
{
    return $postId === 42 && $key === '_wp_attachment_image_alt' ? 'Revisie in uitvoering' : '';
}
function wp_json_encode(mixed $value): string { return json_encode($value, JSON_THROW_ON_ERROR); }

require_once __DIR__ . '/../includes/class-change-controller.php';

$state = (new WPFixPilot_Change_Controller())->current_state(10, 'yoast');
assert(is_array($state));
assert($state['values']['featured_image_id'] === 42);
assert($state['values']['featured_image_alt'] === 'Revisie in uitvoering');

echo "change controller monitoring tests passed\n";
