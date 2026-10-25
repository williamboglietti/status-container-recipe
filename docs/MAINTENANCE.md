# Maintenance et reprise — 25 octobre 2026

## Projet et périmètre

**Status v3** fournit une recette Docker communautaire pour
Cachet v3. Le dépôt de référence est
[`williamboglietti/status-v3`](https://github.com/williamboglietti/status-v3).
Il n'est ni affilié à Cachet ni approuvé par son équipe.

Le nom `status-v3` a été choisi par William le 25 octobre 2026. Le dépôt a été
renommé depuis `status-container-recipe`, en conservant son historique, ses
issues et ses pull requests.

La recette est sous BSD-3-Clause. Cachet, son core, FrankenPHP, PHP et les
dépendances conservent leurs propres licences. Aucun code amont, logo, image
construite, historique d'exploitation ou secret n'est inclus dans le dépôt.
Les sources amont ne sont téléchargées que dans le contexte local de build.

Le nom neutre distingue le projet de Cachet. Les références à Cachet dans la
description expliquent sa compatibilité. Références contrôlées le 25 octobre :
[licence Cachet](https://github.com/cachethq/cachet/blob/3.x/LICENSE.md),
[politique de marque](https://github.com/cachethq/core/blob/main/TRADEMARKS.md).
La licence limite notamment la distribution du logiciel comme produit autonome ;
les usages de marque sont soumis à une politique distincte.

## Architecture retenue

| Élément | Responsabilité |
| --- | --- |
| Dépôt public | Dockerfile, scripts, Compose, tests, documentation et locks |
| CI publique | Construire temporairement les deux architectures, tester, scanner, enregistrer les seuls locks validés |
| Artifacts publics | Locks et rapports synthétiques/scanner uniquement ; aucune image, couche, archive amont ou donnée applicative |
| Poste utilisateur | Construire et tester sa propre image à partir de la recette |
| Constructeur privé distinct | Adopter un SHA public vérifié, construire et tester, puis publier dans son registre privé |
| Exploitation | Déploiement, données persistantes et sauvegardes gérés séparément |

Le dépôt privé existant continue d'exister avec son historique. Il ne doit pas
être archivé ou renommé avant reprise vérifiée de la construction privée, des
anciens digests et des consommateurs. Ce projet public ne change aucun serveur.

## État de la reprise

- Sources de la préparation locale reprises dans un dépôt neuf, sans son
  historique Git, ses dossiers de build ou ses données de test.
- Documentation, Makefile, Compose et liens alignés sur le nouveau nom.
- Suppression des connexions GHCR, droits `packages:write`, pushes d'images et
  promotion de tags dans la CI publique. Les images restent sur les runners.
- Correction des arguments de build et exclusion des caches Python de
  l'empreinte de recette, avec tests unitaires ciblés.
- Les contrôles statiques et les tests d'images doivent être distingués. Une
  exécution historique réussie de la préparation ne valide pas ce nouveau commit.
- Réception locale du 25 octobre : `make lint`, neuf tests unitaires, syntaxe
  des neuf fichiers Python, `docker compose config --quiet`, cohérence des SHA
  du lock Composer/core et absence d'authentification à un registre ou de
  publication d'image dans les deux workflows.
  Aucun moteur Docker n'était disponible sur ce Mac pour recevoir l'image ; les
  tests des deux architectures et des bases sont à recevoir dans la nouvelle CI.

## Lot suivant pour un agent

1. Lire `AGENTS.md`, `CONTRIBUTING.md`, ce document et les dernières CI du SHA
   traité. Reproduire un échec avant de le corriger.
2. Recevoir la CI `Source checks`, puis `Build and validate recipe` : AMD64 et
   ARM64 natifs, SQLite/PostgreSQL/MySQL/MariaDB, login, persistance, healthchecks,
   Compose et scanner. Conserver les échecs comme tels ; un artefact de locks
   candidats ne prouve pas une validation complète.
3. Dans le constructeur privé, préparer une branche qui consomme un SHA public
   immuable. Le contrat HTTP de cette recette est le port **8000** ; vérifier
   les différences avec les anciennes recettes avant leur adoption.
4. Recevoir le registre privé et ses permissions. Un package GHCR peut conserver
   une visibilité privée tout en héritant de droits d'un dépôt lié ; la
   [documentation GitHub](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
   décrit ces deux réglages distincts. Ne pas lier ce publisher à un dépôt public.
5. Tester la migration et la restauration avec `--previous image@sha256:...` dans
   ce contexte privé. Les tests publics n'ont pas accès à une ancienne image
   privée et ne prétendent pas avoir exercé ce chemin.
6. Documenter les digests, les consommateurs et le retour arrière avant toute
   proposition d'archivage. Garder les opérations serveur dans leur lot propre.

Le premier lot peut avancer entièrement dans ce dépôt public. Les étapes
privées doivent conserver les identités et secrets hors des issues publiques.
