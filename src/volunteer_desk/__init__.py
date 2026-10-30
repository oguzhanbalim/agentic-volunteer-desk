"""Reference design: answer from documents with citations, hand the rest to a human desk."""

from .desk import Desk, Outcome
from .model import Citation, Document, build_request, check_reply, load_documents
from .rules import Decision, Route, route
from .tickets import InMemorySink, JsonlSink, Reason, Ticket

__all__ = [
    "Citation",
    "Decision",
    "Desk",
    "Document",
    "InMemorySink",
    "JsonlSink",
    "Outcome",
    "Reason",
    "Route",
    "Ticket",
    "build_request",
    "check_reply",
    "load_documents",
    "route",
]
__version__ = "0.1.0"
