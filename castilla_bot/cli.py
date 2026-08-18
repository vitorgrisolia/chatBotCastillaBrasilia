"""Interface de terminal para testar o chatbot."""

from __future__ import annotations

import sys
from uuid import uuid4

from .bot import CastillaBot


def main() -> None:
    # O Windows pode iniciar o terminal em cp1252, que não representa emojis.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    bot = CastillaBot()
    session_id = str(uuid4())
    print("\nBOT:\n" + bot.start(session_id))

    while True:
        try:
            message = input("\nVOCÊ: ")
        except (EOFError, KeyboardInterrupt):
            print("\nConversa encerrada.")
            break
        if message.strip().casefold() in {"sair", "exit"}:
            print("Conversa encerrada.")
            break
        print("\nBOT:\n" + bot.handle(session_id, message))


if __name__ == "__main__":
    main()
