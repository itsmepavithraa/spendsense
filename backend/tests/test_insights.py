"""Spending insights: the numbers must be right, and each tip must follow from them."""
from datetime import date, datetime, timedelta

import pytest

from app.insights import Txn, build_insights, inr, to_txn
from tests.conftest import register_and_login

END = date(2026, 10, 30)


def tx(day_offset: int, amount: float, merchant: str = "Some Shop", category: str = "Groceries") -> Txn:
    """A payment `day_offset` days before END."""
    return Txn(END - timedelta(days=day_offset), amount, merchant, category)


def tip_ids(result: dict) -> list[str]:
    return [t["id"] for t in result["suggestions"]]


def tip(result: dict, tip_id: str) -> dict:
    return next(t for t in result["suggestions"] if t["id"] == tip_id)


# ------------------------------------------------------------------- formatting
@pytest.mark.parametrize(
    "value, text",
    [(0, "₹0"), (999, "₹999"), (1000, "₹1,000"), (123456, "₹1,23,456"), (12345678, "₹1,23,45,678"), (-2500, "-₹2,500"), (99.6, "₹100")],
)
def test_rupees_use_indian_grouping(value, text):
    assert inr(value) == text


def test_late_night_utc_payments_land_on_the_next_indian_day():
    assert to_txn(datetime(2026, 9, 1, 18, 42, 2), 10, "x", "y").day == date(2026, 9, 2)  # 00:12 IST
    assert to_txn(datetime(2026, 9, 1, 18, 29, 59), 10, "x", "y").day == date(2026, 9, 1)  # 23:59 IST


# ------------------------------------------------------------------------ numbers
def sample() -> list[Txn]:
    return [
        tx(29, 1000, "Corner Cafe", "Food & Dining"),
        tx(28, 1000, "Corner Cafe", "Food & Dining"),
        tx(27, 1000, "Corner Cafe", "Food & Dining"),
        tx(25, 2000, "Mart", "Groceries"),
        tx(0, 500, "Metro", "Transport"),
    ]


def test_totals_shares_and_ordering_add_up():
    r = build_insights(sample(), 30)
    assert r["period"] == {"from": "2026-10-01", "to": "2026-10-30", "days": 30, "all_time": False}
    assert r["totals"]["spent"] == 5500 and r["totals"]["payments"] == 5
    assert r["totals"]["daily_average"] == round(5500 / 30, 2)
    assert [c["category"] for c in r["by_category"]] == ["Food & Dining", "Groceries", "Transport"]  # biggest first
    assert r["by_category"][0]["total"] == 3000 and r["by_category"][0]["count"] == 3
    assert sum(c["share_pct"] for c in r["by_category"]) == pytest.approx(100, abs=0.2)
    assert len(r["daily"]) == 30 and sum(d["total"] for d in r["daily"]) == 5500  # every day listed, none lost
    assert sum(w["total"] for w in r["by_weekday"]) == 5500
    assert r["top_merchants"][0] == {"merchant": "Corner Cafe", "total": 3000, "count": 3, "average": 1000}
    assert r["largest"][0]["amount"] == 2000


def test_no_previous_data_means_no_comparison():
    r = build_insights(sample(), 30)
    assert r["totals"]["previous_spent"] is None and r["totals"]["change_pct"] is None


def test_comparison_with_the_previous_period():
    # the previous 30 days run from offset 59 to 30; payments at both ends prove the data covers them
    earlier = [tx(59, 500, "Corner Cafe", "Food & Dining"), tx(50, 500, "Corner Cafe", "Food & Dining")]
    r = build_insights([*sample(), *earlier], 30)
    assert r["totals"]["previous_spent"] == 1000
    assert r["totals"]["change_pct"] == 450.0  # 5500 vs 1000
    food = r["by_category"][0]
    assert food["previous_total"] == 1000 and food["change_pct"] == 200.0


def test_no_comparison_when_the_history_barely_covers_the_previous_period():
    # a 31-day statement: one payment falls in the "previous 30 days", which is NOT a comparison
    r = build_insights([*sample(), tx(30, 194, "Corner Cafe", "Food & Dining")], 30)
    assert r["totals"]["previous_spent"] is None and r["totals"]["change_pct"] is None
    assert all(c["change_pct"] is None for c in r["by_category"])
    assert "category-rising" not in tip_ids(r) and not any("than the previous" in line for line in r["summary_lines"])


def test_the_comparison_needs_80_percent_coverage():
    # The window starts at offset 29, so the previous window is offsets 59..30. History that
    # begins at offset 53 covers 24 of its 30 days (80%): compared. Beginning at offset 52
    # covers 23 days (77%): not compared.
    covered = build_insights([*sample(), tx(53, 100, "Cafe", "Food & Dining")], 30)
    thin = build_insights([*sample(), tx(52, 100, "Cafe", "Food & Dining")], 30)
    assert covered["totals"]["previous_spent"] == 100
    assert thin["totals"]["previous_spent"] is None


