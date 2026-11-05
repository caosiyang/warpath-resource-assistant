from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from . import models


def run_migrations(engine: Engine, session_factory: sessionmaker) -> None:
    """把旧版 resources.category 迁移到 resource_types + resources.type_id。

    旧库只有 category 文本列；新库直接有 type_id。函数是幂等的：
    缺 type_id 就补列，并把还没关联类型的资源按 category 补上。
    """
    inspector = inspect(engine)
    if "resources" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("resources")}
    if "category" not in columns:
        return

    if "type_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE resources ADD COLUMN type_id INTEGER "
                    "REFERENCES resource_types(id) ON DELETE RESTRICT"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_resources_type_id "
                    "ON resources (type_id)"
                )
            )

    with session_factory() as db:
        categories = (
            db.execute(
                text(
                    "SELECT DISTINCT category FROM resources "
                    "WHERE type_id IS NULL "
                    "AND category IS NOT NULL AND category <> ''"
                )
            )
            .scalars()
            .all()
        )
        for name in categories:
            resource_type = db.scalar(
                select(models.ResourceType).where(models.ResourceType.name == name)
            )
            if resource_type is None:
                resource_type = models.ResourceType(name=name)
                db.add(resource_type)
                db.flush()
            db.execute(
                text("UPDATE resources SET type_id = :type_id WHERE category = :name"),
                {"type_id": resource_type.id, "name": name},
            )
        db.commit()
