"""
gattc - BLE GATT Schema Compiler

A tool for compiling YAML-based GATT service definitions into
platform-specific code (e.g., Zephyr C code).
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("gattc")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
