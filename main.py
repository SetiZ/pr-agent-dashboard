
import os
import hashlib
import hmac
import html
import json
import logging
from contextlib import asynccontextmanager

import bleach
import mistune
from dotenv import load_dotenv
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from fastapi import FastAPI, Request, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from database import init_db, store_review, get_reviews, get_stats, get_meta, set_meta, upsert_pr, get_prs_with_reviews, get_reviews_by_day, get_all_repos_summary
from models import CustomInstructions

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
        if action in ("opened", "reopened"):
            upsert_pr(repo, pr_number, pr_title, "open")
            store_review(repo=repo, pr_number=pr_number, pr_title=pr_title,
                         body=f"### PR #{pr_number}: {pr_title}\n\n*Review en attente...*",
                         author=pr["user"]["login"], comment_id=None)
            log.info("Tracked PR #%s in %s", pr_number, repo)
        elif action == "closed":
            merged = pr.get("merged", False)
            state = "merged" if merged else "closed"
            upsert_pr(repo, pr_number, pr_title, state)
            log.info("PR #%s in %s → %s", pr_number, repo, state)

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
        if author.lower() not in ("pr-agent[bot]", "github-actions[bot]"):
            return {"ok": True, "ignored": "not a known bot"}
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
        if author.lower() in ("pr-agent[bot]", "github-actions[bot]"):
            store_review(repo=repo, pr_number=pr_number, pr_title=pr_title,
                         body=body_text, author=author, comment_id=review_id_field)
            log.info("Stored PR review from PR-Agent on PR #%s/%s", pr_number, repo)

    return {"ok": True}


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


@app.get("/api/timeline")
async def timeline(days: int = Query(30, ge=1, le=365)):
    return get_reviews_by_day(days)


@app.get("/api/repo/{repo:path}/prs")
async def repo_prs(repo: str):
    data = get_prs_with_reviews(repo)
    return {"repo": repo, "prs": data}


PYGMENTS_CSS = HtmlFormatter(style="monokai").get_style_defs(".highlight")


class _HighlightRenderer(mistune.HTMLRenderer):
    def block_code(self, code: str, info: str | None = None) -> str:
        if info:
            try:
                lexer = get_lexer_by_name(info, stripall=False)
                return highlight(code, lexer, HtmlFormatter(style="monokai"))
            except Exception:
                pass
        return f"<pre><code>{html.escape(code)}</code></pre>"


mistune_md = mistune.create_markdown(renderer=_HighlightRenderer(escape=False))

