"""Tests for stackr init — verifies the generated stackr.yml contains all catalog apps."""

from __future__ import annotations

from pathlib import Path

import yaml

from stackr.catalog import Catalog


def _run_init(tmp_path: Path) -> Path:
    """Run the init command non-interactively and return the output path."""
    from typer.testing import CliRunner

    from stackr.cli import app

    output = tmp_path / "stackr.yml"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--output", str(output)],
        input="\n\n\n\n\n\n\n\n\n",  # accept all defaults
    )
    assert result.exit_code == 0, f"init failed: {result.output}\n{result.exception}"
    return output


def test_init_includes_all_catalog_apps(tmp_path: Path) -> None:
    """stackr init must write every catalog app into the generated stackr.yml."""
    output = _run_init(tmp_path)

    with open(output) as f:
        content = f.read()

    catalog = Catalog()
    catalog_names = {a.name for a in catalog.all()}

    # Parse the YAML to get the written app names
    raw = yaml.safe_load(content)
    written_names = {entry["name"] for entry in (raw.get("apps") or [])}

    missing = catalog_names - written_names
    assert not missing, f"init did not write these catalog apps: {sorted(missing)}"


def test_init_only_traefik_and_portainer_enabled(tmp_path: Path) -> None:
    """Only traefik and portainer should be enabled: true by default."""
    output = _run_init(tmp_path)

    with open(output) as f:
        raw = yaml.safe_load(f)

    enabled = {entry["name"] for entry in (raw.get("apps") or []) if entry.get("enabled")}
    # socket-proxy may be auto-injected by the config validator — allow it
    allowed_enabled = {"traefik", "portainer", "socket-proxy"}
    unexpected = enabled - allowed_enabled
    assert not unexpected, f"Unexpected apps enabled by default: {sorted(unexpected)}"


def test_init_all_other_apps_disabled(tmp_path: Path) -> None:
    """Every app except traefik and portainer must be explicitly disabled."""
    output = _run_init(tmp_path)

    with open(output) as f:
        raw = yaml.safe_load(f)

    default_on = {"traefik", "portainer"}
    for entry in raw.get("apps") or []:
        if entry["name"] not in default_on:
            assert entry.get("enabled") is False, (
                f"App '{entry['name']}' should default to enabled: false"
            )


def test_example_file_contains_all_catalog_apps() -> None:
    """stackr.yml.example must list every catalog app so it stays in sync with the catalog."""
    example = Path(__file__).parent.parent / "stackr.yml.example"
    assert example.exists(), "stackr.yml.example not found"

    with open(example) as f:
        raw = yaml.safe_load(f)

    catalog = Catalog()
    catalog_names = {a.name for a in catalog.all()}
    written_names = {entry["name"] for entry in (raw.get("apps") or [])}

    missing = catalog_names - written_names
    assert not missing, (
        f"stackr.yml.example is missing these catalog apps: {sorted(missing)}\n"
        "Update stackr.yml.example to include all catalog apps."
    )