def test_the_window_ends_on_the_latest_transaction_not_on_today():
    old = [Txn(date(2025, 1, 10), 100, "Shop", "Groceries"), Txn(date(2025, 1, 12), 200, "Shop", "Groceries")]
    r = build_insights(old, 30)
    assert r["period"]["to"] == "2025-01-12" and r["totals"]["spent"] == 300  # an old statement still works


def test_all_time_covers_everything_and_has_no_comparison():
    r = build_insights([tx(100, 100), tx(0, 200)], 0)
    assert r["period"]["all_time"] is True and r["period"]["days"] == 101
    assert r["totals"]["spent"] == 300 and r["totals"]["change_pct"] is None


def test_an_empty_account_is_not_an_error():
    r = build_insights([], 30)
    assert r["totals"]["spent"] == 0 and r["suggestions"] == [] and r["by_category"] == []
    assert "No spending" in r["summary_lines"][0]


# ------------------------------------------------------------------------- advice
def test_trim_tip_saving_is_15_percent_of_the_category_scaled_to_a_month():
    t = tip(build_insights(sample(), 30), "trim-discretionary")
    assert t["monthly_saving"] == 450  # 15% of 3000 over exactly 30 days
    assert "Food & Dining" in t["title"] and "₹3,000" in t["detail"] and "54.5%" in t["detail"]  # shows its working


def test_saving_scales_to_a_month_for_a_shorter_window():
    # ₹1,400 of food in only 14 days is ₹3,000 a month, so 15% is about ₹450 a month
    r = build_insights([tx(13, 700, "Cafe", "Food & Dining"), tx(0, 700, "Cafe", "Food & Dining")], 14)
    assert tip(r, "trim-discretionary")["monthly_saving"] == round(1400 * 0.15 * 30 / 14)


def test_many_small_payments_are_called_out_with_the_shop():
    small = [tx(i, 20, "Corner Shop") for i in range(12)]
    r = build_insights([*small, tx(0, 5000, "Furniture Mart", "Shopping")], 30)
    t = tip(r, "small-payments")
    assert "12 payments under ₹100" in t["detail"] and "Corner Shop" in t["detail"]
    assert t["monthly_saving"] == 48  # a fifth of the ₹240
    assert r["small_spends"]["count"] == 12 and r["small_spends"]["total"] == 240


def test_a_rising_category_is_flagged_with_its_increase():
    # latest payment is offset 10 (window 09-21..10-20); the previous window starts at offset 69
    r = build_insights([tx(10, 2000, "Metro", "Transport"), tx(69, 1000, "Metro", "Transport")], 30)
    t = tip(r, "category-rising")
    assert "up 100%" in t["title"] and t["monthly_saving"] == 1000


def test_subscriptions_are_summed_and_named():
    subs = [{"merchant": "Netflix", "amount": 649}, {"merchant": "Spotify", "amount": 119}]
    t = tip(build_insights(sample(), 30, subscriptions=subs), "subscriptions")
    assert "₹768" in t["detail"] and "Netflix" in t["detail"] and "₹9,216 a year" in t["detail"]


def test_one_shop_taking_a_big_share_is_flagged():
    r = build_insights([*[tx(i, 200, "Big Shop") for i in range(8)], tx(0, 1000, "Other", "Transport")], 30)
    assert "one-shop" in tip_ids(r)


def test_the_busiest_weekday_is_flagged():
    monday = date(2026, 10, 19)
    assert monday.weekday() == 0
    txns = [Txn(monday, 5000, "Shop", "Shopping")] + [Txn(monday + timedelta(days=i), 500, "Shop", "Groceries") for i in range(1, 5)]
    t = tip(build_insights(txns, 30), "weekday-peak")
    assert t["title"] == "You spend the most on Mondays"
    assert t["detail"].startswith("Mondays account for ₹5,000")


@pytest.mark.parametrize("offset, plural", [(0, "Mondays"), (1, "Tuesdays"), (3, "Thursdays"), (5, "Saturdays")])
def test_weekday_names_are_written_in_full(offset, plural):
    # regression: "Thu" + "s" once produced "Thus"
    peak = date(2026, 10, 19) + timedelta(days=offset)
    txns = [Txn(peak, 6000, "Shop", "Shopping")] + [Txn(peak - timedelta(days=i), 400, "Shop", "Groceries") for i in range(1, 6)]
    assert tip(build_insights(txns, 30), "weekday-peak")["title"].endswith(plural)


def test_a_tiny_change_is_described_as_about_the_same():
    earlier = [tx(59, 500, "Cafe", "Groceries"), tx(40, 500, "Cafe", "Groceries")]  # previous: 1000
    now = [tx(29, 500, "Cafe", "Groceries"), tx(0, 505, "Cafe", "Groceries")]  # now: 1005, +0.5%
    lines = build_insights([*earlier, *now], 30)["summary_lines"]
    assert any("about the same as the previous 30 days" in line for line in lines)
    assert not any("0% more" in line for line in lines)


