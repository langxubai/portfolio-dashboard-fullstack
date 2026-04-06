# Personal Finance Dashboard - Frontend

这是 Personal Finance Dashboard 项目的前端展示部分，采用 **Streamlit** 构建。作为统一的 Web 管理控制台，它通过 RESTful API 与后端的 FastAPI 服务进行通信，提供资产可视化、数据录入与规则配置等核心功能。

## 开发阶段总结：Phase 4 - Streamlit Web 管理页面

在 Phase 4 阶段，我们成功搭建了与后端逻辑解耦的 Streamlit 交互平台，完成了核心仪表盘和数据维护页面开发：

### 1. 技术栈与架构设计
- **独立环境与包管理:** 在 `frontend/` 目录通过 `uv` 进行了初始化，确保依赖隔离。核心依赖包含 `streamlit`（Web 框架）、`pandas`（数据处理）、`plotly`（交互式图表）以及 `httpx`（API 请求客户端）。
- **API 桥接层 (`api_client.py`)**: 封装了 `FinanceAPIClient`，支持利用 `os.environ` 或是 `dotenv` 从 `.env` 读取 `BACKEND_URL`。集中处理了各种 CRUD 接口访问逻辑与异常态势抛出，使得 UI 代码极其干净、易拓展。后续若部署至 Streamlit Cloud 也能通过配置 Secrets 实现零代改对接生产后端。

### 2. 核心模块与页面实现

本项目采用典型的 Streamlit 多页面架构（Multi-page App）：

- **`app.py` (主仪表盘 Dashboard)**
  - 作为应用的默认主页，聚合展示 `Total Asset Value` 与 `Total Unrealized PnL` 等关键大字报 (Metrics)。
  - 利用 `plotly.express` 绘制 `Asset Allocation` (饼图) 与 `Unrealized PnL by Asset` (柱状图)。
  - 通过表格概览现有持仓的均价、现价、份额及盈亏比。

- **`pages/1_💰_Accounts_&_Assets.py` (账户与资产管理)**
  - 展示现有的投资账户列表（支持多币种如 USD/CNY）和关联的标底资产基底（如 Stock, Fund, Crypto 等）。
  - 内置基于 `st.form` 构建的表单，用于直观地为数据库增添新的 Account 和 Asset 记录。
  - 支持对于 `Custom`（自定义类型）资产的手工历史价格更新，通过引入 `zoneinfo` 进行准确的交易时区选择，确保时间偏移传递至后端被无损落库。

- **`pages/2_📝_Transactions.py` (录入交易数据)**
  - **Trade Form**: 关联账户和资产的下拉框（自动抓取数据库已有内容）。记录单价 (Price)、数量 (Quantity)、交易方向 (BUY/SELL/DIVIDEND) 、发生时间以及 **操作时区 (Timezone)** 的选择，彻底解决了由于前端原先粗糙的零时区转换导致的数据库落表混乱情况。
  - 此页同时作为**流水展示板**，按照时间倒序把用户的任何挂单入库行为拉取反馈出日志级详情记录。

- **`pages/3_🔔_Alert_Rules.py` (报警规则配置与管理)**
  - 完整承接后端的 Alert Engine 配置，可视化设置监控规则类型（`TARGET_PRICE`, `CHANGE_PERCENT`, `CHANGE_ABS`）。
  - 允许精确配置多项参数：阈值、触发方向 (UP/DOWN)、时间窗口 (如 60 mins)、冷静期 (Cooldown)。
  - 支持即时查看哪些规则被配置或触发，及一键根据 ID 删除无用规则的交互功能。

## 本地启动说明

在确保您已经在根目录下克隆好了后端环境并顺利跑通后端服务的情况之下（详见根目录 `README.md`），您只需在当前目录执行：

```bash
uv run streamlit run app.py
```

终端将回显本地服务器的 URL，您可以立即在任何浏览器访问并检阅看板效果。
