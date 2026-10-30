# agentic-volunteer-desk

An event-volunteer assistant where the model is the last resort: emergencies skip it entirely, and an answer without verifiable citations never reaches anyone.

A volunteer asking where to check in needs a fast answer from the handbook. A volunteer reporting smoke needs a human now, and no prompt should stand between them. This is a reference design for that split, using Claude's document blocks with citations for the first case and plain code for the second.

**This has not been run live and has never been deployed.** There is no API key on the machine it was written on. Every test and every output below uses a scripted fake model, so nothing here shows how a real model behaves or how well the answers read. The request and response shapes follow Anthropic's citations documentation, and one offline test parses a documented response with the SDK's own types. The event, "Example Summit 2030", is invented.

Not affiliated with Anthropic.

## Flow

```
message
  |
  v
rules.py (deterministic, 6 languages)
  |-- emergency keyword ---> P0 ticket + fixed safety message   (no model call)
  |-- urgent keyword ------> P1 ticket                          (no model call)
  |-- personal / contact --> P2 ticket                          (no model call)
  |
  v
model call (injected function, documents with citations enabled)
  |-- NOT_IN_DOCUMENTS ----> P3 ticket
  |-- exception -----------> P2 ticket
  |
  v
check_reply (code, not prompt)
  |-- truncated, refused, no citations, cited text not in the document,
  |   or under half the answer cited ---> P3 ticket
  |
  v
answer + citations
```

The design decisions that matter:

- **The model cannot override routing,** because it never sees those messages. Tests assert the fake model received zero requests.
- **The prompt asks for citations; the code requires them.** `check_reply` confirms each `cited_text` appears in the document it names. An injected "ignore your rules" that produces an uncited answer ends in a ticket.
- **A broken ticket system doesn't suppress the safety message.** The emergency reply is returned even if the sink raises, with `ticket_delivered=False`.
- **"Not in the documents" is a sentinel string,** because citations and structured outputs can't be combined in one request.
- **The model call is a function:** request dict in, response dict out. `Desk(documents, model_call, sink)`.

## Quickstart

```
pip install -e .
python examples/mock_demo.py
```

Real output. The model here is scripted, including the bad answer to the second question:

```
Q: How many meal vouchers do I get?
   model called: True
   reply: From the handbook: Volunteers receive one meal voucher per shift of four hours or longer.
   cited [handbook]: Volunteers receive one meal voucher per shift of four hours or longer.

Q: Is there parking for cars?
   model called: True
   reply: A person on the volunteer desk will take this from here.
   ticket: P3 info-desk reason=unverified_answer detail=no_citations
           matched=[]

Q: Is there a volunteer afterparty?
   model called: True
   reply: A person on the volunteer desk will take this from here.
   ticket: P3 info-desk reason=not_in_documents detail=not_in_documents
           matched=[]

Q: When is my shift tomorrow?
   model called: False
   reply: A person on the volunteer desk will take this from here.
   ticket: P2 volunteer-coordinator reason=personal detail=None
           matched=['personal:en:my shift*']

Q: Hall B'de yangın var!
   model called: False
   reply: Bu bir güvenlik sorunu gibi görünüyor. Tehlike varsa hemen yerel acil durum numarasını arayın ve en yakın görevliye haber verin. İnsan masasına bir kayıt açıldı.
   ticket: P0 safety-lead reason=emergency detail=None
           matched=['emergency:tr:yangın*']
```

Routing alone, with no model and no key:

```
$ volunteer-desk route "Hall B'de YANGIN var"
{"route": "emergency", "matched": ["emergency:tr:yangın*"]}
$ volunteer-desk route "Where do volunteers check in?"
{"route": "model", "matched": []}
```

`pip install -e ".[live]"` then `volunteer-desk ask --docs examples/example_summit_2030 "..."` is wired to the real API and defaults to `claude-opus-5-5`. It has never been executed against the API.

## Routing test set

`tests/data/routing_cases.jsonl` holds 113 cases in English, Turkish, German, French, Spanish and Arabic. The tests pin the rules' behaviour on all of them, including the wrong answers. `python scripts/routing_report.py`:

```
113 self-written cases. Keywords and cases have the same author.
correct: 97/113 = 0.858

  en: 23/30
  tr: 18/22
  de: 15/16
  fr: 14/16
  es: 15/16
  ar: 12/13

expected \ actual         model   personal     urgent  emergency
model                        23          0          2          5
personal                      2         21          0          0
urgent                        0          0         12          0
emergency                     7          0          0         41

under-routed: 9
  [en] "My friend is lying on the floor and won't wake up": expected emergency, got model
  [en] 'A man is shouting that he will hurt people': expected emergency, got model
  [en] 'When is Maria working tomorrow?': expected personal, got model
  [tr] 'Arkadaşım yerde yatıyor, uyanmıyor': expected emergency, got model
  [tr] "Ahmet'in vardiyası ne zaman?": expected personal, got model
  [de] 'Jemand liegt am Boden und wacht nicht auf': expected emergency, got model
  [fr] "Quelqu'un est par terre et ne se réveille pas": expected emergency, got model
  [es] 'Un hombre está en el suelo y no se despierta': expected emergency, got model
  [ar] 'شخص ملقى على الأرض ولا يستيقظ': expected emergency, got model
over-routed: 7
  [en] 'Is the canteen open right now?': expected model, got urgent
  [en] 'Where is the fire exit?': expected model, got emergency
  [en] 'Where can I smoke?': expected model, got emergency
  [en] 'Is sangria served at the closing party?': expected model, got emergency
  [tr] 'Kayıt masası hemen girişte mi?': expected model, got urgent
  [tr] 'Acil çıkış nerede?': expected model, got emergency
  [fr] "Le feu d'artifice est à quelle heure ?": expected model, got emergency
```

I wrote both the keywords and the cases, so 0.858 is not an accuracy estimate. Its value is the error list. The seven under-routed emergencies are the serious ones: **a description of an emergency that avoids the keywords goes to the model**, and only the system prompt and the citation check then stand between it and a normal reply. The set also caught a real bug during development: a Turkish `acil*` prefix matched `açılıyor` ("is opening") after folding, which sent a door-times question to the safety lead.

## Limits

- **Never run against a real model.** The system prompt is untested, and the sentinel, the 0.5 cited ratio and the handling of real citation output are all uncalibrated. Expect tuning.
- **Keywords don't understand meaning.** They miss paraphrased emergencies (above), and they don't see negation, so "no fire here" is a P0. Over-triggering is deliberate; under-triggering isn't, and it is unsolved here.
- **Keyword lists and translations are mine and unreviewed by native speakers or safety professionals.** The safety messages name no phone number on purpose, because emergency numbers vary by country; a real event must add its own and have them reviewed.
- **A citation proves the quote exists, not that the answer follows from it.** A model could cite a real sentence and misstate it.
- **Personal data detection is narrow.** First-person phrases, emails and long numbers are caught. Questions about other named people are not (see the `Maria` case), and those go to the model.
- **Tickets go to a sink, and nobody is paged.** `JsonlSink` writes a file. Alerting a person for P0 is the integration this design leaves open, and it's the part that would matter most.
- No conversation memory, authentication, rate limits or monitoring. Each message is handled alone.
- Tested locally on Python 3.12 only. CI is configured for 3.11 and 3.12 but this repository has not been pushed.

## License

MIT
