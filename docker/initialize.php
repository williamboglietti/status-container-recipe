<?php

declare(strict_types=1);

use Cachet\Http\Middleware\AuthenticateApiIfProtected;
use Cachet\Http\Middleware\EnsureApiIsEnabled;
use Cachet\Http\Middleware\EnsureMcpIsEnabled;
use Cachet\Settings\AppSettings;
use Cachet\Settings\CustomizationSettings;
use Illuminate\Contracts\Cache\LockProvider;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Schema;

require __DIR__.'/check-schema.php';

// This also validates the persistent application key before creating any account.
Crypt::encryptString('cachet-initialization-check');

$apiMiddleware = config('cachet.api_middleware', []);
if (!in_array(EnsureApiIsEnabled::class, $apiMiddleware, true)
    || !in_array(AuthenticateApiIfProtected::class, $apiMiddleware, true)
    || !in_array(EnsureMcpIsEnabled::class, config('cachet.mcp_middleware', []), true)) {
    throw new RuntimeException('The current core API/MCP guard configuration must be installed before initialization.');
}

$store = Cache::store();
$driver = config('cache.stores.'.config('cache.default').'.driver');
if (!($store->getStore() instanceof LockProvider) || !in_array($driver, ['database', 'redis', 'file'], true)) {
    throw new RuntimeException('Initialization requires a cache store with shared locking.');
}
$lock = $store->lock('cachet-status-initialization', 300);
if (!$lock->get()) {
    throw new RuntimeException('Another initializer holds the application lock.');
}

function initializeApplication(): void
{
    $marker = storage_path('app/cachet-initialized.json');
    $userModel = config('cachet.user_model');
    if (is_file($marker)) {
        $receipt = json_decode(file_get_contents($marker), true, flags: JSON_THROW_ON_ERROR);
        if (!isset($receipt['user_id']) || !$userModel::query()->whereKey($receipt['user_id'])->exists()) {
            throw new RuntimeException('The initialization marker and database disagree. Inspect the existing data.');
        }
        fwrite(STDOUT, "Existing initialization preserved; no account or settings changed.\n");
        return;
    }

    // Laravel migrations/settings/cache may already contain framework defaults.
    // Every other table must be empty, including jobs, subscriptions and pivots.
    $frameworkTables = ['migrations', 'settings', 'cache', 'cache_locks', 'sessions'];
    foreach (Schema::getTables() as $table) {
        $name = $table['name'];
        if (in_array($name, $frameworkTables, true)) {
            continue;
        }
        $qualifiedName = $table['schema_qualified_name'] ?? $name;
        if (DB::table($qualifiedName)->exists()) {
            throw new RuntimeException('Existing application records detected; initialization refused without modifying them.');
        }
    }

    $email = getenv('ADMIN_EMAIL');
    $password = getenv('ADMIN_PASSWORD');
    $name = getenv('ADMIN_NAME') ?: 'Administrateur';
    if (!is_string($email) || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        throw new RuntimeException('A valid ADMIN_EMAIL_FILE is required.');
    }
    if (!is_string($password) || strlen($password) < 16 || strlen($password) > 72) {
        throw new RuntimeException('ADMIN_PASSWORD_FILE must contain 16 to 72 bytes.');
    }

    $user = DB::transaction(function () use ($userModel, $name, $email, $password) {
        $user = new $userModel();
        $user->forceFill([
            'name' => $name,
            'email' => $email,
            'password' => Hash::make($password),
            'is_admin' => true,
            'email_verified_at' => now(),
            'preferred_locale' => 'en',
        ])->save();
        $persisted = $user->fresh();
        if (!$persisted || !$persisted->is_admin || !Hash::check($password, $persisted->password)) {
            throw new RuntimeException('The first administrator could not be verified.');
        }

        $settings = app(AppSettings::class);
        $settings->name = config('app.name', 'Cachet');
        $settings->about = null;
        $settings->locale = 'en';
        $settings->timezone = 'UTC';
        $settings->show_site_name = true;
        $settings->enable_external_dependencies = false;
        $settings->api_enabled = false;
        $settings->api_protected = true;
        $settings->mcp_enabled = false;
        $settings->mcp_protected = true;
        $settings->display_system_status = true;
        $settings->save();

        $customization = app(CustomizationSettings::class);
        $customization->header = '';
        $customization->footer = '';
        $customization->stylesheet = '';
        $customization->save();

        return $persisted;
    });

    // O_EXCL prevents an existing successful receipt from being overwritten.
    // If writing fails after commit, a new run refuses populated data.
    $handle = fopen($marker, 'x');
    if ($handle === false) {
        throw new RuntimeException('The account exists, but its receipt could not be written. Inspect before retrying.');
    }
    try {
        $receipt = json_encode([
            'user_id' => $user->getKey(),
            'initialized_at' => now()->toIso8601String(),
            'notice' => 'Explicit first initialization; no demonstration data.',
        ], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR)."\n";
        if (fwrite($handle, $receipt) !== strlen($receipt) || !fflush($handle)) {
            throw new RuntimeException('The initialization receipt could not be completed. Preserve the existing account.');
        }
    } finally {
        fclose($handle);
    }
    fwrite(STDOUT, "First administrator created and verified; no demonstration data seeded.\n");
}

try {
    initializeApplication();
} finally {
    $lock->release();
}
