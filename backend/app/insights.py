"""Spending insights: where the money goes, what to watch, and how much could be saved.

Pure functions over a list of transactions, so every number and every piece of advice
can be tested without a database. The advice is rule-based and explainable: each tip
says which of the user's own numbers triggered it, and its saving is an estimate worked
out from those numbers, never a promise. It is not financial advice.

Dates are bucketed in Indian time (IST), the same assumption the statement importer
makes, so a late-night payment lands on the day the user remembers it.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.categories import UNCATEGORIZED, merchant_key

IST = timedelta(hours=5, minutes=30)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # short names for the charts
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]  # for sentences
DISCRETIONARY = {"Food & Dining", "Shopping", "Entertainment"}  # spending a person can choose to reduce
SMALL_PAYMENT = 100.0  # rupees: payments below this count as "small"
CUT_RATE = 0.15  # the realistic trim suggested for a discretionary category


@dataclass
class Txn:
    day: date  # in IST
    amount: float
    merchant: str
    category: str


def to_txn(occurred_at: datetime, amount, merchant: str, category: str) -> Txn:
    """Database row to Txn. SQLite hands back naive datetimes (they are UTC); PostgreSQL
    hands back aware ones."""
    moment = occurred_at.replace(tzinfo=timezone.utc) if occurred_at.tzinfo is None else occurred_at
    local = moment.astimezone(timezone.utc) + IST
    return Txn(local.date(), float(amount), merchant, category)


def inr(value: float) -> str:
    """12345678 -> ₹1,23,45,678 (Indian digit grouping)."""
    n = int(round(value))
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{'-' if n < 0 else ''}₹{digits}"


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _change(current: float, previous: float) -> float | None:
    return round(100 * (current - previous) / previous, 1) if previous else None


def build_insights(txns: list[Txn], days: int, subscriptions: list[dict] | None = None) -> dict:
    """days = length of the window ending on the user's latest transaction; 0 = everything."""
    if not txns:
        return _empty(days)

    end = max(t.day for t in txns)  # anchored on the data, so an older statement still works
    start = end - timedelta(days=days - 1) if days else min(t.day for t in txns)
    span = (end - start).days + 1
    current = [t for t in txns if start <= t.day <= end]
    if not current:
        return _empty(days, start, end)

    # Compare with the previous window only when the data really covers it. A statement of
    # 31 days has just one day of "previous 30 days"; calling that a +13,000% jump would be
    # nonsense, so at least 80% of the earlier window must lie inside the user's history.
    previous: list[Txn] = []
    if days:
        data_start = min(t.day for t in txns)
        prev_start = start - timedelta(days=days)
        covered_days = (start - max(prev_start, data_start)).days
        if covered_days >= 0.8 * days:
            previous = [t for t in txns if prev_start <= t.day < start]

    spent = sum(t.amount for t in current)
    prev_spent = sum(t.amount for t in previous) if previous else None
    per_month = 30 / span  # scales a saving found in this window to "per month"

    # ---- by category (with the same figures for the previous window)
    cat_total: dict[str, float] = defaultdict(float)
    cat_count: Counter = Counter()
    for t in current:
        cat_total[t.category] += t.amount
        cat_count[t.category] += 1
    prev_cat: dict[str, float] = defaultdict(float)
    for t in previous:
        prev_cat[t.category] += t.amount
    by_category = [
        {
            "category": c,
            "total": round(v, 2),
            "count": cat_count[c],
            "share_pct": _pct(v, spent),
            "previous_total": round(prev_cat[c], 2) if previous else None,
            "change_pct": _change(v, prev_cat[c]) if previous else None,
        }
        for c, v in sorted(cat_total.items(), key=lambda kv: -kv[1])
    ]

    # ---- by shop (one entry per shop, however it was capitalised)
    shop_total: dict[str, float] = defaultdict(float)
    shop_count: Counter = Counter()
    shop_name: dict[str, str] = {}
    for t in current:
        key = merchant_key(t.merchant)
        shop_total[key] += t.amount
        shop_count[key] += 1
        shop_name.setdefault(key, t.merchant)
    top_merchants = [
        {"merchant": shop_name[k], "total": round(v, 2), "count": shop_count[k], "average": round(v / shop_count[k], 2)}
        for k, v in sorted(shop_total.items(), key=lambda kv: -kv[1])[:10]
    ]

    # ---- per day, and per weekday
    per_day: dict[date, float] = defaultdict(float)
    for t in current:
        per_day[t.day] += t.amount
    daily = [
        {"date": (start + timedelta(days=i)).isoformat(), "total": round(per_day.get(start + timedelta(days=i), 0.0), 2)}
        for i in range(span)
    ]
    wd_total: dict[int, float] = defaultdict(float)
    wd_count: Counter = Counter()
    for t in current:
        wd_total[t.day.weekday()] += t.amount
        wd_count[t.day.weekday()] += 1
    by_weekday = [{"weekday": WEEKDAYS[i], "total": round(wd_total[i], 2), "count": wd_count[i]} for i in range(7)]
    peak_date, peak_amount = max(per_day.items(), key=lambda kv: kv[1])

    # ---- small payments add up
    small = [t for t in current if t.amount < SMALL_PAYMENT]
    small_total = sum(t.amount for t in small)
    small_shop_total: dict[str, float] = defaultdict(float)
    small_shop_count: Counter = Counter()
    for t in small:
        key = merchant_key(t.merchant)
        small_shop_total[key] += t.amount
        small_shop_count[key] += 1
    small_spends = {
        "threshold": SMALL_PAYMENT,
        "count": len(small),
        "total": round(small_total, 2),
        "share_of_payments_pct": _pct(len(small), len(current)),
        "top_merchants": [
            {"merchant": shop_name[k], "count": small_shop_count[k], "total": round(v, 2)}
            for k, v in sorted(small_shop_total.items(), key=lambda kv: -kv[1])[:5]
        ],
    }

    # ---- biggest payments
    largest = [
        {"date": t.day.isoformat(), "merchant": t.merchant, "category": t.category, "amount": round(t.amount, 2)}
        for t in sorted(current, key=lambda t: -t.amount)[:5]
    ]

    uncategorized_total = cat_total.get(UNCATEGORIZED, 0.0)
    uncategorized = {"count": cat_count.get(UNCATEGORIZED, 0), "total": round(uncategorized_total, 2), "share_pct": _pct(uncategorized_total, spent)}

    totals = {
        "spent": round(spent, 2),
        "payments": len(current),
        "daily_average": round(spent / span, 2),
        "previous_spent": round(prev_spent, 2) if prev_spent is not None else None,
        "change_pct": _change(spent, prev_spent) if prev_spent else None,
        "peak_day": {"date": peak_date.isoformat(), "total": round(peak_amount, 2)},
    }

    result = {
        "period": {"from": start.isoformat(), "to": end.isoformat(), "days": span, "all_time": days == 0},
        "totals": totals,
        "by_category": by_category,
        "top_merchants": top_merchants,
        "daily": daily,
        "by_weekday": by_weekday,
        "small_spends": small_spends,
        "largest": largest,
        "uncategorized": uncategorized,
    }
    result["suggestions"] = _suggestions(result, per_month, subscriptions or [])
    result["summary_lines"] = _summary(result)
    return result


