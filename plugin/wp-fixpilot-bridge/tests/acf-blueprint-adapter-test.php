<?php

declare(strict_types=1);

/**
 * ACF Blueprint Adapter Tests
 * 
 * Tests the ACF adapter implementation of the blueprint contract.
 */

require_once __DIR__ . '/../includes/builder-adapters/interface-blueprint-adapter.php';
require_once __DIR__ . '/../includes/builder-adapters/class-acf-blueprint-adapter.php';

// Mock WordPress functions
function get_field_objects(int $postId): array|false
{
    global $test_acf_fields;
    return $test_acf_fields[$postId] ?? false;
}

function get_field(string $selector, int $postId): mixed
{
    global $test_acf_values;
    return $test_acf_values[$postId][$selector] ?? null;
}

function update_field(string $selector, mixed $value, int $postId): bool
{
    global $test_acf_values;
    if (!isset($test_acf_values[$postId])) {
        $test_acf_values[$postId] = [];
    }
    $test_acf_values[$postId][$selector] = $value;
    return true;
}

function wp_json_encode(mixed $data): string|false
{
    return json_encode($data);
}

function wp_strip_all_tags(string $string): string
{
    return strip_tags($string);
}

// Mock WP_Error
class WP_Error
{
    public function __construct(
        public string $code,
        public string $message,
        public array $data = []
    ) {}
}

function is_wp_error(mixed $thing): bool
{
    return $thing instanceof WP_Error;
}

// Test setup
global $test_acf_fields, $test_acf_values;

// Simple single text field
$test_acf_fields[100] = [
    [
        'key' => 'field_title',
        'name' => 'page_title',
        'label' => 'Page Title',
        'type' => 'text',
        'value' => 'Original Title',
        'required' => true,
    ],
];

// Flexible content with nested fields
$test_acf_fields[200] = [
    [
        'key' => 'field_content_blocks',
        'name' => 'content_blocks',
        'label' => 'Content Blocks',
        'type' => 'flexible_content',
        'value' => [
            0 => [
                'acf_fc_layout' => 'hero',
                'heading' => 'Original Hero Heading',
                'subheading' => 'Original Subheading',
                '_heading' => 'field_heading_key',
            ],
            1 => [
                'acf_fc_layout' => 'benefits',
                'title' => 'Benefit Title',
                'description' => '<p>Rich text content</p>',
            ],
        ],
    ],
];

$test_acf_values = [];

echo "Running ACF Blueprint Adapter Tests...\n\n";

$adapter = new WPFixPilot_ACF_Blueprint_Adapter();

// Test 1: Adapter basics
echo "Test 1: Adapter key and activation\n";
assert($adapter->key() === 'acf', 'Adapter key should be "acf"');
assert($adapter->is_active() === true, 'Adapter should be active (mocked)');
assert($adapter->uses_page(100) === true, 'Should detect ACF usage on page 100');
assert($adapter->uses_page(999) === false, 'Should not detect ACF on non-existent page');
echo "✓ Adapter basics pass\n\n";

// Test 2: Clone meta keys
echo "Test 2: Clone meta keys extraction\n";
$keys = $adapter->clone_meta_keys(100);
assert(in_array('page_title', $keys, true), 'Should include field name');
assert(in_array('_page_title', $keys, true), 'Should include field key reference');
echo "✓ Clone meta keys: " . implode(', ', $keys) . "\n\n";

// Test 3: Schema extraction for simple field
echo "Test 3: Schema extraction (simple field)\n";
$schema = $adapter->schema(100);
assert(!is_wp_error($schema), 'Schema should not be error');
assert($schema['schema_version'] === 'blueprint-v1', 'Schema version should be blueprint-v1');
assert(count($schema['blocks']) === 1, 'Should have 1 block');
assert(count($schema['blocks'][0]['fields']) === 1, 'Block should have 1 field');
$field = $schema['blocks'][0]['fields'][0];
assert($field['current_value'] === 'Original Title', 'Should extract current value');
assert($field['value_type'] === 'plain_text', 'Should detect value type');
assert($field['required'] === true, 'Should preserve required flag');
echo "✓ Simple schema extraction pass\n";
echo "  Field ID: " . $field['id'] . "\n";
echo "  Field label: " . $field['label'] . "\n\n";

