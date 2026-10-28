"""Rule checks for listing text. Pure functions, no API calls."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

from . import rules as R

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(com|net|org|io|co)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
ASIN = re.compile(r"\bB0[0-9A-Z]{8}\b")
HTML = re.compile(r"<(?!/?p\s*>|br\s*/?>)[^>]+>", re.I)
WORD = re.compile(r"[A-Za-z0-9']+")


@dataclass
class Violation:
    field: str          # title | bullet[2] | description | search_terms
    rule: str           # machine id
    severity: str       # fail | warn
    message: str        # what to fix, phrased for the copywriter model
    source: str = ""

    def as_dict(self):
        return asdict(self)


def _phrases(text: str, phrases: list[str]) -> list[str]:
    low = text.lower()
    return [p for p in phrases if re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", low)]


def check_title(title: str, brand: str = "") -> list[Violation]:
    v: list[Violation] = []
    n = len(title)
    if n > R.TITLE_MAX:
        v.append(Violation("title", "title.length", "fail",
                           f"Title is {n} characters; the limit is {R.TITLE_MAX} including spaces. Shorten it.",
                           R.SRC_TITLE_75))
    brand_chars = set(brand)
    bad = sorted({c for c in title if c in R.TITLE_BAD_CHARS and c not in brand_chars})
    if bad:
        v.append(Violation("title", "title.chars", "fail",
                           f"Remove the characters {' '.join(bad)} from the title.", R.SRC_TITLE_2025))
    counts = Counter(w.lower() for w in WORD.findall(title) if w.lower() not in R.MINOR_WORDS)
    rep = [w for w, c in counts.items() if c > 2]
    if rep:
        v.append(Violation("title", "title.repeat", "fail",
                           f"The word(s) {', '.join(rep)} appear more than twice in the title.", R.SRC_TITLE_2025))
    caps = [w for w in WORD.findall(title) if len(w) > 3 and w.isupper() and w not in brand.split()]
    if caps:
        v.append(Violation("title", "title.allcaps", "fail",
                           f"Do not write words in all caps: {', '.join(caps)}.", R.SRC_TITLE_GS))
    promo = _phrases(title, R.PROMO_PHRASES)
    if promo:
        v.append(Violation("title", "title.promo", "fail",
                           f"Remove promotional wording from the title: {', '.join(promo)}.", R.SRC_TITLE_GS))
    if any(ord(c) > 127 for c in title):
        v.append(Violation("title", "title.ascii", "fail",
                           "Use only standard letters, numbers and basic punctuation in the title.", R.SRC_TITLE_GS))
    if brand and not title.lower().startswith(brand.lower()):
        v.append(Violation("title", "title.brand_first", "warn",
                           f"Start the title with the brand name '{brand}'.", R.SRC_STYLE))
    return v


def check_bullets(bullets: list[str]) -> list[Violation]:
    v: list[Violation] = []
    if len(bullets) < 3:
        v.append(Violation("bullets", "bullets.count", "fail", "Provide at least 3 (ideally 5) bullet points.",
                           R.SRC_BULLETS_GS))
    seen = set()
    for i, b in enumerate(bullets):
        f = f"bullet[{i + 1}]"
        s = b.strip()
        if not (R.BULLET_MIN <= len(s) <= R.BULLET_MAX):
            v.append(Violation(f, "bullet.length", "fail",
                               f"Bullet {i + 1} is {len(s)} characters; keep it between {R.BULLET_MIN} and {R.BULLET_MAX}.",
                               R.SRC_BULLETS_GS))
        if s and not s[0].isupper():
            v.append(Violation(f, "bullet.capital", "fail", f"Start bullet {i + 1} with a capital letter.",
                               R.SRC_BULLETS_GS))
        if EMOJI.search(s):
            v.append(Violation(f, "bullet.emoji", "fail", f"Remove emojis from bullet {i + 1}.", R.SRC_BULLETS))
        bad = sorted({c for c in s if c in R.BULLET_BAD_CHARS})
        if bad:
            v.append(Violation(f, "bullet.chars", "fail", f"Remove {' '.join(bad)} from bullet {i + 1}.",
                               R.SRC_BULLETS_GS))
        g = _phrases(s, R.GUARANTEE_PHRASES)
        if g:
            v.append(Violation(f, "bullet.guarantee", "fail",
                               f"Remove guarantee or refund wording from bullet {i + 1}: {', '.join(g)}.", R.SRC_BULLETS))
        banned = _phrases(s, R.BULLET_BANNED) + _phrases(s, R.PESTICIDE)
        if banned:
            v.append(Violation(f, "bullet.claims", "fail",
                               f"Remove restricted claims from bullet {i + 1}: {', '.join(banned)}.", R.SRC_BULLETS_GS))
        warn = _phrases(s, R.UNVERIFIED_CLAIMS)
        if warn:
            v.append(Violation(f, "bullet.claims_unverified", "warn",
                               f"Bullet {i + 1} makes a claim that needs proof: {', '.join(warn)}.", R.SRC_PESTICIDE))
        promo = _phrases(s, R.PROMO_PHRASES)
        if promo:
            v.append(Violation(f, "bullet.promo", "fail",
                               f"Remove promotional wording from bullet {i + 1}: {', '.join(promo)}.", R.SRC_BULLETS_GS))
        if URL.search(s) or EMAIL.search(s) or PHONE.search(s):
            v.append(Violation(f, "bullet.contact", "fail", f"Remove URLs or contact details from bullet {i + 1}.",
                               R.SRC_BULLETS_GS))
        if s.strip().lower() in R.PLACEHOLDERS:
            v.append(Violation(f, "bullet.placeholder", "fail", f"Bullet {i + 1} is a placeholder.", R.SRC_BULLETS_GS))
        key = s.lower()
        if key in seen:
            v.append(Violation(f, "bullet.duplicate", "fail", f"Bullet {i + 1} duplicates another bullet.",
                               R.SRC_BULLETS_GS))
        seen.add(key)
    return v


def check_description(text: str) -> list[Violation]:
    v: list[Violation] = []
    if len(text) > R.DESCRIPTION_MAX:
        v.append(Violation("description", "description.length", "fail",
                           f"Description is {len(text)} characters; the limit is {R.DESCRIPTION_MAX}.", R.SRC_STYLE))
    if URL.search(text) or EMAIL.search(text) or PHONE.search(text):
        v.append(Violation("description", "description.contact", "fail",
                           "Remove web addresses, emails and phone numbers from the description.", R.SRC_STYLE))
    if HTML.search(text):
        v.append(Violation("description", "description.html", "fail",
                           "Use no HTML other than <p> and line breaks.", R.SRC_STYLE))
    claims = _phrases(text, R.PESTICIDE + R.BULLET_BANNED)
    if claims:
        v.append(Violation("description", "description.claims", "fail",
                           f"Remove restricted claims: {', '.join(claims)}.", R.SRC_PESTICIDE))
    promo = _phrases(text, R.PROMO_PHRASES)
    if promo:
        v.append(Violation("description", "description.promo", "fail",
                           f"Remove promotional wording: {', '.join(promo)}.", R.SRC_STYLE))
    return v


def check_search_terms(terms: str, title: str, brand: str = "") -> list[Violation]:
    v: list[Violation] = []
    size = len(terms.encode("utf-8"))
    if size > R.SEARCH_TERMS_MAX_BYTES:
        v.append(Violation("search_terms", "search.bytes", "fail",
                           f"Search terms are {size} bytes; the limit is {R.SEARCH_TERMS_MAX_BYTES} "
                           "(over the limit the whole field is ignored).", R.SRC_KEYWORDS))
    if ASIN.search(terms):
        v.append(Violation("search_terms", "search.asin", "fail", "Remove ASINs from search terms.", R.SRC_KEYWORDS))
    if brand and brand.lower() in terms.lower():
        v.append(Violation("search_terms", "search.brand", "fail",
                           f"Remove the brand name '{brand}' from search terms.", R.SRC_KEYWORDS))
    if re.search(r"[,;|]", terms):
        v.append(Violation("search_terms", "search.punct", "warn",
                           "Separate search terms with spaces, not punctuation.", R.SRC_KEYWORDS))
    words = [w.lower() for w in WORD.findall(terms)]
    dup = sorted({w for w, c in Counter(words).items() if c > 1})
    if dup:
        v.append(Violation("search_terms", "search.repeat", "fail",
                           f"Do not repeat words in search terms: {', '.join(dup)}.", R.SRC_KEYWORDS))
    title_words = {w.lower() for w in WORD.findall(title)} - R.MINOR_WORDS
    overlap = sorted(set(words) & title_words)
    if overlap:
        v.append(Violation("search_terms", "search.in_title", "fail",
                           f"Drop words already in the title: {', '.join(overlap)}.", R.SRC_KEYWORDS))
    subj = _phrases(terms, R.SEARCH_BANNED)
    if subj:
        v.append(Violation("search_terms", "search.subjective", "fail",
                           f"Remove subjective or time-sensitive words: {', '.join(subj)}.", R.SRC_KEYWORDS))
    return v


def check_listing(listing: dict, brand: str = "") -> list[Violation]:
    return (check_title(listing.get("title", ""), brand)
            + check_bullets(listing.get("bullets", []))
            + check_description(listing.get("description", ""))
            + check_search_terms(listing.get("search_terms", ""), listing.get("title", ""), brand))
