<?php

declare(strict_types=1);

require_once __DIR__ . '/template-snapshot-test.php';
require_once __DIR__ . '/../includes/class-change-controller.php';

$GLOBALS['wpfixpilot_optimization_writes'] = 0;

function get_permalink(WP_Post|int $post): string
{
    $postId = $post instanceof WP_Post ? $post->ID : $post;
    return $GLOBALS['wpfixpilot_permalinks'][$postId]
        ?? 'https://member.example/?p=' . $postId;
}

final class Optimization_Snapshot_Test_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string { return 'gutenberg'; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool
    {
        return in_array($postId, [42, 44, 45, 46], true);
    }
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
    '_wp_page_template' => ['service.php'],
    '_thumbnail_id' => [501],
];

function optimization_source_hash(int $postId): string
{
    $state = (new WPFixPilot_Change_Controller(
        [new Optimization_Snapshot_Test_Adapter()]
    ))->current_state($postId, 'yoast');
    assert(!is_wp_error($state));

    return (string) $state['content_hash'];
}

$fingerprintBaseline = optimization_source_hash(42);
$fingerprintMutations = [
    static function (): void {
        $GLOBALS['wpfixpilot_posts'][42]->post_title = 'Changed title';
    },
    static function (): void {
        $GLOBALS['wpfixpilot_posts'][42]->post_name = 'changed-slug';
    },
    static function (): void {
        $GLOBALS['wpfixpilot_permalinks'][42] = 'https://member.example/changed';
    },
    static function (): void {
        $GLOBALS['wpfixpilot_posts'][42]->post_content = '<p>Changed content</p>';
    },
    static function (): void {
        update_post_meta(42, '_wp_page_template', 'changed.php');
    },
    static function (): void {
        update_post_meta(42, '_thumbnail_id', 999);
    },
    static function (): void {
        update_post_meta(42, 'optimization_tree', [
            'title' => 'Changed builder metadata',
        ]);
    },
];
foreach ($fingerprintMutations as $mutate) {
    $sourcePost = clone $GLOBALS['wpfixpilot_posts'][42];
    $sourceMetadata = $GLOBALS['wpfixpilot_meta'][42];
    $sourcePermalink = $GLOBALS['wpfixpilot_permalinks'][42] ?? null;
    $mutate();
    assert(optimization_source_hash(42) !== $fingerprintBaseline);
    $GLOBALS['wpfixpilot_posts'][42] = $sourcePost;
    $GLOBALS['wpfixpilot_meta'][42] = $sourceMetadata;
    if ($sourcePermalink === null) {
        unset($GLOBALS['wpfixpilot_permalinks'][42]);
    } else {
        $GLOBALS['wpfixpilot_permalinks'][42] = $sourcePermalink;
    }
}
$sourceBefore = clone get_post(42);
$sourceMetaBefore = $GLOBALS['wpfixpilot_meta'][42];

$controller = new WPFixPilot_Blueprint_Controller(
    [new Optimization_Snapshot_Test_Adapter()],
    null,
    static fn (): ?string => 'yoast'
);
$sourceIdentity = (new WPFixPilot_Change_Controller(
    [new Optimization_Snapshot_Test_Adapter()]
))->current_state(42, 'yoast');
assert(!is_wp_error($sourceIdentity));
$result = $controller->capture_optimization_snapshot(
    42,
    'direct-snapshot-job',
    'https://member.example/?p=42',
    (string) $sourceIdentity['content_hash']
);

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

function document_field_value(array $schema, string $fieldId): string
{
    foreach ((array) ($schema['document_fields'] ?? []) as $field) {
        if (($field['id'] ?? '') === $fieldId) {
            return (string) ($field['current_value'] ?? '');
        }
    }

    return '';
}

