"""apps/bot/stub.py — заглушка бота до Итерации 0-А.

Просто спит, чтобы контейнер не падал в crash-loop и docker compose
показывал сервис как running. Агент заменит этот файл на реальный
aiogram 3 dispatcher при реализации Итерации 0-А.
"""
import time
import os
import signal
import sys


def _graceful_exit(signum, frame):
    print(f"bot stub: got signal {signum}, exiting", flush=True)
    sys.exit(0)


def main():
    print("bot stub: idle; waiting for Iteration 0-A code", flush=True)
    signal.signal(signal.SIGTERM, _graceful_exit)
    signal.signal(signal.SIGINT, _graceful_exit)
    tz = os.environ.get("TZ", "UTC")
    print(f"bot stub: TZ={tz}", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
