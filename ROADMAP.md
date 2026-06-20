# Roadmap — PR-Agent Dashboard

Idees d'améliorations à implémenter.

## Court terme

- [ ] **Détail d'une review** — Cliquer sur un PR dans le dashboard pour voir le body complet, les suggestions détaillées, et les métadonnées (score, effort, etc.)
- [ ] **Filtre par repo** — Sidebar ou dropdown pour filtrer les reviews par dépôt
- [ ] **Date range picker** — Choisir une période custom pour les stats (pas seulement 30 jours)
- [ ] **UI pour instructions personnalisées** — Formulaire dans le dashboard pour définir les custom review instructions par repo (au lieu de curl)

## Moyen terme

- [ ] **Timeline / graphique** — Nombre de reviews par jour/semaine pour visualiser l'activité
- [ ] **Recherche** — Chercher dans le corps des reviews (mots-clés, suggestions, etc.)
- [ ] **Auto-refresh** — Rafraîchissement automatique ou pull-to-refresh
- [ ] **Diff view** — Afficher les fichiers changés en regard de la review correspondante

## Long terme

- [ ] **Notifications** — Slack / Discord webhook quand une review est prête
- [ ] **Multi-utilisateur / auth** — Login basique pour protéger le dashboard
- [ ] **Export** — Exporter les reviews en CSV ou JSON
