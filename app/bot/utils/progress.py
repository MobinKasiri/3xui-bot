"""Traffic progress bar renderer."""


def traffic_bar(used_bytes: int, total_bytes: int, width: int = 10) -> str:
    """Return a block progress bar string. total_bytes=0 means unlimited."""
    if total_bytes == 0:
        return "∞"
    pct = min(used_bytes / total_bytes, 1.0)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


def format_gb(bytes_: int) -> str:
    if bytes_ < 0:
        bytes_ = 0
    return f"{bytes_ / (1024 ** 3):.1f}"
