<?php

declare(strict_types=1);

final class WP_Error
{
    public function __construct(
        private string $code,
        private string $message,
        private mixed $data = null
    ) {}

    public function get_error_code(): string { return $this->code; }
    public function get_error_message(): string { return $this->message; }
    public function get_error_data(): mixed { return $this->data; }
}

$GLOBALS['wpfixpilot_http_requests'] = [];
$GLOBALS['wpfixpilot_http_responses'] = [];
$GLOBALS['wpfixpilot_created_drafts'] = [];

function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function get_site_url(): string { return 'https://member.example'; }
function wp_json_encode(mixed $value): string
{
    return (string) json_encode($value, JSON_UNESCAPED_SLASHES);
}
function wp_remote_request(string $url, array $args): array|WP_Error
{
    $GLOBALS['wpfixpilot_http_requests'][] = ['url' => $url, 'args' => $args];
    return array_shift($GLOBALS['wpfixpilot_http_responses']);
}
function wp_remote_retrieve_response_code(array $response): int
{
    return (int) ($response['response']['code'] ?? 0);
}
function wp_remote_retrieve_body(array $response): string
{
    return (string) ($response['body'] ?? '');
}

final class Test_Blueprint_Controller
{
    public function create_draft(int $blueprintId, array $payload): array|WP_Error
    {
        $GLOBALS['wpfixpilot_created_drafts'][] = [
            'blueprint_id' => $blueprintId,
            'payload' => $payload,
        ];
        return [
            'wordpress_object_id' => 987,
            'edit_url' => 'https://member.example/wp-admin/post.php?post=987&action=edit',
            'status' => 'draft',
        ];
    }
}

final class WPFixPilot_ACF_Blueprint_Adapter {}
final class WPFixPilot_Elementor_Adapter {}
final class WPFixPilot_WPBakery_Adapter {}
final class WPFixPilot_Bricks_Adapter {}
final class WPFixPilot_Gutenberg_Adapter {}

final class WPFixPilot_Blueprint_Controller
{
    public function __construct(array $adapters = [])
    {
        $GLOBALS['wpfixpilot_default_draft_adapters'] = $adapters;
    }
}

require_once __DIR__ . '/../includes/class-outbound-client.php';
require_once __DIR__ . '/../includes/class-draft-job-controller.php';

new WPFixPilot_Draft_Job_Controller(new stdClass());
assert(count($GLOBALS['wpfixpilot_default_draft_adapters']) === 5);
assert(
    $GLOBALS['wpfixpilot_default_draft_adapters'][0]
    instanceof WPFixPilot_ACF_Blueprint_Adapter
);

function response(int $status, array $body = []): array
{
    return [
        'response' => ['code' => $status],
        'body' => $body === [] ? '' : wp_json_encode($body),
    ];
}

$client = new WPFixPilot_Outbound_Client(
    'https://api.example.test/',
    'project-1',
    'wpfx_secret',
    'https://member.example/'
);

$GLOBALS['wpfixpilot_http_responses'][] = response(200, ['connected' => true]);
$verified = $client->verify();
assert(!is_wp_error($verified));
assert($verified['connected'] === true);
assert(!str_contains($GLOBALS['wpfixpilot_http_requests'][0]['url'], 'wpfx_secret'));
assert(
    $GLOBALS['wpfixpilot_http_requests'][0]['args']['headers']['Authorization']
    === 'Bearer wpfx_secret'
);
assert(
    $GLOBALS['wpfixpilot_http_requests'][0]['args']['headers']['X-WP-FixPilot-Site']
    === 'https://member.example'
);

$GLOBALS['wpfixpilot_http_responses'][] = response(204);
assert($client->claim() === null);

$unknownClient = new WPFixPilot_Outbound_Client(
    'https://api.example.test',
    'project-1',
    'wpfx_secret',
    'https://member.example'
);
$unknownController = new WPFixPilot_Draft_Job_Controller(
    $unknownClient,
    new Test_Blueprint_Controller()
);
$unknown = $unknownController->process_payload([
    'contract_version' => 'wordpress-draft-job-v2',
]);
assert(is_wp_error($unknown));
assert($unknown->get_error_code() === 'wp_fixpilot_unsupported_contract');

$GLOBALS['wpfixpilot_http_responses'][] = response(200, [
    'job' => [
        'id' => 'job-unsupported',
        'contract_version' => 'wordpress-draft-job-v2',
    ],
    'claim_token' => 'unsupported-claim-token-long-enough',
]);
$GLOBALS['wpfixpilot_http_responses'][] = response(200, [
    'id' => 'job-unsupported',
    'state' => 'failed',
]);
$reportedUnknown = $unknownController->process_next();
assert(is_wp_error($reportedUnknown));
assert($reportedUnknown->get_error_code() === 'wp_fixpilot_unsupported_contract');
$unknownFailureRequest = $GLOBALS['wpfixpilot_http_requests'][3];
$unknownFailureBody = json_decode($unknownFailureRequest['args']['body'], true);
assert($unknownFailureBody['error_code'] === 'unsupported_contract');
assert($GLOBALS['wpfixpilot_created_drafts'] === []);

$job = [
    'id' => 'job-1',
    'project_id' => 'project-1',
    'proposal_version_id' => 'proposal-1',
    'contract_version' => 'wordpress-draft-job-v1',
    'payload' => [
        'proposal_version_id' => 'proposal-1',
        'wordpress_blueprint_id' => 321,
        'expected_version' => 4,
        'expected_structure_hash' => 'blueprint-hash',
        'idempotency_key' => 'proposal-1',
        'replacements' => ['acf-title' => 'Nieuwe titel'],
        'approved_urls' => ['/offerte-aanvragen/'],
        'seo' => [
            'title' => 'SEO titel',
            'description' => 'SEO omschrijving',
            'keyword' => 'dsg revisie',
        ],
    ],
];
$GLOBALS['wpfixpilot_http_responses'][] = response(200, [
    'job' => $job,
    'claim_token' => 'claim-token-with-sufficient-length',
]);
$GLOBALS['wpfixpilot_http_responses'][] = response(200, [
    'id' => 'job-1',
    'state' => 'completed',
]);

$controller = new WPFixPilot_Draft_Job_Controller(
    $client,
    new Test_Blueprint_Controller()
);
$result = $controller->process_next();
assert(!is_wp_error($result));
assert($result['status'] === 'draft');
assert($GLOBALS['wpfixpilot_created_drafts'][0]['blueprint_id'] === 321);
assert(
    $GLOBALS['wpfixpilot_created_drafts'][0]['payload']['expected_version'] === 4
);
$completeRequest = $GLOBALS['wpfixpilot_http_requests'][5];
assert(str_ends_with($completeRequest['url'], '/wordpress-draft-jobs/job-1/complete'));
$completeBody = json_decode($completeRequest['args']['body'], true);
assert($completeBody['wordpress_object_id'] === 987);
assert($completeBody['claim_token'] === 'claim-token-with-sufficient-length');

echo "draft job tests passed\n";
