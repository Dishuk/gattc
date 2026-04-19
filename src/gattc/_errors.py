"""Shared error-handling helpers for CLI commands."""


import click


def is_debug(ctx: click.Context | None = None) -> bool:
    """Check if --debug flag is active."""
    ctx = ctx or click.get_current_context(silent=True)
    if ctx and ctx.obj:
        return bool(ctx.obj.get("debug", False))
    return False


def handle_error(e: Exception, context_msg: str) -> None:
    """Handle an error respecting --debug flag.

    In debug mode, re-raises the original exception.
    In normal mode, raises a ClickException with a user-friendly message
    and a hint to use --debug.
    """
    if is_debug():
        raise
    raise click.ClickException(f"{context_msg}: {e}\n  Use --debug for full traceback.")