def test_one_huge_payment_is_flagged():
    r = build_insights([tx(0, 400, "Mart", "Groceries"), tx(2, 9000, "Showroom", "Shopping")], 30)
    t = tip(r, "big-payment")
    assert "₹9,000" in t["detail"] and "Showroom" in t["detail"]


def test_uncategorized_money_is_flagged_only_when_it_is_a_big_share():
    big_share = build_insights([tx(1, 600, "Mystery", "Uncategorized"), tx(0, 400, "Mart", "Groceries")], 30)
    assert "categorise" in tip_ids(big_share)  # 60% of spending has no category
    small_share = build_insights([tx(1, 100, "Mystery", "Uncategorized"), tx(0, 900, "Mart", "Groceries")], 30)
    assert "categorise" not in tip_ids(small_share)  # 10%: not worth a nag


def test_good_news_is_given_when_spending_falls():
    r = build_insights([tx(5, 1000), tx(64, 2000)], 30)  # offset 64 is the first day of the previous window
    t = tip(r, "spending-down")
    assert t["priority"] == "good" and "down 50%" in t["title"]


def test_nothing_remarkable_means_no_advice_rather_than_invented_advice():
    r = build_insights([tx(3, 500), tx(2, 500), tx(1, 500)], 30)
    assert r["suggestions"] == []  # three ordinary grocery payments: nothing worth a tip


def test_tips_are_ordered_by_priority_then_saving_and_capped():
    r = build_insights([*sample(), tx(50, 1000, "Corner Cafe", "Food & Dining"), *[tx(i, 20, "Corner Shop") for i in range(12)]], 30)
    order = {"high": 0, "medium": 1, "low": 2, "good": 3}
    keys = [(order[t["priority"]], -(t["monthly_saving"] or 0)) for t in r["suggestions"]]
    assert keys == sorted(keys) and len(r["suggestions"]) <= 7
    assert all((t["monthly_saving"] or 0) >= 0 for t in r["suggestions"])


def test_the_summary_reads_correctly_for_one_payment_and_for_thousands():
    one = build_insights([tx(0, 50, "Cafe", "Groceries")], 30)["summary_lines"]
    assert "across 1 payment." in one[0] and any("1 of your payments was under" in line for line in one)
    many = build_insights([tx(i % 30, 50, "Cafe", "Groceries") for i in range(1200)], 30)["summary_lines"]
    assert "across 1,200 payments." in many[0]


def test_the_plain_words_summary_matches_the_numbers():
    lines = build_insights(sample(), 30)["summary_lines"]
    assert lines[0].startswith("You spent ₹5,500 from 2026-10-01 to 2026-10-30")
    assert any("Food & Dining: ₹3,000 (54.5%)" in line for line in lines)
    assert any("Corner Cafe" in line for line in lines)


# ------------------------------------------------------------------------ the API
def add(client, headers, merchant, amount, when, **extra):
    r = client.post("/transactions", json={"merchant": merchant, "amount": amount, "occurred_at": when, **extra}, headers=headers)
    assert r.status_code == 201, r.text


def test_the_endpoint_returns_the_analysis_for_my_data(client):
    headers = register_and_login(client)
    for i, day in enumerate((18, 19, 20)):
        add(client, headers, "Swiggy", 1000, f"2026-10-{day}T10:00:00+05:30")
    body = client.get("/analytics/insights?days=30", headers=headers).json()
    assert body["totals"]["spent"] == 3000 and body["totals"]["payments"] == 3
    assert body["by_category"][0]["category"] == "Food & Dining"
    assert "trim-discretionary" in [t["id"] for t in body["suggestions"]]
    assert body["summary_lines"] and body["period"]["to"] == "2026-10-20"


def test_days_are_bucketed_in_indian_time(client):
    headers = register_and_login(client)
    add(client, headers, "Swiggy", 500, "2026-10-20T23:30:00+00:00")  # 05:00 IST on the 21st
    body = client.get("/analytics/insights?days=30", headers=headers).json()
    assert body["totals"]["peak_day"]["date"] == "2026-10-21"


def test_insights_are_private_and_need_login(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")
    add(client, alice, "Swiggy", 1000, "2026-10-20T10:00:00+05:30")
    assert client.get("/analytics/insights", headers=bob).json()["totals"]["spent"] == 0
    assert client.get("/analytics/insights").status_code == 401


def test_the_window_length_is_validated(client):
    headers = register_and_login(client)
    assert client.get("/analytics/insights?days=0", headers=headers).status_code == 200  # all time
    assert client.get("/analytics/insights?days=90", headers=headers).status_code == 200
    for bad in (1, 6, 367, -5):
        assert client.get(f"/analytics/insights?days={bad}", headers=headers).status_code == 422


def test_a_brand_new_account_gets_a_friendly_empty_report(client):
    headers = register_and_login(client)
    body = client.get("/analytics/insights", headers=headers).json()
    assert body["totals"]["spent"] == 0 and body["suggestions"] == []
