<?php

declare(strict_types=1);

final class WPFixPilot_AIOSEO_Adapter implements WPFixPilot_SEO_Adapter
{
    public function build_change_set(string $changeType, mixed $value): array
    {
        if ($changeType === 'focus_keyword') {
            return [
                'meta' => [
                    '_aioseo_keyphrases' => wp_json_encode([
                        'focus' => [
                            'keyphrase' => (string) $value,
                            'score' => 0,
                        ],
                    ]),
                ],
            ];
        }
        $meta = [
            'seo_title' => '_aioseo_title',
            'meta_description' => '_aioseo_description',
            'canonical' => '_aioseo_canonical_url',
            'noindex' => '_aioseo_robots_noindex',
        ];

        return WPFixPilot_Adapter_Changes::build($meta, $changeType, $value);
    }
}
