<?php

declare(strict_types=1);

final class WPFixPilot_Outbound_Client
{
    private string $backendBaseUrl;
    private string $projectId;
    private string $projectKey;
    private string $siteUrl;

    public function __construct(
        string $backendBaseUrl,
        string $projectId,
        string $projectKey,
        ?string $siteUrl = null
    ) {
        $this->backendBaseUrl = rtrim($backendBaseUrl, '/');
        $this->projectId = $projectId;
        $this->projectKey = $projectKey;
        $this->siteUrl = rtrim($siteUrl ?? get_site_url(), '/');
    }

    /** @return array<string, mixed>|WP_Error */
    public function verify(): array|WP_Error
    {
        $result = $this->request('POST', '/verify');
        if (is_wp_error($result)) {
            return $result;
        }
        return is_array($result) ? $result : new WP_Error(
            'wp_fixpilot_outbound_response_invalid',
            'WP FixPilot gaf een ongeldig verbindingsantwoord.'
        );
    }

    /** @return array<string, mixed>|null|WP_Error */
    public function claim(): array|null|WP_Error
    {
        return $this->request('POST', '/claim', [], [200, 204]);
    }

    /** @param array<string, mixed> $draft */
    public function complete(
        string $jobId,
        string $claimToken,
        array $draft
    ): true|WP_Error {
        $result = $this->request(
            'POST',
            '/' . rawurlencode($jobId) . '/complete',
            [
                'claim_token' => $claimToken,
                'wordpress_object_id' => (int) ($draft['wordpress_object_id'] ?? 0),
                'wordpress_edit_url' => isset($draft['edit_url'])
                    ? (string) $draft['edit_url']
                    : null,
            ]
        );
        return is_wp_error($result) ? $result : true;
    }

    public function fail(
        string $jobId,
        string $claimToken,
        string $errorCode,
        string $errorMessage
    ): true|WP_Error {
        $result = $this->request(
            'POST',
            '/' . rawurlencode($jobId) . '/fail',
            [
                'claim_token' => $claimToken,
                'error_code' => $errorCode,
                'error_message' => substr($errorMessage, 0, 500),
            ]
        );
        return is_wp_error($result) ? $result : true;
    }

    /**
     * @param array<string, mixed> $body
     * @param array<int, int> $acceptedStatuses
     * @return array<string, mixed>|null|WP_Error
     */
    private function request(
        string $method,
        string $suffix,
        array $body = [],
        array $acceptedStatuses = [200]
    ): array|null|WP_Error {
        $url = $this->backendBaseUrl
            . '/projects/' . rawurlencode($this->projectId)
            . '/wordpress-draft-jobs' . $suffix;
        $response = wp_remote_request($url, [
            'method' => $method,
            'timeout' => 30,
            'redirection' => 0,
            'headers' => [
                'Authorization' => 'Bearer ' . $this->projectKey,
                'X-WP-FixPilot-Site' => $this->siteUrl,
                'Content-Type' => 'application/json',
            ],
            'body' => wp_json_encode($body),
        ]);
        if (is_wp_error($response)) {
            return new WP_Error(
                'wp_fixpilot_outbound_unavailable',
                'WP FixPilot is tijdelijk niet bereikbaar.'
            );
        }
        $status = wp_remote_retrieve_response_code($response);
        if (!in_array($status, $acceptedStatuses, true)) {
            return new WP_Error(
                'wp_fixpilot_outbound_request_failed',
                'WP FixPilot kon de concepttaak niet verwerken.',
                ['status' => $status]
            );
        }
        if ($status === 204) {
            return null;
        }
        $decoded = json_decode(wp_remote_retrieve_body($response), true);
        if (!is_array($decoded)) {
            return new WP_Error(
                'wp_fixpilot_outbound_response_invalid',
                'WP FixPilot gaf een ongeldig antwoord.'
            );
        }
        return $decoded;
    }
}