def _empty(days: int, start: date | None = None, end: date | None = None) -> dict:
    return {
        "period": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None, "days": days, "all_time": days == 0},
        "totals": {"spent": 0, "payments": 0, "daily_average": 0, "previous_spent": None, "change_pct": None, "peak_day": None},
        "by_category": [], "top_merchants": [], "daily": [], "by_weekday": [],
        "small_spends": {"threshold": SMALL_PAYMENT, "count": 0, "total": 0, "share_of_payments_pct": 0, "top_merchants": []},
        "largest": [], "uncategorized": {"count": 0, "total": 0, "share_pct": 0},
        "suggestions": [],
        "summary_lines": ["No spending found in this period. Add transactions or import a bank statement to see insights."],
    }


# ------------------------------------------------------------------------------ advice
def _suggestions(r: dict, per_month: float, subscriptions: list[dict]) -> list[dict]:
    """Each tip names the numbers that triggered it. monthly_saving is an estimate."""
    spent = r["totals"]["spent"]
    cats = {c["category"]: c for c in r["by_category"]}
    tips: list[dict] = []

    def tip(tip_id: str, priority: str, title: str, detail: str, saving: float | None = None) -> None:
        tips.append({"id": tip_id, "priority": priority, "title": title, "detail": detail,
                     "monthly_saving": round(saving) if saving else None})

    # 1. trim the biggest discretionary category
    discretionary = [c for c in r["by_category"] if c["category"] in DISCRETIONARY and c["share_pct"] >= 5]
    if discretionary:
        c = discretionary[0]
        saving = c["total"] * CUT_RATE * per_month
        tip("trim-discretionary", "high", f"Trim {c['category']} by {int(CUT_RATE * 100)}%",
            f"{c['category']} took {inr(c['total'])} ({c['share_pct']}% of your spending) across {c['count']} payments. "
            f"This is spending you can choose to reduce: a {int(CUT_RATE * 100)}% cut saves about {inr(saving)} a month.", saving)

    # 2. many small payments
    s = r["small_spends"]
    if s["count"] >= 10 and (s["share_of_payments_pct"] >= 30 or s["total"] >= 0.05 * spent):
        top = s["top_merchants"][0] if s["top_merchants"] else None
        where = f" Most went to {top['merchant']} ({top['count']} payments, {inr(top['total'])})." if top else ""
        saving = s["total"] * 0.2 * per_month
        tip("small-payments", "high", "Small payments are adding up",
            f"{s['count']} payments under {inr(s['threshold'])} ({s['share_of_payments_pct']}% of all your payments) "
            f"added up to {inr(s['total'])}.{where} Tiny amounts are the easiest to lose track of: "
            f"buy in one weekly trip instead of daily top-ups, or set a daily limit. Trimming a fifth saves about {inr(saving)} a month.", saving)

    # 3. subscriptions
    if subscriptions:
        monthly = sum(x["amount"] for x in subscriptions)
        names = ", ".join(x["merchant"] for x in subscriptions[:4])
        tip("subscriptions", "medium", f"Review your {len(subscriptions)} subscriptions",
            f"You pay {inr(monthly)} every month ({inr(monthly * 12)} a year) for {names}"
            f"{' and more' if len(subscriptions) > 4 else ''}. Cancel any you haven't used this month. "
            f"Cancelling just the least-used one frees up money every month.", monthly * 0.3)

    # 4. a category that jumped
    risers = [c for c in r["by_category"] if c["change_pct"] is not None and c["change_pct"] >= 30
              and c["share_pct"] >= 5 and c["category"] != UNCATEGORIZED and c["previous_total"] and c["total"] - c["previous_total"] >= 200]
    if risers:
        c = max(risers, key=lambda x: x["total"] - x["previous_total"])
        extra = (c["total"] - c["previous_total"]) * per_month
        tip("category-rising", "medium", f"{c['category']} is up {c['change_pct']:.0f}%",
            f"You spent {inr(c['total'])} on {c['category']} this period against {inr(c['previous_total'])} in the previous one. "
            f"Look at what changed. Getting back to the earlier level would save about {inr(extra)} a month.", extra)

    # 5. one shop takes a big share
    if r["top_merchants"]:
        m = r["top_merchants"][0]
        if m["count"] >= 8 and spent and m["total"] / spent >= 0.12:
            tip("one-shop", "medium", f"A lot goes to {m['merchant']}",
                f"{m['count']} payments to {m['merchant']} came to {inr(m['total'])} ({_pct(m['total'], spent)}% of your spending, "
                f"{inr(m['average'])} on average). Check whether a bigger, planned purchase would cost less than these repeat payments.")

    # 6. spending peaks on one weekday
    wd = r["by_weekday"]
    busy = [d for d in wd if d["count"]]
    if len(busy) >= 4:
        average = sum(d["total"] for d in busy) / len(busy)
        top = max(busy, key=lambda d: d["total"])
        if average and top["total"] >= 1.5 * average and top["total"] >= 0.2 * spent:
            day = WEEKDAY_NAMES[WEEKDAYS.index(top["weekday"])]  # "Thu" -> "Thursday", never "Thus"
            tip("weekday-peak", "low", f"You spend the most on {day}s",
                f"{day}s account for {inr(top['total'])} ({_pct(top['total'], spent)}% of your spending), "
                f"about {_pct(top['total'] - average, average):.0f}% more than a typical day of the week. Plan {day} spending ahead.")

    # 7. one huge payment
    if r["largest"]:
        big = r["largest"][0]
        if spent and big["amount"] / spent >= 0.15 and big["amount"] >= 1000:
            tip("big-payment", "low", "One payment stands out",
                f"{inr(big['amount'])} to {big['merchant']} on {big['date']} is {_pct(big['amount'], spent)}% of your total spending. "
                f"Make sure it was planned. Large one-offs can distort the picture of a normal month.")

    # 8. data quality
    u = r["uncategorized"]
    if u["share_pct"] >= 25:
        tip("categorise", "low", "Categorise your spending for sharper advice",
            f"{inr(u['total'])} ({u['share_pct']}% of your spending, {u['count']} payments) has no category yet, "
            f"so it can't be analysed. Use the Needs a category box on the dashboard to teach the app once.")

    # 9. good news
    change = r["totals"]["change_pct"]
    if change is not None and change <= -10:
        tip("spending-down", "good", f"Spending is down {abs(change):.0f}%",
            f"You spent {inr(spent)} against {inr(r['totals']['previous_spent'])} in the previous period. Keep going.")

    order = {"high": 0, "medium": 1, "low": 2, "good": 3}
    tips.sort(key=lambda t: (order[t["priority"]], -(t["monthly_saving"] or 0)))
    return tips[:7]


