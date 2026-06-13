<?php

declare(strict_types=1);

final class WPFixPilot_Auth
{
    private string $secret;
    private Closure $clock;
    private int $maxAge;
    private Closure $nonceExists;
    private Closure $storeNonce;
    /** @var array<string, true> */
    private array $usedNonces = [];

    public function __construct(
        string $secret,
        ?Closure $clock = null,
        int $maxAge = 300,
        ?Closure $nonceExists = null,
        ?Closure $storeNonce = null
    ) {
        $this->secret = $secret;
        $this->clock = $clock ?? static fn (): int => time();
        $this->maxAge = $maxAge;
        $this->nonceExists = $nonceExists
            ?? fn (string $nonce): bool => isset($this->usedNonces[$nonce]);
        $this->storeNonce = $storeNonce
            ?? function (string $nonce): void {
                $this->usedNonces[$nonce] = true;
            };
    }

    public static function sign(
        string $secret,
        string $method,
        string $route,
        string $timestamp,
        string $nonce,
        string $body
    ): string {
        $canonical = implode("\n", [
            strtoupper($method),
            $route,
            $timestamp,
            $nonce,
            hash('sha256', $body),
        ]);

        return hash_hmac('sha256', $canonical, $secret);
    }

    public function verify(
        string $method,
        string $route,
        string $timestamp,
        string $nonce,
        string $body,
        string $signature
    ): bool {
        if ($this->secret === '' || $nonce === '' || !ctype_digit($timestamp)) {
            return false;
        }

        $age = abs(($this->clock)() - (int) $timestamp);
        if ($age > $this->maxAge || ($this->nonceExists)($nonce)) {
            return false;
        }

        $expected = self::sign(
            $this->secret,
            $method,
            $route,
            $timestamp,
            $nonce,
            $body
        );
        if (!hash_equals($expected, $signature)) {
            return false;
        }

        ($this->storeNonce)($nonce);
        return true;
    }
}
