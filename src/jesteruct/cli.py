"""`jst` command line. Each command is a thin shell over one module."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from .config import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Route documents into processing lanes.")


@app.command()
def route(
    paths: Annotated[list[Path], typer.Argument(exists=True, help="Files or directories to route.")],
    out: Annotated[Path, typer.Option(help="Directory for manifests.")] = Path("out"),
) -> None:
    """Route files natively and write one manifest per document."""
    from .pipeline import route_paths

    manifests = asyncio.run(route_paths(paths, get_settings(), out))
    typer.echo(f"{len(manifests)} manifest(s) in {out}")


@app.command()
def probe(path: Annotated[Path, typer.Argument(exists=True)], page: int = 0) -> None:
    """Print the evidence and Jev state for one page, without calling any provider."""
    from .pipeline import probe_state

    typer.echo(json.dumps(asyncio.run(probe_state(path, page, get_settings())), indent=2, ensure_ascii=False))


@app.command(name="eval")
def evaluate(
    cases: Annotated[Path, typer.Option(help="Labelled cases (JSONL).")] = Path("eval/cases.jsonl"),
    out: Annotated[Path, typer.Option(help="Where to write the report.")] = Path("out/eval"),
    limit: int | None = None,
) -> None:
    """Route the labelled eval set and report lane accuracy, under-routing, latency and cost."""
    from .eval import run_eval

    summary = asyncio.run(run_eval(cases, get_settings(), out, limit))
    typer.echo(json.dumps(summary, indent=2))


@app.command()
def view(
    manifests: Annotated[Path, typer.Argument(exists=True, help="Directory of manifests.")] = Path("out"),
    out: Annotated[Path, typer.Option()] = Path("out/report.html"),
) -> None:
    """Write an HTML page showing every page's thumbnail, lane and reasons."""
    from .view import render_dir

    typer.echo(asyncio.run(render_dir(manifests, get_settings(), out)))


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run("jesteruct.api:create_app", factory=True, host=host, port=port, proxy_headers=True)


@app.command()
def worker(metrics_port: int = 9090) -> None:
    """Run a queue worker."""
    from .worker import run

    asyncio.run(run(get_settings(), metrics_port))
