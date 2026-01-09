from argus.telegram_control.commands import parse_command


class TestParseCommand:
    def test_none(self) -> None:
        assert parse_command(None) is None

    def test_non_command(self) -> None:
        assert parse_command("hello") is None

    def test_simple(self) -> None:
        cmd = parse_command("/start")
        assert cmd is not None
        assert cmd.name == "start"
        assert cmd.args == ""

    def test_args(self) -> None:
        cmd = parse_command("/subscribe us_markets")
        assert cmd is not None
        assert cmd.name == "subscribe"
        assert cmd.args == "us_markets"

    def test_cmd_with_bot_username_matches(self) -> None:
        cmd = parse_command("/start@ArgusBot", bot_username="ArgusBot")
        assert cmd is not None
        assert cmd.name == "start"

    def test_cmd_with_bot_username_mismatch_ignored(self) -> None:
        cmd = parse_command("/start@OtherBot", bot_username="ArgusBot")
        assert cmd is None
