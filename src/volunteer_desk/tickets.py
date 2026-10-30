"""The structured ticket a human desk receives, and where tickets go."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class Reason(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    PERSONAL = "personal"
    NOT_IN_DOCUMENTS = "not_in_documents"
    UNVERIFIED_ANSWER = "unverified_answer"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNUSABLE_QUESTION = "unusable_question"


# (priority, owner) per reason. P0 means a person looks now.
_ROUTING: dict[Reason, tuple[str, str]] = {
    Reason.EMERGENCY: ("P0", "safety-lead"),
    Reason.URGENT: ("P1", "desk-lead"),
    Reason.PERSONAL: ("P2", "volunteer-coordinator"),
    Reason.NOT_IN_DOCUMENTS: ("P3", "info-desk"),
    Reason.UNVERIFIED_ANSWER: ("P3", "info-desk"),
    Reason.MODEL_UNAVAILABLE: ("P2", "info-desk"),
    Reason.UNUSABLE_QUESTION: ("P3", "info-desk"),
}


@dataclass(frozen=True)
class Ticket:
    id: str
    created_at: str
    reason: Reason
    priority: str
    owner: str
    question: str
    volunteer_id: str | None = None
    language: str | None = None
    matched_rules: tuple[str, ...] = ()
    detail: str | None = None
    model_called: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reason"] = self.reason.value
        data["matched_rules"] = list(self.matched_rules)
        return data


def new_ticket(
    reason: Reason,
    question: str,
    *,
    volunteer_id: str | None = None,
    language: str | None = None,
    matched_rules: tuple[str, ...] = (),
    detail: str | None = None,
    model_called: bool = False,
    ticket_id: str | None = None,
    now: datetime | None = None,
) -> Ticket:
    priority, owner = _ROUTING[reason]
    return Ticket(
        id=ticket_id or f"T-{uuid.uuid4().hex[:8]}",
        created_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        reason=reason,
        priority=priority,
        owner=owner,
        question=question,
        volunteer_id=volunteer_id,
        language=language,
        matched_rules=matched_rules,
        detail=detail,
        model_called=model_called,
    )


class TicketSink(Protocol):
    def submit(self, ticket: Ticket) -> None: ...


@dataclass
class InMemorySink:
    tickets: list[Ticket] = field(default_factory=list)

    def submit(self, ticket: Ticket) -> None:
        self.tickets.append(ticket)


@dataclass
class JsonlSink:
    """Appends one JSON object per line. A real deployment would page someone for P0."""

    path: Path

    def submit(self, ticket: Ticket) -> None:
        with Path(self.path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ticket.to_dict(), ensure_ascii=False) + "\n")
