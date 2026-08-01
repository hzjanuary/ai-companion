"""Deterministic Telegram command grammar and response templates.

This module has no database or provider dependency.  Runtime workers use its
typed result to decide whether a durable command job needs authorization or a
state mutation.
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class CommandOperation(StrEnum):
    READ = "read"
    CONFIGURATION = "configuration"
    PREFERENCE = "preference"
    MEMORY = "memory"
    UNKNOWN = "unknown"
    USAGE = "usage"


@dataclass(frozen=True, slots=True)
class CommandRequest:
    name: str
    operation: CommandOperation
    action: str = "status"
    value: str | bool | None = None


_PROFILE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?(?:@[1-9][0-9]*)?$")
_MODES = {"mention_only", "mention_and_name", "ambient_selective"}
_MEMORY_PUBLIC_ID = re.compile(r"^[A-Za-z0-9]{8,24}$")


def parse_command(name: str, arguments: str) -> CommandRequest:
    """Parse the complete, intentionally small command grammar."""

    if name in {"start", "help", "status"}:
        return _empty(name, arguments)
    if name == "quiet" or name == "resume":
        return _empty(name, arguments, CommandOperation.CONFIGURATION, name)
    if name == "mode":
        if not arguments or arguments == "status":
            return CommandRequest(name, CommandOperation.READ)
        if arguments in _MODES:
            return CommandRequest(
                name, CommandOperation.CONFIGURATION, "mode", arguments
            )
        return _usage(name)
    if name == "frequency":
        if not arguments or arguments == "status":
            return CommandRequest(name, CommandOperation.READ)
        if arguments in {"low", "normal", "high"}:
            return CommandRequest(
                name, CommandOperation.CONFIGURATION, "frequency", arguments
            )
        return _usage(name)
    if name == "personality":
        if not arguments or arguments == "status":
            return CommandRequest(name, CommandOperation.READ)
        if arguments == "list":
            return CommandRequest(name, CommandOperation.READ, "list")
        prefix, _, profile = arguments.partition(" ")
        if (
            prefix == "use"
            and profile
            and " " not in profile
            and _PROFILE.fullmatch(profile)
        ):
            return CommandRequest(name, CommandOperation.CONFIGURATION, "use", profile)
        return _usage(name)
    if name in {"stickers", "mentions", "teasing"}:
        if not arguments or arguments == "status":
            return CommandRequest(name, CommandOperation.READ)
        if arguments in {"on", "off"}:
            operation = (
                CommandOperation.PREFERENCE
                if name in {"mentions", "teasing"}
                else CommandOperation.CONFIGURATION
            )
            return CommandRequest(name, operation, "set", arguments == "on")
        return _usage(name)
    if name == "memory":
        if not arguments:
            return CommandRequest(name, CommandOperation.MEMORY, "summary")
        if arguments == "list":
            return CommandRequest(name, CommandOperation.MEMORY, "list")
        if arguments == "reset_group confirm":
            return CommandRequest(name, CommandOperation.MEMORY, "reset_group")
        prefix, separator, content = arguments.partition(" ")
        if prefix == "remember" and separator and content:
            return CommandRequest(name, CommandOperation.MEMORY, "remember", content)
        return _usage(name)
    if name == "forget":
        return (
            CommandRequest(name, CommandOperation.MEMORY, "forget", arguments)
            if _MEMORY_PUBLIC_ID.fullmatch(arguments)
            else _usage(name)
        )
    if name == "forget_me":
        if not arguments:
            return CommandRequest(name, CommandOperation.MEMORY, "warning")
        return (
            CommandRequest(name, CommandOperation.MEMORY, "confirm")
            if arguments == "confirm"
            else _usage(name)
        )
    return CommandRequest(name, CommandOperation.UNKNOWN)


def command_response(
    code: str, *, language: str = "vi", detail: str | None = None
) -> str:
    """Return compact code-owned text; auto language resolves to Vietnamese."""

    english = language == "en"
    templates = {
        "start": (
            "January da san sang. Dung /help de xem lenh.",
            "January is ready. Use /help for commands.",
        ),
        "help": (
            "Xem: /start, /status. Ca nhan: /mentions, /teasing. Quan tri nhom: "
            "/mode, /frequency, /quiet, /resume, /personality, /stickers.",
            "View: /start, /status. Personal: /mentions, /teasing. Group admins: "
            "/mode, /frequency, /quiet, /resume, /personality, /stickers.",
        ),
        "usage": ("Cu phap khong hop le. Dung /help.", "Invalid syntax. Use /help."),
        "unknown": (
            "Lenh chua duoc ho tro. Dung /help.",
            "Unsupported command. Use /help.",
        ),
        "denied": (
            "Ban khong duoc phep thay doi cai dat nay.",
            "You are not allowed to change this setting.",
        ),
        "temporary_failure": (
            "Khong the xac minh quyen luc nay. Thu lai sau.",
            "Cannot verify permission now. Try again later.",
        ),
        "success": ("Da cap nhat.", "Updated."),
        "status": ("Trang thai:", "Status:"),
        "unchanged": (
            "Cai dat da dung nhu hien tai.",
            "That setting is already current.",
        ),
        "ambient_disabled": ("Che do nay chua duoc bat.", "That mode is not enabled."),
        "sticker_mapping_unavailable": (
            "Chua co sticker phu hop de bat tinh nang nay.",
            "No deliverable sticker mapping is configured.",
        ),
        "conflict": (
            "Cai dat vua thay doi. Hay kiem tra /status va thu lai.",
            "That setting changed. Check /status and try again.",
        ),
        "safe_failure": (
            "Khong the xu ly lenh nay luc nay.",
            "Cannot process this command right now.",
        ),
        "profile_not_found": (
            "Khong tim thay cau hinh tinh cach dang hoat dong.",
            "The requested active personality was not found.",
        ),
        "profile_not_owned": (
            "Tinh cach nay khong dung cho January nay.",
            "That personality is not available to this January instance.",
        ),
        "memory_summary": (
            "Bo nho chi luu khi ban dung /memory remember. "
            "Pham vi: cuoc tro chuyen nay.",
            "Memory is saved only with /memory remember and stays "
            "in this conversation.",
        ),
        "memory_saved": ("Da luu bo nho.", "Memory saved."),
        "memory_deleted": ("Da xoa bo nho.", "Memory deleted."),
        "memory_missing": (
            "Khong tim thay bo nho dang hoat dong.",
            "No active memory found.",
        ),
        "memory_reset": ("Da xoa bo nho cua nhom.", "Group memories cleared."),
        "memory_private_reset": (
            "Lenh nay chi dung trong nhom.",
            "This command is available only in groups.",
        ),
        "forget_me_warning": (
            "Xac nhan bang /forget_me confirm. January se xoa/an danh hoa ho so va "
            "noi dung cua ban tai ket noi nay; tin da gui va yeu cau nha cung cap "
            "khong the thu hoi.",
            "Confirm with /forget_me confirm. January will erase/anonymize your "
            "profile and authored content for this connection; delivered messages "
            "and provider requests cannot be retracted.",
        ),
        "forget_me_done": (
            "Da xu ly yeu cau xoa du lieu.",
            "Your deletion request has been processed.",
        ),
        "forget_me_unchanged": (
            "Yeu cau xoa du lieu da duoc xu ly truoc do.",
            "Your deletion request was already processed.",
        ),
    }
    base = templates.get(code, templates["safe_failure"])[1 if english else 0]
    return f"{base} {detail}" if detail else base


def _empty(
    name: str,
    arguments: str,
    operation: CommandOperation = CommandOperation.READ,
    action: str = "status",
) -> CommandRequest:
    return CommandRequest(name, operation, action) if not arguments else _usage(name)


def _usage(name: str) -> CommandRequest:
    return CommandRequest(name, CommandOperation.USAGE)
