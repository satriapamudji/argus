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


class TestNextUpdateCountdown:
    def test_next_update_is_per_stream(self) -> None:
        from datetime import datetime, timezone

        from argus.config import DaemonConfig, ScheduleConfig, StreamConfig, StreamDaemonConfig
        from argus.telegram_control.poller import _format_countdown, _get_next_report_run_utc

        now_utc = datetime(2026, 1, 15, 17, 9, tzinfo=timezone.utc)  # 2026-01-16 01:09 SGT

        cfg = type("Cfg", (), {})()
        cfg.daemon = DaemonConfig()

        us_markets = StreamConfig(
            name="us_markets",
            schedule=ScheduleConfig(
                daily_us_close_sgt="06:00",
                weekend_wrap_sgt="10:00",
                monday_preview_ny="SUN 18:10",
                daily_crypto_utc="00:00",
            ),
            daemon=StreamDaemonConfig(jobs_enabled={"crypto_daily": False}),
        )
        crypto = StreamConfig(
            name="crypto",
            schedule=ScheduleConfig(
                daily_us_close_sgt="06:00",
                weekend_wrap_sgt="10:00",
                monday_preview_ny="SUN 18:10",
                daily_crypto_utc="00:00",
            ),
            daemon=StreamDaemonConfig(
                jobs_enabled={"us_close": False, "weekend_wrap": False, "monday_preview": False}
            ),
        )

        # Minimal stub to satisfy _get_next_report_run_utc(config.get_stream(...))
        def _get_stream(name: str) -> StreamConfig:
            return {"us_markets": us_markets, "crypto": crypto}[name]

        cfg.get_stream = _get_stream

        next_us = _get_next_report_run_utc(cfg, "us_markets", now_utc)
        next_crypto = _get_next_report_run_utc(cfg, "crypto", now_utc)

        assert next_us is not None
        assert next_crypto is not None

        # us_close next run: 06:00 SGT => 22:00 UTC (4h51m from now_utc)
        assert _format_countdown(now_utc, next_us) == (4, 51)

        # crypto_daily next run: 00:00 UTC (6h51m from now_utc)
        assert _format_countdown(now_utc, next_crypto) == (6, 51)
