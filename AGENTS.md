# Consignes pour les agents de code

Les règles du projet, les contrôles à lancer et le processus de publication
sont dans [CONTRIBUTING.md](CONTRIBUTING.md). Ils s'appliquent à toute
modification, qu'elle vienne d'une personne ou d'un agent.

Répondre en français. Lire aussi [le point de reprise](docs/MAINTENANCE.md).
Ce dépôt public contient la recette pour Cachet v3. Ses workflows ne doivent
avoir aucun accès à un registre ni publier une image, ses couches, les sources
amont ou un cache de build. Les données synthétiques des tests restent isolées.
Une image privée se construit depuis un autre dépôt privé, par SHA de recette.
Conserver les licences et attributions amont dans l'image. Employer le nom
Cachet seulement pour décrire la compatibilité ; ne pas présenter le projet
comme officiel. Travailler par branche et documenter les contrôles reçus.
