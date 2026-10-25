<?php

declare(strict_types=1);

use Illuminate\Contracts\Console\Kernel;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

require '/app/vendor/autoload.php';

$application = require '/app/bootstrap/app.php';
$application->make(Kernel::class)->bootstrap();

if (config('app.debug') || config('cachet.demo_mode')) {
    throw new RuntimeException('Debug and demo mode are prohibited in this image.');
}
if (!config('cachet.run_migrations', true)) {
    throw new RuntimeException('The standalone image requires registration of core migrations.');
}

$migrator = $application->make('migrator');
$repository = $migrator->getRepository();
if (!$repository->repositoryExists()) {
    throw new RuntimeException('The database is not migrated. Run the explicit migrate mode first.');
}
$files = $migrator->getMigrationFiles(array_merge(
    $migrator->paths(),
    [$application->databasePath('migrations')],
));
$pending = array_diff(array_keys($files), $repository->getRan());
if ($pending !== []) {
    throw new RuntimeException('Database migrations are pending. Run the explicit migrate mode before starting services.');
}
foreach (['users', 'settings', 'jobs', 'cache'] as $table) {
    if (!Schema::hasTable($table)) {
        throw new RuntimeException('The migrated application schema is incomplete.');
    }
}
// migrate alone leaves upstream API defaults enabled. Ordinary services wait
// for our explicit first-account/settings initialization before serving traffic.
if (($argv[1] ?? '') === 'check-schema' && !DB::table('users')->where('is_admin', true)->exists()) {
    throw new RuntimeException('The first administrator is missing. Run the explicit initialize mode first.');
}
