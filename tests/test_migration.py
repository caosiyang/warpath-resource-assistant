from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.migrations import run_migrations


def test_migrates_category_to_resource_type(tmp_path):
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE resource_types ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(64) UNIQUE NOT NULL, "
                "sort_order INTEGER NOT NULL DEFAULT 0, "
                "note TEXT, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE resources ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(64) UNIQUE NOT NULL, "
                "unit VARCHAR(32) NOT NULL, "
                "category VARCHAR(32), "
                "note TEXT, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO resources (name, unit, category, created_at) "
                "VALUES ('弹药', '1', '兵卡资源', '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO resources (name, unit, category, created_at) "
                "VALUES ('未分类资源', '1', NULL, '2026-01-01')"
            )
        )

    run_migrations(engine, sessionmaker(bind=engine))

    with engine.connect() as connection:
        types = connection.execute(
            text("SELECT id, name FROM resource_types")
        ).fetchall()
        assert [row[1] for row in types] == ["兵卡资源"]
        type_id = types[0][0]

        rows = connection.execute(
            text("SELECT name, type_id FROM resources ORDER BY name")
        ).fetchall()
        by_name = {row[0]: row[1] for row in rows}
        assert by_name["弹药"] == type_id
        assert by_name["未分类资源"] is None

    # 幂等：重复执行不应重复创建类型
    run_migrations(engine, sessionmaker(bind=engine))
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM resource_types")
        ).scalar()
        assert count == 1
