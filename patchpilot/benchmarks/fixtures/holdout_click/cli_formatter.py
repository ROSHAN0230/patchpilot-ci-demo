import click


def format_banner(text: str) -> str:
    """Formats a header banner centered according to terminal width."""
    columns, _ = click.get_terminal_size()
    padding = max(0, (columns - len(text)) // 2)
    return " " * padding + text


def format_status(status: str) -> str:
    columns, _ = click.get_terminal_size()
    divider = "=" * min(columns, 60)
    return f"{divider}\nSTATUS: {status}\n{divider}"
