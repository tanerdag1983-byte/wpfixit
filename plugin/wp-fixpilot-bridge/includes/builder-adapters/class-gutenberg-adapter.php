<?php

declare(strict_types=1);

final class WPFixPilot_Gutenberg_Adapter implements WPFixPilot_Builder_Adapter
{
    public function key(): string
    {
        return 'gutenberg';
    }

    public function is_active(): bool
    {
        return true;
    }

    public function inspect(int $postId): array
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return [];
        }
        $slots = [];
        $this->walk(parse_blocks((string) $post->post_content), '', $slots);
        return $slots;
    }

    public function template_hash(int $postId): string
    {
        $post = get_post($postId);
        return hash('sha256', $post instanceof WP_Post ? (string) $post->post_content : '');
    }

    public function write(int $postId, array $mapping, array $values): bool|WP_Error
    {
        $post = get_post($postId);
        if (!$post instanceof WP_Post) {
            return new WP_Error('wp_fixpilot_draft_missing', 'Conceptpagina niet gevonden.');
        }
        $blocks = parse_blocks((string) $post->post_content);
        foreach ($mapping as $semantic => $path) {
            if (!isset($values[$semantic]) || !str_starts_with($path, 'block:')) {
                return new WP_Error('wp_fixpilot_slot_invalid', 'Ongeldige Gutenberg-blokmapping.');
            }
            $indexes = array_map('intval', explode('.', substr($path, 6)));
            if (!$this->replace_block($blocks, $indexes, (string) $values[$semantic])) {
                return new WP_Error('wp_fixpilot_slot_missing', 'Gutenberg-blok niet gevonden.');
            }
        }
        $result = wp_update_post([
            'ID' => $postId,
            'post_content' => serialize_blocks($blocks),
            'post_status' => 'draft',
        ], true);
        return is_wp_error($result) ? $result : true;
    }

    /** @param array<int, array<string, mixed>> $blocks */
    private function replace_block(array &$blocks, array $indexes, string $value): bool
    {
        $index = array_shift($indexes);
        if (!isset($blocks[$index])) {
            return false;
        }
        if ($indexes !== []) {
            if (!isset($blocks[$index]['innerBlocks']) || !is_array($blocks[$index]['innerBlocks'])) {
                return false;
            }
            return $this->replace_block($blocks[$index]['innerBlocks'], $indexes, $value);
        }
        $current = (string) ($blocks[$index]['innerHTML'] ?? '');
        if (preg_match('/^(<[^>]+>).*?(<\/[^>]+>)$/s', $current, $parts)) {
            $value = $parts[1] . $value . $parts[2];
        }
        $blocks[$index]['innerHTML'] = $value;
        $blocks[$index]['innerContent'] = [$value];
        return true;
    }

    /** @param array<int, array<string, mixed>> $blocks */
    private function walk(array $blocks, string $prefix, array &$slots): void
    {
        $supported = ['core/heading', 'core/paragraph', 'core/html', 'core/list'];
        foreach ($blocks as $index => $block) {
            $path = $prefix === '' ? (string) $index : $prefix . '.' . $index;
            $name = (string) ($block['blockName'] ?? '');
            if (in_array($name, $supported, true)) {
                $preview = trim(wp_strip_all_tags((string) ($block['innerHTML'] ?? '')));
                $slots[] = [
                    'path' => 'block:' . $path,
                    'label' => ($preview !== '' ? mb_substr($preview, 0, 80) : $name),
                    'value_type' => $name === 'core/heading' ? 'text' : 'html',
                ];
            }
            $inner = $block['innerBlocks'] ?? [];
            if (is_array($inner) && $inner !== []) {
                $this->walk($inner, $path, $slots);
            }
        }
    }
}
