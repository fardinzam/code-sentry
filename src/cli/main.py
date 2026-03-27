"""Code Reviewer CLI — AI-powered code review and auto-refactoring.

Entry point: code-reviewer <command> [options]
"""

from __future__ import annotations

import typer
from rich.console import Console

from src.cli import config as config_cmd
from src.cli import index as index_cmd

app = typer.Typer(
    name="code-reviewer",
    help="AI-powered code reviewer and auto-refactor system.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register sub-command groups
app.add_typer(config_cmd.app, name="config")
app.add_typer(index_cmd.app, name="index")


@app.command()
def version() -> None:
    """Print the current version."""
    console.print("[bold cyan]code-reviewer[/] v0.1.0")


@app.command()
def init(
    repo_path: str = typer.Argument(".", help="Path to the repository to register."),
) -> None:
    """Initialize code-reviewer for a repository.

    Creates the .code-reviewer/ directory and scaffolds config files.
    """
    from pathlib import Path
    import shutil

    repo = Path(repo_path).resolve()
    cr_dir = repo / ".code-reviewer"
    cr_dir.mkdir(parents=True, exist_ok=True)
    (cr_dir / "audit").mkdir(exist_ok=True)
    (cr_dir / "logs").mkdir(exist_ok=True)
    (cr_dir / "locks").mkdir(exist_ok=True)

    config_dest = cr_dir / "config.toml"
    if not config_dest.exists():
        default_config = Path(__file__).parent.parent / "config" / "default_config.toml"
        if default_config.exists():
            shutil.copy(default_config, config_dest)
        else:
            config_dest.write_text("# code-reviewer project config\n")

    console.print(f"[green]✓[/] Initialized code-reviewer in [bold]{cr_dir}[/]")
    console.print(f"  Edit [cyan]{config_dest}[/] to configure LLM provider and settings.")
    console.print("  Next: [bold]code-reviewer index[/] to index your codebase.")


if __name__ == "__main__":
    app()
