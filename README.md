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

## PR Agent Commands

These commands can be used as comments on any PR (with `issue_comment` trigger configured) or run automatically via the workflow:

| Command | Description |
|---------|-------------|
| `/review` | Full PR review with feedback on code quality, security, and consistency |
| `/describe` | Generates a PR title and description based on the changes |
| `/improve` | Suggests specific code improvements with before/after examples |
| `/ask "question"` | Ask any question about the PR |
| `/add_docs` | Adds documentation docstrings to new/changed code |
| `/generate_labels` | Suggests appropriate labels for the PR |
| `/update_changelog` | Automatically updates CHANGELOG.md |
| `/help` | Shows all available commands |

The workflow on `main` currently has **auto_review**, **auto_describe**, and **auto_improve** enabled — they run automatically on every new PR without needing a comment.

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
    types: [opened, synchronize, reopened, ready_for_review]
  issue_comment:

jobs:
  pr_agent_job:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get changed files
        id: files
        uses: tj-actions/changed-files@v44
        with:
          separator: ","

      - name: Get memory context from dashboard
        id: memory
        run: |
          FILES="${{ steps.files.outputs.all_changed_files }}"
          RESPONSE=$(curl -s "https://ton-domaine-c…emory?repo=${{ github.repository }}&pr=${{ github.event.number }}&files=$FILES")
          CONTEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('context',''))")
          echo "context<<EOF" >> $GITHUB_OUTPUT
          echo "$CONTEXT" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      - uses: the-pr-agent/pr-agent@main
        env:
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          OPENAI.API_BASE: "https://api.scaleway.ai/${{ secrets.SCALEWAY_PROJECT_ID }}/v1"
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          config.model: "openai/gemma-4-26b-a4b-it"
          config.fallback_models: '["openai/gemma-4-26b-a4b-it"]'
          config.custom_model_max_tokens: "32768"
          pr_reviewer.model: "openai/gemma-4-26b-a4b-it"
          pr_reviewer.extra_instructions: ${{ steps.memory.outputs.context }}
          github_action_config.auto_review: "true"
          github_action_config.auto_describe: "true"
          github_action_config.auto_improve: "true"
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
