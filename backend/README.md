# Personal Finance Dashboard - Backend

这是 Personal Finance Dashboard 项目的后端部分，采用 **FastAPI** 构建，并与 **Supabase** 进行数据库交互。本项目使用 `uv` 进行高效的 Python 包管理与虚拟环境隔离。

## 开发阶段总结：Phase 1 基础设施建设

在 Phase 1 阶段，我们主要完成了数据库的初始化准备与后端基础架构的搭建工作，以下是事无巨细的变更与产出列表：

### 1. 技术栈与环境初始化

- **包管理工具:** 使用了现代化的 Python 依赖管理工具 [uv](https://github.com/astral-sh/uv)，极大地提升了依赖解析和虚拟环境创建的速度。
- **依赖库安装:** 借助 uv 执行 `uv add fastapi "uvicorn[standard]" supabase pydantic pydantic-settings python-dotenv apscheduler` 以配置所有必要后端依赖。
- **环境变量:** 提供并配置了 `.env.example`，用于存放 Supabase 实例的连接凭证。开发者需将其复制为 `.env` 并填入 `SUPABASE_URL` 及 `SUPABASE_KEY` 即可运行项目。

### 2. 数据库设计与建表脚本 (Supabase)

在 `scripts/init_db.sql` 中，我们为 Supabase 编写了标准且带索引优化的 PostgreSQL 初始化脚本，涵括以下 4 张核心表（包含基于 UUID 主键和 UTC 时间戳生成默认值设计的健壮建表语句）：
1. **`accounts` (账户表)**: 用于记录各资金账户，包括名称和结算币种。
2. **`assets` (资产表)**: 用于存储具体投资标的（股票、基金或加密货币）的基础信息。
3. **`transactions` (交易流水表)**: 系统的核心驱动。包含关联资产与账户的 Foreign Key，记录交易类型（买入/卖出/分红）、价格、数量和时间，并配置了 `ON DELETE CASCADE` 级联删除机制。
4. **`alert_rules` (报警规则表)**: 构建了自定义规则引擎的数据层。记录涨跌幅阈值、目标价格、动作方向（UP/DOWN）、时间窗口以及防重发的冷却时间。

所有频繁发生读取及联合查询的外键和时间字段都已配置了对应的 `INDEX`（例如 `idx_transactions_account_id`、`idx_alert_rules_is_active` 等）以提升查询性能。

### 3. 项目架构与目录设计 

建立了标准、具备极高可扩展性的 FastAPI 后端结构：
```text
backend/
├── .env.example            # 环境变量模板
├── README.md               # 本阶段开发详情文档
├── pyproject.toml / uv.lock # uv 依赖与配置锁定文件
├── scripts/
│   └── init_db.sql         # 数据库初始化建表脚本
└── src/
    ├── main.py             # FastAPI 服务入口 (CORS, 路由挂载, Healthcheck)
    ├── database.py         # Supabase 客户端全局单例实例化逻辑
    ├── schemas/            # Pydantic 响应与请求模型定义 (DTO层)
    │   ├── accounts.py     # account 模型增删改查的数据抽象
    │   ├── assets.py       # asset 模型的抽象
    │   ├── transactions.py # 交易流水数据与 Enum 类型的抽象
    │   └── alert_rules.py  # 报警规则的数据抽象
    └── routers/            # 路由层 (Endpoints Controller)
        ├── accounts.py     # 实现 /api/accounts 的 CRUD RESTful 逻辑
        ├── assets.py       # 实现 /api/assets 资产的 CRUD
        ├── transactions.py # 实现 /api/transactions 以及带过滤的查询接口
        └── alert_rules.py  # 实现 /api/alert_rules 的规则维护端点
```

### 4. 核心代码实现详情

1. **服务入口 `src/main.py`**
   - 实例化了 `FastAPI` 应用，并配置了 OpenAPI 文档元数据。
   - 加入了 `CORSMiddleware` 跨域中间件并放行了所有（`*`）原站域名、头部和方法，用于轻松同时兼容后续开发的 Streamlit (Web) 页面与 Scriptable (iOS) 小组件。
   - 实现了一个用于容器和存活探针调用的基础断言探测接口 `/health`。
   - 使用 `app.include_router()` 将子路由控制器 (`accounts`, `assets`, `transactions`, `alert_rules`) 挂载进入当前主应用树中。

2. **数据库连接单例 `src/database.py`**
   - 通过 `dotenv` 读取 `.env` 下属的环境配置。
   - 使用 `supabase-py` 内置核心方法 `create_client(url, key)` 初始化与线上服务的长连接通信客户端。
   - 暴露出了安全的全局单例句柄 `supabase` 供其他路由模块模块依赖引入。

3. **Pydantic 模型绑定与参数验证 `src/schemas/`**
   - 实现数据结构定义与数据流分离操作：在 `accounts.py` 内部创建了 `AccountBase` (共享字段基类), `AccountCreate` (写入传输层), `AccountUpdate` (动态更新), `AccountResponse` (外部响应包裹等)。
   - 并在响应基类利用 `model_config = ConfigDict(from_attributes=True)` 特性，使得通过 ORM 或 Supabase response 返回的 JSON / Dict 对象能无缝由 FastAPI 自动序列化返回给终端 HTTP 调用者。

4. **RESTful 路由控制器 `src/routers/`**
   - 定义了四个标准的带有独立标签和路径前缀的 `APIRouter` 路由组（`Accounts`, `Assets`, `Transactions`, `Alert Rules`）。
   - 深度集成业务逻辑，包含：
     - **POST**：接收合法的请求体，插入新记录，强校验枚举（`TradeType`, `RuleType`等）与数据精度（`Decimal`）。
     - **GET**：列表接口功能，并针对 `transactions` 提供基于 `account_id` 与 `asset_id` 的过滤；针对单条记录利用 UUID 检索。
     - **PUT / PATCH**：对 `alert_rules` 等部分接口提供局部的状态更新能力支持。
     - **DELETE**：结合外键的 `ON DELETE CASCADE` 实现具备安全防卫性质的业务销毁机制。

---

## 开发阶段总结：Phase 2 行情接入与持仓计算

在 Phase 2 阶段，我们成功将静态的交易账本与实时的市场行情相连接，为应用赋予了生命力：

1. **依赖扩展**：引入了开源的 `yfinance` 实现免密钥的实盘数据抓取，并通过 `cachetools` 实现了基于 5 分钟 TTL 的进程内缓存机制。
2. **行情抓取服务 (`src/services/market_data.py`)**：能够基于符号（如 `AAPL`, `00700.HK`）透明地拉取实盘价格，并具备异常容错兜底能力。
3. **持仓聚合引擎 (`src/services/positions.py`)**：通过 chronologically replay 方式遍历指定用户的交易流水，计算精准的当前持有股数（`total_quantity`）与加权单位成本（`average_cost`）。
4. **持仓接口 (`GET /api/positions`)**：对外提供聚合端点，联合上述两个服务实时计算并返回未实现盈亏（`unrealized_pnl`）及盈亏比（`unrealized_pnl_percent`）。

---

## 阶段部署与本地运行指南

执行如下四步指令，即可于本地全功能起步并测试 Phase 1 的各项建设成果：

1. **执行建表（已完成）：** 前往您建立好的 Supabase 项目后台（SQL Editor）并将 `backend/scripts/init_db.sql` 内全部代码覆写运行。
2. **连接鉴权（已完成）：** 在 `backend/` 目录下将 `.env.example` 命名并另存一份副本至 `.env` 文件内，写入从 Supabase 控制台获取到的 URL 与（Anon Key / Service Key）。
3. **启动应用（已完成）：**
   ```bash
   uv run uvicorn src.main:app --reload
   ```
4. **测试联调（已完成）：** 您的控制台会提示 Server Running，打开浏览器前往 http://127.0.0.1:8000/docs 使用互动式 Swagger UI 页面，您即刻能使用我们刚编写好的上述四种 Accounts 接口对云端真实数据集执行各类模拟的增删测试，完成真正的“API 交付初级里程碑”。
