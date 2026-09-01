"""Loads the approved case bank from JSON on disk.

Cases live as plain JSON so a faculty reviewer can read and edit them without
touching Python.  Anything that fails schema validation is refused loudly at
import time rather than silently half-loading into a student session.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .schema import Case

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def _load() -> dict[str, Case]:
    bank: dict[str, Case] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name.startswith("_"):  # _template.json etc.
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        case = Case.model_validate(raw)
        if case.case_id in bank:
            raise ValueError(f"Duplicate case_id {case.case_id} in {path.name}")
        bank[case.case_id] = case
    return bank


class _Bank:
    """Lazy dict-like view so importing this module never touches disk."""

    def __getitem__(self, key: str) -> Case:
        return _load()[key]

    def __iter__(self):
        return iter(_load())

    def __len__(self) -> int:
        return len(_load())

    def values(self):
        return _load().values()

    def items(self):
        return _load().items()

    def keys(self):
        return _load().keys()


CASE_BANK = _Bank()


def get_case(case_id: str) -> Case | None:
    return _load().get(case_id.strip().upper())


def list_cases(difficulty: int | None = None) -> list[dict]:
    """Student-facing catalogue: never leaks the diagnosis."""
    out = []
    for case in _load().values():
        if difficulty is not None and case.difficulty != difficulty:
            continue
        out.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "specialty": case.specialty,
                "difficulty": case.difficulty,
                "setting": case.setting,
                "presenting_complaint": case.chief_complaint,
                "review_status": case.provenance.status,
            }
        )
    return sorted(out, key=lambda c: (c["difficulty"], c["case_id"]))
