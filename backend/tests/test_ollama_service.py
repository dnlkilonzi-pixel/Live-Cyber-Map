"""Unit tests for OllamaService.

Tests cover: _probe (200, non-200, exception), is_available (caching,
double-check-lock), reset_probe, generate_brief (unavailable→fallback,
available→success, available→HTTP error→fallback, available→empty response),
analyze_risk (unavailable, available), summarize_article (unavailable,
available), _build_prompt, _fallback_brief, list_models, pull_model.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.ollama_service import OllamaService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(available: bool | None = None) -> OllamaService:
    svc = OllamaService()
    svc._available = available
    return svc


def _mock_response(status: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body or {}
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# _probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_returns_true_on_200():
    svc = OllamaService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(
        return_value=_mock_response(200, {"models": [{"name": "llama3.2:3b"}]})
    )

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc._probe()

    assert result is True


@pytest.mark.asyncio
async def test_probe_returns_false_on_non_200():
    svc = OllamaService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_mock_response(503))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc._probe()

    assert result is False


@pytest.mark.asyncio
async def test_probe_returns_false_on_network_error():
    svc = OllamaService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc._probe()

    assert result is False


# ---------------------------------------------------------------------------
# is_available – caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_available_returns_cached_true():
    svc = _service(available=True)
    result = await svc.is_available()
    assert result is True


@pytest.mark.asyncio
async def test_is_available_returns_cached_false():
    svc = _service(available=False)
    result = await svc.is_available()
    assert result is False


@pytest.mark.asyncio
async def test_is_available_calls_probe_when_none():
    svc = _service(available=None)
    with patch.object(svc, "_probe", new_callable=AsyncMock, return_value=True):
        result = await svc.is_available()
    assert result is True
    assert svc._available is True


# ---------------------------------------------------------------------------
# reset_probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_probe_clears_cache():
    svc = _service(available=True)
    await svc.reset_probe()
    assert svc._available is None


# ---------------------------------------------------------------------------
# _fallback_brief
# ---------------------------------------------------------------------------


def test_fallback_brief_no_headlines():
    result = OllamaService._fallback_brief([], "geopolitics")
    assert "geopolitics" in result
    assert "No recent" in result


def test_fallback_brief_with_headlines():
    headlines = [
        "War in X",
        "Crisis in Y",
        "Elections in Z",
        "Deal reached",
        "Market crash",
    ]
    result = OllamaService._fallback_brief(headlines, "world")
    assert "world" in result
    assert "War in X" in result
    assert "more stories" in result


def test_fallback_brief_single_headline():
    result = OllamaService._fallback_brief(["Only one headline"], "tech")
    assert "Only one headline" in result


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_contains_context():
    prompt = OllamaService._build_prompt(["h1", "h2"], "cybersecurity", "analyst")
    assert "cybersecurity" in prompt
    assert "analyst" in prompt
    assert "h1" in prompt
    assert "h2" in prompt


def test_build_prompt_limits_to_15_headlines():
    headlines = [f"headline {i}" for i in range(20)]
    prompt = OllamaService._build_prompt(headlines, "test", "role")
    # Only first 15 should appear
    assert "headline 14" in prompt
    assert "headline 15" not in prompt


# ---------------------------------------------------------------------------
# generate_brief – unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_brief_falls_back_when_unavailable():
    svc = _service(available=False)
    result = await svc.generate_brief(["Headline 1", "Headline 2"], context="tech")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# generate_brief – available, successful HTTP call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_brief_returns_ollama_response():
    svc = _service(available=True)
    mock_resp = _mock_response(200, {"response": "Synthesized brief text."})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.generate_brief(["h1", "h2"])

    assert result == "Synthesized brief text."


@pytest.mark.asyncio
async def test_generate_brief_falls_back_on_http_error():
    svc = _service(available=True)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.generate_brief(["h1", "h2"])

    assert isinstance(result, str)
    assert svc._available is False  # marked unavailable after failure


@pytest.mark.asyncio
async def test_generate_brief_falls_back_on_empty_response():
    svc = _service(available=True)
    mock_resp = _mock_response(200, {"response": ""})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.generate_brief(["h1", "h2"], context="security")

    # Empty response → fallback
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# analyze_risk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_risk_unavailable():
    svc = _service(available=False)
    result = await svc.analyze_risk("Germany", ["Event A", "Event B"])
    assert "Germany" in result
    assert "2" in result  # 2 recent events


@pytest.mark.asyncio
async def test_analyze_risk_available_success():
    svc = _service(available=True)
    mock_resp = _mock_response(200, {"response": "Germany is stable."})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.analyze_risk("Germany", ["Event A"])

    assert result == "Germany is stable."


@pytest.mark.asyncio
async def test_analyze_risk_available_exception():
    svc = _service(available=True)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("timeout"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.analyze_risk("France", ["e1"])

    assert "France" in result


# ---------------------------------------------------------------------------
# summarize_article
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_article_unavailable_short_content():
    svc = _service(available=False)
    result = await svc.summarize_article("Title", "Short content")
    assert "Short content" in result


@pytest.mark.asyncio
async def test_summarize_article_unavailable_long_content_truncated():
    svc = _service(available=False)
    long_content = "x" * 500
    result = await svc.summarize_article("Title", long_content)
    assert result.endswith("…")
    assert len(result) == 201  # 200 chars + ellipsis


@pytest.mark.asyncio
async def test_summarize_article_available_success():
    svc = _service(available=True)
    mock_resp = _mock_response(200, {"response": "One-sentence summary."})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.summarize_article("T", "content")

    assert result == "One-sentence summary."


@pytest.mark.asyncio
async def test_summarize_article_available_exception():
    svc = _service(available=True)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("error"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.summarize_article("T", "fallback content")

    assert "fallback content" in result


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_returns_models():
    svc = OllamaService()
    mock_resp = _mock_response(
        200, {"models": [{"name": "llama3.2:3b"}, {"name": "mistral"}]}
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        models = await svc.list_models()

    assert len(models) == 2
    assert models[0]["name"] == "llama3.2:3b"


@pytest.mark.asyncio
async def test_list_models_returns_empty_on_error():
    svc = OllamaService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("offline"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        models = await svc.list_models()

    assert models == []


# ---------------------------------------------------------------------------
# pull_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_model_returns_true_on_200():
    svc = OllamaService()
    mock_resp = _mock_response(200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.pull_model("llama3.2:3b")

    assert result is True


@pytest.mark.asyncio
async def test_pull_model_returns_false_on_error():
    svc = OllamaService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("timeout"))

    with patch(
        "app.services.ollama_service.httpx.AsyncClient", return_value=mock_client
    ):
        result = await svc.pull_model("unknown_model")

    assert result is False
