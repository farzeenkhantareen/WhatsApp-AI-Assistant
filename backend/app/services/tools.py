"""Business knowledge loader and OpenRouter tool definitions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def knowledge_dir() -> Path:
    settings = get_settings()
    path = Path(settings.knowledge_dir)
    if not path.is_absolute():
        # Resolve relative to /app in Docker or backend cwd
        candidates = [
            Path.cwd() / path,
            Path(__file__).resolve().parents[1] / "prompts" / "knowledge",
            Path("/app") / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
    return path


def load_business_knowledge() -> str:
    """Concatenate markdown/text knowledge files for system prompt injection."""
    directory = knowledge_dir()
    if not directory.exists():
        return ""
    chunks: List[str] = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            chunks.append(f"### {path.name}\n{path.read_text(encoding='utf-8').strip()}")
        except OSError as exc:
            logger.warning("Failed reading knowledge file %s: %s", path, exc)
    return "\n\n".join(chunks)


def build_system_prompt() -> str:
    settings = get_settings()
    knowledge = load_business_knowledge()
    if not knowledge:
        return settings.system_prompt
    return (
        f"{settings.system_prompt}\n\n"
        "## Business knowledge\n"
        "Use the following business knowledge when relevant. "
        "If the answer is not covered, say you are unsure.\n\n"
        f"{knowledge}"
    )


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_business_knowledge",
            "description": (
                "Search custom business knowledge documents for policies, "
                "hours, products, pricing, or FAQs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or question to look up",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current UTC date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Execute a tool call and return a string result for the model."""
    if name == "get_current_time":
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return now

    if name == "lookup_business_knowledge":
        query = str(args.get("query") or "").lower().strip()
        knowledge = load_business_knowledge()
        if not knowledge:
            return "No business knowledge documents are configured."
        if not query:
            return knowledge[:4000]
        # Simple keyword filter across paragraphs
        paragraphs = [p.strip() for p in knowledge.split("\n\n") if p.strip()]
        hits = [p for p in paragraphs if any(token in p.lower() for token in query.split())]
        if not hits:
            return "No matching business knowledge found for that query."
        return "\n\n".join(hits)[:6000]

    return f"Unknown tool: {name}"
