ARG FRANKENPHP_IMAGE
ARG COMPOSER_IMAGE

FROM $COMPOSER_IMAGE AS composer_binary

FROM $FRANKENPHP_IMAGE AS toolchain
USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && apt-get install -y --no-install-recommends git unzip ca-certificates \
    && install-php-extensions \
       bcmath gd intl zip opcache pcntl \
       mbstring dom simplexml xml xmlreader xmlwriter \
       pdo_sqlite pdo_pgsql pdo_mysql \
    && rm -rf /var/lib/apt/lists/*
COPY --from=composer_binary /usr/bin/composer /usr/local/bin/composer
WORKDIR /app

FROM toolchain AS application_build
ARG CACHET_APP_REF
ARG CACHET_CORE_REF
ARG SOURCE_FINGERPRINT
ARG BUILD_REVISION
COPY .build/source/ /app/
COPY docker/verify-source.php /usr/local/libexec/cachet/verify-source.php
RUN php /usr/local/libexec/cachet/verify-source.php \
    && COMPOSER_ALLOW_SUPERUSER=1 composer install \
       --no-dev --prefer-dist --no-plugins --no-scripts \
       --no-interaction --no-progress --optimize-autoloader \
    && composer check-platform-reqs --no-dev \
    && composer audit --locked --no-dev --no-interaction \
    && mkdir -p storage/app/public storage/framework/cache/data \
       storage/framework/sessions storage/framework/views storage/logs bootstrap/cache \
    && php artisan package:discover --no-interaction \
    && php artisan vendor:publish --tag=cachet-config --force --no-interaction \
    && php artisan vendor:publish --tag=laravel-assets --force --no-interaction \
    && php artisan vendor:publish --tag=cachet-assets --force --no-interaction \
    && php artisan filament:assets --no-interaction \
    && php artisan storage:link --relative --no-interaction \
    && rm -rf tests .github .agents

FROM toolchain AS runtime
ARG CACHET_APP_REF
ARG CACHET_CORE_REF
ARG SOURCE_FINGERPRINT
ARG BUILD_REVISION
# Keep `org.opencontainers.image.source` unset: GHCR could link the private
# package to this public repository and inherit public read access. `url` keeps
# the public recipe address available in image metadata.
LABEL org.opencontainers.image.title="Status v3 — for Cachet v3" \
      org.opencontainers.image.url="https://github.com/williamboglietti/status-v3" \
      org.opencontainers.image.vendor="" \
      org.opencontainers.image.licenses="LicenseRef-Cachet" \
      org.opencontainers.image.revision="$BUILD_REVISION" \
      org.opencontainers.image.version="$SOURCE_FINGERPRINT" \
      org.opencontainers.image.description="Cachet v3; immutable application and dependencies; explicit initialization and migrations." \
      org.opencontainers.image.cachet-app-revision="$CACHET_APP_REF" \
      org.opencontainers.image.cachet-core-revision="$CACHET_CORE_REF"
RUN apt-get purge -y git unzip \
    && rm -f /usr/local/bin/composer \
    && rm -rf /var/lib/apt/lists/* \
    && cp "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini" \
    && if [ -n "$(getcap /usr/local/bin/frankenphp)" ]; then \
         setcap -r /usr/local/bin/frankenphp; \
       fi
COPY --from=application_build /app/ /app/
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY docker/php.ini /usr/local/etc/php/conf.d/zz-cachet.ini
COPY docker/entrypoint.sh /usr/local/bin/cachet-entrypoint
COPY docker/initialize.php docker/check-schema.php docker/prepare-sqlite.php docker/run-helper.php /usr/local/libexec/cachet/
COPY docker/healthcheck.php /usr/local/libexec/cachet/healthcheck.php
RUN mkdir -p /app/storage/app/public /app/storage/framework/cache/data \
       /app/storage/framework/sessions /app/storage/framework/views /app/storage/logs \
       /app/bootstrap/cache /tmp/caddy/config /tmp/caddy/data \
    && chown -R www-data:www-data /app/storage /app/bootstrap/cache /tmp/caddy \
    && chmod 0755 /usr/local/bin/cachet-entrypoint
# CACHE_STORE, QUEUE_CONNECTION, MAIL_MAILER and LOG_CHANNEL stay unset so the
# entrypoint can map their Cachet 2 image names onto them; Laravel's defaults
# (database, database, log) apply, and logs reach stderr through LOG_STACK.
ENV APP_ENV=production \
    APP_DEBUG=false \
    APP_LOCALE=en \
    APP_FALLBACK_LOCALE=en \
    LOG_STACK=stderr \
    LOG_LEVEL=warning \
    SESSION_DRIVER=database \
    SESSION_SECURE_COOKIE=true \
    CACHET_BEACON=false \
    CACHET_DOCKER=true \
    CACHET_DEMO_MODE=false \
    CACHET_REGISTER_SCHEDULES=true \
    CACHET_FEED_URI="" \
    NIGHTWATCH_ENABLED=false \
    XDG_CONFIG_HOME=/tmp/caddy/config \
    XDG_DATA_HOME=/tmp/caddy/data
USER www-data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
    CMD ["php", "/usr/local/libexec/cachet/healthcheck.php"]
ENTRYPOINT ["/usr/local/bin/cachet-entrypoint"]
CMD ["web"]
