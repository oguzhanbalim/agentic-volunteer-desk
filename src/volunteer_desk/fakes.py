"""Scripted stand-ins for the model, used by the tests and the mock demo."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .model import Document


def cited_block(documents: list[Document], title: str, sentence: str) -> dict[str, Any]:
    """A text block citing `sentence`, in the shape the Messages API documents."""
    for index, document in enumerate(documents):
        if document.title == title:
            start = document.text.index(sentence)
            return {
                "type": "text",
                "text": sentence,
                "citations": [
                    {
                        "type": "char_location",
                        "cited_text": sentence,
                        "document_index": index,
                        "document_title": title,
                        "start_char_index": start,
                        "end_char_index": start + len(sentence),
                    }
                ],
            }
    raise KeyError(title)


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text, "citations": None}


def response(blocks: list[dict[str, Any]], stop_reason: str = "end_turn") -> dict[str, Any]:
    return {"role": "assistant", "content": blocks, "stop_reason": stop_reason}


@dataclass
class ScriptedModel:
    """Returns a canned response per question substring and records every request."""

    script: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    default: dict[str, Any] | None = None
    requests: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, request: dict[str, Any]) -> Mapping[str, Any]:
        self.requests.append(request)
        question = request["messages"][-1]["content"][-1]["text"]
        for fragment, canned in self.script.items():
            if fragment in question:
                return canned
        if self.default is not None:
            return self.default
        return response([text_block("NOT_IN_DOCUMENTS")])
