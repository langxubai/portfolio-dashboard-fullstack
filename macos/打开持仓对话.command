#!/bin/bash
# Finder shortcut for the local, already configured dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/setup_ai.py --show-chat-token | /usr/bin/pbcopy
/usr/bin/open 'http://127.0.0.1:8501/%E9%97%AE%E6%88%91%E7%9A%84%E6%8C%81%E4%BB%93'
echo '聊天口令已复制。请在看板的「聊天口令」框中按 ⌘V。'
