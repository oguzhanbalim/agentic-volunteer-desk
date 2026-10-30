"""Full flow with a SCRIPTED model. No API call happens, and this says nothing about how a
real model would respond. It shows the code paths around the model.

Run: python examples/mock_demo.py
"""

from __future__ import annotations

from pathlib import Path

from volunteer_desk import Desk, InMemorySink, load_documents
from volunteer_desk.fakes import ScriptedModel, cited_block, response, text_block

DOCS = load_documents(Path(__file__).parent / "example_summit_2030")

model = ScriptedModel(
    {
        "voucher": response(
            [
                text_block("From the handbook: "),
                cited_block(
                    DOCS,
                    "handbook",
                    "Volunteers receive one meal voucher per shift of four hours or longer.",
                ),
            ]
        ),
        "parking for cars": response([text_block("Yes, there is plenty of car parking.")]),
    }
)
sink = InMemorySink()
desk = Desk(DOCS, model, sink)

QUESTIONS = [
    "How many meal vouchers do I get?",
    "Is there parking for cars?",
    "Is there a volunteer afterparty?",
    "When is my shift tomorrow?",
    "Hall B'de yangın var!",
]

for question in QUESTIONS:
    calls_before = len(model.requests)
    outcome = desk.handle(question)
    print(f"Q: {question}")
    print(f"   model called: {len(model.requests) > calls_before}")
    print(f"   reply: {outcome.text}")
    for citation in outcome.citations:
        print(f"   cited [{citation.document_title}]: {citation.cited_text}")
    if outcome.ticket:
        t = outcome.ticket
        print(f"   ticket: {t.priority} {t.owner} reason={t.reason.value} detail={t.detail}")
        print(f"           matched={list(t.matched_rules)}")
    print()
