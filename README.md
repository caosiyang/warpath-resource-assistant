# 战火勋章 · 资源助手

资源最大化的数据底座。先把 VIP 黄金兑换比例、商店商品、箱子内容录进本地数据库，用黄金等价物（GEV）计算性价比，并在页面内通过带工具的模型对话给出开箱/兑换建议。

当前阶段：**数据录入 + 计价内核 + 页面内助手**。

## 技术栈

- Python 3.11+
- FastAPI + Jinja2 + Alpine.js（无前端构建）
- SQLAlchemy 2.x
- SQLite（单文件，WAL 模式）
- OpenAI 兼容模型接口（httpx，流式 + function calling）

## 快速开始

```bash
uv sync
cp .env.example .env
# 编辑 .env，填入模型接口地址和 API Key
uv run uvicorn app.main:app --reload --port 8765
```

打开 <http://127.0.0.1:8765>。（如果 8765 被占用，换成其他端口。）

`.env` 已被 gitignore，不会进仓库。不配置模型也能使用录入页面，只是 `/chat` 会提示模型未配置。

首次启动会自动建表并写入种子数据：

- 货币：黄金、战役币、联盟贡献币
- 资源类型：基础资源、稀有资源、兵卡资源
- 资源：食物、木材、钢铁、石油、合金（关联到基础资源/稀有资源）
- 商店类型：
  - 特权商店 → 黄金，默认 1 周，**特权阶梯定价**
  - 联盟商店 → 联盟贡献币，默认 3 天
  - 战役商店 → 战役币，默认 7 天
- 默认设置：当前特权等级 VIP18

数据库文件在 `data/warpath.db`。

## 页面

| 路径 | 功能 |
| --- | --- |
| `/` | 概览与快捷入口 |
| `/resource-types` | 资源类型 |
| `/resource-types/{id}/edit` | 编辑资源类型 |
| `/resources` | 资源字典，创建时必须选择类型 |
| `/resources/{id}/edit` | 编辑资源 |
| `/currencies` | 货币（黄金 / 代币） |
| `/shop-types` | 商店类型（名称 + 绑定货币 + 定价模式） |
| `/shops` | 商店列表 |
| `/shops/new` | 从商店类型创建商店（含首批商品） |
| `/shops/{id}` | 商店详情，增删商品；特权商店支持 VIP 切换 |
| `/shops/{id}/edit` | 编辑商店的刷新周期和备注 |
| `/shops/{id}/offers/{offer_id}/edit` | 编辑商品 |
| `/boxes` | 箱子列表 |
| `/boxes/new` | 新建箱子（含首批资源） |
| `/boxes/{id}` | 箱子详情，增删资源 |
| `/boxes/{id}/items/{item_id}/edit` | 编辑箱内资源 |
| `/chat` | 页面内模型对话（流式 + 本地工具计算） |
| `/settings` | 当前特权等级（1–25） |

## 数据口径

**商品价格**录入的是“折后价/组”和折扣力度，原价自动反算：

```
一组数量     = 30
折后价/组    = 135
折扣力度     = 85    # 表示减 85%
原价/组      = 135 / (1 - 85%) = 900
单价/个      = 135 / 30 = 4.5
```

- 折扣力度填减免百分比：填 `20` 表示减 20%；留空表示无折扣。
- 原价只在页面和 API 中计算，不手工录入。
- 限购单位是“组”，例如限购 20 组。
- 单价按“个”计算，不再按千单位。

**资源类型**：先在 `/resource-types` 维护类型，创建/编辑资源时选择类型。类型下有资源时不能删除；类型改名后资源会自动跟随。

**商店类型绑定货币**：先在 `/shop-types` 维护“商店名称 → 货币”的对应关系，创建商店时选择类型，货币自动带出。一种类型只能创建一个商店；已创建商店后，类型绑定的货币不能修改。

**特权阶梯定价**：

- 商店类型的 `pricing_mode = vip_tiered` 时，每个商品必须有 `min_vip_level`（1–25）；
- 商品在 VIP ≥ `min_vip_level` 时解锁；
- 同一资源有多条可用记录时，取 `discount_pct` 最高的那条；折扣相同取单价最低；
- 商店详情页可以用 `?vip=20` 临时切换查看，不修改全局设置；
- 已创建商店后，商店类型的定价模式不能修改。

**箱子**：所有箱子都是自选资源，只需要录入箱子名称、可选资源和每个资源的数量；不再区分大小、类型、获取途径，也不需要概率。

## 页面内助手

`/chat` 是一个带工具的模型对话页。模型只负责理解问题和组织语言，所有价格与价值由本地 `app/pricing.py` 计算。

计算口径：

