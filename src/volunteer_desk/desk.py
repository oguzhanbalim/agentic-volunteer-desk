"""The desk: route first, ask the model only if allowed, verify, otherwise open a ticket."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from .model import (
    DEFAULT_MIN_CITED_RATIO,
    Citation,
    Document,
    ModelCall,
    Verdict,
    build_request,
    check_reply,
)
from .rules import Decision, Route, route
from .tickets import InMemorySink, Reason, Ticket, TicketSink, new_ticket

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 2000

EMERGENCY_REPLY = {
    "en": "This sounds like a safety issue. If anyone is in danger, call your local emergency "
    "number now and tell the nearest staff member. The human desk has been given a ticket.",
    "tr": "Bu bir güvenlik sorunu gibi görünüyor. Tehlike varsa hemen yerel acil durum numarasını "
    "arayın ve en yakın görevliye haber verin. İnsan masasına bir kayıt açıldı.",
    "de": "Das klingt nach einem Sicherheitsproblem. Wenn jemand in Gefahr ist, rufen Sie sofort "
    "den örtlichen Notruf und informieren Sie das nächste Personal. Der Helpdesk hat ein Ticket "
    "erhalten.",
    "fr": "Cela ressemble à un problème de sécurité. Si quelqu'un est en danger, appelez "
    "immédiatement le numéro d'urgence local et prévenez le membre du personnel le plus proche. "
    "L'équipe d'accueil a reçu un ticket.",
    "es": "Esto parece un problema de seguridad. Si alguien está en peligro, llame ahora al número "
    "local de emergencias y avise al miembro del personal más cercano. El equipo humano ha "
    "recibido un ticket.",
    "ar": "يبدو أن هذه مشكلة تتعلق بالسلامة. إذا كان أي شخص في خطر، فاتصل برقم الطوارئ المحلي الآن "
    "وأبلغ أقرب موظف. تم إرسال تذكرة إلى المكتب البشري.",
}

HANDOFF_REPLY = {
    "en": "A person on the volunteer desk will take this from here.",
    "tr": "Bundan sonra gönüllü masasından bir görevli ilgilenecek.",
    "de": "Eine Person vom Helfer-Desk übernimmt das von hier.",
    "fr": "Une personne de l'accueil des bénévoles prend le relais.",
    "es": "Una persona del equipo de voluntarios se encargará a partir de aquí.",
    "ar": "سيتولى شخص من مكتب المتطوعين الأمر من هنا.",
}

_VERDICT_REASON = {
    Verdict.NOT_IN_DOCUMENTS: Reason.NOT_IN_DOCUMENTS,
    Verdict.INCOMPLETE: Reason.UNVERIFIED_ANSWER,
    Verdict.NO_CITATIONS: Reason.UNVERIFIED_ANSWER,
    Verdict.BAD_CITATION: Reason.UNVERIFIED_ANSWER,
    Verdict.MOSTLY_UNCITED: Reason.UNVERIFIED_ANSWER,
}


@dataclass(frozen=True)
class Outcome:
    """What the volunteer sees, and what happened. `ticket` is None only for a cited answer."""

    text: str
    citations: tuple[Citation, ...] = ()
    ticket: Ticket | None = None
    model_called: bool = False
    ticket_delivered: bool = True

    @property
    def answered(self) -> bool:
        return self.ticket is None


class Desk:
    def __init__(
        self,
        documents: list[Document],
        model_call: ModelCall,
        sink: TicketSink | None = None,
        *,
        model: str | None = None,
        min_cited_ratio: float = DEFAULT_MIN_CITED_RATIO,
        router: Callable[[str], Decision] = route,
    ) -> None:
        self._documents = documents
        self._model_call = model_call
        self.sink: TicketSink = sink if sink is not None else InMemorySink()
        self._model = model
        self._min_cited_ratio = min_cited_ratio
        self._router = router

    def handle(
        self,
        question: str,
        *,
        volunteer_id: str | None = None,
        language: str | None = None,
    ) -> Outcome:
        decision = self._router(question)
        lang = decision.language or language

        if decision.route is Route.EMERGENCY:
            return self._hand_off(Reason.EMERGENCY, question, volunteer_id, lang, decision)
        if decision.route is Route.URGENT:
            return self._hand_off(Reason.URGENT, question, volunteer_id, lang, decision)
        if decision.route is Route.PERSONAL:
            return self._hand_off(Reason.PERSONAL, question, volunteer_id, lang, decision)
        if not question.strip() or len(question) > MAX_QUESTION_CHARS:
            detail = "empty" if not question.strip() else f"over {MAX_QUESTION_CHARS} characters"
            return self._hand_off(
                Reason.UNUSABLE_QUESTION, question, volunteer_id, lang, decision, detail=detail
            )
        return self._ask_model(question, volunteer_id, lang, decision)

    def _ask_model(
        self, question: str, volunteer_id: str | None, lang: str | None, decision: Decision
    ) -> Outcome:
        kwargs = {"model": self._model} if self._model else {}
        request = build_request(question, self._documents, **kwargs)
        try:
            response = self._model_call(request)
        except Exception as error:  # noqa: BLE001 - any failure must end at a human, not a crash
            logger.exception("model call failed")
            return self._hand_off(
                Reason.MODEL_UNAVAILABLE, question, volunteer_id, lang, decision,
                detail=type(error).__name__, model_called=True,
            )
        checked = check_reply(response, self._documents, min_cited_ratio=self._min_cited_ratio)
        if checked.verdict is Verdict.ANSWER:
            return Outcome(checked.text, citations=checked.citations, model_called=True)
        detail = checked.verdict.value if not checked.detail else (
            f"{checked.verdict.value}: {checked.detail}"
        )
        return self._hand_off(
            _VERDICT_REASON[checked.verdict], question, volunteer_id, lang, decision,
            detail=detail, model_called=True,
        )

    def _hand_off(
        self,
        reason: Reason,
        question: str,
        volunteer_id: str | None,
        lang: str | None,
        decision: Decision,
        *,
        detail: str | None = None,
        model_called: bool = False,
    ) -> Outcome:
        ticket = new_ticket(
            reason,
            question,
            volunteer_id=volunteer_id,
            language=lang,
            matched_rules=tuple(str(hit) for hit in decision.hits),
            detail=detail,
            model_called=model_called,
        )
        table = EMERGENCY_REPLY if reason is Reason.EMERGENCY else HANDOFF_REPLY
        text = table.get(lang or "en", table["en"])
        delivered = True
        try:
            self.sink.submit(ticket)
        except Exception:  # noqa: BLE001 - the safety message must still be returned
            logger.exception("ticket %s could not be delivered", ticket.id)
            delivered = False
        return Outcome(text, ticket=ticket, model_called=model_called, ticket_delivered=delivered)
