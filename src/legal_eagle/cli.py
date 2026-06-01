"""Typer-based CLI for Legal Eagle AI.

Usage:
  legal-eagle research "your legal question here"
  legal-eagle show <session_id>
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .db import DB
from .pipeline import ResearchPipeline

app = typer.Typer(add_completion=False, help="Legal Eagle AI CLI")
console = Console()


def _render_markdown(report) -> str:
    lines: list[str] = []
    lines.append("# Legal Eagle AI — Research Report")
    lines.append(f"**Session:** `{report.session_id}`  ")
    lines.append(f"**Query:** {report.original_query}")
    lines.append("")

    if report.us_documents:
        lines.append("## US Documents")
        for d in report.us_documents:
            lines.append(f"- [{d.title}]({d.url}) — `{d.document_id}`")
        lines.append("")
    if report.eu_documents:
        lines.append("## EU Documents")
        for d in report.eu_documents:
            lines.append(f"- [{d.title}]({d.url}) — `{d.document_id}`")
        lines.append("")

    if report.us_summary:
        lines.append("## US Summary")
        lines.append(report.us_summary.summary_text or "_(no summary)_")
        lines.append("")
    if report.eu_summary:
        lines.append("## EU Summary")
        lines.append(report.eu_summary.summary_text or "_(no summary)_")
        lines.append("")

    if report.synthesis:
        s = report.synthesis
        if s.alignment_matrix:
            lines.append("## Principle Alignment Matrix")
            lines.append("| Principle | US | EU | Status |")
            lines.append("|---|---|---|---|")
            for row in s.alignment_matrix:
                lines.append(
                    f"| {row.get('principle', '')} | {row.get('us_position', '')} | "
                    f"{row.get('eu_position', '')} | {row.get('status', '')} |"
                )
            lines.append("")
        if s.eurovoc_bridge:
            lines.append("## EuroVoc ↔ US Bridge (v1.1)")
            for b in s.eurovoc_bridge:
                lines.append(
                    f"- **{b.get('eurovoc_label', '')}** → {b.get('us_concept', '')} "
                    f"(confidence {b.get('confidence', 0):.2f}) — {b.get('rationale', '')}"
                )
            lines.append("")
        if s.eurovoc_hierarchy:
            lines.append("## EuroVoc Hierarchies Consulted")
            for h in s.eurovoc_hierarchy[:10]:
                if not h.get("found"):
                    continue
                broader = ", ".join(h.get("broader") or [])
                narrower = ", ".join(h.get("narrower") or [])
                lines.append(
                    f"- **{h.get('concept')}** (uri: {h.get('uri', 'n/a')})\n"
                    f"  - broader: {broader or '(none)'}\n"
                    f"  - narrower: {narrower or '(none)'}"
                )
            lines.append("")
        if s.divergences:
            lines.append("## Divergences")
            for d in s.divergences:
                lines.append(
                    f"- **{d.get('topic', '')}** — US: {d.get('us_view', '')}; "
                    f"EU: {d.get('eu_view', '')}; Implication: {d.get('implication', '')}"
                )
            lines.append("")
        if s.similar_precedents:
            lines.append("## Similar Precedents")
            for p in s.similar_precedents:
                lines.append(
                    f"- US `{p.get('us_doc_id', '')}` ↔ EU `{p.get('eu_doc_id', '')}` — "
                    f"{p.get('shared_principle', '')}"
                )
            lines.append("")
        if s.narrative:
            lines.append("## Comparative Narrative")
            lines.append(s.narrative)
            lines.append("")

    if report.verification:
        v = report.verification
        lines.append("## Verification")
        lines.append(f"- Passed: **{v.passed}**")
        lines.append(f"- Citation validation rate: **{v.citation_validation_rate:.0%}**")
        if v.flags:
            lines.append(f"- Flags ({len(v.flags)}):")
            for f in v.flags[:25]:
                lines.append(
                    f"  - [{f.severity}] {f.code} ({f.document_id or '-'}): {f.message}"
                )
        else:
            lines.append("- No flags raised.")
        lines.append("")
    return "\n".join(lines)


@app.command()
def research(
    query: str = typer.Argument(..., help="Your legal research question."),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write report (JSON) to this file."
    ),
    markdown: Optional[Path] = typer.Option(
        None, "--markdown", "-m", help="Write report (Markdown) to this file."
    ),
) -> None:
    """Run a research session."""
    pipeline = ResearchPipeline()
    with console.status("[bold green]Running research pipeline..."):
        report = asyncio.run(pipeline.run(query))
    console.print(
        Panel.fit(
            f"Session [bold]{report.session_id}[/bold]\n"
            f"US docs: {len(report.us_documents)} | "
            f"EU docs: {len(report.eu_documents)} | "
            f"Verified: {report.verification.passed if report.verification else 'n/a'}",
            title="Legal Eagle AI",
        )
    )
    md = _render_markdown(report)
    console.print(Markdown(md))
    if output:
        output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[dim]Wrote JSON to {output}[/dim]")
    if markdown:
        markdown.write_text(md, encoding="utf-8")
        console.print(f"[dim]Wrote Markdown to {markdown}[/dim]")


@app.command()
def show(session_id: str = typer.Argument(..., help="Session id to fetch.")) -> None:
    """Show a previously stored report (Supabase or in-memory)."""
    db = DB()
    report = db.get_report(session_id)
    if report is None:
        typer.echo(f"Session {session_id} not found.", err=True)
        raise typer.Exit(code=1)
    console.print(Markdown(_render_markdown(report)))


if __name__ == "__main__":
    app()
