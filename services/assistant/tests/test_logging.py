import logging

from toy_lair_assistant.factory import build_app
from toy_lair_assistant.settings import Settings


def test_factory_sets_assistant_logger_info() -> None:
    build_app(Settings(assistant_api_token="secret", tick_interval_seconds=0, zayka_sync_enabled=False))
    assert logging.getLogger("toy_lair_assistant").level == logging.INFO
