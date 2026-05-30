"""Jarvis terminal client — the payoff of the schema.

Introspection over the event spine: tail events, show projected state, inspect a row,
trace a causal chain, peek the DLQ — plus `ingest`/`consume` to run the spine. Built on
Typer + Rich. No model is involved (that arrives in M3).

Note: this module intentionally avoids `from __future__ import annotations` — Typer reads
runtime type hints to build the CLI, and stringized annotations break that.
"""


from datetime import UTC

import typer
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from jarvis import db
from jarvis.config import get_settings
from jarvis.events.models import utcnow
from jarvis.events.repository import get_event
from jarvis.events.stream import get_redis

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Jarvis CLI")
events_app = typer.Typer(no_args_is_help=True, help="Event log introspection")
state_app = typer.Typer(no_args_is_help=True, help="State projection")
metrics_app = typer.Typer(no_args_is_help=True, help="Resource metrics ingest")
topology_app = typer.Typer(no_args_is_help=True, help="Service-dependency topology")
code_app = typer.Typer(no_args_is_help=True, help="Code intelligence (index + Q&A)")
deploy_app = typer.Typer(no_args_is_help=True, help="Deployment / image-change detection")
notify_app = typer.Typer(no_args_is_help=True, help="Contextual notifications")
playbook_app = typer.Typer(no_args_is_help=True, help="Operational playbooks (procedural memory)")
inspect_app = typer.Typer(no_args_is_help=True, help="Inspect a single record")
intents_app = typer.Typer(no_args_is_help=True, help="Propose / approve / execute intents")
incidents_app = typer.Typer(no_args_is_help=True, help="Correlated alert incidents")
replay_app = typer.Typer(no_args_is_help=True, help="Replay a decision")
backup_app = typer.Typer(no_args_is_help=True, help="Backups + restore drill")
snapshot_app = typer.Typer(no_args_is_help=True, help="State snapshots (compaction / DR)")
plan_app = typer.Typer(no_args_is_help=True, help="Multi-step plans (planner + executor)")
connectors_app = typer.Typer(no_args_is_help=True, help="External connectors (read + act)")
routine_app = typer.Typer(no_args_is_help=True, help="Scheduled routines (proactive briefings)")
obs_app = typer.Typer(no_args_is_help=True, help="Observability ingest (Prometheus + Loki)")
memory_app = typer.Typer(no_args_is_help=True, help="Memory governance (list/forget/consolidate)")
kb_app = typer.Typer(no_args_is_help=True, help="Knowledge base (index runbooks/docs into memory)")
remind_app = typer.Typer(no_args_is_help=True, help="Reminders (time-based nudges → notification)")
app.add_typer(events_app, name="events")
app.add_typer(state_app, name="state")
app.add_typer(metrics_app, name="metrics")
app.add_typer(topology_app, name="topology")
app.add_typer(code_app, name="code")
app.add_typer(deploy_app, name="deploy")
app.add_typer(notify_app, name="notify")
app.add_typer(playbook_app, name="playbook")
app.add_typer(inspect_app, name="inspect")
app.add_typer(intents_app, name="intents")
app.add_typer(incidents_app, name="incidents")
app.add_typer(replay_app, name="replay")
app.add_typer(backup_app, name="backup")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(plan_app, name="plan")
app.add_typer(connectors_app, name="connectors")
app.add_typer(routine_app, name="routine")
app.add_typer(obs_app, name="obs")
app.add_typer(memory_app, name="memory")
app.add_typer(kb_app, name="kb")
app.add_typer(remind_app, name="remind")

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
    from jarvis.audit.log import record
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        result = service.approve(conn, intent_id)
        record(conn, actor="cli", action="intent.approve", target=intent_id)
        _print_intent(result)


@intents_app.command("reject")
def intents_reject(intent_id: str) -> None:
    from jarvis.audit.log import record
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        result = service.reject(conn, intent_id)
        record(conn, actor="cli", action="intent.reject", target=intent_id)
        _print_intent(result)


