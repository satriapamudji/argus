"""Command parsing + routing for Telegram control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: str


def parse_command(
    text: Optional[str], *, bot_username: Optional[str] = None
) -> Optional[ParsedCommand]:
    if not text:
        return None

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    first, *rest = stripped.split(maxsplit=1)
    args = rest[0].strip() if rest else ""

    # Support "/cmd@BotName" form in groups.
    cmd = first[1:]
    if "@" in cmd:
        cmd_name, cmd_bot = cmd.split("@", 1)
        if bot_username and cmd_bot.lower() != bot_username.lower():
            return None
        cmd = cmd_name

    return ParsedCommand(name=cmd.lower(), args=args)
