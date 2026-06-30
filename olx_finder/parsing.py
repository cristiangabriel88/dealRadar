"""Title normalization and brand/model extraction.

The marketplace pre-tags a brand on only a minority of listings, so the title
parser is the primary source of brand/model. We normalize hard (lowercase,
strip Romanian diacritics, collapse spacing/punctuation) before matching.
"""

from __future__ import annotations

import re
import unicodedata

from olx_finder.products import BIKES, Product

# Romanian diacritics -> ASCII. unicodedata handles the combining-mark cases,
# but we map the precomposed ones explicitly for clarity and to cover the
# comma-below vs cedilla variants of ș/ț.
_DIACRITIC_MAP = str.maketrans(
    {
        "ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t",
        "Ă": "a", "Â": "a", "Î": "i", "Ș": "s", "Ş": "s", "Ț": "t", "Ţ": "t",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9' ]+")
_MULTISPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip diacritics, and collapse spacing/punctuation.

    >>> normalize("GT Avalanche  3.0 — stare bună!")
    "gt avalanche 3 0 stare buna"
    """
    if not text:
        return ""
    text = text.translate(_DIACRITIC_MAP)
    # Decompose any remaining accented chars and drop combining marks.
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    text = text.lower()
    # Keep apostrophes (for "b'twin") and digits; turn everything else to space.
    text = _NON_ALNUM.sub(" ", text)
    return _MULTISPACE.sub(" ", text).strip()


# Precompute a normalized alias -> canonical brand map per product, longest
# aliases first so multi-word brands ("rock rider") win over their single-word
# substrings. Indices are built lazily and cached by product key (each product's
# ``brands`` dict is a stable module-level constant).
def _build_alias_index(brands: dict[str, list[str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for canonical, aliases in brands.items():
        seen: set[str] = set()
        for alias in [canonical, *aliases]:
            norm = normalize(alias)
            if norm and norm not in seen:
                seen.add(norm)
                pairs.append((norm, canonical))
    # Longest alias first to prefer the most specific match.
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


_ALIAS_CACHE: dict[str, list[tuple[str, str]]] = {}


def _alias_index(product: Product) -> list[tuple[str, str]]:
    index = _ALIAS_CACHE.get(product.key)
    if index is None:
        index = _build_alias_index(product.brands)
        _ALIAS_CACHE[product.key] = index
    return index


# A model token: an alphanumeric word, optionally with a trailing number group
# (e.g. "marlin", "7", "540", "avalanche").
_WORD = re.compile(r"[a-z0-9]+")
# A 4-digit model year (1990-2099). Years are never part of a model name, so we
# never let one become (or extend) the model — "Avalanche 2020" is an Avalanche.
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def _extract_model(norm_title: str, alias: str, stopwords: frozenset[str]) -> str | None:
    """Extract the model family following the brand alias.

    Up to two meaningful tokens following the brand form the model, so real
    multi-word models survive ("touring sl", "marlin 7", "st 540"). Descriptive
    tails ("bun", "import") are stopwords and model years ("2020") are dropped, so
    all "GT Avalanche …" listings collapse to one comparable model rather than
    fragmenting into one-off groups.
    """
    idx = norm_title.find(alias)
    if idx == -1:
        return None
    tail = norm_title[idx + len(alias):].strip()
    tokens = _WORD.findall(tail)
    model_tokens: list[str] = []
    for tok in tokens:
        if tok in stopwords:
            # Stop at the first descriptor once we already have a model word;
            # otherwise skip leading stopwords and keep looking.
            if model_tokens:
                break
            continue
        if _YEAR_RE.match(tok):
            # A model year is never part of the name: stop if it trails the model,
            # skip it if it leads (e.g. "GT 2020 Avalanche").
            if model_tokens:
                break
            continue
        model_tokens.append(tok)
        # A name token plus one trailing token (e.g. "marlin" "7") -> take both.
        if len(model_tokens) >= 2:
            break
    if not model_tokens:
        return None
    return " ".join(model_tokens)


def extract_brand_model(
    title: str, brand_hint: str | None = None, product: Product = BIKES
) -> tuple[str | None, str | None]:
    """Return (canonical_brand, model) for a listing title.

    Prefers the marketplace-provided ``brand_hint`` when it matches a known
    brand, otherwise scans the normalized title for any known alias. ``model``
    may be None when nothing usable follows the brand. ``product`` selects which
    brand list and model-stopword vocabulary to match against (default: bikes).
    """
    norm_title = normalize(title)
    alias_index = _alias_index(product)

    # 1) Trust the marketplace brand hint if it maps to a known brand.
    chosen_brand: str | None = None
    chosen_alias: str | None = None
    if brand_hint:
        norm_hint = normalize(brand_hint)
        for alias, canonical in alias_index:
            if norm_hint == alias:
                chosen_brand = canonical
                # Find the alias inside the title (if present) for model parsing.
                chosen_alias = alias if alias in norm_title else None
                break

    # 2) Otherwise scan the title for the first (longest) alias present.
    if chosen_brand is None:
        for alias, canonical in alias_index:
            if _alias_in_title(norm_title, alias):
                chosen_brand = canonical
                chosen_alias = alias
                break

    if chosen_brand is None:
        return None, None

    model = (
        _extract_model(norm_title, chosen_alias, product.model_stopwords)
        if chosen_alias
        else None
    )
    return chosen_brand, model


def _alias_in_title(norm_title: str, alias: str) -> bool:
    """Whole-word/phrase containment so 'gt' doesn't match 'light'."""
    pattern = r"(?:^| )" + re.escape(alias) + r"(?: |$)"
    return re.search(pattern, norm_title) is not None


def is_part_listing(title: str, product: Product = BIKES) -> bool:
    """True when the title indicates parts/accessories rather than a whole item.

    Three tiers, from strongest to weakest:

    * ``part_noise_tokens`` — "strong": always a part, dropped outright (a
      complete item never titles itself "cadru"/"amplificator").
    * ``part_component_tokens`` — a part word a *whole item also names* ("frane
      disc", "doze EMG"). Kept when a ``whole_item_tokens`` word **or** a known
      brand is present (the item is describing its own components), else a part.
    * ``part_accessory_tokens`` — a separate add-on ("husa", "pompa"). A standalone
      accessory listing routinely names the item it's *for* ("husa chitara",
      "pompa bicicleta"), so a whole-item word does NOT rescue it — only a known
      brand does ("Trek Marlin cu pompa cadou" survives; "pompa bicicleta" drops).

    Products that leave the component/accessory sets empty keep the strict "any
    strong token => a part" behaviour.
    """
    tokens = set(normalize(title).split())
    if tokens & product.part_noise_tokens:
        return True

    component_hit = bool(tokens & product.part_component_tokens)
    accessory_hit = bool(tokens & product.part_accessory_tokens)
    if not (component_hit or accessory_hit):
        return False

    # A real brand rescues both tiers (a branded item naming an add-on is the item).
    if extract_brand_model(title, product=product)[0] is not None:
        return False
    # A whole-item word rescues only a component listing, not a standalone accessory.
    if component_hit and (tokens & product.whole_item_tokens):
        return False
    return True


def detect_condition(
    title: str, description: str | None = None, product: Product = BIKES
) -> str | None:
    """Best-effort condition read from a listing's title/description.

    Returns ``"needs_work"``, ``"refurbished"``, ``"like_new"`` or ``None`` (no
    condition wording found). Scans both fields (like
    :func:`find_premium_components`) and applies the worst-case tier when wording
    collides: ``needs_work`` > ``refurbished`` > ``like_new``, so a "defect"
    caveat outweighs a boilerplate "stare buna". Drives the per-condition fix-up
    buffer in the margin/ROI math (see :class:`olx_finder.models.DealResult`).
    """
    tokens = set(normalize(f"{title} {description or ''}").split())
    if tokens & product.condition_needs_work_tokens:
        return "needs_work"
    if tokens & product.condition_refurbished_tokens:
        return "refurbished"
    if tokens & product.condition_like_new_tokens:
        return "like_new"
    return None


# Premium-component alias index, built lazily and cached per product (same shape
# and whole-word/phrase matching as the brand index).
_PREMIUM_CACHE: dict[str, list[tuple[str, str]]] = {}


def _premium_index(product: Product) -> list[tuple[str, str]]:
    index = _PREMIUM_CACHE.get(product.key)
    if index is None:
        index = _build_alias_index(product.premium_components)
        _PREMIUM_CACHE[product.key] = index
    return index


def find_premium_components(
    title: str, description: str | None = None, product: Product = BIKES
) -> list[str]:
    """Canonical premium-component labels named in the title/description.

    Scans both fields (a neglected listing often buries the good parts in the
    body) for any of ``product.premium_components``. Each component is reported
    once, longest-alias-first so a multi-word alias wins over its substrings.
    Returns [] when the product defines no premium vocabulary.
    """
    text = normalize(f"{title} {description or ''}")
    found: list[str] = []
    seen: set[str] = set()
    for alias, canonical in _premium_index(product):
        if canonical in seen:
            continue
        if _alias_in_title(text, alias):
            seen.add(canonical)
            found.append(canonical)
    return found


# Plausible bicycle wheel diameters (inches) to avoid matching frame sizes etc.
_PLAUSIBLE_WHEELS = {12, 14, 16, 20, 24, 26, 27, 28, 29}
# A standalone 2-digit number (optionally .5), not part of a longer number such
# as a year ("2024") or a price. Boundaries prevent matching inside 4-digit runs.
_WHEEL_RE = re.compile(r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)")


def parse_wheel_inches(title: str) -> float | None:
    """Best-effort wheel diameter (inches) from a title, or None.

    Works on the raw title (lowercased) so decimals like 27.5 survive; ignores
    4-digit years and only accepts diameters that are plausible wheel sizes.
    """
    text = title.lower().replace(",", ".")
    for match in _WHEEL_RE.finditer(text):
        try:
            val = float(match.group(1))
        except ValueError:
            continue
        if int(round(val)) in _PLAUSIBLE_WHEELS:
            return val
    return None


def is_kids_listing(
    title: str, wheel_inches: float | None, product: Product = BIKES
) -> bool:
    """True when a listing is a kids/junior item (or, for bikes, a small-wheel one).

    The wheel-size guard only applies to products that define one
    (``product.small_wheel_max_inches``); products without it (e.g. guitars) are
    judged on the kids title tokens alone.
    """
    max_wheel = product.small_wheel_max_inches
    if max_wheel is not None and wheel_inches is not None and wheel_inches <= max_wheel:
        return True
    tokens = set(normalize(title).split())
    if tokens & product.kids_title_tokens:
        return True
    if max_wheel is not None:
        # Fall back to a wheel size parsed from the title itself.
        title_wheel = parse_wheel_inches(title)
        if title_wheel is not None and title_wheel <= max_wheel:
            return True
    return False
