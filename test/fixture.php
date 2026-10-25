<?php

declare(strict_types=1);

// CI helper only: never copied into the application image.
use Cachet\Enums\ComponentStatusEnum;
use Cachet\Enums\IncidentStatusEnum;
use Cachet\Enums\ResourceVisibilityEnum;
use Cachet\Models\Component;
use Cachet\Models\Incident;
use Cachet\Settings\AppSettings;
use Illuminate\Contracts\Console\Kernel;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;

require '/app/vendor/autoload.php';
$app = require '/app/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();
$action = $argv[1] ?? 'snapshot';
$upload = storage_path('app/public/ci-preservation.txt');

if ($action === 'fixture') {
    Component::withoutEvents(function (): void {
        Component::query()->create([
            'name' => 'CI preserved component',
            'description' => 'Synthetic disposable CI data',
            'status' => ComponentStatusEnum::operational,
            'enabled' => true,
            'checked' => false,
            'order' => 1,
        ]);
    });
    Incident::withoutEvents(function (): void {
        Incident::query()->create([
            'guid' => '00000000-0000-4000-8000-000000000001',
            'name' => 'CI preserved incident',
            'message' => 'Synthetic incident retained across the image upgrade.',
            'status' => IncidentStatusEnum::fixed,
            'visible' => ResourceVisibilityEnum::guest,
            'notifications' => 0,
            'published_at' => now(),
            'occurred_at' => now(),
        ]);
    });
    if (file_put_contents($upload, "Synthetic upload retained across upgrades.\n") === false) {
        throw new RuntimeException('CI upload creation failed');
    }
}

$userModel = config('cachet.user_model');
$email = trim(file_get_contents(getenv('ADMIN_EMAIL_FILE')));
$password = trim(file_get_contents(getenv('ADMIN_PASSWORD_FILE')));
$user = $userModel::query()->where('email', $email)->sole();
if (!$user->is_admin || !$user->email_verified_at || !Hash::check($password, $user->password)) {
    throw new RuntimeException('Administrator identity/password was not preserved');
}
$settings = app(AppSettings::class);
if ($settings->api_enabled || !$settings->api_protected || $settings->mcp_enabled
    || !$settings->mcp_protected || !$settings->display_system_status || $settings->enable_external_dependencies) {
    throw new RuntimeException('Initial security/display settings differ from the image contract');
}
if (config('cachet.demo_mode') || config('app.debug')) {
    throw new RuntimeException('Demo/debug configuration enabled in production image');
}
if (!in_array(Cachet\Http\Middleware\EnsureApiIsEnabled::class, config('cachet.api_middleware'), true)) {
    throw new RuntimeException('App config overrides the core API protection middleware');
}
$tables = [
    'users' => ['id', 'name', 'email', 'password', 'is_admin', 'email_verified_at'],
    'components' => ['id', 'name', 'description', 'status', 'enabled', 'checked'],
    'incidents' => ['id', 'guid', 'name', 'message', 'status', 'visible', 'occurred_at', 'published_at'],
];
$result = ['tables' => [], 'settings' => [], 'upload_sha256' => is_file($upload) ? hash_file('sha256', $upload) : null];
foreach ($tables as $table => $columns) {
    $rows = DB::table($table)->orderBy('id')->get($columns)->toArray();
    $result['tables'][$table] = ['count' => count($rows), 'sha256' => hash('sha256', json_encode($rows, JSON_THROW_ON_ERROR))];
}
foreach (DB::table('settings')->orderBy('group')->orderBy('name')->get(['group', 'name', 'payload']) as $row) {
    $result['settings'][$row->group.'.'.$row->name] = hash('sha256', $row->payload);
}
fwrite(STDOUT, json_encode($result, JSON_THROW_ON_ERROR).PHP_EOL);
