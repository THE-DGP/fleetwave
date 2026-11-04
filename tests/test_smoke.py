"""Smoke tests: the package imports and the CLI entry point works."""

import importlib

import pytest
from typer.testing import CliRunner

from fleetwave import __version__
from fleetwave.cli import app

MODULES = [
    "fleetwave.models",
    "fleetwave.integration",
    "fleetwave.scheduler.baseline",
    "fleetwave.scheduler.model",
    "fleetwave.scheduler.montecarlo",
    "fleetwave.scheduler.scenarios",
    "fleetwave.scanner.checks",
    "fleetwave.scanner.score",
    "fleetwave.scanner.sources",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output
