"""pytest conftest: sys.path setup ve `slow` marker davranışı."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`-m slow` verilmediyse slow testleri atla.

    Varsayılan koşu (`pytest`) sadece hızlı unit testleri çalıştırır; OCR gerektiren
    uçtan uca testler `pytest -m slow` ile açıkça istendiğinde koşar.
    """
    keyword = config.getoption("-m", default="")
    if "slow" in keyword:
        return  # kullanıcı zaten slow istiyor
    skip_slow = pytest.mark.skip(reason="slow test — `pytest -m slow` ile koşun")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
