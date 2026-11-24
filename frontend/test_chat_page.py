import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from streamlit.testing.v1 import AppTest


CHAT_PAGE = str(next(Path(__file__).parent.glob("pages/4_*")))


class PortfolioChatTest(unittest.TestCase):
    def setUp(self):
        self.status = {
            "access_configured": True,
            "providers": [
                {"id": "codex", "label": "Mac 上的 Codex", "configured": True},
                {"id": "api", "label": "模型 API", "configured": True},
            ],
        }
        self.api = Mock()
        self.api.get_ai_status.return_value = self.status
        self.api.ask_about_positions.return_value = "前三个持仓合计占 72%。"
        replacement = patch("api_client.api", self.api)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.app = AppTest.from_file(CHAT_PAGE)

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()

    def unlock(self):
        self.app.text_input[0].set_value("test-owner-token")
        self.click("使用此口令")

    def test_followup_and_provider_switch(self):
        self.app.run()
        self.assertTrue(self.app.chat_input[0].disabled)
        self.unlock()
        self.app.chat_input[0].set_value("前三级仓位？").run()
        self.app.chat_input[0].set_value("其中美元占多少？").run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(self.api.ask_about_positions.call_args.args, (
            "codex", [
                {"role": "user", "content": "前三级仓位？"},
                {"role": "assistant", "content": "前三个持仓合计占 72%。"},
                {"role": "user", "content": "其中美元占多少？"},
            ], "test-owner-token",
        ))
        self.app.selectbox[0].select("api").run()
        self.assertEqual(len(self.app.chat_message), 0)
        self.app.selectbox[0].select("codex").run()
        self.assertEqual(len(self.app.chat_message), 4)
        self.click("清空本次对话")
        self.assertEqual(len(self.app.chat_message), 0)
        self.click("锁定对话")
        self.assertTrue(self.app.chat_input[0].disabled)

    def test_failed_question_retries_only_on_click(self):
        self.api.ask_about_positions.side_effect = [ValueError("模型暂时不可用"), "回答"]
        self.app.run()
        self.unlock()
        self.app.chat_input[0].set_value("哪些标的缺少行情？").run()
        self.assertEqual(self.app.error[0].value, "模型暂时不可用")
        self.app.run()
        self.assertEqual(self.api.ask_about_positions.call_count, 1)
        self.click("重试这条提问")
        self.assertEqual(len(self.app.chat_message), 2)
        self.assertEqual(self.api.ask_about_positions.call_count, 2)
        self.assertEqual(len(self.api.ask_about_positions.call_args.args[1]), 1)

    def test_reenter_token_then_replace_failed_question(self):
        from api_client import ChatAccessError

        self.api.ask_about_positions.side_effect = [ChatAccessError("请重新输入口令"), "回答"]
        self.app.run()
        self.unlock()
        self.app.chat_input[0].set_value("原始提问").run()
        self.assertTrue(self.app.chat_input[0].disabled)
        self.assertEqual(len(self.app.chat_message), 1)
        self.unlock()
        self.app.chat_input[0].set_value("更正后的提问").run()
        sent = self.api.ask_about_positions.call_args.args[1]
        self.assertEqual(sent, [{"role": "user", "content": "更正后的提问"}])
        self.assertEqual(len(self.app.chat_message), 2)
        self.api.get_ai_status.side_effect = ConnectionError()
        self.app.run()
        self.assertTrue(self.app.chat_input[0].disabled)
        self.assertEqual(len(self.app.chat_message), 2)

    def test_oldest_whole_turn_is_trimmed(self):
        self.app.run()
        self.unlock()
        for i in range(8):
            self.app.chat_input[0].set_value(f"问题 {i}").run()
        sent = self.api.ask_about_positions.call_args.args[1]
        self.assertEqual(len(sent), 13)
        self.assertEqual(sent[0], {"role": "user", "content": "问题 1"})
        self.assertEqual(len(self.app.chat_message), 16)

    def test_unconfigured_provider_cannot_send(self):
        self.status["providers"][0]["configured"] = False
        self.status["providers"][1]["configured"] = False
        self.app.run()
        self.assertTrue(self.app.chat_input[0].disabled)
        self.assertTrue(any("启动看板助手" in item.value for item in self.app.info))
        self.api.ask_about_positions.assert_not_called()


class ChatRequestTest(unittest.TestCase):
    def test_lost_reply_does_not_repeat_post(self):
        from api_client import FinanceAPIClient

        seen = []

        def disconnect(request):
            seen.append(request)
            raise httpx.RemoteProtocolError("connection closed after POST")

        with httpx.Client(base_url="http://test", transport=httpx.MockTransport(disconnect)) as http:
            client = FinanceAPIClient.__new__(FinanceAPIClient)
            client._client = http
            with self.assertRaisesRegex(ValueError, "手动重试"):
                client.ask_about_positions("codex", [{"role": "user", "content": "测试"}], "private-token")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].headers["authorization"], "Bearer private-token")
        self.assertNotIn(b"private-token", seen[0].content)


if __name__ == "__main__":
    unittest.main()
