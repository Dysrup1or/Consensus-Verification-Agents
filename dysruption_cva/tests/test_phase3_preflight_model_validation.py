from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest


def test_phase3_preflight_model_validation_skips_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CVA_PREFLIGHT_VALIDATE_MODELS", raising=False)

    # Import after env changes
    import preflight

    res = preflight.check_llm_models_accessible()
    assert res.status == preflight.Status.SKIP


def test_phase3_preflight_model_validation_fails_on_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Enable model validation
    monkeypatch.setenv("CVA_PREFLIGHT_VALIDATE_MODELS", "1")

    # Patch preflight paths to use tmp dirs
    import preflight

    backend_dir = tmp_path / "dysruption_cva"
    backend_dir.mkdir(parents=True, exist_ok=True)

    # Minimal config with one model
    (backend_dir / "config.yaml").write_text(
        """
llms:
  architect:
    model: "anthropic/does-not-exist"
    provider: "anthropic"

fallback:
  models:
    - "openai/gpt-4o"
""".lstrip(),
        encoding="utf-8",
    )

    # Provide some key so the check doesn't SKIP early
    (backend_dir / ".env").write_text("ANTHROPIC_API_KEY=dummy\n", encoding="utf-8")

    monkeypatch.setattr(preflight, "BACKEND_DIR", backend_dir)

    class NotFoundError(Exception):
        pass

    def fake_completion(*args, **kwargs):
        raise NotFoundError("model not found")

    fake_litellm = SimpleNamespace(completion=fake_completion)

    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    res = preflight.check_llm_models_accessible()
    assert res.status == preflight.Status.FAIL


def test_phase3_preflight_model_validation_passes_when_completion_succeeds(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("CVA_PREFLIGHT_VALIDATE_MODELS", "1")

    import preflight

    backend_dir = tmp_path / "dysruption_cva"
    backend_dir.mkdir(parents=True, exist_ok=True)

    (backend_dir / "config.yaml").write_text(
        """
llms:
  architect:
    model: "anthropic/claude-sonnet-4-20250514"
    provider: "anthropic"
""".lstrip(),
        encoding="utf-8",
    )
    (backend_dir / ".env").write_text("ANTHROPIC_API_KEY=dummy\n", encoding="utf-8")

    monkeypatch.setattr(preflight, "BACKEND_DIR", backend_dir)

    def fake_completion(*args, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    fake_litellm = SimpleNamespace(completion=fake_completion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    res = preflight.check_llm_models_accessible()
    assert res.status == preflight.Status.PASS
