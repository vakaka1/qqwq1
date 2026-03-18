from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.services.backend_client import BackendClient
from app.services.managed_bot_runner import ManagedBotRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


async def main() -> None:
    settings = get_settings()
    backend_client = BackendClient()
    runner = ManagedBotRunner(backend_client, settings.sync_interval_seconds)

    try:
        await backend_client.ping()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Не удалось проверить backend при старте bot-runner: %s", exc)

    try:
        await runner.run_forever()
    finally:
        await runner.shutdown()
        await backend_client.close()


if __name__ == "__main__":
    asyncio.run(main())
