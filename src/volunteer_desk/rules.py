"""Deterministic routing. This module decides what the model never gets to see.

Rules run before any model call. All languages' lists run on every message, because a
volunteer may write in any language and a language detector would be one more thing to fail.

Term syntax, applied after folding (see `fold`):
    "fire"      whole word or phrase
    "yangın*"   prefix, for agglutinative or inflected forms. Check it against folded words:
                "acil*" would also match "açılıyor", since both fold to acil-.
    "~حريق"     substring, for Arabic prefixes such as ال and و
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Route(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    PERSONAL = "personal"
    MODEL = "model"


EMERGENCY_TERMS: dict[str, tuple[str, ...]] = {
    "en": (
        "fire", "smoke", "flames", "bleeding", "blood", "unconscious", "not breathing",
        "can't breathe", "cant breathe", "cannot breathe", "heart attack", "chest pain",
        "seizure", "stroke", "choking", "collapsed", "passed out", "fainted", "ambulance",
        "paramedic*", "overdose", "allergic reaction", "anaphylaxis", "emergency", "weapon*",
        "gun", "knife", "stabbed", "bomb", "assault*", "attacked", "harass*", "suicide",
        "kill myself", "hurt myself", "missing child", "lost child", "evacuat*", "gas leak",
        "injured", "threatened", "call 911", "call 112",
    ),
    "tr": (
        "yangın*", "duman*", "kanam*", "kanıyor", "bayıl*", "baygın*", "nefes alam*",
        "kalp kriz*", "ambulans*", "acil", "acile", "acilde", "acilen", "silah*", "bıçak*",
        "bomba*", "saldır*", "taciz*",
        "intihar*", "kendime zarar", "kayıp çocuk", "çocuk kayboldu", "gaz kaçağı", "tahliye*",
        "yaralı*", "nöbet geçir*", "112'yi ara*",
    ),
    "de": (
        "feuer", "feuerwehr", "es brennt", "rauch", "notfall*", "blutet", "blutung*",
        "bewusstlos", "ohnmächtig", "atmet nicht", "keine luft", "herzinfarkt", "krampfanfall",
        "krankenwagen", "rettungswagen", "notarzt", "waffe*", "messer", "bombe*", "angegriffen",
        "belästig*", "selbstmord", "suizid*", "verletzt*", "vermisstes kind", "gasleck",
        "evakuierung*",
    ),
    "fr": (
        "incendie", "feu", "fumée", "saigne*", "inconscient*", "évanoui*", "ne respire plus",
        "mal à respirer", "crise cardiaque", "ambulance", "pompiers", "samu", "urgence*",
        "arme à feu", "couteau", "bombe*", "agress*", "harcel*", "suicide", "enfant perdu",
        "fuite de gaz", "blessé*", "évacu*",
    ),
    "es": (
        "incendio", "fuego", "humo", "sangr*", "inconsciente", "desmay*", "no respira",
        "no puede respirar", "infarto", "convulsi*", "ambulancia", "emergencia*", "urgencia*",
        "pistola", "arma", "cuchillo", "bomba*", "agredi*", "acoso", "suicid*", "niño perdido",
        "fuga de gas", "herido*", "evacua*",
    ),
    "ar": (
        "~حريق", "~دخان", "~نزيف", "~ينزف", "~إغماء", "~مغمى عليه", "~لا يتنفس", "~نوبة قلبية",
        "~سكتة", "~إسعاف", "~طوارئ", "~سلاح", "~سكين", "~قنبلة", "~اعتداء", "~تحرش", "~انتحار",
        "~طفل مفقود", "~تسرب غاز", "~مصاب", "~إخلاء",
    ),
}

URGENT_TERMS: dict[str, tuple[str, ...]] = {
    "en": ("urgent*", "asap", "right now", "immediately", "as soon as possible", "locked out"),
    "tr": ("ivedi*", "hemen", "derhal", "acele*"),
    "de": ("dringend*", "sofort"),
    "fr": ("tout de suite", "immédiatement"),
    "es": ("urgente*", "inmediatamente", "ahora mismo"),
    "ar": ("~عاجل", "~فورا", "~حالا"),
}

PERSONAL_TERMS: dict[str, tuple[str, ...]] = {
    "en": (
        "my badge", "my shift*", "my schedule", "my rota", "my visa", "my invitation letter",
        "my passport", "my payment", "my reimbursement", "my contract", "my registration",
        "my application", "my account", "my email", "my phone", "my address", "my allergy",
        "my medical", "my disability", "my dietary", "my name", "cancel my", "change my",
        "i am pregnant", "i'm pregnant", "i am sick", "i'm sick", "i will be late", "i'll be late",
        "i can't make it", "home address", "phone number of", "email of", "refund",
    ),
    "tr": (
        "vardiyam*", "yaka kartım*", "kartım*", "vizem*", "pasaportum*", "ödemem*", "sözleşmem*",
        "başvurum*", "kaydım*", "hesabım*", "telefon numaram*", "adresim*", "alerjim*", "engelim*",
        "hamileyim", "hastayım", "gelemeyeceğim", "geç kalacağım", "ev adresi*",
        "telefon numarası*",
    ),
    "de": (
        "meine schicht", "meinen ausweis", "mein ausweis", "mein badge", "mein visum",
        "meine bewerbung", "meine zahlung", "meine adresse", "meine telefonnummer",
        "meine allergie", "ich bin krank", "ich bin schwanger", "ich komme später",
    ),
    "fr": (
        "mon badge", "mon planning", "mon visa", "mon passeport", "mon paiement", "mon contrat",
        "ma candidature", "mon inscription", "mon adresse", "mon numéro", "mon allergie",
        "mon créneau", "je suis malade", "je suis enceinte",
    ),
    "es": (
        "mi turno", "mi credencial", "mi acreditación", "mi visa", "mi pasaporte", "mi pago",
        "mi contrato", "mi solicitud", "mi inscripción", "mi dirección", "mi teléfono",
        "mi alergia", "estoy enferm*", "estoy embarazada",
    ),
    "ar": (
        "~مناوبتي", "~شارتي", "~تأشيرتي", "~جواز سفري", "~دفعتي", "~عقدي", "~طلبي", "~عنواني",
        "~رقم هاتفي", "~حساسيتي", "~راتبي",
    ),
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_NUMBER_RE = re.compile(r"(?<!\d)\+?\d(?:[ ().-]?\d){6,}(?!\d)")


def fold(text: str) -> str:
    """Case- and accent-insensitive key: YANGIN, yangın and yangin all fold to 'yangin'."""
    text = unicodedata.normalize("NFKC", text).replace("’", "'").casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFD", text)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def _compile(term: str) -> re.Pattern[str]:
    if term.startswith("~"):
        return re.compile(re.escape(fold(term[1:])))
    is_prefix = term.endswith("*")
    body = re.escape(fold(term.rstrip("*"))).replace(r"\ ", r"\s+")
    tail = r"\w*" if is_prefix else r"(?!\w)"
    return re.compile(rf"(?<!\w){body}{tail}")


def _compile_table(table: dict[str, tuple[str, ...]]) -> list[tuple[str, str, re.Pattern[str]]]:
    return [(lang, term, _compile(term)) for lang, terms in table.items() for term in terms]


_TABLES = (
    (Route.EMERGENCY, _compile_table(EMERGENCY_TERMS)),
    (Route.URGENT, _compile_table(URGENT_TERMS)),
    (Route.PERSONAL, _compile_table(PERSONAL_TERMS)),
)


@dataclass(frozen=True)
class RuleHit:
    route: Route
    language: str
    term: str

    def __str__(self) -> str:
        return f"{self.route.value}:{self.language}:{self.term}"


@dataclass(frozen=True)
class Decision:
    route: Route
    hits: tuple[RuleHit, ...]

    @property
    def language(self) -> str | None:
        """Language of the first rule that decided the route. Personal-data hits have none."""
        for hit in self.hits:
            if hit.route is self.route and hit.language != "any":
                return hit.language
        return None


def route(text: str) -> Decision:
    """Pick the most serious route any rule matches; MODEL only if none match."""
    folded = fold(text)
    hits: list[RuleHit] = []
    for name, table in _TABLES:
        hits.extend(RuleHit(name, lang, term) for lang, term, rx in table if rx.search(folded))
    if _EMAIL_RE.search(text):
        hits.append(RuleHit(Route.PERSONAL, "any", "email-address"))
    if _LONG_NUMBER_RE.search(text):
        hits.append(RuleHit(Route.PERSONAL, "any", "long-number"))
    return Decision(hits[0].route if hits else Route.MODEL, tuple(hits))
