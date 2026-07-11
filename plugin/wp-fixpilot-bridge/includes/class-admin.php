<?php

declare(strict_types=1);

final class WPFixPilot_Admin
{
    private WPFixPilot_Manual_Handoff_Controller $manualHandoffController;
    private Closure $outboundClientFactory;
    private Closure $draftJobControllerFactory;

    public function __construct(
        ?WPFixPilot_Manual_Handoff_Controller $manualHandoffController = null,
        ?Closure $outboundClientFactory = null,
        ?Closure $draftJobControllerFactory = null
    ) {
        $this->manualHandoffController = $manualHandoffController
            ?? new WPFixPilot_Manual_Handoff_Controller();
        $this->outboundClientFactory = $outboundClientFactory
            ?? fn (): object => $this->new_outbound_client();
        $this->draftJobControllerFactory = $draftJobControllerFactory
            ?? fn (): object => new WPFixPilot_Draft_Job_Controller(
                $this->new_outbound_client()
            );
    }

    public function register(): void
    {
        add_options_page(
            'WP FixPilot Bridge',
            'WP FixPilot',
            'manage_options',
            'wp-fixpilot',
            [$this, 'render_settings_page']
        );

        add_submenu_page(
            null,
            'WP FixPilot import',
            'WP FixPilot import',
            'edit_pages',
            'wp-fixpilot-import',
            [$this->manualHandoffController, 'render_import_page']
        );
    }

    public function register_action_handlers(): void
    {
        add_action('admin_post_wp_fixpilot_regenerate_secret', [$this, 'regenerate_secret']);
        add_action('admin_post_wp_fixpilot_redeem_handoff', [$this->manualHandoffController, 'handle_redeem']);
        add_action('admin_post_wp_fixpilot_confirm_import', [$this->manualHandoffController, 'handle_confirm_import']);
        add_action('admin_post_wp_fixpilot_save_outbound_connection', [$this, 'save_outbound_connection']);
        add_action('admin_post_wp_fixpilot_test_outbound_connection', [$this, 'test_outbound_connection']);
        add_action('admin_post_wp_fixpilot_fetch_draft_job', [$this, 'fetch_draft_job']);
    }

    public function register_cron_handlers(): void
    {
        add_filter('cron_schedules', [$this, 'cron_schedules']);
        add_action('wp_fixpilot_poll_draft_jobs', [$this, 'poll_draft_jobs']);
    }

    /** @param array<string, array<string, int|string>> $schedules */
    public function cron_schedules(array $schedules): array
    {
        $schedules['wp_fixpilot_five_minutes'] = [
            'interval' => 300,
            'display' => 'Iedere vijf minuten',
        ];
        return $schedules;
    }

    public function save_outbound_connection(): void
    {
        $this->require_capability('manage_options');
        check_admin_referer('wp_fixpilot_save_outbound_connection');
        $backendUrl = rtrim(esc_url_raw($this->posted('backend_base_url')), '/');
        $projectId = sanitize_text_field($this->posted('project_id'));
        $projectKey = sanitize_text_field($this->posted('project_key'));
        if (
            parse_url($backendUrl, PHP_URL_SCHEME) !== 'https'
            || $projectId === ''
            || ($projectKey === '' && get_option('wp_fixpilot_outbound_project_key', '') === '')
            || ($projectKey !== '' && !str_starts_with($projectKey, 'wpfx_'))
        ) {
            wp_die('Ongeldige uitgaande verbinding.');
        }
        update_option('wp_fixpilot_outbound_backend_url', $backendUrl, false);
        update_option('wp_fixpilot_outbound_project_id', $projectId, false);
        if ($projectKey !== '') {
            update_option('wp_fixpilot_outbound_project_key', $projectKey, false);
        }
        $this->redirect_settings('outbound_saved');
    }

    public function test_outbound_connection(): void
    {
        $this->require_capability('manage_options');
        check_admin_referer('wp_fixpilot_test_outbound_connection');
        try {
            $client = ($this->outboundClientFactory)();
            $result = $client->verify();
        } catch (Throwable $error) {
            $result = new WP_Error(
                'wp_fixpilot_outbound_not_configured',
                'De uitgaande WP FixPilot-verbinding is niet compleet.'
            );
        }
        $this->store_outbound_result(
            is_wp_error($result) ? $result : ['status' => 'connected']
        );
        $this->redirect_settings(is_wp_error($result) ? 'outbound_error' : 'outbound_connected');
    }

    public function fetch_draft_job(): void
    {
        $this->require_capability('edit_pages');
        check_admin_referer('wp_fixpilot_fetch_draft_job');
        $result = $this->poll_draft_jobs();
        $notice = is_wp_error($result)
            ? 'outbound_error'
            : ($result === null ? 'outbound_empty' : 'outbound_completed');
        $this->redirect_settings($notice);
    }

    /** @return array<string, mixed>|null|WP_Error */
    public function poll_draft_jobs(): array|null|WP_Error
    {
        try {
            $controller = ($this->draftJobControllerFactory)();
            $result = $controller->process_next();
        } catch (Throwable $error) {
            $result = new WP_Error(
                'wp_fixpilot_outbound_not_configured',
                'De uitgaande WP FixPilot-verbinding is niet compleet.'
            );
        }
        $this->store_outbound_result($result);
        return $result;
    }

    public function regenerate_secret(): void
    {
        if (!current_user_can('manage_options')) {
            wp_die('Geen toegang.');
        }
        check_admin_referer('wp_fixpilot_regenerate_secret');
        update_option('wp_fixpilot_secret', wp_generate_password(64, false, false), false);
        wp_safe_redirect(admin_url('options-general.php?page=wp-fixpilot&regenerated=1'));
        exit;
    }

