<?php

declare(strict_types=1);

require_once __DIR__ . '/blueprint-test.php';

function test_snapshot_post_type_is_private(): void
{
    $store = new WPFixPilot_Template_Snapshot_Store();
    $store->register();
    $object = get_post_type_object(WPFixPilot_Template_Snapshot_Store::POST_TYPE);

    assert($object instanceof WP_Post_Type);
    assert($object->public === false);
    assert($object->publicly_queryable === false);
    assert($object->show_ui === false);
    assert($object->exclude_from_search === true);
}

function blueprint_controller(): WPFixPilot_Blueprint_Controller
{
    return new WPFixPilot_Blueprint_Controller([
        new Test_Blueprint_Adapter([41]),
    ]);
}

function test_capture_creates_snapshot_without_mutating_source(): void
{
    seed_source_page(41);
    $sourceBefore = clone get_post(41);
    $result = blueprint_controller()->capture([
        'source_page_id' => 41,
        'name' => 'Dienstpagina',
        'page_type' => 'service',
        'version' => 1,
    ]);

    assert(!is_wp_error($result));
    assert($result['wordpress_snapshot_id'] === $result['wordpress_blueprint_id']);
    assert($result['snapshot_version'] === 1);
    assert($result['schema_version'] === 'snapshot-text-v1');
    assert(get_post($result['wordpress_snapshot_id'])->post_type === 'wpfixpilot_snapshot');
    assert(get_post($result['wordpress_snapshot_id'])->post_status === 'private');
    assert((new WPFixPilot_Template_Snapshot_Store())->assert_snapshot(
        $result['wordpress_snapshot_id']
    ) instanceof WP_Post);
    assert(is_wp_error((new WPFixPilot_Template_Snapshot_Store())->assert_snapshot(41)));
    assert(get_post(41) == $sourceBefore);
}

test_snapshot_post_type_is_private();
test_capture_creates_snapshot_without_mutating_source();

echo "template snapshot tests passed\n";