$seoFamilies = [
    'yoast' => [
        'post_id' => 44,
        'meta' => [
            '_yoast_wpseo_title' => 'Yoast title',
            '_yoast_wpseo_metadesc' => 'Yoast description',
            '_yoast_wpseo_focuskw' => 'yoast keyword',
        ],
    ],
    'rank_math' => [
        'post_id' => 45,
        'meta' => [
            'rank_math_title' => 'Rank Math title',
            'rank_math_description' => 'Rank Math description',
            'rank_math_focus_keyword' => 'rank math keyword',
        ],
    ],
    'aioseo' => [
        'post_id' => 46,
        'meta' => [
            '_aioseo_title' => 'AIOSEO title',
            '_aioseo_description' => 'AIOSEO description',
            '_aioseo_keyphrases' => wp_json_encode([
                'focus' => ['keyphrase' => 'aioseo keyword'],
            ]),
        ],
    ],
];
foreach ($seoFamilies as $plugin => $fixture) {
    $postId = (int) $fixture['post_id'];
    $seoSource = new WP_Post();
    $seoSource->ID = $postId;
    $seoSource->post_title = strtoupper($plugin) . ' page';
    $seoSource->post_name = $plugin . '-page';
    $seoSource->post_content = '<p>SEO source</p>';
    $GLOBALS['wpfixpilot_posts'][$postId] = $seoSource;
    $GLOBALS['wpfixpilot_meta'][$postId] = [
        'optimization_tree' => [['title' => 'SEO heading']],
    ];
    foreach ($fixture['meta'] as $key => $value) {
        $GLOBALS['wpfixpilot_meta'][$postId][$key] = [$value];
    }
    $seoSourceBefore = clone $seoSource;
    $seoMetaBefore = $GLOBALS['wpfixpilot_meta'][$postId];
    $seoController = new WPFixPilot_Blueprint_Controller(
        [new Optimization_Snapshot_Test_Adapter()],
        null,
        static fn (): ?string => $plugin
    );
    $seoIdentity = (new WPFixPilot_Change_Controller(
        [new Optimization_Snapshot_Test_Adapter()]
    ))->current_state($postId, $plugin);
    assert(!is_wp_error($seoIdentity));
    $seoResult = $seoController->capture_optimization_snapshot(
        $postId,
        'seo-snapshot-job-' . $plugin,
        get_permalink($postId),
        (string) $seoIdentity['content_hash']
    );

    assert(!is_wp_error($seoResult));
    assert(document_field_value(
        $seoResult['schema'],
        'seo:title'
    ) === (string) $seoIdentity['values']['seo_title']);
    assert(document_field_value(
        $seoResult['schema'],
        'seo:meta_description'
    ) === (string) $seoIdentity['values']['meta_description']);
    assert(document_field_value(
        $seoResult['schema'],
        'seo:focus_keyword'
    ) === (string) $seoIdentity['values']['focus_keyword']);
    foreach ($fixture['meta'] as $key => $value) {
        assert(
            get_post_meta((int) $seoResult['snapshot_id'], $key, true)
            === $value
        );
    }
    assert(get_post($postId) == $seoSourceBefore);
    assert($GLOBALS['wpfixpilot_meta'][$postId] === $seoMetaBefore);
}

