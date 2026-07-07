<?php

declare(strict_types=1);

final class WPFixPilot_Manual_Handoff_Controller
{
    private WPFixPilot_Import_Session_Store $store;

    private string $backendBaseUrl;

    private ?object $pagePackageController;

    public function __construct(
        ?WPFixPilot_Import_Session_Store $store = null,
        ?string $backendBaseUrl = null,
        ?object $pagePackageController = null
    ) {
        $this->store = $store ?? new WPFixPilot_Import_Session_Store();
        $configuredBaseUrl = (string) get_option('wp_fixpilot_backend_base_url', '');
        $this->backendBaseUrl = rtrim(
            $backendBaseUrl ?? $configuredBaseUrl,
            '/'
        );
        $this->pagePackageController = $pagePackageController;
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

    public function confirm_import(string $sessionId, int $wordpressUserId): array|WP_Error
    {
        $session = $this->store->get($sessionId);
        if (!is_array($session)) {
            return new WP_Error(
                'wp_fixpilot_import_session_missing',
                'De importsessie is verlopen.',
                ['status' => 410]
            );
        }

        $payload = (array) ($session['payload'] ?? []);
        if ((int) ($payload['wordpress_user_id'] ?? 0) !== $wordpressUserId) {
            return new WP_Error(
                'wp_fixpilot_import_forbidden',
                'Deze importsessie hoort bij een andere WordPress-gebruiker.',
                ['status' => 403]
            );
        }

        $completedDraft = $payload['completed_draft'] ?? null;
        if (is_array($completedDraft)) {
            return $completedDraft;
        }

        $package = (array) ($payload['package'] ?? []);
        $draft = $this->page_package_controller()->create_draft([
            'template_id' => $package['template_id'] ?? null,
            'expected_template_hash' => $package['expected_template_hash'] ?? '',
            'builder' => $package['builder'] ?? '',
            'mapping' => (array) ($package['mapping'] ?? []),
            'seo_plugin' => $package['seo_plugin'] ?? '',
            'idempotency_key' => $package['idempotency_key'] ?? '',
            'proposal_version_id' => $package['proposal_version_id'] ?? '',
            'snapshot_hash' => $package['snapshot_hash'] ?? '',
            'package' => (array) ($package['package'] ?? []),
        ]);
        if (is_wp_error($draft)) {
            return $draft;
        }

        $completion = $this->report_completion(
            (string) ($payload['handoff']['project_id'] ?? ''),
            (string) ($session['handoff_id'] ?? ''),
            [
                'wordpress_object_id' => (int) ($draft['wordpress_object_id'] ?? 0),
                'edit_url' => (string) ($draft['edit_url'] ?? ''),
            ]
        );
        if (is_wp_error($completion)) {
            return $completion;
        }

        $payload['completed_draft'] = $draft;
        $this->store->update_payload($sessionId, $payload);

        return $draft;
    }

    private function report_completion(
        string $projectId,
        string $handoffId,
        array $draft
    ): true|WP_Error {
        if ($this->backendBaseUrl === '' || $projectId === '' || $handoffId === '') {
            return new WP_Error(
                'wp_fixpilot_backend_missing',
                'WP FixPilot backend URL ontbreekt.',
                ['status' => 500]
            );
        }

        $route = sprintf(
            '/projects/%s/page-proposals/handoffs/%s/complete',
            rawurlencode($projectId),
            rawurlencode($handoffId)
        );
        $body = wp_json_encode($draft);
        $timestamp = (string) time();
        $nonce = wp_generate_password(20, false, false);
        $secret = (string) get_option('wp_fixpilot_secret', '');

        $response = wp_remote_post(
            $this->backendBaseUrl . $route,
            [
                'headers' => [
                    'Content-Type' => 'application/json',
                    'x-wp-fixpilot-timestamp' => $timestamp,
                    'x-wp-fixpilot-nonce' => $nonce,
                    'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
                        $secret,
                        'POST',
                        $route,
                        $timestamp,
                        $nonce,
                        $body
                    ),
                ],
                'body' => $body,
                'timeout' => 30,
            ]
        );

        if (is_wp_error($response)) {
            return $response;
        }

        $status = wp_remote_retrieve_response_code($response);
        if ($status < 200 || $status >= 300) {
            return new WP_Error(
                'wp_fixpilot_complete_failed',
                'De draft-import kon niet worden afgerond.',
                ['status' => $status ?: 502]
            );
        }

        return true;
    }

    private function page_package_controller(): object
    {
        if ($this->pagePackageController === null) {
            $this->pagePackageController = new WPFixPilot_Page_Package_Controller();
        }

        return $this->pagePackageController;
    }
}
