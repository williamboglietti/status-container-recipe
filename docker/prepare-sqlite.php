<?php

declare(strict_types=1);

$connection = getenv('DB_CONNECTION');
if (!is_string($connection) || !in_array($connection, ['sqlite', 'pgsql', 'mysql', 'mariadb'], true)) {
    throw new RuntimeException('Configure DB_CONNECTION explicitly before running migrations.');
}
if ($connection !== 'sqlite') {
    return;
}

$database = getenv('DB_DATABASE');
$storage = realpath('/app/storage/app');
if (!is_string($database) || !str_starts_with($database, '/') || $storage === false) {
    throw new RuntimeException('SQLite requires an explicit absolute DB_DATABASE in persistent storage/app.');
}
$directory = realpath(dirname($database));
if ($directory === false || ($directory !== $storage && !str_starts_with($directory, $storage.'/'))) {
    throw new RuntimeException('The SQLite database must use an existing directory in persistent storage/app.');
}
if (is_link($database)) {
    throw new RuntimeException('A symlink is not an accepted SQLite database path.');
}
if (file_exists($database)) {
    if (!is_file($database) || !is_readable($database) || !is_writable($database)) {
        throw new RuntimeException('The existing SQLite database is not a readable and writable file.');
    }
    return;
}

$handle = fopen($database, 'x');
if ($handle === false) {
    throw new RuntimeException('The new persistent SQLite database could not be created.');
}
fclose($handle);
