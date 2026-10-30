# 战火勋章 · 资源助手

资源最大化的数据底座。先把 VIP 黄金兑换比例、商店商品、箱子内容录进本地数据库，后续用黄金等价物（GEV）计算性价比，并由 OpenCode agent 给出开箱/兑换建议。

当前阶段：**M0 + M1 数据录入端**。

## 技术栈

- Python 3.11+
- FastAPI + Jinja2 + Alpine.js（无前端构建）
- SQLAlchemy 2.x
- SQLite（单文件，WAL 模式）

## 快速开始

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8765
```

打开 <http://127.0.0.1:8765>。（如果 8765 被占用，换成其他端口。）

首次启动会自动建表并写入种子数据：

- 货币：黄金、战役币、联盟贡献币
- 资源：食物、木材、钢铁、石油、合金
- 商店类型：
  - 特权商店 → 黄金，默认 1 周
  - 联盟商店 → 联盟贡献币，默认 3 天
  - 战役商店 → 战役币，默认 7 天

数据库文件在 `data/warpath.db`。

## 页面

| 路径 | 功能 |
| --- | --- |
| `/` | 概览与快捷入口 |
| `/resources` | 资源字典 |
| `/currencies` | 货币（黄金 / 代币） |
| `/shop-types` | 商店类型（名称 + 绑定货币） |
| `/shops` | 商店列表 |
| `/shops/new` | 从商店类型创建商店（含首批商品） |
| `/shops/{id}` | 商店详情，增删商品 |
| `/shops/{id}/edit` | 编辑商店的刷新周期和备注 |
| `/shops/{id}/offers/{offer_id}/edit` | 编辑商品 |
| `/boxes` | 箱子列表 |
| `/boxes/new` | 新建箱子（含首批资源） |
| `/boxes/{id}` | 箱子详情，增删资源 |
| `/boxes/{id}/items/{item_id}/edit` | 编辑箱内资源 |

## 数据口径

**折扣**填减免百分比：

```
填 20  =>  实付 = 原价 × (1 - 20%) = 原价 × 0.8
留空   =>  无折扣
```

商品单价：

```
实付货币 = list_currency_qty × (1 - discount_pct / 100)
单价     = 实付货币 / (resource_qty / 1000)
```

**商店类型绑定货币**：先在 `/shop-types` 维护“商店名称 → 货币”的对应关系，创建商店时选择类型，货币自动带出。一种类型只能创建一个商店；已创建商店后，类型绑定的货币不能修改。

**箱子类型**：

- `choose_one` 自选一个
- `fixed` 固定内容
- `random` 随机，需要填概率（0–1）

## API

所有页面操作都有对应的 JSON 接口，后续 agent 直接调用。

```
GET/POST      /api/resources
GET/PATCH/DELETE /api/resources/{id}

GET/POST      /api/currencies
GET/PATCH/DELETE /api/currencies/{id}

GET/POST      /api/shop-types
GET/PATCH/DELETE /api/shop-types/{id}

GET/POST      /api/shops
GET/PATCH/DELETE /api/shops/{id}
POST          /api/shops/{id}/offers
PATCH/DELETE  /api/shops/{id}/offers/{offer_id}

GET/POST      /api/boxes
GET/PATCH/DELETE /api/boxes/{id}
POST          /api/boxes/{id}/items
PATCH/DELETE  /api/boxes/{id}/items/{item_id}

GET           /api/health
```

示例：

```bash
curl -s http://127.0.0.1:8765/api/shops | python -m json.tool
```

创建商店的请求体：

```json
{
  "shop_type_id": 1,
  "refresh_period": "1周",
  "offers": [
    {
      "resource_id": 1,
      "resource_qty": 100000,
      "list_currency_qty": 500,
      "discount_pct": 20
    }
  ]
}
```

## 测试

```bash
uv run pytest -q
```

## 下一步

- M2：录入真实数据并核对口径
- M3：计价引擎（GEV、性价比排名、缺口规划）
- M4：OpenCode agent + skill 接入

## 目录

```
app/
  main.py          FastAPI 入口
  db.py            SQLite 连接与 WAL
  models.py        ORM 模型
  schemas.py       Pydantic 校验
  services.py      业务逻辑（页面与 API 共用）
  seed.py          种子数据
  routers/         页面与 API 路由
  templates/       Jinja2 模板
  static/          CSS / Alpine.js
data/warpath.db    本地数据库
tests/             pytest
```
