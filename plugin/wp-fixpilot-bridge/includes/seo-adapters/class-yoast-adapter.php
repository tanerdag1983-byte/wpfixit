<?php

declare(strict_types=1);

final class WPFixPilot_Yoast_Adapter implements WPFixPilot_SEO_Adapter
{
    public function build_change_set(string $changeType, mixed $value): array
    {
        $meta = [
            'seo_title' => '_yoast_wpseo_title',
            'meta_description' => '_yoast_wpseo_metadesc',
            'focus_keyword' => '_yoast_wpseo_focuskw',
            'canonical' => '_yoast_wpseo_canonical',
            'noindex' => '_yoast_wpseo_meta-robots-noindex',
        ];

        if ($changeType === 'noindex') {
            $value = (bool) $value ? '1' : '2';
        }
        return WPFixPilot_Adapter_Changes::build($meta, $changeType, $value);
    }
}
