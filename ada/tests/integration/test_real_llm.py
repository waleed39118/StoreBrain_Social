"""Runs against a REAL local Ollama model (CI job `local-ai`). Skipped unless ADA_TEST_LLM_URL is set."""
import os

import pytest

from app.config import Settings
from app.core.local_llm import LocalLLM

URL = os.getenv("ADA_TEST_LLM_URL")
pytestmark = pytest.mark.skipif(not URL, reason="ADA_TEST_LLM_URL not set")

CASES = [
    ("باقي عندنا شي من الحليب؟", "stock"),
    ("وش أكثر شي ينباع هالأسبوع؟", "best_sellers"),
    ("ايش لازم نطلب من المورد؟", "reorder"),
    ("وصلتنا 20 كرتونة مياه ضيفها", "restock"),
    ("the customer is taking three loaves of bread", "sell"),
    ("which products are about to run out?", "low_stock"),
]


def test_real_model_classifies_dialects():
    llm = LocalLLM(Settings(llm_enabled=True, llm_url=URL, auth_secret="x" * 40,
                            llm_model=os.getenv("ADA_TEST_LLM_MODEL", "qwen2.5:1.5b"),
                            llm_timeout_sec=60))
    assert llm.status()["reachable"]
    results = {text: (llm.classify(text) or None) for text, _ in CASES}
    correct = sum(1 for text, want in CASES if results[text] and results[text].intent == want)
    print({t: (r.intent if r else None) for t, r in results.items()})
    assert all(r is not None for r in results.values())      # always valid structured JSON
    assert correct >= len(CASES) - 2                          # small CI model; prod uses 3b/7b
