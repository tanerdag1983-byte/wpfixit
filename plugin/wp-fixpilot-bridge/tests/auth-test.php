<?php

declare(strict_types=1);

require_once __DIR__ . '/../includes/class-auth.php';

$secret = 'test-secret';
$timestamp = (string) time();
$nonce = 'fixed-nonce';
$method = 'GET';
$route = '/wp-json/wpfixpilot/v1/inventory';
$body = '';
$signature = WPFixPilot_Auth::sign(
    $secret,
    $method,
    $route,
    $timestamp,
    $nonce,
    $body
);

$auth = new WPFixPilot_Auth(
    $secret,
    static fn (): int => (int) $timestamp,
    300
);

assert($auth->verify($method, $route, $timestamp, $nonce, $body, $signature));
assert(!$auth->verify($method, $route, $timestamp, $nonce, $body, $signature));

echo "auth tests passed\n";

