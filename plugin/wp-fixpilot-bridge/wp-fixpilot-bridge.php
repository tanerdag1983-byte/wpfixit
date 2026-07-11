<?php
/**
 * Plugin Name: WP FixPilot Bridge
 * Description: Secure inventory and publishing bridge for WP FixPilot.
 * Version: 0.3.15
 * Requires at least: 6.5
 * Requires PHP: 8.1
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

define('WPFIXPILOT_BRIDGE_VERSION', '0.3.15');

require_once __DIR__ . '/includes/class-auth.php';
require_once __DIR__ . '/includes/class-admin.php';
require_once __DIR__ . '/includes/class-import-session-store.php';
require_once __DIR__ . '/includes/class-manual-handoff-controller.php';
require_once __DIR__ . '/includes/seo-adapters/interface-seo-adapter.php';
require_once __DIR__ . '/includes/seo-adapters/class-adapter-changes.php';
require_once __DIR__ . '/includes/seo-adapters/class-yoast-adapter.php';
require_once __DIR__ . '/includes/seo-adapters/class-rank-math-adapter.php';
require_once __DIR__ . '/includes/seo-adapters/class-aioseo-adapter.php';
require_once __DIR__ . '/includes/class-change-controller.php';
require_once __DIR__ . '/includes/builder-adapters/interface-builder-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/interface-blueprint-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-gutenberg-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-elementor-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-bricks-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-wpbakery-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-acf-adapter.php';
require_once __DIR__ . '/includes/builder-adapters/class-acf-blueprint-adapter.php';
require_once __DIR__ . '/includes/class-post-cloner.php';
require_once __DIR__ . '/includes/class-page-package-controller.php';
require_once __DIR__ . '/includes/class-blueprint-controller.php';
require_once __DIR__ . '/includes/class-outbound-client.php';
require_once __DIR__ . '/includes/class-draft-job-controller.php';
require_once __DIR__ . '/includes/class-rest-controller.php';

register_activation_hook(__FILE__, static function (): void {
    if (get_option('wp_fixpilot_secret', '') === '') {
        update_option(
            'wp_fixpilot_secret',
            wp_generate_password(64, false, false),
            false
        );
    }
    if (!wp_next_scheduled('wp_fixpilot_poll_draft_jobs')) {
        wp_schedule_event(
            time() + 300,
            'wp_fixpilot_five_minutes',
            'wp_fixpilot_poll_draft_jobs'
        );
    }
});

register_deactivation_hook(__FILE__, static function (): void {
    wp_clear_scheduled_hook('wp_fixpilot_poll_draft_jobs');
});

add_action('rest_api_init', static function (): void {
    $controller = new WPFixPilot_REST_Controller();
    $controller->register_routes();
});

$wpFixPilotAdmin = new WPFixPilot_Admin();
$wpFixPilotAdmin->register_action_handlers();
$wpFixPilotAdmin->register_cron_handlers();
add_action('admin_menu', [$wpFixPilotAdmin, 'register']);

add_action('template_redirect', static function (): void {
    if (!is_singular()) {
        return;
    }
    $target = (string) get_post_meta(
        (int) get_queried_object_id(),
        '_wp_fixpilot_redirect_to',
        true
    );
    if ($target !== '') {
        wp_safe_redirect($target, 301, 'WP FixPilot');
        exit;
    }
});
