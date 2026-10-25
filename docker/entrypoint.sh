#!/bin/sh
set -eu
umask 077
cd /app

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

load_secret() {
    secret_name="$1"
    if secret_file="$(printenv "$secret_name"_FILE)"; then
        :
    else
        secret_file=""
    fi
    if secret_value="$(printenv "$secret_name")"; then
        secret_present=true
    else
        secret_value=""
        secret_present=false
    fi
    if [ -n "$secret_file" ]; then
        [ "$secret_present" = false ] || fail "$secret_name and its _FILE variant cannot both be set."
        [ -f "$secret_file" ] && [ -r "$secret_file" ] || fail "The file for $secret_name is not readable."
        secret_value="$(cat -- "$secret_file")"
        [ -n "$secret_value" ] || fail "The file for $secret_name is empty."
        export "$secret_name=$secret_value"
    fi
    unset secret_value
}

record_service() {
    printf '%s %s\n' "$mode" "$$" > /tmp/cachet-healthcheck
}

# The Cachet 2 image (cachethq/docker) used older Laravel names for these settings.
map_v2_variable() {
    legacy_name="$1"
    current_name="$2"
    if legacy_value="$(printenv "$legacy_name")"; then
        if current_value="$(printenv "$current_name")"; then
            [ "$current_value" = "$legacy_value" ] || fail "$legacy_name and $current_name are both set with different values."
        else
            export "$current_name=$legacy_value"
        fi
    fi
    unset legacy_value current_value
}

for secret_name in APP_KEY DB_PASSWORD MAIL_PASSWORD ADMIN_EMAIL ADMIN_PASSWORD ADMIN_NAME; do
    load_secret "$secret_name"
done

map_v2_variable DB_DRIVER DB_CONNECTION
map_v2_variable CACHE_DRIVER CACHE_STORE
map_v2_variable QUEUE_DRIVER QUEUE_CONNECTION
map_v2_variable MAIL_DRIVER MAIL_MAILER
map_v2_variable MAIL_ADDRESS MAIL_FROM_ADDRESS
map_v2_variable MAIL_NAME MAIL_FROM_NAME
map_v2_variable REDIS_DATABASE REDIS_DB
map_v2_variable APP_LOG LOG_CHANNEL
map_v2_variable TRUSTED_PROXIES CACHET_TRUSTED_PROXIES

for ignored_name in DB_PREFIX CACHET_EMOJI CACHET_AUTO_TWITTER NEXMO_KEY NEXMO_SECRET NEXMO_SMS_FROM PHP_MAX_CHILDREN FORCE_MIGRATION; do
    if [ -n "$(printenv "$ignored_name" || true)" ]; then
        printf 'Warning: %s comes from the Cachet 2 image and has no effect here.\n' "$ignored_name" >&2
    fi
done

if [ "$(printenv CACHE_STORE || true)" = apc ] || [ "$(printenv SESSION_DRIVER || true)" = apc ]; then
    fail "APC is not available in this image; use the database (default) or file driver."
fi
if [ "$(printenv MAIL_MAILER || true)" = sendmail ]; then
    fail "This image has no local mail server; send mail through SMTP (MAIL_MAILER=smtp)."
fi

for protected_name in APP_DEBUG CACHET_DEMO_MODE; do
    if protected_value="$(printenv "$protected_name")"; then
        :
    else
        protected_value=false
    fi
    protected_value="$(printf '%s' "$protected_value" | tr '[:upper:]' '[:lower:]')"
    case "$protected_value" in
        false|0|"") export "$protected_name=false" ;;
        *) fail "$protected_name must remain false in this image." ;;
    esac
done
unset protected_value

if [ "$#" -eq 0 ]; then
    set -- web
fi
mode="$1"
shift

case "$mode" in
    web|worker|scheduler|migrate|initialize|exec)
        if app_key="$(printenv APP_KEY)"; then
            [ -n "$app_key" ] || fail "APP_KEY or APP_KEY_FILE is required."
        else
            fail "APP_KEY or APP_KEY_FILE is required."
        fi
        unset app_key
        ;;
    *) fail "Supported modes: web, worker, scheduler, migrate, initialize, exec." ;;
esac

case "$mode" in
    web)
        [ "$#" -eq 0 ] || fail "The web mode does not accept additional arguments."
        php /usr/local/libexec/cachet/run-helper.php check-schema
        record_service
        exec frankenphp run --config /etc/caddy/Caddyfile --adapter caddyfile
        ;;
    worker)
        php /usr/local/libexec/cachet/run-helper.php check-schema
        record_service
        exec php artisan queue:work --sleep=3 --tries=3 --timeout=60 --max-time=3600 --no-interaction "$@"
        ;;
    scheduler)
        php /usr/local/libexec/cachet/run-helper.php check-schema
        record_service
        exec php artisan schedule:work --no-interaction "$@"
        ;;
    migrate)
        php /usr/local/libexec/cachet/run-helper.php prepare-sqlite
        exec php artisan migrate --force --no-interaction "$@"
        ;;
    initialize)
        [ "$#" -eq 0 ] || fail "Initialize reads credentials from ADMIN_EMAIL_FILE and ADMIN_PASSWORD_FILE."
        exec php /usr/local/libexec/cachet/run-helper.php initialize
        ;;
    exec)
        [ "$#" -gt 0 ] || fail "The exec mode requires a command."
        exec "$@"
        ;;
esac
