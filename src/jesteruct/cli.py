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


@app.command()
def evaluate(
    cases: Annotated[Path, typer.Option(help="Labelled cases (JSONL).")] = Path("evalset/cases.jsonl"),
    out: Annotated[Path, typer.Option(help="Where to write the report.")] = Path("out/evaluate"),
    limit: int | None = None,
    api: Annotated[str | None, typer.Option(help="A running service to route through (http://localhost:8000).")] = None,
) -> None:
    """Route the labelled eval set and report lane accuracy, under-routing, latency and cost."""
    from .eval import run_eval

    summary = asyncio.run(run_eval(cases, get_settings(), out, limit, api))
    typer.echo(json.dumps(summary, indent=2))


@app.command()
def calibrate(
    results: Annotated[list[Path], typer.Argument(exists=True, help="`jst evaluate` results.jsonl file(s) to fit on.")],
    check: Annotated[Path | None, typer.Option(exists=True, help="Held-out results.jsonl to report on.")] = None,
    cost_ratio: Annotated[float, typer.Option(help="Cost of a silent wrong lane / cost of one review.")] = 10.0,
    out: Annotated[Path | None, typer.Option(help="Where to write the calibration.")] = None,
) -> None:
    """Fit the review calibration on evaluation results and write it where the router loads it.

    Rows of the held-out split are never fitted on; they are reported separately.
    """
    from . import calibrate as cal
    from .pipeline import CALIBRATION_FILE

    rows = [json.loads(line) for path in results for line in path.read_text().split("\n") if line.strip()]
    held_out = [r for r in rows if r.get("split") == "holdout"]
    fit_rows = [r for r in rows if r.get("split") != "holdout"]
    fitted = cal.fit(fit_rows, cost_ratio, fitted_on=", ".join(str(p) for p in results) + ", holdout excluded")
    cal.save(fitted, out or CALIBRATION_FILE)
    report = {
        "version": fitted.version,
        "n": fitted.n,
        "threshold": fitted.threshold,
        "fit": cal.evaluate(fitted, fit_rows),
    }
    if held_out:
        report["holdout"] = cal.evaluate(fitted, held_out)
    if check:
        held_out = [json.loads(line) for line in check.read_text().split("\n") if line.strip()]
        report["check"] = cal.evaluate(fitted, held_out)
    typer.echo(json.dumps(report, indent=2))


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
