# Coordination du projet status-v3

Cette branche `codex/project-coordination` conserve les décisions, passations,
preuves de travail et prochaines étapes personnelles de maintenance du projet.
Elle n'est pas destinée à être fusionnée globalement dans `main`.

## Règle choisie par William le 25 octobre 2026

- `main` présente le projet aux utilisateurs et aux contributeurs : code,
  installation, configuration, mises à jour, licences et guide de contribution.
- `AGENTS.md` est l'unique point d'entrée concis pour les agents sur `main`.
- Les notes de session, consignes personnelles, passations et états de
  préparation restent dans cette branche de coordination.
- Les évolutions publiques partent de `origin/main` sur une branche dédiée et
  sont intégrées par pull request. Ne pas emporter les notes de cette branche.
- Les secrets et données d'exploitation restent hors Git sur toutes les branches.

## Documents conservés

- [Passation et plan de maintenance](../docs/MAINTENANCE.md).
- [Copie de l'issue1 avant réorganisation](ISSUE-1-HANDOFF.md).

## État au début de cette réorganisation

- Projet public renommé en `status-v3`, `main` à `ab1c680`.
- Première validation complète des deux architectures et moteurs de base reçue
  sur `afa10e7`, run40213445384 ; locks validés au commit `624adbb`.
- Validation de la tête renommée suivie dans le run40214162804 ; vérifier son
  résultat terminal avant de l'annoncer reçue.
- La construction privée, la réception des permissions du package et les tests
  de migration/restauration depuis l'ancienne image privée restent à préparer.
- `cachet-status` privé et le dossier original `_public-prep/cachet-status`
  sont préservés. Aucune opération sur un serveur n'est autorisée par ces notes.

## Nettoyage public en cours

La passation `docs/MAINTENANCE.md` sera retirée de `main`, avec ses liens dans
le README et le guide de contribution. L'issue1 sera recentrée sur une validation
publique du produit ; son contenu personnel est conservé ci-dessus.
