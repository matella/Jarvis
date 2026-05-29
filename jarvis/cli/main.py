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
metrics_app = typer.Typer(no_args_is_help=True, help="Resource metrics ingest")
topology_app = typer.Typer(no_args_is_help=True, help="Service-dependency topology")
code_app = typer.Typer(no_args_is_help=True, help="Code intelligence (index + Q&A)")
inspect_app = typer.Typer(no_args_is_help=True, help="Inspect a single record")
intents_app = typer.Typer(no_args_is_help=True, help="Propose / approve / execute intents")
incidents_app = typer.Typer(no_args_is_help=True, help="Correlated alert incidents")
replay_app = typer.Typer(no_args_is_help=True, help="Replay a decision")
app.add_typer(events_app, name="events")
app.add_typer(state_app, name="state")
app.add_typer(metrics_app, name="metrics")
app.add_typer(topology_app, name="topology")
app.add_typer(code_app, name="code")
app.add_typer(inspect_app, name="inspect")
app.add_typer(intents_app, name="intents")
app.add_typer(incidents_app, name="incidents")
app.add_typer(replay_app, name="replay")

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


def _print_intent(intent) -> None:
    r = intent.reasoning
    console.print(
        f"[bold]{intent.intent_id}[/bold]  {intent.type}  status={intent.status.value}"
    )
    console.print(
        f"  risk={r.risk.value} confidence={r.confidence} reversible={r.reversible} "
        f"requires_approval={intent.requires_approval}"
    )
    console.print(f"  target={intent.target}")
    console.print(f"  summary: {r.summary}")
    console.print(f"  correlation_id={intent.correlation_id}  context_ref={intent.context_ref}")


@intents_app.command("propose")
def intents_propose(entity: str) -> None:
    """Run the infrastructure agent over an entity and persist a proposed intent."""
    from jarvis.agents.infrastructure import propose_intent

    _print_intent(propose_intent(entity))


