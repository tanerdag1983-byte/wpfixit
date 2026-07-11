<?php

declare(strict_types=1);

define('WPFIXPILOT_TESTING', true);

final class WP_Error
{
    public function __construct(private string $code, private string $message) {}
    public function get_error_code(): string { return $this->code; }
    public function get_error_message(): string { return $this->message; }
}

final class WPFixPilot_Manual_Handoff_Controller
{
    public function render_import_page(): void {}
    public function handle_redeem(): void {}
    public function handle_confirm_import(): void {}
}

final class Test_Outbound_Client
{
    public function verify(): array { return ['connected' => true]; }
}

final class Test_Draft_Processor
{
    public function process_next(): ?array
    {
        $GLOBALS['wpfixpilot_processed_job_count']++;
        return [
            'status' => 'draft',
            'wordpress_object_id' => 987,
            'edit_url' => 'https://member.example/wp-admin/post.php?post=987',
        ];
    }
}

$GLOBALS['wpfixpilot_options'] = [];
$GLOBALS['wpfixpilot_actions'] = [];
$GLOBALS['wpfixpilot_filters'] = [];
$GLOBALS['wpfixpilot_capabilities'] = ['manage_options', 'edit_pages'];
$GLOBALS['wpfixpilot_processed_job_count'] = 0;
$GLOBALS['wpfixpilot_redirect_to'] = '';

function add_action(string $hook, callable $callback): void
{
    $GLOBALS['wpfixpilot_actions'][$hook][] = $callback;
}
function add_filter(string $hook, callable $callback): void
{
    $GLOBALS['wpfixpilot_filters'][$hook][] = $callback;
}
function add_options_page(...$args): void {}
function add_submenu_page(...$args): void {}
function current_user_can(string $capability): bool
{
    return in_array($capability, $GLOBALS['wpfixpilot_capabilities'], true);
}
function check_admin_referer(string $action): void {}
function get_option(string $key, mixed $default = false): mixed
{
    return $GLOBALS['wpfixpilot_options'][$key] ?? $default;
}
function update_option(string $key, mixed $value, bool $autoload = false): bool
{
    $GLOBALS['wpfixpilot_options'][$key] = $value;
    return true;
}
function wp_die(string $message): never { throw new RuntimeException($message); }
function wp_safe_redirect(string $url): void { $GLOBALS['wpfixpilot_redirect_to'] = $url; }
function admin_url(string $path = ''): string
{
    return 'https://member.example/wp-admin/' . ltrim($path, '/');
}
function sanitize_text_field(string $value): string { return trim($value); }
function esc_url_raw(string $value): string { return trim($value); }
function wp_unslash(string $value): string { return $value; }
function is_wp_error(mixed $value): bool { return $value instanceof WP_Error; }
function get_site_url(): string { return 'https://member.example'; }
function wp_generate_password(...$args): string { return 'generated-secret'; }
function esc_html(string $value): string { return $value; }
function esc_attr(string $value): string { return $value; }
function esc_url(string $value): string { return $value; }
function rest_url(string $path): string { return 'https://member.example/wp-json/' . $path; }
function wp_nonce_field(string $action): void {}
function submit_button(...$args): void {}

require_once __DIR__ . '/../includes/class-admin.php';

$admin = new WPFixPilot_Admin(
    new WPFixPilot_Manual_Handoff_Controller(),
    static fn (): object => new Test_Outbound_Client(),
    static fn (): object => new Test_Draft_Processor()
);
$admin->register_action_handlers();
$admin->register_cron_handlers();

assert(isset($GLOBALS['wpfixpilot_actions']['admin_post_wp_fixpilot_save_outbound_connection']));
assert(isset($GLOBALS['wpfixpilot_actions']['admin_post_wp_fixpilot_test_outbound_connection']));
assert(isset($GLOBALS['wpfixpilot_actions']['admin_post_wp_fixpilot_fetch_draft_job']));
assert(isset($GLOBALS['wpfixpilot_actions']['wp_fixpilot_poll_draft_jobs']));
assert(isset($GLOBALS['wpfixpilot_filters']['cron_schedules']));

$_POST = [
    'backend_base_url' => 'https://api.example.test/',
    'project_id' => 'project-1',
    'project_key' => 'wpfx_secret',
];
$admin->save_outbound_connection();
assert(get_option('wp_fixpilot_outbound_backend_url') === 'https://api.example.test');
assert(get_option('wp_fixpilot_outbound_project_id') === 'project-1');
assert(get_option('wp_fixpilot_outbound_project_key') === 'wpfx_secret');

$admin->test_outbound_connection();
assert(get_option('wp_fixpilot_outbound_last_status') === 'connected');
assert(get_option('wp_fixpilot_outbound_last_contact') !== '');

$admin->fetch_draft_job();
assert($GLOBALS['wpfixpilot_processed_job_count'] === 1);
assert(get_option('wp_fixpilot_outbound_last_status') === 'completed');

$cronCallback = $GLOBALS['wpfixpilot_actions']['wp_fixpilot_poll_draft_jobs'][0];
$cronCallback();
assert($GLOBALS['wpfixpilot_processed_job_count'] === 2);

ob_start();
$admin->render_settings_page();
$settingsPage = ob_get_clean();
assert(!str_contains($settingsPage, 'wpfx_secret'));
assert(str_contains($settingsPage, 'Uitgaande verbinding'));

$GLOBALS['wpfixpilot_capabilities'] = [];
try {
    $admin->save_outbound_connection();
    assert(false, 'save should require manage_options');
} catch (RuntimeException $error) {
    assert($error->getMessage() === 'Geen toegang.');
}
try {
    $admin->fetch_draft_job();
    assert(false, 'fetch should require edit_pages');
} catch (RuntimeException $error) {
    assert($error->getMessage() === 'Geen toegang.');
}

echo "draft job admin tests passed\n";
