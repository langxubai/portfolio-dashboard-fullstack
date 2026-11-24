"""Configure Finance Board's private chat and optional macOS login helper."""

import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import plistlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV = ROOT / "backend" / ".env"
SUPPORT = Path.home() / "Library/Application Support/Finance Board"
LABEL = "dev.finance-board.codex-bridge"
PLIST = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
CHAT_TOKEN = "AI_CHAT_ACCESS_TOKEN"
BRIDGE_TOKEN = "FINANCE_BOARD_BRIDGE_TOKEN"
HOST_URL = "http://host.docker.internal:8765"


def atomic_write(path, contents):
    # NamedTemporaryFile creates the replacement with owner-only permissions.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        try:
            temp.write(contents)
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(temp.name, path)
        finally:
            Path(temp.name).unlink(missing_ok=True)


@contextmanager
def config_lock(directory):
    handle = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        os.close(handle)


def assignment(text, key):
    matches = list(re.finditer(r"^(?:[ \t]*export[ \t]+)?[ \t]*" + key
                               + r"[ \t]*=[ \t]*([^\r\n]*)$", text, re.M))
    if len(matches) > 1:
        raise ValueError(f"配置文件中有多条 {key}，请保留一条后重试。")
    return matches[0] if matches else None


def value(text, key):
    match = assignment(text, key)
    if match is None:
        return ""
    parts = shlex.split(match.group(1), comments=True)
    if len(parts) > 1:
        raise ValueError(f"请检查 {key} 的配置格式。")
    return parts[0] if parts else ""


def fill(text, key, new_value):
    if value(text, key):
        return text
    match = assignment(text, key)
    line = f"{key}={new_value}"
    if match:
        return text[:match.start()] + line + text[match.end():]
    return text + ("" if text.endswith("\n") else "\n") + line + "\n"


def configure(env_path, support, api_only):
    with config_lock(env_path.parent):
        original = env_path.read_text()
        chat = value(original, CHAT_TOKEN) or secrets.token_urlsafe(32)
        updated = fill(original, CHAT_TOKEN, chat)
        if not api_only:
            support.mkdir(parents=True, mode=0o700, exist_ok=True)
            host_env = support / "bridge.env"
            host_secret = value(host_env.read_text(), BRIDGE_TOKEN) if host_env.exists() else ""
            backend_secret = value(original, BRIDGE_TOKEN)
            if host_secret and backend_secret and host_secret != backend_secret:
                raise ValueError("Mac 助手与 backend/.env 的助手密钥不同，请先核对两处配置。")
            bridge = backend_secret or host_secret or secrets.token_urlsafe(32)
            if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{32,256}", bridge) or bridge == chat:
                raise ValueError("助手密钥须为独立的随机字符串（至少 32 位），请检查两处配置。")
            updated = fill(updated, BRIDGE_TOKEN, bridge)
            updated = fill(updated, "AI_BRIDGE_URL", HOST_URL)
            if not host_secret:
                atomic_write(host_env, (BRIDGE_TOKEN + "=" + bridge + "\n").encode())
            host_env.chmod(0o600)
        if original != updated:
            atomic_write(env_path, updated.encode())
        env_path.chmod(0o600)


def find_codex():
    configured = os.environ.get("FINANCE_BOARD_CODEX_BIN")
    path = configured or shutil.which("codex") or (
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
    if not os.path.isabs(path) or not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise ValueError("找不到 Codex CLI。请安装并登录，或用 FINANCE_BOARD_CODEX_BIN 指定绝对路径。")
    return path


def manage_agent(install):
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    loaded = subprocess.run(["launchctl", "print", service], capture_output=True).returncode == 0
    if install:
        executable = find_codex()
        helper = SUPPORT / "codex_bridge.py"
        atomic_write(helper, (ROOT / "macos/codex_bridge.py").read_bytes())
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        agent = {
            "Label": LABEL,
            "ProgramArguments": [sys.executable, "-I", "-B", str(helper), "--env-file", str(SUPPORT / "bridge.env")],
            "EnvironmentVariables": {"FINANCE_BOARD_CODEX_BIN": executable},
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 20,
        }
        contents = plistlib.dumps(agent)
        if loaded and PLIST.is_file() and PLIST.read_bytes() == contents:
            subprocess.run(["launchctl", "kickstart", "-k", service], check=True)
            print("已更新并重启当前用户的 Mac 助手。")
            return
        atomic_write(PLIST, contents)
    if loaded:
        subprocess.run(["launchctl", "bootout", service], check=True)
    if install:
        # A previous bootout can still be releasing the label for a short time.
        for attempt in range(5):
            result = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], capture_output=True)
            if result.returncode == 0:
                break
            if result.returncode != 5 or attempt == 4:
                result.check_returncode()
            time.sleep(0.5)
        print("Mac 助手已交给当前用户的登录服务管理。")
    else:
        PLIST.unlink(missing_ok=True)
        print("已停用登录助手，现有配置和密钥已保留。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--api-only", action="store_true", help="只准备看板口令")
    group.add_argument("--show-chat-token", action="store_true", help="输出看板口令，可用管道复制")
    group.add_argument("--install-agent", action="store_true", help="配置并注册 macOS 登录助手")
    group.add_argument("--uninstall-agent", action="store_true", help="停用并移除登录项")
    args = parser.parse_args()
    if not (args.show_chat_token or args.api_only) and sys.platform != "darwin":
        parser.exit(1, "本机 Codex 助手需要 macOS。仅使用 API 可加 --api-only。\n")
    try:
        if args.uninstall_agent:
            manage_agent(False)
            return
        if not BACKEND_ENV.exists():
            raise ValueError("请先按根 README 设置 backend/.env 及数据库连接。")
        if args.show_chat_token:
            token = value(BACKEND_ENV.read_text(), CHAT_TOKEN)
            if not token:
                raise ValueError("尚未配置看板口令，请先运行设置命令。")
            print(token)
            return
        configure(BACKEND_ENV, SUPPORT, args.api_only)
        if args.install_agent:
            manage_agent(True)
        print("配置已就绪。使用 docker compose up -d --build 载入配置和页面。")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
