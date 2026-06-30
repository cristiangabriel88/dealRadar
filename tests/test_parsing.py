"""Unit tests for normalization and brand/model extraction (no network)."""

from __future__ import annotations

import pytest

from olx_finder.parsing import (
    extract_brand_model,
    find_premium_components,
    is_kids_listing,
    is_part_listing,
    normalize,
    parse_wheel_inches,
)


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
