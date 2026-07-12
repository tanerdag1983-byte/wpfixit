<?php

declare(strict_types=1);

final class WPFixPilot_ACF_Adapter implements
    WPFixPilot_Builder_Adapter,
    WPFixPilot_Blueprint_Adapter
{
    public function key(): string
    {
        return 'acf';
    }

    public function is_active(): bool
    {
        return function_exists('get_field_objects') && function_exists('update_field');
    }

    public function uses_page(int $postId): bool
    {
        return $this->field_objects($postId) !== [];
    }

    /** @return array<int, array{path: string, label: string, value_type: string}> */
    public function inspect(int $postId): array
    {
        return $this->legacy_inspect($postId);
    }

    public function template_hash(int $postId): string
    {
        $fields = $this->field_objects($postId);
        if ($fields === []) {
            return '';
        }

        return hash('sha256', (string) wp_json_encode($fields));
    }

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        foreach ($mapping as $path) {
            if (
                str_starts_with((string) $path, 'acf:')
                || str_starts_with((string) $path, 'acf-block:')
                || str_starts_with((string) $path, 'acf-value:')
            ) {
                return $this->legacy_write($postId, $mapping, $values);
            }
        }

        $schema = $this->schema($postId);
        if (is_wp_error($schema)) {
            return $schema;
        }

        $replacements = [];
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic])) {
                return new WP_Error(
                    'wp_fixpilot_slot_invalid',
                    'Ongeldige ACF-mapping.'
                );
            }

            $fieldId = $this->field_id_for_path($schema, (string) $path);
            if ($fieldId === null) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'ACF-veld kon niet worden bijgewerkt.'
                );
            }

            $replacements[$fieldId] = (string) $values[$semantic];
        }

        return $this->apply_replacements($postId, $schema, $replacements);
    }

    /** @return array<int, string> */
    public function clone_meta_keys(int $postId): array
    {
        $fields = $this->field_objects($postId);
        if ($fields === []) {
            return [];
        }

        $keys = [];
        $prefixes = [];
        foreach ($fields as $field) {
            $name = (string) ($field['name'] ?? '');
            if ($name === '') {
                continue;
            }

            $keys[] = $name;
            $keys[] = '_' . $name;
            $prefixes[] = $name;
            $prefixes[] = '_' . $name;
        }

        if (function_exists('get_post_meta')) {
            foreach (array_keys((array) get_post_meta($postId)) as $metaKey) {
                $metaKey = (string) $metaKey;
                if ($this->is_excluded_meta_key($metaKey)) {
                    continue;
                }

                foreach ($prefixes as $prefix) {
                    if (
                        $metaKey === $prefix
                        || str_starts_with($metaKey, $prefix . '_')
                    ) {
                        $keys[] = $metaKey;
                        break;
                    }
                }
            }
        }

        $keys = array_values(array_unique($keys));
        sort($keys);

        return $keys;
    }

    /** @return array<string, mixed>|WP_Error */
    public function schema(int $postId): array|WP_Error
    {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'ACF is niet actief.',
                ['status' => 409]
            );
        }

        $fields = $this->field_objects($postId);
        if ($fields === []) {
            return new WP_Error(
                'wp_fixpilot_no_editable_content',
                'Geen bewerkbare tekstinhoud gevonden.',
                ['status' => 400]
            );
        }

        $blocks = [];
        foreach ($fields as $field) {
            $blocks = array_merge($blocks, $this->schema_blocks_for_field($field));
        }

        if ($blocks === []) {
            return new WP_Error(
                'wp_fixpilot_no_editable_content',
                'Geen bewerkbare tekstinhoud gevonden.',
                ['status' => 400]
            );
        }

        return [
            'schema_version' => 'blueprint-v1',
            'blocks' => $blocks,
        ];
    }

    public function structure_hash(int $postId): string
    {
        $fields = $this->field_objects($postId);
        if ($fields === []) {
            return '';
        }

        $normalized = [];
        foreach ($fields as $field) {
            $normalized[] = $this->normalize_field_structure(
                $field,
                $field['value'] ?? null
            );
        }

        return hash('sha256', (string) wp_json_encode($normalized));
    }

    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error {
        if (!$this->is_active()) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'ACF is niet actief.',
                ['status' => 409]
            );
        }

        $fields = $this->schema_fields($schema);
        foreach ($replacements as $fieldId => $value) {
            if (!isset($fields[$fieldId])) {
                return new WP_Error(
                    'wp_fixpilot_blueprint_field_unknown',
                    'Onbekend blueprint-veld.',
                    ['status' => 400]
                );
            }
        }

        $updates = [];
        foreach ($replacements as $fieldId => $replacement) {
            $field = $fields[$fieldId];
            $target = $this->parse_path((string) $field['path']);
            if ($target === null) {
                return new WP_Error(
                    'wp_fixpilot_field_invalid',
                    'ACF-veld heeft ongeldige structuur.',
                    ['status' => 500]
                );
            }

            $topFieldKey = $target['top_field_key'];
            if (!isset($updates[$topFieldKey])) {
                $current = get_field($topFieldKey, $postId, false);
                if ($current === null) {
                    $current = get_field(
                        $target['top_field_name'],
                        $postId,
                        false
                    );
                }
                if ($current === null) {
                    $current = $this->top_level_field_value(
                        $postId,
                        $topFieldKey,
                        $target['top_field_name']
                    );
                }
                $updates[$topFieldKey] = [
                    'value' => $current,
                    'top_field_name' => $target['top_field_name'],
                    'replacements' => [],
                ];
            }

            if (
                !$this->replace_value_at_segments(
                    $updates[$topFieldKey]['value'],
                    $target['segments'],
                    (string) $replacement
                )
            ) {
                return new WP_Error(
                    'wp_fixpilot_field_invalid',
                    'ACF-veld heeft ongeldige structuur.',
                    ['status' => 500]
                );
            }
            $updates[$topFieldKey]['replacements'][] = [
                'segments' => $target['segments'],
                'value' => (string) $replacement,
                'meta' => $this->leaf_meta_target(
                    $postId,
                    $topFieldKey,
                    $target['top_field_name'],
                    $target['segments']
                ),
            ];
        }

        foreach ($updates as $topFieldKey => $update) {
            $writeByKey = update_field((string) $topFieldKey, $update['value'], $postId);
            $expected = wp_json_encode($update['value']);
            $persistedByKey = get_field((string) $topFieldKey, $postId, false);
            $persistedByName = get_field(
                (string) $update['top_field_name'],
                $postId,
                false
            );
            $persisted = wp_json_encode($persistedByKey) === $expected
                || wp_json_encode($persistedByName) === $expected
                || $this->persisted_replacements_match(
                    $persistedByKey,
                    $update['replacements']
                )
                || $this->persisted_replacements_match(
                    $persistedByName,
                    $update['replacements']
                );
            if (!$persisted) {
                $writeByName = update_field(
                    (string) $update['top_field_name'],
                    $update['value'],
                    $postId
                );
                $persistedByKey = get_field(
                    (string) $topFieldKey,
                    $postId,
                    false
                );
                $persistedByName = get_field(
                    (string) $update['top_field_name'],
                    $postId,
                    false
                );
                $persisted = wp_json_encode($persistedByKey) === $expected
                    || wp_json_encode($persistedByName) === $expected
                    || $this->persisted_replacements_match(
                        $persistedByKey,
                        $update['replacements']
                    )
                    || $this->persisted_replacements_match(
                        $persistedByName,
                        $update['replacements']
                    );
            }
            if (
                !$persisted
                && $this->write_leaf_meta_replacements(
                    $postId,
                    $update['replacements']
                )
            ) {
                $persisted = true;
            }
            if (!$persisted) {
                $mismatch = $this->first_replacement_mismatch(
                    $persistedByKey,
                    $persistedByName,
                    $update['replacements']
                );
                return new WP_Error(
                    'wp_fixpilot_field_write_failed',
                    sprintf(
                        'ACF-veld kon niet worden bijgewerkt: selector %s / %s; pad %s; key write %s; name write %s; key type %s; name type %s.',
                        (string) $topFieldKey,
                        (string) $update['top_field_name'],
                        $mismatch['path'],
                        $writeByKey === false ? 'false' : 'ok',
                        ($writeByName ?? null) === false ? 'false' : 'ok',
                        gettype($persistedByKey),
                        gettype($persistedByName)
                    ),
                    [
                        'status' => 500,
                        'top_field_key' => (string) $topFieldKey,
                        'top_field_name' => (string) $update['top_field_name'],
                        'expected_type' => gettype($update['value']),
                        'persisted_key_type' => gettype($persistedByKey),
                        'persisted_name_type' => gettype($persistedByName),
                    ]
                );
            }
        }

        return true;
    }

    /**
     * @param array<int, array{segments: array<int, string>, value: string, meta?: array{meta_key: string, field_key: string}|null}> $replacements
     */
    private function write_leaf_meta_replacements(
        int $postId,
        array $replacements
    ): bool {
        if (!function_exists('update_post_meta')) {
            return false;
        }

        foreach ($replacements as $replacement) {
            $meta = $replacement['meta'] ?? null;
            if (!is_array($meta)) {
                return false;
            }
            $metaKey = (string) ($meta['meta_key'] ?? '');
            $fieldKey = (string) ($meta['field_key'] ?? '');
            if ($metaKey === '') {
                return false;
            }
            if (
                update_post_meta($postId, $metaKey, $replacement['value']) === false
                && (
                    !function_exists('get_post_meta')
                    || get_post_meta($postId, $metaKey, true) !== $replacement['value']
                )
            ) {
                return false;
            }
            if (
                $fieldKey !== ''
                && update_post_meta($postId, '_' . $metaKey, $fieldKey) === false
                && (
                    !function_exists('get_post_meta')
                    || get_post_meta($postId, '_' . $metaKey, true) !== $fieldKey
                )
            ) {
                return false;
            }
        }

        return true;
    }

    /** @return array<int, array{path: string, label: string, value_type: string}> */
    private function legacy_inspect(int $postId): array
    {
        $slots = [];
        foreach ($this->field_objects($postId) as $field) {
            $fieldKey = (string) ($field['key'] ?? '');
            $label = $this->field_label($field);
            $type = (string) ($field['type'] ?? '');
            if ($type === 'flexible_content') {
                $slots = array_merge($slots, $this->legacy_flexible_block_slots($field));
                continue;
            }

            if (in_array($type, ['text', 'textarea', 'wysiwyg', 'url'], true)) {
                $slots[] = [
                    'path' => 'acf:' . $fieldKey,
                    'label' => $label,
                    'value_type' => $type === 'wysiwyg' ? 'html' : 'text',
                ];
                continue;
            }

            if ($fieldKey !== '' && is_array($field['value'] ?? null)) {
                $this->legacy_nested_slots(
                    $field['value'],
                    $fieldKey,
                    [],
                    $label,
                    $slots
                );
            }
        }

        return array_values(array_filter(
            $slots,
            static fn (array $slot): bool => $slot['path'] !== 'acf:'
        ));
    }

    private function legacy_write(
        int $postId,
        array $mapping,
        array $values
    ): bool|WP_Error {
        if (!function_exists('update_field')) {
            return new WP_Error(
                'wp_fixpilot_builder_inactive',
                'ACF is niet actief.'
            );
        }

        $fields = $this->field_objects($postId);
        $nestedUpdates = [];
        $blockTargets = [];
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic])) {
                return new WP_Error(
                    'wp_fixpilot_slot_invalid',
                    'Ongeldige ACF-mapping.'
                );
            }

            $path = (string) $path;
            if (str_starts_with($path, 'acf-block:')) {
                if (preg_match('/^acf-block:([^:]+):([0-9]+)$/', $path, $match) !== 1) {
                    return new WP_Error(
                        'wp_fixpilot_slot_invalid',
                        'Ongeldige ACF-mapping.'
                    );
                }

                $fieldKey = (string) $match[1];
                $rowIndex = (string) $match[2];
                if (!array_key_exists($fieldKey, $nestedUpdates)) {
                    $field = $this->field_by_key($fields, $fieldKey);
                    if ($field === null || !is_array($field['value'] ?? null)) {
                        return new WP_Error(
                            'wp_fixpilot_slot_missing',
                            'ACF-blok kon niet worden bijgewerkt.'
                        );
                    }
                    $nestedUpdates[$fieldKey] = $field['value'];
                }

                if (
                    !isset($nestedUpdates[$fieldKey][$rowIndex])
                    || !is_array($nestedUpdates[$fieldKey][$rowIndex])
                ) {
                    return new WP_Error(
                        'wp_fixpilot_slot_missing',
                        'ACF-blok kon niet worden bijgewerkt.'
                    );
                }

                $targetSegments = $this->legacy_block_target_segments(
                    $nestedUpdates[$fieldKey][$rowIndex],
                    (string) $semantic,
                    $blockTargets[$path] ?? []
                );
                if ($targetSegments === null) {
                    return new WP_Error(
                        'wp_fixpilot_slot_missing',
                        'ACF-blok heeft geen passend tekstveld.'
                    );
                }

                if (
                    !$this->legacy_replace_nested_value(
                        $nestedUpdates[$fieldKey],
                        [$rowIndex, ...$targetSegments],
                        (string) $values[$semantic]
                    )
                ) {
                    return new WP_Error(
                        'wp_fixpilot_slot_missing',
                        'ACF-blok kon niet worden bijgewerkt.'
                    );
                }
                $blockTargets[$path][] = implode('/', $targetSegments);
                continue;
            }

            if (str_starts_with($path, 'acf-value:')) {
                if (preg_match('/^acf-value:([^:]+):(.+)$/', $path, $match) !== 1) {
                    return new WP_Error(
                        'wp_fixpilot_slot_invalid',
                        'Ongeldige ACF-mapping.'
                    );
                }

                $fieldKey = (string) $match[1];
                if (!array_key_exists($fieldKey, $nestedUpdates)) {
                    $field = $this->field_by_key($fields, $fieldKey);
                    if ($field === null || !is_array($field['value'] ?? null)) {
                        return new WP_Error(
                            'wp_fixpilot_slot_missing',
                            'ACF-veld kon niet worden bijgewerkt.'
                        );
                    }
                    $nestedUpdates[$fieldKey] = $field['value'];
                }

                $segments = array_map('rawurldecode', explode('/', (string) $match[2]));
                if (
                    !$this->legacy_replace_nested_value(
                        $nestedUpdates[$fieldKey],
                        $segments,
                        (string) $values[$semantic]
                    )
                ) {
                    return new WP_Error(
                        'wp_fixpilot_slot_missing',
                        'ACF-veld kon niet worden bijgewerkt.'
                    );
                }
                continue;
            }

            if (!str_starts_with($path, 'acf:')) {
                return new WP_Error(
                    'wp_fixpilot_slot_invalid',
                    'Ongeldige ACF-mapping.'
                );
            }

            $fieldKey = substr($path, 4);
            if (
                $fieldKey === ''
                || update_field($fieldKey, (string) $values[$semantic], $postId) === false
            ) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'ACF-veld kon niet worden bijgewerkt.'
                );
            }
        }

        foreach ($nestedUpdates as $fieldKey => $value) {
            if (update_field((string) $fieldKey, $value, $postId) === false) {
                return new WP_Error(
                    'wp_fixpilot_slot_missing',
                    'ACF-veld kon niet worden bijgewerkt.'
                );
            }
        }

        return true;
    }

    /** @return array<int, array<string, mixed>> */
    private function field_objects(int $postId): array
    {
        if (!function_exists('get_field_objects')) {
            return [];
        }

        $fields = get_field_objects($postId);
        if (!is_array($fields)) {
            return [];
        }

        return array_values(array_filter($fields, 'is_array'));
    }

    /** @return array<int, array<string, mixed>> */
    private function schema_blocks_for_field(array $field): array
    {
        $type = (string) ($field['type'] ?? '');
        $value = $field['value'] ?? null;
        $name = (string) ($field['name'] ?? '');
        $key = (string) ($field['key'] ?? '');
        $label = $this->field_label($field);

        if ($type === 'flexible_content') {
            $blocks = [];
            $rows = is_array($value) ? $value : [];
            $layouts = $this->layouts_by_name($field);
            if ($layouts === []) {
                return $this->schema_blocks_from_flexible_values(
                    $rows,
                    $key,
                    $name,
                    $label
                );
            }
            foreach ($rows as $rowIndex => $row) {
                if (!is_array($row)) {
                    continue;
                }
                $layoutName = (string) ($row['acf_fc_layout'] ?? '');
                if ($layoutName === '' || !isset($layouts[$layoutName])) {
                    continue;
                }
                $layout = $layouts[$layoutName];
                $fields = [];
                foreach ($this->sub_fields($layout) as $subField) {
                    $subName = (string) ($subField['name'] ?? '');
                    $fields = array_merge(
                        $fields,
                        $this->schema_fields_from_definition(
                            $subField,
                            $row[$subName] ?? null,
                            $key,
                            $name,
                            [(string) $rowIndex, $subName],
                            [
                                $name . ':' . $key,
                                'layout:' . $layoutName,
                                'row:' . $rowIndex,
                                $subName . ':' . (string) ($subField['key'] ?? ''),
                            ],
                            [$label, $this->field_label($layout)]
                        )
                    );
                }
                if ($fields === []) {
                    continue;
                }
                $blocks[] = [
                    'id' => wpfixpilot_field_id(
                        'acf',
                        implode('/', [$key, $name, 'layout', $layoutName, 'row', (string) $rowIndex])
                    ),
                    'layout' => $layoutName,
                    'label' => $label . ' (' . $this->field_label($layout) . ')',
                    'semantic_role' => $this->infer_semantic_role($layoutName, $label),
                    'fields' => $fields,
                ];
            }

            return $blocks;
        }

        if ($type === 'repeater') {
            $rows = is_array($value) ? $value : [];
            $blocks = [];
            foreach ($rows as $rowIndex => $row) {
                if (!is_array($row)) {
                    continue;
                }

                $fields = [];
                foreach ($this->sub_fields($field) as $subField) {
                    $subName = (string) ($subField['name'] ?? '');
                    $fields = array_merge(
                        $fields,
                        $this->schema_fields_from_definition(
                            $subField,
                            $row[$subName] ?? null,
                            $key,
                            $name,
                            [(string) $rowIndex, $subName],
                            [
                                $name . ':' . $key,
                                'row:' . $rowIndex,
                                $subName . ':' . (string) ($subField['key'] ?? ''),
                            ],
                            [$label]
                        )
                    );
                }
                if ($fields === []) {
                    continue;
                }
                $blocks[] = [
                    'id' => wpfixpilot_field_id(
                        'acf',
                        implode('/', [$key, $name, 'row', (string) $rowIndex])
                    ),
                    'layout' => $name !== '' ? $name : 'repeater',
                    'label' => $label,
                    'semantic_role' => $this->infer_semantic_role($name, $label),
                    'fields' => $fields,
                ];
            }

            return $blocks;
        }

        $fields = $this->schema_fields_from_definition(
            $field,
            $value,
            $key,
            $name,
            [],
            [$name . ':' . $key],
            [$label]
        );
        if ($fields === []) {
            return [];
        }

        return [[
            'id' => wpfixpilot_field_id('acf', implode('/', [$key, $name, 'block'])),
            'layout' => $name !== '' ? $name : $type,
            'label' => $label,
            'semantic_role' => $this->infer_semantic_role($name, $label),
            'fields' => $fields,
        ]];
    }

    /**
     * @param array<int, string> $valueSegments
     * @param array<int, string> $idSegments
     * @param array<int, string> $labelSegments
     * @return array<int, array<string, mixed>>
     */
    private function schema_fields_from_definition(
        array $field,
        mixed $value,
        string $topFieldKey,
        string $topFieldName,
        array $valueSegments,
        array $idSegments,
        array $labelSegments
    ): array {
        $type = (string) ($field['type'] ?? '');
        $name = (string) ($field['name'] ?? '');

        if ($type === 'group') {
            $groupValue = is_array($value) ? $value : [];
            $fields = [];
            foreach ($this->sub_fields($field) as $subField) {
                $subName = (string) ($subField['name'] ?? '');
                $fields = array_merge(
                    $fields,
                    $this->schema_fields_from_definition(
                        $subField,
                        $groupValue[$subName] ?? null,
                        $topFieldKey,
                        $topFieldName,
                        [...$valueSegments, $subName],
                        [...$idSegments, $subName . ':' . (string) ($subField['key'] ?? '')],
                        [...$labelSegments, $this->field_label($field)]
                    )
                );
            }

            return $fields;
        }

        if ($type === 'repeater') {
            $rows = is_array($value) ? $value : [];
            $fields = [];
            foreach ($rows as $rowIndex => $row) {
                $rowValues = is_array($row) ? $row : [];
                foreach ($this->sub_fields($field) as $subField) {
                    $subName = (string) ($subField['name'] ?? '');
                    $fields = array_merge(
                        $fields,
                        $this->schema_fields_from_definition(
                            $subField,
                            $rowValues[$subName] ?? null,
                            $topFieldKey,
                            $topFieldName,
                            [...$valueSegments, (string) $rowIndex, $subName],
                            [...$idSegments, 'row:' . $rowIndex, $subName . ':' . (string) ($subField['key'] ?? '')],
                            $labelSegments
                        )
                    );
                }
            }

            return $fields;
        }

        if ($type === 'flexible_content') {
            $rows = is_array($value) ? $value : [];
            $layouts = $this->layouts_by_name($field);
            $fields = [];
            foreach ($rows as $rowIndex => $row) {
                if (!is_array($row)) {
                    continue;
                }
                $layoutName = (string) ($row['acf_fc_layout'] ?? '');
                if ($layoutName === '' || !isset($layouts[$layoutName])) {
                    continue;
                }
                foreach ($this->sub_fields($layouts[$layoutName]) as $subField) {
                    $subName = (string) ($subField['name'] ?? '');
                    $fields = array_merge(
                        $fields,
                        $this->schema_fields_from_definition(
                            $subField,
                            $row[$subName] ?? null,
                            $topFieldKey,
                            $topFieldName,
                            [...$valueSegments, (string) $rowIndex, $subName],
                            [...$idSegments, 'layout:' . $layoutName, 'row:' . $rowIndex, $subName . ':' . (string) ($subField['key'] ?? '')],
                            $labelSegments
                        )
                    );
                }
            }

            return $fields;
        }

        if ($type === 'link') {
            $linkValue = is_array($value) ? $value : [];
            $metaKey = $this->meta_key_from_segments(
                $topFieldName,
                [...$valueSegments, 'url']
            );

            return [[
                'id' => wpfixpilot_field_id(
                    'acf',
                    implode('/', [...$idSegments, 'url'])
                ),
                'path' => $this->field_path(
                    $topFieldKey,
                    $topFieldName,
                    [...$valueSegments, 'url']
                ),
                'label' => $this->field_output_label($labelSegments, $field),
                'value_type' => 'url',
                'current_value' => isset($linkValue['url']) && is_string($linkValue['url'])
                    ? $linkValue['url']
                    : '',
                'required' => !empty($field['required']),
                'max_length' => 2000,
            ]];
        }

        if (!$this->is_editable_leaf_type($type)) {
            return [];
        }

        return [[
            'id' => wpfixpilot_field_id('acf', implode('/', $idSegments)),
            'path' => $this->field_path($topFieldKey, $topFieldName, $valueSegments),
            'label' => $this->field_output_label($labelSegments, $field),
            'value_type' => $this->acf_value_type($field),
            'current_value' => is_string($value) ? $value : '',
            'required' => !empty($field['required']),
            'max_length' => $this->max_length_for_type($type),
        ]];
    }

    /**
     * @param array<int, string> $segments
     */
    private function meta_key_from_segments(
        string $topFieldName,
        array $segments
    ): string {
        return implode('_', array_merge([$topFieldName], $segments));
    }

    /**
     * @param array<int, string> $segments
     * @return array{meta_key: string, field_key: string}|null
     */
    private function leaf_meta_target(
        int $postId,
        string $topFieldKey,
        string $topFieldName,
        array $segments
    ): ?array {
        $topField = $this->field_by_key($this->field_objects($postId), $topFieldKey);
        if (!is_array($topField)) {
            foreach ($this->field_objects($postId) as $field) {
                if ((string) ($field['name'] ?? '') === $topFieldName) {
                    $topField = $field;
                    break;
                }
            }
        }
        if (!is_array($topField)) {
            return null;
        }

        $metaKey = $this->meta_key_from_segments($topFieldName, $segments);
        $field = $this->leaf_field_definition($topField, $segments, $topField['value'] ?? null);
        $fieldKey = is_array($field) ? (string) ($field['key'] ?? '') : '';
        if ($fieldKey === '' && function_exists('get_post_meta')) {
            $fieldKey = (string) get_post_meta($postId, '_' . $metaKey, true);
        }
        return [
            'meta_key' => $metaKey,
            'field_key' => $fieldKey,
        ];
    }

    /**
     * @param array<string, mixed> $field
     * @param array<int, string> $segments
     */
    private function leaf_field_definition(
        array $field,
        array $segments,
        mixed $value
    ): ?array {
        if ($segments === []) {
            return $field;
        }

        $type = (string) ($field['type'] ?? '');
        if ($type === 'flexible_content') {
            $rowIndex = array_shift($segments);
            if ($rowIndex === null || !is_array($value) || !is_array($value[$rowIndex] ?? null)) {
                return null;
            }
            $row = $value[$rowIndex];
            $layoutName = (string) ($row['acf_fc_layout'] ?? '');
            $layouts = $this->layouts_by_name($field);
            if ($layoutName === '' || !isset($layouts[$layoutName])) {
                return null;
            }
            $childName = array_shift($segments);
            if ($childName === null) {
                return null;
            }
            $child = $this->sub_field_by_name($this->sub_fields($layouts[$layoutName]), $childName);
            return is_array($child)
                ? $this->leaf_field_definition($child, $segments, $row[$childName] ?? null)
                : null;
        }

        if ($type === 'repeater') {
            $rowIndex = array_shift($segments);
            $childName = array_shift($segments);
            if (
                $rowIndex === null
                || $childName === null
                || !is_array($value)
                || !is_array($value[$rowIndex] ?? null)
            ) {
                return null;
            }
            $row = $value[$rowIndex];
            $child = $this->sub_field_by_name($this->sub_fields($field), $childName);
            return is_array($child)
                ? $this->leaf_field_definition($child, $segments, $row[$childName] ?? null)
                : null;
        }

        if ($type === 'group') {
            $childName = array_shift($segments);
            if ($childName === null) {
                return null;
            }
            $child = $this->sub_field_by_name($this->sub_fields($field), $childName);
            return is_array($child)
                ? $this->leaf_field_definition(
                    $child,
                    $segments,
                    is_array($value) ? ($value[$childName] ?? null) : null
                )
                : null;
        }

        if ($type === 'link' && $segments === ['url']) {
            return $field;
        }

        return $segments === [] ? $field : null;
    }

    /**
     * @param array<int, array<string, mixed>> $fields
     */
    private function sub_field_by_name(array $fields, string $name): ?array
    {
        foreach ($fields as $field) {
            if (is_array($field) && (string) ($field['name'] ?? '') === $name) {
                return $field;
            }
        }

        return null;
    }

    /**
     * @param array<int|string, mixed> $rows
     * @return array<int, array<string, mixed>>
     */
    private function schema_blocks_from_flexible_values(
        array $rows,
        string $topFieldKey,
        string $topFieldName,
        string $label
    ): array {
        $blocks = [];
        foreach ($rows as $rowIndex => $row) {
            if (!is_array($row)) {
                continue;
            }

            $layoutName = (string) ($row['acf_fc_layout'] ?? 'content');
            $fields = $this->schema_fields_from_value(
                $row,
                $topFieldKey,
                $topFieldName,
                [(string) $rowIndex],
                [$topFieldName . ':' . $topFieldKey, 'layout:' . $layoutName, 'row:' . $rowIndex],
                [$label]
            );
            if ($fields === []) {
                continue;
            }

            $blocks[] = [
                'id' => wpfixpilot_field_id(
                    'acf',
                    implode('/', [$topFieldKey, $topFieldName, 'layout', $layoutName, 'row', (string) $rowIndex])
                ),
                'layout' => $layoutName,
                'label' => $label . ' (' . $layoutName . ')',
                'semantic_role' => $this->infer_semantic_role($layoutName, $label),
                'fields' => $fields,
            ];
        }

        return $blocks;
    }

    /**
     * @param array<int|string, mixed> $value
     * @param array<int, string> $valueSegments
     * @param array<int, string> $idSegments
     * @param array<int, string> $labelSegments
     * @return array<int, array<string, mixed>>
     */
    private function schema_fields_from_value(
        array $value,
        string $topFieldKey,
        string $topFieldName,
        array $valueSegments,
        array $idSegments,
        array $labelSegments
    ): array {
        $fields = [];
        foreach ($value as $key => $child) {
            if ($key === 'acf_fc_layout' || str_starts_with((string) $key, '_')) {
                continue;
            }

            $segments = [...$valueSegments, (string) $key];
            $childIdSegments = [...$idSegments, (string) $key];
            if (is_array($child)) {
                $fields = array_merge(
                    $fields,
                    $this->schema_fields_from_value(
                        $child,
                        $topFieldKey,
                        $topFieldName,
                        $segments,
                        $childIdSegments,
                        $labelSegments
                    )
                );
                continue;
            }

            if (!is_string($child) || trim($child) === '') {
                continue;
            }

            $valueType = wp_strip_all_tags($child) !== $child
                ? 'rich_text'
                : (filter_var($child, FILTER_VALIDATE_URL) === false ? 'plain_text' : 'url');
            $fields[] = [
                'id' => wpfixpilot_field_id('acf', implode('/', $childIdSegments)),
                'path' => $this->field_path($topFieldKey, $topFieldName, $segments),
                'label' => implode(' · ', [...$labelSegments, (string) $key]),
                'value_type' => $valueType,
                'current_value' => $child,
                'required' => true,
                'max_length' => match ($valueType) {
                    'rich_text' => 20000,
                    'url' => 2000,
                    default => 5000,
                },
            ];
        }

        return $fields;
    }

    /** @return array<string, mixed> */
    private function normalize_field_structure(array $field, mixed $value): array
    {
        $type = (string) ($field['type'] ?? '');
        $normalized = [
            'key' => (string) ($field['key'] ?? ''),
            'name' => (string) ($field['name'] ?? ''),
            'type' => $type,
        ];

        if ($type === 'flexible_content') {
            $rows = is_array($value) ? $value : [];
            $layouts = $this->layouts_by_name($field);
            $normalized['rows'] = [];
            foreach ($rows as $rowIndex => $row) {
                if (!is_array($row)) {
                    continue;
                }
                $layoutName = (string) ($row['acf_fc_layout'] ?? '');
                $layout = $layouts[$layoutName] ?? null;
                $normalized['rows'][] = [
                    'index' => $rowIndex,
                    'layout' => $layoutName,
                    'fields' => $layout === null
                        ? []
                        : $this->normalize_sub_field_structures(
                            $this->sub_fields($layout),
                            $row
                        ),
                ];
            }

            return $normalized;
        }

        if ($type === 'repeater') {
            $rows = is_array($value) ? $value : [];
            $normalized['rows'] = [];
            foreach ($rows as $rowIndex => $row) {
                $normalized['rows'][] = [
                    'index' => $rowIndex,
                    'fields' => $this->normalize_sub_field_structures(
                        $this->sub_fields($field),
                        is_array($row) ? $row : []
                    ),
                ];
            }

            return $normalized;
        }

        if ($type === 'group') {
            $normalized['fields'] = $this->normalize_sub_field_structures(
                $this->sub_fields($field),
                is_array($value) ? $value : []
            );

            return $normalized;
        }

        if ($type === 'link') {
            $linkValue = is_array($value) ? $value : [];
            $normalized['editable'] = 'url';
            $normalized['locked'] = [
                'title' => (string) ($linkValue['title'] ?? ''),
                'target' => (string) ($linkValue['target'] ?? ''),
            ];

            return $normalized;
        }

        if ($this->is_editable_leaf_type($type)) {
            $normalized['editable'] = $this->acf_value_type($field);

            return $normalized;
        }

        $normalized['locked'] = $this->normalize_locked_value($value);

        return $normalized;
    }

    /**
     * @param array<int, array<string, mixed>> $subFields
     * @param array<string, mixed> $values
     * @return array<int, array<string, mixed>>
     */
    private function normalize_sub_field_structures(
        array $subFields,
        array $values
    ): array {
        $normalized = [];
        foreach ($subFields as $subField) {
            $name = (string) ($subField['name'] ?? '');
            $normalized[] = $this->normalize_field_structure(
                $subField,
                $values[$name] ?? null
            );
        }

        return $normalized;
    }

    /** @return array<string, string>|null */
    private function parse_path(string $path): ?array
    {
        if (!str_starts_with($path, 'acf:')) {
            return null;
        }

        $segments = array_map(
            'rawurldecode',
            explode('/', substr($path, 4))
        );
        if (count($segments) < 2) {
            return null;
        }

        $topFieldKey = (string) array_shift($segments);
        $topFieldName = (string) array_shift($segments);
        if ($topFieldKey === '' || $topFieldName === '') {
            return null;
        }

        return [
            'top_field_key' => $topFieldKey,
            'top_field_name' => $topFieldName,
            'segments' => $segments,
        ];
    }

    /**
     * @param array<int, string> $segments
     */
    private function field_path(
        string $topFieldKey,
        string $topFieldName,
        array $segments
    ): string {
        $parts = array_merge(
            [$topFieldKey, $topFieldName],
            array_map('rawurlencode', $segments)
        );

        return 'acf:' . implode('/', $parts);
    }

    private function top_level_field_value(
        int $postId,
        string $topFieldKey,
        string $topFieldName
    ): mixed {
        foreach ($this->field_objects($postId) as $field) {
            if (
                (string) ($field['key'] ?? '') === $topFieldKey
                || (string) ($field['name'] ?? '') === $topFieldName
            ) {
                return $field['value'] ?? null;
            }
        }

        return null;
    }

    private function field_by_key(array $fields, string $fieldKey): ?array
    {
        foreach ($fields as $field) {
            if (is_array($field) && ($field['key'] ?? null) === $fieldKey) {
                return $field;
            }
        }

        return null;
    }

    /**
     * @param array<int, string> $segments
     */
    private function replace_value_at_segments(
        mixed &$value,
        array $segments,
        string $replacement
    ): bool {
        if ($segments === []) {
            $value = $replacement;

            return true;
        }

        if (!is_array($value)) {
            return false;
        }

        $cursor = &$value;
        foreach ($segments as $index => $segment) {
            $isLast = $index === array_key_last($segments);
            if ($isLast) {
                $cursor[$segment] = $replacement;

                return true;
            }

            if (!isset($cursor[$segment]) || !is_array($cursor[$segment])) {
                $cursor[$segment] = [];
            }

            $cursor = &$cursor[$segment];
        }

        return false;
    }

    /**
     * @param array<int, array{segments: array<int, string>, value: string}> $replacements
     */
    private function persisted_replacements_match(
        mixed $persisted,
        array $replacements
    ): bool {
        foreach ($replacements as $replacement) {
            $value = $this->value_at_segments(
                $persisted,
                $replacement['segments']
            );
            if ((string) $value !== $replacement['value']) {
                return false;
            }
        }

        return true;
    }

    /**
     * @param array<int, array{segments: array<int, string>, value: string}> $replacements
     * @return array{path: string}
     */
    private function first_replacement_mismatch(
        mixed $persistedByKey,
        mixed $persistedByName,
        array $replacements
    ): array {
        foreach ($replacements as $replacement) {
            $keyValue = $this->value_at_segments(
                $persistedByKey,
                $replacement['segments']
            );
            $nameValue = $this->value_at_segments(
                $persistedByName,
                $replacement['segments']
            );
            if (
                (string) $keyValue !== $replacement['value']
                && (string) $nameValue !== $replacement['value']
            ) {
                return [
                    'path' => implode('/', $replacement['segments']),
                ];
            }
        }

        return ['path' => '(unknown)'];
    }

    /**
     * @param array<int, string> $segments
     */
    private function value_at_segments(mixed $value, array $segments): mixed
    {
        $cursor = $value;
        foreach ($segments as $segment) {
            if (!is_array($cursor) || !array_key_exists($segment, $cursor)) {
                return null;
            }
            $cursor = $cursor[$segment];
        }

        return $cursor;
    }

    private function legacy_nested_slots(
        mixed $value,
        string $fieldKey,
        array $segments,
        string $label,
        array &$slots
    ): void {
        if (is_array($value)) {
            foreach ($value as $key => $child) {
                if ($key === 'acf_fc_layout' || str_starts_with((string) $key, '_')) {
                    continue;
                }
                $this->legacy_nested_slots(
                    $child,
                    $fieldKey,
                    [...$segments, (string) $key],
                    $label,
                    $slots
                );
            }

            return;
        }

        if (!is_string($value) || trim($value) === '') {
            return;
        }

        $preview = trim(wp_strip_all_tags($value));
        if ($preview === '') {
            $preview = (string) end($segments);
        }

        $slots[] = [
            'path' => 'acf-value:' . $fieldKey . ':' . implode(
                '/',
                array_map('rawurlencode', $segments)
            ),
            'label' => $label . ' · ' . $this->short_label($preview),
            'value_type' => wp_strip_all_tags($value) !== $value ? 'html' : 'text',
        ];
    }

    /** @return array<int, array{path: string, label: string, value_type: string}> */
    private function legacy_flexible_block_slots(array $field): array
    {
        $fieldKey = (string) ($field['key'] ?? '');
        if ($fieldKey === '') {
            return [];
        }

        $rows = is_array($field['value'] ?? null) ? $field['value'] : [];
        $layouts = $this->layouts_by_name($field);
        $slots = [];
        foreach ($rows as $rowIndex => $row) {
            if (!is_array($row)) {
                continue;
            }

            $layoutName = (string) ($row['acf_fc_layout'] ?? '');
            $layout = $layouts[$layoutName] ?? null;
            $blockLabel = $layout !== null
                ? $this->field_label($layout)
                : ($layoutName !== '' ? $layoutName : $this->legacy_first_text_preview($row));
            if ($blockLabel === '') {
                $blockLabel = 'Blok ' . ((int) $rowIndex + 1);
            }

            $slots[] = [
                'path' => 'acf-block:' . $fieldKey . ':' . (string) $rowIndex,
                'label' => $this->field_label($field) . ' · ' . $blockLabel,
                'preview' => $this->legacy_block_preview($row),
                'value_type' => $this->legacy_row_contains_html($row) ? 'html' : 'text',
            ];
        }

        return $slots;
    }

    private function legacy_block_preview(array $row): string
    {
        $parts = [];
        $this->legacy_collect_preview_parts($row, $parts);

        return implode(' · ', array_slice(array_values(array_unique($parts)), 0, 2));
    }

    /** @param array<int, string> $parts */
    private function legacy_collect_preview_parts(array $value, array &$parts): void
    {
        foreach ($value as $key => $child) {
            if ($key === 'acf_fc_layout' || str_starts_with((string) $key, '_')) {
                continue;
            }
            if (is_array($child)) {
                $this->legacy_collect_preview_parts($child, $parts);
                continue;
            }
            if (!is_string($child)) {
                continue;
            }

            $text = trim(wp_strip_all_tags($child));
            if (
                $text === ''
                || filter_var($text, FILTER_VALIDATE_URL) !== false
                || preg_match('/^#[0-9a-f]{3,8}$/i', $text) === 1
                || preg_match('/^(fa-|image\/|svg\+xml)/i', $text) === 1
            ) {
                continue;
            }
            $parts[] = $this->short_label($text);
            if (count($parts) >= 2) {
                return;
            }
        }
    }

    /** @return array<int, string>|null */
    private function legacy_block_target_segments(
        array $row,
        string $semantic,
        array $usedPaths = []
    ): ?array
    {
        $candidates = match ($semantic) {
            'hero_title', 'cta_title' => [
                'title', 'heading', 'headline', 'kop', 'titel', 'label',
            ],
            'faq' => [
                'answer', 'antwoord', 'body', 'content', 'description', 'text', 'copy',
            ],
            'introduction' => [
                'description', 'intro', 'introduction', 'subheading', 'body', 'copy', 'content', 'text',
            ],
            'main_content', 'cta_text' => [
                'body', 'content', 'description', 'copy', 'text', 'answer',
            ],
            default => [],
        };

        $textPaths = $this->legacy_text_paths($row);
        foreach ($candidates as $candidate) {
            foreach ($textPaths as $path) {
                $key = (string) end($path);
                $pathKey = implode('/', $path);
                if (
                    !in_array($pathKey, $usedPaths, true)
                    && ($key === $candidate || preg_match(
                        '/(?:^|[_-])' . preg_quote($candidate, '/') . '$/',
                        $key
                    ) === 1)
                ) {
                    return $path;
                }
            }
        }

        return null;
    }

    /** @return array<int, array<int, string>> */
    private function legacy_text_paths(array $value, array $prefix = []): array
    {
        $paths = [];
        foreach ($value as $key => $child) {
            $key = (string) $key;
            if ($key === 'acf_fc_layout' || str_starts_with($key, '_')) {
                continue;
            }
            if (is_array($child)) {
                $paths = array_merge(
                    $paths,
                    $this->legacy_text_paths($child, [...$prefix, $key])
                );
                continue;
            }
            if (is_string($child) && $this->legacy_is_editable_text_leaf($key, $child)) {
                $paths[] = [...$prefix, $key];
            }
        }

        return $paths;
    }

    private function legacy_is_editable_text_leaf(string $key, string $value): bool
    {
        $key = strtolower($key);
        $text = trim(wp_strip_all_tags($value));

        return $text !== ''
            && preg_match(
                '/(?:^|_)(?:url|link|color|icon|image|class|id|style|setting|target|mime|type)(?:$|_)/',
                $key
            ) !== 1
            && filter_var($text, FILTER_VALIDATE_URL) === false
            && preg_match('/^#[0-9a-f]{3,8}$/i', $text) !== 1
            && preg_match('/^(?:fa-|image\/|svg\+xml)/i', $text) !== 1;
    }

    /** @return array<int, string>|null */
    private function legacy_first_text_path(array $value): ?array
    {
        foreach ($value as $key => $child) {
            $key = (string) $key;
            if ($key === 'acf_fc_layout' || str_starts_with($key, '_')) {
                continue;
            }
            if (is_array($child)) {
                $nested = $this->legacy_first_text_path($child);
                if ($nested !== null) {
                    return [$key, ...$nested];
                }
                continue;
            }
            if (is_string($child)) {
                return [$key];
            }
        }

        return null;
    }

    private function legacy_first_text_preview(array $value): string
    {
        $path = $this->legacy_first_text_path($value);
        if ($path === null) {
            return '';
        }

        $cursor = $value;
        foreach ($path as $segment) {
            if (!is_array($cursor) || !array_key_exists($segment, $cursor)) {
                return '';
            }
            $cursor = $cursor[$segment];
        }

        return is_string($cursor)
            ? $this->short_label(trim(wp_strip_all_tags($cursor)))
            : '';
    }

    private function legacy_row_contains_html(array $value): bool
    {
        foreach ($value as $key => $child) {
            if ($key === 'acf_fc_layout' || str_starts_with((string) $key, '_')) {
                continue;
            }
            if (is_array($child) && $this->legacy_row_contains_html($child)) {
                return true;
            }
            if (is_string($child) && wp_strip_all_tags($child) !== $child) {
                return true;
            }
        }

        return false;
    }

    private function legacy_replace_nested_value(
        array &$value,
        array $segments,
        string $replacement
    ): bool {
        if ($segments === []) {
            return false;
        }

        $cursor = &$value;
        foreach ($segments as $index => $segment) {
            if (!is_array($cursor) || !array_key_exists($segment, $cursor)) {
                return false;
            }
            if ($index === array_key_last($segments)) {
                $cursor[$segment] = $replacement;

                return true;
            }
            $cursor = &$cursor[$segment];
        }

        return false;
    }

    private function short_label(string $value): string
    {
        return function_exists('mb_substr')
            ? mb_substr($value, 0, 80)
            : substr($value, 0, 80);
    }

    /** @return array<string, array<string, mixed>> */
    private function schema_fields(array $schema): array
    {
        $fields = [];
        foreach ((array) ($schema['blocks'] ?? []) as $block) {
            foreach ((array) ($block['fields'] ?? []) as $field) {
                if (
                    is_array($field)
                    && isset($field['id'])
                    && is_string($field['id'])
                ) {
                    $fields[$field['id']] = $field;
                }
            }
        }

        return $fields;
    }

    private function field_id_for_path(array $schema, string $path): ?string
    {
        foreach ($this->schema_fields($schema) as $fieldId => $field) {
            if (($field['path'] ?? null) === $path) {
                return $fieldId;
            }
        }

        return null;
    }

    /** @return array<int, array<string, mixed>> */
    private function sub_fields(array $field): array
    {
        $subFields = $field['sub_fields'] ?? [];
        if (!is_array($subFields)) {
            return [];
        }

        return array_values(array_filter($subFields, 'is_array'));
    }

    /** @return array<string, array<string, mixed>> */
    private function layouts_by_name(array $field): array
    {
        $layouts = [];
        foreach ((array) ($field['layouts'] ?? []) as $layout) {
            if (!is_array($layout)) {
                continue;
            }
            $name = (string) ($layout['name'] ?? '');
            if ($name === '') {
                continue;
            }
            $layouts[$name] = $layout;
        }

        return $layouts;
    }

    private function field_label(array $field): string
    {
        $label = (string) ($field['label'] ?? '');
        if ($label !== '') {
            return $label;
        }

        $name = (string) ($field['name'] ?? '');

        return $name !== '' ? $name : 'ACF field';
    }

    /**
     * @param array<int, string> $labelSegments
     */
    private function field_output_label(array $labelSegments, array $field): string
    {
        $segments = array_filter($labelSegments, static fn (string $label): bool => $label !== '');
        $segments[] = $this->field_label($field);

        return implode(' · ', array_values(array_unique($segments)));
    }

    private function is_editable_leaf_type(string $type): bool
    {
        return in_array($type, ['text', 'textarea', 'wysiwyg', 'url'], true);
    }

    private function acf_value_type(array $field): string
    {
        $type = (string) ($field['type'] ?? '');
        if ($type === 'wysiwyg') {
            return 'rich_text';
        }
        if ($type === 'url') {
            return 'url';
        }

        $name = strtolower((string) ($field['name'] ?? ''));
        $label = strtolower($this->field_label($field));
        $combined = $name . ' ' . $label;
        if (str_contains($combined, 'heading')) {
            return 'heading';
        }
        if (
            str_contains($combined, 'button')
            || str_contains($combined, 'knop')
            || str_contains($combined, 'cta')
        ) {
            return 'button_text';
        }

        return 'plain_text';
    }

    private function max_length_for_type(string $type): int
    {
        return match ($type) {
            'text' => 500,
            'textarea' => 5000,
            'wysiwyg' => 20000,
            'url' => 2000,
            default => 5000,
        };
    }

    private function infer_semantic_role(string $name, string $label): string
    {
        $combined = strtolower($name . ' ' . $label);
        if (str_contains($combined, 'hero') || str_contains($combined, 'header')) {
            return 'hero';
        }
        if (str_contains($combined, 'intro') || str_contains($combined, 'inleiding')) {
            return 'introduction';
        }
        if (str_contains($combined, 'benefit') || str_contains($combined, 'voordel')) {
            return 'benefits';
        }
        if (str_contains($combined, 'proces') || str_contains($combined, 'stap')) {
            return 'process';
        }
        if (str_contains($combined, 'faq') || str_contains($combined, 'vraag')) {
            return 'faq';
        }
        if (str_contains($combined, 'cta') || str_contains($combined, 'call')) {
            return 'cta';
        }

        return 'content';
    }

    private function normalize_locked_value(mixed $value): mixed
    {
        if (is_array($value)) {
            $normalized = [];
            foreach ($value as $key => $child) {
                $normalized[$key] = $this->normalize_locked_value($child);
            }

            return $normalized;
        }

        return $value;
    }

    private function slot_value_type(string $valueType): string
    {
        return $valueType === 'rich_text' ? 'html' : 'text';
    }

    private function is_excluded_meta_key(string $metaKey): bool
    {
        if (str_starts_with($metaKey, '_wp_fixpilot_')) {
            return true;
        }

        return in_array($metaKey, ['_edit_lock', '_edit_last', '_wp_old_slug'], true);
    }
}
