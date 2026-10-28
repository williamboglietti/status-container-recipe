# Consignes pour les agents

- Lire [README.md](README.md) et [CONTRIBUTING.md](CONTRIBUTING.md).
- Partir de `main` dans une branche `codex/…` et proposer une pull request.
- Garder la documentation de `main` destinée aux utilisateurs et contributeurs.
  Les passations, notes de session et consignes personnelles restent sur une
  branche de coordination séparée ; ne pas les inclure dans les pull requests.
- Ne jamais publier d'image publiquement ni envoyer des couches, des sources
  amont ou un cache de build dans les artifacts. Le publisher mainteneur ne peut
  pousser que vers un package GHCR privé, isolé des permissions publiques du
  dépôt, après réussite des contrôles AMD64, ARM64 et du scanner. Le secret de
  publication est réservé aux événements de `main`, jamais aux pull requests.
  Conserver les licences et attributions amont dans l'image.
- Ne jamais versionner de secrets ou de données d'exploitation.
- Exécuter les contrôles adaptés au changement et les indiquer dans la PR.
