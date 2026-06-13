<?php

declare(strict_types=1);

final class WPFixPilot_Adapter_Changes
{
    /**
     * @param array<string, string> $meta
     * @return array<string, mixed>
     */
    public static function build(
        array $meta,
        string $changeType,
        mixed $value
    ): array {
        if (isset($meta[$changeType])) {
            return [
                'meta' => [$meta[$changeType] => $value],
            ];
        }
        if (in_array($changeType, ['content', 'internal_links'], true)) {
            return ['post' => ['post_content' => (string) $value]];
        }
        if ($changeType === 'redirect') {
            return ['redirect' => (string) $value];
        }
        throw new InvalidArgumentException('Niet-ondersteund wijzigingstype.');
    }
}
