
import os
import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from database import init_db, store_review, get_reviews, get_stats, get_memory_context, get_meta, set_meta
from models import MemoryRequest, CustomInstructions

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pr-agent-dashboard")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

PR_AGENT_BOT = os.getenv("PR_AGENT_BOT_USERNAME", "pr-agent[bot]")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log.info("Database ready at pr_agent.db")
    yield


app = FastAPI(title="PR-Agent Dashboard", version="0.1.0", lifespan=lifespan)


def verify_webhook(payload_body: bytes, signature_header: str | None) -> bool:
    if not WEBHOOK_SECRET:
        return True
    if not signature_header:
        return False
    sha_name, signature = signature_header.split("=", 1)
    if sha_name != "sha256":
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def github_webhook(request: Request):
    sig = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    if not verify_webhook(body, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")
    payload = await request.json()
    event = request.headers.get("X-GitHub-Event", "unknown")
    log.info("Webhook event=%s action=%s", event, payload.get("action"))

    if event == "pull_request" and payload.get("pull_request"):
        pr = payload["pull_request"]
        repo = pr["base"]["repo"]["full_name"]
        pr_number = pr["number"]
        pr_title = pr["title"]
        action = payload.get("action", "")
        if action in ("opened", "reopened", "synchronize"):
            store_review(repo=repo, pr_number=pr_number, pr_title=pr_title,
                         body=f"### PR #{pr_number}: {pr_title}\n\n*Review en attente...*",
                         author=pr["user"]["login"], comment_id=None)
            log.info("Tracked PR #%s in %s", pr_number, repo)

    elif event == "issue_comment" and payload.get("comment"):
        issue = payload.get("issue", {})
        if not issue.get("pull_request"):
            return {"ok": True, "ignored": "not a PR comment"}
        comment = payload["comment"]
        repo = payload["repository"]["full_name"]
        pr_number = issue["number"]
        pr_title = issue.get("title", "")
        author = comment["user"]["login"]
        body_text = comment["body"]
        comment_id = comment["id"]
        if author.lower() != PR_AGENT_BOT.lower():
            return {"ok": True, "ignored": "not PR-Agent bot"}
        rid = store_review(repo=repo, pr_number=pr_number, pr_title=pr_title,
                           body=body_text, author=author, comment_id=comment_id)
        log.info("Stored review #%s from PR-Agent on PR #%s/%s", rid, pr_number, repo)

    elif event == "pull_request_review" and payload.get("review"):
        review = payload["review"]
        pr = payload["pull_request"]
        repo = pr["base"]["repo"]["full_name"]
        pr_number = pr["number"]
        pr_title = pr["title"]
        author = review["user"]["login"]
        body_text = review.get("body", "")
        review_id_field = review.get("id")
        if author.lower() == PR_AGENT_BOT.lower():
            store_review(repo=repo, pr_number=pr_number, pr_title=pr_title,
                         body=body_text, author=author, comment_id=review_id_field)
            log.info("Stored PR review from PR-Agent on PR #%s/%s", pr_number, repo)

    return {"ok": True}


@app.get("/memory")
async def get_memory(repo: str = Query(...), pr_number: int = Query(...),
                     files: str = Query("")):
    files_list = [f.strip() for f in files.split(",") if f.strip()]
    context = get_memory_context(repo, files_list)
    if not context:
        return {"context": ""}
    custom = get_meta(repo, "review_instructions")
    if custom:
        context += f"\n\nInstructions personnalisées pour ce repo :\n{custom}\n"
    return {"context": context}


@app.post("/memory/instructions")
async def set_custom_instructions(instr: CustomInstructions):
    set_meta(instr.repo, "review_instructions", instr.instructions)
    return {"ok": True, "repo": instr.repo}


@app.get("/reviews")
async def list_reviews(repo: str | None = Query(None), limit: int = Query(50, ge=1, le=200),
                       offset: int = Query(0, ge=0)):
    rows = get_reviews(repo, limit, offset)
    return {"reviews": rows, "total": len(rows), "limit": limit, "offset": offset}


@app.get("/stats")
async def stats(days: int = Query(30, ge=1, le=365)):
    return get_stats(days)


STYLES = """
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem;max-width:1200px;margin:0 auto;}
h1{color:#58a6ff;margin-bottom:1.5rem;font-size:1.8rem;}
h2{color:#f0f6fc;margin:1.5rem 0 0.75rem;font-size:1.3rem;}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem;}
.stat-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.2rem;text-align:center;}
.stat-value{font-size:2rem;font-weight:700;color:#58a6ff;}
.stat-label{font-size:0.85rem;color:#8b949e;margin-top:0.3rem;}
table{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;}
th{background:#1c2128;padding:0.75rem 1rem;text-align:left;font-size:0.8rem;text-transform:uppercase;color:#8b949e;border-bottom:1px solid #30363d;}
td{padding:0.75rem 1rem;border-bottom:1px solid #21262d;font-size:0.9rem;}
tr:hover td{background:#1c2128;}
.badge{display:inline-block;background:#1f6feb33;color:#58a6ff;font-size:0.75rem;padding:0.15rem 0.5rem;border-radius:12px;}
.repo-link{color:#58a6ff;text-decoration:none;}
.repo-link:hover{text-decoration:underline;}
.pr-link{color:#c9d1d9;text-decoration:none;}
.pr-link:hover{color:#58a6ff;}
.preview{color:#8b949e;font-size:0.85rem;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.footer{margin-top:2rem;text-align:center;color:#484f58;font-size:0.8rem;}
</style>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    s = get_stats(30)
    recent = get_reviews(limit=20)
    rows = ""
    for r in recent:
        preview = r["body"][:120].replace("\n", " ").strip() if r["body"] else ""
        rows += f"<tr><td><a class='repo-link' href='/?repo={r['repo']}'>{r['repo']}</a></td>"
        rows += f"<td><a class='pr-link' href='https://github.com/{r['repo']}/pull/{r['pr_number']}' target='_blank'>#{r['pr_number']}</a></td>"
        rows += f"<td><div class='preview'>{preview}</div></td>"
        rows += f"<td><span class='badge'>{r['suggestions_count']}</span></td>"
        rows += f"<td>{r['created_at'][:10]}</td></tr>"

    if not rows:
        rows = "<tr><td colspan='5' style='text-align:center;color:#484f58;padding:2rem;'>Aucune review pour l'instant. Configure le webhook GitHub.</td></tr>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>PR-Agent Dashboard</title>{STYLES}</head>
<body>
<h1>📊 PR-Agent Dashboard</h1>
<div class="stats-grid">
<div class="stat-card"><div class="stat-value">{s['total_reviews']}</div><div class="stat-label">Reviews (30j)</div></div>
<div class="stat-card"><div class="stat-value">{s['prs']}</div><div class="stat-label">PRs reviewées</div></div>
<div class="stat-card"><div class="stat-value">{s['repos']}</div><div class="stat-label">Repos actifs</div></div>
<div class="stat-card"><div class="stat-value">{s['total_suggestions']}</div><div class="stat-label">Suggestions émises</div></div>
<div class="stat-card"><div class="stat-value">{s['avg_suggestions']:.1f}</div><div class="stat-label">Suggestions/review</div></div>
<div class="stat-card"><div class="stat-value">{s['reviews_per_day']:.1f}</div><div class="stat-label">Reviews/jour</div></div>
</div>
<h2>Dernières reviews</h2>
<table><thead><tr><th>Repo</th><th>PR</th><th>Aperçu</th><th>Suggestions</th><th>Date</th></tr></thead><tbody>{rows}</tbody></table>
<div class="footer">PR-Agent Dashboard v0.1 · <a href="/docs" style="color:#58a6ff;">API docs</a></div>
</body></html>""")


@app.get("/health")
async def health():
    return {"status": "ok"}
