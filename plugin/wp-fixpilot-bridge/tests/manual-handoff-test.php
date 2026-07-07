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

$GLOBALS['wpfixpilot_transients'] = [];
$GLOBALS['wpfixpilot_options'] = [
    'wp_fixpilot_secret' => 'bridge-secret',
];
$GLOBALS['wpfixpilot_http_requests'] = [];
$GLOBALS['wpfixpilot_created_drafts'] = [];
$GLOBALS['wpfixpilot_browser_history_fragment_cleared'] = false;

function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function get_option(string $key, mixed $default = false): mixed { return $GLOBALS['wpfixpilot_options'][$key] ?? $default; }
function update_option(string $key, mixed $value, bool $autoload = false): bool { $GLOBALS['wpfixpilot_options'][$key] = $value; return true; }
function wp_generate_password(int $length = 12, bool $specialChars = true, bool $extraSpecialChars = false): string { return 'session-1'; }
function set_transient(string $key, mixed $value, int $expiration): bool { $GLOBALS['wpfixpilot_transients'][$key] = $value; return true; }
function get_transient(string $key): mixed { return $GLOBALS['wpfixpilot_transients'][$key] ?? false; }
function delete_transient(string $key): bool { unset($GLOBALS['wpfixpilot_transients'][$key]); return true; }
function get_site_url(): string { return 'https://member.example'; }
function wp_remote_post(string $url, array $args = []): array
{
    $GLOBALS['wpfixpilot_http_requests'][] = ['url' => $url, 'args' => $args];
    if (str_ends_with($url, '/complete')) {
        return [
            'response' => ['code' => 200],
            'body' => json_encode([
                'handoff' => ['state' => 'completed'],
                'proposal_version' => ['state' => 'draft_created'],
            ]),
        ];
    }

    return [
        'response' => ['code' => 200],
        'body' => json_encode([
            'handoff' => [
                'id' => 'handoff-1',
                'project_id' => 'project-1',
                'proposal_version_id' => 'proposal-7',
                'state' => 'redeemed',
            ],
            'package' => [
                'proposal_version_id' => 'proposal-7',
                'version_number' => 7,
                'state' => 'approved',
                'package' => ['title' => 'DSG revisie pagina'],
            ],
        ]),
    ];
}
function wp_remote_retrieve_response_code(array $response): int { return (int) ($response['response']['code'] ?? 500); }
function wp_remote_retrieve_body(array $response): string { return (string) ($response['body'] ?? ''); }
function admin_url(string $path = ''): string { return 'https://member.example/wp-admin/' . ltrim($path, '/'); }
function wp_create_nonce(string $action): string { return 'nonce'; }
function current_user_can(string $capability): bool { return $capability === 'edit_pages'; }
function esc_url(string $value): string { return $value; }
function esc_html(string $value): string { return $value; }
function esc_attr(string $value): string { return $value; }
function sanitize_text_field(string $value): string { return trim($value); }
function wp_unslash(string $value): string { return $value; }
function wp_json_encode(mixed $value): string { return (string) json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE); }

require_once __DIR__ . '/../includes/class-import-session-store.php';
require_once __DIR__ . '/../includes/class-auth.php';
require_once __DIR__ . '/../includes/class-manual-handoff-controller.php';

final class Test_Page_Package_Controller
{
    public function create_draft(array $payload): array
    {
        $GLOBALS['wpfixpilot_created_drafts'][] = $payload;
        return [
            'wordpress_object_id' => 20,
            'edit_url' => 'https://example.com/wp-admin/post.php?post=20',
            'status' => 'draft',
        ];
    }
}

$store = new WPFixPilot_Import_Session_Store();
$sessionId = $store->create('handoff-1', [
    'proposal_version_id' => 'proposal-7',
    'wordpress_user_id' => 12,
]);
assert($sessionId === 'session-1');
assert($store->get('session-1')['payload']['proposal_version_id'] === 'proposal-7');

$controller = new WPFixPilot_Manual_Handoff_Controller($store, 'https://api.example.test');
$redeemed = $controller->redeem_code('opaque-code', 12);
assert(!is_wp_error($redeemed));
assert($redeemed['summary']['proposal_version'] === 7);
assert($redeemed['summary']['draft_only'] === true);
assert($GLOBALS['wpfixpilot_browser_history_fragment_cleared'] === true);

$importController = new WPFixPilot_Manual_Handoff_Controller(
    $store,
    'https://api.example.test',
    new Test_Page_Package_Controller()
);
$confirmed = $importController->confirm_import('session-1', 12);
assert(!is_wp_error($confirmed));
assert($confirmed['wordpress_object_id'] === 20);
assert($confirmed['edit_url'] === 'https://example.com/wp-admin/post.php?post=20');
assert(count($GLOBALS['wpfixpilot_http_requests']) === 2);
assert(
    $GLOBALS['wpfixpilot_http_requests'][1]['url']
    === 'https://api.example.test/projects/project-1/page-proposals/handoffs/handoff-1/complete'
);

$repeat = $importController->confirm_import('session-1', 12);
assert(!is_wp_error($repeat));
assert($repeat['wordpress_object_id'] === 20);
assert(count($GLOBALS['wpfixpilot_created_drafts']) === 1);
assert(count($GLOBALS['wpfixpilot_http_requests']) === 2);

echo "manual handoff tests passed\n";
