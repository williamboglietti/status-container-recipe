# Guide de contribution

## Signaler un problème

Les demandes d'évolution et les rapports de bug passent par le
[gestionnaire d'issues](https://github.com/williamboglietti/status-container-recipe/issues).
Ce dépôt est une recette communautaire, sans lien avec l'équipe de Cachet : un
problème de Cachet lui-même se signale en amont, sur
[cachethq/cachet](https://github.com/cachethq/cachet/issues). Le support est
assuré au mieux.

Ne joignez jamais d'`APP_KEY`, de mot de passe, de dump de base de données ni
de contenu de `.secrets/` à une issue.

## Branches et validation

- `main` contient la recette publique et ses locks. Préparer les évolutions dans
  une branche, puis une pull request ; les agents utilisent le préfixe `codex/`.
- Les contrôles de sources tournent sur les pull requests. Chaque push sur
  `main` construit et teste les images sur `linux/amd64` et `linux/arm64`.
- Les mises à jour amont sont vérifiées toutes les deux heures, avec résolution
  Composer quotidienne et reconstruction hebdomadaire sans cache.
- Après réussite des deux architectures, le workflow enregistre seulement
  `sources.lock.json` et `composer.lock` dans un commit de mise à jour.
- La CI publique n'a aucun accès aux packages et ne publie aucune image, couche,
  archive de sources amont ou sauvegarde. Les artifacts contiennent seulement
  les locks et les rapports des données synthétiques ou du scanner.

Pour forcer une validation : **Actions → Build and validate recipe → Run workflow**.

## Image privée et reprise

L'image se construit chez l'utilisateur. Un registre d'images privées se gère
à partir d'un dépôt de construction privé séparé, en épinglant un commit de la
recette publique. La confidentialité du registre et ses permissions doivent
être reçues avant toute publication privée. Ne pas convertir le dépôt privé
existant en public ni l'archiver pendant cette préparation.

Le [point de reprise](docs/MAINTENANCE.md) décrit l'architecture, les preuves
attendues et les travaux restants. Aucune version de cette recette ne constitue
une autorisation de modifier un serveur.

## Règles du projet

- `sources.lock.json` et `composer.lock` décrivent exactement ce qui a été
  testé. Seuls `scripts/resolve.py` (`make update-dependencies`) et la CI les
  modifient.
- Ne pas ajouter de publication d’image ou de cache de build aux workflows
  publics. Les anciens digests privés relèvent du constructeur privé.
- Aucune clé `APP_KEY`, aucun mot de passe, token, fichier `.env`, base de
  données ou upload dans Git ou dans l'image.
- `web`, `worker` et `scheduler` ne migrent ni n'initialisent jamais la base.
  `migrate` et `initialize` restent des commandes explicites.
- Pas de seeder de démonstration ; le mode démo et `APP_DEBUG` restent
  interdits dans l'image.
- Conserver la distribution amont, ses fichiers de licence et ses
  attributions. Ne pas utiliser le logo de Cachet ni présenter ce dépôt comme
  officiel ([politique de marque](https://github.com/cachethq/core/blob/main/TRADEMARKS.md)).
- Épingler toute action GitHub par SHA. La CI n'utilise que `GITHUB_TOKEN` et
  les runners hébergés par GitHub.

## Avant une pull request

```sh
make lint                # actionlint et shellcheck
make test-unit           # outils sans Docker
make build               # image locale status-container-recipe:local
make test                # SQLite, PostgreSQL, MySQL, MariaDB et docker-compose.yml
```

Décrivez dans la pull request les contrôles réellement lancés. Un test sur des
données synthétiques ne prouve pas la restauration d'une instance réelle.
