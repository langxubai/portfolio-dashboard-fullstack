import tempfile
import unittest
from pathlib import Path

from setup_ai import BRIDGE_TOKEN, CHAT_TOKEN, configure, value


class PrivateSetupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = Path(self.folder.name) / ".env"
        self.support = Path(self.folder.name) / "Finance Board"
        self.env.write_text('UNKNOWN="existing setting"\nAI_CHAT_ACCESS_TOKEN=""\n')

    def test_install_reuses_secrets_and_preserves_settings(self):
        configure(self.env, self.support, api_only=False)
        initial = self.env.read_text()
        self.assertIn('UNKNOWN="existing setting"\n', initial)
        host = self.support / "bridge.env"
        self.assertEqual(value(initial, BRIDGE_TOKEN), value(host.read_text(), BRIDGE_TOKEN))
        self.assertNotEqual(value(initial, BRIDGE_TOKEN), value(initial, CHAT_TOKEN))
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(host.stat().st_mode & 0o777, 0o600)
        configure(self.env, self.support, api_only=False)
        self.assertEqual(initial, self.env.read_text())
        host.write_text(f"{BRIDGE_TOKEN}={'x' * 40}\n")
        with self.assertRaises(ValueError):
            configure(self.env, self.support, api_only=False)
        self.assertEqual(initial, self.env.read_text())

    def test_can_enable_api_then_add_codex(self):
        configure(self.env, self.support, api_only=True)
        chat = value(self.env.read_text(), CHAT_TOKEN)
        self.assertFalse(self.support.exists())
        self.assertTrue(chat)
        configure(self.env, self.support, api_only=False)
        self.assertEqual(value(self.env.read_text(), CHAT_TOKEN), chat)
        self.assertTrue((self.support / "bridge.env").is_file())


if __name__ == "__main__":
    unittest.main()