STYLES = """
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem;max-width:1200px;margin:0 auto;}
h1{color:#58a6ff;margin-bottom:1.5rem;font-size:1.8rem;}
h2{color:#f0f6fc;margin:1.5rem 0 0.75rem;font-size:1.3rem;}
h3{color:#f0f6fc;margin:1rem 0 0.5rem;font-size:1.1rem;}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem;}
.stat-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.2rem;text-align:center;}
.stat-value{font-size:2rem;font-weight:700;color:#58a6ff;}
.stat-label{font-size:0.85rem;color:#8b949e;margin-top:0.3rem;}
table{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;}
th{background:#1c2128;padding:0.75rem 1rem;text-align:left;font-size:0.8rem;text-transform:uppercase;color:#8b949e;border-bottom:1px solid #30363d;}
td{padding:0.75rem 1rem;border-bottom:1px solid #21262d;font-size:0.9rem;}
tr:hover td{background:#1c2128;}
.badge{display:inline-block;background:#1f6feb33;color:#58a6ff;font-size:0.75rem;padding:0.15rem 0.5rem;border-radius:12px;}
.repo-link{color:#58a6ff;text-decoration:none;}
.repo-link:hover{text-decoration:underline;}
.pr-link{color:#c9d1d9;text-decoration:none;}
.pr-link:hover{color:#58a6ff;}
.footer{margin-top:2rem;text-align:center;color:#484f58;font-size:0.8rem;}
.back-link{display:inline-block;margin-bottom:1rem;color:#8b949e;text-decoration:none;font-size:0.9rem;}
.back-link:hover{color:#58a6ff;}
.state-open{color:#3fb950;font-size:0.75rem;padding:0.15rem 0.5rem;border:1px solid #3fb95055;border-radius:12px;}
.state-merged{color:#d2a8ff;font-size:0.75rem;padding:0.15rem 0.5rem;border:1px solid #d2a8ff55;border-radius:12px;}
.state-closed{color:#f85149;font-size:0.75rem;padding:0.15rem 0.5rem;border:1px solid #f8514955;border-radius:12px;}
.detail-btn{background:none;border:none;color:#58a6ff;cursor:pointer;font-size:0.85rem;}
.detail-btn:hover{text-decoration:underline;}
details.review-details{background:#161b22;border:1px solid #30363d;border-radius:6px;margin:0.5rem 0;padding:0.5rem 1rem;}
details.review-details summary{cursor:pointer;color:#c9d1d9;padding:0.3rem 0;}
details.review-details .body{color:#c9d1d9;font-size:0.85rem;line-height:1.5;padding:0.5rem 0;max-width:100%;}
details.review-details .body pre{overflow-x:auto;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:0.75rem;max-height:400px;}
details.review-details .body code{font-family:'SFMono-Regular',Consolas,monospace;font-size:0.85rem;}
details.review-details .body details{background:#0d1117;border:1px solid #30363d;border-radius:6px;margin:0.5rem 0;padding:0.5rem 0.75rem;}
details.review-details .body details summary{cursor:pointer;color:#58a6ff;font-weight:600;}
details.review-details .body table{display:block;overflow-x:auto;max-width:100%;}
details.review-details .body .highlight{background:#272822;border-radius:6px;padding:0.75rem;overflow-x:auto;}
.timeline{display:flex;align-items:end;gap:2px;height:100px;padding:0.5rem 0;margin-bottom:1.5rem;}
.timeline-bar{flex:1;background:#1f6feb;border-radius:2px 2px 0 0;min-width:4px;position:relative;transition:background 0.2s;}
.timeline-bar:hover{background:#58a6ff;}
.timeline-bar .tooltip{display:none;position:absolute;bottom:100%;left:50%;transform:translateX(-50%);background:#1c2128;color:#c9d1d9;padding:0.25rem 0.5rem;border-radius:4px;font-size:0.7rem;white-space:nowrap;z-index:10;border:1px solid #30363d;}
.timeline-bar:hover .tooltip{display:block;}
.timeline-empty{color:#484f58;text-align:center;padding:1rem;}
.section-label{display:flex;align-items:center;gap:0.5rem;margin:1.5rem 0 0.75rem;}
.section-label .count{color:#8b949e;font-size:0.85rem;}
@media(max-width:640px){
body{padding:1rem;}
h1{font-size:1.4rem;}
table{font-size:0.8rem;}
th,td{padding:0.5rem;}
th:nth-child(3),td:nth-child(3){display:none;}
th:nth-child(4),td:nth-child(4){display:none;}
.repo-link{font-size:0.8rem;}
.badge{font-size:0.65rem;}
.detail-btn{font-size:0.75rem;}
.stats-grid{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.5rem;}
.stat-card{padding:0.75rem;}
.stat-value{font-size:1.5rem;}
.stat-label{font-size:0.75rem;}
.footer{font-size:0.7rem;}
details.review-details{padding:0.4rem 0.6rem;}
details.review-details summary{font-size:0.8rem;}
.back-link{font-size:0.8rem;}
}
</style>
"""

FULL_STYLES = STYLES.replace("</style>", f"\n{PYGMENTS_CSS}\n</style>")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    repos = get_all_repos_summary()

    repo_cards = ""
    if repos:
        for repo_info in repos:
            repo_cards += f"""
            <a href='/repo/{repo_info['repo']}' style='text-decoration:none;'>
            <div style='background:#161b22;border:1px solid #30363d;border-radius:8px;padding:0.75rem 1rem;display:flex;align-items:center;gap:1rem;'>
                <span style='color:#58a6ff;font-weight:600;flex:1;'>{repo_info['repo']}</span>
                <span class='badge'>{repo_info['pr_count']} PRs</span>
                <span class='badge'>{repo_info['review_count']} reviews</span>
            </div>
            </a>"""
    else:
        repo_cards = "<p style='color:#484f58;text-align:center;padding:2rem;'>Aucune review pour l'instant. Configure le webhook GitHub.</p>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PR-Agent Dashboard</title>{FULL_STYLES}</head>
