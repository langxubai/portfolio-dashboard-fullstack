# 个人全栈金融资产看板 (Personal Finance Dashboard)

详细技术路径参考 ./frontend/README.md 和 ./backend/README.md 文件。

## 1. 项目概述 (Project Overview)
本项目旨在开发一个自动化、多端的个人金融资产跟踪与管理系统。系统通过中心化的后端 API 管理多账户的资产流水，实时计算持仓及盈亏，并内置**自定义规则引擎**，支持多维度的价格异动与目标价实时推送报警。

**技术栈选型:**
* **Database:** Supabase (PostgreSQL)
* **Backend:** Python + FastAPI + APScheduler (定时任务与规则引擎)
* **Frontend (Web):** Streamlit
* **Frontend (Mobile Widget):** iOS Scriptable (JavaScript)
* **3rd Party Services:** 实时行情 API (Yahoo Finance / AkShare)、推送服务 (Bark / Telegram Bot)

---

## 2. 数据库设计 (Database Schema)
系统采用“事件驱动”设计，所有持仓由流水动态计算，并独立配置报警规则表。

### `accounts` (资金账户表)
* `id` (UUID, Primary Key)
* `name` (String): 账户名称 (如：华泰证券、招商银行)
* `currency` (String): 结算货币 (如：CNY, USD)

### `assets` (资产基础信息表)
* `id` (UUID, Primary Key)
* `symbol` (String): 资产代码 (如：AAPL, 00700.HK)
* `name` (String): 资产名称 (如：苹果, 腾讯控股)
* `asset_type` (String): 资产类型 (Stock, Fund, FundCN, Crypto 等)

### `transactions` (交易流水表 - 核心计算源)
* `id` (UUID, Primary Key)
* `account_id` (UUID, Foreign Key)
* `asset_id` (UUID, Foreign Key)
* `trade_type` (String): 交易类型 (BUY, SELL, DIVIDEND)
* `price` (Decimal): 成交单价
* `quantity` (Decimal): 交易数量
* `trade_time` (Timestamp): 交易发生时间

### `alert_rules` (自定义报警规则表 - 规则引擎)
* `id` (UUID, Primary Key)
* `asset_id` (UUID, Foreign Key)
* `rule_type` (String): 规则类型 (TARGET_PRICE 目标价, CHANGE_PERCENT 比例波动, CHANGE_ABS 绝对值波动)
* `direction` (String): 触发方向 (UP 向上, DOWN 向下)
* `target_value` (Decimal): 触发阈值 (如 150 刀，或 0.05 代表 5%)
* `time_window_minutes` (Integer): 时间窗口 (如 60 分钟内，目标价报警可为空)
* `is_active` (Boolean): 规则是否启用
* `cooldown_minutes` (Integer): 冷却时间 (如 1440 分钟，防止频繁打扰)
* `last_triggered_at` (Timestamp): 上次触发时间

---

## 3. 后端 API 与规则引擎 (Backend & Rule Engine)

### 核心 RESTful API
* **`POST /api/transactions`**: 录入新的交易流水。
* **`GET /api/positions`**: 聚合计算当前持仓状态（利用历史流水计算总持仓与均价，结合外部行情 API 计算实时盈亏）。
* **`POST /api/alerts`**: 增删改查用户的自定义报警规则。

### 后台定时任务与规则引擎 (Background Tasks)
使用 `APScheduler` 在交易时段内高频执行（例如每 1~5 分钟）：
1. **拉取规则**: 获取所有 `is_active = True` 且不在冷却期内的规则。
2. **获取数据**: 拉取关联资产的最新现价，以及波动规则所需的历史时间点价格。
3. **逻辑校验**: 遍历规则，判断最新价是否击穿 `TARGET_PRICE`，或指定时间内的涨跌幅是否超过设定的 `CHANGE_PERCENT` / `CHANGE_ABS` 阈值。
4. **触发推送**: 若条件满足，调用 Bark 或 Telegram API 发送格式化通知，并更新数据库中的 `last_triggered_at`，单次规则触发后自动设为 inactive。

---

## 4. 前端与交互端设计 (Clients)

### A. Web 管理控制台 (Streamlit)
* **Dashboard 页面:** 数据可视化，展示资产分布饼图、各资产盈亏柱状图、总资产折线图。
* **录入页面:** 提供表单，用于手动添加、修改交易流水。
* **报警设置页面 (Alerts):** 可视化界面配置监控规则，设定具体资产、报警类型、时间跨度及阈值。

