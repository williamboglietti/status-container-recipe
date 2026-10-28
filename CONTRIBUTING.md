# Guide de contribution

## Signaler un problème

Ouvrez une [issue](https://github.com/williamboglietti/status-v3/issues) pour un
problème de construction, de configuration ou de fonctionnement du conteneur.
Indiquez le commit utilisé, l'architecture, les versions de Docker et Compose,
les étapes de reproduction et le résultat attendu.

Pour un problème du logiciel Cachet lui-même, utilisez le dépôt amont
[cachethq/cachet](https://github.com/cachethq/cachet/issues).

Ne joignez pas de clé `APP_KEY`, de mot de passe, de dump, de fichier `.env`
ou de contenu de `.secrets/` à une issue ou à une pull request.

## Proposer une modification

Créez une branche depuis `main`, puis une pull request qui décrit le problème,
le changement proposé et les contrôles réellement exécutés. Gardez chaque PR
centrée sur un sujet et mettez à jour la documentation utilisateur si le
comportement change.

`main` contient le code et la documentation publics du projet. Les documents
publiés doivent aider à installer, utiliser, développer ou contribuer à la
recette.

## Environnement de développement

La construction et les tests demandent Docker avec Compose et Buildx, `make`
et Python 3.12+. Les contrôles statiques utilisent `actionlint` et `shellcheck`.
Les scripts Python utilisent uniquement la bibliothèque standard.

```sh
make lint
make test-unit
make build
make test
```

Les tests d'intégration créent des conteneurs, volumes et identifiants
synthétiques, puis les suppriment à la fin. Ils ne doivent pas utiliser une
instance en service ni ses données.

| Commande | Contrôle |
| --- | --- |
| `make lint` | Workflows GitHub Actions et scripts shell |
| `make test-unit` | Outils de build, arguments et empreintes, sans Docker |
| `make test-image` | Installation SQLite, connexion et persistance |
| `make test-healthcheck` | Rôles web, worker et scheduler, y compris un worker interrompu |
| `make test-pgsql`, `make test-mysql`, `make test-mariadb` | Installation et persistance avec chaque moteur |
| `make test-compose` | Démarrage et redémarrage du fichier Compose fourni |
| `make test` | Ensemble des contrôles unitaires et d'intégration |

`IMAGE` permet de choisir le nom de l'image locale et `PLATFORM` sa plateforme,
par exemple `make build IMAGE=status-v3:dev PLATFORM=linux/arm64`.

Pour tester une migration depuis une image précédente et la restauration des
données synthétiques associées, fournissez son digest immuable :

```sh
python3 test/test-image.py --image status-v3:local \
  --previous 'exemple/image@sha256:<digest>'
python3 test/test-database.py --image status-v3:local --database pgsql \
  --previous 'exemple/image@sha256:<digest>'
```

Remplacez l'image et le digest par une référence accessible dans votre
environnement. Sans `--previous`, ces scénarios de migration et de restauration
ne sont pas exécutés.

## Sources et dépendances

`sources.lock.json` et `composer.lock` fixent les commits Cachet, les dépendances
Composer et les digests des images de base. Pour les actualiser :

```sh
make update-dependencies
```

Cette commande résout les nouvelles entrées et modifie les locks. Construisez
et testez l'image avant de proposer leur mise à jour ; ne les éditez pas à la
main. L'empreinte de recette exclut les caches Python et fichiers générés.

## Intégration continue

[`checks.yml`](.github/workflows/checks.yml) contrôle les sources à chaque
pull request et push sur `main` : actionlint, ShellCheck, tests unitaires,
syntaxe Python et validation Compose.

[`image.yml`](.github/workflows/image.yml) construit et teste les images sur
des runners natifs AMD64 et ARM64 à chaque pull request, sur la branche `main`
et selon le calendrier. Il vérifie les entrées amont toutes les deux heures,
résout les dépendances Composer quotidiennement et reconstruit sans cache
chaque semaine ISO UTC. Un lancement manuel demande également une validation.

Le workflow vérifie les installations SQLite, PostgreSQL, MySQL et MariaDB,
les rôles et le fichier Compose. `composer audit` et Trivy bloquent les
vulnérabilités selon les critères définis dans le workflow. Les locks ne sont
enregistrés qu'après réussite des deux architectures et si `main` n'a pas
changé pendant les tests.

Les pull requests utilisent `checks.yml` et la partie build/test de `image.yml` ;
elles ne reçoivent aucun identifiant GHCR. Le workflow d'image construit des
images temporaires ; il ne publie aucune image publiquement, aucune couche et
aucune archive de sources amont. Après réussite des deux architectures, des
tests et de Trivy sur `main`, il peut publier les digests testés dans le package
privé `ghcr.io/williamboglietti/status-v3`.

La publication privée est activée dès que le secret Actions
`STATUS_V3_GHCR_TOKEN` est configuré. Le secret doit être un PAT classic limité
à `read:packages` et `write:packages`, sans scope `repo`. Sans ce secret, la CI
continue de valider les images mais ne publie rien. Le secret n'est utilisé que
par les workflows de `main`, jamais par les tests de pull request. Après succès
des tests et du scanner, le workflow publie l'image privée ; il ne déclenche
aucun déploiement.

Un lancement manuel sur une branche autre que `main` valide les deux images
sans accès GHCR, sans mise à jour des locks et sans publication. Les jobs de
publication et d'enregistrement des locks sont réservés à `main`.

Le package GHCR doit rester privé et sans héritage d'accès du dépôt public. Le
workflow vérifie sa visibilité avant la promotion des tags `v3` et `latest`.
L'image ne porte pas le label OCI `org.opencontainers.image.source`, afin que
GHCR ne la lie pas automatiquement aux permissions publiques du dépôt. Les
artifacts ne contiennent que les locks, les rapports synthétiques/scanner et
les reçus SHA256 des candidats testés, jamais les couches ou l'image.

## Contrats à préserver

- `web`, `worker` et `scheduler` ne migrent ni n'initialisent la base ; ces
  opérations utilisent les commandes explicites `migrate` et `initialize`.
- Le mode démonstration et `APP_DEBUG=true` restent refusés.
- Les secrets sont lus à l'exécution et restent absents de Git, de l'image et
  des journaux.
- Les fichiers de licence et attributions amont restent dans l'image. Le projet
  est indépendant de Cachet ; respecter sa
  [politique de marque](https://github.com/cachethq/core/blob/main/TRADEMARKS.md).
- Chaque action GitHub est épinglée par SHA.
