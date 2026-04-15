"""Ollama local AI service for generating intelligence briefs.

Connects to a locally-running Ollama instance (http://localhost:11434 by default).
Falls back gracefully if Ollama is not available, returning a plain text summary.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
BRIEF_MAX_TOKENS = 250
REQUEST_TIMEOUT = 60.0


class OllamaService:
    """Wraps the Ollama HTTP API for local AI inference."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None  # None = not yet checked
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Availability probe
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Return True if Ollama is reachable and has a model ready."""
        if self._available is not None:
            return self._available
        async with self._lock:
            if self._available is not None:
                return self._available
            self._available = await self._probe()
            return self._available

    async def _probe(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                if resp.status_code == 200:
                    tags = resp.json().get("models", [])
                    logger.info(
                        "Ollama available – %d model(s): %s",
                        len(tags),
                        [t.get("name") for t in tags],
                    )
                    return True
        except Exception as exc:
            logger.info("Ollama not reachable (%s) – running without AI briefs.", exc)
        return False

    async def reset_probe(self) -> None:
        """Force re-check of availability on next call."""
        async with self._lock:
            self._available = None

    # ------------------------------------------------------------------
    # Brief generation
    # ------------------------------------------------------------------

    async def generate_brief(
        self,
        headlines: list[str],
        context: str = "world events",
        style: str = "intelligence analyst",
    ) -> str:
        """Generate a synthesized intelligence brief from a list of headlines.

        Falls back to a plain concatenated summary if Ollama is unavailable.
        """
        if not await self.is_available():
            return self._fallback_brief(headlines, context)

        prompt = self._build_prompt(headlines, context, style)

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": BRIEF_MAX_TOKENS,
                            "temperature": 0.3,
                            "top_p": 0.9,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text: str = data.get("response", "").strip()
                if text:
                    return text
        except Exception as exc:
            logger.warning("Ollama generate failed: %s", exc)
            # Mark as unavailable so we don't keep hammering a broken instance
            self._available = False

        return self._fallback_brief(headlines, context)

    async def analyze_risk(
        self,
        country: str,
        recent_events: list[str],
    ) -> str:
        """Generate a risk assessment paragraph for a country."""
        if not await self.is_available():
            return f"Risk assessment for {country}: {len(recent_events)} recent events detected."

        prompt = (
            f"You are a geopolitical risk analyst. Based on these recent events for {country}:\n"
            + "\n".join(f"- {e}" for e in recent_events[:10])
            + f"\n\nWrite a 2-sentence risk assessment for {country} suitable for an intelligence dashboard. "
            "Focus on stability, security, and economic risk. Be concise and factual."
        )

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 120, "temperature": 0.2},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except Exception as exc:
            logger.warning("Ollama risk analysis failed: %s", exc)

        return f"Risk assessment for {country}: {len(recent_events)} recent events detected."

    async def summarize_article(self, title: str, content: str) -> str:
        """Summarize a single news article in 1-2 sentences."""
        if not await self.is_available():
            return content[:200] + ("…" if len(content) > 200 else "")

        prompt = (
            f"Summarize this news article in 1-2 sentences for an intelligence dashboard:\n\n"
            f"Title: {title}\n\nContent: {content[:800]}\n\nSummary:"
        )

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 80, "temperature": 0.2},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except Exception as exc:
            logger.warning("Ollama summarize failed: %s", exc)

        return content[:200] + ("…" if len(content) > 200 else "")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        headlines: list[str], context: str, style: str
    ) -> str:
        headline_block = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:15]))
        return (
            f"You are a {style}. Based on the following recent news headlines about {context}, "
            f"write a concise 3-4 sentence intelligence brief that synthesizes the key themes, "
            f"identifies the most significant developments, and highlights any patterns or risks.\n\n"
            f"Headlines:\n{headline_block}\n\n"
            f"Intelligence Brief:"
        )

    @staticmethod
    def _fallback_brief(headlines: list[str], context: str) -> str:
        """Plain text fallback when Ollama is unavailable."""
        if not headlines:
            return f"No recent news available for {context}."
        top = headlines[:5]
        return (
            f"Recent {context} developments: "
            + " | ".join(top[:3])
            + (f" and {len(headlines) - 3} more stories." if len(headlines) > 3 else ".")
        )

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict]:  # type: ignore[type-arg]
        """List models available in the local Ollama instance."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                if resp.status_code == 200:
                    return resp.json().get("models", [])
        except Exception:
            pass
        return []

    async def pull_model(self, model_name: str) -> bool:
        """Pull a model into Ollama (non-blocking check; actual pull is long-running)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/pull",
                    json={"name": model_name, "stream": False},
                    timeout=300.0,
                )
                return resp.status_code == 200
        except Exception:
            return False


# Module-level singleton
ollama_service = OllamaService()
