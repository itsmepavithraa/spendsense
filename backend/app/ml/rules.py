"""Keyword rules that run BEFORE the ML categorizer.

Why rules as well as a model? The model learned a few dozen well-known brands. Real
statements are full of small shops ("Sri Lakshmi Provision Store", "City Bakery",
"Tiffin Centre") that it has never seen but that any person can categorise at a glance
from one word. A short list of unambiguous keywords catches those reliably and
explainably; everything else still goes to the model, and if the model is unsure the
row stays "Uncategorized" rather than being guessed.

Matching works on the lower-cased merchant name:
* keywords of 5+ letters match anywhere inside the name with spaces removed
  ("sribombaybadammilkstall" contains "milkstall");
* shorter keywords must be a whole word ("ola" must not match "pistola").

Keep keywords UNAMBIGUOUS. The generic word "store" is deliberately absent: "Mobile
Store" and "Grocery Store" are different things. Big brands the model already knows
(Amazon, Netflix...) are also left to it, so rules never override its confident answers.
Categories are checked in the order below; the first match wins.
"""
import re

RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Groceries",
        (
            "grocery", "groceries", "provision", "supermarket", "kirana", "vegetable", "fruits",
            "genaral", "general", "dmart", "zepto", "blinkit", "instamart", "bigbasket",
        ),
    ),
    (
        "Food & Dining",
        (
            "restaurant", "tiffin", "tiffen", "bakery", "bake", "cafe", "coffee", "juice", "lassi",
            "pizza", "dominos", "jubilant", "foodworks", "biryani", "hotel", "canteen", "sweets",
            "icecream", "milkstall", "swiggy", "zomato", "kfc", "burger", "dhaba", "mess",
        ),
    ),
    (
        "Transport",
        (
            "bmtc", "bmrcl", "metro", "redbus", "railway", "irctc", "uber", "rapido", "petrol",
            "fuel", "taxi", "cabs", "ola", "ksrtc", "bus", "auto",
        ),
    ),
    (
        "Health",
        (
            "pharmacy", "pharmeasy", "medical", "medplus", "apollo", "hospital", "clinic", "gym",
            "fitness", "diagnostic", "dental", "optical",
        ),
    ),
    (
        "Entertainment",
        ("bigtree", "bookmyshow", "cinema", "pvr", "inox", "theatre", "movie", "gaming"),
    ),
    (
        "Shopping",
        (
            "silks", "fancy", "department", "ekart", "meesho", "easybuy", "pilgrim", "textile",
            "garments", "fashion", "jewellers", "footwear", "electronics",
        ),
    ),
    ("Utilities", ("electricity", "bescom", "recharge", "broadband", "airtel", "jio", "bsnl")),
    ("Education", ("school", "college", "tuition", "academy", "university", "udemy", "coursera")),
]


def rule_category(merchant: str) -> str | None:
    """The category a keyword rule gives this merchant, or None if no rule applies."""
    lowered = merchant.lower()
    words = set(re.findall(r"[a-z]+", lowered))
    compact = re.sub(r"[^a-z]", "", lowered)
    for category, keywords in RULES:
        for keyword in keywords:
            if (len(keyword) >= 5 and keyword in compact) or keyword in words:
                return category
    return None
