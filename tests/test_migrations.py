"""The Alembic migrations must build the same schema the models describe."""
from flask_migrate import upgrade
from sqlalchemy import inspect

from app import create_app
from app.extensions import db


def test_migrations_upgrade_to_head(tmp_path):
    app = create_app("testing", overrides={
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'mig.db'}",
    })
    with app.app_context():
        upgrade()
        tables = set(inspect(db.engine).get_table_names())
        db.engine.dispose()
    assert {"users", "scans", "scan_results", "alembic_version"} <= tables
