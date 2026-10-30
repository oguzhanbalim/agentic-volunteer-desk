import pytest

from volunteer_desk.fakes import cited_block, response, text_block
from volunteer_desk.model import (
    DEFAULT_MODEL,
    NOT_IN_DOCUMENTS,
    Document,
    Verdict,
    anthropic_call,
    build_request,
    check_reply,
    load_documents,
)

DOCS = [
    Document("handbook", "Check-in opens at 08:15. Wear closed shoes."),
    Document("venue", "Hall C holds the canteen."),
]
CHECK_IN = cited_block(DOCS, "handbook", "Check-in opens at 08:15.")


def test_request_shape():
    request = build_request("When?", DOCS)
    assert request["model"] == DEFAULT_MODEL == "claude-opus-5-5"
    blocks = request["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["document", "document", "text"]
    assert blocks[0]["citations"] == {"enabled": True}
    assert blocks[0]["source"] == {
        "type": "text",
        "media_type": "text/plain",
        "data": DOCS[0].text,
    }
    assert blocks[0]["title"] == "handbook"
    assert blocks[-1]["text"] == "<question>When?</question>"


def test_request_avoids_parameters_we_should_not_send():
    request = build_request("When?", DOCS)
    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "thinking", "output_config"):
        assert forbidden not in request
    assert request["messages"][-1]["role"] == "user"


def test_good_reply():
    checked = check_reply(response([CHECK_IN]), DOCS)
    assert checked.verdict is Verdict.ANSWER
    assert checked.text == "Check-in opens at 08:15."
    assert checked.citations[0].document_title == "handbook"
    assert checked.citations[0].start_char_index == 0


def test_connecting_text_is_allowed():
    blocks = [text_block("Per the handbook: "), CHECK_IN]
    assert check_reply(response(blocks), DOCS).verdict is Verdict.ANSWER


def test_citation_text_with_surrounding_whitespace_is_accepted():
    # The documented example returns cited_text trimmed against a span including the space.
    block = {
        "type": "text",
        "text": "Shoes must be closed.",
        "citations": [
            {
                "type": "char_location",
                "cited_text": "Wear closed shoes. ",
                "document_index": 0,
                "document_title": "handbook",
                "start_char_index": 25,
                "end_char_index": 44,
            }
        ],
    }
    assert check_reply(response([block]), DOCS).verdict is Verdict.ANSWER


def test_sentinel_is_recognised_even_with_extra_words():
    reply = response([text_block(f"Sorry. {NOT_IN_DOCUMENTS}")])
    assert check_reply(reply, DOCS).verdict is Verdict.NOT_IN_DOCUMENTS


def test_no_citations_is_rejected():
    reply = response([text_block("Check-in opens at 08:15.")])
    assert check_reply(reply, DOCS).verdict is Verdict.NO_CITATIONS


def test_mostly_uncited_is_rejected():
    long_claim = text_block("Volunteers also get free parking and a bonus on the last day " * 2)
    checked = check_reply(response([CHECK_IN, long_claim]), DOCS)
    assert checked.verdict is Verdict.MOSTLY_UNCITED


@pytest.mark.parametrize(
    "citation",
    [
        {"type": "char_location", "cited_text": "Invented text.", "document_index": 0},
        {"type": "char_location", "cited_text": "Hall C holds", "document_index": 0},
        {"type": "char_location", "cited_text": "Check-in opens", "document_index": 9},
        {"type": "char_location", "cited_text": "", "document_index": 0},
        {"type": "page_location", "cited_text": "Check-in opens", "document_index": 0},
        {"type": "char_location", "cited_text": "Check-in opens"},
    ],
)
def test_citations_that_do_not_hold_up_are_rejected(citation):
    block = {"type": "text", "text": "Something", "citations": [citation]}
    assert check_reply(response([block]), DOCS).verdict is Verdict.BAD_CITATION


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal", "pause_turn", None])
def test_incomplete_stop_reasons_are_rejected(stop_reason):
    reply = response([CHECK_IN], stop_reason=stop_reason)
    assert check_reply(reply, DOCS).verdict is Verdict.INCOMPLETE


def test_empty_reply_is_rejected():
    assert check_reply(response([]), DOCS).verdict is Verdict.INCOMPLETE


def test_non_text_blocks_are_ignored():
    reply = response([{"type": "thinking", "thinking": "...", "signature": "x"}, CHECK_IN])
    assert check_reply(reply, DOCS).verdict is Verdict.ANSWER


def test_real_sdk_types_round_trip_offline():
    # No network: parses a documented response with the SDK's own model, then checks it.
    anthropic = pytest.importorskip("anthropic")
    message = anthropic.types.Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": DEFAULT_MODEL,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [CHECK_IN, text_block(" Bring shoes.")],
        }
    )

    class FakeMessages:
        def create(self, **_):
            return message

    class FakeClient:
        messages = FakeMessages()

    raw = anthropic_call(FakeClient())(build_request("When?", DOCS))
    checked = check_reply(raw, DOCS)
    assert checked.verdict is Verdict.ANSWER
    assert checked.citations[0].cited_text == "Check-in opens at 08:15."


def test_load_documents_is_sorted_and_filters(tmp_path):
    (tmp_path / "b.md").write_text("B", encoding="utf-8")
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "skip.pdf").write_bytes(b"x")
    assert [d.title for d in load_documents(tmp_path)] == ["a", "b"]
