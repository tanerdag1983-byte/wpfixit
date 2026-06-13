<?php

declare(strict_types=1);

interface WPFixPilot_SEO_Adapter
{
    /** @return array<string, mixed> */
    public function build_change_set(string $changeType, mixed $value): array;
}
