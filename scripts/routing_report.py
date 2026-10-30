"""Run the offline routing set and print accuracy, per language and by error direction.

An under-route is the dangerous kind: the message went to a lower route than it should have.
An over-route costs a person a minute. Run: python scripts/routing_report.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from volunteer_desk.rules import Route, route

CASES = Path(__file__).resolve().parent.parent / "tests" / "data" / "routing_cases.jsonl"
SEVERITY = [Route.MODEL, Route.PERSONAL, Route.URGENT, Route.EMERGENCY]


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    cases = load_cases()
    per_language: dict[str, Counter] = {}
    confusion: Counter = Counter()
    errors = []
    for case in cases:
        actual = route(case["text"]).route
        expected = Route(case["expected"])
        confusion[(expected, actual)] += 1
        bucket = per_language.setdefault(case["lang"], Counter())
        bucket["total"] += 1
        bucket["correct"] += actual is expected
        if actual is not expected:
            direction = "under" if SEVERITY.index(actual) < SEVERITY.index(expected) else "over"
            errors.append((direction, case["lang"], case["text"], expected, actual))

    correct = sum(b["correct"] for b in per_language.values())
    print(f"{len(cases)} self-written cases. Keywords and cases have the same author.")
    print(f"correct: {correct}/{len(cases)} = {correct / len(cases):.3f}")
    print()
    for lang, bucket in per_language.items():
        print(f"  {lang}: {bucket['correct']}/{bucket['total']}")
    print()
    print("expected \\ actual".ljust(20) + "".join(r.value.rjust(11) for r in SEVERITY))
    for expected in SEVERITY:
        cells = "".join(str(confusion[(expected, a)]).rjust(11) for a in SEVERITY)
        print(expected.value.ljust(20) + cells)
    print()
    for direction in ("under", "over"):
        chosen = [e for e in errors if e[0] == direction]
        print(f"{direction}-routed: {len(chosen)}")
        for _, lang, text, expected, actual in chosen:
            print(f"  [{lang}] {text!r}: expected {expected.value}, got {actual.value}")


if __name__ == "__main__":
    main()
