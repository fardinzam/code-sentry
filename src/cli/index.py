"""CLI sub-commands for codebase indexing."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Index a repository's codebase.")
console = Console()


@app.callback(invoke_without_command=True)
def index_run(
    ctx: typer.Context,
    repo_path: str = typer.Argument(".", help="Repository to index."),
    resume: bool = typer.Option(False, "--resume", help="Resume from the last checkpoint."),
    status: bool = typer.Option(False, "--status", help="Show indexing statistics."),
) -> None:
    """Index the codebase for AI-powered review and querying."""
    if ctx.invoked_subcommand is not None:
        return

    if status:
        _show_status(repo_path)
        return

    _run_index(repo_path, resume=resume)


def _show_status(repo_path: str) -> None:
    """Display current indexing statistics from the checkpoint file."""
    import json

    checkpoint = Path(repo_path) / ".code-reviewer" / "index_checkpoint.json"
    if not checkpoint.exists():
        console.print("[yellow]No indexing data found. Run [bold]code-reviewer index[/] first.[/]")
        return

    data = json.loads(checkpoint.read_text())
    console.print(f"[bold]Indexing Status[/] (in progress / last checkpoint)")
    console.print(f"  Files indexed: [cyan]{len(data.get('completed_files', []))}[/]")
    console.print(f"  Total chunks:  [cyan]{data.get('total_chunks', 0)}[/]")


def _run_index(repo_path: str, resume: bool) -> None:
    """Execute the indexing pipeline."""
    import os
    from src.config.settings import get_settings
    from src.indexing.embedder import make_embedding_client
    from src.indexing.vectordb import ChromaDBClient
    from src.indexing.pipeline import IndexingPipeline
    from src.utils.logging import configure_logging

    repo = Path(repo_path).resolve()
    cr_dir = repo / ".code-reviewer"
    cr_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings(repo)
    configure_logging(
        level=settings.logging.level,
        fmt=settings.logging.format,
        log_dir=Path(settings.logging.log_dir),
    )

    console.print(f"[bold]Indexing[/] [cyan]{repo}[/]" + (" (resuming)" if resume else ""))

    embedder = make_embedding_client(
        provider=settings.embedding.provider,
        model=settings.embedding.model,
        batch_size=settings.embedding.batch_size,
    )

    vector_db = ChromaDBClient(
        persist_directory=str(cr_dir / "vectordb"),
        collection_name=settings.vectordb.collection_name,
    )

    pipeline = IndexingPipeline(
        repo_root=repo,
        embedder=embedder,
        vector_db=vector_db,
        settings=settings.indexing,
        code_reviewer_dir=cr_dir,
    )

    try:
        stats = pipeline.run(resume=resume)
        console.print(
            f"[green]✓[/] Indexing complete: "
            f"[cyan]{stats['files_processed']}[/] files, "
            f"[cyan]{stats['chunks_created']}[/] chunks "
            f"([dim]{stats['files_skipped']} skipped[/])"
        )
    except Exception as exc:
        console.print(f"[red]✗ Indexing failed:[/] {exc}")
        raise typer.Exit(1)
