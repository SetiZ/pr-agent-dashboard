# PR-Agent Dashboard 🧠📊

Dashboard + mémoire persistante pour PR-Agent, conçu pour tourner sur **Coolify**.

## Architecture

```
GitHub Action (PR-Agent)
     │
     ├── Avant review → GET /memory   → récupère le contexte des anciennes reviews
     └── Après review  ← Webhook GH   → stocke le commentaire dans la base
                                   │
                              ┌────▼────┐
                              │  Coolify │
                              │ (FastAPI)│
                              └────┬────┘
                                   │
                              ┌────▼────┐
                              │ SQLite   │
                              └─────────┘
```

## Fonctionnalités

| Endpoint | Méthode | Description |
|---|---|---|
| `GET /` | — | Dashboard web (stats + historique) |
| `GET /stats` | API | Stats JSON (reviews, PRs, suggestions) |
| `GET /reviews` | API | Historique des reviews |
| `GET /memory` | API | Contexte mémoire pour injecter dans PR-Agent |
| `POST /webhook` | API | Webhook GitHub (collecte les reviews) |
| `POST /memory/instructions` | API | Instructions de review personnalisées par repo |
| `GET /health` | API | Healthcheck |

## Déploiement sur Coolify

### 1. Déploie l'API

1. Dans Coolify → **Service** → **Docker Compose**
2. Colle le `docker-compose.yml` du projet
3. Configure la variable `APP_URL` avec ton domaine Coolify
4. Déploie

### 2. Configure le webhook GitHub

Va dans les settings de ton repo GitHub :

```
Settings → Webhooks → Add webhook
```

- **Payload URL** : `https://ton-domaine-c…t/webhook`
- **Content type** : `application/json`
- **Secret** : (optionnel, mets-en un et configure `GITHUB_WEBHOOK_SECRET`)
- **Events** : coche **Pull requests**, **Issue comments**, **Pull request reviews**

### 3. Ajoute la mémoire à PR-Agent

Crée (ou modifie) `.github/workflows/pr-agent.yml` :

```yaml
name: PR Agent with Memory
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  pr_agent_job:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: write
    steps:
      - name: Get memory context
        id: memory
        run: |
          RESPONSE=$(curl -s "https://ton-domaine-c…emory?repo=${{ github.repository }}&pr=${{ github.event.number }}")
          CONTEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('context',''))")
          echo "context<<EOF" >> $GITHUB_OUTPUT
          echo "$CONTEXT" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      - uses: the-pr-agent/pr-agent@main
        env:
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          pr_reviewer.extra_instructions: ${{ steps.memory.outputs.context }}
```

### 4. (Optionnel) Instructions personnalisées

```bash
curl -X POST https://ton-domaine-c…emory/instructions \
  -H "Content-Type: application/json" \
  -d '{"repo": "owner/repo", "instructions": "Vérifie les fuites mémoire dans les closures JS."}'
```

## Stack

- **Backend** : Python 3.12 + FastAPI
- **Base** : SQLite (fichier, pas de dépendance externe)
- **Déploiement** : Docker (Coolify-ready)
