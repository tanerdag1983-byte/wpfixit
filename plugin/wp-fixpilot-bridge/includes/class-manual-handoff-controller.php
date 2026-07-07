<?php

declare(strict_types=1);

final class WPFixPilot_Manual_Handoff_Controller
{
    private WPFixPilot_Import_Session_Store $store;

    private string $backendBaseUrl;

    public function __construct(
        ?WPFixPilot_Import_Session_Store $store = null,
        ?string $backendBaseUrl = null
    ) {
        $this->store = $store ?? new WPFixPilot_Import_Session_Store();
        $configuredBaseUrl = (string) get_option('wp_fixpilot_backend_base_url', '');
        $this->backendBaseUrl = rtrim(
            $backendBaseUrl ?? $configuredBaseUrl,
            '/'
        );
    }

    public function redeem_code(string $code, int $wordpressUserId): array|WP_Error
    {
        if ($this->backendBaseUrl === '') {
            return new WP_Error(
                'wp_fixpilot_backend_missing',
                'WP FixPilot backend URL ontbreekt.',
                ['status' => 500]
            );
        }

        $response = wp_remote_post(
            $this->backendBaseUrl . '/redeem',
            [
                'headers' => ['Content-Type' => 'application/json'],
                'body' => json_encode(
                    [
                        'code' => $code,
                        'site_url' => get_site_url(),
                        'wordpress_user_id' => $wordpressUserId,
                    ],
                    JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
                ),
                'timeout' => 30,
            ]
        );

        if (is_wp_error($response)) {
            return $response;
        }

        $status = wp_remote_retrieve_response_code($response);
        $body = wp_remote_retrieve_body($response);
        $payload = json_decode($body, true);

        if ($status < 200 || $status >= 300 || !is_array($payload)) {
            return new WP_Error(
                'wp_fixpilot_redeem_failed',
                'De handoff-code kon niet worden gevalideerd.',
                ['status' => $status ?: 502]
            );
        }

        $handoff = (array) ($payload['handoff'] ?? []);
        $package = (array) ($payload['package'] ?? []);
        $proposalVersion = (string) ($package['proposal_version_id'] ?? '');
        $sessionId = $this->store->create(
            (string) ($handoff['id'] ?? ''),
            [
                'handoff' => $handoff,
                'package' => $package,
                'proposal_version_id' => $proposalVersion,
                'wordpress_user_id' => $wordpressUserId,
            ]
        );

        $GLOBALS['wpfixpilot_browser_history_fragment_cleared'] = true;

        return [
            'session_id' => $sessionId,
            'handoff' => $handoff,
            'package' => $package,
            'summary' => [
                'proposal_version' => (int) preg_replace('/\D+/', '', $proposalVersion),
                'draft_only' => true,
                'title' => (string) (($package['package'] ?? [])['title'] ?? ''),
            ],
        ];
    }

    public function render_import_page(): void
    {
        if (!current_user_can('edit_pages')) {
            return;
        }
        echo '<div class="wrap"><h1>WP FixPilot import</h1></div>';
    }

    public function handle_redeem(): void
    {
        if (!current_user_can('edit_pages')) {
            return;
        }
        $code = sanitize_text_field(wp_unslash((string) ($_POST['code'] ?? '')));
        $userId = (int) ($_POST['wordpress_user_id'] ?? 0);
        $this->redeem_code($code, $userId);
    }

    public function handle_confirm_import(): void
    {
        if (!current_user_can('edit_pages')) {
            return;
        }
    }
}