@intents_app.command("preview")
def intents_preview(intent_id: str) -> None:
    """Show what an intent WOULD change before approving (universal preview/diff)."""
    from jarvis.core.governance import preview_intent

    with db.connect() as conn:
        try:
            result = preview_intent(conn, intent_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
    console.print(JSON(__import__("json").dumps(result, default=str)))


@intents_app.command("execute")
def intents_execute(intent_id: str) -> None:
    """Execute an intent through the approval + mode gate (dry-run under observe)."""
    from jarvis.audit.log import record
    from jarvis.core.modes import get_mode
    from jarvis.intents import service

    with db.connect(autocommit=True) as conn:
        mode = get_mode(conn).value
        try:
            execution = service.execute(conn, intent_id)
        except (service.ApprovalRequired, service.ModeBlocked) as exc:
            record(conn, actor="cli", action="intent.execute.blocked", target=intent_id,
                   reason=str(exc))
            console.print(f"[yellow]blocked[/yellow] — {exc}")
            raise typer.Exit(code=1) from exc
        record(conn, actor="cli", action="intent.execute", target=intent_id,
               outcome=execution.outcome.value, mode=mode)
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


@code_app.command("propose-edit")
def code_propose_edit(request: str) -> None:
    """Propose a config-file edit as an intent (gated). Apply via `intents approve/execute`."""
    import difflib

    from jarvis.agents.code_editor import propose_edit
    from jarvis.ingest.code_index import _read_file

    intent = propose_edit(request)
    r = intent.reasoning
    console.print(
        f"[bold]{intent.intent_id}[/bold]  {intent.type}  status={intent.status.value}  "
        f"risk={r.risk.value} confidence={r.confidence} approval={intent.requires_approval}"
    )
    console.print(f"  target: {intent.target['path']}")
    console.print(f"  summary: {r.summary}")

    current = _read_file(get_settings().remote_ssh, intent.target["path"],
                         get_settings().code_max_file_bytes)
    diff = difflib.unified_diff(
        current.splitlines(), intent.target["new_content"].splitlines(),
        fromfile="current", tofile="proposed", lineterm="",
    )
    console.print("\n[bold]proposed diff:[/bold]")
    for line in diff:
        color = "green" if line.startswith("+") else "red" if line.startswith("-") else "dim"
        console.print(f"[{color}]{line}[/{color}]")
    console.print(
        f"\n[dim]apply: jarvis intents approve {intent.intent_id} ; "
        f"JARVIS_MODE=assist jarvis intents execute {intent.intent_id}[/dim]"
    )


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


@deploy_app.command("detect")
def deploy_detect() -> None:
    """Detect container image changes since the last run; emit container.deployed events."""
    from jarvis.ingest.deploy import detect_deployments

    count = detect_deployments()
    console.print(f"deployments detected: {count}")


@deploy_app.command("show")
def deploy_show() -> None:
    """Show the current per-container image baseline."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT entity, image, updated_at FROM container_images ORDER BY entity"
        ).fetchall()
    table = Table(title=f"container images ({len(rows)})")
    for col in ("entity", "image", "updated_at"):
        table.add_column(col, overflow="fold")
    for r in rows:
        table.add_row(r["entity"], r["image"], _short(r["updated_at"]))
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


@notify_app.command("run")
def notify_run(once: bool = typer.Option(False, help="Process one batch then exit")) -> None:
    """Run the notifier: push notify-worthy events (incidents, critical) to the webhook."""
    from jarvis.notify.notifier import run_notifier

    run_notifier(once=once)


@notify_app.command("test")
def notify_test() -> None:
    """Send a test notification through the configured channel."""
    from jarvis.notify.channel import send

    url = get_settings().notify_webhook_url or "(unset — log only)"
    sent = send(title="Jarvis test", message="notification channel check", priority="default")
    console.print(f"channel={url}  delivered={sent}")


@playbook_app.command("add")
def playbook_add(
    title: str,
    procedure: str,
    when: str = typer.Option("", "--when", help="When this playbook applies (matching basis)"),
) -> None:
    """Add an operational playbook (procedural memory the agent can retrieve)."""
    from jarvis.models import router
    from jarvis.playbooks.models import Playbook
    from jarvis.playbooks.repository import add_playbook

    pb = Playbook(title=title, when_to_use=when, procedure=procedure)
    vec = router.embed(f"{title}\n{when}")
    with db.connect(autocommit=True) as conn:
        add_playbook(conn, pb, vec)
    console.print(f"added playbook [bold]{pb.id}[/bold]: {title}")


@playbook_app.command("list")
def playbook_list() -> None:
    """List operational playbooks."""
    from jarvis.playbooks.repository import list_playbooks

    with db.connect() as conn:
        rows = list_playbooks(conn)
    table = Table(title=f"playbooks ({len(rows)})")
    for col in ("title", "when_to_use", "procedure", "id"):
        table.add_column(col, overflow="fold")
    for p in rows:
        table.add_row(p.title, p.when_to_use, p.procedure, p.id)
    console.print(table)


@playbook_app.command("forget")
def playbook_forget(playbook_id: str) -> None:
    """Forget (delete) a playbook by id (memory governance)."""
    from jarvis.playbooks.repository import delete_playbook

    with db.connect(autocommit=True) as conn:
        ok = delete_playbook(conn, playbook_id)
    console.print(f"{'forgot' if ok else 'no such playbook'}: {playbook_id}")


@app.command()
def predict() -> None:
    """Project metric trends toward thresholds; report anything forecast to cross soon."""
    from jarvis.ingest.predict import TrendTracker, detect_trends

    with db.connect() as conn:
        preds = detect_trends(conn, TrendTracker())
    if not preds:
        console.print("[dim]no trends approaching thresholds[/dim]")
        return
    table = Table(title=f"predictions ({len(preds)})")
    for col in ("entity", "metric", "current", "threshold", "eta_min"):
        table.add_column(col, overflow="fold")
    for p in preds:
        table.add_row(p["entity"], p["metric"], str(p["current"]),
                      str(p["threshold"]), str(p["eta_minutes"]))
    console.print(table)


@app.command()
def reactor(once: bool = typer.Option(False, help="Process one batch then exit")) -> None:
    """Ambient reactor: auto-propose gated intents on container-down events (observe-only)."""
    from jarvis.core.reactor import run_reactor

    run_reactor(once=once)


@app.command("kill")
def kill_cmd() -> None:
    """Emergency stop: flip to maintenance (freeze). Reactor/executor halt within a cycle."""
    from jarvis.audit.log import record
    from jarvis.core.modes import Mode, get_mode, set_mode

    with db.connect(autocommit=True) as conn:
        prev = get_mode(conn).value
        set_mode(conn, Mode.maintenance)
        record(conn, actor="cli", action="kill", target="maintenance", previous=prev)
    console.print(
        f"[bold red]KILL[/bold red] — mode {prev} → [bold]maintenance[/bold]. "
        "Acting workers freeze within one cycle; restore with [bold]jarvis mode <mode>[/bold]."
    )


@app.command("mode")
def mode_cmd(
    set_to: str = typer.Argument(
        None, metavar="[MODE]", help="observe|approval_required|semi_autonomous|maintenance"
    ),
) -> None:
    """Show the current operational mode, or set it (persisted; the daemon picks it up live)."""
    from jarvis.core.modes import Mode, get_mode, set_mode

    with db.connect(autocommit=True) as conn:
        if set_to is None:
            console.print(f"mode: [bold]{get_mode(conn).value}[/bold]")
            return
        try:
            new = Mode(set_to)
        except ValueError as exc:
            raise typer.BadParameter(
                f"unknown mode {set_to!r}; choose: {[m.value for m in Mode]}"
            ) from exc
        set_mode(conn, new)
        from jarvis.audit.log import record
        record(conn, actor="cli", action="mode.set", target=new.value)
        console.print(f"mode set to [bold]{new.value}[/bold]")


@app.command("self")
def self_cmd() -> None:
    """Self-observability: worker liveness, DLQ/stream, inference latency, reachability."""
    from jarvis.ops.health import health

    h = health()
    status = "[red]DEGRADED[/red]" if h["degraded"] else "[green]healthy[/green]"
    console.print(f"jarvis: {status}")
    w = h["workers"]
    console.print(f"  workers alive: {len(w['alive'])}/{len(w['expected'])}"
                  + (f"  [red]missing: {', '.join(w['missing'])}[/red]" if w["missing"] else ""))
    console.print("  reachable: " + "  ".join(
        f"{k}={'ok' if v else '[red]down[/red]'}" for k, v in h["reachable"].items()))
    console.print(f"  dlq_depth={h['dlq_depth']}  stream_pending={h['stream_pending']}")
    inf = h["inference"]
    console.print(f"  inference: last={inf['last_ms']}ms avg={inf['avg_ms']}ms "
                  f"(n={inf['samples']})")


@app.command()
def audit(n: int = typer.Option(30, "-n", "--number")) -> None:
    """Show the audit timeline (who did what)."""
    from jarvis.audit.log import list_audit

    with db.connect() as conn:
        rows = list_audit(conn, n)
    table = Table(title=f"audit ({len(rows)})")
    for col in ("ts", "actor", "action", "target", "details"):
        table.add_column(col, overflow="fold")
    for r in reversed(rows):
        table.add_row(
            _short(r["ts"]), r["actor"], r["action"],
            r["target"] or "", str(r["details"]),
        )
    console.print(table)


@app.command()
def run() -> None:
    """Run the whole spine: ingest+consume+metrics+notify+reactor+topology+deploy."""
    from jarvis.core.supervisor import run as run_supervisor

    run_supervisor()


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host (default from config)"),
    port: int | None = typer.Option(None, help="Bind port (default from config)"),
) -> None:
    """Start the conversational gateway (FastAPI + WebSocket). Local homelab only."""
    import uvicorn

    s = get_settings()
    bind_host, bind_port = host or s.gateway_host, port or s.gateway_port
    auth = "token-required" if s.gateway_token else "OPEN dev-mode (no token)"
    console.print(
        f"gateway → http://{bind_host}:{bind_port}  "
        f"ws://{bind_host}:{bind_port}/ws  [{auth}]"
    )
    uvicorn.run("jarvis.gateway.app:app", host=bind_host, port=bind_port, log_level="info")


def _render_plan(plan) -> None:  # noqa: ANN001 — Plan, kept loose to avoid a CLI import cycle
    console.print(
        f"plan [bold]{plan.plan_id}[/bold]  status=[bold]{plan.status.value}[/bold]  "
        f"goal: {plan.goal}"
    )
    table = Table(title=f"{len(plan.steps)} steps")
    for col in ("id", "kind", "capability", "target", "depends_on", "status", "outcome"):
        table.add_column(col, overflow="fold")
    for s in plan.steps:
        table.add_row(
            s.id, s.kind.value, s.capability, str(s.target),
            ",".join(s.depends_on), s.status.value, s.outcome or "",
        )
    console.print(table)


@plan_app.command("make")
def plan_make(
    goal: str,
    run: bool = typer.Option(False, "--run", help="Execute the plan after building it"),
    simulate: bool = typer.Option(False, "--simulate", help="Preview actions; touch nothing"),
) -> None:
    """Plan a multi-step goal (one inference → validated DAG); optionally run or simulate it."""
    from jarvis.core import planner
    from jarvis.core.plan_executor import execute_plan

    try:
        plan = planner.plan(goal)
    except planner.PlanRejected as exc:
        console.print(f"[red]plan rejected[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if run or simulate:
        plan = execute_plan(plan.plan_id, simulate=simulate)
    _render_plan(plan)


@plan_app.command("run")
def plan_run(
    plan_id: str,
    simulate: bool = typer.Option(False, "--simulate", help="Preview actions; touch nothing"),
) -> None:
    """Execute (or simulate) a previously-built plan by id."""
    from jarvis.core.plan_executor import execute_plan

    _render_plan(execute_plan(plan_id, simulate=simulate))


@plan_app.command("show")
def plan_show(n: int = typer.Option(10, "-n", "--number")) -> None:
    """List recent plans."""
    from jarvis.orchestration.repository import list_plans

    with db.connect() as conn:
        plans = list_plans(conn, n)
    table = Table(title=f"plans ({len(plans)})")
    for col in ("plan_id", "status", "steps", "goal", "created_at"):
        table.add_column(col, overflow="fold")
    for p in plans:
        table.add_row(p.plan_id, p.status.value, str(len(p.steps)), p.goal, _short(p.created_at))
    console.print(table)


@connectors_app.command("list")
def connectors_list() -> None:
    """Show registered connectors (read) and connector act-Tools (gated)."""
    import jarvis.connectors  # noqa: F401 — register act-Tools + connectors
    from jarvis.connectors.base import connectors as read_connectors
    from jarvis.tools.registry import capabilities

    s = get_settings()
    console.print(f"enabled: [bold]{', '.join(s.connectors_enabled) or '(none)'}[/bold]")
    console.print(f"read connectors: {', '.join(read_connectors()) or '(none)'}")
    act = [c for c in capabilities() if c.split(".", 1)[0] in {"mail", "ha", "calendar"}]
    console.print(f"act-Tools: {', '.join(act) or '(none)'}")


@connectors_app.command("poll")
def connectors_poll(name: str = typer.Argument(..., help="feeds|mail")) -> None:
    """Run one ingest pass for a connector now."""
    import jarvis.connectors  # noqa: F401
    from jarvis.connectors.base import get_connector

    connector = get_connector(name)
    if connector is None:
        console.print(f"[red]unknown connector[/red] {name}")
        raise typer.Exit(code=1)
    count = connector.ingest(once=True)
    console.print(f"{name}: emitted [bold]{count}[/bold] events")


@routine_app.command("add")
def routine_add(
    name: str,
    daily: str = typer.Option(None, help="Daily at HH:MM (UTC), e.g. 07:30"),
    every: int = typer.Option(None, help="Interval seconds (alternative to --daily)"),
    action: str = typer.Option("briefing", help="briefing|summary|search"),
    hours: int = typer.Option(12, help="Window for briefing/summary"),
    query: str = typer.Option("", help="Query for the search action"),
) -> None:
    """Add a scheduled routine (proactive briefing/summary/search)."""
    from jarvis.routines.models import Action, Routine, Schedule
    from jarvis.routines.repository import insert_routine

    if daily:
        schedule = Schedule(kind="daily", at=daily)
    elif every:
        schedule = Schedule(kind="interval", seconds=every)
    else:
        raise typer.BadParameter("provide --daily HH:MM or --every SECONDS")
    routine = Routine(
        name=name, schedule=schedule,
        action=Action(kind=action, hours=hours, query=query),
    )
    with db.connect(autocommit=True) as conn:
        insert_routine(conn, routine)
    console.print(f"added routine [bold]{routine.name}[/bold] ({routine.id})")


@routine_app.command("list")
def routine_list() -> None:
    """List configured routines."""
    from jarvis.routines.repository import list_routines

    with db.connect() as conn:
        routines = list_routines(conn)
    table = Table(title=f"routines ({len(routines)})")
    for col in ("id", "name", "schedule", "action", "enabled", "last_run"):
        table.add_column(col, overflow="fold")
    for r in routines:
        sched = r.schedule.at if r.schedule.kind.value == "daily" else f"{r.schedule.seconds}s"
        table.add_row(
            r.id, r.name, f"{r.schedule.kind.value} {sched}", r.action.kind.value,
            str(r.enabled), _short(r.last_run) if r.last_run else "—",
        )
    console.print(table)


@routine_app.command("run")
def routine_run(routine_id: str) -> None:
    """Run a routine now (ignores schedule)."""
    from jarvis.routines.repository import get_routine
    from jarvis.routines.scheduler import run_routine

    with db.connect() as conn:
        routine = get_routine(conn, routine_id)
    if routine is None:
        console.print(f"[red]no routine[/red] {routine_id}")
        raise typer.Exit(code=1)
    text = run_routine(routine, notify=False)
    console.print(f"[bold]{routine.name}[/bold]:\n{text}")


@memory_app.command("list")
def memory_list(
    kind: str = typer.Option(None, help="Filter by kind (e.g. summary)"),
    n: int = typer.Option(20, "-n", "--number"),
) -> None:
    """List stored memories/summaries."""
    from jarvis.memory.governance import list_memories

    with db.connect() as conn:
        rows = list_memories(conn, kind=kind, limit=n)
    table = Table(title=f"memory ({len(rows)})")
    for col in ("id", "kind", "content", "ts"):
        table.add_column(col, overflow="fold")
    for r in rows:
        content = str(r["content"])
        table.add_row(r["id"], r["kind"], content[:120] + ("…" if len(content) > 120 else ""),
                      _short(r["ts"]))
    console.print(table)


@memory_app.command("forget")
def memory_forget(memory_id: str) -> None:
    """Forget (delete) a memory by id."""
    from jarvis.memory.governance import forget

    with db.connect(autocommit=True) as conn:
        ok = forget(conn, memory_id)
    console.print(f"{'forgot' if ok else 'no such memory'}: {memory_id}")


@memory_app.command("fact")
def memory_fact(
    action: str = typer.Argument(..., help="set | list | forget"),
    key: str = typer.Argument("", help="fact key (for set/forget), e.g. city"),
    value: str = typer.Argument("", help="fact value (for set), e.g. Brussels"),
) -> None:
    """Durable operator facts the agent recalls every turn (e.g. `fact set city Brussels`)."""
    from jarvis.memory.facts import forget_fact, list_facts, set_fact

    with db.connect(autocommit=True) as conn:
        if action == "set":
            if not key or not value:
                console.print("[red]set needs a key and a value[/red]")
                raise typer.Exit(1)
            fact = set_fact(conn, key, value)
            console.print(f"remembered: {fact.key} = {fact.value}")
        elif action == "forget":
            if not key:
                console.print("[red]forget needs a key[/red]")
                raise typer.Exit(1)
            ok = forget_fact(conn, key)
            console.print(f"{'forgot' if ok else 'no such fact'}: {key}")
        elif action == "list":
            facts = list_facts(conn)
            table = Table(title=f"operator facts ({len(facts)})")
            for col in ("key", "value"):
                table.add_column(col, overflow="fold")
            for f in facts:
                table.add_row(f.key, f.value)
            console.print(table)
        else:
            console.print(f"[red]unknown action {action!r} (use set|list|forget)[/red]")
            raise typer.Exit(1)


@memory_app.command("consolidate")
def memory_consolidate(
    kind: str = typer.Option("summary", help="Which kind to consolidate"),
    keep: int = typer.Option(5, help="Keep this many newest; compact the rest"),
) -> None:
    """Compact older memories of a kind into one higher-level summary."""
    from jarvis.memory.governance import consolidate

    with db.connect(autocommit=True) as conn:
        report = consolidate(conn, kind=kind, keep_recent=keep)
    if not report["consolidated"]:
        console.print("[yellow]nothing to consolidate[/yellow] (need ≥2 older records)")
        return
    console.print(f"consolidated [bold]{report['consolidated']}[/bold] → {report['new_id']}")
    console.print(f"\n[bold]{report['summary']}[/bold]")


@remind_app.command("add")
def remind_add(
    text: str,
    in_: str = typer.Option("", "--in", help="relative: 90s, 30m, 2h, 1d"),
    at: str = typer.Option("", "--at", help="absolute ISO 8601 UTC, e.g. 2026-05-31T09:00:00Z"),
) -> None:
    """Schedule a reminder (fired via the notifier when due)."""
    from datetime import datetime

    from jarvis.events.models import utcnow
    from jarvis.reminders import add_reminder

    if at:
        due = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
    elif in_:
        due = utcnow() + _parse_duration(in_)
    else:
        raise typer.BadParameter("give --in or --at")
    with db.connect(autocommit=True) as conn:
        rem = add_reminder(conn, text, due)
    console.print(f"reminder [bold]{rem.id}[/bold] set for {rem.due_at.isoformat()}")


@remind_app.command("list")
def remind_list(all_: bool = typer.Option(False, "--all", help="include fired")) -> None:
    """List pending (or all) reminders."""
    from jarvis.reminders import list_reminders

    with db.connect() as conn:
        rems = list_reminders(conn, pending_only=not all_)
    table = Table(title=f"reminders ({len(rems)})")
    for col in ("id", "due_at", "fired", "text"):
        table.add_column(col, overflow="fold")
    for r in rems:
        table.add_row(r.id, _short(r.due_at), str(r.fired), r.text)
    console.print(table)


@remind_app.command("fire")
def remind_fire() -> None:
    """Fire all due reminders now (one pass) — what the daemon worker does on a loop."""
    from jarvis.reminders import fire_due

    with db.connect(autocommit=True) as conn:
        n = fire_due(conn)
    console.print(f"fired [bold]{n}[/bold] due reminder(s)")


@obs_app.command("prometheus")
def obs_prometheus() -> None:
    """Run one Prometheus scrape now (samples configured PromQL into `metrics`)."""
    from jarvis.ingest.prometheus import scrape_once

    count = scrape_once()
    console.print(f"prometheus: sampled [bold]{count}[/bold] series")


@obs_app.command("loki")
def obs_loki() -> None:
    """Run one Loki scan now (emits a log.spike event per over-threshold query)."""
    from jarvis.ingest.loki import scan_once

    spikes = scan_once()
    console.print(f"loki: [bold]{spikes}[/bold] spike event(s)")


@app.command()
def feedback(
    target_id: str,
    up: bool = typer.Option(False, "--up", help="👍 (default 👎 if omitted)"),
    target_type: str = typer.Option("intent", help="intent|incident|plan|routine"),
    note: str = typer.Option("", help="Optional note"),
) -> None:
    """Rate a proposal/incident 👍/👎 (the adaptive-attention signal)."""
    from jarvis import feedback as fb

    with db.connect(autocommit=True) as conn:
        try:
            fb.record(conn, target_type=target_type, target_id=target_id,
                      rating=1 if up else -1, actor="cli", note=note or None)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        s = fb.score(conn, target_type=target_type, target_id=target_id)
    console.print(f"recorded {'👍' if up else '👎'} on {target_type}:{target_id} (net score {s})")


@kb_app.command("index")
def kb_index(path: str = typer.Argument(None, help="Remote dir/file (default: KB_PATHS)")) -> None:
    """Index runbooks/notes/docs (markdown/text) over SSH into memory (kind=kb)."""
    from jarvis.ingest.kb import index_kb

    n = index_kb(paths=[path] if path else None)
    console.print(f"indexed [bold]{n}[/bold] doc chunks into memory")


@kb_app.command("search")
def kb_search(query: str, k: int = typer.Option(5, "-k")) -> None:
    """Retrieve KB chunks relevant to a query."""
    from jarvis.ingest.kb import search_kb

    hits = search_kb(query, k=k)
    if not hits:
        console.print("[yellow]no KB matches[/yellow]")
        return
    for i, h in enumerate(hits, 1):
        console.print(f"[teal]{i}.[/teal] {h[:300]}")


@app.command("deferred")
def deferred_cmd(
    drain: bool = typer.Option(False, "--drain", help="Replay deferred reasoning now (if LLM up)"),
) -> None:
    """Reasoning deferred while the LLM was down (graceful degradation). --drain to replay."""
    from jarvis.core.degrade import _default_handlers, pending, reasoning_available
    from jarvis.core.degrade import drain as drain_fn

    if drain:
        with db.connect(autocommit=True) as conn:
            n = drain_fn(conn, _default_handlers())
        up = "up" if reasoning_available() else "down"
        console.print(f"replayed [bold]{n}[/bold] (reasoning {up})")
        return
    with db.connect() as conn:
        rows = pending(conn)
    table = Table(title=f"deferred reasoning ({len(rows)})")
    for col in ("id", "kind", "payload", "attempts"):
        table.add_column(col, overflow="fold")
    for r in rows:
        table.add_row(r["id"], r["kind"], str(r["payload"]), str(r["attempts"]))
    console.print(table)


@app.command("state-at")
def state_at_cmd(ago: str = typer.Argument(..., help="How far back, e.g. 12h, 30m, 2d")) -> None:
    """Reconstruct the state projection as it stood `ago` ago (time-travel over the event log)."""
    from jarvis.state.timetravel import state_at

    ts = utcnow() - _parse_duration(ago)
    with db.connect() as conn:
        snap = state_at(conn, ts)
    table = Table(title=f"state as of {_short(ts)} ({len(snap)} entities)")
    for col in ("entity", "status", "last_action"):
        table.add_column(col, overflow="fold")
    for entity in sorted(snap):
        row = snap[entity]
        table.add_row(entity, row.get("status") or "", str(row["attrs"].get("last_action", "")))
    console.print(table)


@app.command("diff")
def diff_cmd(
    since: str = typer.Argument(..., help="Start point, e.g. 24h"),
    until: str = typer.Option("0m", help="End point (default: now)"),
) -> None:
    """What changed between two points in time (added/removed/status changes)."""
    from jarvis.state.timetravel import diff

    now = utcnow()
    t1, t2 = now - _parse_duration(since), now - _parse_duration(until)
    with db.connect() as conn:
        d = diff(conn, t1, t2)
    console.print(f"[teal]added[/teal]: {', '.join(d['added']) or '—'}")
    console.print(f"[red]removed[/red]: {', '.join(d['removed']) or '—'}")
    if d["changed"]:
        console.print("[amber]changed[/amber]:")
        for entity, ch in d["changed"].items():
            a, b = ch["status"]
            console.print(f"  {entity}: {a} → {b}")
    else:
        console.print("changed: —")


@app.command("plugins")
def plugins_cmd() -> None:
    """Load external tool plugins from PLUGINS_DIR and list the capabilities they register."""
    from jarvis.plugins.loader import load_plugins

    loaded = load_plugins()
    console.print(f"loaded plugins: [bold]{', '.join(loaded) or '(none)'}[/bold]")


@app.command("cache")
def cache_cmd() -> None:
    """Show the embedding cache stats (cost-aware caching)."""
    from jarvis.models.cache import enabled, get_cache

    s = get_cache().stats()
    console.print(
        f"embedding cache [{'on' if enabled() else 'off'}]: "
        f"size {s['size']}/{s['capacity']} · hits {s['hits']} · misses {s['misses']} · "
        f"hit-rate {s['hit_rate']}"
    )


@app.command("anomaly")
def anomaly_cmd() -> None:
    """Scan metrics for self-anomalies (z-score over each metric's own history) once."""
    from jarvis.ingest.anomaly import scan_once

    console.print(f"flagged [bold]{scan_once()}[/bold] metric anomaly(ies)")


@app.command("postmortem")
def postmortem_cmd(
    incident_id: str,
    adopt: bool = typer.Option(False, "--adopt", help="Also codify the suggested playbook"),
) -> None:
    """Generate a postmortem for an incident (and optionally adopt the suggested playbook)."""
    from jarvis.agents.postmortem import adopt_playbook, generate

    try:
        pm = generate(incident_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold]{pm.as_text()}[/bold]")
    console.print(f"\n[teal]Suggested playbook:[/teal] {pm.playbook_title}")
    console.print(f"  when: {pm.playbook_when}")
    console.print(f"  procedure: {pm.playbook_procedure}")
    if adopt:
        pid = adopt_playbook(pm)
        console.print(
            f"\nadopted playbook → [bold]{pid}[/bold]" if pid
            else "\n[yellow]no playbook to adopt[/yellow]"
        )


@app.command("verify")
def verify_cmd(
    show: bool = typer.Option(False, "--show", help="List recent verifications instead of running"),
) -> None:
    """Outcome verification: did past actions actually work? (run a pass, or --show recent)."""
    if show:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT created_at, subject_id, status, detail FROM verifications "
                "ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
        table = Table(title=f"verifications ({len(rows)})")
        for col in ("created_at", "subject_id", "status", "detail"):
            table.add_column(col, overflow="fold")
        for r in rows:
            tone = {"verified": "green", "unverified": "red"}.get(r["status"], "yellow")
            table.add_row(_short(r["created_at"]), r["subject_id"],
                          f"[{tone}]{r['status']}[/{tone}]", r["detail"] or "")
        console.print(table)
        return
    from jarvis.verify.runner import run_once

    console.print(f"verified [bold]{run_once()}[/bold] execution(s)")


@app.command("eval")
def eval_cmd(
    limit: int = typer.Option(5, help="How many recent agent proposals to replay"),
    intent_id: str = typer.Option(None, help="Replay a single intent instead"),
) -> None:
    """Replay stored decisions through the current model and report drift (regression gate)."""
    from jarvis.eval.harness import recent_proposer_intents, run_suite

    ids_to_run = [intent_id] if intent_id else recent_proposer_intents(limit)
    if not ids_to_run:
        console.print("[yellow]no replayable agent proposals found[/yellow]")
        return
    report = run_suite(ids_to_run)
    title = f"eval — {report.drifted}/{report.total} drifted (rate {report.drift_rate})"
    table = Table(title=title)
    for col in ("intent_id", "orig→replayed", "type Δ", "target Δ", "conf Δ", "drift"):
        table.add_column(col, overflow="fold")
    for r in report.results:
        table.add_row(
            r.intent_id, f"{r.original_type}→{r.replayed_type}",
            "yes" if r.type_changed else "—", "yes" if r.target_changed else "—",
            f"{r.confidence_delta:+.2f}", "[red]DRIFT[/red]" if r.drift else "ok",
        )
    console.print(table)


@app.command()
def search(
    query: str,
    raw: bool = typer.Option(False, help="Show raw results, skip synthesis"),
) -> None:
    """Web RAG search (SearXNG): cited answer, or --raw for the source list."""
    from jarvis.search.rag import synthesize, web_search

    try:
        results = web_search(query)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]search failed[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if not results:
        console.print("[yellow]no results[/yellow]")
        return
    table = Table(title=f"sources ({len(results)})")
    for col in ("#", "title", "url"):
        table.add_column(col, overflow="fold")
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r.title, r.url)
    console.print(table)
    if not raw:
        console.print(f"\n[bold]{synthesize(query, results)}[/bold]")


@app.command()
def capture(url: str, out: str = typer.Option("capture.png", help="Output PNG path")) -> None:
    """Screenshot a page (egress-allowlisted) → a PNG file."""
    import base64

    from jarvis.search.capture import screenshot

    try:
        result = screenshot(url)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]capture failed[/red] {exc}")
        raise typer.Exit(code=1) from exc
    png = base64.b64decode(result["url"].split(",", 1)[1])
    with open(out, "wb") as fh:
        fh.write(png)
    console.print(f"captured [bold]{url}[/bold] → {out} ({len(png)} bytes)")


