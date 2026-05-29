"""Jarvis terminal client — the payoff of the schema.

Introspection over the event spine: tail events, show projected state, inspect a row,
trace a causal chain, peek the DLQ — plus `ingest`/`consume` to run the spine. Built on
Typer + Rich. No model is involved (that arrives in M3).

Note: this module intentionally avoids `from __future__ import annotations` — Typer reads
runtime type hints to build the CLI, and stringized annotations break that.
"""


import typer
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from jarvis import db
from jarvis.config import get_settings
from jarvis.events.repository import get_event
from jarvis.events.stream import get_redis

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Jarvis CLI")
events_app = typer.Typer(no_args_is_help=True, help="Event log introspection")
state_app = typer.Typer(no_args_is_help=True, help="State projection")
inspect_app = typer.Typer(no_args_is_help=True, help="Inspect a single record")
app.add_typer(events_app, name="events")
app.add_typer(state_app, name="state")
app.add_typer(inspect_app, name="inspect")

console = Console()


def _short(value: object) -> str:
    text = str(value) if value is not None else ""
    return text[:19] if len(text) > 19 else text


def _parse_duration(text: str):
    """Parse '12h' / '30m' / '2d' / '90s' into a timedelta."""
    from datetime import timedelta

    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = text.strip().lower()
    if len(text) < 2 or text[-1] not in units or not text[:-1].isdigit():
        raise typer.BadParameter("duration must look like 12h, 30m, 2d, or 90s")
    return timedelta(seconds=int(text[:-1]) * units[text[-1]])


@app.command()
def ingest(once: bool = typer.Option(False, help="Publish one event then exit")) -> None:
    """Stream Docker events from the remote daemon into the event spine."""
    from jarvis.ingest.docker_events import run_ingester

    run_ingester(once=once)


@app.command()
def consume(once: bool = typer.Option(False, help="Run one batch then exit")) -> None:
    """Consume the event stream → events table → state projector."""
    from jarvis.events.consumer import run_forever, run_once

    if once:
        result = run_once()
        console.print(result)
    else:
        run_forever()


@events_app.command("tail")
def events_tail(n: int = typer.Option(20, "-n", "--number", help="How many recent events")) -> None:
    """Show the most recent events (newest last)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, occurred_at, type, severity, entity_ref, correlation_id "
            "FROM events ORDER BY id DESC LIMIT %s",
            (n,),
        ).fetchall()

    table = Table(title=f"events (last {len(rows)})")
    for col in ("occurred_at", "type", "severity", "entity_ref", "correlation_id", "id"):
        table.add_column(col, overflow="fold")
    for row in reversed(rows):
        table.add_row(
            _short(row["occurred_at"]), row["type"], row["severity"],
            row["entity_ref"] or "", row["correlation_id"], row["id"],
        )
    console.print(table)


@state_app.command("show")
def state_show(kind: str | None = typer.Option(None, help="Filter by kind")) -> None:
    """Show the current state projection."""
    sql = "SELECT entity, kind, status, attrs, updated_at, last_event_id FROM state"
    params: tuple = ()
    if kind is not None:
        sql += " WHERE kind = %s"
        params = (kind,)
    sql += " ORDER BY entity"
    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    table = Table(title=f"state ({len(rows)} rows)")
    for col in ("entity", "kind", "status", "attrs", "updated_at"):
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            row["entity"], row["kind"], row["status"] or "",
            str(row["attrs"]), _short(row["updated_at"]),
        )
    console.print(table)


@inspect_app.command("event")
def inspect_event(event_id: str) -> None:
    """Print a single event row in full."""
    with db.connect() as conn:
        event = get_event(conn, event_id)
    if event is None:
        console.print(f"[red]no event[/red] {event_id}")
        raise typer.Exit(code=1)
    console.print(JSON(event.model_dump_json()))


@app.command()
def trace(correlation_id: str) -> None:
    """Show the full causal chain (events + intents + executions) for a correlation id."""
    # (record_kind, table, id column, type column, detail column)
    specs = (
        ("event", "events", "id", "type", "severity"),
        ("intent", "intents", "intent_id", "type", "status"),
        ("execution", "executions", "exec_id", "outcome", "failure_class"),
    )
    rows: list[dict] = []
    with db.connect() as conn:
        for record_kind, table, id_col, type_col, detail_col in specs:
            sql = (
                f"SELECT {id_col} AS id, {type_col} AS type, "
                f"{detail_col} AS detail, causation_id "
                f"FROM {table} WHERE correlation_id = %s"
            )
            for row in conn.execute(sql, (correlation_id,)).fetchall():
                row["record_kind"] = record_kind
                rows.append(row)

    rows.sort(key=lambda r: r["id"])  # ULID ids sort chronologically
    table = Table(title=f"trace {correlation_id} ({len(rows)} records)")
    for col in ("record_kind", "id", "type", "detail", "causation_id"):
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            row["record_kind"], row["id"], str(row["type"]),
            str(row["detail"]) if row["detail"] is not None else "",
            row["causation_id"] or "",
        )
    console.print(table)


@app.command()
def dlq(n: int = typer.Option(20, "-n", "--number", help="How many DLQ entries")) -> None:
    """Show recent dead-lettered messages."""
    settings = get_settings()
    r = get_redis()
    entries = r.xrevrange(settings.dlq_stream, count=n)

    table = Table(title=f"dlq ({len(entries)} entries)")
    for col in ("stream_id", "failure_class", "error", "original_id"):
        table.add_column(col, overflow="fold")
    for stream_id, fields in entries:
        table.add_row(
            stream_id, fields.get("failure_class", ""),
            fields.get("error", ""), fields.get("original_id", ""),
        )
    console.print(table)


@app.command()
def summarize(
    since: str = typer.Option("12h", "--since", help="Window: 12h, 30m, 2d, 90s"),
) -> None:
    """Summarize recent events with the reasoning model (one-shot)."""
    from jarvis.agents.summarizer import summarize as run_summary

    result = run_summary(_parse_duration(since))
    console.print(
        f"[bold]Summary[/bold]  window={result.window}  events={result.event_count}"
    )
    console.print(result.summary or "[dim](empty)[/dim]")
    if result.notable:
        table = Table(title=f"notable ({len(result.notable)})")
        for col in ("occurred_at", "severity", "type", "entity_ref"):
            table.add_column(col, overflow="fold")
        for item in result.notable:
            table.add_row(
                _short(item.occurred_at), item.severity, item.type, item.entity_ref or ""
            )
        console.print(table)


@app.command()
def models() -> None:
    """Show configured model roles and what's currently loaded in VRAM."""
    from jarvis.models import client

    settings = get_settings()
    roles = Table(title="model roles")
    roles.add_column("role")
    roles.add_column("ollama tag")
    roles.add_row("reasoning", settings.model_reasoning)
    roles.add_row("coder", settings.model_coder)
    roles.add_row("embedding", settings.model_embedding)
    console.print(roles)
    try:
        running = client.ps()
        console.print(f"loaded now: {', '.join(running) if running else '(none)'}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]ollama unreachable[/red] — {exc}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
