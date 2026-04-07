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
  - **动态金额推算**: 新增了总金额 (Total Amount) 列。允许用户在 Unit Price, Quantity, 和 Total Amount 之间任填两项（剩余一项填 0），系统能够在执行入库前自动推导并结算剩余项目，极大地方便了按总金额交易的情况。
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

## 开发阶段总结：Phase 5 - 进阶功能与体验优化

在此阶段，重点提升了用户体验、操作安全性以及复杂资产场景的兼容性：

### 1. 核心数据可视化增强 (`app.py`)
- **昨日收益与已实现盈亏**: 看板顶部指标全方位升级，对接后端新增的解析逻辑，展示精确的 **昨日收益 (Yesterday PnL)** 并在资产明细表中暴露 **已实现收益 (Realized PnL)** 与 **未实现收益 (Unrealized PnL)**。
- **动态收益率曲线**: 新增了基于时间维度的交互式折线图，可以通过 `api_client.py` 封装好的一层 `get_portfolio_history()` 调用，使用户能以 `1M`, `3M`, `YTD`, `1Y`, `ALL` 等多维尺度自由筛查整体组合净值及累计收益率走向。

### 2. 表单推导与操作时区修复 (`pages/2_📝_Transactions.py`)
- **时区偏移修复**: 引入 Python 原生 `zoneinfo` 模块，在添加交易表单内植入 **Timezone (时区)** 下拉框，确保 `trade_time` 被赋予正确的时区偏移 (如 `Asia/Shanghai`) 后以 ISO 8601 标准传至后台，彻底解决原来交易只记录日期、系统强切至零时区覆盖时间的偏差问题。
- **总金额智能推导计算**: 表单支持了 **Total Amount (总金额)** 输入，允许用户在单价、数量、总金额三个维度中“三选二”输入。在用户点击提交 (Submit) 时自动推导出第三值，极大地方便了按固定总金额投资或抛售退出时的计算痛点。

### 3. 数据安全与二次交互确认
- 我们为所有具有彻底破坏性的删除操作 (`api_client.py` 内含 `delete_account`, `delete_asset`, `delete_transaction`) 全部套上了 `st.dialog` 二次确认机制。
- 这些弹窗非完全静态，它带入了后端聚合上下文警告信息，例如：预备删除账号时会弹窗提醒“该账户下仍然存续的资产数量”；预备删除资产时将明示“该资产的持仓数量和警报规则数量”；充分阻断了盲目误删造成的级联流失恶性事故。

### 4. 非标（自定义）资产专属看板 (`pages/1_💰_Accounts_&_Assets.py`)
- 对于不在公开交易市场流转的数据类型（如银行定期存单、私募等），我们向用户开放了 `Custom` 强交互入口。
- 新增了专属于 `Custom` 类型资产的历史净值修改/价格提交面板，通过 `create_custom_asset_price()` 配合时区控件向服务端追加时序表现。另外我们对于后端传回的手动定价事件妥善处置，并在 UI 侧规避了这种手工调整而无端触发非必要性警告推送警报逻辑的发生。
