"""把本机 SQLite 的业务数据导出成可提交的 JSON。

用法：
    uv run python scripts/export_data.py
    uv run python scripts/export_data.py --out data/warpath-data.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data_io import DEFAULT_DATA_JSON, export_data, write_data_json  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导出业务数据到 JSON")
    parser.add_argument(
        "--out",
        default=os.environ.get("WARPATH_DATA_JSON", str(DEFAULT_DATA_JSON)),
        help="输出路径，默认 data/warpath-data.json",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        payload = export_data(db)

    path = write_data_json(payload, args.out)
    size = path.stat().st_size
    print(f"已导出到 {path}（{size / 1024:.1f} KB）")
    print(
        "资源 {resources}、商店 {shops}、商品 {offers}、箱子 {boxes}、VIP {vip}".format(
            resources=len(payload["resources"]),
            shops=len(payload["shops"]),
            offers=sum(len(shop["offers"]) for shop in payload["shops"]),
            boxes=len(payload["boxes"]),
            vip=payload["settings"]["current_vip_level"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
