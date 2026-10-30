"""Command line. `route` needs nothing. `ask` calls the real API and has not been run live."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .desk import Desk
from .model import anthropic_call, load_documents
from .rules import route
from .tickets import JsonlSink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="volunteer-desk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    route_cmd = sub.add_parser("route", help="show the routing decision; no model involved")
    route_cmd.add_argument("message")

    ask = sub.add_parser("ask", help="full flow against the Anthropic API (needs the live extra)")
    ask.add_argument("message")
    ask.add_argument("--docs", type=Path, required=True)
    ask.add_argument("--tickets", type=Path, default=Path("tickets.jsonl"))

    args = parser.parse_args(argv)
    if args.command == "route":
        decision = route(args.message)
        output = {"route": decision.route.value, "matched": [str(h) for h in decision.hits]}
        print(json.dumps(output, ensure_ascii=False))
        return 0

    desk = Desk(load_documents(args.docs), anthropic_call(), JsonlSink(args.tickets))
    outcome = desk.handle(args.message)
    print(outcome.text)
    for citation in outcome.citations:
        print(f"  [{citation.document_title}] {citation.cited_text}")
    if outcome.ticket:
        print(f"  ticket {outcome.ticket.id} ({outcome.ticket.priority}, {outcome.ticket.owner})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
