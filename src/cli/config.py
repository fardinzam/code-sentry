"""CLI sub-commands for configuration management."""

from __future__ import annotations

import warnings
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Manage code-reviewer configuration.")
console = Console()


@app.command("show")
def config_show(
    repo_path: str = typer.Option(".", help="Repository path."),
) -> None:
    """Print the resolved configuration (sensitive values masked)."""
    from src.config.settings import get_settings, SENSITIVE_KEY_FRAGMENTS

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = get_settings(Path(repo_path).resolve())

    table = Table(title="Resolved Configuration", show_header=True)
    table.add_column("Section.Key", style="cyan")
    table.add_column("Value", style="white")

    for section_name in vars(settings):
        section = getattr(settings, section_name)
        for key, value in vars(section).items():
            if key.startswith("_"):
                continue
            display_value = (
                "***MASKED***"
                if any(frag in key for frag in SENSITIVE_KEY_FRAGMENTS)
                else str(value)
            )
            table.add_row(f"{section_name}.{key}", display_value)

    console.print(table)


@app.command("init")
def config_init(
    repo_path: str = typer.Argument(".", help="Repository path."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config."),
) -> None:
    """Generate a .code-reviewer/config.toml in the repository."""
    import shutil

    repo = Path(repo_path).resolve()
    config_dest = repo / ".code-reviewer" / "config.toml"
    config_dest.parent.mkdir(parents=True, exist_ok=True)

    if config_dest.exists() and not force:
        console.print(f"[yellow]Config already exists:[/] {config_dest}")
        console.print("Use [bold]--force[/] to overwrite.")
        raise typer.Exit(1)

    default_src = Path(__file__).parent.parent / "config" / "default_config.toml"
    if default_src.exists():
        shutil.copy(default_src, config_dest)
    else:
        config_dest.write_text("# code-reviewer project config\n")

    console.print(f"[green]✓[/] Config written to [bold]{config_dest}[/]")


@app.command("validate")
def config_validate(
    repo_path: str = typer.Option(".", help="Repository path."),
) -> None:
    """Validate the configuration for errors."""
    import warnings
    from pydantic import ValidationError

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from src.config.settings import get_settings
            get_settings(Path(repo_path).resolve())

        if caught:
            console.print("[yellow]Warnings:[/]")
            for w in caught:
                console.print(f"  ⚠  {w.message}")

        console.print("[green]✓[/] Configuration is valid.")

    except Exception as exc:
        console.print(f"[red]✗ Configuration error:[/] {exc}")
        raise typer.Exit(1)
