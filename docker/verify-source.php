<?php

declare(strict_types=1);

$appRef = getenv('CACHET_APP_REF');
$coreRef = getenv('CACHET_CORE_REF');
$fingerprint = getenv('SOURCE_FINGERPRINT');
$revision = getenv('BUILD_REVISION');
foreach ([$appRef, $coreRef] as $reference) {
    if (!is_string($reference) || !preg_match('/^[a-f0-9]{40}$/D', $reference)) {
        throw new RuntimeException('Explicit full upstream commit references are required.');
    }
}
if (!is_string($fingerprint) || !preg_match('/^[a-f0-9]{64}$/D', $fingerprint)
    || !is_string($revision) || $revision === '') {
    throw new RuntimeException('The source fingerprint and build revision are required.');
}
$lock = json_decode(file_get_contents('/app/composer.lock'), true, flags: JSON_THROW_ON_ERROR);
$packages = array_values(array_filter($lock['packages'], fn (array $package): bool => $package['name'] === 'cachethq/core'));
if (count($packages) !== 1
    || ($packages[0]['source']['reference'] ?? null) !== $coreRef
    || ($packages[0]['dist']['reference'] ?? $coreRef) !== $coreRef) {
    throw new RuntimeException('The resolved lock does not identify the requested Cachet core commit.');
}
file_put_contents('/app/cachet-build.json', json_encode([
    'app_ref' => $appRef,
    'core_ref' => $coreRef,
    'source_fingerprint' => $fingerprint,
    'build_revision' => $revision,
    'composer_lock_sha256' => hash_file('sha256', '/app/composer.lock'),
], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR)."\n");
