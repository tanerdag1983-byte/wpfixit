<?php

declare(strict_types=1);

require_once __DIR__ . '/../includes/seo-adapters/interface-seo-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-adapter-changes.php';
require_once __DIR__ . '/../includes/seo-adapters/class-yoast-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-rank-math-adapter.php';
require_once __DIR__ . '/../includes/seo-adapters/class-aioseo-adapter.php';

$adapters = [
    new WPFixPilot_Yoast_Adapter(),
    new WPFixPilot_Rank_Math_Adapter(),
    new WPFixPilot_AIOSEO_Adapter(),
];
$changeTypes = [
    'seo_title',
    'meta_description',
    'canonical',
    'noindex',
    'content',
    'internal_links',
    'redirect',
];

foreach ($adapters as $adapter) {
    foreach ($changeTypes as $changeType) {
        $changeSet = $adapter->build_change_set(
            $changeType,
            $changeType === 'noindex' ? true : 'new value'
        );
        assert($changeSet !== []);
    }
}

echo "change controller tests passed\n";