    public function render_settings_page(): void
    {
        if (!current_user_can('manage_options')) {
            return;
        }
        $secret = (string) get_option('wp_fixpilot_secret', '');
        if ($secret === '') {
            $secret = wp_generate_password(64, false, false);
            update_option('wp_fixpilot_secret', $secret, false);
        }
        ?>
        <div class="wrap">
            <h1>WP FixPilot Bridge</h1>
            <?php if (isset($_GET['regenerated'])) : ?>
                <div class="notice notice-success"><p>Bridge secret vernieuwd.</p></div>
            <?php endif; ?>
            <p>
                Gebruik deze gegevens in WP FixPilot om deze WordPress-site veilig te koppelen.
            </p>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">WordPress URL</th>
                    <td><code><?php echo esc_html(get_site_url()); ?></code></td>
                </tr>
                <tr>
                    <th scope="row">Bridge secret</th>
                    <td>
                        <input
                            type="text"
                            readonly
                            class="large-text code"
                            value="<?php echo esc_attr($secret); ?>"
                            onclick="this.select();"
                        />
                        <p class="description">
                            Kopieer deze secret naar WP FixPilot. Deel deze secret niet openbaar.
                        </p>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Health endpoint</th>
                    <td>
                        <code><?php echo esc_html(rest_url('wpfixpilot/v1/health')); ?></code>
                    </td>
                </tr>
            </table>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <?php wp_nonce_field('wp_fixpilot_regenerate_secret'); ?>
                <input type="hidden" name="action" value="wp_fixpilot_regenerate_secret" />
                <?php submit_button('Nieuwe secret genereren', 'secondary'); ?>
            </form>
            <hr />
            <h2>Uitgaande verbinding</h2>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <?php wp_nonce_field('wp_fixpilot_save_outbound_connection'); ?>
                <input type="hidden" name="action" value="wp_fixpilot_save_outbound_connection" />
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row"><label for="wpfixpilot-backend-url">Backend URL</label></th>
                        <td><input id="wpfixpilot-backend-url" name="backend_base_url" type="url" class="regular-text" value="<?php echo esc_attr((string) get_option('wp_fixpilot_outbound_backend_url', '')); ?>" required /></td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="wpfixpilot-project-id">Project ID</label></th>
                        <td><input id="wpfixpilot-project-id" name="project_id" type="text" class="regular-text" value="<?php echo esc_attr((string) get_option('wp_fixpilot_outbound_project_id', '')); ?>" required /></td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="wpfixpilot-project-key">Projectkey</label></th>
                        <td><input id="wpfixpilot-project-key" name="project_key" type="password" class="regular-text" value="" autocomplete="new-password" /></td>
                    </tr>
                </table>
                <?php submit_button('Verbinding opslaan'); ?>
            </form>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <?php wp_nonce_field('wp_fixpilot_test_outbound_connection'); ?>
                <input type="hidden" name="action" value="wp_fixpilot_test_outbound_connection" />
                <?php submit_button('Verbinding testen', 'secondary'); ?>
            </form>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <?php wp_nonce_field('wp_fixpilot_fetch_draft_job'); ?>
                <input type="hidden" name="action" value="wp_fixpilot_fetch_draft_job" />
                <?php submit_button('Concepttaken ophalen', 'secondary'); ?>
            </form>
            <p><strong>Status:</strong> <?php echo esc_html((string) get_option('wp_fixpilot_outbound_last_status', 'niet verbonden')); ?></p>
            <p><strong>Laatste contact:</strong> <?php echo esc_html((string) get_option('wp_fixpilot_outbound_last_contact', '')); ?></p>
            <?php $lastError = (string) get_option('wp_fixpilot_outbound_last_error', ''); ?>
            <?php if ($lastError !== '') : ?>
                <div class="notice notice-error inline"><p><?php echo esc_html($lastError); ?></p></div>
            <?php endif; ?>
        </div>
        <?php
    }

    private function new_outbound_client(): WPFixPilot_Outbound_Client
    {
        $backendUrl = (string) get_option('wp_fixpilot_outbound_backend_url', '');
        $projectId = (string) get_option('wp_fixpilot_outbound_project_id', '');
        $projectKey = (string) get_option('wp_fixpilot_outbound_project_key', '');
        if ($backendUrl === '' || $projectId === '' || $projectKey === '') {
            throw new RuntimeException('Outbound connection is not configured');
        }
        return new WPFixPilot_Outbound_Client(
            $backendUrl,
            $projectId,
            $projectKey
        );
    }

    /** @param array<string, mixed>|null|WP_Error $result */
    private function store_outbound_result(array|null|WP_Error $result): void
    {
        update_option('wp_fixpilot_outbound_last_contact', gmdate('c'), false);
        if (is_wp_error($result)) {
            update_option('wp_fixpilot_outbound_last_status', 'error', false);
            update_option(
                'wp_fixpilot_outbound_last_error',
                substr($result->get_error_message(), 0, 500),
                false
            );
            return;
        }
        update_option('wp_fixpilot_outbound_last_error', '', false);
        update_option(
            'wp_fixpilot_outbound_last_status',
            $result === null ? 'empty' : (($result['status'] ?? '') === 'connected' ? 'connected' : 'completed'),
            false
        );
    }

    private function posted(string $key): string
    {
        return isset($_POST[$key]) ? (string) wp_unslash($_POST[$key]) : '';
    }

    private function require_capability(string $capability): void
    {
        if (!current_user_can($capability)) {
            wp_die('Geen toegang.');
        }
    }

    private function redirect_settings(string $notice): void
    {
        wp_safe_redirect(
            admin_url('options-general.php?page=wp-fixpilot&notice=' . $notice)
        );
        if (!defined('WPFIXPILOT_TESTING')) {
            exit;
        }
    }
}