- **GEV（黄金等价物）**：当前 VIP 下，该资源在黄金商店的最便宜单价（黄金/个）；
- 资源价值 = 数量 × GEV；
- 自选箱只能选一个资源栈，按 `value_gev` 比较；
- 黄金商店内部的 `efficiency` 接近 1，不能用来跨资源比较，应看折扣、限购和卡点；
- 代币商店只有和黄金商店存在同资源重叠时，才反推汇率并换算成黄金成本；
- 没有价格或汇率时直接说明数据不足，不估算。

模型可调用的只读工具：

```
get_settings          当前 VIP
get_resource_values   资源 GEV 表 + 未定价资源
list_boxes            箱子及可选资源
evaluate_box          箱子各选项价值与推荐
list_shops            商店、货币、有效商品数
evaluate_shop         商品折扣、限购、价值与性价比
get_data_status       数据完整度与缺口
```

对话接口用 SSE 流式返回：

```
event: session   会话 ID
event: tool      正在执行的工具
event: token     模型输出片段
event: html      最终 Markdown 渲染结果
event: done      完成
event: error     错误
```

会话历史存 SQLite 的 `chat_sessions` / `chat_messages`，刷新页面后可继续。

模型配置读环境变量或项目根目录 `.env`：

```
WARPATH_LLM_BASE_URL=http://10.110.147.148:8317/v1
WARPATH_LLM_API_KEY=...
WARPATH_LLM_MODEL=deepseek-v4.1-flash
WARPATH_LLM_TIMEOUT=60
```

## API

所有页面操作都有对应的 JSON 接口；对话页的计算工具与页面共用同一套逻辑。

```
GET/POST      /api/resource-types
GET/PATCH/DELETE /api/resource-types/{id}

GET/POST      /api/resources
GET/PATCH/DELETE /api/resources/{id}

GET/POST      /api/currencies
GET/PATCH/DELETE /api/currencies/{id}

GET/POST      /api/shop-types
GET/PATCH/DELETE /api/shop-types/{id}

GET/POST      /api/shops
GET/PATCH/DELETE /api/shops/{id}
GET           /api/shops/{id}/effective?vip_level=18
POST          /api/shops/{id}/offers
PATCH/DELETE  /api/shops/{id}/offers/{offer_id}

GET/POST      /api/boxes
GET/PATCH/DELETE /api/boxes/{id}
POST          /api/boxes/{id}/items
PATCH/DELETE  /api/boxes/{id}/items/{item_id}

GET           /api/chat/sessions
POST          /api/chat/sessions
GET/DELETE    /api/chat/sessions/{id}
POST          /api/chat                 # SSE 对话

GET/PUT       /api/settings
GET           /api/health
```

示例：

```bash
curl -s http://127.0.0.1:8765/api/shops | python -m json.tool
```

创建资源的请求体（`type_id` 必填）：

```json
{
  "name": "弹药",
  "unit": "1",
  "type_id": 1
}
```

创建商店的请求体：

```json
{
  "shop_type_id": 1,
  "refresh_period": "1周",
  "offers": [
    {
      "resource_id": 1,
      "resource_qty": 30,
      "discounted_currency_qty": 135,
      "discount_pct": 85,
      "min_vip_level": 18,
      "limit_qty": 20
    }
  ]
}
```

这条商品表示：135 金币卖 30 个零件，限购 20 组；折扣 85% 时原价自动反算为 900，单价 4.5 金币/个。

特权商店必须填写 `min_vip_level`；普通商店不要传这个字段。

临时查询某个 VIP 下的最优商品：

```bash
curl -s "http://127.0.0.1:8765/api/shops/1/effective?vip_level=18"
```

修改全局特权等级：

```bash
curl -X PUT http://127.0.0.1:8765/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"current_vip_level": 20}'
```

## 测试

```bash
uv run pytest -q
```

## 下一步

- 继续录入联盟商店、战役商店商品和更多资源价格
- 增加预算规划与缺口清单（`--need` / 目标数量）
- 对话页支持多轮工具编排和更细的卡点权重

## 目录

```
app/
  main.py          FastAPI 入口
  db.py            SQLite 连接与 WAL
  models.py        ORM 模型（含对话会话）
  schemas.py       Pydantic 校验
  services.py      业务逻辑（页面与 API 共用）
  pricing.py       GEV、箱子、商店性价比计算
  llm.py           OpenAI 兼容流式客户端
  chat.py          工具定义、agent loop、SSE、会话持久化
  seed.py          种子数据
  routers/         页面与 API 路由
  templates/       Jinja2 模板
  static/          CSS / Alpine.js
.env               本地模型配置（gitignore）
data/warpath.db    本地数据库
tests/             pytest
```
