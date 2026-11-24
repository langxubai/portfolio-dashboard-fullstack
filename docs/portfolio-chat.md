# 在 Finance Board 里和 AI 讨论持仓

## 从一次提问开始

1. 已配置并启动看板后，可以在 Finder 双击 `macos/打开持仓对话.command`。它会将聊天口令复制到剪贴板，打开本机的聊天页面；在密码框中按 ⌘V 即可。也可以自行打开看板，从左侧选择「问我的持仓」。这个口令只用来解锁本看板的 AI 接口。
2. 选择回答方。选「Codex」使用 Mac 上的 Codex 登录；选「API」使用后端配置的服务地址、模型和 API key。
3. 输入「我最大的三个仓位合计占多少？请说明计算范围。」发送。页面会等待回答，然后将回答展示在同一个窗口。
4. 可以接着问「其中哪些仓位的行情可能过期？」。每次提问都会读取当前仓位和行情快照，如果刚刚录入交易或刷新了行情，两次回答的统计基准可能不同。
5. 可以在页面清空本次对话。切换提供方时对话分别保存，避免把给一家服务的聊天自动转发给另一家。

## 我应该选哪种模式

| 项目 | 用 Mac 上的 Codex | 用模型厂商的 API |
|---|---|---|
| 准备工作 | Mac 安装 Codex CLI，并已使用 ChatGPT 账户登录 | 准备兼容 Chat Completions 协议的服务地址、模型标识和 API key |
| 哪个进程发请求 | Docker 后端连接 Mac 助手，由助手启动 CLI | Docker 后端直接联系配置的服务 |
| 额度 | 使用已登录账户可用的 Codex 额度，适用套餐限制 | 依所选提供方的 API 账户或服务计费 |
| 数据去向 | Mac 上运行客户端，提交给 Codex 的文字仍会传到 OpenAI | 问题、近期对话和持仓摘要传到配置的服务地址 |
| 适合的情况 | 自己在这台 Mac 上使用，已有 Codex 登录 | 想指定模型、换厂商，或将看板部署到另一台机器 |

本次接入的 API 协议是 `POST /chat/completions`。填写服务商文档给出的基础地址（许多服务以 `/v1` 结尾）和该账户可用的真实模型标识。使用其他协议的厂商需要相应适配。两种模式分别启用；请求失败后由使用者决定是否换提供方。

## 初次设置