<body>
<h1>📊 PR-Agent Dashboard</h1>
<h2>📂 Dépôts</h2>
<div style="display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1.5rem;">{repo_cards}</div>
<div class="footer">PR-Agent Dashboard · <a href="/docs" style="color:#58a6ff;">API docs</a></div>
</body></html>""")


@app.post("/repo/{repo:path}/instructions")
async def update_instructions(repo: str, instructions: str = Form("")):
    set_meta(repo, "review_instructions", instructions)
    return RedirectResponse(url=f"/repo/{repo}", status_code=303)


@app.get("/repo/{repo:path}", response_class=HTMLResponse)
async def repo_detail(repo: str):
    data = get_prs_with_reviews(repo)
    timeline_data = get_reviews_by_day(30)

    total_reviews = sum(len(pr["reviews"]) for pr in data)
    open_prs = sum(1 for pr in data if pr["state"] == "open")
    merged_prs = sum(1 for pr in data if pr["state"] == "merged")
    closed_prs = sum(1 for pr in data if pr["state"] == "closed")
    current_instructions = get_meta(repo, "review_instructions") or ""

    timeline_bars = ""
    if timeline_data:
        max_count = max(d["count"] for d in timeline_data) or 1
        for d in timeline_data:
            h = max(3, int(d["count"] / max_count * 90))
            timeline_bars += f"<div class='timeline-bar' style='height:{h}px'><span class='tooltip'>{d['date']}: {d['count']}</span></div>"
    else:
        timeline_bars = "<div class='timeline-empty'>Aucune review ces 30 derniers jours</div>"

    pr_sections = {"open": "", "merged": "", "closed": ""}
    for pr in data:
        state = pr["state"]
        state_label = {"open": "🟢 open", "merged": "🟣 merged", "closed": "🔴 closed"}
        state_class = {"open": "state-open", "merged": "state-merged", "closed": "state-closed"}
        reviews_html = ""
        for r in pr["reviews"]:
            raw = mistune_md(r["body"])
            body = bleach.clean(raw,
                tags=["p","h1","h2","h3","h4","h5","h6","ul","ol","li",
                      "pre","code","strong","em","a","blockquote","hr","br",
                      "table","thead","tbody","tr","th","td","div","span",
                      "details","summary"],
                attributes={"a": ["href","target"], "*": ["class"]})
            reviews_html += f"""
            <details class='review-details'>
                <summary>Review #{r['id']} — {r['created_at'][:16]} <span class='badge'>{r['suggestions_count']} suggestions</span></summary>
                <div class='body'>{body}</div>
            </details>"""
        if not reviews_html:
            reviews_html = "<p style='color:#8b949e;font-size:0.85rem;padding:0.5rem 0;'>Aucune review stockée.</p>"

        pr_sections[state] += f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin-bottom:0.75rem;">
            <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
                <a class="pr-link" href="https://github.com/{repo}/pull/{pr['pr_number']}" target="_blank" style="font-weight:600;">
                    #{pr['pr_number']}
                </a>
                <span class="{state_class[state]}">{state_label[state]}</span>
                <span style="color:#8b949e;font-size:0.85rem;flex:1;">{html.escape(pr['pr_title'] or '(aucun titre)')}</span>
                <span class='badge'>{len(pr['reviews'])} review(s)</span>
            </div>
            {reviews_html}
        </div>"""

    open_html = pr_sections.get("open", "")
    merged_html = pr_sections.get("merged", "")
    closed_html = pr_sections.get("closed", "")

    sections = ""
    if open_html:
        sections += f"""<div class="section-label"><h2>🟡 Ouvertes</h2><span class="count">({open_prs})</span></div>{open_html}"""
    if merged_html:
        sections += f"""<div class="section-label"><h2>🟣 Fusionnées</h2><span class="count">({merged_prs})</span></div>{merged_html}"""
    if closed_html:
        sections += f"""<div class="section-label"><h2>🔴 Fermées</h2><span class="count">({closed_prs})</span></div>{closed_html}"""
    if not sections:
        sections = "<p style='color:#8b949e;text-align:center;padding:3rem;'>Aucun PR suivi pour ce dépôt.</p>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{repo} — PR-Agent Dashboard</title>{FULL_STYLES}</head>
<body>
<a class="back-link" href="/">← Retour au dashboard</a>
<h1>📂 {repo}</h1>
<div class="stats-grid">
<div class="stat-card"><div class="stat-value">{len(data)}</div><div class="stat-label">PRs suivis</div></div>
<div class="stat-card"><div class="stat-value">{open_prs}</div><div class="stat-label">Ouvertes</div></div>
<div class="stat-card"><div class="stat-value">{merged_prs}</div><div class="stat-label">Fusionnées</div></div>
<div class="stat-card"><div class="stat-value">{closed_prs}</div><div class="stat-label">Fermées</div></div>
<div class="stat-card"><div class="stat-value">{total_reviews}</div><div class="stat-label">Reviews</div></div>
</div>
<h2>📈 Activité (30 jours)</h2>
<div class="timeline">{timeline_bars}</div>
<h2>Instructions personnalisées</h2>
<form method="POST" action="/repo/{repo}/instructions" style="margin-bottom:1.5rem;">
    <textarea name="instructions" rows="4" style="width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;padding:0.75rem;font-family:inherit;font-size:0.85rem;resize:vertical;">{html.escape(current_instructions)}</textarea>
    <button type="submit" style="margin-top:0.5rem;background:#1f6feb;color:#fff;border:none;border-radius:6px;padding:0.5rem 1rem;font-size:0.85rem;cursor:pointer;">Enregistrer</button>
</form>
{sections}
<div class="footer">PR-Agent Dashboard · <a href="/docs" style="color:#58a6ff;">API docs</a></div>
</body></html>""")


@app.get("/health")
async def health():
    return {"status": "ok"}
