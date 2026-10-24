"""Small text helpers shared by retrieval, quoting and the citation guard.

PDF text is untrusted data: these functions only measure and slice it.
"""

import re
import unicodedata

STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because
    been before being below between both but by can could did do does doing down during
    each few for from further had has have having he her here hers herself him himself
    his how i if in into is it its itself just me more most my myself no nor not now of
    off on once only or other our ours ourselves out over own same she should so some
    such than that the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which while who whom
    why will with would you your yours yourself yourselves paper papers study studies
    show shows shown use used using et al""".split()
)

NEGATIONS = frozenset(
    "no not never none cannot without fails fail failed neither nor lack lacks "
    "worse decrease decreases decreased reduce reduces reduced unlike".split()
)

_WORD = re.compile(r"[a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9]", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?%?")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
# "1 INTRODUCTION 1 ", "APPENDIX 15 ", "3.2 RESULTS ": section numbers, upper-case
# headings and page numbers in front of the first real word.
_HEADING_PREFIX = re.compile(
    r"^(?:[\d.]+\s+)?(?:[A-Z][A-Z\-&]{2,}\s+)+(?:\d+\s+)?(?=[A-Z])"
)
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_PUNCTUATION = str.maketrans(
    {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-"}
)


def words(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD.finditer(text)]


def content_terms(text: str) -> list[str]:
    """Lower-cased words that carry meaning (no stopwords, at least 3 letters)."""
    return [w for w in words(text) if len(w) > 2 and w not in STOPWORDS]


def numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def has_negation(text: str) -> bool:
    return any(word in NEGATIONS for word in words(text)) or "n't" in text.lower()


def clean_display(text: str) -> str:
    """Joins words hyphenated across lines and collapses whitespace."""
    for ligature, letters in _LIGATURES.items():
        text = text.replace(ligature, letters)
    return " ".join(_HYPHEN_BREAK.sub(r"\1\2", text).split())


def normalize_for_match(text: str) -> str:
    """The form both sides take before a quote is checked against its chunk."""
    text = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return " ".join(text.casefold().split())


def quote_in_text(quote: str, text: str) -> bool:
    """True when `quote` is in `text`, ignoring whitespace, case and hyphenation."""
    needle = normalize_for_match(quote).strip(" .\"'")
    return len(needle) >= 12 and needle in normalize_for_match(text)


def sentences(text: str, *, min_length: int = 30, max_length: int = 400) -> list[str]:
    """Display-ready sentences of `text`; long runs are cut at a word boundary.

    Running heads glued to a sentence ("3 METHOD 5 We train…") are dropped, so
    each sentence stays a substring of the chunk's text.
    """
    result = []
    for sentence in _SENTENCE_END.split(clean_display(text)):
        sentence = _HEADING_PREFIX.sub("", sentence.strip()).strip()
        if len(sentence) < min_length:
            continue
        if len(sentence) > max_length:
            sentence = sentence[:max_length].rsplit(" ", 1)[0]
        result.append(sentence)
    return result


def overlap(query_terms: set[str], text: str) -> float:
    """Share of the query's terms that appear in `text` (0–1)."""
    if not query_terms:
        return 0.0
    return len(query_terms & set(content_terms(text))) / len(query_terms)


def best_sentences(text: str, query: str, count: int = 1) -> list[str]:
    """The sentences of `text` that share the most terms with `query`."""
    terms = set(content_terms(query))
    candidates = sentences(text)
    if not candidates:
        cleaned = clean_display(text)
        return [cleaned[:300].rsplit(" ", 1)[0] if len(cleaned) > 300 else cleaned]
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (-overlap(terms, item[1]), item[0]),
    )
    return [sentence for _, sentence in ranked[:count]]


def short_value(sentence: str, limit: int = 160) -> str:
    if len(sentence) <= limit:
        return sentence
    return sentence[:limit].rsplit(" ", 1)[0] + "…"
