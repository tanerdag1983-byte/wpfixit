<?php

declare(strict_types=1);

final class WPFixPilot_Draft_Job_Controller
{
    private const CONTRACT_VERSION = 'wordpress-draft-job-v1';

    private object $client;
    private object $blueprintController;

    public function __construct(
        object $client,
        ?object $blueprintController = null
    ) {
        $this->client = $client;
        $this->blueprintController = $blueprintController
            ?? new WPFixPilot_Blueprint_Controller();
    }

    /** @return array<string, mixed>|null|WP_Error */
    public function process_next(): array|null|WP_Error
    {
        $claimed = $this->client->claim();
        if ($claimed === null || is_wp_error($claimed)) {
            return $claimed;
        }
        $job = $claimed['job'] ?? null;
        $claimToken = (string) ($claimed['claim_token'] ?? '');
        if (!is_array($job) || $claimToken === '') {
            return new WP_Error(
                'wp_fixpilot_job_invalid',
                'De ontvangen concepttaak is ongeldig.'
            );
        }

        $result = $this->process_payload($job);
        if (is_wp_error($result)) {
            $failure = $this->client->fail(
                (string) ($job['id'] ?? ''),
                $claimToken,
                $this->backend_error_code($result),
                $result->get_error_message()
            );
            return is_wp_error($failure) ? $failure : $result;
        }
        if (
            ($result['status'] ?? '') !== 'draft'
            || (int) ($result['wordpress_object_id'] ?? 0) < 1
        ) {
            $error = new WP_Error(
                'wp_fixpilot_draft_not_persisted',
                'WordPress kon het concept niet blijvend opslaan.'
            );
            $failure = $this->client->fail(
                (string) ($job['id'] ?? ''),
                $claimToken,
                'draft_not_persisted',
                $error->get_error_message()
            );
            return is_wp_error($failure) ? $failure : $error;
        }

        $completed = $this->client->complete(
            (string) ($job['id'] ?? ''),
            $claimToken,
            $result
        );
        return is_wp_error($completed) ? $completed : $result;
    }

    /** @param array<string, mixed> $job */
    public function process_payload(array $job): array|WP_Error
    {
        if (($job['contract_version'] ?? '') !== self::CONTRACT_VERSION) {
            return new WP_Error(
                'wp_fixpilot_unsupported_contract',
                'Deze concepttaak gebruikt een onbekende contractversie.'
            );
        }
        $payload = $job['payload'] ?? null;
        if (!is_array($payload) || !$this->valid_payload($payload)) {
            return new WP_Error(
                'wp_fixpilot_job_invalid',
                'De ontvangen concepttaak is niet compleet.'
            );
        }
        return $this->blueprintController->create_draft(
            (int) $payload['wordpress_blueprint_id'],
            [
                'expected_version' => (int) $payload['expected_version'],
                'expected_structure_hash' => (string) $payload['expected_structure_hash'],
                'idempotency_key' => (string) $payload['idempotency_key'],
                'replacements' => (array) $payload['replacements'],
                'approved_urls' => array_values((array) $payload['approved_urls']),
                'seo' => (array) $payload['seo'],
            ]
        );
    }

    /** @param array<string, mixed> $payload */
    private function valid_payload(array $payload): bool
    {
        $required = [
            'proposal_version_id',
            'wordpress_blueprint_id',
            'expected_version',
            'expected_structure_hash',
            'idempotency_key',
            'replacements',
            'approved_urls',
            'seo',
        ];
        foreach ($required as $key) {
            if (!array_key_exists($key, $payload)) {
                return false;
            }
        }
        return (int) $payload['wordpress_blueprint_id'] > 0
            && (int) $payload['expected_version'] > 0
            && (string) $payload['expected_structure_hash'] !== ''
            && (string) $payload['proposal_version_id'] !== ''
            && hash_equals(
                (string) $payload['proposal_version_id'],
                (string) $payload['idempotency_key']
            )
            && is_array($payload['replacements'])
            && is_array($payload['approved_urls'])
            && is_array($payload['seo']);
    }

    private function backend_error_code(WP_Error $error): string
    {
        return match ($error->get_error_code()) {
            'wp_fixpilot_unsupported_contract' => 'unsupported_contract',
            'wp_fixpilot_blueprint_conflict' => 'blueprint_drift',
            'wp_fixpilot_blueprint_field_unknown' => 'unknown_field',
            'wp_fixpilot_blueprint_url_not_approved' => 'url_not_approved',
            default => 'wordpress_error',
        };
    }
}