// Test 4: Schema extraction for flexible content
echo "Test 4: Schema extraction (flexible content)\n";
$schema2 = $adapter->schema(200);
assert(!is_wp_error($schema2), 'Schema should not be error');
assert(count($schema2['blocks']) >= 2, 'Should have at least 2 blocks');
$heroBlock = $schema2['blocks'][0];
assert($heroBlock['layout'] === 'hero', 'First block should be hero layout');
assert($heroBlock['semantic_role'] === 'hero', 'Should infer hero semantic role');
assert(count($heroBlock['fields']) >= 2, 'Hero should have at least 2 fields');
echo "✓ Flexible content schema extraction pass\n";
echo "  Blocks found: " . count($schema2['blocks']) . "\n";
echo "  Hero fields: " . count($heroBlock['fields']) . "\n\n";

// Test 5: Structure hash
echo "Test 5: Structure hash generation\n";
$hash1 = $adapter->structure_hash(100);
$hash2 = $adapter->structure_hash(100);
assert($hash1 === $hash2, 'Structure hash should be deterministic');
assert(strlen($hash1) === 64, 'Should be SHA256 hash');
echo "✓ Structure hash: " . substr($hash1, 0, 16) . "...\n\n";

// Test 6: Apply replacements (simple field)
echo "Test 6: Apply replacements (simple field)\n";
$schema = $adapter->schema(100);
$field_id = $schema['blocks'][0]['fields'][0]['id'];
$replacements = [
    $field_id => 'Updated Title',
];
$result = $adapter->apply_replacements(100, $schema, $replacements);
assert($result === true, 'Apply replacements should succeed');
// Verify the update worked
$updated = get_field('field_title', 100);
assert($updated === 'Updated Title', 'Field value should be updated');
echo "✓ Simple field replacement pass\n";
echo "  New value: $updated\n\n";

// Test 7: Apply replacements (flexible content)
echo "Test 7: Apply replacements (flexible content)\n";
$test_acf_values[200] = [
    'field_content_blocks' => [
        0 => [
            'acf_fc_layout' => 'hero',
            'heading' => 'Original Hero Heading',
            'subheading' => 'Original Subheading',
        ],
        1 => [
            'acf_fc_layout' => 'benefits',
            'title' => 'Benefit Title',
            'description' => '<p>Rich text content</p>',
        ],
    ],
];

$schema3 = $adapter->schema(200);
$first_field_id = $schema3['blocks'][0]['fields'][0]['id'];
$replacements2 = [
    $first_field_id => 'New Hero Heading',
];
$result2 = $adapter->apply_replacements(200, $schema3, $replacements2);
assert($result2 === true, 'Flexible content replacement should succeed');
$updated_flex = get_field('field_content_blocks', 200);
assert($updated_flex[0]['heading'] === 'New Hero Heading', 'Nested field should be updated');
echo "✓ Flexible content replacement pass\n";
echo "  Updated heading: " . $updated_flex[0]['heading'] . "\n\n";

// Test 8: Error handling
echo "Test 8: Error handling (non-existent page)\n";
$schema_error = $adapter->schema(999);
assert(is_wp_error($schema_error), 'Should return WP_Error for page without ACF');
assert($schema_error->code === 'wp_fixpilot_no_editable_content', 'Should have correct error code');
echo "✓ Error handling pass\n";
echo "  Error: " . $schema_error->message . "\n\n";

echo "═══════════════════════════════════════\n";
echo "All ACF Blueprint Adapter tests passed!\n";
echo "═══════════════════════════════════════\n";
