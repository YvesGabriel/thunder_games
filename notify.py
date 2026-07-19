#!/usr/bin/env python3
"""Compat: o Telegram agora vive em services/telegram.py.

Este arquivo mantém `import notify` (usado pelo bot.py) e o teste
`python notify.py "msg"` funcionando enquanto a refatoração acontece.
"""

import sys

from services.telegram import get_updates, send_message, send_video  # noqa: F401

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Thunder Games conectado! 🎮⚡"
    print(send_message(msg))
