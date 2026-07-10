<?php

declare(strict_types=1);

final class WPFixPilot_Manual_Handoff_Controller
{
    private WPFixPilot_Import_Session_Store $store;

    private string $backendBaseUrl;

    private ?object $pagePackageController;

    private ?object $blueprintController;

    public function __construct(
        ?WPFixPilot_Import_Session_Store $store = null,
        ?string $backendBaseUrl = null,
        ?object $pagePackageController = null,
        ?object $blueprintController = null
    ) {
        $this->store = $store ?? new WPFixPilot_Import_Session_Store();
        $configuredBaseUrl = (string) get_option('wp_fixpilot_backend_base_url', '');
        $this->backendBaseUrl = rtrim(
            $backendBaseUrl ?? $configuredBaseUrl,
            '/'
        );
        $this->pagePackageController = $pagePackageController;
        $this->blueprintController = $blueprintController;
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

        $payload = [
            'code' => $code,
            'site_url' => get_site_url(),
            'wordpress_user_id' => $wordpressUserId,
        ];
        $response = $this->signed_backend_post(
            '/redeem',
            $payload
        );

        if (is_wp_error($response)) {
            return $response;
        }

        $status = wp_remote_retrieve_response_code($response);
        $body = wp_remote_retrieve_body($response);
        $payload = json_decode($body, true);

        if ($status < 200 || $status >= 300 || !is_array($payload)) {
            $message = 'De handoff-code kon niet worden gevalideerd.';
            if (is_array($payload)) {
                $detail = $payload['detail'] ?? $payload['message'] ?? null;
                if (is_string($detail) && $detail !== '') {
                    $message = $detail;
                } elseif (is_array($detail)) {
                    $formatted = $this->format_validation_detail($detail);
                    if ($formatted !== '') {
                        $message = $formatted;
                    }
                }
            }
            return new WP_Error(
                'wp_fixpilot_redeem_failed',
                $message,
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
        if (
            ($handoff['state'] ?? '') === 'completed'
            && !empty($handoff['wordpress_edit_url'])
            && !empty($handoff['wordpress_object_id'])
        ) {
            $this->store->update_payload(
                $sessionId,
                [
                    'handoff' => $handoff,
                    'package' => $package,
                    'proposal_version_id' => $proposalVersion,
                    'wordpress_user_id' => $wordpressUserId,
                    'completed_draft' => [
                        'wordpress_object_id' => (int) $handoff['wordpress_object_id'],
                        'edit_url' => (string) $handoff['wordpress_edit_url'],
                        'status' => 'draft',
                    ],
                ]
            );
        }

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

        $backend = esc_url_raw((string) ($_GET['backend'] ?? ''));
        if ($backend !== '') {
            update_option('wp_fixpilot_backend_base_url', untrailingslashit($backend), false);
        }

        $code = sanitize_text_field((string) ($_GET['code'] ?? ''));
        if ($code !== '' && !isset($_GET['session_id'])) {
            $result = $this->redeem_code($code, get_current_user_id());
            if (is_wp_error($result)) {
                $this->redirect_to_import_page([
                    'notice' => 'redeem_failed',
                    'message' => $result->get_error_message(),
                ]);
                return;
            }

            $this->redirect_to_import_page([
                'notice' => 'redeemed',
                'session_id' => (string) ($result['session_id'] ?? ''),
            ]);
            return;
        }

        $sessionId = sanitize_text_field((string) ($_GET['session_id'] ?? ''));
        $notice = sanitize_text_field((string) ($_GET['notice'] ?? ''));
        $noticeMessage = sanitize_text_field((string) ($_GET['message'] ?? ''));
        $session = $sessionId !== '' ? $this->store->get($sessionId) : null;
        $payload = is_array($session) ? (array) ($session['payload'] ?? []) : [];
        $summary = $this->summary_from_payload($payload);
        $completedDraft = is_array($payload['completed_draft'] ?? null)
            ? (array) $payload['completed_draft']
            : null;
        ?>
        <div class="wrap">
            <h1>WP FixPilot import</h1>
            <p>Haal eerst het goedgekeurde paginapakket op en maak daarna een WordPress-concept aan.</p>

            <?php if ($notice === 'redeemed') : ?>
                <div class="notice notice-success"><p>Het paginapakket is opgehaald en klaar om te importeren.</p></div>
            <?php elseif ($notice === 'imported') : ?>
                <div class="notice notice-success"><p>Het WordPress-concept is aangemaakt.</p></div>
            <?php elseif ($notice === 'redeem_failed') : ?>
                <div class="notice notice-error">
                    <p>
                        <?php echo esc_html($noticeMessage !== '' ? $noticeMessage : 'De handoff-code kon niet worden gevalideerd.'); ?>
                    </p>
                </div>
            <?php elseif ($notice === 'import_failed') : ?>
                <div class="notice notice-error">
                    <p>
                        <?php echo esc_html($noticeMessage !== '' ? $noticeMessage : 'Het WordPress-concept kon niet worden aangemaakt.'); ?>
                    </p>
                </div>
            <?php endif; ?>

            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <?php wp_nonce_field('wp_fixpilot_redeem_handoff'); ?>
                <input type="hidden" name="action" value="wp_fixpilot_redeem_handoff" />
                <input type="hidden" name="wordpress_user_id" value="<?php echo esc_attr((string) get_current_user_id()); ?>" />
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row"><label for="wp-fixpilot-code">Handoff-code</label></th>
                        <td>
                            <input id="wp-fixpilot-code" name="code" type="text" class="regular-text code" value="" />
                            <p class="description">Plak hier de code uit WP FixPilot om het paginapakket op te halen.</p>
                        </td>
                    </tr>
                </table>
                <?php submit_button('Paginapakket ophalen', 'secondary', 'submit', false); ?>
            </form>

            <?php if ($sessionId !== '' && is_array($session)) : ?>
                <hr />
                <h2>Klaar om te importeren</h2>
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row">Paginatitel</th>
                        <td><strong><?php echo esc_html($summary['title']); ?></strong></td>
                    </tr>
                    <tr>
                        <th scope="row">Voorstelversie</th>
                        <td>#<?php echo esc_html((string) $summary['proposal_version']); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Status</th>
                        <td><?php echo $summary['draft_only'] ? 'Alleen concept' : 'Onbekend'; ?></td>
                    </tr>
                </table>

                <?php if ($completedDraft && !empty($completedDraft['edit_url'])) : ?>
                    <p>
                        <a class="button button-primary" href="<?php echo esc_url((string) $completedDraft['edit_url']); ?>">
                            Concept openen in WordPress
                        </a>
                    </p>
                <?php else : ?>
                    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <?php wp_nonce_field('wp_fixpilot_confirm_import'); ?>
                        <input type="hidden" name="action" value="wp_fixpilot_confirm_import" />
                        <input type="hidden" name="session_id" value="<?php echo esc_attr($sessionId); ?>" />
                        <input type="hidden" name="wordpress_user_id" value="<?php echo esc_attr((string) get_current_user_id()); ?>" />
                        <?php submit_button('WordPress-concept aanmaken'); ?>
                    </form>
                <?php endif; ?>
            <?php endif; ?>
        </div>
        <?php
    }

    public function handle_redeem(): void
    {
        if (!current_user_can('edit_pages')) {
            return;
        }
        check_admin_referer('wp_fixpilot_redeem_handoff');
        $code = sanitize_text_field(wp_unslash((string) ($_POST['code'] ?? '')));
        $userId = (int) ($_POST['wordpress_user_id'] ?? 0);
        $result = $this->redeem_code($code, $userId);

        if (is_wp_error($result)) {
            $this->redirect_to_import_page([
                'notice' => 'redeem_failed',
                'message' => $result->get_error_message(),
            ]);
            return;
        }

        $this->redirect_to_import_page([
            'notice' => 'redeemed',
            'session_id' => (string) ($result['session_id'] ?? ''),
        ]);
    }

    public function handle_confirm_import(): void
    {
        if (!current_user_can('edit_pages')) {
            return;
        }
        check_admin_referer('wp_fixpilot_confirm_import');
        $sessionId = sanitize_text_field(wp_unslash((string) ($_POST['session_id'] ?? '')));
        $userId = (int) ($_POST['wordpress_user_id'] ?? 0);
        try {
            $result = $this->confirm_import($sessionId, $userId);
        } catch (Throwable $error) {
            $this->redirect_to_import_page([
                'notice' => 'import_failed',
                'session_id' => $sessionId,
                'message' => $error->getMessage(),
            ]);
            return;
        }

        if (is_wp_error($result)) {
            $this->redirect_to_import_page([
                'notice' => 'import_failed',
                'session_id' => $sessionId,
                'message' => $result->get_error_message(),
            ]);
            return;
        }

        $this->redirect_to_import_page([
            'notice' => 'imported',
            'session_id' => $sessionId,
        ]);
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
        $draft = $this->create_draft_from_payload($package);
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

        $response = $this->signed_backend_post(
            '/' . rawurlencode($handoffId) . '/complete',
            $draft
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

    private function blueprint_controller(): object
    {
        if ($this->blueprintController === null) {
            $this->blueprintController = new WPFixPilot_Blueprint_Controller([
                new WPFixPilot_ACF_Blueprint_Adapter(),
                new WPFixPilot_Elementor_Adapter(),
                new WPFixPilot_WPBakery_Adapter(),
                new WPFixPilot_Bricks_Adapter(),
                new WPFixPilot_Gutenberg_Adapter(),
            ]);
        }

        return $this->blueprintController;
    }

    private function create_draft_from_payload(array $package): array|WP_Error
    {
        $blueprint = (array) ($package['blueprint'] ?? []);
        $generatedPackage = (array) ($package['package'] ?? []);
        $schema = (array) (($package['config_snapshot'] ?? [])['content_schema'] ?? []);
        $wordpressBlueprintId = (int) ($blueprint['wordpress_blueprint_id'] ?? 0);
        $expectedVersion = (int) ($blueprint['version'] ?? 0);
        $expectedStructureHash = (string) ($blueprint['structure_hash'] ?? '');

        if (
            $wordpressBlueprintId > 0
            && $expectedVersion > 0
            && $expectedStructureHash !== ''
            && isset($generatedPackage['replacements'])
        ) {
            return $this->blueprint_controller()->create_draft(
                $wordpressBlueprintId,
                [
                    'expected_version' => $expectedVersion,
                    'expected_structure_hash' => $expectedStructureHash,
                    'idempotency_key' => (string) ($package['proposal_version_id'] ?? ''),
                    'replacements' => $this->blueprint_replacements($generatedPackage),
                    'approved_urls' => $this->approved_urls($generatedPackage, $schema),
                    'seo' => [
                        'title' => (string) ($generatedPackage['seo_title'] ?? ''),
                        'description' => (string) ($generatedPackage['meta_description'] ?? ''),
                        'keyword' => (string) ($generatedPackage['focus_keyword'] ?? ''),
                    ],
                ]
            );
        }

        return $this->page_package_controller()->create_draft([
            'template_id' => $package['template_id'] ?? null,
            'expected_template_hash' => $package['expected_template_hash'] ?? '',
            'builder' => $package['builder'] ?? '',
            'mapping' => (array) ($package['mapping'] ?? []),
            'seo_plugin' => $package['seo_plugin'] ?? '',
            'idempotency_key' => $package['idempotency_key'] ?? '',
            'proposal_version_id' => $package['proposal_version_id'] ?? '',
            'snapshot_hash' => $package['snapshot_hash'] ?? '',
            'package' => $generatedPackage,
        ]);
    }

    /** @return array<string, string> */
    private function blueprint_replacements(array $generatedPackage): array
    {
        $mapped = [];
        foreach ((array) ($generatedPackage['replacements'] ?? []) as $replacement) {
            if (!is_array($replacement)) {
                continue;
            }
            $fieldId = sanitize_text_field((string) ($replacement['field_id'] ?? ''));
            if ($fieldId === '') {
                continue;
            }
            $mapped[$fieldId] = (string) ($replacement['value'] ?? '');
        }

        return $mapped;
    }

    /** @return array<int, string> */
    private function approved_urls(array $generatedPackage, array $schema): array
    {
        $approved = [];
        foreach ((array) ($generatedPackage['internal_links'] ?? []) as $link) {
            if (!is_array($link)) {
                continue;
            }
            $url = (string) ($link['url'] ?? '');
            if ($url !== '') {
                $approved[$url] = $url;
            }
        }

        $urlFieldIds = [];
        foreach ((array) ($schema['blocks'] ?? []) as $block) {
            if (!is_array($block)) {
                continue;
            }
            foreach ((array) ($block['fields'] ?? []) as $field) {
                if (
                    is_array($field)
                    && ($field['value_type'] ?? '') === 'url'
                    && is_string($field['id'] ?? null)
                ) {
                    $urlFieldIds[(string) $field['id']] = true;
                }
            }
        }

        foreach ((array) ($generatedPackage['replacements'] ?? []) as $replacement) {
            if (!is_array($replacement)) {
                continue;
            }
            $fieldId = (string) ($replacement['field_id'] ?? '');
            $value = (string) ($replacement['value'] ?? '');
            if ($value !== '' && isset($urlFieldIds[$fieldId])) {
                $approved[$value] = $value;
            }
        }

        return array_values($approved);
    }

    /** @return array{proposal_version:int,draft_only:bool,title:string} */
    private function summary_from_payload(array $payload): array
    {
        $package = (array) ($payload['package'] ?? []);
        $proposalVersion = (string) ($package['proposal_version_id'] ?? ($payload['proposal_version_id'] ?? ''));

        return [
            'proposal_version' => (int) preg_replace('/\D+/', '', $proposalVersion),
            'draft_only' => true,
            'title' => (string) (($package['package'] ?? [])['title'] ?? ''),
        ];
    }

    /** @return array{url:string,route:string} */
    private function backend_endpoint(string $suffix = ''): array
    {
        $normalizedSuffix = $suffix === '' ? '' : '/' . ltrim($suffix, '/');
        $basePath = (string) parse_url($this->backendBaseUrl, PHP_URL_PATH);
        $routeBase = rtrim($basePath, '/');
        if (str_starts_with($routeBase, '/api/')) {
            $routeBase = substr($routeBase, 4);
        } elseif ($routeBase === '/api') {
            $routeBase = '';
        }
        $route = $routeBase . $normalizedSuffix;

        return [
            'url' => $this->backendBaseUrl . $normalizedSuffix,
            'route' => $route,
        ];
    }

    private function signed_backend_post(string $suffix, array $payload): array|WP_Error
    {
        $endpoint = $this->backend_endpoint($suffix);
        $body = json_encode(
            $payload,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
        if (!is_string($body)) {
            return new WP_Error(
                'wp_fixpilot_encode_failed',
                'WP FixPilot verzoek kon niet worden opgebouwd.',
                ['status' => 500]
            );
        }
        $timestamp = (string) time();
        $nonce = wp_generate_password(20, false, false);
        $secret = (string) get_option('wp_fixpilot_secret', '');

        return wp_remote_post(
            $endpoint['url'],
            [
                'headers' => [
                    'Content-Type' => 'application/json',
                    'x-wp-fixpilot-timestamp' => $timestamp,
                    'x-wp-fixpilot-nonce' => $nonce,
                    'x-wp-fixpilot-signature' => WPFixPilot_Auth::sign(
                        $secret,
                        'POST',
                        $endpoint['route'],
                        $timestamp,
                        $nonce,
                        $body
                    ),
                ],
                'body' => $body,
                'timeout' => 30,
            ]
        );
    }

    private function format_validation_detail(array $detail): string
    {
        $messages = [];
        foreach ($detail as $item) {
            if (!is_array($item)) {
                continue;
            }
            $message = $item['msg'] ?? $item['message'] ?? '';
            if (!is_string($message) || $message === '') {
                continue;
            }
            $location = '';
            if (isset($item['loc']) && is_array($item['loc'])) {
                $parts = array_values(array_filter(
                    $item['loc'],
                    static fn (mixed $part): bool => is_string($part) || is_int($part)
                ));
                $location = implode('.', array_map('strval', $parts));
            }
            $messages[] = $location !== '' ? $location . ': ' . $message : $message;
        }

        return implode('; ', $messages);
    }

    private function redirect_to_import_page(array $params): void
    {
        $query = http_build_query(array_filter(
            array_merge(['page' => 'wp-fixpilot-import'], $params),
            static fn (mixed $value): bool => $value !== ''
        ));
        wp_safe_redirect(admin_url('admin.php?' . $query));
        if (!defined('WPFIXPILOT_TESTING')) {
            exit;
        }
    }
}
