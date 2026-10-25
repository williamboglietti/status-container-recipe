<?php

declare(strict_types=1);

function unhealthy(string $message): never
{
    // Docker stores this output in inspect; never include environment or argv.
    fwrite(STDERR, $message . "\n");
    exit(1);
}

// The entrypoint records its own PID before exec, after the schema guard.
// /tmp is container-local, unlike the shared application storage volume.
$marker = @file_get_contents('/tmp/cachet-healthcheck');
if ($marker === false || !preg_match('/\A(web|worker|scheduler) ([1-9][0-9]*)\n\z/', $marker, $match)) {
    unhealthy('Service role is not ready.');
}
[, $role, $pid] = $match;

if ($role === 'web') {
    $context = stream_context_create(['http' => ['timeout' => 3, 'follow_location' => 0]]);
    $response = @file_get_contents('http://127.0.0.1:8000/up', false, $context);
    if ($response === false || !preg_match('/^HTTP\/\S+ 200\b/', $http_response_header[0] ?? '')) {
        unhealthy('Web HTTP probe failed.');
    }
    exit(0);
}

$command = $role === 'worker' ? 'queue:work' : 'schedule:work';
$cmdline = @file_get_contents('/proc/' . $pid . '/cmdline');
$status = @file_get_contents('/proc/' . $pid . '/status');
$arguments = explode("\0", $cmdline === false ? '' : $cmdline);
if ($status === false || !preg_match('/^State:\s+[RSDI]\b/m', $status)
    || basename($arguments[0]) !== 'php'
    || ($arguments[1] ?? '') !== 'artisan'
    || ($arguments[2] ?? '') !== $command) {
    unhealthy(ucfirst($role) . ' process is absent, stopped or not running the expected command.');
}
exit(0);
