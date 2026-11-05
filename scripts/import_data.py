"""从 JSON 重建本机 SQLite 的业务数据。

用法：
    uv run python scripts/import_data.py                 # 仅空库
    uv run python scripts/import_data.py --replace       # 清空业务表后导入
    uv run python scripts/import_data.py --in data/warpath-data.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data_io import (  # noqa: E402
    DEFAULT_DATA_JSON,
    DataError,
    import_data,
    load_data_json,
)
from app.db import Base, SessionLocal, engine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="从 JSON 导入业务数据")
    parser.add_argument(
        "--in",
        dest="source",
        default=os.environ.get("WARPATH_DATA_JSON", str(DEFAULT_DATA_JSON)),
        help="输入路径，默认 data/warpath-data.json",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="清空业务数据后导入（对话历史不受影响）",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    payload = load_data_json(args.source)

    with SessionLocal() as db:
        try:
            counts = import_data(db, payload, replace=args.replace)
        except DataError as exc:
            print(f"导入失败：{exc}")
            return 1

    print(f"已从 {args.source} 导入：")
    for key, value in counts.items():
        print(f"  {key:16} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
