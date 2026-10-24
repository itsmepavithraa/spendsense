"""Keyword rules in front of the ML categoriser. All names here are invented."""
import pytest

from app.ml.inference import predict_categories
from app.ml.rules import rule_category


@pytest.mark.parametrize(
    "merchant, category",
    [
        ("City Grocery Store", "Groceries"),
        ("Lakshmi Provision Store", "Groceries"),
        ("Ravi General Store", "Groceries"),
        ("Corner Bakery", "Food & Dining"),
        ("Tiffin Centre", "Food & Dining"),
        ("Sri Sai Tiffen Room", "Food & Dining"),  # common local spelling
        ("Fresh Juice Corner", "Food & Dining"),
        ("Show Off Bake N Jui", "Food & Dining"),  # whole word "bake"
        ("Sribombaybadammilkstall", "Food & Dining"),  # run-together name: substring match
        ("Metro Kudlu Gate", "Transport"),
        ("Redbus India Private Limited", "Transport"),
        ("Power House Gym", "Health"),
        ("Sunrise Pharmacy", "Health"),
        ("Bigtree Entertainment Private", "Entertainment"),
        ("The Royal Silks", "Shopping"),
        ("Rose Fancy Store", "Shopping"),
        ("Green Department Store", "Shopping"),
    ],
)
def test_obvious_keywords_decide_the_category(merchant, category):
    assert rule_category(merchant) == category


@pytest.mark.parametrize(
    "merchant",
    [
        "Sri Manjunath Store",  # "store" alone is ambiguous: must NOT be guessed
        "Mahalingeshwara Store",
        "Ramesh Traders",
        "Pistola Systems",  # "ola" is only a keyword as a whole word
        "Mg Road",
        "Rahul Sharma",
    ],
)
def test_ambiguous_names_get_no_rule(merchant):
    assert rule_category(merchant) is None


def test_rules_do_not_override_brands_the_model_knows():
    # "Amazon Books" is Education for the model; no rule may steal it
    assert rule_category("Amazon Books") is None
    assert predict_categories(["Amazon Books"]) == ["Education"]


def test_names_the_model_has_never_seen_are_not_guessed():
    # regression: at a 0.5 confidence bar the model labelled a person "Transport"
    assert predict_categories(["Raguvaran", "Gangeri Chaitanya", "Sunil"]) == ["Uncategorized"] * 3


def test_brands_the_model_knows_still_get_their_category():
    assert predict_categories(["Netflix", "Swiggy", "Uber", "Amazon Books", "Medplus Pharmacy"]) == [
        "Subscriptions", "Food & Dining", "Transport", "Education", "Health",
    ]


def test_rules_then_model_then_uncategorized_in_one_batch():
    result = predict_categories(["Corner Bakery", "Swiggy", "Sri Manjunath Store"])
    assert result == ["Food & Dining", "Food & Dining", "Uncategorized"]
