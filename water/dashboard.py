"""
Observability dashboard for Water flow executions.

Provides a React SPA-based UI for viewing flow execution sessions,
task runs, and aggregate statistics, plus data API methods for the
backend endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from water.storage import FlowSession, FlowStatus, StorageBackend, TaskRun


class FlowDashboard:
    """Serves data APIs and the SPA HTML for the Water dashboard.

    Args:
        storage: A StorageBackend instance to read sessions and task runs from.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    # ------------------------------------------------------------------
    # Data API methods
    # ------------------------------------------------------------------

    async def get_stats(self) -> Dict[str, Any]:
        """Return JSON-friendly statistics about flow executions."""
        sessions: List[FlowSession] = await self.storage.list_sessions()
        by_status: Dict[str, int] = {}
        for s in sessions:
            key = s.status.value if isinstance(s.status, FlowStatus) else s.status
            by_status[key] = by_status.get(key, 0) + 1

        sorted_sessions = sorted(
            sessions, key=lambda s: s.created_at, reverse=True
        )
        recent = [s.to_dict() for s in sorted_sessions[:10]]

        return {
            "total_sessions": len(sessions),
            "by_status": by_status,
            "recent_sessions": recent,
        }

    async def get_sessions_list(
        self,
        flow_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return a paginated list of sessions."""
        sessions: List[FlowSession] = await self.storage.list_sessions(
            flow_id=flow_id
        )
        sorted_sessions = sorted(
            sessions, key=lambda s: s.created_at, reverse=True
        )
        total = len(sorted_sessions)
        page = sorted_sessions[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "sessions": [s.to_dict() for s in page],
        }

    async def get_session_detail(
        self, execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return full session detail including task runs."""
        session = await self.storage.get_session(execution_id)
        if session is None:
            return None

        task_runs: List[TaskRun] = await self.storage.get_task_runs(
            execution_id
        )
        return {
            **session.to_dict(),
            "task_runs": [tr.to_dict() for tr in task_runs],
        }

    def get_flows_summary(self, flows: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return summary info for each registered flow.

        Args:
            flows: Mapping of flow_id -> Flow object (as kept by FlowServer).
        """
        result = []
        for flow_id, flow in flows.items():
            result.append({
                "id": flow_id,
                "description": getattr(flow, "description", ""),
            })
        return result

    def get_spa_html(self) -> str:
        """Return the single-page application HTML string."""
        return _SPA_HTML


# ----------------------------------------------------------------------
# React SPA (plain JS, no build step)
# ----------------------------------------------------------------------

_SPA_HTML = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Water Dashboard</title>
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/recharts@2/umd/Recharts.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  body { font-family: 'Inter', sans-serif; }
  .font-mono { font-family: 'JetBrains Mono', monospace; }
</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen transition-colors duration-200">
<div id="root"></div>
<script>
// ── Setup ────────────────────────────────────────────────────────────
var h = React.createElement;
var useState = React.useState;
var useEffect = React.useEffect;
var useCallback = React.useCallback;
var useRef = React.useRef;

tailwind.config = { darkMode: 'class' };

var STATUS_COLORS = {
  completed: '#10b981',
  failed:    '#ef4444',
  running:   '#f59e0b',
  paused:    '#3b82f6',
  pending:   '#6b7280',
  stopped:   '#6b7280'
};

var STATUS_BG = {
  completed: 'bg-emerald-500/20 text-emerald-400',
  failed:    'bg-red-500/20 text-red-400',
  running:   'bg-amber-500/20 text-amber-400',
  paused:    'bg-blue-500/20 text-blue-400',
  pending:   'bg-gray-500/20 text-gray-400',
  stopped:   'bg-gray-500/20 text-gray-400'
};

var STATUS_BG_LIGHT = {
  completed: 'bg-emerald-100 text-emerald-700',
  failed:    'bg-red-100 text-red-700',
  running:   'bg-amber-100 text-amber-700',
  paused:    'bg-blue-100 text-blue-700',
  pending:   'bg-gray-200 text-gray-600',
  stopped:   'bg-gray-200 text-gray-600'
};

// ── Hooks ────────────────────────────────────────────────────────────
function useTheme() {
  var stored = localStorage.getItem('water-theme') || 'dark';
  var st = useState(stored);
  var theme = st[0], setTheme = st[1];

  useEffect(function () {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.body.className = theme === 'dark'
      ? 'bg-gray-950 text-gray-100 min-h-screen transition-colors duration-200'
      : 'bg-gray-50 text-gray-900 min-h-screen transition-colors duration-200';
    localStorage.setItem('water-theme', theme);
  }, [theme]);

  var toggle = useCallback(function () {
    setTheme(function (t) { return t === 'dark' ? 'light' : 'dark'; });
  }, []);

  return { theme: theme, toggle: toggle };
}

function useFetch(url, interval) {
  var st  = useState(null);  var data    = st[0],  setData    = st[1];
  var st2 = useState(true);  var loading = st2[0], setLoading = st2[1];
  var st3 = useState(null);  var error   = st3[0], setError   = st3[1];
  var mountedRef = useRef(true);

  var doFetch = useCallback(function () {
    if (!url) return;
    fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (d) {
      if (mountedRef.current) { setData(d); setLoading(false); setError(null); }
    }).catch(function (e) {
      if (mountedRef.current) { setError(e.message); setLoading(false); }
    });
  }, [url]);

  useEffect(function () {
    mountedRef.current = true;
    setLoading(true);
    doFetch();
    var id = interval ? setInterval(doFetch, interval) : null;
    return function () { mountedRef.current = false; if (id) clearInterval(id); };
  }, [doFetch, interval]);

  return { data: data, loading: loading, error: error, refetch: doFetch };
}

// ── Utility ──────────────────────────────────────────────────────────
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : s; }

function fmtDuration(start, end) {
  if (!start || !end) return '-';
  var ms = new Date(end) - new Date(start);
  if (ms < 1000) return ms + 'ms';
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
  return (ms / 60000).toFixed(1) + 'm';
}

function fmtDate(iso) {
  if (!iso) return '-';
  var d = new Date(iso);
  return d.toLocaleString();
}

// ── Small Components ─────────────────────────────────────────────────
function LoadingSpinner() {
  return h('div', { className: 'flex items-center justify-center py-20' },
    h('div', { className: 'animate-spin rounded-full h-10 w-10 border-4 border-gray-600 border-t-blue-500' })
  );
}

function ErrorMessage(props) {
  return h('div', { className: 'flex flex-col items-center justify-center py-20 gap-4' },
    h('div', { className: 'text-red-400 text-lg' }, 'Error: ' + props.message),
    h('button', {
      className: 'px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors',
      onClick: props.onRetry
    }, 'Retry')
  );
}

function StatusBadge(props) {
  var isDark = document.documentElement.classList.contains('dark');
  var map = isDark ? STATUS_BG : STATUS_BG_LIGHT;
  var cls = map[props.status] || map.pending;
  return h('span', {
    className: 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ' + cls
  }, props.status);
}

function StatsCard(props) {
  return h('div', {
    className: 'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 p-5 ' +
      'bg-gray-900 dark:bg-gray-900 bg-white transition-colors'
  },
    h('div', { className: 'flex items-center justify-between mb-3' },
      h('span', { className: 'text-sm font-medium text-gray-400 dark:text-gray-400 text-gray-500' }, props.title),
      h('span', { className: 'text-2xl' }, props.icon)
    ),
    h('div', { className: 'text-3xl font-bold', style: { color: props.color || '#e5e7eb' } }, props.value)
  );
}

function JsonViewer(props) {
  var st = useState(false); var open = st[0], setOpen = st[1];
  var content = props.data != null ? JSON.stringify(props.data, null, 2) : 'null';

  return h('div', { className: 'rounded-lg border border-gray-800 dark:border-gray-800 border-gray-200 overflow-hidden' },
    h('button', {
      className: 'w-full flex items-center justify-between px-4 py-2 text-sm font-medium ' +
        'bg-gray-800 dark:bg-gray-800 bg-gray-100 hover:bg-gray-700 dark:hover:bg-gray-700 hover:bg-gray-200 transition-colors',
      onClick: function () { setOpen(!open); }
    },
      h('span', null, props.label || 'Data'),
      h('span', { className: 'transition-transform ' + (open ? 'rotate-180' : '') }, '\u25BC')
    ),
    open && h('pre', {
      className: 'p-4 text-xs font-mono overflow-x-auto bg-gray-950 dark:bg-gray-950 bg-gray-50 text-gray-300 dark:text-gray-300 text-gray-700 max-h-64 overflow-y-auto'
    }, content)
  );
}

// ── Navbar ───────────────────────────────────────────────────────────
function Navbar(props) {
  var links = [
    { hash: '#/', label: 'Overview' },
    { hash: '#/flows', label: 'Flows' }
  ];

  return h('nav', {
    className: 'sticky top-0 z-50 border-b border-gray-800 dark:border-gray-800 border-gray-200 ' +
      'bg-gray-900/80 dark:bg-gray-900/80 bg-white/80 backdrop-blur-md'
  },
    h('div', { className: 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-14' },
      h('a', { href: '#/', className: 'flex items-center gap-2 font-bold text-lg' },
        h('span', null, '\uD83D\uDCA7'),
        h('span', null, 'Water Dashboard')
      ),
      h('div', { className: 'flex items-center gap-6' },
        links.map(function (lnk) {
          var active = props.currentPage === lnk.hash ||
            (lnk.hash === '#/' && (props.currentPage === '' || props.currentPage === '#' || props.currentPage === '#/'));
          return h('a', {
            key: lnk.hash,
            href: lnk.hash,
            className: 'text-sm font-medium transition-colors ' +
              (active ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200 dark:hover:text-gray-200 hover:text-gray-700')
          }, lnk.label);
        }),
        h('button', {
          onClick: props.toggleTheme,
          className: 'ml-2 p-2 rounded-lg hover:bg-gray-800 dark:hover:bg-gray-800 hover:bg-gray-200 transition-colors text-lg',
          title: 'Toggle theme'
        }, props.theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19')
      )
    )
  );
}

// ── Overview Page ────────────────────────────────────────────────────
function OverviewPage() {
  var f = useFetch('/api/dashboard/stats', 5000);
  if (f.loading) return h(LoadingSpinner);
  if (f.error)   return h(ErrorMessage, { message: f.error, onRetry: f.refetch });

  var stats = f.data;
  var bs = stats.by_status || {};

  var cards = [
    { title: 'Total Executions', value: stats.total_sessions, icon: '\uD83D\uDCCA', color: '#e5e7eb' },
    { title: 'Completed',        value: bs.completed || 0,     icon: '\u2705',       color: '#10b981' },
    { title: 'Failed',           value: bs.failed || 0,        icon: '\u274C',       color: '#ef4444' },
    { title: 'Running',          value: bs.running || 0,       icon: '\u26A1',       color: '#f59e0b' }
  ];

  // Pie data
  var pieData = Object.keys(bs).map(function (k) {
    return { name: k, value: bs[k], fill: STATUS_COLORS[k] || '#6b7280' };
  });

  var PieChart   = window.Recharts.PieChart;
  var Pie        = window.Recharts.Pie;
  var Cell       = window.Recharts.Cell;
  var Tooltip    = window.Recharts.Tooltip;
  var Legend     = window.Recharts.Legend;
  var ResponsiveContainer = window.Recharts.ResponsiveContainer;

  return h('div', { className: 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8' },

    // Stat cards
    h('div', { className: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4' },
      cards.map(function (c) { return h(StatsCard, Object.assign({ key: c.title }, c)); })
    ),

    // Chart + recent table row
    h('div', { className: 'grid grid-cols-1 lg:grid-cols-3 gap-6' },

      // Pie chart
      pieData.length > 0 && h('div', {
        className: 'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 ' +
          'bg-gray-900 dark:bg-gray-900 bg-white p-5'
      },
        h('h3', { className: 'text-sm font-medium text-gray-400 mb-4' }, 'Status Distribution'),
        h(ResponsiveContainer, { width: '100%', height: 260 },
          h(PieChart, null,
            h(Pie, {
              data: pieData,
              cx: '50%', cy: '50%',
              innerRadius: 55, outerRadius: 90,
              paddingAngle: 3,
              dataKey: 'value',
              nameKey: 'name',
              label: function (e) { return e.name + ' (' + e.value + ')'; },
              labelLine: true
            },
              pieData.map(function (entry, i) {
                return h(Cell, { key: 'cell-' + i, fill: entry.fill });
              })
            ),
            h(Tooltip, { contentStyle: { background: '#1f2937', border: 'none', borderRadius: '8px', color: '#e5e7eb' } }),
            h(Legend, null)
          )
        )
      ),

      // Recent executions
      h('div', {
        className: (pieData.length > 0 ? 'lg:col-span-2 ' : 'lg:col-span-3 ') +
          'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 ' +
          'bg-gray-900 dark:bg-gray-900 bg-white p-5 overflow-x-auto'
      },
        h('h3', { className: 'text-sm font-medium text-gray-400 mb-4' }, 'Recent Executions'),
        stats.recent_sessions && stats.recent_sessions.length > 0
          ? h('table', { className: 'w-full text-sm' },
              h('thead', null,
                h('tr', { className: 'text-left text-gray-500 border-b border-gray-800 dark:border-gray-800 border-gray-200' },
                  h('th', { className: 'pb-2 pr-4' }, 'Execution ID'),
                  h('th', { className: 'pb-2 pr-4' }, 'Flow'),
                  h('th', { className: 'pb-2 pr-4' }, 'Status'),
                  h('th', { className: 'pb-2 pr-4' }, 'Created'),
                  h('th', { className: 'pb-2' }, 'Duration')
                )
              ),
              h('tbody', null,
                stats.recent_sessions.map(function (s) {
                  return h('tr', {
                    key: s.execution_id,
                    className: 'border-b border-gray-800/50 dark:border-gray-800/50 border-gray-100 hover:bg-gray-800/50 dark:hover:bg-gray-800/50 hover:bg-gray-50 transition-colors'
                  },
                    h('td', { className: 'py-2.5 pr-4 font-mono text-xs' },
                      h('a', {
                        href: '#/session/' + s.execution_id,
                        className: 'text-blue-400 hover:text-blue-300 hover:underline'
                      }, truncate(s.execution_id, 20))
                    ),
                    h('td', { className: 'py-2.5 pr-4' }, s.flow_id),
                    h('td', { className: 'py-2.5 pr-4' }, h(StatusBadge, { status: s.status })),
                    h('td', { className: 'py-2.5 pr-4 text-gray-400' }, fmtDate(s.created_at)),
                    h('td', { className: 'py-2.5 text-gray-400' }, fmtDuration(s.created_at, s.updated_at))
                  );
                })
              )
            )
          : h('p', { className: 'text-gray-500 text-center py-8' }, 'No executions yet.')
      )
    )
  );
}

// ── Session Detail Page ──────────────────────────────────────────────
function SessionDetailPage(props) {
  var f = useFetch('/api/dashboard/sessions/' + encodeURIComponent(props.executionId), 5000);
  if (f.loading) return h(LoadingSpinner);
  if (f.error)   return h(ErrorMessage, { message: f.error, onRetry: f.refetch });
  if (!f.data)   return h('div', { className: 'max-w-7xl mx-auto px-4 py-8 text-gray-400' }, 'Session not found.');

  var s = f.data;
  var taskRuns = s.task_runs || [];

  return h('div', { className: 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6' },

    // Back
    h('a', {
      href: '#/',
      className: 'inline-flex items-center gap-1 text-sm text-gray-400 hover:text-blue-400 transition-colors'
    }, '\u2190 Back to Overview'),

    // Session card
    h('div', {
      className: 'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 ' +
        'bg-gray-900 dark:bg-gray-900 bg-white p-6 space-y-4'
    },
      h('div', { className: 'flex flex-col sm:flex-row sm:items-center justify-between gap-2' },
        h('h2', { className: 'text-xl font-bold' }, 'Session Detail'),
        h(StatusBadge, { status: s.status })
      ),
      h('div', { className: 'grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm' },
        h('div', null,
          h('span', { className: 'text-gray-500' }, 'Execution ID'),
          h('p', { className: 'font-mono text-xs mt-0.5 break-all' }, s.execution_id)
        ),
        h('div', null,
          h('span', { className: 'text-gray-500' }, 'Flow ID'),
          h('p', { className: 'mt-0.5' }, s.flow_id)
        ),
        h('div', null,
          h('span', { className: 'text-gray-500' }, 'Created'),
          h('p', { className: 'mt-0.5' }, fmtDate(s.created_at))
        ),
        h('div', null,
          h('span', { className: 'text-gray-500' }, 'Updated'),
          h('p', { className: 'mt-0.5' }, fmtDate(s.updated_at))
        )
      ),
      s.error && h('div', {
        className: 'rounded-lg bg-red-500/10 border border-red-500/30 p-4 text-sm text-red-400'
      },
        h('span', { className: 'font-medium' }, 'Error: '),
        h('span', { className: 'font-mono text-xs' }, s.error)
      ),
      h(JsonViewer, { data: s.input_data, label: 'Input Data' }),
      h(JsonViewer, { data: s.result, label: 'Output / Result' })
    ),

    // Task runs
    h('div', {
      className: 'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 ' +
        'bg-gray-900 dark:bg-gray-900 bg-white p-6'
    },
      h('h3', { className: 'text-lg font-semibold mb-4' }, 'Task Runs (' + taskRuns.length + ')'),
      taskRuns.length > 0
        ? h('div', { className: 'space-y-3' },
            taskRuns.map(function (tr) { return h(TaskRunCard, { key: tr.id, run: tr }); })
          )
        : h('p', { className: 'text-gray-500 text-center py-6' }, 'No task runs recorded.')
    )
  );
}

function TaskRunCard(props) {
  var st = useState(false); var expanded = st[0], setExpanded = st[1];
  var tr = props.run;

  return h('div', {
    className: 'rounded-lg border border-gray-800 dark:border-gray-800 border-gray-200 overflow-hidden'
  },
    h('button', {
      className: 'w-full flex items-center justify-between px-4 py-3 text-sm ' +
        'hover:bg-gray-800/50 dark:hover:bg-gray-800/50 hover:bg-gray-50 transition-colors text-left',
      onClick: function () { setExpanded(!expanded); }
    },
      h('div', { className: 'flex items-center gap-3 flex-wrap' },
        h('span', { className: 'font-medium' }, tr.task_id),
        h(StatusBadge, { status: tr.status }),
        h('span', { className: 'text-gray-500 text-xs' },
          fmtDate(tr.started_at) + ' \u2192 ' + fmtDate(tr.completed_at)
        ),
        h('span', { className: 'text-gray-500 text-xs' },
          'Duration: ' + fmtDuration(tr.started_at, tr.completed_at)
        )
      ),
      h('span', { className: 'text-gray-500 transition-transform ' + (expanded ? 'rotate-180' : '') }, '\u25BC')
    ),
    expanded && h('div', { className: 'px-4 pb-4 space-y-2 border-t border-gray-800 dark:border-gray-800 border-gray-200 pt-3' },
      tr.error && h('div', {
        className: 'rounded bg-red-500/10 border border-red-500/30 p-2 text-xs text-red-400 font-mono'
      }, tr.error),
      h(JsonViewer, { data: tr.input_data, label: 'Task Input' }),
      h(JsonViewer, { data: tr.output_data, label: 'Task Output' })
    )
  );
}

// ── Flows Page ───────────────────────────────────────────────────────
function FlowsPage() {
  var f = useFetch('/api/dashboard/flows', 10000);
  if (f.loading) return h(LoadingSpinner);
  if (f.error)   return h(ErrorMessage, { message: f.error, onRetry: f.refetch });

  var flows = f.data && f.data.flows ? f.data.flows : [];

  return h('div', { className: 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6' },
    h('h2', { className: 'text-xl font-bold' }, 'Registered Flows'),
    flows.length > 0
      ? h('div', { className: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4' },
          flows.map(function (fl) {
            return h('div', {
              key: fl.flow_id,
              className: 'rounded-xl border border-gray-800 dark:border-gray-800 border-gray-200 ' +
                'bg-gray-900 dark:bg-gray-900 bg-white p-5 space-y-3'
            },
              h('h3', { className: 'font-semibold text-lg' }, fl.flow_id),
              fl.description && h('p', { className: 'text-sm text-gray-400' }, fl.description),
              h('div', { className: 'flex items-center gap-4 text-xs text-gray-500' },
                fl.task_count != null && h('span', null, fl.task_count + ' tasks'),
                fl.version && h('span', null, 'v' + fl.version)
              )
            );
          })
        )
      : h('p', { className: 'text-gray-500 text-center py-12' }, 'No flows registered yet.')
  );
}

// ── Router / App ─────────────────────────────────────────────────────
function App() {
  var themeHook = useTheme();
  var st = useState(window.location.hash || '#/');
  var page = st[0], setPage = st[1];

  useEffect(function () {
    function onHash() { setPage(window.location.hash || '#/'); }
    window.addEventListener('hashchange', onHash);
    return function () { window.removeEventListener('hashchange', onHash); };
  }, []);

  var content;
  var sessionMatch = page.match(/^#\/session\/(.+)$/);

  if (sessionMatch) {
    content = h(SessionDetailPage, { executionId: decodeURIComponent(sessionMatch[1]) });
  } else if (page === '#/flows') {
    content = h(FlowsPage);
  } else {
    content = h(OverviewPage);
  }

  return h('div', null,
    h(Navbar, {
      theme: themeHook.theme,
      toggleTheme: themeHook.toggle,
      currentPage: page
    }),
    content
  );
}

// ── Mount ────────────────────────────────────────────────────────────
ReactDOM.createRoot(document.getElementById('root')).render(h(App));
</script>
</body>
</html>
"""
