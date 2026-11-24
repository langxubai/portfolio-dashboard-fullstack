import streamlit as st

from api_client import ChatAccessError, api


def context_for_next_reply(history):
    """Keep complete question/answer pairs within the backend's context limits."""
    messages = history[-13:]
    while len(messages) > 1 and sum(len(item["content"]) for item in messages) > 36_000:
        messages = messages[2:]
    return messages


st.set_page_config(page_title="问我的持仓", page_icon="💬")
st.title("问我的持仓")

backend_online = True
try:
    status = api.get_ai_status()
    st.session_state["portfolio_chat_status"] = status
except Exception:
    backend_online = False
    st.error("无法读取 AI 服务配置。请确认看板后端已启动，并已更新到支持持仓对话的版本。")
    st.button("重新连接")
    status = st.session_state.get("portfolio_chat_status")
    if not status:
        st.stop()

providers = {item["id"]: item for item in status["providers"]}
preferred = next((key for key, item in providers.items() if item["configured"]), None)
if not providers:
    st.info("还没有可用的对话服务，请先按 README 配置持仓对话。")
    st.stop()

provider = st.selectbox(
    "回答问题的服务",
    list(providers),
    index=list(providers).index(preferred) if preferred else 0,
    format_func=lambda key: providers[key]["label"],
    key="portfolio_chat_provider",
)
conversations = st.session_state.setdefault("portfolio_chat_conversations", {})
history = conversations.setdefault(provider, [])
errors = st.session_state.setdefault("portfolio_chat_errors", {})
ready = backend_online and status["access_configured"] and providers[provider]["configured"]

if provider == "codex":
    st.caption("提问将使用 Mac 上登录的 Codex。对话内容和持仓摘要会发送给 OpenAI，使用该登录方式对应的额度。")
else:
    st.caption("提问会将对话内容和持仓摘要发送到你配置的模型 API，使用该服务的额度。")
with st.expander("模型会看到哪些数据？"):
    st.write("每次提问都会读取看板当前的持仓快照，发送标的、持仓占比、币种和行情时效等信息。"
             "看板会排除账户名称、持仓绝对金额和逐笔流水。你在问题中主动填写的内容会随问题一起发送。")
    st.write("看板在当前浏览器会话中分别保存各服务的对话。每次最多附带同一服务最近六轮问答，"
             "文字较长时会减少轮数。需要用最新报价时，请先在首页点击「刷新最新价格」并等待完成。")

if not status["access_configured"]:
    st.info("请先在运行看板的电脑上按项目 README 设置聊天口令，再重启后端。")
if not providers[provider]["configured"]:
    if provider == "codex":
        st.info("要启用 Codex，请按 README 在 Mac 上登录 Codex、启动看板助手，并在后端配置连接地址和助手口令。")
    else:
        st.info("要启用模型 API，请按 README 在后端设置服务地址、API 密钥和模型名称，再重启后端。")

token = st.session_state.get("portfolio_chat_token")
if ready and not token:
    with st.form("portfolio_chat_unlock", clear_on_submit=True):
        entered = st.text_input("聊天口令", type="password",
                                help="在 Mac 项目目录运行 python3 scripts/setup_ai.py --show-chat-token 可查看。")
        if st.form_submit_button("使用此口令") and entered.strip():
            st.session_state["portfolio_chat_token"] = entered.strip()
            st.rerun()

if history or token:
    controls = st.columns(2)
    if controls[0].button("清空本次对话", disabled=not history, help="清除当前服务在此会话中的消息。"):
        history.clear()
        errors.pop(provider, None)
        st.rerun()
    if token and controls[1].button("锁定对话", help="移除本次会话的聊天口令，并清除所有服务的消息。"):
        st.session_state.pop("portfolio_chat_token", None)
        conversations.clear()
        errors.clear()
        st.rerun()

# A pending question stays on screen after errors or interrupted page runs.
# Only a new input event or an explicit retry may start another paid request.
pending = bool(history and history[-1]["role"] == "user")
for index, item in enumerate(history):
    with st.chat_message(item["role"]):
        if pending and index == len(history) - 1:
            pending_text = st.empty()
            pending_text.markdown(item["content"])
        else:
            st.markdown(item["content"])

can_send = bool(ready and token)
retry = False
if pending:
    if provider in errors:
        st.error(errors[provider])
    else:
        st.info("上一条提问还没有收到回答。")
    retry = st.button("重试这条提问", disabled=not can_send)

prompt = st.chat_input(
    "重新输入以替换上一条提问" if pending else "例如，我最大的三个仓位合计占多少？",
    disabled=not can_send,
    max_chars=4000,
    key=f"portfolio_chat_input_{provider}",
)
if can_send and ((prompt and prompt.strip()) or retry):
    if prompt and prompt.strip():
        question = {"role": "user", "content": prompt.strip()}
        if pending:
            history[-1] = question
            pending_text.markdown(question["content"])
        else:
            history.append(question)
            with st.chat_message("user"):
                st.markdown(question["content"])
    errors.pop(provider, None)
    try:
        with st.spinner("正在读取持仓并等待回答…"):
            answer = api.ask_about_positions(provider, context_for_next_reply(history), token)
        history.append({"role": "assistant", "content": answer})
    except ChatAccessError as exc:
        st.session_state.pop("portfolio_chat_token", None)
        errors[provider] = str(exc)
    except ValueError as exc:
        errors[provider] = str(exc)
    st.rerun()