def _summary(r: dict) -> list[str]:
    t, p = r["totals"], r["period"]
    payments = f"{t['payments']:,} payment{'s' if t['payments'] != 1 else ''}"
    lines = [f"You spent {inr(t['spent'])} from {p['from']} to {p['to']}: about {inr(t['daily_average'])} a day across {payments}."]
    if t["change_pct"] is not None:
        if abs(t["change_pct"]) < 1:
            lines.append(f"That is about the same as the previous {p['days']} days ({inr(t['previous_spent'])}).")
        else:
            direction = "more" if t["change_pct"] > 0 else "less"
            lines.append(f"That is {abs(t['change_pct']):.0f}% {direction} than the previous {p['days']} days ({inr(t['previous_spent'])}).")
    cats = [c for c in r["by_category"] if c["category"] != UNCATEGORIZED]
    if cats:
        top = cats[0]
        line = f"Your biggest category is {top['category']}: {inr(top['total'])} ({top['share_pct']}%)."
        if len(cats) > 1:
            line += f" Next is {cats[1]['category']} with {inr(cats[1]['total'])} ({cats[1]['share_pct']}%)."
        lines.append(line)
    if r["top_merchants"]:
        m = r["top_merchants"][0]
        lines.append(f"The shop you paid most is {m['merchant']}: {inr(m['total'])} over {m['count']} payment{'s' if m['count'] != 1 else ''}.")
    s = r["small_spends"]
    if s["count"]:
        verb = "was" if s["count"] == 1 else "were"
        lines.append(f"{s['count']:,} of your payments {verb} under {inr(s['threshold'])}, together {inr(s['total'])}.")
    if t["peak_day"]:
        lines.append(f"Your highest-spending day was {t['peak_day']['date']} at {inr(t['peak_day']['total'])}.")
    u = r["uncategorized"]
    if u["count"]:
        lines.append(f"{inr(u['total'])} ({u['share_pct']}%) is still uncategorized.")
    return lines
