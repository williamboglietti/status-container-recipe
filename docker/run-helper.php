<?php

declare(strict_types=1);

// Laravel registers an exception handler during bootstrap. An uncaught exception
// in an ad-hoc console helper can otherwise be rendered with a successful exit.
$name = $argv[1] ?? '';
if (!in_array($name, ['check-schema', 'initialize', 'prepare-sqlite'], true)) {
    fwrite(STDERR, "Unknown application helper.\n");
    exit(1);
}
try {
    require __DIR__.'/'.$name.'.php';
} catch (Throwable $error) {
    // Our own guard messages contain no secret values. Framework/DB exception
    // messages may contain SQL/bindings, so never dump them or their stack here.
    $reason = get_class($error) === RuntimeException::class
        ? $error->getMessage()
        : get_class($error).' (code '.(string) $error->getCode().')';
    fwrite(STDERR, 'Cachet '.$name.' refused or failed: '.$reason.PHP_EOL);
    exit(1);
}