final class Mutating_Optimization_Test_Adapter implements WPFixPilot_Blueprint_Adapter
{
    public function key(): string { return 'gutenberg'; }
    public function is_active(): bool { return true; }
    public function uses_page(int $postId): bool { return $postId === 43; }
    public function clone_meta_keys(int $postId): array { return ['optimization_tree']; }
    public function schema(int $postId): array|WP_Error
    {
        if ($postId !== 43) {
            $GLOBALS['wpfixpilot_meta'][43]['optimization_tree'] = [[
                'title' => 'Changed builder metadata',
            ]];
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
        return true;
    }
}

$changingSource = new WP_Post();
$changingSource->ID = 43;
$changingSource->post_title = 'Changing page';
$changingSource->post_name = 'changing-page';
$changingSource->post_content = '<p>Original</p>';
$GLOBALS['wpfixpilot_posts'][43] = $changingSource;
$GLOBALS['wpfixpilot_meta'][43] = [
    'optimization_tree' => [['title' => 'Original builder metadata']],
];
$changingIdentity = (new WPFixPilot_Change_Controller(
    [new Mutating_Optimization_Test_Adapter()]
))->current_state(43, 'yoast');
assert(!is_wp_error($changingIdentity));
$snapshotIdBeforeChange = $GLOBALS['wpfixpilot_next_post_id'];
$changedDuringCapture = (new WPFixPilot_Blueprint_Controller(
    [new Mutating_Optimization_Test_Adapter()],
    null,
    static fn (): ?string => 'yoast'
))->capture_optimization_snapshot(
    43,
    'mutating-snapshot-job',
    get_permalink(43),
    (string) $changingIdentity['content_hash']
);

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
function wp_remote_request(string $url, array $args): array|WP_Error
{
    $GLOBALS['wpfixpilot_optimization_requests'][] = compact('url', 'args');
    return array_shift($GLOBALS['wpfixpilot_optimization_responses']);
}
function get_posts(array $args): array
{
    $ids = [];
    $metaQuery = (array) ($args['meta_query'] ?? []);
    foreach ($GLOBALS['wpfixpilot_posts'] as $postId => $post) {
        if (
            !$post instanceof WP_Post
            || $post->post_type !== ($args['post_type'] ?? '')
            || $post->post_status !== ($args['post_status'] ?? '')
        ) {
            continue;
        }
        $matches = true;
        foreach ($metaQuery as $condition) {
            if (
                !is_array($condition)
                || (string) get_post_meta(
                    (int) $postId,
                    (string) ($condition['key'] ?? ''),
                    true
                ) !== (string) ($condition['value'] ?? '')
            ) {
                $matches = false;
                break;
            }
        }
        if ($matches) {
            $ids[] = (int) $postId;
        }
    }

    return array_slice($ids, 0, (int) ($args['numberposts'] ?? count($ids)));
}
function optimization_response(int $status, array $body = []): array
{
    return [
        'response' => ['code' => $status],
        'body' => $body === [] ? '' : wp_json_encode($body),
    ];
}

require_once __DIR__ . '/../includes/class-outbound-client.php';

$outboundIdentity = (new WPFixPilot_Change_Controller(
    [new Optimization_Snapshot_Test_Adapter()]
))->current_state(42, 'yoast');
assert(!is_wp_error($outboundIdentity));
$GLOBALS['wpfixpilot_optimization_requests'] = [];
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, [
        'job' => [
            'id' => 'snapshot-job-1',
            'source_post_id' => 42,
            'source_url' => get_permalink(42),
            'source_content_hash' => $outboundIdentity['content_hash'],
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

$staleIdentity = $outboundIdentity['content_hash'];
$GLOBALS['wpfixpilot_posts'][42]->post_title = 'Changed before snapshot';
$freshIdentity = optimization_source_hash(42);
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, [
        'job' => [
            'id' => 'snapshot-job-source-drift',
            'source_post_id' => 42,
            'source_url' => get_permalink(42),
            'source_content_hash' => $staleIdentity,
        ],
        'claim_token' => 'source-drift-claim-token-valid-length',
    ]),
    optimization_response(200, [
        'id' => 'snapshot-job-source-drift',
        'state' => 'failed',
    ]),
];
$sourceDrift = $client->process_next_snapshot($controller);
$sourceDriftRequest = json_decode(
    $GLOBALS['wpfixpilot_optimization_requests'][3]['args']['body'],
    true
);
assert(is_wp_error($sourceDrift));
assert($sourceDriftRequest['error_code'] === 'source_identity_changed');
assert($sourceDriftRequest['source_post_id'] === 42);
assert($sourceDriftRequest['source_url'] === get_permalink(42));
assert($sourceDriftRequest['source_content_hash'] === $freshIdentity);
$GLOBALS['wpfixpilot_posts'][42]->post_title = 'Existing page';

$snapshotCountBeforeAmbiguous = count(array_filter(
    $GLOBALS['wpfixpilot_posts'],
    static fn (WP_Post $post): bool =>
        $post->post_type === WPFixPilot_Template_Snapshot_Store::POST_TYPE
));
$ambiguousClaim = [
    'job' => [
        'id' => 'snapshot-job-ambiguous',
        'source_post_id' => 42,
        'source_url' => get_permalink(42),
        'source_content_hash' => $outboundIdentity['content_hash'],
    ],
    'claim_token' => 'ambiguous-claim-token-with-valid-length',
];
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, $ambiguousClaim),
    new WP_Error('timeout', 'Completion response was lost.'),
    optimization_response(200, $ambiguousClaim),
    optimization_response(200, [
        'id' => 'snapshot-job-ambiguous',
        'state' => 'completed',
    ]),
];
$firstAmbiguous = $client->process_next_snapshot($controller);
assert(is_wp_error($firstAmbiguous));
$secondAmbiguous = $client->process_next_snapshot($controller);
assert(!is_wp_error($secondAmbiguous));
assert($firstAmbiguous->code === 'wp_fixpilot_outbound_unavailable');
assert(
    count(array_filter(
        $GLOBALS['wpfixpilot_posts'],
        static fn (WP_Post $post): bool =>
            $post->post_type === WPFixPilot_Template_Snapshot_Store::POST_TYPE
    )) === $snapshotCountBeforeAmbiguous + 1
);
assert(
    $secondAmbiguous['snapshot_id']
    === (new WPFixPilot_Template_Snapshot_Store())->find_for_job(
        'snapshot-job-ambiguous'
    )
);

