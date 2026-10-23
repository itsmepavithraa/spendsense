"""add BI views for Power BI and subscription detection

Revision ID: b7e1c9a04d12
Revises: ca21125486dc
Create Date: 2026-10-23 12:00:00

Why views? Power BI (and the subscriptions API) should read clean, analysis-ready
tables, not raw app tables. Views also let us change the app schema later without
breaking dashboards. Amounts are cast to float8 so Power BI treats them as numbers.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7e1c9a04d12"
down_revision: Union[str, None] = "ca21125486dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One row per transaction, with the date parts a dashboard slices by.
    op.execute(
        """
        CREATE VIEW bi_transactions AS
        SELECT
            t.id                                         AS transaction_id,
            t.user_id,
            u.email                                      AS user_email,
            t.merchant,
            t.category,
            t.amount::float8                             AS amount,
            t.is_anomaly,
            t.occurred_at,
            t.occurred_at::date                          AS date,
            date_trunc('month', t.occurred_at)::date     AS month_start,
            EXTRACT(YEAR  FROM t.occurred_at)::int       AS year,
            EXTRACT(MONTH FROM t.occurred_at)::int       AS month,
            to_char(t.occurred_at, 'Mon')                AS month_name,
            EXTRACT(ISODOW FROM t.occurred_at)::int      AS weekday_number,
            to_char(t.occurred_at, 'Dy')                 AS weekday,
            EXTRACT(HOUR FROM t.occurred_at)::int        AS hour
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        """
    )

    # Pre-aggregated: spend per user, month and category.
    op.execute(
        """
        CREATE VIEW bi_monthly_category AS
        SELECT
            user_id,
            date_trunc('month', occurred_at)::date AS month_start,
            category,
            SUM(amount)::float8                    AS total_spend,
            COUNT(*)                               AS txn_count
        FROM transactions
        GROUP BY 1, 2, 3
        """
    )

    # Subscription detection: the same merchant charging the same amount about
    # every month. LAG() looks at the previous charge. Rules:
    #   - ignore gaps under 20 days (duplicate / same-day charges are noise)
    #   - at least 2 qualifying gaps (3+ charges)
    #   - the average gap is 25-35 days (monthly)
    #   - the gaps are CONSISTENT (standard deviation <= 5 days). Random repeat
    #     purchases of the same amount have wildly varying gaps; real subscriptions don't.
    op.execute(
        """
        CREATE VIEW bi_subscriptions AS
        WITH gaps AS (
            SELECT
                user_id, merchant, amount, occurred_at,
                EXTRACT(EPOCH FROM (
                    occurred_at - LAG(occurred_at) OVER (
                        PARTITION BY user_id, merchant, amount ORDER BY occurred_at
                    )
                )) / 86400.0 AS gap_days
            FROM transactions
        )
        SELECT
            user_id,
            merchant,
            amount::float8                                                    AS amount,
            COUNT(*) + 1                                                      AS charges,
            ROUND(AVG(gap_days)::numeric, 1)::float8                          AS avg_gap_days,
            MAX(occurred_at)                                                  AS last_charge,
            (amount * 12)::float8                                             AS yearly_cost
        FROM gaps
        WHERE gap_days >= 20
        GROUP BY user_id, merchant, amount
        HAVING COUNT(*) >= 2
           AND AVG(gap_days) BETWEEN 25 AND 35
           AND STDDEV_SAMP(gap_days) <= 5
        """
    )

    # Business side: money the app itself earned.
    op.execute(
        """
        CREATE VIEW bi_revenue AS
        SELECT
            p.id                          AS payment_id,
            p.user_id,
            u.email                       AS user_email,
            p.status,
            p.currency,
            (p.amount_paise / 100.0)::float8 AS amount,
            p.created_at,
            p.paid_at,
            p.paid_at::date               AS paid_date
        FROM payments p
        JOIN users u ON u.id = p.user_id
        """
    )

    # Users, for conversion analysis (how many are Pro?).
    op.execute(
        """
        CREATE VIEW bi_users AS
        SELECT id AS user_id, email, full_name, is_pro, created_at, created_at::date AS signup_date
        FROM users
        """
    )


def downgrade() -> None:
    for view in ("bi_users", "bi_revenue", "bi_subscriptions", "bi_monthly_category", "bi_transactions"):
        op.execute(f"DROP VIEW IF EXISTS {view}")