@intents_app.command("list")
def intents_list(n: int = typer.Option(20, "-n", "--number")) -> None:
    """List recent intents."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT intent_id, created_at, type, status, requires_approval, "
            "reasoning->>'risk' AS risk, reasoning->>'confidence' AS confidence "
            "FROM intents ORDER BY intent_id DESC LIMIT %s",
            (n,),
        ).fetchall()
    table = Table(title=f"intents (last {len(rows)})")
    for col in ("created_at", "type", "status", "risk", "conf", "approval?", "intent_id"):
        table.add_column(col, overflow="fold")
    for row in reversed(rows):
        table.add_row(
            _short(row["created_at"]), row["type"], row["status"], row["risk"] or "",
            row["confidence"] or "", str(row["requires_approval"]), row["intent_id"],
        )
    console.print(table)


@intents_app.command("approve")
def intents_approve(intent_id: str) -> None:
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        _print_intent(service.approve(conn, intent_id))


@intents_app.command("reject")
def intents_reject(intent_id: str) -> None:
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        _print_intent(service.reject(conn, intent_id))


@intents_app.command("execute")
def intents_execute(intent_id: str) -> None:
    """Execute an intent through the approval + mode gate (dry-run under observe)."""
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        try:
            execution = service.execute(conn, intent_id)
        except service.ApprovalRequired as exc:
            console.print(f"[yellow]blocked[/yellow] — {exc}")
            raise typer.Exit(code=1) from exc
    mode = get_settings().jarvis_mode
    console.print(
        f"[bold]execution[/bold] {execution.exec_id}  outcome={execution.outcome.value}  "
        f"mode={mode}"
    )
    console.print(f"  before={execution.before_state}  after={execution.after_state}")
    if execution.error:
        console.print(f"  [red]error[/red] ({execution.failure_class}): {execution.error}")
    console.print(f"  correlation_id={execution.correlation_id}")


@inspect_app.command("intent")
def inspect_intent(intent_id: str) -> None:
    """Print a single intent row in full."""
    from jarvis.intents.repository import get_intent

    with db.connect() as conn:
        intent = get_intent(conn, intent_id)
    if intent is None:
        console.print(f"[red]no intent[/red] {intent_id}")
        raise typer.Exit(code=1)
    console.print(JSON(intent.model_dump_json()))


@app.command()
def explain(intent_id: str) -> None:
    """Show the stored context (prompt + model/params) that produced an intent."""
    from jarvis.core.context_store import get_context
    from jarvis.intents.repository import get_intent

    with db.connect() as conn:
        intent = get_intent(conn, intent_id)
        if intent is None:
            console.print(f"[red]no intent[/red] {intent_id}")
            raise typer.Exit(code=1)
        ctx = get_context(conn, intent.context_ref) if intent.context_ref else None

    _print_intent(intent)
    console.print()
    if ctx is None:
        console.print("[yellow]no stored context for this intent[/yellow]")
        return
    console.print(f"[bold]context[/bold] {ctx.context_ref}  model={ctx.model}  params={ctx.params}")
    console.print(ctx.prompt)


@replay_app.command("intent")
def replay_intent(intent_id: str) -> None:
    """Re-run the model on the stored context and diff against the original decision."""
    from jarvis.agents.infrastructure import replay

    result = replay(intent_id)
    console.print(f"[bold]replay[/bold] {intent_id}  context_ref={result['context_ref']}")
    console.print(f"  original : {result['original']}")
    console.print(f"  replayed : {result['replayed']}")
    console.print(
        f"  type matches original: {result['matches_type']} "
        "[dim](inference is non-deterministic; differences are expected)[/dim]"
    )


@metrics_app.command("run")
def metrics_run(once: bool = typer.Option(False, help="Sample one cycle then exit")) -> None:
    """Poll docker stats + GPU into the metrics table; emit threshold signal events."""
    from jarvis.ingest.metrics import run_poller

    run_poller(once=once)


@metrics_app.command("show")
def metrics_show(
    kind: str | None = typer.Option(None, help="Filter: container | gpu"),
) -> None:
    """Show the latest sample per entity."""
    from jarvis.ingest.metrics_store import latest_per_entity

    with db.connect() as conn:
        rows = latest_per_entity(conn, kind)

    table = Table(title=f"metrics ({len(rows)} entities)")
    for col in ("entity", "kind", "key stats", "ts"):
        table.add_column(col, overflow="fold")
    for row in sorted(rows, key=lambda r: r["entity"]):
        sample = row["sample"]
        if row["kind"] == "container":
            stats = f"cpu={sample.get('cpu_pct')}% mem={sample.get('mem_pct')}%"
        else:
            stats = (
                f"util={sample.get('util_pct')}% mem={sample.get('mem_pct')}% "
                f"temp={sample.get('temp_c')}C"
            )
        table.add_row(row["entity"], row["kind"], stats, _short(row["ts"]))
    console.print(table)


@topology_app.command("build")
def topology_build() -> None:
    """Derive the service-dependency graph from docker inspect and store it."""
    from jarvis.ingest.topology import build_topology

    count = build_topology()
    console.print(f"topology built: {count} edges")


@topology_app.command("show")
def topology_show() -> None:
    """Show the current topology edges."""
    from jarvis.ingest.topology import all_edges

    with db.connect() as conn:
        edges = all_edges(conn)
    table = Table(title=f"topology ({len(edges)} edges)")
    for col in ("src", "relation", "dst"):
        table.add_column(col, overflow="fold")
    for src, dst, rel in edges:
        table.add_row(src, rel, dst)
    console.print(table)


@code_app.command("index")
def code_index() -> None:
    """Index the configured repo (over SSH) into the code vector store."""
    from jarvis.ingest.code_index import index_repo

    count = index_repo()
    console.print(f"indexed {count} chunks from {get_settings().code_repo_name}")


@code_app.command("ask")
def code_ask(question: str) -> None:
    """Ask the coder model a question grounded in the indexed code."""
    from jarvis.agents.coder import ask

    result = ask(question)
    console.print(result.answer)
    if result.sources:
        console.print("\n[dim]sources:[/dim] " + ", ".join(result.sources))


@code_app.command("search")
def code_search(
    query: str, n: int = typer.Option(6, "-n", "--number")
) -> None:
    """Show the code chunks most relevant to a query (retrieval only, no model)."""
    from jarvis.ingest.code_index import search_chunks
    from jarvis.models import router

    query_vec = router.embed(query)
    with db.connect() as conn:
        hits = search_chunks(conn, query_vec, k=n)
    table = Table(title=f"code search ({len(hits)} hits)")
    for col in ("path:lines", "distance", "first line"):
        table.add_column(col, overflow="fold")
    for path, start, end, content, distance in hits:
        first = content.splitlines()[0] if content else ""
        table.add_row(f"{path}:{start}-{end}", f"{distance:.3f}", first[:80])
    console.print(table)


@app.command()
def journal(
    since: str = typer.Option("24h", "--since", help="Window: 24h, 12h, 2d"),
) -> None:
    """Show a curated operational timeline (incidents, intents/executions, alerts)."""
    from jarvis.core.journal import build_journal

    with db.connect() as conn:
        entries = build_journal(conn, _parse_duration(since))
    table = Table(title=f"operational journal (since {since}, {len(entries)} entries)")
    for col in ("time", "kind", "severity", "what", "ref"):
        table.add_column(col, overflow="fold")
    for e in entries:
        table.add_row(_short(e.ts), e.kind, e.severity, e.title, e.ref)
    console.print(table)


@app.command()
def correlate(
    since: str = typer.Option("1h", "--since", help="Window: 1h, 30m, 2d"),
) -> None:
    """Correlate recent warning+ alerts into incidents (deterministic cluster + LLM root-cause)."""
    from jarvis.agents.correlator import correlate as run_correlate

    incidents = run_correlate(_parse_duration(since))
    if not incidents:
        console.print("[dim]no incidents (no alert clusters met the threshold)[/dim]")
        return
    for inc in incidents:
        console.print(
            f"[bold]{inc.incident_id}[/bold]  severity={inc.severity.value}  "
            f"events={inc.event_count}  entities={len(inc.entity_refs)}"
        )
        console.print(f"  summary: {inc.summary}")
        console.print(f"  root cause: {inc.root_cause}")


@incidents_app.command("list")
def incidents_list(n: int = typer.Option(20, "-n", "--number")) -> None:
    """List recent incidents."""
    from jarvis.incidents.repository import list_incidents

    with db.connect() as conn:
        rows = list_incidents(conn, n)
    table = Table(title=f"incidents (last {len(rows)})")
    for col in ("created_at", "severity", "events", "summary", "incident_id"):
        table.add_column(col, overflow="fold")
    for inc in reversed(rows):
        table.add_row(
            _short(inc.created_at), inc.severity.value, str(inc.event_count),
            inc.summary, inc.incident_id,
        )
    console.print(table)


@incidents_app.command("show")
def incidents_show(incident_id: str) -> None:
    """Show a single incident in full (incl. the alerts it grouped)."""
    from jarvis.incidents.repository import get_incident

    with db.connect() as conn:
        inc = get_incident(conn, incident_id)
    if inc is None:
        console.print(f"[red]no incident[/red] {incident_id}")
        raise typer.Exit(code=1)
    console.print(JSON(inc.model_dump_json()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
