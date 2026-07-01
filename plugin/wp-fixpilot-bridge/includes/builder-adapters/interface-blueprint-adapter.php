<?php

declare(strict_types=1);

interface WPFixPilot_Blueprint_Adapter
{
    public function key(): string;

    public function is_active(): bool;

    public function uses_page(int $postId): bool;

    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array;

    /** @return array<string, mixed>|WP_Error */
    public function schema(int $postId): array|WP_Error;

    public function structure_hash(int $postId): string;

    /**
     * @param array<string, mixed> $schema
     * @param array<string, string> $replacements
     */
    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error;
}

if (!function_exists('wpfixpilot_field_id')) {
    function wpfixpilot_field_id(string $builder, string $path): string
    {
        return $builder . '-' . substr(hash('sha256', $path), 0, 20);
    }
}
