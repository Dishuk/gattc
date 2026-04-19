"""
Command-line interface for gattc.
"""

import click

from . import __version__
from .commands.changelog import changelog
from .commands.check import check
from .commands.compile import compile
from .commands.docs import docs
from .commands.init_cmd import init
from .commands.release import release


@click.group()
@click.version_option(version=__version__, prog_name="gattc")
@click.option("--debug", is_flag=True, default=False, help="Show full tracebacks on errors")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """gattc - BLE GATT schema compiler for Zephyr.

    Compiles YAML-based GATT service definitions into Zephyr C code.

    If gattc.yaml exists in current directory, runs in project mode.
    Otherwise, requires explicit schema path.
    """
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


main.add_command(compile)
main.add_command(check)
main.add_command(docs)
main.add_command(release)
main.add_command(init)
main.add_command(changelog)


if __name__ == "__main__":
    main()
