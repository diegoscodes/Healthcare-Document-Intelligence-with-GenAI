from __future__ import annotations

from types import SimpleNamespace

import app.services.rag_pipeline as rp


class _FakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def invoke(self, prompt: str):
        self.calls.append(prompt)
        return SimpleNamespace(content='{"decision":"approved"}')


def test_parse_llm_json_with_repair_success() -> None:
    fake_llm = _FakeLLM()

    payload, warnings = rp.parse_llm_json_with_repair(
        fake_llm,
        schema_prompt="(schema here)",
        raw="NOT JSON AT ALL",
    )

    assert payload["decision"] == "approved"
    assert any("auto-repaired" in w.lower() for w in warnings)
    assert len(fake_llm.calls) == 1