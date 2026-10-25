# Passation conservée avant nettoyage de la documentation publique

Issue source : https://github.com/williamboglietti/status-v3/issues/1

Titre initial : Réception initiale et adoption de la recette par un constructeur privé

État capturé le 25 octobre 2026, avant réorganisation demandée par William.

---

Le projet public est structuré et publié sur `main` au commit `afa10e70e941f58c0d45540d0025eb317917494f` (réception ShellCheck intégrée par #2).

Lire d’abord [AGENTS.md](https://github.com/williamboglietti/status-v3/blob/main/AGENTS.md), [CONTRIBUTING.md](https://github.com/williamboglietti/status-v3/blob/main/CONTRIBUTING.md) et [le point de reprise](https://github.com/williamboglietti/status-v3/blob/main/docs/MAINTENANCE.md). La CI publique construit et teste sans authentification à un registre ni publication d’image. Les sources amont restent dans les contextes temporaires de build.

Réception locale du 25 octobre 2026 : actionlint, shellcheck, neuf tests unitaires, syntaxe des neuf fichiers Python, Compose et cohérence des locks réussis. Les tests d’images du nouveau commit restent à recevoir dans GitHub Actions ; les anciens tests de la préparation ne les remplacent pas.

- [x] Reprendre les sources dans un dépôt neuf, avec nom neutre, BSD-3-Clause pour la recette et licences amont distinctes.
- [x] Séparer les builds publics de la publication des images privées ; retirer les droits packages et tous les pushes d’images des workflows publics.
- [x] Corriger le passage des arguments de build et les empreintes dépendantes des caches Python, avec tests de régression.
- [x] Recevoir `Source checks` sur le SHA publié : [run 40213445370](https://github.com/williamboglietti/status-v3/actions/runs/40213445370), réussi sur `afa10e70e941f58c0d45540d0025eb317917494f`.
- [x] Première réception de `Build and validate recipe` : [run 40213445384](https://github.com/williamboglietti/status-v3/actions/runs/40213445384), réussi sur `afa10e70e941f58c0d45540d0025eb317917494f` pour AMD64 et ARM64 natifs, SQLite/PostgreSQL/MySQL/MariaDB, login, persistance, healthchecks, Compose et scanner. Les locks validés sont enregistrés au commit `624adbb`.
- [ ] Préparer dans un constructeur privé une branche qui consomme un SHA public immuable, avec contrôle du port 8000 et des autres écarts de contrat.
- [ ] Recevoir la confidentialité du package et ses permissions, puis les tests `--previous image@sha256:...` de migration/restauration dans ce contexte privé.
- [ ] Documenter les consommateurs et le retour arrière avant toute éventuelle proposition d’archivage de l’ancien dépôt privé.

Travailler par branche et PR pour les suites. Ne pas inclure de secrets, noms d’hôtes privés ou données d’exploitation dans cette issue. Cette issue de préparation ne déclenche aucun déploiement serveur.

Au relevé du 25 octobre après intégration de #2, la validation des images est en cours : [run 40213445384](https://github.com/williamboglietti/status-v3/actions/runs/40213445384), SHA `afa10e70e941f58c0d45540d0025eb317917494f`, résolution des entrées de build. Vérifier son état terminal avant de valider la case correspondante. Le premier run du SHA précédent a été annulé au profit de cette tête corrigée.


Nom retenu par William le 25 octobre : **status-v3**. Le dépôt a été renommé en conservant ses issues, PR et historique. Le clone local porte également ce nom. [PR3](https://github.com/williamboglietti/status-v3/pull/3) fusionnée au commit `ab1c680b79abd1853d7f8f479449229adbb0ba1b` : liens, titres, labels et tags locaux alignés. [Source checks de la PR](https://github.com/williamboglietti/status-v3/actions/runs/40214094250) reçus ; [nouvelle validation d’images](https://github.com/williamboglietti/status-v3/actions/runs/40214162804) lancée sur la tête renommée. La construction privée et ses tests de migration/restauration restent les lots suivants.

