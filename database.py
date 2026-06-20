"""Base de données SQLite pour le dashboard PR-Agent."""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", "pr_agent.db"))


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite. Appelle `init_db()` au premier appel."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                repo        TEXT    NOT NULL,
                pr_number   INTEGER NOT NULL,
                pr_title    TEXT    DEFAULT '',
                comment_id  INTEGER,
                author      TEXT    DEFAULT 'unknown',
                body        TEXT    DEFAULT '',
                suggestions_count INTEGER DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(repo, pr_number, comment_id)
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id   INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                category    TEXT    DEFAULT 'other',
                file_path   TEXT    DEFAULT '',
                line_number INTEGER,
                summary     TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS meta (
                repo        TEXT    NOT NULL,
                key         TEXT    NOT NULL,
                value       TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (repo, key)
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_repo_pr
                ON reviews(repo, pr_number);
            CREATE INDEX IF NOT EXISTS idx_reviews_created
                ON reviews(created_at);
            CREATE INDEX IF NOT EXISTS idx_suggestions_review
                ON suggestions(review_id);
        """)


# ──────────────────── CRUD ────────────────────

def store_review(
    repo: str,
    pr_number: int,
    pr_title: str,
    body: str,
    author: str,
    comment_id: int | None = None,
) -> int:
    """Stocke une review et retourne son ID."""
    suggestions_count = body.count("**") // 2  # approximation simple
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO reviews (repo, pr_number, pr_title, comment_id, author, body, suggestions_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(repo, pr_number, comment_id) DO UPDATE SET
                   body = excluded.body,
                   suggestions_count = excluded.suggestions_count""",
            (repo, pr_number, pr_title, comment_id, author, body, suggestions_count),
        )
        return cur.lastrowid


def get_reviews(repo: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """Historique des reviews, trié par date décroissante."""
    with get_connection() as conn:
        if repo:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE repo = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (repo, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]


def get_stats(days: int = 30) -> dict:
    """Statistiques globales sur les N derniers jours."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT
                   COUNT(*)                                  AS total_reviews,
                   COUNT(DISTINCT repo)                      AS repos,
                   COUNT(DISTINCT pr_number)                 AS prs,
                   IFNULL(SUM(suggestions_count), 0)         AS total_suggestions,
                   IFNULL(AVG(suggestions_count), 0.0)       AS avg_suggestions,
                   IFNULL(COUNT(*) / CAST(? AS REAL), 0.0)   AS reviews_per_day
               FROM reviews
               WHERE created_at >= datetime('now', ? || ' days')""",
            (days, f"-{days}"),
        ).fetchone()
        return dict(rows)


def get_memory_context(repo: str, files_changed: list[str]) -> str:
    """Génère un contexte mémoire à partir des reviews passées sur le même repo.

    Cherche les reviews qui mentionnent les fichiers changés et retourne
    un résumé textuel injectable dans PR-Agent comme extra_instructions.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT pr_number, body, created_at
               FROM reviews
               WHERE repo = ? AND suggestions_count > 0
               ORDER BY created_at DESC
               LIMIT 5""",
            (repo,),
        ).fetchall()

    if not rows:
        return ""

    parts = [
        "📚 **Mémoire des reviews passées (pour contexte) :**",
        "",
    ]
    for r in rows:
        date = r["created_at"][:10]
        # On prend juste les premières lignes significatives de l'ancienne review
        preview = "\n".join(r["body"].split("\n")[:8])
        parts.append(f"--- PR #{r['pr_number']} ({date}) ---")
        parts.append(preview)
        parts.append("")

    return "\n".join(parts)


def set_meta(repo: str, key: str, value: str):
    """Stocke une métadonnée (ex: instructions de review personnalisées)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (repo, key, value, updated_at) VALUES (?, ?, ?, datetime('now'))",
            (repo, key, value),
        )


def get_meta(repo: str, key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE repo = ? AND key = ?", (repo, key)
        ).fetchone()
        return row["value"] if row else None
