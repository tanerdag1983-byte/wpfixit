<?php

declare(strict_types=1);

if (!interface_exists('WPFixPilot_Builder_Adapter', false)) {
    require_once __DIR__ . '/interface-builder-adapter.php';
}

if (!class_exists('WPFixPilot_ACF_Adapter', false)) {
    require_once __DIR__ . '/class-acf-adapter.php';
}

if (!class_exists('WPFixPilot_ACF_Blueprint_Adapter', false)) {
    class_alias('WPFixPilot_ACF_Adapter', 'WPFixPilot_ACF_Blueprint_Adapter');
}
