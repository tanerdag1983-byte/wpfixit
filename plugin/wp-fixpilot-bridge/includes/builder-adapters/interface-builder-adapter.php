<?php

declare(strict_types=1);

interface WPFixPilot_Builder_Adapter
{
    public function key(): string;

    public function is_active(): bool;

    /** @return array<int, array{path: string, label: string, value_type: string}> */
    public function inspect(int $postId): array;

    public function template_hash(int $postId): string;
}
