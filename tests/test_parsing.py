"""Unit tests for normalization and brand/model extraction (no network)."""

from __future__ import annotations

import pytest

from olx_finder.parsing import (
    detect_condition,
    extract_brand_model,
    find_premium_components,
    is_kids_listing,
    is_part_listing,
    normalize,
    parse_wheel_inches,
)
from olx_finder.products import GUITARS


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("GT Avalanche  3.0 — stare bună!", "gt avalanche 3 0 stare buna"),
        ("Bicicletă Btwin Rockrider", "bicicleta btwin rockrider"),
        ("ȘĂÎÂȚ", "saiat"),
        ("  multiple   spaces  ", "multiple spaces"),
        ("B'Twin Triban", "b'twin triban"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "title, brand, model",
    [
        ("GT Avalanche 3.0", "GT", "avalanche 3"),
        ("Bicicleta Trek Marlin 7 2021", "Trek", "marlin 7"),
        ("Vand Specialized Rockhopper", "Specialized", "rockhopper"),
        ("Rockrider ST 540 stare buna", "Rockrider", "st 540"),
        ("Bicicleta Cannondale Habit", "Cannondale", "habit"),
        ("bicicleta fara brand cunoscut", None, None),
    ],
)
def test_extract_brand_model(title: str, brand: str | None, model: str | None) -> None:
    got_brand, got_model = extract_brand_model(title)
    assert got_brand == brand
    assert got_model == model


def test_brand_hint_aliases_to_canonical() -> None:
    # OLX tags Decathlon house bikes as "B'Twin"; both normalize to Btwin.
    brand, _ = extract_brand_model("Bicicleta de oras", brand_hint="B'Twin")
    assert brand == "Btwin"
    brand2, _ = extract_brand_model("bicicleta", brand_hint="Decathlon")
    assert brand2 == "Btwin"


def test_brand_word_boundary() -> None:
    # "gt" must not match inside "light".
    assert extract_brand_model("bicicleta light usoara")[0] is None


@pytest.mark.parametrize(
    "title",
    [
        "Cadru carbon 29er",
        "Roti 28 inch",
        "Set piese bicicleta",
        "Furca RockShox",
        "Ghidon aluminiu",
    ],
)
def test_is_part_listing(title: str) -> None:
    assert is_part_listing(title) is True


def test_whole_bike_not_part() -> None:
    assert is_part_listing("Bicicleta Trek Marlin 7") is False


@pytest.mark.parametrize(
    "title",
    [
        "Bicicleta MTB 26 frane disc",   # component word, but a whole bike (mtb)
        "MTB hardtail roti 29 frane hidraulice",  # "roti 29" = wheel size, not a wheel
        "Trek Marlin frane disc",        # known brand present
    ],
)
def test_component_word_with_whole_item_is_not_part(title: str) -> None:
    # The loosened filter must keep bikes described by their components.
    assert is_part_listing(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "Frane disc hidraulice Shimano",  # no whole-item word, no known brand
        "Schimbator spate 9v",
        "Roti 28 inch",                    # still a bare wheel listing
    ],
)
def test_bare_component_is_still_part(title: str) -> None:
    assert is_part_listing(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Trek Marlin cu pompa si casca cadou",       # brand rescues the accessory
        "Specialized Rockhopper cu suport telefon",
        "Giant Talon cu portbagaj si far cadou",
    ],
)
def test_branded_bike_with_bonus_accessory_is_not_part(title: str) -> None:
    # The recall fix: a *branded* bike that merely mentions a bonus accessory must
    # survive (previously the strong "pompa"/"casca"/… dropped it outright).
    assert is_part_listing(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "Pompa bicicleta cu manometru",  # accessory; whole-item word does NOT rescue
        "Casca protectie marime L",
        "Portbagaj spate bicicleta",
    ],
)
def test_bare_accessory_is_still_part(title: str) -> None:
    # A standalone accessory names the item it's for, so a whole-item word can't
    # rescue it — only a real brand can (see test above).
    assert is_part_listing(title) is True


@pytest.mark.parametrize(
    "title, description, expected",
    [
        ("Bicicleta noua nefolosita", None, "like_new"),
        ("Bicicleta MTB", "frane defecte, necesita reparatii", "needs_work"),
        ("Bicicleta reconditionata, revizie facuta", None, "refurbished"),
        ("Bicicleta stare buna ca noua", "dar are o janta defecta", "needs_work"),  # worst wins
        ("Chitara reconditionata impecabila", None, "refurbished"),  # refurb > like_new
        ("Bicicleta de oras", "stare ok", None),  # no condition wording
    ],
)
def test_detect_condition(title: str, description: str | None, expected: str | None) -> None:
    assert detect_condition(title, description) == expected


def test_guitar_branded_with_bonus_accessory_is_not_part() -> None:
    # Guitar parity: a *branded* guitar that throws in a case/tuner survives.
    assert is_part_listing("Fender Stratocaster cu husa", GUITARS) is False
    assert is_part_listing("Yamaha F310 cu husa si acordor", GUITARS) is False


def test_guitar_naming_premium_pickups_survives() -> None:
    # A cheap guitar advertising its pickups is a sleeper: the component tier +
    # whole-item word keeps it (it used to be dropped by the strong "doze" token).
    assert is_part_listing("Chitara electrica cu doze EMG active", GUITARS) is False
    # But bare pickups on their own are still a part.
    assert is_part_listing("Doze EMG active de vanzare", GUITARS) is True


@pytest.mark.parametrize(
    "title",
    [
        "Husa chitara clasica",      # accessory; whole-item word does NOT rescue
        "Amplificator chitara 30W",  # strong standalone gear
        "Set corzi pentru chitara",
    ],
)
def test_guitar_bare_part_is_still_part(title: str) -> None:
    assert is_part_listing(title, GUITARS) is True


def test_guitar_premium_components() -> None:
    found = find_premium_components(
        "Chitara electrica",
        description="cu Floyd Rose si doze EMG, corp mahon",
        product=GUITARS,
    )
    assert "Floyd Rose" in found
    assert "EMG" in found
    assert "Mahogany" in found
    assert find_premium_components("Chitara clasica incepatori", product=GUITARS) == []


def test_find_premium_components() -> None:
    # Reads both title and description, dedups, and labels canonically.
    found = find_premium_components(
        "Bicicleta MTB", description="schimbator Deore XT, furca RockShox, cadru carbon"
    )
    assert "XT" in found
    assert "RockShox" in found
    assert "Carbon" in found
    # A plain bike with no premium parts named returns nothing.
    assert find_premium_components("Bicicleta de oras", description="stare buna") == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('26"', 26.0),
        ("bicicleta 27.5 inch", 27.5),
        ("MTB 29er", 29.0),
        ("fara marime", None),
    ],
)
def test_parse_wheel_inches(raw: str, expected: float | None) -> None:
    assert parse_wheel_inches(raw) == expected


def test_is_kids_listing() -> None:
    assert is_kids_listing("Bicicleta pentru copii", None) is True
    assert is_kids_listing("Bicicleta 14 inch", None) is True
    assert is_kids_listing("Bicicleta MTB adulti", 26.0) is False
    # Wheel param overrides: a 16" bike is a kids bike.
    assert is_kids_listing("Bicicleta oras", 16.0) is True
