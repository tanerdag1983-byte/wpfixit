<?php

declare(strict_types=1);

final class WPFixPilot_Rank_Math_Adapter implements WPFixPilot_SEO_Adapter
{
    public function build_change_set(string $changeType, mixed $value): array
    {
        $meta = [
            'seo_title' => 'rank_math_title',
            'meta_description' => 'rank_math_description',
            'focus_keyword' => 'rank_math_focus_keyword',
            'canonical' => 'rank_math_canonical_url',
            'noindex' => 'rank_math_robots',
        ];

        if ($changeType === 'noindex') {
            $value = (bool) $value ? ['noindex'] : ['index'];
        }
        return WPFixPilot_Adapter_Changes::build($meta, $changeType, $value);
    }
}
