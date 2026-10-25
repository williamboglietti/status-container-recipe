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
- Validation complète de la tête renommée `ab1c680` reçue dans le
  run40214162804 : deux architectures, quatre bases, rôles, Compose et scanner.
  Locks enregistrés au commit `240b545`.
- La construction privée, la réception des permissions du package et les tests
  de migration/restauration depuis l'ancienne image privée restent à préparer.
- `cachet-status` privé et le dossier original `_public-prep/cachet-status`
  sont préservés. Aucune opération sur un serveur n'est autorisée par ces notes.

## Nettoyage de la documentation publique

[PR4](https://github.com/williamboglietti/status-v3/pull/4), tête `14acf5e` :
passation retirée de `main`, README centré sur l'installation et l'exploitation,
CONTRIBUTING centré sur le développement, AGENTS réduit aux règles essentielles.
Les cinq fichiers modifiés sont Markdown ; runtime et workflows inchangés.
Vérifier l'état de la PR et sa CI avant de poursuivre un développement public.

L'issue1 est recentrée sur la validation publique multiarchitecture et close
sur les preuves reçues. Sa passation personnelle initiale est conservée dans
`ISSUE-1-HANDOFF.md`. Les tâches du constructeur privé et de restauration depuis
un ancien digest restent ouvertes dans cette branche de coordination.