$snapshotCountBeforeLeaseExpiry = count(array_filter(
    $GLOBALS['wpfixpilot_posts'],
    static fn (WP_Post $post): bool =>
        $post->post_type === WPFixPilot_Template_Snapshot_Store::POST_TYPE
));
$leaseJob = [
    'id' => 'snapshot-job-expired-lease',
    'source_post_id' => 42,
    'source_url' => get_permalink(42),
    'source_content_hash' => $outboundIdentity['content_hash'],
];
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, [
        'job' => $leaseJob,
        'claim_token' => 'expired-claim-token-with-valid-length',
    ]),
    optimization_response(409, [
        'detail' => ['code' => 'snapshot_claim_invalid'],
    ]),
    optimization_response(200, [
        'job' => $leaseJob,
        'claim_token' => 'reclaimed-token-with-valid-length',
    ]),
    optimization_response(200, [
        'id' => 'snapshot-job-expired-lease',
        'state' => 'completed',
    ]),
];
$expiredLease = $client->process_next_snapshot($controller);
assert(is_wp_error($expiredLease));
$retainedSnapshotId = (
    new WPFixPilot_Template_Snapshot_Store()
)->find_for_job('snapshot-job-expired-lease');
assert($retainedSnapshotId !== null);
$reclaimedLease = $client->process_next_snapshot($controller);
assert(!is_wp_error($reclaimedLease));
assert($reclaimedLease['snapshot_id'] === $retainedSnapshotId);
assert(
    count(array_filter(
        $GLOBALS['wpfixpilot_posts'],
        static fn (WP_Post $post): bool =>
            $post->post_type === WPFixPilot_Template_Snapshot_Store::POST_TYPE
    )) === $snapshotCountBeforeLeaseExpiry + 1
);

$snapshotCountBeforeRejection = count($GLOBALS['wpfixpilot_posts']);
$GLOBALS['wpfixpilot_optimization_responses'] = [
    optimization_response(200, [
        'job' => [
            'id' => 'snapshot-job-rejected',
            'source_post_id' => 42,
            'source_url' => get_permalink(42),
            'source_content_hash' => $outboundIdentity['content_hash'],
        ],
        'claim_token' => 'rejected-claim-token-with-valid-length',
    ]),
    optimization_response(409, [
        'detail' => ['code' => 'snapshot_conflict'],
    ]),
];
$rejected = $client->process_next_snapshot($controller);
assert(is_wp_error($rejected));
assert($rejected->code === 'wp_fixpilot_outbound_request_failed');
assert(count($GLOBALS['wpfixpilot_posts']) === $snapshotCountBeforeRejection);
assert(
    (new WPFixPilot_Template_Snapshot_Store())->find_for_job(
        'snapshot-job-rejected'
    ) === null
);

echo "optimization snapshot job tests passed\n";
