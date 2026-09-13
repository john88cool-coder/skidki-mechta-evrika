from skidki import config


def test_dotenv_fills_only_missing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# комментарий\nTELEGRAM_BOT_TOKEN="123:abc"\nTELEGRAM_CHAT_ID=42\nEMPTY=\n',
        encoding="utf-8",
    )
    environ = {"TELEGRAM_CHAT_ID": "from-env"}
    config._load_dotenv(env_file, environ)
    assert environ == {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "from-env"}


def test_missing_dotenv_is_fine(tmp_path):
    environ: dict[str, str] = {}
    config._load_dotenv(tmp_path / "нет.env", environ)
    assert environ == {}


def test_load_rules_reads_deal_and_watch(tmp_path):
    rules_file = tmp_path / "rules.toml"
    rules_file.write_text(
        'deal_pct = 25\ndeal_min_price = 30000\n[[watch]]\nquery = "Watch"\nmax_price = 100000\n',
        encoding="utf-8",
    )
    rules = config.load_rules(rules_file)
    assert rules.deal_pct == 25 and rules.deal_min_price == 30_000
    assert rules.watch[0].query == "Watch" and rules.watch[0].max_price == 100_000


def test_repo_rules_file_parses():
    rules = config.load_rules(config.ROOT / "rules.toml")
    assert rules.deal_pct == 20 and rules.deal_min_price == 20_000 and rules.drop_pct == 7
