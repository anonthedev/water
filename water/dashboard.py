"""
Observability dashboard for Water flow executions.

Provides an HTML-based UI for viewing flow execution sessions,
task runs, and aggregate statistics.
"""

import html
from datetime import datetime
from typing import Any, Dict, List

from water.storage import FlowSession, FlowStatus, StorageBackend, TaskRun


_STATUS_COLORS = {
    "completed": "#28a745",
    "failed": "#dc3545",
    "running": "#ffc107",
    "paused": "#007bff",
    "pending": "#6c757d",
    "stopped": "#6c757d",
}

_BASE_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #333; }
h1 { margin-top: 0; }
a { color: #007bff; text-decoration: none; }
a:hover { text-decoration: underline; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f9fa; font-weight: 600; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px; color: #fff; font-size: 0.85em; font-weight: 500; }
.container { max-width: 1100px; margin: 0 auto; }
.card { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
pre { background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 0.9em; }
.empty { text-align: center; padding: 40px; color: #888; }
"""


def _esc(value: Any) -> str:
    """HTML-escape a value."""
    return html.escape(str(value))


def _badge(status: str) -> str:
    color = _STATUS_COLORS.get(status, "#6c757d")
    return f'<span class="badge" style="background:{color}">{_esc(status)}</span>'


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class FlowDashboard:
    """Generates HTML pages for viewing flow execution data.

    Args:
        storage: A StorageBackend instance to read sessions and task runs from.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    async def get_dashboard_html(self) -> str:
        """Generate an HTML page listing all flow sessions."""
        sessions: List[FlowSession] = await self.storage.list_sessions()
        rows = ""
        if sessions:
            for s in sessions:
                rows += (
                    "<tr>"
                    f"<td><a href=\"/dashboard/session/{_esc(s.execution_id)}\">{_esc(s.execution_id)}</a></td>"
                    f"<td>{_esc(s.flow_id)}</td>"
                    f"<td>{_badge(s.status.value if isinstance(s.status, FlowStatus) else s.status)}</td>"
                    f"<td>{_format_dt(s.created_at)}</td>"
                    "</tr>"
                )
        body = rows if rows else '<tr><td colspan="4" class="empty">No sessions found.</td></tr>'
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Water Dashboard</title>"
            f"<style>{_BASE_CSS}</style></head><body>"
            '<div class="container">'
            "<h1>Water Flow Dashboard</h1>"
            "<table><thead><tr>"
            "<th>Execution ID</th><th>Flow ID</th><th>Status</th><th>Created At</th>"
            "</tr></thead><tbody>"
            f"{body}"
            "</tbody></table></div></body></html>"
        )

    async def get_session_detail_html(self, execution_id: str) -> str:
        """Generate an HTML detail page for a single session."""
        session = await self.storage.get_session(execution_id)
        if session is None:
            return (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<title>Session Not Found</title>"
                f"<style>{_BASE_CSS}</style></head><body>"
                '<div class="container">'
                '<p class="empty">Session not found.</p>'
                '<a href="/dashboard">&larr; Back to dashboard</a>'
                "</div></body></html>"
            )

        status_val = session.status.value if isinstance(session.status, FlowStatus) else session.status
        info = (
            '<div class="card">'
            f"<h2>Session: {_esc(session.execution_id)}</h2>"
            f"<p><strong>Flow ID:</strong> {_esc(session.flow_id)}</p>"
            f"<p><strong>Status:</strong> {_badge(status_val)}</p>"
            f"<p><strong>Input Data:</strong></p><pre>{_esc(str(session.input_data))}</pre>"
        )
        if session.result is not None:
            info += f"<p><strong>Result:</strong></p><pre>{_esc(str(session.result))}</pre>"
        if session.error is not None:
            info += f"<p><strong>Error:</strong></p><pre>{_esc(session.error)}</pre>"
        info += "</div>"

        # Task runs
        task_runs: List[TaskRun] = await self.storage.get_task_runs(execution_id)
        task_rows = ""
        if task_runs:
            for tr in task_runs:
                started = _format_dt(tr.started_at)
                completed = _format_dt(tr.completed_at)
                task_rows += (
                    "<tr>"
                    f"<td>{_esc(tr.task_id)}</td>"
                    f"<td>{_badge(tr.status)}</td>"
                    f"<td>{started}</td>"
                    f"<td>{completed}</td>"
                    f"<td><pre>{_esc(str(tr.input_data))}</pre></td>"
                    f"<td><pre>{_esc(str(tr.output_data))}</pre></td>"
                    "</tr>"
                )
        task_table_body = task_rows if task_rows else '<tr><td colspan="6" class="empty">No task runs.</td></tr>'

        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Session {_esc(execution_id)}</title>"
            f"<style>{_BASE_CSS}</style></head><body>"
            '<div class="container">'
            '<a href="/dashboard">&larr; Back to dashboard</a>'
            f"{info}"
            "<h3>Task Runs</h3>"
            "<table><thead><tr>"
            "<th>Task ID</th><th>Status</th><th>Started</th><th>Completed</th><th>Input</th><th>Output</th>"
            "</tr></thead><tbody>"
            f"{task_table_body}"
            "</tbody></table></div></body></html>"
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Return JSON-friendly statistics about flow executions."""
        sessions: List[FlowSession] = await self.storage.list_sessions()
        by_status: Dict[str, int] = {}
        for s in sessions:
            key = s.status.value if isinstance(s.status, FlowStatus) else s.status
            by_status[key] = by_status.get(key, 0) + 1

        sorted_sessions = sorted(sessions, key=lambda s: s.created_at, reverse=True)
        recent = [s.to_dict() for s in sorted_sessions[:10]]

        return {
            "total_sessions": len(sessions),
            "by_status": by_status,
            "recent_sessions": recent,
        }