以下命令均从仓库根目录执行。前置条件是已有可用的 Finance Board 安装，且 `backend/.env` 中的数据库凭据能让首页显示持仓。初次部署整个看板请先完成[根 README 的启动说明](../README.md#7-如何启动与测试应用-how-to-run-and-test)。这个功能沿用原有持仓和行情表，聊天本身无需新增数据库表。

### 使用 Mac 上的 Codex

1. 在当前 macOS 用户下运行 `codex login status`。如果尚未登录，运行 `codex login` 并选用自己的 ChatGPT 账户。如果终端找不到命令，请安装 Codex CLI，或向设置脚本提供 `FINANCE_BOARD_CODEX_BIN`（Codex 可执行文件的绝对路径）。安装程序也会查找本机 ChatGPT 应用自带的常见 CLI 路径。
2. 运行以下命令配置看板口令、Mac 助手及当前用户的登录项。

   ```bash
   python3 scripts/setup_ai.py --install-agent
   docker compose up -d --build
   ```

3. 复制看板口令，然后在页面专用密码框粘贴。下列命令直接写入 Mac 剪贴板。

   ```bash
   python3 scripts/setup_ai.py --show-chat-token | pbcopy
   ```

4. 打开[本机看板](http://localhost:8501)。登录项属于当前 macOS 用户，需要执行设置的用户拥有可用的 Codex 登录。

希望临时前台运行助手时，可以使用以下命令。它与登录项监听同一端口，二者择一启动。

```bash
python3 scripts/setup_ai.py
python3 macos/codex_bridge.py --env-file "$HOME/Library/Application Support/Finance Board/bridge.env"
```

### 只使用 API

1. 运行 `python3 scripts/setup_ai.py --api-only` 生成看板口令。
2. 编辑 **`backend/.env`**，设置 `AI_API_BASE_URL`、`AI_API_MODEL`、`AI_API_KEY`。请使用自己信任的服务地址；该地址将收到该服务的密钥及发送给模型的内容。公开网络使用 HTTPS。
3. 运行 `docker compose up -d --build`，使后端重新读取配置。按照上面的复制命令取得看板口令，在页面选择 API。该模式也可与 Codex 同时配置。

### 设置脚本在机器上做了什么

| 位置 | 用途 |
|---|---|
| `backend/.env` | 保存看板口令、Docker 访问助手的地址和独立的助手密钥。API key 也只配置在后端。脚本保留已有非空设置与其他业务配置。 |
| `~/Library/Application Support/Finance Board/bridge.env` | 服务间密钥的 Mac 端副本，仅当前用户可读写。 |
| `~/Library/Application Support/Finance Board/codex_bridge.py` | 登录项使用的独立助手副本，仓库更新后重新运行安装命令同步。 |
| `~/Library/LaunchAgents/dev.finance-board.codex-bridge.plist` | 在用户登录时启动助手，记录 Python、CLI 和脚本路径。 |

普通的设置命令可重复执行，会复用原先生成的密钥。只有 `--install-agent` 会注册登录项。卸载登录项使用 `python3 scripts/setup_ai.py --uninstall-agent`；它会停止助手并保留配置，已配置的 API 模式仍可使用。Mac 助手监听 `127.0.0.1:8765`，OrbStack 内的后端通过 `http://host.docker.internal:8765` 联系它。若后端直接在 Mac 里用 `uv` 运行，可将 `AI_BRIDGE_URL` 改为 `http://127.0.0.1:8765`，并重启后端。

## 一条消息经过哪些组件

1. **看板前端**显示聊天记录、读取本轮问题和看板口令，将对话发送到后端。口令通过 HTTP 授权头传输，与聊天正文分开。
2. **FastAPI 后端**验证口令，按现有流水核算持仓，从已保存的行情与汇率快照形成摘要。聊天读取数据库；行情更新仍由原有采集任务或主页的「刷新最新价格」触发。
3. **提供方**接收问题、近期对话和摘要。使用 Codex 时，后端另用助手密钥向 Mac 发送请求；使用 API 时，由后端加上该厂商的 API key。
4. **前端**在原来的对话下方显示回答。想把最新行情纳入分析时，先在主页发起刷新，待采集完成再回到聊天页提问。

## 持仓摘要如何计算

后台沿用首页的持仓核算，选取各账户仍有正持有数量的资产，按已保存汇率统一折算为人民币。相同公开证券依代码、资产类型和计价币种跨账户合并。自定义资产使用「匿名资产 1」一类标签。摘要中不含账户标识、券商名称、资产自定义名称、绝对金额、交易时间、持有数量和逐笔流水。你在问题中主动写入的内容会随问题发送。

| 字段或问题 | 计算口径 |
|---|---|
| 「前三大仓位占多少」 | 先合并同一证券，按可估值持仓的人民币市值排序，再用前三项市值之和除以可估值总额；模型收到的是已算好的百分比。 |
| 「美元资产占多少」 | 按资产的计价币种汇总。基金穿透后的地区分布、公司收入来源和经济敞口需要其他数据。 |
| 报价或汇率缺失 | 相应持仓在摘要里有缺失提示，占比为空，且不进入分母。所有持仓均无法估值时，前三大占比也为空。 |
| 报价存在但较旧 | 保留最后一次可用估值，同时带上行情日期、来源和时效提示；日期超过五个自然日会额外提示陈旧。该阈值用于提示，未经各交易所交易日历校正。 |
| 现金与历史 | 分母为当前可估值持仓。银行/券商未入账的现金、已平仓项目、历史组合和逐笔记录均在范围之外。 |

举例而言，某个虚构组合有两笔可估值持仓以及一只缺价基金。前两笔的权重可以合计到 100%，这表示**已估值部分的 100%**。基金实际占全部财富的比例仍然未知。如果想核对金额、看某一交易日的仓位或回放一笔买卖，需要回到相应的账本或历史功能。

## 对话与错误处理

- 每个服务在当前 Streamlit 会话中有一段独立历史。发送时最多保留最近六组完整问答和当前问题，合计上限 36,000 字符。单个问题上限 4,000 字符，单条回复上限 12,000 字符。清空会话或刷新浏览器可能丢失页面记录。
- 「清空本次对话」清除当前提供方的本地消息；「锁定对话」同时移除当前会话的口令及两个提供方的消息。服务商自身的请求保留策略取决于该服务和账户设置。
- 每个后端进程同时处理一个生成请求。等待中断时页面保留问题，由你手动重试或改写。对已经到达模型的请求，重新发送可能再次使用额度。首版在生成完成后展示整段文字。
- `GET /api/ai/status` 返回两个通道的配置状态。真正提问走 `POST /api/ai/chat`，需要看板口令；公开的状态接口既不读取持仓也不查询账户余额或模型额度。接口示例见[后端 README](../backend/README.md)。

## 常见故障与复核

| 现象 | 检查与处理 |
|---|---|
| 首页正常，侧栏没有聊天页 | 在仓库根目录执行 `docker compose up -d --build`，再重新打开看板。 |
| 页面提示服务未配置 | 访问 `http://127.0.0.1:8000/api/ai/status`。确认相应服务的 `configured` 为 true。修改 `backend/.env` 后用 `docker compose up -d` 重新载入环境。 |
| 提示聊天口令错误 | 重新运行复制命令，将看板口令粘贴到页面。页面口令是 `AI_CHAT_ACCESS_TOKEN`，助手配对密钥是独立的 `FINANCE_BOARD_BRIDGE_TOKEN`。 |
| Mac 助手没有启动 | 在 Mac 运行 `curl --noproxy '*' http://127.0.0.1:8765/health`。查看 `launchctl print gui/$(id -u)/dev.finance-board.codex-bridge`。更换 Python 或 Codex 的位置后，重新执行安装命令。 |
| Mac 健康检查成功，容器仍连接失败 | 用下面的容器健康命令分别检查网关和助手。Compose 把 `host.docker.internal` 指向 Docker 自己的 `host-gateway`，避免 VPN 或代理 DNS 改写该名称；修改 Compose 后须重建容器。 |
| Codex 繁忙、超时或模型服务拒绝 | 等待当前问题结束，检查 Mac 上的 ChatGPT 登录、套餐可用量和网络。更新 CLI 后可用下面的虚构持仓命令独立复查。外部 API 模式另查自己的 API key、模型授权、剩余额度和基础 URL。 |
| 模型说部分仓位缺价 | 先看首页相应资产的行情时间、采集时间、备用来源和状态；可以发起「刷新最新价格」。若报价源仍无数据，该持仓继续列为未估值。 |

从 Docker 验证到 Mac 的连通性。这条命令只读取助手状态。

```bash
docker compose exec -T backend .venv/bin/python -c \
  'import httpx; c=httpx.Client(trust_env=False); print(c.get("http://host.docker.internal:8765/health",timeout=5).json())'
```

需要真实模型复核时，下列命令会通过所选通道发出**一次**提问，可能消耗该账户额度。测试输入写死为两只虚构资产，占比分别是 60% 和 40%；测试脚本不会读取真实持仓、启动行情任务或打印密钥。选其一执行。

```bash
docker compose exec -T backend .venv/bin/python -m scripts.check_ai codex
docker compose exec -T backend .venv/bin/python -m scripts.check_ai api
```

## 本次开发和验证记录 · 2026-11-20

| 步骤 | 实施与验证 |
|---|---|
| 确认现有环境 | 保留原有的 Streamlit、FastAPI、数据库和 Docker 网络。Mac 上 Codex CLI 版本为 0.169.1，确认当前用户已使用 ChatGPT 登录。 |
| 后端 | 新增只读摘要、两个模型适配和独立的聊天口令。用合成数据验证跨账户合并、多币种权重、零估值、缺价/缺汇、隐私字段、请求校验和上游异常。 |
| 前端 | 增加「问我的持仓」页面。用 Streamlit 测试连续追问、分别保留两个服务的历史、口令失效、断线重试、清空与锁定。另在本机浏览器确认了入口、模型选择和密码框。 |
| Mac 助手 | 每次生成在临时目录启动受限 CLI，提问经标准输入传入。验证助手鉴权、格式和大小限制、并发、超时处理。用本机模拟模型检查了 CLI 实际发出的请求；验证中还发现 CLI 会加载用户的全局指令文件，最终版在启动子进程时限制读取这些文件。复查时，标记文本和可调用工具都没有出现在请求中。CLI 仍会附加自身的运行指令。 |
| 安装与启动 | 在临时目录验证重复运行不会更换现有口令，API 模式可再增配 Codex。随后安装了本机用户登录项并重新构建、启动两个实际容器。 |
| 现场网络问题 | 首次通过普通 DNS 连接助手时，Mac 的健康检查成功，容器内却得到代理网段地址并断开。给后端增加 `host-gateway` 映射后，测试容器可以访问仅监听回环地址的助手。 |
| 真实 Codex 复核 | 使用更新后的实际 Docker 后端，通过 Mac 登录助手向云端 Codex 发送一组虚构的 60%／40% 仓位。真实回答通过 60% 的数值校验。整个自测没有读取或提交个人仓位。独立 API key 模式通过模拟接口验证，本机未配置该服务的密钥。 |
| 本机数据路径 | 另一次检查从实际部署的数据库读取了当前持仓，并经鉴权的聊天路由生成摘要。这次在本地用固定回答替代了模型，验证数据路径时没有输出仓位或向模型发送个人数据。 |
| 回归与修复 | 共运行 39 项测试（后端 24、前端 8、Mac 助手 5、安装配置 2）。联调还发现首页测试在特定运行顺序下会连接到本机后台；调整模拟服务后，两种测试顺序均通过。 |

日常回归可离线运行，下面的测试使用虚构数据和模拟服务。

```bash
(cd backend && .venv/bin/python -m unittest test_ai_chat test_market_refresh test_market_snapshot_architecture)
(cd frontend && .venv/bin/python -m unittest test_chat_page test_app_smoke)
python3 -m unittest discover -s macos -p 'test_codex_bridge.py'
python3 -m unittest discover -s scripts -p 'test_setup_ai.py'
```

## 资料

- [Codex 的非交互调用](https://developers.openai.com/codex/noninteractive)
- [Codex 登录与计费](https://developers.openai.com/codex/auth)
- [OrbStack 从容器访问 Mac 上的服务](https://docs.orbstack.dev/docker/network#connecting-to-servers-on-mac)
