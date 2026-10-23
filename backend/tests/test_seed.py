"""The demo-data seeder, and its safe 'only if empty' mode used on every production start."""
from sqlalchemy import func, select


def test_if_empty_mode_never_touches_existing_data(client, monkeypatch, tmp_path):
    from app.database import SessionLocal
    from app.models import Transaction
    from scripts import seed

    monkeypatch.chdir(tmp_path)  # the seeder also writes a CSV into ./data

    def count() -> int:
        with SessionLocal() as db:
            return db.scalar(select(func.count(Transaction.id)))

    seed.main()
    first = count()
    assert first > 4000

    # delete some rows, then run the production-style seed: it must leave things alone
    with SessionLocal() as db:
        db.query(Transaction).filter(Transaction.id <= 100).delete()
        db.commit()
    seed.main(if_empty=True)
    assert count() == first - 100  # not re-created, not duplicated, not wiped

    # but a plain run (the developer command) does reset the demo account
    seed.main()
    assert count() == first
