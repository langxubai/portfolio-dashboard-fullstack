import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from codex_bridge import BridgeError, ChatServer, TOKEN_NAME, generate_reply, read_token, validate_payload


QUESTION = {"portfolio": {"valuation_currency": "CNY"}, "messages": [{"role": "user", "content": "合计多少？"}]}
TOKEN = "test-only-pairing-" * 3


class BridgeTests(unittest.TestCase):
    def test_token_file_only_reads_pairing_setting(self):
        with tempfile.TemporaryDirectory() as location, patch.dict(os.environ, {}, clear=True):
            config = Path(location) / "bridge.env"
            config.write_text(f"IGNORED=x\n{TOKEN_NAME}={TOKEN}\n", encoding="utf-8")
            self.assertEqual(read_token(config), TOKEN)
            os.environ[TOKEN_NAME] = "x" * 32
            self.assertEqual(read_token(config), "x" * 32)
            os.environ[TOKEN_NAME] = "too short"
            with self.assertRaises(ValueError):
                read_token(config)

    def test_rejects_non_user_roles_or_other_parameters(self):
        for request in (
            dict(QUESTION, command="whoami"),
            dict(QUESTION, messages=[{"role": "system", "content": "x"}]),
            dict(QUESTION, messages=[{"role": "user", "content": "x" * 4001}]),
        ):
            with self.subTest(), self.assertRaises(BridgeError):
                validate_payload(request)

    @unittest.skipUnless(Path("/usr/bin/sandbox-exec").is_file(), "uses native macOS process sandbox")
    def test_cli_prompt_uses_stdin_temp_workdir_and_no_app_secrets(self):
        with tempfile.TemporaryDirectory() as location:
            cli = Path(location) / "codex"
            cli.write_text(
                "#!/usr/bin/env python3\n"
                "import json,os,sys\n"
                "from pathlib import Path\n"
                "args=sys.argv[1:]\n"
                "assert '--ephemeral' in args and '--ignore-user-config' in args\n"
                "assert 'shell_tool' in args and 'plugins' in args and 'memories' in args\n"
                "assert 'approval_policy=\\\"never\\\"' in args and 'web_search=\\\"disabled\\\"' in args\n"
                "assert 'FINANCE_BOARD_BRIDGE_TOKEN' not in os.environ and 'OPENAI_API_KEY' not in os.environ\n"
                "answer=json.load(sys.stdin)['messages'][0]['content']\n"
                "assert all(answer not in arg for arg in args)\n"
                "assert not list(Path.cwd().iterdir())\n"
                "try: (Path(os.environ['CODEX_HOME'])/'AGENTS.md').read_text()\n"
                "except PermissionError: pass\n"
                "else: raise AssertionError('personal instructions were readable')\n"
                "Path(args[args.index('--output-last-message')+1]).write_text(answer,encoding='utf-8')\n",
                encoding="utf-8",
            )
            cli.chmod(0o700)
            (Path(location) / "AGENTS.md").write_text("private example")
            with patch.dict(os.environ, {TOKEN_NAME: TOKEN, "OPENAI_API_KEY": "test-only", "CODEX_HOME": location}):
                self.assertEqual(generate_reply(str(cli), QUESTION), "合计多少？")

    @unittest.skipUnless(Path("/usr/bin/sandbox-exec").is_file(), "uses native macOS process sandbox")
    def test_timeout_and_cli_failure_are_sanitized(self):
        with tempfile.TemporaryDirectory() as location:
            cli = Path(location) / "codex"
            cli.write_text("#!/bin/sh\nexec /bin/sleep 30\n")
            cli.chmod(0o700)
            with patch("codex_bridge.CLI_TIMEOUT", 0.1), self.assertRaises(BridgeError) as caught:
                generate_reply(str(cli), QUESTION)
            self.assertEqual(caught.exception.status, 504)
            cli.write_text("#!/bin/sh\necho private-diagnostic >&2\nexit 9\n")
            with self.assertRaises(BridgeError) as caught:
                generate_reply(str(cli), QUESTION)
            self.assertEqual(caught.exception.status, 502)
            self.assertNotIn("private-diagnostic", str(caught.exception))

    def test_local_http_rejects_bad_auth_and_only_replies_to_valid_chats(self):
        calls = []

        def reply(data):
            calls.append(data)
            return "模拟回复"

        with ChatServer(0, TOKEN, reply) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def request(method, path, headers=None, body=None):
                    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
                    try:
                        conn.request(method, path, body=body, headers=headers or {})
                        response = conn.getresponse()
                        return response.status, json.loads(response.read())
                    finally:
                        conn.close()
                self.assertEqual(request("GET", "/health"), (200, {"status": "ok"}))
                self.assertEqual(request("POST", "/chat")[0], 401)
                auth = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
                self.assertEqual(request("POST", "/chat", dict(auth, Origin="http://localhost"))[0], 401)
                self.assertEqual(request("POST", "/chat", auth, "{}")[0], 400)
                with server.slot:
                    self.assertEqual(request("POST", "/chat", auth, json.dumps(QUESTION))[0], 429)
                self.assertEqual(request("POST", "/chat", auth, json.dumps(QUESTION)), (200, {"reply": "模拟回复"}))
                self.assertEqual(calls, [QUESTION])
            finally:
                server.shutdown()
                worker.join(2)


if __name__ == "__main__":
    unittest.main()