@backup_app.command("run")
def backup_run() -> None:
    """Back up the DB now (off-box + a remote copy), pruning to retention."""
    from jarvis.ops.backup import run_backup

    info = run_backup()
    console.print(f"backup [bold]{info['file']}[/bold]  {info['bytes']} bytes  → {info['offbox']}")


@backup_app.command("verify")
def backup_verify(
    file: str | None = typer.Option(None, "--file", help="Specific dump (default: latest)"),
) -> None:
    """DR drill: restore a dump into a scratch DB and sanity-check it."""
    from jarvis.ops.backup import verify_restore

    report = verify_restore(file)
    console.print(
        f"[green]restore OK[/green]  {report['path']}  events={report['events']}  "
        f"alembic={report['alembic_version']}"
    )


@snapshot_app.command("write")
def snapshot_write() -> None:
    """Write a state snapshot (compaction checkpoint)."""
    from jarvis.state.snapshotter import write_snapshot

    with db.connect(autocommit=True) as conn:
        snap_id = write_snapshot(conn)
    console.print(f"snapshot [bold]{snap_id}[/bold] written")


@snapshot_app.command("rebuild")
def snapshot_rebuild(
    yes: bool = typer.Option(False, "--yes", help="Confirm (rebuild truncates + replays state)"),
) -> None:
    """DR: rebuild the state projection from the latest snapshot + replayed events."""
    from jarvis.state.snapshotter import rebuild_state

    if not yes:
        console.print("[yellow]refusing without --yes[/yellow] (rebuild truncates state)")
        raise typer.Exit(code=1)
    with db.connect(autocommit=True) as conn:
        result = rebuild_state(conn)
    console.print(
        f"rebuilt state: {result['restored_rows']} rows "
        f"+ {result['replayed_events']} replayed events"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
