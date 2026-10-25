import pytest

from backend.agents.narration import NarrationError, validate_narration


def rental_context(role="buyer"):
    return {
        "role": role,
        "action": "COUNTER",
        "terms": {
            "price": "20",
            "pickup": "2026-10-28T17:00:00-07:00",
            "location": "Hayden Library",
            "rental_days": 3,
        },
        "previous_offer": {
            "price": "16",
            "pickup": "2026-10-28T17:00:00-07:00",
            "location": "Hayden Library",
            "rental_days": 3,
        },
        "item": {"title": "TI-84 Calculator", "type": "Rent"},
        "conversation": [
            {"role": "buyer", "text": "Would $16 work?", "terms": None}
        ],
    }


def test_rejects_false_per_day_price():
    with pytest.raises(NarrationError, match="total"):
        validate_narration("Could we do {price} per day?", rental_context())


def test_rejects_seller_claiming_pickup():
    with pytest.raises(NarrationError, match="Seller"):
        validate_narration(
            "I can pick up at {location} for {price}.",
            rental_context("seller"),
        )


def test_allows_total_rental_price():
    assert validate_narration(
        "Could we do {price} for the whole rental?",
        rental_context(),
    ) == "Could we do {price} for the whole rental?"
