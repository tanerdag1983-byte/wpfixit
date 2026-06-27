<?php

declare(strict_types=1);

require_once __DIR__ . '/../includes/builder-adapters/interface-builder-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-gutenberg-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-elementor-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-bricks-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-wpbakery-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-acf-adapter.php';

$adapters = [
    new WPFixPilot_Gutenberg_Adapter(),
    new WPFixPilot_Elementor_Adapter(),
    new WPFixPilot_Bricks_Adapter(),
    new WPFixPilot_WPBakery_Adapter(),
    new WPFixPilot_ACF_Adapter(),
];

$keys = array_map(
    static fn (WPFixPilot_Builder_Adapter $adapter): string => $adapter->key(),
    $adapters
);

assert($keys === ['gutenberg', 'elementor', 'bricks', 'wpbakery', 'acf']);
assert(count(array_unique($keys)) === 5);

echo "page package adapter tests passed\n";
