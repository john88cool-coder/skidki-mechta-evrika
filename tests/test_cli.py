import logging

from skidki import cli


def test_http_client_logs_never_carry_bot_token(caplog):
    # httpx на INFO логирует полный URL, а в URL Bot API — токен бота.
    cli._configure_logging(verbose=True)
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("httpx").info("POST https://api.telegram.org/bot123:SECRET/sendMessage")
    assert "SECRET" not in caplog.text