### B. iOS 桌面看板 (Scriptable)
* 桌面小组件定时调用 `/api/positions`。
* 渲染总资产、今日盈亏绝对值与百分比，实现免打开 App 随时看盘。

### C. 聊天快捷交互 (Chatbot)
* 预留 Webhook 接收自然语言指令。
* 支持快速记账（如："买入 AAPL 10 150"）和快速设警（如："提醒：AAPL 跌破 150"）。

---

## 5. 项目结构 (Project Directory Structure)

```text
finance-board/
├── backend/                  # FastAPI 核心服务端
│   ├── src/                  # 包含各路由、状态模型、服务 (Rule Engine)
│   ├── scripts/              # Supabase 相关的 SQL 数据库初始脚本
│   └── README.md             # 后端子项目的实施细节
├── frontend/                 # Streamlit Web 前端页面
│   ├── app.py                # Dashboard 仪表盘主页
│   ├── pages/                # 各功能子页 (账户、交易录入、规则配置)
│   └── README.md             # 前端子项目的实施细节
├── ios_widget/               # iOS 桌面端免挂靠看板
│   ├── FinanceBoardWidget.js # Scriptable 原生小组件源码
│   └── README.md             # 如何在 iPhone / Tailscale 上配置
└── README.md                 # 当前总说明文档
```

---

## 6. 开发阶段规划 (Development Milestones)

* **Phase 1: 基础设施建设** (✅ 已完成)
  * 配置 Supabase，执行 SQL 脚本建立 4 张核心数据表。
  * 搭建 FastAPI 基础框架，完成基本的 CRUD 接口。
* **Phase 2: 行情接入与持仓计算** (✅ 已完成)
  * 接入第三方金融数据源 API。
  * 完成 `/api/positions` 的历史流水聚合与实时盈亏计算逻辑。
* **Phase 3: 规则引擎与报警推送** (✅ 已完成)
  * 开发并测试基于 `APScheduler` 的报警评估引擎。
  * 对接 Bark 或其他推送服务，完成消息下发。
* **Phase 4: 多端前端实现** (✅ 已完成)
  * 开发 Streamlit Web 管理页面（包含账单录入与报警规则配置）。
  * 编写 iOS Scriptable 脚本，完成桌面看板 UI。
  * （目前不需要）开发 Telegram Bot 快捷指令接入。
* **Phase 5: 高级功能与产品细节优化** (✅ 已完成)
  * **前端强化**：引入可视化收益率历史走势图；通过携带数据的弹窗确认拦截高危删改操作；为非标 Custom 资产开辟独立数据面板。
  * **后端核算升级**：支持自定义理财资产的时序价格录入并纳入合并资盘；加入已实现盈亏 (Realized PnL) 分片剥离算法。
  * **环境部署优化**：通过 Cloudflare Tunnel 与 tmux 保活脚本完成向公网虚机的云端部署。
* **Phase 6: 多样化资产接入 (FundCN 等)** (✅ 已完成)
  * 引入 `akshare` 增加 `FundCN` 支持自动拉取其对应 6 位数代码历史曲线和单位净额走势，同样支持多空 PnL 核算。
* **Phase 7: 核心算法与体验稳定性打磨** (✅ 已完成)
  * **前端深造**：完全重构图表逻辑呈现清晰的基于资产名称的大盘视角；引入具备长连接重连防断流机制的底层请求器防止组件因假死而抛出 500 报错；增加金额推导四舍五入、精细纯数字时间输入框与列表置顶字典排序等易用性交互；引入细微浮点抹平显示。详细修复查阅 [frontend/README.md](./frontend/README.md)。
  * **后端稳固**：支持大盘全局 Base Currency，合并估值时按比例融合外汇汇率（Forex）与各类资产；重写净值合并器（避开 Timezone 不兼容报错），抛弃粗暴市值法转为标准 TWR（时间加权回报率）杜绝减仓复位带来的斜率畸变失真；强化核心模块为 8 位小数精密承接。详细查阅 [backend/README.md](./backend/README.md)。

---

## 7. 如何启动与测试应用 (How to Run and Test)

本项目采用前后端分离式架构，由于利用 `uv` 进行了依赖隔离，您需要分别启动后端 API 服务与前端 Web 面板。

### 第一步(本地)：启动 FastAPI 后端环境

后端负责接收数据读写请求、拉取行情以及运行定时规则报警引擎：

1. 进入后端目录：`cd backend`
2. 确保您已经根目录下设置了 `.env` 并配置好 Supabase。
3. 启动并持续运行后端：
   ```bash
   uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. 后端将默认运行在 `http://127.0.0.1:8000`（并允许局域网或 Tailscale 进行访问）。您可以立刻访问 `http://127.0.0.1:8000/docs` 查看并测试自动生成的 Swagger API 文档。

