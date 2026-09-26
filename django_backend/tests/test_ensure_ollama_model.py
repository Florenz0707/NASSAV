#!/usr/bin/env python
"""Verify the Compose model preparation gate.

Run: uv run pytest tests/test_ensure_ollama_model.py -q
"""

from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

CONFIG = {"qwen": {"type": "ollama", "url": "http://unused", "model": "qwen2.5:0.5b"}}


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


@override_settings(ACTIVE_TRANSLATOR="qwen", TRANSLATOR_CONFIG=CONFIG)
def test_prepare_model_pulls_then_verifies(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    with (
        patch(
            "nassav.management.commands.ensure_ollama_model.requests.get",
            side_effect=[
                response({"models": []}),
                response({"models": [{"name": "qwen2.5:0.5b"}]}),
            ],
        ) as get,
        patch(
            "nassav.management.commands.ensure_ollama_model.requests.post",
            return_value=response({"status": "success"}),
        ) as post,
    ):
        call_command("ensure_ollama_model")

    assert get.call_count == 2
    post.assert_called_once_with(
        "http://ollama:11434/api/pull",
        json={"model": "qwen2.5:0.5b", "stream": False},
        timeout=(10, 3600),
    )


@override_settings(ACTIVE_TRANSLATOR="qwen", TRANSLATOR_CONFIG=CONFIG)
def test_check_only_rejects_missing_model_without_pull(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    with (
        patch(
            "nassav.management.commands.ensure_ollama_model.requests.get",
            return_value=response({"models": []}),
        ),
        patch("nassav.management.commands.ensure_ollama_model.requests.post") as post,
        pytest.raises(CommandError, match="not installed"),
    ):
        call_command("ensure_ollama_model", check_only=True)

    post.assert_not_called()


@override_settings(ACTIVE_TRANSLATOR="qwen", TRANSLATOR_CONFIG=CONFIG)
def test_ollama_url_environment_overrides_config(monkeypatch):
    from nassav.translator.OllamaTranslator import OllamaTranslator

    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    assert OllamaTranslator(config_name="qwen").url == "http://ollama:11434"
