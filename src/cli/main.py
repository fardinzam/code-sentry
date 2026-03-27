"""Code Reviewer CLI — AI-powered code review and auto-refactoring."""

import typer

app = typer.Typer(
    name="code-reviewer",
    help="AI-powered code reviewer and auto-refactor system.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the current version."""
    typer.echo("code-reviewer v0.1.0")


if __name__ == "__main__":
    app()
