# Status v3

Recette Docker pour [Cachet](https://cachethq.io/) v3, le logiciel de page de
statut. Elle construit une image prête à l'auto-hébergement, la teste sur
SQLite, PostgreSQL, MySQL et MariaDB, et la reconstruit automatiquement quand
le code amont, ses dépendances ou les images de base changent.

Ce dépôt reprend les conventions de l'image Docker de Cachet 2,
[cachethq/Docker](https://github.com/cachethq/Docker) : port 8000, utilisateur
non root, journaux sur stdout et stderr, `docker-compose.yml` et `Makefile` à
la racine, mêmes noms de variables d'environnement quand Cachet 3 le permet.
Les écarts sont décrits plus bas.

> Ce projet n'est ni affilié à Cachet ni approuvé par Cachet. Il assemble le
> code amont sans en modifier l'interface, les assets ou les attributions.

## Aucune image publique

**Ce dépôt ne distribue pas l'image construite.** La licence de Cachet 3
interdit de distribuer Cachet comme produit autonome. Le dépôt fournit donc
seulement la recette : chacun construit l'image lui-même, avec `make build`,
ou la tire de son propre registre privé.

Les références de Cachet, des dépendances et des images de base sont figées
pour rendre la construction reproductible. La CI valide les mises à jour sur
AMD64 et ARM64 sans distribuer les images construites.

## Démarrage rapide

Prérequis : Docker avec Compose et Buildx, `make` et Python 3.12+.

1. Cloner le dépôt :

   ```sh
   git clone https://github.com/williamboglietti/status-v3.git
   cd status-v3
   ```

2. Construire l'image locale `status-v3:local` à partir des sources figées :

   ```sh
   make compose-build
   ```

3. Facultatif : créer un fichier `.env` à côté de `docker-compose.yml` pour
   adapter `APP_NAME`, `APP_URL` (par défaut `http://localhost:8000`) ou
   `MAIL_MAILER`.

4. Démarrer :

   ```sh
   make compose-up
   ```

   `make compose-up` crée les secrets manquants dans `.secrets/` (clé
   d'application, mot de passe PostgreSQL, adresse et mot de passe du premier
   administrateur), puis lance `docker compose up --detach`. Compose migre la
   base, crée l'administrateur, puis démarre `web`, `worker` et `scheduler`.
   Pour choisir l'adresse de l'administrateur :
   `make compose-up ADMIN_EMAIL=vous@example.com`.

5. Cachet répond sur `http://localhost:8000`. Le tableau de bord est sous
   `/dashboard` ; les identifiants sont dans `.secrets/admin-email` et
   `.secrets/admin-password`.

Le port n'est publié que sur `127.0.0.1` : en production, placez un reverse
proxy HTTPS devant. `CACHET_HTTP=0.0.0.0:80` dans `.env` reproduit le
`80:8000` de l'image v2, mais les cookies de session sont réservés à HTTPS
(`SESSION_SECURE_COOKIE=true`) hors de `localhost`.

Sans `make`, utiliser `python3 scripts/project.py build`, puis
`python3 scripts/project.py compose-up`. Pour une image tirée d'un
registre privé, mettez `CACHET_IMAGE=<registre>/<image>@sha256:...` dans
`.env`.

## Écarts avec l'image v2

| Sujet | cachethq/Docker (Cachet 1.2 à 2.4) | Cette recette (Cachet 3) |
| --- | --- | --- |
| Serveur | nginx, PHP-FPM et supervisor sur Alpine | FrankenPHP en mode classique sur Debian |
| Processus | nginx, PHP-FPM et la file d'attente dans un conteneur | Un rôle par conteneur : `web`, `worker`, `scheduler` |
| Courrier | Postfix intégré pour `MAIL_DRIVER=sendmail` | Pas de serveur de courrier : SMTP externe |
| Base de données | `cachet:install`, migrations et seed à chaque démarrage | Étapes explicites `migrate` puis `initialize`, enchaînées par Compose |
| `APP_KEY` absente | Clé générée affichée dans les logs, arrêt | Démarrage refusé ; `make compose-up` génère la clé |
| Configuration | `.env` réécrit par `sed` dans l'image | Variables d'environnement seules, secrets en `*_FILE` |
| Valeurs par défaut | `APP_ENV=development`, `APP_DEBUG=true` | `APP_ENV=production` ; `APP_DEBUG=true` refusé |
| Utilisateur | `www-data`, UID 1001, groupe root | `www-data`, UID 33 (Debian), capacités retirées |
| Port | 8000 (publié sur `80`) | 8000 (publié sur `127.0.0.1:8000`) |
| Sources | Archive de la branche ou du tag `cachet_ver` | Commits, `composer.lock` et digests figés et vérifiés |
| Tests | bats sur SQLite, MySQL et PostgreSQL | Python sur SQLite, PostgreSQL 17, MySQL 8.4, MariaDB 11.4 et Compose |
| Architectures | amd64 (branche arm32 à part) | amd64 et arm64, construites nativement |
| Publication | Image publique sur Docker Hub, un tag par version | Aucune image publique (licence de Cachet 3) |

**FrankenPHP à la place de nginx, PHP-FPM et supervisor.** Un seul processus
et un seul fichier de configuration ([`docker/Caddyfile`](docker/Caddyfile))
servent les fichiers statiques et exécutent PHP. FrankenPHP est publié sous
licence MIT dans l'organisation GitHub du projet PHP
([php/frankenphp](https://github.com/php/frankenphp)). Il bénéficie du soutien
officiel de la PHP Foundation et Laravel Octane le prend en charge. L'image
l'utilise en mode classique (`php_server`), sans mode worker ni Octane : c'est
le mode le plus éprouvé, équivalent à PHP-FPM, où chaque requête démarre
l'application. La file d'attente et le planificateur tournent dans des
conteneurs séparés, avec la même image ; supervisor devient inutile.

**Pas de postfix intégré.** Un serveur de courrier dans le conteneur de
l'application demande des droits root (l'image v2 passait par `sudo`). Il
garde aussi les messages en attente dans un système de fichiers éphémère et
n'offre pas la réputation d'envoi (SPF, DKIM) d'un vrai relais. Cachet 3 met
déjà tous ses e-mails en file d'attente : le rôle `worker` les envoie à un
serveur SMTP externe (`MAIL_MAILER=smtp`).

**Pas de modèle OpenShift.** L'image n'accepte pas d'UID arbitraire : ses
répertoires inscriptibles appartiennent à l'UID 33.

## Variables d'environnement

Les noms de l'image v2 restent acceptés : l'entrypoint les recopie sous leur
nom Laravel actuel. Si l'ancien et le nouveau nom sont tous deux définis avec
des valeurs différentes, le conteneur refuse de démarrer. Les variables v2 sans
effet affichent un avertissement.

| Variable v2 | Défaut v2 | Équivalent ici | Remarque |
| --- | --- | --- | --- |
| `APP_KEY` | (vide) | `APP_KEY` ou `APP_KEY_FILE` | Obligatoire, format `base64:...`. |
| `APP_ENV` | `development` | `APP_ENV` | Défaut `production`. |
| `APP_DEBUG` | `true` | `APP_DEBUG` | Défaut `false` ; `true` est refusé. |
| `APP_URL` | `http://localhost` | `APP_URL` | |
| `APP_LOG` | `errorlog` | `LOG_CHANNEL` | Alias. Par défaut, tout va sur stderr. |
| `DB_DRIVER` | `pgsql` | `DB_CONNECTION` | Alias. `sqlite`, `mysql`, `mariadb` ou `pgsql`. |
| `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME` | `postgres`, `5432`, `cachet`, `postgres` | mêmes noms | Pas de défaut dans l'image ; SQLite demande un chemin absolu sous `/app/storage/app`. |
| `DB_PASSWORD` | `postgres` | `DB_PASSWORD` ou `DB_PASSWORD_FILE` | |
| `DB_PREFIX` | (vide) | aucun | Cachet 3 n'utilise pas de préfixe de tables. |
| `CACHE_DRIVER` | `apc` | `CACHE_STORE` | Alias. Défaut `database` ; `apc` est refusé (extension absente). |
| `SESSION_DRIVER` | `apc` | `SESSION_DRIVER` | Défaut `database` ; `apc` est refusé. |
| `SESSION_DOMAIN` | (vide) | `SESSION_DOMAIN` | |
| `SESSION_SECURE_COOKIE` | (vide) | `SESSION_SECURE_COOKIE` | Défaut `true` : HTTPS requis hors de `localhost`. |
| `QUEUE_DRIVER` | `database` | `QUEUE_CONNECTION` | Alias. Défaut `database`, traité par le rôle `worker`. |
| `MAIL_DRIVER` | `smtp` | `MAIL_MAILER` | Alias. Défaut `log` ; `sendmail` est refusé (pas de postfix). |
| `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_ENCRYPTION` | `localhost`, `25` | mêmes noms | Défauts Laravel : `127.0.0.1`, `2525`, `tls`. |
| `MAIL_PASSWORD` | (vide) | `MAIL_PASSWORD` ou `MAIL_PASSWORD_FILE` | |
| `MAIL_ADDRESS`, `MAIL_NAME` | (vide) | `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME` | Alias. |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | (vide) | mêmes noms | L'extension `phpredis` n'est pas incluse : Redis n'est pas utilisable. |
| `REDIS_DATABASE` | (vide) | `REDIS_DB` | Alias. |
| `TRUSTED_PROXIES` | (vide) | `CACHET_TRUSTED_PROXIES` | Alias. Liste séparée par des virgules, ou `*`. |
| `CACHET_BEACON` | `true` | `CACHET_BEACON` | Défaut `false` ici : aucune télémétrie sans accord explicite. |
| `CACHET_EMOJI`, `CACHET_AUTO_TWITTER` | `false`, `true` | aucun | Sans effet dans Cachet 3. |
| `NEXMO_KEY`, `NEXMO_SECRET`, `NEXMO_SMS_FROM` | (vide), `Cachet` | aucun | Pas de SMS dans Cachet 3. |
| `GITHUB_TOKEN` | (vide) | aucun | Cachet 3 ne le lit pas. |
| `PHP_MAX_CHILDREN` | `5` | aucun | Réglage PHP-FPM ; FrankenPHP dimensionne ses threads lui-même. |
| `FORCE_MIGRATION` | `false` | aucun | Les migrations passent par l'étape `migrate`. |
| `DEBUG` | `false` | aucun | L'entrypoint ne trace pas ses commandes, pour ne jamais afficher un secret. |
| `cachet_ver` (build) | `2.4` | `sources.lock.json` | Commits figés, mis à jour par la CI ou `make update-dependencies`. |

Nouvelles variables :

| Variable | Rôle |
| --- | --- |
| `APP_KEY_FILE`, `DB_PASSWORD_FILE`, `MAIL_PASSWORD_FILE` | Lire le secret dans un fichier (lisible par l'UID 33) plutôt que dans l'environnement. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` (et `*_FILE`) | Premier administrateur, lu seulement par `initialize`. Mot de passe de 16 à 72 octets. |
| `APP_NAME` | Nom affiché ; `CACHET_TITLE` vaut par défaut `"${APP_NAME} - Status"`. |
| `LOG_LEVEL` | Défaut `warning`. |
| `CACHET_FEED_URI` | Vide par défaut : pas d'appel au flux du blog de Cachet. |
| `CACHET_DOCKER` | `true` dans l'image ; information transmise par la télémétrie si elle est activée. |
| `CACHET_IMAGE`, `CACHET_HTTP` | Compose seulement : image utilisée (défaut `status-v3:local`) et adresse publiée (défaut `127.0.0.1:8000`). |

Les autres variables de Cachet 3 (`CACHET_PATH`, `CACHET_TITLE`,
`CACHET_API_RATE_LIMIT`, etc.) sont décrites dans la
[documentation de Cachet](https://docs.cachethq.io/v3.x/configuration/environment).

## Migrer depuis cachethq/docker (v2)

Le chemin de migration des données de Cachet 2.4 vers Cachet 3 est
[incomplet en amont](https://docs.cachethq.io/v3.x/migration-guide) : ne lancez
pas les migrations de Cachet 3 sur une base 2.4.

1. Sauvegardez la base et les fichiers de l'instance v2, et vérifiez que la
   sauvegarde se restaure. Laissez l'instance v2 en service.
2. Déployez cette recette à côté, avec **une nouvelle base de données**.
3. Reprenez la configuration : les noms v2 de la table ci-dessus fonctionnent
   tels quels. Remplacez `CACHE_DRIVER=apc`, `SESSION_DRIVER=apc` et
   `MAIL_DRIVER=sendmail` s'ils étaient définis, et retirez les variables sans
   effet. Une nouvelle `APP_KEY` convient, puisque les données ne sont pas
   reprises.
4. Recréez les composants, les groupes et les abonnés dans le tableau de bord ou
   par l'API, puis basculez le DNS ou le reverse proxy.
5. Arrêtez l'instance v2 une fois la nouvelle validée, en gardant sa
   sauvegarde.

Dans le compose v2, `migrate`, `initialize`, `worker` et `scheduler`
remplacent le conteneur unique `cachet`, et `.secrets/` remplace `APP_KEY` et
les mots de passe écrits en clair dans le fichier.

## Rôles de l'image

| Commande | Effet |
| --- | --- |
| `web` (défaut) | Serveur HTTP sur le port 8000 ; refuse un schéma non migré ou sans administrateur. |
| `worker` | File d'attente Laravel (`queue:work`), dont les e-mails aux abonnés. |
| `scheduler` | Tâches planifiées de Cachet ; un seul exemplaire par instance. |
| `migrate` | Applique les migrations ; à lancer une fois par mise à jour du schéma. |
| `initialize` | Crée le premier administrateur sur une base vide ; sans effet ensuite. |
| `exec <commande>` | Commande de maintenance, après chargement des secrets, par exemple `docker compose run --rm web exec php artisan about`. |

`web`, `worker` et `scheduler` ne migrent jamais la base et ne créent jamais de
compte : plusieurs réplicas peuvent démarrer sans se concurrencer. Dans
`docker-compose.yml`, `migrate` et `initialize` sont des étapes ponctuelles
lancées avant les trois services.

- **Données à persister** : la base et `/app/storage` (les uploads sont sous
  `storage/app/public`). Ne montez rien sur `/app/vendor` ni sur
  `/app/public/vendor`.
- **Mémoire** : au moins 256 Mio pour `worker` et `scheduler` si leur mémoire
  est limitée.
- **Healthcheck** : HTTP 200 sur `/up` pour `web` ; présence et état du
  processus `queue:work` ou `schedule:work` pour les deux autres.
- **Journaux** : accès HTTP sur stdout ; erreurs PHP et journaux Laravel sur
  stderr.

## Mettre à jour une instance

1. Sauvegardez ensemble la base, le volume `/app/storage` et `APP_KEY`, et
   notez l'image en service.
2. `docker compose down`, puis reconstruisez l'image (`git pull` puis
   `make compose-build`) ou changez le digest de `CACHET_IMAGE`.
3. `docker compose up --detach` : l'étape `migrate` s'exécute avant le
   redémarrage des services.
4. Vérifiez comptes, composants, incidents, abonnés et uploads.

Pour revenir en arrière, restaurez la sauvegarde **et** l'image précédente :
une image plus ancienne ne sait pas relire des données déjà migrées.

## Sources et contributions

[`sources.lock.json`](sources.lock.json) et [`composer.lock`](composer.lock)
identifient les versions utilisées pour construire l'image. Les mises à jour
amont sont validées automatiquement avant l'enregistrement de nouveaux locks.
La mise à jour d'une instance reste une opération explicite, décrite ci-dessus.

Pour modifier la recette, lancer les tests ou comprendre les contrôles CI,
consultez le [guide de contribution](CONTRIBUTING.md).

## Licences

- La recette (fichiers de ce dépôt) est sous licence
  [BSD-3-Clause](LICENSE), comme cachethq/Docker.
- **Cachet n'est pas sous cette licence.** Cachet 3 est distribué par Alt Three
  Services Limited sous la « Cachet license »
  ([`LICENSE.md`](https://github.com/cachethq/cachet/blob/3.x/LICENSE.md)), qui
  interdit notamment de le distribuer comme produit autonome. Son nom et ses
  logos relèvent de sa
  [politique de marque](https://github.com/cachethq/core/blob/main/TRADEMARKS.md).
  L'image construite conserve les fichiers de licence amont.
- FrankenPHP (MIT), PHP, les paquets Debian et les dépendances Composer restent
  sous leurs licences respectives.
