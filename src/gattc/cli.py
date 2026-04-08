"""
Command-line interface for gattc.
"""

from typing import Optional

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="gattc")
@click.option("--debug", is_flag=True, default=False, help="Show full tracebacks on errors")
@click.pass_context
def main(ctx, debug):
    """gattc - BLE GATT schema compiler for Zephyr.

    Compiles YAML-based GATT service definitions into Zephyr C code.

    If gattc.yaml exists in current directory, runs in project mode.
    Otherwise, requires explicit schema path.
    """
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


def _is_debug(ctx: Optional[click.Context] = None) -> bool:
    """Check if --debug flag is active."""
    ctx = ctx or click.get_current_context(silent=True)
    if ctx and ctx.obj:
        return ctx.obj.get("debug", False)
    return False


def _handle_error(e: Exception, context_msg: str) -> None:
    """Handle an error respecting --debug flag.

    In debug mode, re-raises the original exception.
    In normal mode, raises a ClickException with a user-friendly message
    and a hint to use --debug.
    """
    if _is_debug():
        raise
    raise click.ClickException(f"{context_msg}: {e}\n  Use --debug for full traceback.")


# Register commands
from .commands.compile import compile  # noqa: E402
from .commands.check import check  # noqa: E402
from .commands.docs import docs  # noqa: E402
from .commands.release import release  # noqa: E402
from .commands.init_cmd import init  # noqa: E402

main.add_command(compile)
main.add_command(check)
main.add_command(docs)
main.add_command(release)
main.add_command(init)


if __name__ == "__main__":
    main()
