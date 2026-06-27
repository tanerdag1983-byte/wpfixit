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
