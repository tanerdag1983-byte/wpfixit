<?php

declare(strict_types=1);

final class WPFixPilot_REST_Controller
{
    private const NAMESPACE = 'wpfixpilot/v1';

    public function register_routes(): void
    {
        register_rest_route(self::NAMESPACE, '/health', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [$this, 'health'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/inventory', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [$this, 'inventory'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/content/(?P<id>\d+)', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [$this, 'current_content'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/changes/(?P<id>\d+)', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [$this, 'apply_change'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/builders', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [$this, 'builders'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/templates/(?P<id>\d+)/slots', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [$this, 'template_slots'],
            'permission_callback' => [$this, 'authorize'],
        ]);
        register_rest_route(self::NAMESPACE, '/draft-pages', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [$this, 'create_draft_page'],
            'permission_callback' => [$this, 'authorize'],
        ]);
    }

    public function authorize(WP_REST_Request $request): bool|WP_Error
    {
        $secret = (string) get_option('wp_fixpilot_secret', '');
        $auth = new WPFixPilot_Auth(
            $secret,
            null,
            300,
            static fn (string $nonce): bool =>
                get_transient('wp_fixpilot_nonce_' . hash('sha256', $nonce)) !== false,
            static function (string $nonce): void {
                set_transient(
                    'wp_fixpilot_nonce_' . hash('sha256', $nonce),
                    '1',
                    300
                );
            }
        );

        $valid = $auth->verify(
            $request->get_method(),
            $request->get_route(),
            (string) $request->get_header('x-wp-fixpilot-timestamp'),
            (string) $request->get_header('x-wp-fixpilot-nonce'),
            (string) $request->get_body(),
            (string) $request->get_header('x-wp-fixpilot-signature')
        );
        if (!$valid) {
            return new WP_Error(
                'wp_fixpilot_forbidden',
                'Ongeldige WP FixPilot-handtekening.',
                ['status' => 403]
            );
        }
        return true;
    }

    public function health(): WP_REST_Response
    {
        return new WP_REST_Response([
            'status' => 'ok',
            'site_url' => get_site_url(),
            'wordpress_version' => get_bloginfo('version'),
            'plugin_version' => '0.2.0',
            'seo_plugin' => $this->detect_seo_plugin(),
        ]);
    }

    public function inventory(): WP_REST_Response
    {
        $query = new WP_Query([
            'post_type' => ['post', 'page'],
            'post_status' => ['publish', 'draft', 'private'],
            'posts_per_page' => -1,
            'orderby' => 'ID',
            'order' => 'ASC',
        ]);
        $items = [];
        foreach ($query->posts as $post) {
            $content = (string) $post->post_content;
            $items[] = [
                'id' => (int) $post->ID,
                'type' => (string) $post->post_type,
                'status' => (string) $post->post_status,
                'title' => get_the_title($post),
                'slug' => (string) $post->post_name,
                'url' => get_permalink($post),
                'modified' => get_post_modified_time('c', true, $post),
                'content_hash' => (
                    new WPFixPilot_Change_Controller()
                )->current_state((int) $post->ID)['content_hash'],
            ];
        }

        return new WP_REST_Response([
            'status' => 'ok',
            'site_url' => get_site_url(),
            'count' => count($items),
            'items' => $items,
        ]);
    }

    public function current_content(
        WP_REST_Request $request
    ): WP_REST_Response|WP_Error {
        $result = (new WPFixPilot_Change_Controller())->current_state(
            (int) $request->get_param('id')
        );
        return is_wp_error($result) ? $result : new WP_REST_Response($result);
    }

    public function apply_change(
        WP_REST_Request $request
    ): WP_REST_Response|WP_Error {
        $result = (new WPFixPilot_Change_Controller())->apply(
            (int) $request->get_param('id'),
            (array) $request->get_json_params()
        );
        return is_wp_error($result) ? $result : new WP_REST_Response($result);
    }

    public function builders(): WP_REST_Response
    {
        return new WP_REST_Response(
            (new WPFixPilot_Page_Package_Controller())->builders()
        );
    }

    public function template_slots(
        WP_REST_Request $request
    ): WP_REST_Response|WP_Error {
        $result = (new WPFixPilot_Page_Package_Controller())->inspect(
            (int) $request->get_param('id'),
            sanitize_key((string) $request->get_param('builder'))
        );
        return is_wp_error($result) ? $result : new WP_REST_Response($result);
    }

    public function create_draft_page(
        WP_REST_Request $request
    ): WP_REST_Response|WP_Error {
        $result = (new WPFixPilot_Page_Package_Controller())->create_draft(
            (array) $request->get_json_params()
        );
        return is_wp_error($result) ? $result : new WP_REST_Response($result);
    }

    private function detect_seo_plugin(): ?string
    {
        if (defined('WPSEO_VERSION')) {
            return 'yoast';
        }
        if (defined('RANK_MATH_VERSION')) {
            return 'rank_math';
        }
        if (defined('AIOSEO_VERSION')) {
            return 'aioseo';
        }
        return null;
    }
}
