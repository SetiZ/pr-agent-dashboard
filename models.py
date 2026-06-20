"""Modèles Pydantic pour l'API."""

from pydantic import BaseModel
from typing import Optional


class WebhookPayload(BaseModel):
    """Payload minimal du webhook GitHub — on ne garde que ce qui nous intéresse."""
    action: str = ""
    repository: Optional[dict] = None
    pull_request: Optional[dict] = None
    comment: Optional[dict] = None
    review: Optional[dict] = None
    sender: Optional[dict] = None


class MemoryRequest(BaseModel):
    repo: str
    pr_number: int
    files: list[str] = []


class CustomInstructions(BaseModel):
    """Instructions de review personnalisées pour un repo."""
    repo: str
    instructions: str
