<?php

declare(strict_types=1);

require __DIR__ . '/blueprint-test.php';

$jobController = new WPFixPilot_Draft_Job_Controller(new stdClass(), $controller);
$currentSnapshot = $controller->read(200);
assert(!is_wp_error($currentSnapshot));
$sourcePostId = (int) $currentSnapshot['source_page_id'];
$sourcePost = get_post($sourcePostId);
assert($sourcePost instanceof WP_Post);
$sourcePostBefore = serialize(get_object_vars($sourcePost));
$sourceContentBefore = $sourcePost->post_content;
$sourceMetaBefore = serialize($GLOBALS['wpfixpilot_meta'][$sourcePostId] ?? []);
$snapshotJob = [
    'contract_version' => 'wordpress-snapshot-draft-job-v1',
    'payload' => [
        'proposal_version_id' => 'snapshot-proposal-200',
        'snapshot_id' => 200,
        'snapshot_version' => 1,
        'snapshot_structure_hash' => $currentSnapshot['structure_hash'],
        'schema_version' => 'snapshot-text-v1',
        'idempotency_key' => 'snapshot-proposal-200',
        'text_replacements' => array_merge(valid_replacements(), [
            'document:title' => 'Snapshotgestuurde titel',
            'document:slug' => 'snapshotgestuurde-titel',
            'seo:title' => 'Snapshot SEO titel',
            'seo:meta_description' => 'Snapshot SEO omschrijving',
            'seo:focus_keyword' => 'snapshot zoekwoord',
        ]),
        'approved_urls' => [],
    ],
];

$result = $jobController->process_payload($snapshotJob);
assert(
    !is_wp_error($result),
    is_wp_error($result) ? $result->code . ': ' . $result->message : ''
);
$draft = get_post((int) $result['wordpress_object_id']);
assert($draft instanceof WP_Post);
assert($draft->post_type === 'page');
assert($draft->post_status === 'draft');
assert($draft->post_title === 'Snapshotgestuurde titel');
$sourcePostAfter = get_post($sourcePostId);
assert($sourcePostAfter instanceof WP_Post);
assert(serialize(get_object_vars($sourcePostAfter)) === $sourcePostBefore);
assert($sourcePostAfter->post_content === $sourceContentBefore);
assert(
    serialize($GLOBALS['wpfixpilot_meta'][$sourcePostId] ?? [])
    === $sourceMetaBefore
);

$replayed = $jobController->process_payload($snapshotJob);
assert(!is_wp_error($replayed));
assert($replayed['wordpress_object_id'] === $result['wordpress_object_id']);

$snapshotJob['payload']['unexpected'] = true;
$invalid = $jobController->process_payload($snapshotJob);
assert(is_wp_error($invalid));
assert($invalid->code === 'wp_fixpilot_job_invalid');

$snapshotJob['payload'] = array_diff_key(
    $snapshotJob['payload'],
    ['unexpected' => true]
);
$snapshotJob['payload']['snapshot_id'] = '200';
$invalidType = $jobController->process_payload($snapshotJob);
assert(is_wp_error($invalidType));
assert($invalidType->code === 'wp_fixpilot_job_invalid');

echo "snapshot draft job tests passed\n";
