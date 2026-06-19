<?php

declare(strict_types=1);

final class WPFixPilot_Admin
{
    public function register(): void
    {
        add_options_page(
            'WP FixPilot Bridge',
            'WP FixPilot',
            'manage_options',
            'wp-fixpilot',
            [$this, 'render_settings_page']
        );

        add_action('admin_post_wp_fixpilot_regenerate_secret', [$this, 'regenerate_secret']);
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
        </div>
        <?php
    }
}
