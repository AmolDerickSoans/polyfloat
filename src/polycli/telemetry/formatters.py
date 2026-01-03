"""Telemetry output formatters for poly stats command."""
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

from rich.console import Console
from rich.table import Table

from .store import TelemetryStore
from .models import TelemetryEvent

console = Console()


def format_timestamp(ts: float) -> str:
    """Format timestamp as YYYY-MM-DD HH:MM:SS"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _count_by_type(events: List[TelemetryEvent]) -> Dict[str, int]:
    """Count events by type."""
    counts = defaultdict(int)
    for event in events:
        counts[event.event_type] += 1
    return dict(counts)


def _show_summary(store: TelemetryStore, since: float) -> None:
    """Show usage summary statistics."""
    cutoff = since
    all_events = store.query(filters={"since": cutoff}, limit=10000)

    if not all_events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        return

    command_counts = defaultdict(int)
    agent_proposals = 0
    approved = 0
    rejected = 0
    trade_attempted = 0
    trade_succeeded = 0
    trade_failed = 0
    sessions = set()

    for event in all_events:
        if event.event_type == "command_invoked":
            command = event.payload.get("command", "unknown")
            command_counts[command] += 1
        elif event.event_type == "agent_proposal_created":
            agent_proposals += 1
        elif event.event_type == "proposal_approved":
            approved += 1
        elif event.event_type == "proposal_rejected":
            rejected += 1
        elif event.event_type == "trade_executed":
            trade_succeeded += 1
            trade_attempted += 1
        elif event.event_type == "trade_failed":
            trade_failed += 1
            trade_attempted += 1

        sessions.add(event.session_id)

    total_commands = sum(command_counts.values())

    console.print("[bold]=== PolyFloat Usage Summary (Last 7 Days) ===[/bold]")
    console.print()

    console.print(f"[bold]Commands Invoked:[/bold] {total_commands}")
    for cmd, count in sorted(command_counts.items(), key=lambda x: -x[1])[:5]:
        pct = (count / total_commands * 100) if total_commands > 0 else 0
        console.print(f"  - {cmd}: {count} ({pct:.1f}%)")

    other_count = total_commands - sum(
        count for cmd, count in list(command_counts.items())[:5]
    )
    if other_count > 0 and total_commands > 0:
        console.print(
            f"  - other: {other_count} ({other_count/total_commands*100:.1f}%)"
        )
    console.print()

    console.print(f"[bold]Agent Proposals:[/bold] {agent_proposals}")
    if agent_proposals > 0:
        console.print(f"  - Approved: {approved} ({approved/agent_proposals*100:.1f}%)")
        console.print(f"  - Rejected: {rejected} ({rejected/agent_proposals*100:.1f}%)")
    console.print()

    console.print("[bold]Trade Execution:[/bold]")
    console.print(f"  - Attempted: {trade_attempted}")
    if trade_attempted > 0:
        console.print(
            f"  - Succeeded: {trade_succeeded} ({trade_succeeded/trade_attempted*100:.1f}%)"
        )
        console.print(
            f"  - Failed: {trade_failed} ({trade_failed/trade_attempted*100:.1f}%)"
        )
    console.print()

    console.print(f"[bold]Sessions:[/bold] {len(sessions)}")

    if len(sessions) > 0:
        session_durations = []
        for session_id in sessions:
            session_events = [e for e in all_events if e.session_id == session_id]
            if session_events:
                start_ts = min(e.timestamp for e in session_events)
                end_ts = max(e.timestamp for e in session_events)
                session_durations.append(end_ts - start_ts)

        if session_durations:
            avg_duration = sum(session_durations) / len(session_durations)
            avg_mins = avg_duration / 60
            console.print(f"Avg Session Duration: {avg_mins:.0f} min")


def _show_funnel(store: TelemetryStore, since: float) -> None:
    """Show proposal -> execution funnel."""
    cutoff = since
    all_events = store.query(filters={"since": cutoff}, limit=10000)

    if not all_events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        return

    proposals_created = 0
    proposals_approved = 0
    risk_guard_blocked = 0
    trade_executed = 0
    trade_failed = 0

    for event in all_events:
        if event.event_type == "agent_proposal_created":
            proposals_created += 1
        elif event.event_type == "proposal_approved":
            proposals_approved += 1
        elif event.event_type == "trade_executed":
            trade_executed += 1
        elif event.event_type == "trade_failed":
            stage = event.payload.get("stage", "")
            if stage == "risk_guard":
                risk_guard_blocked += 1
            trade_failed += 1

    risk_passed = max(0, proposals_approved - risk_guard_blocked)
    total = proposals_created if proposals_created > 0 else 1

    console.print(f"[bold]=== Proposal -> Execution Funnel ===[/bold]")
    console.print()

    if proposals_created > 0:
        console.print(f"[1] Proposals Created:     {proposals_created} (100%)")
    if proposals_created > 0:
        drop_approved = proposals_created - proposals_approved
        console.print(
            f"[2] Proposals Approved:    {proposals_approved} ({proposals_approved/total*100:.1f}%)  -- {drop_approved} dropped"
        )
    if proposals_created > 0:
        console.print(
            f"[3] Risk Check Passed:     {risk_passed} ({risk_passed/total*100:.1f}%)  -- {risk_guard_blocked} blocked"
        )
    if proposals_created > 0:
        trade_drop = trade_failed
        console.print(
            f"[4] Trade Executed:        {trade_executed} ({trade_executed/total*100:.1f}%)  -- {trade_drop} failed"
        )
    console.print()

    console.print("[bold]Drop-off Analysis:[/bold]")
    if proposals_created > 0:
        user_reject_pct = (
            (proposals_created - proposals_approved) / proposals_created * 100
        )
        console.print(
            f"  - User Rejection: {user_reject_pct:.1f}% ({proposals_created - proposals_approved}/{proposals_created})"
        )
        if proposals_approved > 0:
            risk_pct = risk_guard_blocked / proposals_created * 100
            console.print(
                f"  - Risk Guard: {risk_pct:.1f}% ({risk_guard_blocked}/{proposals_created})"
            )
        if risk_passed > 0:
            provider_pct = trade_failed / proposals_created * 100
            console.print(
                f"  - Provider Failure: {provider_pct:.1f}% ({trade_failed}/{proposals_created})"
            )


def _show_errors(store: TelemetryStore, since: float) -> None:
    """Show error code distribution."""
    cutoff = since
    all_events = store.query(filters={"since": cutoff}, limit=10000)

    if not all_events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        return

    risk_rejections = defaultdict(int)
    provider_failures = defaultdict(int)

    for event in all_events:
        if event.event_type == "trade_failed":
            stage = event.payload.get("stage", "")
            error_code = event.payload.get("error_code", "")
            error_type = event.payload.get("error_type", "")

            if stage == "risk_guard" or error_code.startswith("E"):
                if error_code:
                    risk_rejections[error_code] += 1
            else:
                if error_type:
                    provider_failures[error_type] += 1

    console.print(f"[bold]=== Error Analysis ===[/bold]")
    console.print()

    total_risk = sum(risk_rejections.values())
    console.print(f"[bold]RiskGuard Rejections:[/bold] {total_risk}")
    error_descriptions = {
        "E001": "Position Size",
        "E002": "Position Size %",
        "E003": "Insufficient Balance",
        "E004": "Daily Loss Limit",
        "E005": "Max Drawdown",
        "E006": "Trade Frequency (min)",
        "E007": "Trade Frequency (hr)",
        "E008": "Trading Disabled",
        "E009": "Agent Disabled",
        "E010": "Circuit Breaker",
        "E011": "Price Deviation",
    }
    for code, count in sorted(risk_rejections.items(), key=lambda x: -x[1]):
        desc = error_descriptions.get(code, "Unknown")
        console.print(f"  - {code} ({desc}): {count}")

    console.print()
    total_provider = sum(provider_failures.values())
    console.print(f"[bold]Provider Failures:[/bold] {total_provider}")
    for err_type, count in sorted(provider_failures.items(), key=lambda x: -x[1]):
        console.print(f"  - {err_type}: {count}")

    if total_risk == 0 and total_provider == 0:
        console.print("[green]No errors recorded.[/green]")


def _show_recent(store: TelemetryStore, limit: int) -> None:
    """Show recent events."""
    events = store.query(filters={}, limit=limit)

    if not events:
        console.print("[yellow]No events found.[/yellow]")
        return

    console.print(f"[bold]=== Last {limit} Events ===[/bold]")
    console.print()

    for event in events:
        ts = format_timestamp(event.timestamp)
        event_type = event.event_type
        summary = _format_event_summary(event)
        console.print(f"{ts}  {event_type:<20} {summary}")


def _format_event_summary(event: TelemetryEvent) -> str:
    """Format an event for display in recent list."""
    payload = event.payload

    if event.event_type == "command_invoked":
        return payload.get("command", "unknown")
    elif event.event_type == "trade_executed":
        side = payload.get("side", "BUY")
        amount = payload.get("amount_usd", 0)
        duration = payload.get("duration_ms", 0)
        return f"{side} ${amount} ({duration}ms)"
    elif event.event_type == "trade_failed":
        reason = payload.get("error_code", payload.get("error_type", "unknown"))
        return f"FAILED: {reason}"
    elif event.event_type == "proposal_approved":
        age = payload.get("age_seconds", 0)
        return f"{age}s old"
    elif event.event_type == "agent_proposal_created":
        agent = payload.get("agent", payload.get("agent_id", "unknown"))
        return agent
    elif event.event_type == "proposal_rejected":
        reason = payload.get("reason", "unknown")
        return f"REJECTED: {reason}"
    elif event.event_type == "risk_guard_blocked":
        error_code = payload.get("error_code", "unknown")
        return f"BLOCKED: {error_code}"
    else:
        return str(payload)[:30] if payload else ""


def _show_sessions(store: TelemetryStore, since: float) -> None:
    """Show session list with durations."""
    cutoff = since
    all_events = store.query(filters={"since": cutoff}, limit=10000)

    if not all_events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        return

    sessions = {}
    for event in all_events:
        session_id = event.session_id
        if session_id not in sessions:
            sessions[session_id] = {"first": event.timestamp, "last": event.timestamp}
        else:
            sessions[session_id]["first"] = min(
                sessions[session_id]["first"], event.timestamp
            )
            sessions[session_id]["last"] = max(
                sessions[session_id]["last"], event.timestamp
            )

    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    console.print(f"[bold]=== Sessions (Last 7 Days) ===[/bold]")
    console.print()

    sorted_sessions = sorted(sessions.items(), key=lambda x: x[1]["last"], reverse=True)

    table = Table()
    table.add_column("Session ID", style="dim")
    table.add_column("Start", style="cyan")
    table.add_column("End", style="cyan")
    table.add_column("Duration", justify="right")

    for session_id, times in sorted_sessions:
        start_str = format_timestamp(times["first"])
        end_str = format_timestamp(times["last"])
        duration_secs = times["last"] - times["first"]
        duration_mins = duration_secs / 60

        if duration_mins < 60:
            duration_str = f"{duration_mins:.0f} min"
        else:
            duration_hours = duration_mins / 60
            duration_str = f"{duration_hours:.1f} hr"

        session_short = session_id[:20] + "..." if len(session_id) > 20 else session_id
        table.add_row(session_short, start_str, end_str, duration_str)

    console.print(table)

    if len(sessions) > 0:
        total_duration = sum(s[1]["last"] - s[1]["first"] for s in sessions.items())
        avg_duration = total_duration / len(sessions)
        console.print(f"\nTotal Sessions: {len(sessions)}")
        console.print(f"Avg Session Duration: {avg_duration/60:.0f} min")
