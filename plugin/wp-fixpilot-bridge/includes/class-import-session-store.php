<?php

declare(strict_types=1);

final class WPFixPilot_Import_Session_Store
{
    private const PREFIX = 'wp_fixpilot_import_';
    private const TTL = 600;

    public function create(string $handoffId, array $payload): string
    {
        $sessionId = wp_generate_password(20, false, false);
        set_transient(
            self::PREFIX . $sessionId,
            [
                'handoff_id' => $handoffId,
                'payload' => $payload,
                'created_at' => time(),
            ],
            self::TTL
        );

        return $sessionId;
    }

    public function get(string $sessionId): ?array
    {
        $payload = get_transient(self::PREFIX . $sessionId);
        return is_array($payload) ? $payload : null;
    }

    public function delete(string $sessionId): void
    {
        delete_transient(self::PREFIX . $sessionId);
    }
}
