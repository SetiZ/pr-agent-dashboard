# AGENT.md — PR-Agent Dashboard

## Qu'est-ce que ce projet ?

Un backend qui s'intercale entre **PR-Agent** (GitHub Action) et une base SQLite
pour ajouter deux fonctionnalités manquantes à PR-Agent :

1. **Mémoire persistante** — contexte des reviews passées injecté dans les nouvelles
2. **Dashboard** — statistiques et historique visibles via une interface web

## Architecture

```
GitHub (PR-Agent) ←→ API REST (FastAPI) ←→ SQLite
                     ↕
                  Dashboard HTML
```

## Structure du code

```
pr-agent-dashboard/
├── main.py         # Serveur FastAPI (endpoints, dashboard HTML)
├── database.py     # Modèle SQLite (init, CRUD, stats, mémoire)
├── models.py       # Pydantic models
├── Dockerfile      # Image Docker
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── AGENT.md
```

## Points importants pour l'agent

- **Base de données** : SQLite fichier unique (`pr_agent.db`). En Docker, mounté sur un volume pour persistance.
- **Webhook** : Accepte les events GitHub (`pull_request`, `issue_comment`, `pull_request_review`). Filtre les commentaires par `PR_AGENT_BOT_USERNAME`.
- **Mémoire** : Renvoie les 5 dernières reviews d'un repo. Un mécanisme plus fin (par fichier changé) peut être ajouté.
- **Dashboard** : Page HTML inline (pas de template externe ni de JS). Style dark theme GitHub.

## Conventions

- Les retours API sont toujours des dict Python (pas de ORM, SQL brut).
- Les timestamps sont UTC stockés en texte ISO 8601.
- Le mot-clé `repo` est toujours au format `owner/name`.
- Les routes REST sont préfixées : `/webhook`, `/memory`, `/reviews`, `/stats`.

## Extension possible

- Webhook Slack/Discord pour notifier les nouvelles reviews
- Parsing des suggestions pour catégoriser (sécu, perf, style…)
- API `/reviews/{id}/suggestions` pour les suggestions détaillées
- UI avec filtre par repo, date, catégorie

## Déploiement

Coolify → Docker Compose. Variables d'env dans l'interface Coolify.