### 第一步(云端)：启动 FastAPI 后端环境

1. ssh 连接到云服务器：
   ```bash
   ssh -i ~/.ssh/your_key.key ubuntu@[IP_ADDRESS]
   ```
2. 进入后端目录：`cd backend`
3. 拷贝根目录下的 `.env.example` 到 `.env` 文件：
   ```bash
   cp ../.env.example .env
   ```
   并编辑环境文件配置好密钥：
   ```bash
   nano .env
   ```
4. 启动进程保护：
   ```bash
   tmux new -s finance-board-backend
   ```
4. 启动并持续运行后端：
   ```bash
   uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. 后端将默认运行在 `http://[IP_ADDRESS]`（并允许局域网或 Tailscale 进行访问）。您可以立刻访问 `http://[IP_ADDRESS]/docs` 查看并测试自动生成的 Swagger API 文档。

6. 临时退出 tmux 会话，但不结束进程：
   ```bash
   Ctrl + b, d
   ```
7. 重新进入 tmux 会话：
   ```bash
   tmux attach -t finance-board-backend
   ```
8. 彻底退出 tmux 会话：
   ```bash
   exit
   ```

9. 退出 ssh 连接：
   ```bash
   exit
   ```
   或者
   ```bash
   Ctrl + d
   ```

### 第二步（本地）：启动 Streamlit 前端看板

1. 进入前端目录：`cd frontend`
2. 确保您已经在根目录下设置了 `.env` 并配置好 Supabase 的关联信息。
3. 启动应用：
   ```bash
   uv run streamlit run app.py
   ```
4. 浏览器将自动打开并运行在 `http://localhost:8501`。

---

## 8. 待办事项 (To-Do List)

### 目前可以进行的计划

✅ 1. 现在速度太慢了，不知道是哪一步慢了，特别是首页查看收益率，需要等待10-20秒。
    *(已解决：在后端加入了对 Yahoo Finance 和 AkShare 历史行情的 1小时内存缓存，避免了每次刷新都重新下载整个历史价格序列的心智和性能开销。即除了周期的第一次请求会稍慢，后续均为毫秒级渲染。)*
✅ 2. 首页的历史收益率图表，增加时间范围3年和10年；原先的“全部”应该从用户的第一笔交易开始算起，而不是从有数据开始算起。
    *(已解决：在 `frontend/app.py` 中添加了 3 年和 10 年的图表时间字典映射，同时在 `backend/src/services/portfolio_history.py` 中通过 `pd.to_datetime` 取首笔交易时间对齐过滤，彻底截断了早于第一笔流水的长尾空载价格序列，使得数据起点正确。)*
3. 增加修改资产名称、代码、类型和货币的功能。
4. 增加修改账户名称和货币的功能。
5. 历史回顾功能：回顾过去某个指定时刻的持仓情况和对应的收益情况。（基于此可以引入ai分析持仓倾向、资产配置等。也可以不基于此？但是首先需要数据清洗！！！不保留券商名称，只保留券商uuid；不保留绝对金额，仓位占比；不保留交易时间，只保留交易日期）
6. 设计前端和后端的登录功能。目前为了实现iOS的Scriptable小组件功能，后端api暴露在外，但是这样不安全，所以需要后端增加登录功能。如果想要实现前端部署在云上（推荐域名stocks.*），前端同样也需要登录功能，要不然谁拿到网址都能看到我的资产信息。
7. 合并frontend和backend的git仓库。
8. 分别封装到docker容器（写入dockerfile和docker yml），也可以封装到openclaw。（目前我的开发环境是mac arm orbstack）。

### 后续有时间再说的计划
1. 检查卖出份额不超过持仓份额？也许可以用负份额表示负债？
2. 提示用户账户和货币种类不挂钩（或者可以直接删除货币种类？但是也许有点用？）。
3. 在创建可以用API获取价格的资产的时候（也就是除了custom资产），应该首先矫正这个代码能不能在API上查到。（也许可以先不矫正，如果api有问题之类的就不会报错了）
4. 后续可以考虑名称搜索（已经可以实现）或者模糊搜索进行删除。
5. 优化账户/资产/交易/报警规则编辑功能的可读性，存在大量的后端数据，导致可读性差。但是前提是实现模糊搜索功能，uuid至少可以保证唯一性，还是先用uuid进行删除。
6. 前端增加修改交易记录的数量/价格/交易时间的功能。但是用处不大，因为可以删了重新填写。
