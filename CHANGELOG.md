# Change Log

Ce journal suit les changements de la recette. Les mises à jour automatiques de
Cachet, de ses dépendances et des images de base sont enregistrées par la CI
dans les commits `build: update validated Cachet sources …`.

## [Unreleased](https://github.com/williamboglietti/status-v3/commits/main)

Première version publique de la recette pour Cachet v3.

Nom du projet : `status-v3` (renommage de `status-container-recipe`).

**Fonctionnalités :**

- Image FrankenPHP (PHP 8.4, Debian bookworm) en mode classique, port 8000,
  utilisateur non root `www-data`.
- Rôles `web`, `worker`, `scheduler`, `migrate`, `initialize` et `exec` dans
  une seule image.
- `docker-compose.yml` prêt à l'emploi avec PostgreSQL 17, et `Makefile`
  (`build`, `test`, `compose-build`, `compose-up`, `update-dependencies`).
- Noms de variables de l'image v2 (`DB_DRIVER`, `CACHE_DRIVER`, `QUEUE_DRIVER`,
  `MAIL_DRIVER`, `MAIL_ADDRESS`, `MAIL_NAME`, `REDIS_DATABASE`, `APP_LOG`,
  `TRUSTED_PROXIES`) acceptés comme alias.
- Sources amont figées par commit, `composer.lock` et digests des images de
  base ; `composer audit` et Trivy bloquants.
- Tests sur SQLite, PostgreSQL 17, MySQL 8.4 et MariaDB 11.4, et test de bout
  en bout du `docker-compose.yml`.
- CI sur les runners GitHub : vérification toutes les deux heures, résolution
  Composer quotidienne, reconstruction hebdomadaire sans cache, validation sans publication des images pour `linux/amd64` et `linux/arm64`.

- CI publique limitée aux sources, locks et rapports ; construction privée séparée.
- Lanceur de build sans interpolation shell et empreintes indépendantes des caches Python.
