"""The fixed list of categories, shared by the API, the models and the frontend's dropdowns."""

CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Entertainment",
    "Utilities",
    "Health",
    "Education",
    "Subscriptions",
]
UNCATEGORIZED = "Uncategorized"
ALLOWED_CATEGORIES = [*CATEGORIES, UNCATEGORIZED]


def merchant_key(merchant: str) -> str:
    """How merchant names are compared: trimmed, lower-case, single spaces.
    'Sri Manjunath  Store ' and 'SRI MANJUNATH STORE' are the same shop."""
    return " ".join(merchant.lower().split())
