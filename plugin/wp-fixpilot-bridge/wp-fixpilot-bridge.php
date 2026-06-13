<?php
/**
 * Plugin Name: WP FixPilot Bridge
 * Description: Secure inventory and publishing bridge for WP FixPilot.
 * Version: 0.1.0
 * Requires at least: 6.5
 * Requires PHP: 8.1
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

require_once __DIR__ . '/includes/class-auth.php';
require_once __DIR__ . '/includes/class-rest-controller.php';

register_activation_hook(__FILE__, static function (): void {
    if (get_option('wp_fixpilot_secret', '') === '') {
        update_option(
            'wp_fixpilot_secret',
            wp_generate_password(64, false, false),
            false
        );
    }
});

add_action('rest_api_init', static function (): void {
    $controller = new WPFixPilot_REST_Controller();
    $controller->register_routes();
});

