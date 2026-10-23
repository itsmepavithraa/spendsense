"""Export the Power BI views to CSV files.

Why: Power BI can read Postgres directly, but that needs a database driver. CSVs
need nothing, so they are the zero-setup way to build the dashboard (and a handy
backup for demos).

Run:  docker compose exec api python -m scripts.export_bi_csv
Output: backend/data/bi/*.csv  (on your machine; the folder is git-ignored)
"""
from pathlib import Path

import pandas as pd

from app.database import engine

VIEWS = ["bi_transactions", "bi_monthly_category", "bi_subscriptions", "bi_revenue", "bi_users"]
OUT = Path("data/bi")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for view in VIEWS:
        df = pd.read_sql_query(f"SELECT * FROM {view}", engine)  # noqa: S608 (fixed names above)
        df.to_csv(OUT / f"{view}.csv", index=False)
        print(f"{view}: {len(df):>6} rows -> {OUT / (view + '.csv')}")


if __name__ == "__main__":
    main()
