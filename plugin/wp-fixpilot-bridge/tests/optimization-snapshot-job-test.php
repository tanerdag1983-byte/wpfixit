<?php

declare(strict_types=1);

require_once __DIR__ . '/template-snapshot-test.php';
require_once __DIR__ . '/../includes/class-change-controller.php';

$GLOBALS['wpfixpilot_optimization_writes'] = 0;

function get_permalink(WP_Post|int $post): string
{
    $postId = $post instanceof WP_Post ? $post->ID : $post;
    return 'https://member.example/?p=' . $postId;
}

final class Optimization_Snapshot_Test_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string { return 'gutenberg'; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool { return $postId === 42; }
    public function clone_meta_keys(int $postId): array { return ['optimization_tree']; }

    public function schema(int $postId): array|WP_Error
    {
        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => [[
                'id' => 'content',
                'layout' => 'content',
                'label' => 'Content',
                'semantic_role' => 'content',
                'fields' => [[
                    'id' => 'content:title',
                    'path' => 'optimization_tree/title',
                    'label' => 'Titel',
                    'value_type' => 'heading',
                    'current_value' => (string) get_post_meta(
                        $postId,
                        'optimization_tree',
                        true
                    )['title'],
                    'required' => true,
                    'max_length' => 180,
                ]],
            ]],
        ];
    }

    public function structure_hash(int $postId): string
    {
        return hash(
            'sha256',
            wp_json_encode(get_post_meta($postId, 'optimization_tree', true))
        );
    }

    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        $GLOBALS['wpfixpilot_optimization_writes']++;
        return true;
    }
}

$source = new WP_Post();
$source->ID = 42;
$source->post_title = 'Existing page';
$source->post_name = 'existing-page';
$source->post_content = '<!-- wp:paragraph --><p>Original</p><!-- /wp:paragraph -->';
$GLOBALS['wpfixpilot_posts'][42] = $source;
$GLOBALS['wpfixpilot_meta'][42] = [
    'optimization_tree' => [['title' => 'Original title']],
];
$sourceBefore = clone $source;
$sourceMetaBefore = $GLOBALS['wpfixpilot_meta'][42];

$controller = new WPFixPilot_Blueprint_Controller(
    [new Optimization_Snapshot_Test_Adapter()],
    null,
    static fn (): ?string => 'yoast'
);
$result = $controller->capture_optimization_snapshot(42);

assert(!is_wp_error($result));
assert($result['source_post_id'] === 42);
assert($result['snapshot_kind'] === 'optimization_source');
assert($result['source_url'] === 'https://member.example/?p=42');
assert($result['schema_version'] === 'snapshot-text-v1');
assert($result['schema']['schema_version'] === 'snapshot-text-v1');
assert($result['captured_at'] !== '');
assert(
    (new WPFixPilot_Template_Snapshot_Store())->load(
        (int) $result['snapshot_id']
    )['source_post_id'] === 42
);
assert(get_post(42) == $sourceBefore);
assert($GLOBALS['wpfixpilot_meta'][42] === $sourceMetaBefore);
assert($GLOBALS['wpfixpilot_optimization_writes'] === 0);

final class Mutating_Optimization_Test_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string { return 'gutenberg'; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool { return $postId === 43; }
    public function clone_meta_keys(int $postId): array { return []; }
    public function schema(int $postId): array|WP_Error
    {
        if ($postId !== 43) {
            $GLOBALS['wpfixpilot_posts'][43]->post_content = '<p>Changed</p>';
        }
        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => [[
                'id' => 'content',
                'layout' => 'content',
                'label' => 'Content',
                'semantic_role' => 'content',
                'fields' => [[
                    'id' => 'content:title',
                    'path' => 'post_content',
                    'label' => 'Content',
                    'value_type' => 'rich_text',
                    'current_value' => '<p>Original</p>',
                    'required' => true,
                    'max_length' => 1000,
                ]],
            ]],
        ];
    }
    public function structure_hash(int $postId): string
    {
        return hash('sha256', (string) get_post($postId)->post_content);
    }
    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        return true;
    }
}

$changingSource = new WP_Post();
$changingSource->ID = 43;
$changingSource->post_title = 'Changing page';
$changingSource->post_name = 'changing-page';
$changingSource->post_content = '<p>Original</p>';
$GLOBALS['wpfixpilot_posts'][43] = $changingSource;
$snapshotIdBeforeChange = $GLOBALS['wpfixpilot_next_post_id'];
$changedDuringCapture = (new WPFixPilot_Blueprint_Controller(
    [new Mutating_Optimization_Test_Adapter()],
    null,
    static fn (): ?string => 'yoast'
))->capture_optimization_snapshot(43);

assert(is_wp_error($changedDuringCapture));
assert($changedDuringCapture->code === 'wp_fixpilot_snapshot_source_changed');
assert(get_post($snapshotIdBeforeChange) === null);

function get_site_url(): string { return 'https://member.example'; }
function wp_remote_retrieve_response_code(array $response): int
{
    return (int) ($response['response']['code'] ?? 0);
}
function wp_remote_retrieve_body(array $response): string
{
    return (string) ($response['body'] ?? '');
}
function wp_remote_request(string $url, array $args): array
{
    $GLOBALS['wpfixpilot_optimization_requests'][] = compact('url', 'args');
    return array_shift($GLOBALS['wpfixpilot_optimization_responses']);
}
function optimization_response(int $status, array $body = []): array
{
    return [
        'response' => ['code' => $status],
        'body' => $body === [] ? '' : wp_json_encode($body),
    ];
}

require_once __DIR__ . '/../includes/class-outbound-client.php';

$GLOBALS['wpfixpilot_optimization_requests'] = [];
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, [
        'job' => [
            'id' => 'snapshot-job-1',
            'source_post_id' => 42,
        ],
        'claim_token' => 'snapshot-claim-token-with-valid-length',
    ]),
    optimization_response(200, [
        'id' => 'snapshot-job-1',
        'state' => 'completed',
    ]),
];
$client = new WPFixPilot_Outbound_Client(
    'https://api.example.test',
    'project-1',
    'wpfx_secret',
    'https://member.example'
);
$processed = $client->process_next_snapshot($controller);

assert(!is_wp_error($processed));
assert($processed['source_post_id'] === 42);
assert(str_ends_with(
    $GLOBALS['wpfixpilot_optimization_requests'][0]['url'],
    '/wordpress-snapshot-jobs/claim'
));
assert(str_ends_with(
    $GLOBALS['wpfixpilot_optimization_requests'][1]['url'],
    '/wordpress-snapshot-jobs/snapshot-job-1/complete'
));

echo "optimization snapshot job tests passed\n";
