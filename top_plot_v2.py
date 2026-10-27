#!/usr/bin/env python
"""
Top Plot Analyzer v2.0
Modern Qt UI and Comprehensive Linux/Android Top & Topmem Log Profiler.
Features:
- Dual-axis interactive telemetry visualizations with Plotly (embedded & exportable)
- Full per-PID CPU and Memory (RES, %MEM, SHR) tracking and multi-selection
- Drag-and-drop ingestion for files and directories with automatic top & topmen pairing
- System metrics breakdown (%cpu_total, %user, %sys, %idle, RAM total/used, /proc/meminfo)
- Dark automotive-grade UI with responsive filters and session queue
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import re
import os
import sys
import logging
import json
import csv
import html

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. Data Models
# ----------------------------------------------------------------------

@dataclass
class ProcessRecord:
    """Telemetry record for a single process at a timestamp."""
    pid: int
    user: str
    virt_mb: float
    res_mb: float
    shr_mb: float
    state: str
    cpu: float
    mem_pct: float
    args: str
    time_plus: str = ""


@dataclass
class LogJob:
    """Represents a telemetry session comprising top and/or topmen log files."""
    label: str
    top_file: Optional[str] = None
    topmen_file: Optional[str] = None
    parsed_data: Optional['ParsedLogV2'] = None


@dataclass
class Snapshot:
    """Telemetry snapshot captured at a specific point in time."""
    timestamp: str
    cpu_metrics: Dict[str, float] = field(default_factory=dict)
    mem_metrics: Dict[str, float] = field(default_factory=dict)
    meminfo: Dict[str, float] = field(default_factory=dict)
    processes: Dict[int, ProcessRecord] = field(default_factory=dict)


@dataclass
class ParsedLogV2:
    """Container for parsed log snapshots and indexed queries."""
    snapshots: List[Snapshot] = field(default_factory=list)

    @property
    def timestamps(self) -> List[str]:
        return [s.timestamp for s in self.snapshots]

    @property
    def system_metrics(self) -> Dict[str, List[float]]:
        """Extract aligned system-level metric time series."""
        metrics: Dict[str, List[float]] = {}
        for s in self.snapshots:
            for k, v in s.cpu_metrics.items():
                metrics.setdefault(k, []).append(v)
            for k, v in s.mem_metrics.items():
                metrics.setdefault(k, []).append(v)
            for k, v in s.meminfo.items():
                metrics.setdefault(k, []).append(v)
        return metrics

    def get_all_pids(self) -> List[int]:
        """Return all unique PIDs observed across all snapshots."""
        pids = set()
        for s in self.snapshots:
            pids.update(s.processes.keys())
        return sorted(pids)

    def get_process_name(self, pid: int) -> str:
        """Get best known process args/name for a given PID."""
        for s in reversed(self.snapshots):
            if pid in s.processes:
                return s.processes[pid].args
        return f"PID {pid}"

    def get_pid_metrics(self, pid: int) -> Dict[str, Any]:
        """Return complete time series and summary for a single PID."""
        cpu_series: List[float] = []
        res_series: List[float] = []
        shr_series: List[float] = []
        mem_pct_series: List[float] = []
        last_args = f"PID {pid}"

        for s in self.snapshots:
            rec = s.processes.get(pid)
            if rec:
                cpu_series.append(rec.cpu)
                res_series.append(rec.res_mb)
                shr_series.append(rec.shr_mb)
                mem_pct_series.append(rec.mem_pct)
                last_args = rec.args
            else:
                cpu_series.append(0.0)
                res_series.append(0.0)
                shr_series.append(0.0)
                mem_pct_series.append(0.0)

        max_cpu = max(cpu_series) if cpu_series else 0.0
        avg_cpu = (sum(cpu_series) / len(cpu_series)) if cpu_series else 0.0
        max_res = max(res_series) if res_series else 0.0
        max_shr = max(shr_series) if shr_series else 0.0

        return {
            "pid": pid,
            "args": last_args,
            "cpu": cpu_series,
            "res_mb": res_series,
            "shr_mb": shr_series,
            "mem_pct": mem_pct_series,
            "max_cpu": max_cpu,
            "avg_cpu": avg_cpu,
            "max_res_mb": max_res,
            "max_shr_mb": max_shr
        }

    def get_top_pids_by_cpu(self, limit: int = 10) -> List[Tuple[int, str, float]]:
        """Return top PIDs ranked by peak CPU percentage."""
        pids = self.get_all_pids()
        ranked = []
        for pid in pids:
            m = self.get_pid_metrics(pid)
            ranked.append((pid, m["args"], m["max_cpu"]))
        ranked.sort(key=lambda x: x[2], reverse=True)
        return ranked[:limit]

    def get_top_pids_by_mem(self, limit: int = 10) -> List[Tuple[int, str, float]]:
        """Return top PIDs ranked by peak RES memory in MB."""
        pids = self.get_all_pids()
        ranked = []
        for pid in pids:
            m = self.get_pid_metrics(pid)
            ranked.append((pid, m["args"], m["max_res_mb"]))
        ranked.sort(key=lambda x: x[2], reverse=True)
        return ranked[:limit]

    def to_csv(self, file_path: str) -> str:
        """Export telemetry data as CSV."""
        all_pids = self.get_all_pids()
        pid_names = {pid: self.get_process_name(pid) for pid in all_pids}

        headers = ["Timestamp", "System_CPU%", "System_RAM_MB", "Swap_Used_MB"]
        for pid in all_pids:
            safe_name = pid_names[pid].replace(",", "_")[:30]
            headers.extend([f"PID_{pid}_{safe_name}_CPU%", f"PID_{pid}_{safe_name}_RES_MB"])

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for i, snap in enumerate(self.snapshots):
                row = [
                    snap.timestamp,
                    snap.cpu_metrics.get("%cpu_total", 0.0),
                    snap.mem_metrics.get("mem_used_mb", 0.0),
                    snap.mem_metrics.get("swap_used_mb", 0.0),
                ]
                for pid in all_pids:
                    proc = snap.processes.get(pid)
                    row.append(proc.cpu if proc else 0.0)
                    row.append(proc.res_mb if proc else 0.0)
                writer.writerow(row)
        return file_path

    def to_json(self, file_path: str) -> str:
        """Export telemetry data as JSON."""
        all_pids = self.get_all_pids()
        result = {
            "timestamps": self.timestamps,
            "system_metrics": self.system_metrics,
            "processes": {}
        }
        for pid in all_pids:
            m = self.get_pid_metrics(pid)
            result["processes"][str(pid)] = {
                "args": m["args"],
                "cpu": m["cpu"],
                "res_mb": m["res_mb"],
                "shr_mb": m["shr_mb"],
                "mem_pct": m["mem_pct"],
                "max_cpu": m["max_cpu"],
                "avg_cpu": m["avg_cpu"],
                "max_res_mb": m["max_res_mb"]
            }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return file_path


# ----------------------------------------------------------------------
# 2. Parsing Functions & Regex Engine
# ----------------------------------------------------------------------

_TIMESTAMP_DHU = re.compile(r'^(\d{8}_\d{2}-\d{2}-\d{2})')
_TIMESTAMP_WATCH = re.compile(r'([A-Za-z]{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})')
_CPU_LINE = re.compile(r'(\d+)%cpu.*?\d+%user')
_MEM_LINE = re.compile(r'^\s*Mem:\s+(\d+)K\s+total,\s+(\d+)K\s+used,\s+(\d+)K\s+free(?:,\s+(\d+)K\s+buffers)?', re.IGNORECASE)
_SWAP_LINE = re.compile(r'^\s*Swap:\s+(\d+)K\s+total,\s+(\d+)K\s+used,\s+(\d+)K\s+free(?:,\s+(\d+)K\s+cached)?', re.IGNORECASE)
_MEMINFO_LINE = re.compile(r'^([A-Za-z0-9_()]+):\s+(\d+)\s+kB')
_PROCESS_LINE_RE = re.compile(r'^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([SRDIZT])\s+([0-9.]+)\s+([0-9.]+)\s+(\S+)\s+(.+)$')


def parse_memory_mb(val: Optional[str]) -> float:
    """Parse memory string (e.g. 569M, 19G, 1024K, 0) into megabytes float."""
    if not val:
        return 0.0
    val = val.strip()
    if not val:
        return 0.0
    unit = val[-1].upper()
    try:
        if unit == 'G':
            return float(val[:-1]) * 1024.0
        elif unit == 'M':
            return float(val[:-1])
        elif unit == 'K':
            return float(val[:-1]) / 1024.0
        elif unit == 'B':
            return float(val[:-1]) / (1024.0 * 1024.0)
        else:
            return float(val)
    except ValueError:
        return 0.0


def parse_process_row(line: str) -> Optional[ProcessRecord]:
    """Parse a single process table row from top output."""
    if not line:
        return None
    match = _PROCESS_LINE_RE.match(line)
    if not match:
        return None
    
    pid_str, user, pr, ni, virt, res, shr, state, cpu_str, mem_str, time_plus, args = match.groups()
    try:
        return ProcessRecord(
            pid=int(pid_str),
            user=user,
            virt_mb=parse_memory_mb(virt),
            res_mb=parse_memory_mb(res),
            shr_mb=parse_memory_mb(shr),
            state=state,
            cpu=float(cpu_str),
            mem_pct=float(mem_str),
            args=args.strip(),
            time_plus=time_plus
        )
    except (ValueError, TypeError):
        return None


class LogParserV2:
    """High-performance parser for Linux and Android top / topmem logs."""

    def __init__(self):
        self.percentage_labels = (
            '%user', '%sys', '%nice', '%irq', '%sirq', '%iow', '%host', '%idle'
        )

    def parse_file(self, file_path: str, encoding: str = 'utf-8') -> Optional[ParsedLogV2]:
        """Parse log file from disk."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
            return self.parse_string(content)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return None

    def parse_job(self, job: LogJob, encoding: str = 'utf-8') -> Optional[ParsedLogV2]:
        """Parse and merge a paired top/topmen LogJob session."""
        top_data: Optional[ParsedLogV2] = None
        topmen_data: Optional[ParsedLogV2] = None

        if job.top_file and os.path.exists(job.top_file):
            top_data = self.parse_file(job.top_file, encoding)
        if job.topmen_file and os.path.exists(job.topmen_file):
            topmen_data = self.parse_file(job.topmen_file, encoding)

        if top_data and not topmen_data:
            job.parsed_data = top_data
            return top_data
        elif topmen_data and not top_data:
            job.parsed_data = topmen_data
            return topmen_data
        elif not top_data and not topmen_data:
            return None

        # Both present: merge by timestamp
        ts_map: Dict[str, Snapshot] = {s.timestamp: s for s in top_data.snapshots}

        for s_mem in topmen_data.snapshots:
            if s_mem.timestamp in ts_map:
                s_target = ts_map[s_mem.timestamp]
                # Merge meminfo
                s_target.meminfo.update(s_mem.meminfo)
                # Merge mem metrics if missing
                for k, v in s_mem.mem_metrics.items():
                    if k not in s_target.mem_metrics:
                        s_target.mem_metrics[k] = v
                # Merge or augment processes
                for pid, proc in s_mem.processes.items():
                    if pid in s_target.processes:
                        target_proc = s_target.processes[pid]
                        if proc.res_mb > 0 and target_proc.res_mb == 0:
                            target_proc.res_mb = proc.res_mb
                        if proc.shr_mb > 0 and target_proc.shr_mb == 0:
                            target_proc.shr_mb = proc.shr_mb
                    else:
                        s_target.processes[pid] = proc
            else:
                ts_map[s_mem.timestamp] = s_mem

        # Re-sort snapshots by timestamp
        merged_snapshots = sorted(ts_map.values(), key=lambda s: s.timestamp)
        unified = ParsedLogV2(snapshots=merged_snapshots)
        job.parsed_data = unified
        return unified

    def parse_string(self, content: str) -> ParsedLogV2:
        """Parse log string content into ParsedLogV2."""
        lines = content.splitlines()
        snapshots: List[Snapshot] = []
        current_snapshot: Optional[Snapshot] = None

        def save_current_snapshot():
            nonlocal current_snapshot
            if current_snapshot and (current_snapshot.cpu_metrics or current_snapshot.processes):
                snapshots.append(current_snapshot)
            current_snapshot = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check timestamp
            ts_match = _TIMESTAMP_DHU.search(line_str) or _TIMESTAMP_WATCH.search(line_str)
            if ts_match:
                save_current_snapshot()
                current_snapshot = Snapshot(timestamp=ts_match.group(1))
                continue

            if current_snapshot is None:
                current_snapshot = Snapshot(timestamp="initial")

            # Check CPU Summary
            if _CPU_LINE.search(line_str):
                cpu_dict = self._parse_cpu_summary(line_str)
                current_snapshot.cpu_metrics.update(cpu_dict)
                continue

            # Check Mem line
            mem_m = _MEM_LINE.match(line_str)
            if mem_m:
                total_k, used_k, free_k, buf_k = mem_m.groups()
                current_snapshot.mem_metrics["mem_total_mb"] = float(total_k) / 1024.0
                current_snapshot.mem_metrics["mem_used_mb"] = float(used_k) / 1024.0
                current_snapshot.mem_metrics["mem_free_mb"] = float(free_k) / 1024.0
                if buf_k:
                    current_snapshot.mem_metrics["mem_buffers_mb"] = float(buf_k) / 1024.0
                continue

            # Check Swap line
            swap_m = _SWAP_LINE.match(line_str)
            if swap_m:
                total_k, used_k, free_k, cache_k = swap_m.groups()
                current_snapshot.mem_metrics["swap_total_mb"] = float(total_k) / 1024.0
                current_snapshot.mem_metrics["swap_used_mb"] = float(used_k) / 1024.0
                current_snapshot.mem_metrics["swap_free_mb"] = float(free_k) / 1024.0
                if cache_k:
                    current_snapshot.mem_metrics["mem_cached_mb"] = float(cache_k) / 1024.0
                continue

            # Check /proc/meminfo lines
            meminfo_m = _MEMINFO_LINE.match(line_str)
            if meminfo_m:
                key, kb_val = meminfo_m.groups()
                current_snapshot.meminfo[f"meminfo_{key}_mb"] = float(kb_val) / 1024.0
                continue

            # Check Process Row
            proc_rec = parse_process_row(line_str)
            if proc_rec:
                current_snapshot.processes[proc_rec.pid] = proc_rec

        save_current_snapshot()
        return ParsedLogV2(snapshots=snapshots)

    def _parse_cpu_summary(self, line: str) -> Dict[str, float]:
        """Extract individual metric percentages and total non-idle CPU."""
        res: Dict[str, float] = {}
        tokens = line.split()
        
        total_capacity = 100.0
        for token in tokens:
            if token.endswith('%cpu'):
                try:
                    total_capacity = float(token.replace('%cpu', ''))
                except ValueError:
                    pass
                break
        res['%cpu_capacity'] = total_capacity

        for label in self.percentage_labels:
            for token in tokens:
                if label in token:
                    try:
                        val = float(token.replace(label, ''))
                        res[label] = val
                    except ValueError:
                        pass
                    break

        idle = res.get('%idle', 0.0)
        res['%cpu_total'] = max(0.0, total_capacity - idle)
        return res


# ----------------------------------------------------------------------
# 3. Interactive Visualization Engine (Plotly) & Color Themes
# ----------------------------------------------------------------------

THEMES: Dict[str, Dict[str, Any]] = {
    "Dark Fusion": {
        "bg_window": "#111827",
        "bg_card": "#1f2937",
        "bg_header": "#374151",
        "fg_text": "#f3f4f6",
        "fg_muted": "#9ca3af",
        "border": "#374151",
        "accent_cpu": "#10b981",
        "accent_mem": "#f59e0b",
        "grid": "#4b5563",
        "curve_colors": ["#06b6d4", "#a855f7", "#ec4899", "#3b82f6", "#eab308", "#14b8a6", "#f97316", "#84cc16"],
        "plotly_template": "plotly_dark"
    },
    "Light Mode": {
        "bg_window": "#f8fafc",
        "bg_card": "#ffffff",
        "bg_header": "#e2e8f0",
        "fg_text": "#0f172a",
        "fg_muted": "#64748b",
        "border": "#cbd5e1",
        "accent_cpu": "#059669",
        "accent_mem": "#d97706",
        "grid": "#94a3b8",
        "curve_colors": ["#0284c7", "#7c3aed", "#db2777", "#2563eb", "#ca8a04", "#0d9488", "#ea580c", "#65a30d"],
        "plotly_template": "plotly_white"
    },
    "Midnight Neon": {
        "bg_window": "#0a0e17",
        "bg_card": "#111827",
        "bg_header": "#1f293d",
        "fg_text": "#e0e7ff",
        "fg_muted": "#818cf8",
        "border": "#312e81",
        "accent_cpu": "#06b6d4",
        "accent_mem": "#f43f5e",
        "grid": "#1e293b",
        "curve_colors": ["#38bdf8", "#c084fc", "#f472b6", "#60a5fa", "#facc15", "#2dd4bf", "#fb923c", "#a3e635"],
        "plotly_template": "plotly_dark"
    },
    "Solarized Dark": {
        "bg_window": "#002b36",
        "bg_card": "#073642",
        "bg_header": "#094352",
        "fg_text": "#93a1a1",
        "fg_muted": "#657b83",
        "border": "#586e75",
        "accent_cpu": "#2aa198",
        "accent_mem": "#b58900",
        "grid": "#586e75",
        "curve_colors": ["#268bd2", "#6c71c4", "#d33682", "#859900", "#cb4b16", "#2aa198", "#b58900", "#268bd2"],
        "plotly_template": "plotly_dark"
    },
    "Monokai": {
        "bg_window": "#1e1e1e",
        "bg_card": "#252526",
        "bg_header": "#333333",
        "fg_text": "#f8f8f2",
        "fg_muted": "#75715e",
        "border": "#3e3e42",
        "accent_cpu": "#a6e22e",
        "accent_mem": "#fd971f",
        "grid": "#49483e",
        "curve_colors": ["#66d9ef", "#ae81ff", "#f92672", "#a6e22e", "#fd971f", "#e6db74", "#66d9ef", "#ae81ff"],
        "plotly_template": "plotly_dark"
    }
}


def hex_to_rgb_str(hex_str: str) -> str:
    """Convert hex color string to 'r, g, b' string."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = ''.join([c * 2 for c in hex_str])
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return f"{r}, {g}, {b}"
    except Exception:
        return "16, 185, 129"


class PlotlyHtmlGenerator:
    """Generates interactive Plotly HTML visualizations with dynamic process control table."""

    def __init__(self, data: ParsedLogV2):
        self.data = data

    def create_figure(
        self,
        selected_pids: Optional[List[int]] = None,
        plot_sys_cpu: bool = True,
        plot_sys_mem: bool = True,
        plot_cpu_breakdown: bool = False,
        plot_sys_swap: bool = False,
        theme_name: str = "Dark Fusion",
        include_all_processes: bool = True
    ):
        """Create Plotly Figure with dual Y-axes for CPU and Memory with theme styling."""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        theme = THEMES.get(theme_name, THEMES["Dark Fusion"])
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        x_vals = self.data.timestamps

        trace_idx = 0
        sys_traces: Dict[str, Any] = {}
        pid_traces: Dict[int, List[int]] = {}

        # 1. Total System CPU
        if "%cpu_total" in self.data.system_metrics:
            rgb = hex_to_rgb_str(theme.get("accent_cpu", "#10b981"))
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=self.data.system_metrics["%cpu_total"],
                    name="System Total CPU%",
                    mode="lines",
                    line=dict(color=theme.get("accent_cpu", "#10b981"), width=2),
                    fill="tozeroy",
                    fillcolor=f"rgba({rgb}, 0.09)",
                    visible=bool(plot_sys_cpu)
                ),
                secondary_y=False
            )
            sys_traces["sys_cpu"] = trace_idx
            trace_idx += 1

        # CPU Breakdown stacked area traces
        cpu_breakdown_labels = [
            ("%user", "CPU %user"),
            ("%sys", "CPU %sys"),
            ("%nice", "CPU %nice"),
            ("%irq", "CPU %irq"),
            ("%sirq", "CPU %sirq"),
            ("%iow", "CPU %iow"),
        ]
        cpu_breakdown_colors = ["#3b82f6", "#ef4444", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4"]

        bd_trace_indices = []
        if plot_cpu_breakdown or include_all_processes:
            for idx, (metric_key, trace_label) in enumerate(cpu_breakdown_labels):
                if metric_key in self.data.system_metrics:
                    bd_color = cpu_breakdown_colors[idx % len(cpu_breakdown_colors)]
                    bd_rgb = hex_to_rgb_str(bd_color)
                    fig.add_trace(
                        go.Scatter(
                            x=x_vals,
                            y=self.data.system_metrics[metric_key],
                            name=trace_label,
                            mode="lines",
                            line=dict(color=bd_color, width=1.5),
                            fill="tozeroy",
                            fillcolor=f"rgba({bd_rgb}, 0.15)",
                            visible=bool(plot_cpu_breakdown),
                            stackgroup="cpubreakdown"
                        ),
                        secondary_y=False
                    )
                    sys_traces[f"bd_{metric_key}"] = trace_idx
                    bd_trace_indices.append(trace_idx)
                    trace_idx += 1
            if bd_trace_indices:
                sys_traces["cpu_breakdown"] = bd_trace_indices

        # 2. System Memory Used (MB)
        if "mem_used_mb" in self.data.system_metrics:
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=self.data.system_metrics["mem_used_mb"],
                    name="System RAM Used (MB)",
                    mode="lines",
                    line=dict(color=theme.get("accent_mem", "#f59e0b"), width=1.5, dash="dot"),
                    visible=bool(plot_sys_mem)
                ),
                secondary_y=True
            )
            sys_traces["sys_mem"] = trace_idx
            trace_idx += 1

        # System Swap Used (MB)
        if (plot_sys_swap or include_all_processes) and "swap_used_mb" in self.data.system_metrics:
            swap_color = "#f43f5e"  # rose-500
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=self.data.system_metrics["swap_used_mb"],
                    name="System Swap Used (MB)",
                    mode="lines",
                    line=dict(color=swap_color, width=1.5, dash="dashdot"),
                    visible=bool(plot_sys_swap)
                ),
                secondary_y=True
            )
            sys_traces["sys_swap"] = trace_idx
            trace_idx += 1

        # 3. Process Traces (CPU on Left Y, RES Memory on Right Y)
        all_pids = self.data.get_all_pids()
        sorted_pids = sorted(all_pids, key=lambda p: self.data.get_pid_metrics(p)["max_cpu"], reverse=True)

        selected_set = set(selected_pids or [])
        if include_all_processes:
            top_pids = sorted_pids[:150]
            pids_to_add = top_pids + [p for p in sorted_pids[150:] if p in selected_set]
        else:
            pids_to_add = [p for p in sorted_pids if p in selected_set]

        curve_colors = theme.get("curve_colors", [
            "#06b6d4", "#a855f7", "#ec4899", "#3b82f6",
            "#eab308", "#14b8a6", "#f97316", "#84cc16"
        ])

        for idx, pid in enumerate(pids_to_add):
            m = self.data.get_pid_metrics(pid)
            color = curve_colors[idx % len(curve_colors)]
            proc_title = m['args'] if len(m['args']) <= 60 else (m['args'][:57] + '...')
            p_label = f"PID {pid} ({proc_title})"
            is_visible = bool(selected_pids and pid in selected_set)

            # Primary Y: PID CPU Trace
            cpu_idx = trace_idx
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=m["cpu"],
                    name=f"{p_label} CPU%",
                    mode="lines",
                    line=dict(color=color, width=2),
                    visible=is_visible
                ),
                secondary_y=False
            )
            trace_idx += 1

            # Secondary Y: PID RES Memory Trace
            res_idx = trace_idx
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=m["res_mb"],
                    name=f"{p_label} RES MB",
                    mode="lines",
                    line=dict(color=color, width=1.2, dash="dash"),
                    visible=is_visible
                ),
                secondary_y=True
            )
            trace_idx += 1

            pid_traces[pid] = [cpu_idx, res_idx]

        fig.update_layout(
            template=theme.get("plotly_template", "plotly_dark"),
            paper_bgcolor=theme["bg_window"],
            plot_bgcolor=theme["bg_card"],
            font=dict(color=theme["fg_text"], family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
            hovermode="x unified",
            hoverlabel=dict(
                namelength=-1,
                bgcolor=theme["bg_card"],
                font=dict(color=theme["fg_text"], size=11, family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif")
            ),
            margin=dict(l=45, r=45, t=50, b=40),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color=theme["fg_text"], size=11)
            )
        )
        fig.update_xaxes(
            title_text="Timestamp",
            showgrid=True,
            gridcolor=theme["grid"],
            color=theme["fg_text"],
            linecolor=theme["border"]
        )
        fig.update_yaxes(
            title_text="CPU Usage (%)",
            secondary_y=False,
            showgrid=True,
            gridcolor=theme["grid"],
            color=theme["accent_cpu"]
        )
        fig.update_yaxes(
            title_text="Memory (MB)",
            secondary_y=True,
            showgrid=False,
            color=theme["accent_mem"]
        )

        fig._pid_trace_map = pid_traces
        fig._sys_trace_map = sys_traces
        fig._theme_name = theme_name
        return fig

    def generate_html(
        self,
        selected_pids: Optional[List[int]] = None,
        plot_sys_cpu: bool = True,
        plot_sys_mem: bool = True,
        plot_cpu_breakdown: bool = False,
        plot_sys_swap: bool = False,
        theme_name: str = "Dark Fusion",
        include_plotlyjs: bool = True
    ) -> str:
        """Generate self-contained interactive HTML dashboard with chart and full-control process table."""
        if theme_name not in THEMES:
            theme_name = "Dark Fusion"

        fig = self.create_figure(
            selected_pids=selected_pids,
            plot_sys_cpu=plot_sys_cpu,
            plot_sys_mem=plot_sys_mem,
            plot_cpu_breakdown=plot_cpu_breakdown,
            plot_sys_swap=plot_sys_swap,
            theme_name=theme_name,
            include_all_processes=True
        )

        plot_div = fig.to_html(
            include_plotlyjs=include_plotlyjs,
            full_html=False,
            div_id="telemetry_plot"
        )

        all_pids = self.data.get_all_pids()
        sorted_pids = sorted(all_pids, key=lambda p: self.data.get_pid_metrics(p)["max_cpu"], reverse=True)
        top_cpu_pids = sorted_pids[:5]
        top_mem_pids = sorted(all_pids, key=lambda p: self.data.get_pid_metrics(p)["max_res_mb"], reverse=True)[:5]
        selected_set = set(selected_pids or [])

        # Build Process Table Rows
        table_rows = []
        for pid in sorted_pids:
            m = self.data.get_pid_metrics(pid)
            cpu_vals = m["cpu"]
            avg_cpu = sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0.0
            mem_pct_vals = m.get("mem_pct", [0.0])
            max_mem_pct = max(mem_pct_vals) if mem_pct_vals else 0.0
            max_shr = max(m["shr_mb"]) if m.get("shr_mb") else 0.0
            checked_attr = "checked" if pid in selected_set else ""

            args_esc = html.escape(m["args"])
            user_esc = html.escape(m.get("user", ""))

            row_html = (
                f'<tr data-pid="{pid}">'
                f'<td style="text-align: center;"><input type="checkbox" class="proc-check" data-pid="{pid}" {checked_attr} /></td>'
                f'<td><span class="pid-badge">{pid}</span></td>'
                f'<td class="proc-args" title="{args_esc}">{args_esc}</td>'
                f'<td>{user_esc}</td>'
                f'<td class="num-cell highlight-cpu" data-val="{m["max_cpu"]:.2f}">{m["max_cpu"]:.1f}%</td>'
                f'<td class="num-cell" data-val="{avg_cpu:.2f}">{avg_cpu:.1f}%</td>'
                f'<td class="num-cell highlight-mem" data-val="{m["max_res_mb"]:.2f}">{m["max_res_mb"]:.1f} MB</td>'
                f'<td class="num-cell" data-val="{max_shr:.2f}">{max_shr:.1f} MB</td>'
                f'<td class="num-cell" data-val="{max_mem_pct:.2f}">{max_mem_pct:.1f}%</td>'
                f'</tr>'
            )
            table_rows.append(row_html)

        tbody_html = "\n".join(table_rows)

        # Build Theme Options
        theme_options = []
        for t_key in THEMES.keys():
            sel = "selected" if t_key == theme_name else ""
            theme_options.append(f'<option value="{t_key}" {sel}>{t_key}</option>')
        theme_options_html = "\n".join(theme_options)

        # JSON data for Client-Side JavaScript
        pid_trace_map_json = json.dumps(fig._pid_trace_map)
        sys_trace_map_json = json.dumps(fig._sys_trace_map)
        top_cpu_pids_json = json.dumps(top_cpu_pids)
        top_mem_pids_json = json.dumps(top_mem_pids)
        themes_dict_json = json.dumps(THEMES)

        theme_layouts = {}
        for t_name, t_val in THEMES.items():
            theme_layouts[t_name] = {
                "paper_bgcolor": t_val["bg_window"],
                "plot_bgcolor": t_val["bg_card"],
                "font": {"color": t_val["fg_text"]},
                "hoverlabel": {
                    "namelength": -1,
                    "bgcolor": t_val["bg_card"],
                    "font": {"color": t_val["fg_text"]}
                },
                "legend": {
                    "font": {"color": t_val["fg_text"], "size": 11},
                    "orientation": "h",
                    "yanchor": "bottom",
                    "y": 1.02,
                    "xanchor": "right",
                    "x": 1
                },
                "legend.font.color": t_val["fg_text"],
                "xaxis": {
                    "gridcolor": t_val["grid"],
                    "color": t_val["fg_text"],
                    "linecolor": t_val["border"]
                },
                "yaxis": {
                    "gridcolor": t_val["grid"],
                    "color": t_val["accent_cpu"]
                },
                "yaxis2": {
                    "color": t_val["accent_mem"]
                }
            }
        theme_layouts_json = json.dumps(theme_layouts)

        chk_sys_cpu_attr = "checked" if plot_sys_cpu else ""
        chk_sys_mem_attr = "checked" if plot_sys_mem else ""
        chk_cpu_breakdown_attr = "checked" if plot_cpu_breakdown else ""
        chk_sys_swap_attr = "checked" if plot_sys_swap else ""

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Top Log Telemetry Report - {theme_name}</title>
  <style>
    :root, [data-theme="Dark Fusion"] {{
      --bg-window: #111827;
      --bg-card: #1f2937;
      --bg-header: #374151;
      --fg-text: #f3f4f6;
      --fg-muted: #9ca3af;
      --border: #374151;
      --accent-cpu: #10b981;
      --accent-mem: #f59e0b;
      --grid: #4b5563;
    }}
    [data-theme="Light Mode"] {{
      --bg-window: #f8fafc;
      --bg-card: #ffffff;
      --bg-header: #e2e8f0;
      --fg-text: #0f172a;
      --fg-muted: #64748b;
      --border: #cbd5e1;
      --accent-cpu: #059669;
      --accent-mem: #d97706;
      --grid: #94a3b8;
    }}
    [data-theme="Midnight Neon"] {{
      --bg-window: #0a0e17;
      --bg-card: #111827;
      --bg-header: #1f293d;
      --fg-text: #e0e7ff;
      --fg-muted: #818cf8;
      --border: #312e81;
      --accent-cpu: #06b6d4;
      --accent-mem: #f43f5e;
      --grid: #1e293b;
    }}
    [data-theme="Solarized Dark"] {{
      --bg-window: #002b36;
      --bg-card: #073642;
      --bg-header: #094352;
      --fg-text: #93a1a1;
      --fg-muted: #657b83;
      --border: #586e75;
      --accent-cpu: #2aa198;
      --accent-mem: #b58900;
      --grid: #586e75;
    }}
    [data-theme="Monokai"] {{
      --bg-window: #1e1e1e;
      --bg-card: #252526;
      --bg-header: #333333;
      --fg-text: #f8f8f2;
      --fg-muted: #75715e;
      --border: #3e3e42;
      --accent-cpu: #a6e22e;
      --accent-mem: #fd971f;
      --grid: #49483e;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 16px;
      background-color: var(--bg-window);
      color: var(--fg-text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      transition: background-color 0.2s, color 0.2s;
    }}
    .dashboard-container {{
      max-width: 1600px;
      margin: 0 auto;
    }}
    .header-bar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-card);
      padding: 12px 20px;
      border-radius: 8px;
      border: 1px solid var(--border);
      margin-bottom: 16px;
      gap: 12px;
    }}
    .title-group {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .title-group h1 {{
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .badge {{
      background: var(--bg-header);
      color: var(--fg-muted);
      font-size: 0.8rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      font-weight: 500;
    }}
    .header-controls {{
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .toggle-label {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.88rem;
      font-weight: 500;
      cursor: pointer;
    }}
    .toggle-label input[type="checkbox"] {{
      cursor: pointer;
      accent-color: var(--accent-cpu);
      width: 16px;
      height: 16px;
    }}
    .theme-select {{
      background: var(--bg-window);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      cursor: pointer;
      outline: none;
    }}
    .theme-select:focus {{
      border-color: var(--accent-cpu);
    }}
    .plot-box {{
      background: var(--bg-card);
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 8px;
      margin-bottom: 20px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}
    /* SVG Plotly Legend text color override ensuring perfect theme contrast */
    .legend text, g.legend text, .js-plotly-plot .legend text {{
      fill: var(--fg-text) !important;
    }}
    .table-panel {{
      background: var(--bg-card);
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 16px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}
    .table-toolbar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .toolbar-left h2 {{
      margin: 0;
      font-size: 1.1rem;
      font-weight: 600;
    }}
    .toolbar-left .subtext {{
      color: var(--fg-muted);
      font-size: 0.82rem;
      display: block;
      margin-top: 2px;
    }}
    .toolbar-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .search-wrapper {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .search-input {{
      background: var(--bg-window);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      width: 240px;
      outline: none;
    }}
    .search-input:focus {{
      border-color: var(--accent-cpu);
    }}
    .btn-group {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .btn {{
      background: var(--bg-header);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .btn:hover {{
      background: var(--border);
      border-color: var(--accent-cpu);
    }}
    .table-scroll {{
      max-height: 440px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
    }}
    .telemetry-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }}
    .telemetry-table th {{
      position: sticky;
      top: 0;
      background: var(--bg-header);
      color: var(--fg-text);
      padding: 10px 12px;
      text-align: left;
      font-weight: 600;
      border-bottom: 2px solid var(--border);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      z-index: 2;
    }}
    .telemetry-table th:hover {{
      background: var(--border);
    }}
    .telemetry-table td {{
      padding: 7px 12px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    .telemetry-table tr:hover {{
      background-color: rgba(255, 255, 255, 0.04);
    }}
    .pid-badge {{
      background: var(--bg-window);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: monospace;
      font-weight: bold;
      border: 1px solid var(--border);
    }}
    .proc-args {{
      max-width: 420px;
      overflow: hidden;
      text-overflow: ellipsis;
      font-family: monospace;
    }}
    .num-cell {{
      text-align: right;
      font-family: monospace;
    }}
    .highlight-cpu {{
      color: var(--accent-cpu);
      font-weight: 600;
    }}
    .highlight-mem {{
      color: var(--accent-mem);
      font-weight: 600;
    }}
    .table-footer {{
      margin-top: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--fg-muted);
      font-size: 0.8rem;
    }}
    /* SVG Plotly Legend & Hover Box theme styling */
    .legend text, g.legend text, .js-plotly-plot .legend text {{
      fill: var(--fg-text) !important;
    }}
    .legend rect, g.legend rect {{
      fill: var(--bg-card) !important;
      stroke: var(--border) !important;
    }}
  </style>
</head>
<body data-theme="{theme_name}">
  <div class="dashboard-container">
    <div class="header-bar">
      <div class="title-group">
        <h1>Top Log Telemetry Explorer</h1>
        <span class="badge">{len(self.data.snapshots)} Snapshots</span>
        <span class="badge">{len(all_pids)} Total Processes</span>
      </div>
      <div class="header-controls">
        <label class="toggle-label">
          <input type="checkbox" id="chkSysCpu" {chk_sys_cpu_attr} />
          <span>System CPU%</span>
        </label>
        <label class="toggle-label">
          <input type="checkbox" id="chkSysMem" {chk_sys_mem_attr} />
          <span>System RAM MB</span>
        </label>
        <label class="toggle-label">
          <input type="checkbox" id="chkCpuBreakdown" {chk_cpu_breakdown_attr} />
          <span>CPU Breakdown</span>
        </label>
        <label class="toggle-label">
          <input type="checkbox" id="chkSysSwap" {chk_sys_swap_attr} />
          <span>System Swap MB</span>
        </label>
        <label class="toggle-label" style="margin-left: 8px;">
          <span>Theme:</span>
          <select id="htmlThemeSelect" class="theme-select">
            {theme_options_html}
          </select>
        </label>
      </div>
    </div>

    <div class="plot-box">
      {plot_div}
    </div>

    <div class="table-panel">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <h2>Process Telemetry Table</h2>
          <span class="subtext">Toggle checkboxes to interactively plot or hide any process in the chart above.</span>
        </div>
        <div class="toolbar-actions">
          <div class="search-wrapper">
            <input type="text" id="processSearch" class="search-input" placeholder="Filter processes (e.g. maps, system)..." />
            <label class="toggle-label" style="font-size: 0.8rem;">
              <input type="checkbox" id="chkHtmlRegex" />
              <span>Regex</span>
            </label>
          </div>
          <div class="btn-group">
            <button type="button" class="btn" id="btnTop5Cpu">Top 5 CPU</button>
            <button type="button" class="btn" id="btnTop5Mem">Top 5 MEM</button>
            <button type="button" class="btn" id="btnSelectAll">Select All</button>
            <button type="button" class="btn" id="btnClearAll">Clear All</button>
          </div>
        </div>
      </div>

      <div class="table-scroll">
        <table id="processTable" class="telemetry-table">
          <thead>
            <tr>
              <th style="width: 45px; text-align: center;"><input type="checkbox" id="thMasterCheck" title="Toggle Visible Rows" /></th>
              <th class="sortable" data-col="1" data-type="num">PID <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="2" data-type="str">Process Name / ARGS <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="3" data-type="str">User <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="4" data-type="num" style="text-align: right;">Max CPU% <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="5" data-type="num" style="text-align: right;">Avg CPU% <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="6" data-type="num" style="text-align: right;">Peak RES (MB) <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="7" data-type="num" style="text-align: right;">Peak SHR (MB) <span class="sort-icon">▲▼</span></th>
              <th class="sortable" data-col="8" data-type="num" style="text-align: right;">Max MEM% <span class="sort-icon">▲▼</span></th>
            </tr>
          </thead>
          <tbody>
            {tbody_html}
          </tbody>
        </table>
      </div>
      <div class="table-footer">
        <span id="rowCountLabel">Showing {len(sorted_pids)} of {len(sorted_pids)} processes</span>
        <span>Click any column header to sort</span>
      </div>
    </div>
  </div>

  <script>
    (function() {{
      const pidTraceMap = {pid_trace_map_json};
      const sysTraceMap = {sys_trace_map_json};
      const topCpuPids = {top_cpu_pids_json};
      const topMemPids = {top_mem_pids_json};
      const themeLayouts = {theme_layouts_json};
      const themesDict = {themes_dict_json};

      function hexToRgba(hex, alpha) {{
        if (!hex) return `rgba(16, 185, 129, ${{alpha}})`;
        let c = hex.replace('#', '');
        if (c.length === 3) c = c.split('').map(x => x + x).join('');
        const num = parseInt(c, 16);
        return `rgba(${{(num >> 16) & 255}}, ${{(num >> 8) & 255}}, ${{num & 255}}, ${{alpha}})`;
      }}

      function getPlotDiv() {{
        return document.getElementById('telemetry_plot');
      }}

      function toggleProcessTrace(pid, isVisible) {{
        const traces = pidTraceMap[pid];
        const plotDiv = getPlotDiv();
        if (traces && traces.length > 0 && plotDiv && typeof Plotly !== 'undefined') {{
          Plotly.restyle(plotDiv, {{ visible: isVisible ? true : false }}, traces);
        }}
      }}

      // Individual Process Checkbox Events
      document.querySelectorAll('.proc-check').forEach(function(chk) {{
        chk.addEventListener('change', function(e) {{
          const pid = parseInt(e.target.getAttribute('data-pid'), 10);
          toggleProcessTrace(pid, e.target.checked);
        }});
      }});

      // Master Checkbox Event (toggles visible rows)
      const masterCheck = document.getElementById('thMasterCheck');
      if (masterCheck) {{
        masterCheck.addEventListener('change', function(e) {{
          const checked = e.target.checked;
          const rows = document.querySelectorAll('#processTable tbody tr');
          rows.forEach(function(r) {{
            if (r.style.display !== 'none') {{
              const chk = r.querySelector('.proc-check');
              if (chk && chk.checked !== checked) {{
                chk.checked = checked;
                toggleProcessTrace(parseInt(chk.getAttribute('data-pid'), 10), checked);
              }}
            }}
          }});
        }});
      }}

      // System Metric Toggles
      const chkSysCpu = document.getElementById('chkSysCpu');
      if (chkSysCpu && sysTraceMap.sys_cpu !== undefined) {{
        chkSysCpu.addEventListener('change', function(e) {{
          const plotDiv = getPlotDiv();
          if (plotDiv && typeof Plotly !== 'undefined') {{
            Plotly.restyle(plotDiv, {{ visible: e.target.checked ? true : false }}, [sysTraceMap.sys_cpu]);
          }}
        }});
      }}

      const chkSysMem = document.getElementById('chkSysMem');
      if (chkSysMem && sysTraceMap.sys_mem !== undefined) {{
        chkSysMem.addEventListener('change', function(e) {{
          const plotDiv = getPlotDiv();
          if (plotDiv && typeof Plotly !== 'undefined') {{
            Plotly.restyle(plotDiv, {{ visible: e.target.checked ? true : false }}, [sysTraceMap.sys_mem]);
          }}
        }});
      }}

      const chkCpuBreakdown = document.getElementById('chkCpuBreakdown');
      const bdIndices = sysTraceMap.cpu_breakdown || Object.keys(sysTraceMap).filter(function(k) {{ return k.startsWith('bd_'); }}).map(function(k) {{ return sysTraceMap[k]; }});
      if (chkCpuBreakdown && bdIndices.length > 0) {{
        chkCpuBreakdown.addEventListener('change', function(e) {{
          const plotDiv = getPlotDiv();
          if (plotDiv && typeof Plotly !== 'undefined') {{
            Plotly.restyle(plotDiv, {{ visible: e.target.checked ? true : false }}, bdIndices);
          }}
        }});
      }}

      const chkSysSwap = document.getElementById('chkSysSwap');
      if (chkSysSwap && sysTraceMap.sys_swap !== undefined) {{
        chkSysSwap.addEventListener('change', function(e) {{
          const plotDiv = getPlotDiv();
          if (plotDiv && typeof Plotly !== 'undefined') {{
            Plotly.restyle(plotDiv, {{ visible: e.target.checked ? true : false }}, [sysTraceMap.sys_swap]);
          }}
        }});
      }}

      // Helper to batch set checked PIDs
      function setCheckedPids(targetPids) {{
        const targetSet = new Set(targetPids);
        document.querySelectorAll('.proc-check').forEach(function(chk) {{
          const pid = parseInt(chk.getAttribute('data-pid'), 10);
          const shouldCheck = targetSet.has(pid);
          if (chk.checked !== shouldCheck) {{
            chk.checked = shouldCheck;
            toggleProcessTrace(pid, shouldCheck);
          }}
        }});
      }}

      // Quick Action Buttons
      document.getElementById('btnTop5Cpu')?.addEventListener('click', function() {{
        setCheckedPids(topCpuPids);
      }});

      document.getElementById('btnTop5Mem')?.addEventListener('click', function() {{
        setCheckedPids(topMemPids);
      }});

      document.getElementById('btnClearAll')?.addEventListener('click', function() {{
        setCheckedPids([]);
        if (masterCheck) masterCheck.checked = false;
      }});

      document.getElementById('btnSelectAll')?.addEventListener('click', function() {{
        const visiblePids = [];
        document.querySelectorAll('#processTable tbody tr').forEach(function(r) {{
          if (r.style.display !== 'none') {{
            visiblePids.push(parseInt(r.getAttribute('data-pid'), 10));
          }}
        }});
        setCheckedPids(visiblePids);
        if (masterCheck) masterCheck.checked = true;
      }});

      // Search & Regex Filtering
      const searchInput = document.getElementById('processSearch');
      const chkRegex = document.getElementById('chkHtmlRegex');
      const countLabel = document.getElementById('rowCountLabel');

      function filterTableRows() {{
        const query = (searchInput ? searchInput.value : '').trim();
        const useRegex = chkRegex ? chkRegex.checked : false;
        let regexObj = null;

        if (useRegex && query) {{
          try {{
            regexObj = new RegExp(query, 'i');
            searchInput.style.borderColor = '';
          }} catch (err) {{
            searchInput.style.borderColor = '#ef4444';
            return;
          }}
        }} else {{
          if (searchInput) searchInput.style.borderColor = '';
        }}

        const queryLower = query.toLowerCase();
        const rows = document.querySelectorAll('#processTable tbody tr');
        let visibleCount = 0;

        rows.forEach(function(r) {{
          let matches = true;
          if (query) {{
            const rowText = r.innerText.toLowerCase();
            if (regexObj) {{
              matches = regexObj.test(r.innerText);
            }} else {{
              matches = rowText.includes(queryLower);
            }}
          }}
          r.style.display = matches ? '' : 'none';
          if (matches) visibleCount++;
        }});

        if (countLabel) {{
          countLabel.textContent = `Showing ${{visibleCount}} of ${{rows.length}} processes`;
        }}
      }}

      if (searchInput) searchInput.addEventListener('input', filterTableRows);
      if (chkRegex) chkRegex.addEventListener('change', filterTableRows);

      // Column Sorting Logic
      let sortColIndex = -1;
      let sortAscending = true;

      document.querySelectorAll('#processTable th.sortable').forEach(function(th) {{
        th.addEventListener('click', function() {{
          const colIndex = parseInt(th.getAttribute('data-col'), 10);
          const colType = th.getAttribute('data-type');
          if (sortColIndex === colIndex) {{
            sortAscending = !sortAscending;
          }} else {{
            sortColIndex = colIndex;
            sortAscending = true;
          }}

          document.querySelectorAll('#processTable th.sortable .sort-icon').forEach(function(icon) {{
            icon.textContent = '▲▼';
          }});
          const iconSpan = th.querySelector('.sort-icon');
          if (iconSpan) iconSpan.textContent = sortAscending ? '▲' : '▼';

          const tbody = document.querySelector('#processTable tbody');
          const rowsArray = Array.from(tbody.querySelectorAll('tr'));

          rowsArray.sort(function(a, b) {{
            const cellA = a.children[colIndex];
            const cellB = b.children[colIndex];
            if (!cellA || !cellB) return 0;

            const valA = cellA.getAttribute('data-val') !== null ? parseFloat(cellA.getAttribute('data-val')) : cellA.innerText.trim();
            const valB = cellB.getAttribute('data-val') !== null ? parseFloat(cellB.getAttribute('data-val')) : cellB.innerText.trim();

            if (colType === 'num') {{
              const numA = isNaN(valA) ? 0 : valA;
              const numB = isNaN(valB) ? 0 : valB;
              return sortAscending ? (numA - numB) : (numB - numA);
            }} else {{
              return sortAscending ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
            }}
          }});

          rowsArray.forEach(function(row) {{
            tbody.appendChild(row);
          }});
        }});
      }});

      // Theme Selector In Browser
      const themeSelect = document.getElementById('htmlThemeSelect');
      if (themeSelect) {{
        themeSelect.addEventListener('change', function(e) {{
          const chosenTheme = e.target.value;
          document.body.setAttribute('data-theme', chosenTheme);
          const t = themesDict[chosenTheme];
          const plotDiv = getPlotDiv();
          if (t && plotDiv && plotDiv.data && typeof Plotly !== 'undefined') {{
            // 1. Recolor data traces
            if (sysTraceMap.sys_cpu !== undefined && plotDiv.data[sysTraceMap.sys_cpu]) {{
              plotDiv.data[sysTraceMap.sys_cpu].line.color = t.accent_cpu;
              plotDiv.data[sysTraceMap.sys_cpu].fillcolor = hexToRgba(t.accent_cpu, 0.12);
              plotDiv.data[sysTraceMap.sys_cpu].hoverlabel = {{
                bgcolor: t.bg_card,
                bordercolor: t.accent_cpu,
                font: {{ color: t.fg_text, size: 11 }}
              }};
            }}
            if (sysTraceMap.sys_mem !== undefined && plotDiv.data[sysTraceMap.sys_mem]) {{
              plotDiv.data[sysTraceMap.sys_mem].line.color = t.accent_mem;
              plotDiv.data[sysTraceMap.sys_mem].hoverlabel = {{
                bgcolor: t.bg_card,
                bordercolor: t.accent_mem,
                font: {{ color: t.fg_text, size: 11 }}
              }};
            }}
            const curveCols = t.curve_colors;
            let pIdx = 0;
            for (const pid in pidTraceMap) {{
              const col = curveCols[pIdx % curveCols.length];
              const pTraces = pidTraceMap[pid];
              if (pTraces && pTraces.length === 2) {{
                const cpuT = plotDiv.data[pTraces[0]];
                const memT = plotDiv.data[pTraces[1]];
                if (cpuT && cpuT.line) {{
                  cpuT.line.color = col;
                  cpuT.hoverlabel = {{ bgcolor: t.bg_card, bordercolor: col, font: {{ color: t.fg_text, size: 11 }} }};
                }}
                if (memT && memT.line) {{
                  memT.line.color = col;
                  memT.hoverlabel = {{ bgcolor: t.bg_card, bordercolor: col, font: {{ color: t.fg_text, size: 11 }} }};
                }}
              }}
              pIdx++;
            }}

            // 2. Build updated layout
            const updatedLayout = {{
              ...plotDiv.layout,
              template: t.plotly_template || (chosenTheme === 'Light Mode' ? 'plotly_white' : 'plotly_dark'),
              paper_bgcolor: t.bg_window,
              plot_bgcolor: t.bg_card,
              font: {{ color: t.fg_text, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }},
              hovermode: "x unified",
              hoverlabel: {{
                namelength: -1,
                bgcolor: t.bg_card,
                bordercolor: t.border,
                font: {{ color: t.fg_text, size: 11, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }}
              }},
              legend: {{
                ...plotDiv.layout.legend,
                bgcolor: t.bg_card,
                bordercolor: t.border,
                borderwidth: 1,
                font: {{ color: t.fg_text, size: 11 }},
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                xanchor: "right",
                x: 1
              }},
              xaxis: {{
                ...plotDiv.layout.xaxis,
                title: "Timestamp",
                gridcolor: t.grid,
                color: t.fg_text,
                linecolor: t.border
              }},
              yaxis: {{
                ...plotDiv.layout.yaxis,
                title: "CPU Usage (%)",
                gridcolor: t.grid,
                color: t.accent_cpu
              }},
              yaxis2: {{
                ...plotDiv.layout.yaxis2,
                title: "Memory (MB)",
                color: t.accent_mem
              }}
            }};

            Plotly.react(plotDiv, plotDiv.data, updatedLayout);
          }}
        }});
      }}
    }})();
  </script>
</body>
</html>"""
        return html_template

    def save_html(
        self,
        output_path: str,
        selected_pids: Optional[List[int]] = None,
        plot_sys_cpu: bool = True,
        plot_sys_mem: bool = True,
        plot_cpu_breakdown: bool = False,
        plot_sys_swap: bool = False,
        theme_name: str = "Dark Fusion",
        include_plotlyjs: bool = True
    ) -> str:
        """Export standalone HTML file to disk."""
        html_str = self.generate_html(
            selected_pids=selected_pids,
            plot_sys_cpu=plot_sys_cpu,
            plot_sys_mem=plot_sys_mem,
            plot_cpu_breakdown=plot_cpu_breakdown,
            plot_sys_swap=plot_sys_swap,
            theme_name=theme_name,
            include_plotlyjs=include_plotlyjs
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_str)
        return output_path


def build_standalone_app(output_path: str = "top_log_analyzer_standalone.html") -> str:
    """Build a 100% self-contained, offline-capable single-page web app for parsing and plotting top logs."""
    try:
        import plotly.offline as po
        plotly_js = po.get_plotlyjs()
    except Exception:
        plotly_js = ""

    themes_json = json.dumps(THEMES)

    # Embedded sample snippet for instant 1-click Demo in the browser
    sample_demo_snippet = """20260917_17-33-01
top_cpu:
Tasks: 568 total,   2 running, 566 sleeping,   0 stopped,   0 zombie
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
 Swap:  4194300K total,   255488K used,  3938812K free,  2436928K cached
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S  3.4   5.5   1:40.49 system_server
 6864 u10_a160     20   0  18G 198M 125M S  6.8   2.6   2:36.19 com.android.vending:background
 3904 u10_a112     20   0  17G 156M 112M S  2.1   2.0   0:45.12 com.spotify.music
 1535 root         20   0 2.1G 45M   28M S  1.5   0.6   0:15.30 surfaceflinger

20260917_17-33-11
top_cpu:
Tasks: 567 total,   2 running, 565 sleeping,   0 stopped,   0 zombie
  Mem:  7594756K total,  6340152K used,  1254604K free,    15396K buffers
 Swap:  4194300K total,   254976K used,  3939324K free,  2531312K cached
800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 6864 u10_a160     20   0  18G 198M 125M S 84.3   2.6   2:44.43 com.android.vending:background
 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S 12.0   5.5   1:41.00 system_server
 3904 u10_a112     20   0  17G 158M 112M S 18.2   2.0   0:46.90 com.spotify.music
 1535 root         20   0 2.1G 45M   28M S  8.4   0.6   0:16.10 surfaceflinger

20260917_17-33-21
top_cpu:
Tasks: 567 total,   1 running, 566 sleeping,   0 stopped,   0 zombie
  Mem:  7594756K total,  6410200K used,  1184556K free,    15396K buffers
 Swap:  4194300K total,   254976K used,  3939324K free,  2531312K cached
800%cpu  72%user  85%nice  81%sys 422%idle  10%iow  15%irq   4%sirq  71%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 568M 328M S 75.4   7.6  11:20.22 com.google.android.apps.maps
 2078 system       18  -2  21G 412M 279M S 24.6   5.5   1:43.46 system_server
 6864 u10_a160     20   0  18G 199M 125M S 14.2   2.6   2:45.85 com.android.vending:background
 3904 u10_a112     20   0  17G 158M 112M S  5.1   2.0   0:47.41 com.spotify.music
 1535 root         20   0 2.1G 45M   28M S  4.2   0.6   0:16.52 surfaceflinger
"""
    sample_demo_json = json.dumps(sample_demo_snippet)

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Top Log Analyzer — Standalone Web App</title>
  <style>
    :root, [data-theme="Dark Fusion"] {
      --bg-window: #111827;
      --bg-card: #1f2937;
      --bg-header: #374151;
      --fg-text: #f3f4f6;
      --fg-muted: #9ca3af;
      --border: #374151;
      --accent-cpu: #10b981;
      --accent-mem: #f59e0b;
      --grid: #4b5563;
    }
    [data-theme="Light Mode"] {
      --bg-window: #f8fafc;
      --bg-card: #ffffff;
      --bg-header: #e2e8f0;
      --fg-text: #0f172a;
      --fg-muted: #64748b;
      --border: #cbd5e1;
      --accent-cpu: #059669;
      --accent-mem: #d97706;
      --grid: #94a3b8;
    }
    [data-theme="Midnight Neon"] {
      --bg-window: #0a0e17;
      --bg-card: #111827;
      --bg-header: #1f293d;
      --fg-text: #e0e7ff;
      --fg-muted: #818cf8;
      --border: #312e81;
      --accent-cpu: #06b6d4;
      --accent-mem: #f43f5e;
      --grid: #1e293b;
    }
    [data-theme="Solarized Dark"] {
      --bg-window: #002b36;
      --bg-card: #073642;
      --bg-header: #094352;
      --fg-text: #93a1a1;
      --fg-muted: #657b83;
      --border: #586e75;
      --accent-cpu: #2aa198;
      --accent-mem: #b58900;
      --grid: #586e75;
    }
    [data-theme="Monokai"] {
      --bg-window: #1e1e1e;
      --bg-card: #252526;
      --bg-header: #333333;
      --fg-text: #f8f8f2;
      --fg-muted: #75715e;
      --border: #3e3e42;
      --accent-cpu: #a6e22e;
      --accent-mem: #fd971f;
      --grid: #49483e;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 16px;
      background-color: var(--bg-window);
      color: var(--fg-text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      transition: background-color 0.2s, color 0.2s;
    }
    .dashboard-container {
      max-width: 1600px;
      margin: 0 auto;
    }
    .header-bar {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-card);
      padding: 12px 20px;
      border-radius: 8px;
      border: 1px solid var(--border);
      margin-bottom: 16px;
      gap: 12px;
    }
    .title-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .title-group h1 {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .badge {
      background: var(--bg-header);
      color: var(--fg-muted);
      font-size: 0.8rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      font-weight: 500;
    }
    .header-controls {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .toggle-label {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.88rem;
      font-weight: 500;
      cursor: pointer;
    }
    .toggle-label input[type="checkbox"] {
      cursor: pointer;
      accent-color: var(--accent-cpu);
      width: 16px;
      height: 16px;
    }
    .theme-select {
      background: var(--bg-window);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      cursor: pointer;
      outline: none;
    }
    .btn {
      background: var(--bg-header);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn:hover {
      background: var(--border);
      border-color: var(--accent-cpu);
    }
    .btn-accent {
      background: var(--accent-cpu);
      color: #ffffff;
      border-color: var(--accent-cpu);
    }
    .btn-accent:hover {
      opacity: 0.9;
    }
    .upload-card {
      background: var(--bg-card);
      border: 2px dashed var(--border);
      border-radius: 12px;
      padding: 40px 20px;
      text-align: center;
      margin-bottom: 24px;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .upload-card.dragover {
      border-color: var(--accent-cpu);
      background-color: rgba(16, 185, 129, 0.05);
      transform: scale(1.005);
    }
    .upload-icon {
      font-size: 2.8rem;
      margin-bottom: 12px;
    }
    .upload-card h3 {
      margin: 0 0 8px 0;
      font-size: 1.25rem;
    }
    .upload-card p {
      color: var(--fg-muted);
      margin: 0 0 16px 0;
      font-size: 0.88rem;
    }
    .file-input {
      display: none;
    }
    .session-pills {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .session-pill {
      background: var(--bg-header);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.82rem;
      cursor: pointer;
      font-weight: 500;
    }
    .session-pill.active {
      background: var(--accent-cpu);
      color: #ffffff;
      border-color: var(--accent-cpu);
    }
    .plot-box {
      background: var(--bg-card);
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 8px;
      margin-bottom: 20px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .table-panel {
      background: var(--bg-card);
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 16px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .table-toolbar {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }
    .toolbar-left h2 {
      margin: 0;
      font-size: 1.1rem;
      font-weight: 600;
    }
    .toolbar-left .subtext {
      color: var(--fg-muted);
      font-size: 0.82rem;
      display: block;
      margin-top: 2px;
    }
    .toolbar-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-wrapper {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .search-input {
      background: var(--bg-window);
      color: var(--fg-text);
      border: 1px solid var(--border);
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      width: 260px;
      outline: none;
    }
    .search-input:focus {
      border-color: var(--accent-cpu);
    }
    .btn-group {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .table-scroll {
      max-height: 440px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
    }
    .telemetry-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    .telemetry-table th {
      position: sticky;
      top: 0;
      background: var(--bg-header);
      color: var(--fg-text);
      padding: 10px 12px;
      text-align: left;
      font-weight: 600;
      border-bottom: 2px solid var(--border);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      z-index: 2;
    }
    .telemetry-table th:hover {
      background: var(--border);
    }
    .telemetry-table td {
      padding: 7px 12px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    .telemetry-table tr:hover {
      background-color: rgba(255, 255, 255, 0.04);
    }
    .pid-badge {
      background: var(--bg-window);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: monospace;
      font-weight: bold;
      border: 1px solid var(--border);
    }
    .proc-args {
      max-width: 440px;
      overflow: hidden;
      text-overflow: ellipsis;
      font-family: monospace;
    }
    .num-cell {
      text-align: right;
      font-family: monospace;
    }
    .highlight-cpu {
      color: var(--accent-cpu);
      font-weight: 600;
    }
    .highlight-mem {
      color: var(--accent-mem);
      font-weight: 600;
    }
    .table-footer {
      margin-top: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--fg-muted);
      font-size: 0.8rem;
    }
    /* SVG Plotly Legend & Hover Box theme styling */
    .legend text, g.legend text, .js-plotly-plot .legend text {
      fill: var(--fg-text) !important;
    }
    .legend rect, g.legend rect {
      fill: var(--bg-card) !important;
      stroke: var(--border) !important;
    }
  </style>
  __PLOTLY_SCRIPT_TAG__
</head>
<body data-theme="Dark Fusion">
  <div class="dashboard-container">
    <!-- Header Bar -->
    <div class="header-bar">
      <div class="title-group">
        <h1>⚡ Top Log Analyzer — Standalone Web Edition</h1>
        <span class="badge" id="appModeBadge">Client-Side • Offline Ready</span>
      </div>
      <div class="header-controls">
        <button type="button" class="btn" id="btnUploadToggle">📂 Upload Logs</button>
        <button type="button" class="btn btn-accent" id="btnLoadDemo">🚀 Load Demo Log</button>
        <label class="toggle-label" style="margin-left: 6px;">
          <span>Theme:</span>
          <select id="htmlThemeSelect" class="theme-select">
            <option value="Dark Fusion" selected>Dark Fusion</option>
            <option value="Light Mode">Light Mode</option>
            <option value="Midnight Neon">Midnight Neon</option>
            <option value="Solarized Dark">Solarized Dark</option>
            <option value="Monokai">Monokai</option>
          </select>
        </label>
      </div>
    </div>

    <!-- Drop Zone -->
    <div id="dropZone" class="upload-card">
      <div class="upload-icon">📂</div>
      <h3>Drag & Drop Top Log Files Here</h3>
      <p>Supports automotive <code>log_top@...</code> and <code>log_topmen@...</code> paired files or standard Linux/Android top logs.<br>
      Parsed 100% locally in your browser with zero server roundtrips.</p>
      <button type="button" class="btn btn-accent" id="btnBrowseFiles">Browse Files</button>
      <input type="file" id="fileInput" class="file-input" multiple accept=".log,.txt" />
    </div>

    <!-- Session Navigation Pills -->
    <div id="sessionPills" class="session-pills" style="display: none;"></div>

    <!-- Telemetry Dashboard -->
    <div id="telemetryView" style="display: none;">
      <div class="header-bar" style="margin-bottom: 12px;">
        <div class="title-group">
          <h2 id="currentSessionTitle" style="margin: 0; font-size: 1.15rem;">Session</h2>
          <span class="badge" id="snapshotBadge">0 Snapshots</span>
          <span class="badge" id="processBadge">0 Processes</span>
        </div>
        <div class="header-controls">
          <label class="toggle-label"><input type="checkbox" id="chkSysCpu" checked /> <span>System CPU%</span></label>
          <label class="toggle-label"><input type="checkbox" id="chkSysMem" checked /> <span>System RAM MB</span></label>
          <label class="toggle-label"><input type="checkbox" id="chkCpuBreakdown" /> <span>CPU Breakdown</span></label>
          <label class="toggle-label"><input type="checkbox" id="chkSysSwap" /> <span>System Swap MB</span></label>
          <button type="button" class="btn" id="btnDownloadCsv">📊 Download CSV</button>
          <button type="button" class="btn" id="btnDownloadJson">📋 Download JSON</button>
        </div>
      </div>

      <div class="plot-box">
        <div id="telemetry_plot" style="width: 100%; height: 500px;"></div>
      </div>

      <div class="table-panel">
        <div class="table-toolbar">
          <div class="toolbar-left">
            <h2>Process Telemetry Table</h2>
            <span class="subtext">Toggle checkboxes to interactively plot or hide any process in the chart above.</span>
          </div>
          <div class="toolbar-actions">
            <div class="search-wrapper">
              <input type="text" id="processSearch" class="search-input" placeholder="Filter processes (e.g. maps, system)..." />
              <label class="toggle-label" style="font-size: 0.8rem;">
                <input type="checkbox" id="chkHtmlRegex" />
                <span>Regex</span>
              </label>
            </div>
            <div class="btn-group">
              <button type="button" class="btn" id="btnTop5Cpu">Top 5 CPU</button>
              <button type="button" class="btn" id="btnTop5Mem">Top 5 MEM</button>
              <button type="button" class="btn" id="btnSelectAll">Select All</button>
              <button type="button" class="btn" id="btnClearAll">Clear All</button>
            </div>
          </div>
        </div>

        <div class="table-scroll">
          <table id="processTable" class="telemetry-table">
            <thead>
              <tr>
                <th style="width: 45px; text-align: center;"><input type="checkbox" id="thMasterCheck" title="Toggle Visible Rows" /></th>
                <th class="sortable" data-col="1" data-type="num">PID <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="2" data-type="str">Process Name / ARGS <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="3" data-type="str">User <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="4" data-type="num" style="text-align: right;">Max CPU% <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="5" data-type="num" style="text-align: right;">Avg CPU% <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="6" data-type="num" style="text-align: right;">Peak RES (MB) <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="7" data-type="num" style="text-align: right;">Peak SHR (MB) <span class="sort-icon">▲▼</span></th>
                <th class="sortable" data-col="8" data-type="num" style="text-align: right;">Max MEM% <span class="sort-icon">▲▼</span></th>
              </tr>
            </thead>
            <tbody id="processTableBody"></tbody>
          </table>
        </div>
        <div class="table-footer">
          <span id="rowCountLabel">Showing 0 of 0 processes</span>
          <span>Click any column header to sort</span>
        </div>
      </div>
    </div>
  </div>

  <script>
    const THEMES = __THEMES_JSON__;
    const DEMO_SNIPPET = __SAMPLE_DEMO_JSON__;

    // Parsed sessions store: { sessionKey: { label, timestamps, systemMetrics, pidData, topCpuPids, topMemPids } }
    const loadedSessions = {};
    let activeSessionKey = null;
    let pidTraceMap = {};
    let sysTraceMap = {};

    function hexToRgba(hex, alpha) {
      if (!hex) return `rgba(16, 185, 129, ${alpha})`;
      let c = hex.replace('#', '');
      if (c.length === 3) c = c.split('').map(x => x + x).join('');
      const num = parseInt(c, 16);
      return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
    }

    function parseMemoryMb(valStr) {
      if (!valStr) return 0.0;
      valStr = String(valStr).trim();
      const lastChar = valStr.slice(-1).toUpperCase();
      const numPart = parseFloat(valStr.slice(0, -1));
      if (!isNaN(numPart)) {
        if (lastChar === 'G') return numPart * 1024.0;
        if (lastChar === 'M') return numPart;
        if (lastChar === 'K') return numPart / 1024.0;
      }
      const fullNum = parseFloat(valStr);
      return isNaN(fullNum) ? 0.0 : fullNum / 1024.0;
    }

    function parseTopLog(content, filename) {
      const lines = content.split(/\\r?\\n/);
      const timestamps = [];
      const systemMetrics = {
        "%cpu_total": [],
        "mem_used_mb": [],
        "swap_used_mb": [],
        "%user": [],
        "%sys": [],
        "%nice": [],
        "%irq": [],
        "%sirq": [],
        "%iow": []
      };
      const pidData = {};

      let currentTs = null;
      let currentCpu = 0.0;
      let currentMem = 0.0;
      let currentSwap = 0.0;
      let currentCpuBreakdown = { "%user": 0.0, "%sys": 0.0, "%nice": 0.0, "%irq": 0.0, "%sirq": 0.0, "%iow": 0.0 };
      let currentPidsInSnapshot = {};
      let inProcTable = false;

      const tsRegex = /^(\\d{8}[_-]\\d{2}[-:]\\d{2}[-:]\\d{2}|\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2}|\\d{8}_\\d{6})/;
      const memRegex = /Mem:\\s+(\\d+[KkMmGg]?)\\s+total,\\s+(\\d+[KkMmGg]?)\\s+used/i;
      const swapRegex = /Swap:\\s+(\\d+[KkMmGg]?)\\s+total,\\s+(\\d+[KkMmGg]?)\\s+used/i;
      const cpuRegex = /(\\d+)%cpu\\s+(\\d+)%user\\s+(\\d+)%nice\\s+(\\d+)%sys\\s+(\\d+)%idle(?:\\s+(\\d+)%iow)?(?:\\s+(\\d+)%irq)?(?:\\s+(\\d+)%sirq)?/i;
      const procRegex = /^\\s*(\\d+)\\s+(\\S+)\\s+(\\S+)\\s+(\\S+)\\s+(\\S+)\\s+(\\S+)\\s+(\\S+)\\s+([RSDZTtWw])\\s+(\\d+(?:\\.\\d+)?)\\s+(\\d+(?:\\.\\d+)?)\\s+(\\S+)\\s+(.+)$/;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const tsMatch = line.match(tsRegex);
        if (tsMatch) {
          if (currentTs !== null) {
            timestamps.push(currentTs);
            systemMetrics["%cpu_total"].push(currentCpu);
            systemMetrics["mem_used_mb"].push(currentMem);
            systemMetrics["swap_used_mb"].push(currentSwap);
            systemMetrics["%user"].push(currentCpuBreakdown["%user"]);
            systemMetrics["%sys"].push(currentCpuBreakdown["%sys"]);
            systemMetrics["%nice"].push(currentCpuBreakdown["%nice"]);
            systemMetrics["%irq"].push(currentCpuBreakdown["%irq"]);
            systemMetrics["%sirq"].push(currentCpuBreakdown["%sirq"]);
            systemMetrics["%iow"].push(currentCpuBreakdown["%iow"]);
            for (const pid in pidData) {
              if (!currentPidsInSnapshot[pid]) {
                pidData[pid].cpu.push(0.0);
                const lastRes = pidData[pid].res_mb.length ? pidData[pid].res_mb[pidData[pid].res_mb.length - 1] : 0.0;
                pidData[pid].res_mb.push(lastRes);
                const lastShr = pidData[pid].shr_mb.length ? pidData[pid].shr_mb[pidData[pid].shr_mb.length - 1] : 0.0;
                pidData[pid].shr_mb.push(lastShr);
                pidData[pid].mem_pct.push(0.0);
              }
            }
          }
          currentTs = tsMatch[1];
          currentCpu = 0.0;
          currentMem = 0.0;
          currentSwap = 0.0;
          currentCpuBreakdown = { "%user": 0.0, "%sys": 0.0, "%nice": 0.0, "%irq": 0.0, "%sirq": 0.0, "%iow": 0.0 };
          currentPidsInSnapshot = {};
          inProcTable = false;
          continue;
        }

        if (!currentTs) continue;

        const memMatch = line.match(memRegex);
        if (memMatch) {
          currentMem = parseMemoryMb(memMatch[2]);
          continue;
        }

        const swapMatch = line.match(swapRegex);
        if (swapMatch) {
          currentSwap = parseMemoryMb(swapMatch[2]);
          continue;
        }

        const cpuMatch = line.match(cpuRegex);
        if (cpuMatch) {
          const cap = parseFloat(cpuMatch[1]);
          const user = parseFloat(cpuMatch[2]) || 0.0;
          const nice = parseFloat(cpuMatch[3]) || 0.0;
          const sys = parseFloat(cpuMatch[4]) || 0.0;
          const idle = parseFloat(cpuMatch[5]) || 0.0;
          const iow = parseFloat(cpuMatch[6]) || 0.0;
          const irq = parseFloat(cpuMatch[7]) || 0.0;
          const sirq = parseFloat(cpuMatch[8]) || 0.0;
          currentCpu = Math.max(0.0, cap - idle);
          currentCpuBreakdown = {
            "%user": user,
            "%sys": sys,
            "%nice": nice,
            "%irq": irq,
            "%sirq": sirq,
            "%iow": iow
          };
          continue;
        }

        if (line.includes("PID") && line.includes("USER") && (line.includes("ARGS") || line.includes("CMD"))) {
          inProcTable = true;
          continue;
        }

        if (inProcTable) {
          const pMatch = line.match(procRegex);
          if (pMatch) {
            const pid = parseInt(pMatch[1], 10);
            const user = pMatch[2];
            const resMb = parseMemoryMb(pMatch[6]);
            const shrMb = parseMemoryMb(pMatch[7]);
            const cpu = parseFloat(pMatch[9]);
            const memPct = parseFloat(pMatch[10]);
            const args = pMatch[12].trim();

            if (!pidData[pid]) {
              pidData[pid] = {
                pid: pid,
                user: user,
                args: args,
                cpu: new Array(timestamps.length).fill(0.0),
                res_mb: new Array(timestamps.length).fill(0.0),
                shr_mb: new Array(timestamps.length).fill(0.0),
                mem_pct: new Array(timestamps.length).fill(0.0),
                max_cpu: 0.0,
                max_res_mb: 0.0,
                max_shr_mb: 0.0
              };
            }

            pidData[pid].cpu.push(cpu);
            pidData[pid].res_mb.push(resMb);
            pidData[pid].shr_mb.push(shrMb);
            pidData[pid].mem_pct.push(memPct);
            if (cpu > pidData[pid].max_cpu) pidData[pid].max_cpu = cpu;
            if (resMb > pidData[pid].max_res_mb) pidData[pid].max_res_mb = resMb;
            if (shrMb > pidData[pid].max_shr_mb) pidData[pid].max_shr_mb = shrMb;
            if (args && args.length > pidData[pid].args.length) pidData[pid].args = args;
            currentPidsInSnapshot[pid] = true;
          }
        }
      }

      // Finalize last snapshot
      if (currentTs !== null) {
        timestamps.push(currentTs);
        systemMetrics["%cpu_total"].push(currentCpu);
        systemMetrics["mem_used_mb"].push(currentMem);
        systemMetrics["swap_used_mb"].push(currentSwap);
        systemMetrics["%user"].push(currentCpuBreakdown["%user"]);
        systemMetrics["%sys"].push(currentCpuBreakdown["%sys"]);
        systemMetrics["%nice"].push(currentCpuBreakdown["%nice"]);
        systemMetrics["%irq"].push(currentCpuBreakdown["%irq"]);
        systemMetrics["%sirq"].push(currentCpuBreakdown["%sirq"]);
        systemMetrics["%iow"].push(currentCpuBreakdown["%iow"]);
        for (const pid in pidData) {
          if (!currentPidsInSnapshot[pid]) {
            pidData[pid].cpu.push(0.0);
            const lastRes = pidData[pid].res_mb.length ? pidData[pid].res_mb[pidData[pid].res_mb.length - 1] : 0.0;
            pidData[pid].res_mb.push(lastRes);
            const lastShr = pidData[pid].shr_mb.length ? pidData[pid].shr_mb[pidData[pid].shr_mb.length - 1] : 0.0;
            pidData[pid].shr_mb.push(lastShr);
            pidData[pid].mem_pct.push(0.0);
          }
        }
      }

      const allPids = Object.keys(pidData).map(p => parseInt(p, 10));
      const sortedByCpu = allPids.slice().sort((a, b) => pidData[b].max_cpu - pidData[a].max_cpu);
      const sortedByMem = allPids.slice().sort((a, b) => pidData[b].max_res_mb - pidData[a].max_res_mb);

      return {
        label: filename || "Telemetry Session",
        timestamps: timestamps,
        systemMetrics: systemMetrics,
        pidData: pidData,
        allPids: sortedByCpu,
        topCpuPids: sortedByCpu.slice(0, 5),
        topMemPids: sortedByMem.slice(0, 5)
      };
    }

    function renderSession(sessionKey) {
      const session = loadedSessions[sessionKey];
      if (!session) return;
      activeSessionKey = sessionKey;

      document.getElementById('currentSessionTitle').textContent = session.label;
      document.getElementById('snapshotBadge').textContent = `${session.timestamps.length} Snapshots`;
      document.getElementById('processBadge').textContent = `${session.allPids.length} Processes`;
      document.getElementById('telemetryView').style.display = 'block';

      // Update pills
      document.querySelectorAll('.session-pill').forEach(p => {
        p.classList.toggle('active', p.getAttribute('data-key') === sessionKey);
      });

      const currentTheme = document.body.getAttribute('data-theme') || 'Dark Fusion';
      const theme = THEMES[currentTheme] || THEMES['Dark Fusion'];

      // Build Plotly Traces
      const traces = [];
      let traceIdx = 0;
      sysTraceMap = {};
      pidTraceMap = {};

      // 1. Sys CPU
      traces.push({
        x: session.timestamps,
        y: session.systemMetrics["%cpu_total"],
        name: "System Total CPU%",
        type: "scatter",
        mode: "lines",
        line: { color: theme.accent_cpu, width: 2 },
        fill: "tozeroy",
        fillcolor: hexToRgba(theme.accent_cpu, 0.12),
        hoverlabel: {
          bgcolor: theme.bg_card,
          bordercolor: theme.accent_cpu,
          font: { color: theme.fg_text, size: 11 }
        },
        visible: document.getElementById('chkSysCpu').checked,
        yaxis: "y"
      });
      sysTraceMap.sys_cpu = traceIdx++;

      // 2. Sys RAM
      traces.push({
        x: session.timestamps,
        y: session.systemMetrics["mem_used_mb"],
        name: "System RAM Used (MB)",
        type: "scatter",
        mode: "lines",
        line: { color: theme.accent_mem, width: 1.5, dash: "dot" },
        hoverlabel: {
          bgcolor: theme.bg_card,
          bordercolor: theme.accent_mem,
          font: { color: theme.fg_text, size: 11 }
        },
        visible: document.getElementById('chkSysMem').checked,
        yaxis: "y2"
      });
      sysTraceMap.sys_mem = traceIdx++;

      // Sys Swap
      if (session.systemMetrics["swap_used_mb"] && session.systemMetrics["swap_used_mb"].length > 0) {
        const isSwapChecked = document.getElementById('chkSysSwap') ? document.getElementById('chkSysSwap').checked : false;
        traces.push({
          x: session.timestamps,
          y: session.systemMetrics["swap_used_mb"],
          name: "System Swap Used (MB)",
          type: "scatter",
          mode: "lines",
          line: { color: "#f43f5e", width: 1.5, dash: "dashdot" },
          hoverlabel: {
            bgcolor: theme.bg_card,
            bordercolor: "#f43f5e",
            font: { color: theme.fg_text, size: 11 }
          },
          visible: isSwapChecked,
          yaxis: "y2"
        });
        sysTraceMap.sys_swap = traceIdx++;
      }

      // CPU Breakdown stacked area traces
      const breakdownLabels = [
        ["%user", "CPU %user"],
        ["%sys", "CPU %sys"],
        ["%nice", "CPU %nice"],
        ["%irq", "CPU %irq"],
        ["%sirq", "CPU %sirq"],
        ["%iow", "CPU %iow"]
      ];
      const breakdownColors = ["#3b82f6", "#ef4444", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4"];
      const isBreakdownChecked = document.getElementById('chkCpuBreakdown') ? document.getElementById('chkCpuBreakdown').checked : false;
      const bdTraceIndices = [];

      breakdownLabels.forEach(([key, label], bIdx) => {
        if (session.systemMetrics[key] && session.systemMetrics[key].length > 0) {
          const col = breakdownColors[bIdx % breakdownColors.length];
          const bdIdx = traceIdx++;
          bdTraceIndices.push(bdIdx);
          sysTraceMap[`bd_${key}`] = bdIdx;
          traces.push({
            x: session.timestamps,
            y: session.systemMetrics[key],
            name: label,
            type: "scatter",
            mode: "lines",
            line: { color: col, width: 1.5 },
            fill: "tozeroy",
            fillcolor: hexToRgba(col, 0.15),
            stackgroup: "cpubreakdown",
            hoverlabel: {
              bgcolor: theme.bg_card,
              bordercolor: col,
              font: { color: theme.fg_text, size: 11 }
            },
            visible: isBreakdownChecked,
            yaxis: "y"
          });
        }
      });
      sysTraceMap.cpu_breakdown = bdTraceIndices;

      // 3. Processes (top 4 checked initially)
      const initialChecked = new Set(session.topCpuPids.slice(0, 4));
      const curveColors = theme.curve_colors;

      session.allPids.forEach((pid, idx) => {
        const p = session.pidData[pid];
        const col = curveColors[idx % curveColors.length];
        const isChecked = initialChecked.has(pid);
        const procTitle = p.args.length <= 60 ? p.args : (p.args.slice(0, 57) + "...");
        const label = `PID ${pid} (${procTitle})`;

        const cpuIdx = traceIdx++;
        traces.push({
          x: session.timestamps,
          y: p.cpu,
          name: `${label} CPU%`,
          type: "scatter",
          mode: "lines",
          line: { color: col, width: 2 },
          hoverlabel: {
            bgcolor: theme.bg_card,
            bordercolor: col,
            font: { color: theme.fg_text, size: 11 }
          },
          visible: isChecked,
          yaxis: "y"
        });

        const resIdx = traceIdx++;
        traces.push({
          x: session.timestamps,
          y: p.res_mb,
          name: `${label} RES MB`,
          type: "scatter",
          mode: "lines",
          line: { color: col, width: 1.2, dash: "dash" },
          hoverlabel: {
            bgcolor: theme.bg_card,
            bordercolor: col,
            font: { color: theme.fg_text, size: 11 }
          },
          visible: isChecked,
          yaxis: "y2"
        });

        pidTraceMap[pid] = [cpuIdx, resIdx];
      });

      const layout = {
        template: theme.plotly_template || (currentTheme === "Light Mode" ? "plotly_white" : "plotly_dark"),
        paper_bgcolor: theme.bg_window,
        plot_bgcolor: theme.bg_card,
        font: { color: theme.fg_text, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
        hovermode: "x unified",
        hoverlabel: {
          namelength: -1,
          bgcolor: theme.bg_card,
          bordercolor: theme.border,
          font: { color: theme.fg_text, size: 11, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }
        },
        margin: { l: 45, r: 45, t: 50, b: 40 },
        legend: {
          orientation: "h",
          yanchor: "bottom",
          y: 1.02,
          xanchor: "right",
          x: 1,
          bgcolor: theme.bg_card,
          bordercolor: theme.border,
          borderwidth: 1,
          font: { color: theme.fg_text, size: 11 }
        },
        xaxis: {
          title: "Timestamp",
          showgrid: true,
          gridcolor: theme.grid,
          color: theme.fg_text,
          linecolor: theme.border
        },
        yaxis: {
          title: "CPU Usage (%)",
          showgrid: true,
          gridcolor: theme.grid,
          color: theme.accent_cpu
        },
        yaxis2: {
          title: "Memory (MB)",
          overlaying: "y",
          side: "right",
          showgrid: false,
          color: theme.accent_mem
        }
      };

      Plotly.newPlot("telemetry_plot", traces, layout, { responsive: true });

      // Populate Table
      const tbody = document.getElementById("processTableBody");
      tbody.innerHTML = "";

      session.allPids.forEach(pid => {
        const p = session.pidData[pid];
        const isChecked = initialChecked.has(pid);
        const avgCpu = p.cpu.length ? (p.cpu.reduce((a, b) => a + b, 0) / p.cpu.length) : 0.0;
        const maxMemPct = p.mem_pct.length ? Math.max(...p.mem_pct) : 0.0;
        const maxShrMb = p.max_shr_mb !== undefined ? p.max_shr_mb : (p.shr_mb && p.shr_mb.length ? Math.max(...p.shr_mb) : 0.0);

        const tr = document.createElement("tr");
        tr.setAttribute("data-pid", pid);
        tr.innerHTML = `
          <td style="text-align: center;"><input type="checkbox" class="proc-check" data-pid="${pid}" ${isChecked ? 'checked' : ''} /></td>
          <td><span class="pid-badge">${pid}</span></td>
          <td class="proc-args" title="${p.args.replace(/"/g, '&quot;')}">${p.args.replace(/</g, '&lt;')}</td>
          <td>${(p.user || '').replace(/</g, '&lt;')}</td>
          <td class="num-cell highlight-cpu" data-val="${p.max_cpu.toFixed(2)}">${p.max_cpu.toFixed(1)}%</td>
          <td class="num-cell" data-val="${avgCpu.toFixed(2)}">${avgCpu.toFixed(1)}%</td>
          <td class="num-cell highlight-mem" data-val="${p.max_res_mb.toFixed(2)}">${p.max_res_mb.toFixed(1)} MB</td>
          <td class="num-cell" data-val="${maxShrMb.toFixed(2)}">${maxShrMb.toFixed(1)} MB</td>
          <td class="num-cell" data-val="${maxMemPct.toFixed(2)}">${maxMemPct.toFixed(1)}%</td>
        `;
        tbody.appendChild(tr);
      });

      document.getElementById('rowCountLabel').textContent = `Showing ${session.allPids.length} of ${session.allPids.length} processes`;
      bindTableEvents();
    }

    function toggleTrace(pid, visible) {
      const traces = pidTraceMap[pid];
      const plotDiv = document.getElementById('telemetry_plot');
      if (traces && plotDiv && typeof Plotly !== 'undefined') {
        Plotly.restyle(plotDiv, { visible: visible }, traces);
      }
    }

    function bindTableEvents() {
      // Individual Checkboxes
      document.querySelectorAll('.proc-check').forEach(chk => {
        chk.addEventListener('change', (e) => {
          const pid = parseInt(e.target.getAttribute('data-pid'), 10);
          toggleTrace(pid, e.target.checked);
        });
      });

      // Master Checkbox
      const masterCheck = document.getElementById('thMasterCheck');
      if (masterCheck) {
        masterCheck.checked = false;
        masterCheck.addEventListener('change', (e) => {
          const checked = e.target.checked;
          document.querySelectorAll('#processTableBody tr').forEach(r => {
            if (r.style.display !== 'none') {
              const chk = r.querySelector('.proc-check');
              if (chk && chk.checked !== checked) {
                chk.checked = checked;
                toggleTrace(parseInt(chk.getAttribute('data-pid'), 10), checked);
              }
            }
          });
        });
      }
    }

    function setTargetPidsChecked(targetPids) {
      const targetSet = new Set(targetPids);
      document.querySelectorAll('.proc-check').forEach(chk => {
        const pid = parseInt(chk.getAttribute('data-pid'), 10);
        const shouldCheck = targetSet.has(pid);
        if (chk.checked !== shouldCheck) {
          chk.checked = shouldCheck;
          toggleTrace(pid, shouldCheck);
        }
      });
    }

    // Quick Action Buttons
    document.getElementById('btnTop5Cpu')?.addEventListener('click', () => {
      if (activeSessionKey && loadedSessions[activeSessionKey]) {
        setTargetPidsChecked(loadedSessions[activeSessionKey].topCpuPids);
      }
    });

    document.getElementById('btnTop5Mem')?.addEventListener('click', () => {
      if (activeSessionKey && loadedSessions[activeSessionKey]) {
        setTargetPidsChecked(loadedSessions[activeSessionKey].topMemPids);
      }
    });

    document.getElementById('btnClearAll')?.addEventListener('click', () => {
      setTargetPidsChecked([]);
      const mc = document.getElementById('thMasterCheck');
      if (mc) mc.checked = false;
    });

    document.getElementById('btnSelectAll')?.addEventListener('click', () => {
      const visiblePids = [];
      document.querySelectorAll('#processTableBody tr').forEach(r => {
        if (r.style.display !== 'none') {
          visiblePids.push(parseInt(r.getAttribute('data-pid'), 10));
        }
      });
      setTargetPidsChecked(visiblePids);
      const mc = document.getElementById('thMasterCheck');
      if (mc) mc.checked = true;
    });

    // System Metric Checkbox Toggles
    document.getElementById('chkSysCpu')?.addEventListener('change', (e) => {
      const plotDiv = document.getElementById('telemetry_plot');
      if (plotDiv && typeof Plotly !== 'undefined' && sysTraceMap.sys_cpu !== undefined) {
        Plotly.restyle(plotDiv, { visible: e.target.checked }, [sysTraceMap.sys_cpu]);
      }
    });

    document.getElementById('chkSysMem')?.addEventListener('change', (e) => {
      const plotDiv = document.getElementById('telemetry_plot');
      if (plotDiv && typeof Plotly !== 'undefined' && sysTraceMap.sys_mem !== undefined) {
        Plotly.restyle(plotDiv, { visible: e.target.checked }, [sysTraceMap.sys_mem]);
      }
    });

    document.getElementById('chkCpuBreakdown')?.addEventListener('change', (e) => {
      const plotDiv = document.getElementById('telemetry_plot');
      if (plotDiv && typeof Plotly !== 'undefined' && sysTraceMap.cpu_breakdown) {
        Plotly.restyle(plotDiv, { visible: e.target.checked }, sysTraceMap.cpu_breakdown);
      }
    });

    document.getElementById('chkSysSwap')?.addEventListener('change', (e) => {
      const plotDiv = document.getElementById('telemetry_plot');
      if (plotDiv && typeof Plotly !== 'undefined' && sysTraceMap.sys_swap !== undefined) {
        Plotly.restyle(plotDiv, { visible: e.target.checked }, [sysTraceMap.sys_swap]);
      }
    });

    // CSV / JSON Export Handlers
    function downloadCSV() {
      if (!activeSessionKey || !loadedSessions[activeSessionKey]) return;
      const session = loadedSessions[activeSessionKey];
      const allPids = session.allPids || [];
      const timestamps = session.timestamps || [];
      const sysMetrics = session.systemMetrics || {};

      const headers = ["Timestamp", "System_CPU%", "System_RAM_MB", "Swap_Used_MB"];
      allPids.forEach(pid => {
        const p = session.pidData[pid];
        const safeName = (p && p.args ? p.args : ("PID_" + pid)).replace(/,/g, '_').substring(0, 30);
        headers.push(`PID_${pid}_${safeName}_CPU%`);
        headers.push(`PID_${pid}_${safeName}_RES_MB`);
      });

      const rows = [headers.join(",")];
      for (let i = 0; i < timestamps.length; i++) {
        const ts = timestamps[i];
        const sysCpu = (sysMetrics["%cpu_total"] && sysMetrics["%cpu_total"][i] !== undefined) ? sysMetrics["%cpu_total"][i] : 0.0;
        const sysMem = (sysMetrics["mem_used_mb"] && sysMetrics["mem_used_mb"][i] !== undefined) ? sysMetrics["mem_used_mb"][i] : 0.0;
        const sysSwap = (sysMetrics["swap_used_mb"] && sysMetrics["swap_used_mb"][i] !== undefined) ? sysMetrics["swap_used_mb"][i] : 0.0;
        const row = [ts, sysCpu, sysMem, sysSwap];

        allPids.forEach(pid => {
          const p = session.pidData[pid];
          const cpuVal = (p && p.cpu && p.cpu[i] !== undefined) ? p.cpu[i] : 0.0;
          const resVal = (p && p.res_mb && p.res_mb[i] !== undefined) ? p.res_mb[i] : 0.0;
          row.push(cpuVal);
          row.push(resVal);
        });
        rows.push(row.join(","));
      }

      const csvContent = rows.join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const baseName = session.label ? session.label.replace(/\\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_\\-]/g, "_") : "telemetry";
      a.download = baseName + ".csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    function downloadJSON() {
      if (!activeSessionKey || !loadedSessions[activeSessionKey]) return;
      const session = loadedSessions[activeSessionKey];
      const result = {
        timestamps: session.timestamps,
        system_metrics: session.systemMetrics,
        processes: {}
      };
      const allPids = session.allPids || [];
      allPids.forEach(pid => {
        const p = session.pidData[pid];
        if (p) {
          result.processes[String(pid)] = {
            args: p.args,
            cpu: p.cpu,
            res_mb: p.res_mb,
            shr_mb: p.shr_mb,
            mem_pct: p.mem_pct,
            max_cpu: p.max_cpu,
            avg_cpu: p.cpu && p.cpu.length ? (p.cpu.reduce((a, b) => a + b, 0) / p.cpu.length) : 0.0,
            max_res_mb: p.max_res_mb
          };
        }
      });
      const jsonContent = JSON.stringify(result, null, 2);
      const blob = new Blob([jsonContent], { type: "application/json;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const baseName = session.label ? session.label.replace(/\\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_\\-]/g, "_") : "telemetry";
      a.download = baseName + ".json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    document.getElementById('btnDownloadCsv')?.addEventListener('click', downloadCSV);
    document.getElementById('btnDownloadJson')?.addEventListener('click', downloadJSON);

    // Search and Regex Filter
    const searchInput = document.getElementById('processSearch');
    const chkRegex = document.getElementById('chkHtmlRegex');
    function filterRows() {
      const query = (searchInput?.value || '').trim();
      const isRegex = chkRegex?.checked;
      let regexObj = null;

      if (isRegex && query) {
        try {
          regexObj = new RegExp(query, 'i');
          searchInput.style.borderColor = '';
        } catch (err) {
          searchInput.style.borderColor = '#ef4444';
          return;
        }
      } else {
        if (searchInput) searchInput.style.borderColor = '';
      }

      const qLower = query.toLowerCase();
      const rows = document.querySelectorAll('#processTableBody tr');
      let visibleCount = 0;

      rows.forEach(r => {
        let matches = true;
        if (query) {
          matches = regexObj ? regexObj.test(r.innerText) : r.innerText.toLowerCase().includes(qLower);
        }
        r.style.display = matches ? '' : 'none';
        if (matches) visibleCount++;
      });

      const countLabel = document.getElementById('rowCountLabel');
      if (countLabel) countLabel.textContent = `Showing ${visibleCount} of ${rows.length} processes`;
    }

    searchInput?.addEventListener('input', filterRows);
    chkRegex?.addEventListener('change', filterRows);

    // Column Sorting
    let sortCol = -1;
    let sortAsc = true;
    document.querySelectorAll('#processTable th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const colIdx = parseInt(th.getAttribute('data-col'), 10);
        const colType = th.getAttribute('data-type');
        sortAsc = (sortCol === colIdx) ? !sortAsc : true;
        sortCol = colIdx;

        document.querySelectorAll('#processTable th.sortable .sort-icon').forEach(icon => icon.textContent = '▲▼');
        const curIcon = th.querySelector('.sort-icon');
        if (curIcon) curIcon.textContent = sortAsc ? '▲' : '▼';

        const tbody = document.getElementById('processTableBody');
        const rows = Array.from(tbody.querySelectorAll('tr'));

        rows.sort((a, b) => {
          const cellA = a.children[colIdx];
          const cellB = b.children[colIdx];
          if (!cellA || !cellB) return 0;
          const valA = cellA.getAttribute('data-val') !== null ? parseFloat(cellA.getAttribute('data-val')) : cellA.innerText.trim();
          const valB = cellB.getAttribute('data-val') !== null ? parseFloat(cellB.getAttribute('data-val')) : cellB.innerText.trim();

          if (colType === 'num') {
            const numA = isNaN(valA) ? 0 : valA;
            const numB = isNaN(valB) ? 0 : valB;
            return sortAsc ? (numA - numB) : (numB - numA);
          } else {
            return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
          }
        });

        rows.forEach(r => tbody.appendChild(r));
      });
    });

    // Theme Switcher & Complete Recolor
    function applyThemeToPlot(chosenTheme) {
      document.body.setAttribute('data-theme', chosenTheme);
      const t = THEMES[chosenTheme];
      const plotDiv = document.getElementById('telemetry_plot');
      if (!t || !plotDiv || !plotDiv.data || typeof Plotly === 'undefined') return;

      // 1. Recolor data traces
      if (sysTraceMap.sys_cpu !== undefined && plotDiv.data[sysTraceMap.sys_cpu]) {
        plotDiv.data[sysTraceMap.sys_cpu].line.color = t.accent_cpu;
        plotDiv.data[sysTraceMap.sys_cpu].fillcolor = hexToRgba(t.accent_cpu, 0.12);
        plotDiv.data[sysTraceMap.sys_cpu].hoverlabel = {
          bgcolor: t.bg_card,
          bordercolor: t.accent_cpu,
          font: { color: t.fg_text, size: 11 }
        };
      }
      if (sysTraceMap.sys_mem !== undefined && plotDiv.data[sysTraceMap.sys_mem]) {
        plotDiv.data[sysTraceMap.sys_mem].line.color = t.accent_mem;
        plotDiv.data[sysTraceMap.sys_mem].hoverlabel = {
          bgcolor: t.bg_card,
          bordercolor: t.accent_mem,
          font: { color: t.fg_text, size: 11 }
        };
      }

      if (activeSessionKey && loadedSessions[activeSessionKey]) {
        const session = loadedSessions[activeSessionKey];
        const curveCols = t.curve_colors;
        session.allPids.forEach((pid, idx) => {
          const col = curveCols[idx % curveCols.length];
          const pTraces = pidTraceMap[pid];
          if (pTraces && pTraces.length === 2) {
            const cpuT = plotDiv.data[pTraces[0]];
            const memT = plotDiv.data[pTraces[1]];
            if (cpuT && cpuT.line) {
              cpuT.line.color = col;
              cpuT.hoverlabel = { bgcolor: t.bg_card, bordercolor: col, font: { color: t.fg_text, size: 11 } };
            }
            if (memT && memT.line) {
              memT.line.color = col;
              memT.hoverlabel = { bgcolor: t.bg_card, bordercolor: col, font: { color: t.fg_text, size: 11 } };
            }
          }
        });
      }

      // 2. Build updated layout
      const updatedLayout = {
        ...plotDiv.layout,
        template: t.plotly_template || (chosenTheme === 'Light Mode' ? 'plotly_white' : 'plotly_dark'),
        paper_bgcolor: t.bg_window,
        plot_bgcolor: t.bg_card,
        font: { color: t.fg_text, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
        hovermode: "x unified",
        hoverlabel: {
          namelength: -1,
          bgcolor: t.bg_card,
          bordercolor: t.border,
          font: { color: t.fg_text, size: 11, family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }
        },
        legend: {
          ...plotDiv.layout.legend,
          bgcolor: t.bg_card,
          bordercolor: t.border,
          borderwidth: 1,
          font: { color: t.fg_text, size: 11 },
          orientation: "h",
          yanchor: "bottom",
          y: 1.02,
          xanchor: "right",
          x: 1
        },
        xaxis: {
          ...plotDiv.layout.xaxis,
          title: "Timestamp",
          gridcolor: t.grid,
          color: t.fg_text,
          linecolor: t.border
        },
        yaxis: {
          ...plotDiv.layout.yaxis,
          title: "CPU Usage (%)",
          gridcolor: t.grid,
          color: t.accent_cpu
        },
        yaxis2: {
          ...plotDiv.layout.yaxis2,
          title: "Memory (MB)",
          color: t.accent_mem
        }
      };

      Plotly.react(plotDiv, plotDiv.data, updatedLayout);
    }

    document.getElementById('htmlThemeSelect')?.addEventListener('change', (e) => {
      applyThemeToPlot(e.target.value);
    });

    // File Drop & Upload Handlers
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    document.getElementById('btnBrowseFiles')?.addEventListener('click', () => fileInput.click());
    document.getElementById('btnUploadToggle')?.addEventListener('click', () => {
      dropZone.style.display = dropZone.style.display === 'none' ? 'block' : 'none';
    });

    // Global Drag & Drop Prevention so dropping anywhere on page works cleanly
    ['dragenter', 'dragover'].forEach(eventName => {
      window.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
      }, false);
    });

    ['dragleave'].forEach(eventName => {
      window.addEventListener(eventName, (e) => {
        e.preventDefault();
      }, false);
    });

    window.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      const files = e.dataTransfer ? e.dataTransfer.files : null;
      if (files && files.length) handleFiles(files);
    }, false);

    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      const files = e.dataTransfer ? e.dataTransfer.files : null;
      if (files && files.length) handleFiles(files);
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) handleFiles(e.target.files);
    });

    function mergeTopAndTopmen(topParsed, topmenParsed, sessionLabel) {
      if (!topParsed && !topmenParsed) return null;
      if (!topParsed) return topmenParsed;
      if (!topmenParsed) return topParsed;

      const merged = JSON.parse(JSON.stringify(topParsed));
      merged.label = sessionLabel;

      if (topmenParsed.systemMetrics["mem_used_mb"] && topmenParsed.systemMetrics["mem_used_mb"].length) {
        merged.systemMetrics["mem_used_mb"] = topmenParsed.systemMetrics["mem_used_mb"];
      }

      for (const pid in topmenParsed.pidData) {
        const tmPid = topmenParsed.pidData[pid];
        if (merged.pidData[pid]) {
          merged.pidData[pid].res_mb = tmPid.res_mb;
          merged.pidData[pid].max_res_mb = tmPid.max_res_mb;
          if (tmPid.mem_pct && tmPid.mem_pct.length) {
            merged.pidData[pid].mem_pct = tmPid.mem_pct;
          }
        } else {
          merged.pidData[pid] = tmPid;
          merged.allPids.push(parseInt(pid, 10));
        }
      }

      merged.allPids = Array.from(new Set(merged.allPids));
      merged.topMemPids = [...merged.allPids].sort((a, b) => (merged.pidData[b].max_res_mb || 0) - (merged.pidData[a].max_res_mb || 0));

      return merged;
    }

    function handleFiles(files) {
      if (!files || !files.length) return;
      let pending = files.length;
      const fileBatch = {};

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const reader = new FileReader();
        reader.onload = (event) => {
          const content = event.target.result;
          const name = file.name;
          let label = name.replace(/\\.(log|txt|top)$/i, '');
          const isTop = name.includes("log_top@");
          const isTopmen = name.includes("log_topmen@");

          if (isTop) label = label.replace("log_top@", "");
          if (isTopmen) label = label.replace("log_topmen@", "");

          if (!fileBatch[label]) {
            fileBatch[label] = { label: label, top: null, topmen: null, other: null };
          }

          if (isTop) {
            fileBatch[label].top = content;
          } else if (isTopmen) {
            fileBatch[label].topmen = content;
          } else {
            fileBatch[label].other = content;
          }

          pending--;
          if (pending === 0) {
            processFileBatch(fileBatch);
          }
        };
        reader.readAsText(file, "utf-8");
      }
    }

    function processFileBatch(fileBatch) {
      let firstNewKey = null;
      for (const label in fileBatch) {
        const b = fileBatch[label];
        let sessionParsed = null;

        if (b.top && b.topmen) {
          const pTop = parseTopLog(b.top, label);
          const pMen = parseTopLog(b.topmen, label);
          sessionParsed = mergeTopAndTopmen(pTop, pMen, label);
        } else if (b.top) {
          sessionParsed = parseTopLog(b.top, label);
        } else if (b.topmen) {
          sessionParsed = parseTopLog(b.topmen, label);
        } else if (b.other) {
          sessionParsed = parseTopLog(b.other, label);
        }

        if (sessionParsed && sessionParsed.timestamps && sessionParsed.timestamps.length > 0) {
          loadedSessions[label] = sessionParsed;
          if (!firstNewKey) firstNewKey = label;
        }
      }

      if (firstNewKey) {
        updateSessionPills(firstNewKey);
      }
    }

    function updateSessionPills(selectKey) {
      const keys = Object.keys(loadedSessions);
      if (!keys.length) return;

      const pillsContainer = document.getElementById('sessionPills');
      pillsContainer.innerHTML = "";
      pillsContainer.style.display = "flex";

      const targetKey = (selectKey && loadedSessions[selectKey]) ? selectKey : (activeSessionKey || keys[0]);

      keys.forEach(k => {
        const btn = document.createElement("button");
        btn.className = "session-pill" + (k === targetKey ? " active" : "");
        btn.setAttribute("data-key", k);
        btn.textContent = `📁 ${k} (${loadedSessions[k].timestamps.length} samples)`;
        btn.addEventListener('click', () => {
          document.querySelectorAll('.session-pill').forEach(p => p.classList.toggle('active', p.getAttribute('data-key') === k));
          renderSession(k);
        });
        pillsContainer.appendChild(btn);
      });

      // Hide dropzone to make room for telemetry
      dropZone.style.display = "none";
      renderSession(targetKey);
    }

    // Load Demo Log Handler
    document.getElementById('btnLoadDemo')?.addEventListener('click', () => {
      const demoParsed = parseTopLog(DEMO_SNIPPET, "Demo_Automotive_Batch");
      loadedSessions["Demo_Automotive_Batch"] = demoParsed;
      updateSessionPills();
    });
  </script>
</body>
</html>
"""

    if plotly_js:
        script_tag = f"<script>{plotly_js}</script>"
    else:
        script_tag = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'

    full_html = (
        html_template
        .replace("__PLOTLY_SCRIPT_TAG__", script_tag)
        .replace("__THEMES_JSON__", themes_json)
        .replace("__SAMPLE_DEMO_JSON__", sample_demo_json)
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    return os.path.abspath(output_path)



# ----------------------------------------------------------------------
# 4. Drag & Drop File Scanner
# ----------------------------------------------------------------------

def scan_log_paths(paths: List[str]) -> List[LogJob]:
    """Scan list of file or folder paths and return paired LogJob instances without duplicates."""
    discovered_files: List[str] = []
    valid_exts = (".log", ".txt", ".top")

    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in sorted(files):
                    if any(f.lower().endswith(ext) for ext in valid_exts):
                        abs_f = os.path.abspath(os.path.join(root, f))
                        if abs_f not in discovered_files:
                            discovered_files.append(abs_f)
        elif os.path.isfile(path):
            abs_p = os.path.abspath(path)
            if abs_p not in discovered_files:
                discovered_files.append(abs_p)
            dir_name = os.path.dirname(abs_p)
            base_name = os.path.basename(abs_p)
            if "log_top@" in base_name:
                counterpart = os.path.join(dir_name, base_name.replace("log_top@", "log_topmen@"))
                if os.path.exists(counterpart) and counterpart not in discovered_files:
                    discovered_files.append(counterpart)
            elif "log_topmen@" in base_name:
                counterpart = os.path.join(dir_name, base_name.replace("log_topmen@", "log_top@"))
                if os.path.exists(counterpart) and counterpart not in discovered_files:
                    discovered_files.append(counterpart)

    jobs_map: Dict[str, LogJob] = {}

    for f_path in discovered_files:
        dir_name = os.path.dirname(f_path)
        filename = os.path.basename(f_path)
        is_top = "log_top@" in filename
        is_topmen = "log_topmen@" in filename

        if is_top:
            raw_key = filename.replace("log_top@", "")
        elif is_topmen:
            raw_key = filename.replace("log_topmen@", "")
        else:
            raw_key = filename

        key = f"{dir_name}::{raw_key}"

        if key not in jobs_map:
            label = os.path.splitext(raw_key)[0]
            jobs_map[key] = LogJob(label=label)

        if is_top:
            jobs_map[key].top_file = f_path
        elif is_topmen:
            jobs_map[key].topmen_file = f_path
        else:
            if not jobs_map[key].top_file:
                jobs_map[key].top_file = f_path
            elif not jobs_map[key].topmen_file:
                jobs_map[key].topmen_file = f_path

    return sorted(jobs_map.values(), key=lambda j: j.label)


# ----------------------------------------------------------------------
# 5. Modern Qt Desktop GUI (PySide6) with Native Matplotlib Engine
# ----------------------------------------------------------------------

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
        QPushButton, QLabel, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
        QHeaderView, QGroupBox, QAbstractItemView, QProgressBar, QComboBox,
        QToolTip
    )
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
    import webbrowser

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


def generate_qss(theme: Dict[str, Any]) -> str:
    """Generate dynamic Qt Stylesheet (QSS) for a chosen theme palette."""
    return f"""
        QMainWindow, QWidget {{
            background-color: {theme['bg_window']};
            color: {theme['fg_text']};
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        QGroupBox {{
            border: 1px solid {theme['border']};
            border-radius: 6px;
            margin-top: 6px;
            padding-top: 10px;
            font-size: 11px;
            font-weight: bold;
            color: {theme['fg_muted']};
        }}
        QPushButton {{
            background-color: {theme['bg_card']};
            color: {theme['fg_text']};
            border: 1px solid {theme['border']};
            border-radius: 5px;
            padding: 5px 10px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {theme['bg_header']};
            border-color: {theme['accent_cpu']};
        }}
        QLineEdit, QComboBox {{
            background-color: {theme['bg_card']};
            border: 1px solid {theme['border']};
            border-radius: 5px;
            padding: 4px 8px;
            color: {theme['fg_text']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {theme['bg_card']};
            color: {theme['fg_text']};
            selection-background-color: {theme['bg_header']};
        }}
        QTableWidget {{
            background-color: {theme['bg_card']};
            alternate-background-color: {theme['bg_window']};
            gridline-color: {theme['border']};
            border: 1px solid {theme['border']};
            border-radius: 6px;
        }}
        QHeaderView::section {{
            background-color: {theme['bg_header']};
            color: {theme['fg_text']};
            padding: 4px;
            border: 1px solid {theme['border']};
            font-weight: bold;
        }}
        QListWidget {{
            background-color: {theme['bg_card']};
            border: 1px solid {theme['border']};
            border-radius: 6px;
        }}
        QToolTip {{
            background-color: {theme['bg_card']};
            color: {theme['fg_text']};
            border: 1px solid {theme['border']};
            border-radius: 6px;
            padding: 5px;
            font-size: 11px;
        }}
    """


if GUI_AVAILABLE:
    class MplTelemetryCanvas(FigureCanvasQTAgg):
        """Native Matplotlib Canvas with Dual Y-Axes and Dynamic Theme Palettes."""

        def __init__(self, parent=None, width=8, height=4, dpi=100):
            self.theme_name = "Dark Fusion"
            self.fig = Figure(figsize=(width, height), dpi=dpi)
            self.ax_cpu = self.fig.add_subplot(111)
            self.ax_mem = self.ax_cpu.twinx()
            super().__init__(self.fig)
            self.setParent(parent)
            self.setMouseTracking(True)
            self._legend_map: Dict[Any, Dict[str, Any]] = {}
            self._cursor_line = None
            self._current_data: Optional[ParsedLogV2] = None
            self._current_selected_pids: List[int] = []
            self._plot_sys_cpu: bool = True
            self._plot_sys_mem: bool = True
            self._plot_cpu_breakdown: bool = False
            self._plot_sys_swap: bool = False
            self._last_hover_idx: int = -1
            self.mpl_connect('pick_event', self._on_legend_pick)
            self.mpl_connect('motion_notify_event', self._on_mouse_move)
            self.mpl_connect('figure_leave_event', self._on_mouse_leave)
            self._setup_style()

        def set_theme(self, theme_name: str):
            """Apply theme palette to figure, axes, ticks and grids."""
            if theme_name in THEMES:
                self.theme_name = theme_name
                self._setup_style()

        def _setup_style(self):
            t = THEMES.get(self.theme_name, THEMES["Dark Fusion"])
            self.fig.patch.set_facecolor(t["bg_window"])
            self.ax_cpu.set_facecolor(t["bg_card"])
            self.ax_cpu.tick_params(colors=t["fg_muted"], labelsize=8)
            self.ax_mem.tick_params(colors=t["accent_mem"], labelsize=8)
            for spine in self.ax_cpu.spines.values():
                spine.set_color(t["border"])
            for spine in self.ax_mem.spines.values():
                spine.set_color(t["border"])
            self.ax_cpu.grid(True, linestyle='--', alpha=0.25, color=t["grid"])
            self.ax_cpu.set_ylabel("CPU Usage (%)", color=t["accent_cpu"], fontsize=9, fontweight='bold')
            self.ax_mem.set_ylabel("Memory (MB)", color=t["accent_mem"], fontsize=9, fontweight='bold')
            self.fig.tight_layout()

        def plot_telemetry(
            self,
            data: ParsedLogV2,
            selected_pids: Optional[List[int]] = None,
            plot_sys_cpu: bool = True,
            plot_sys_mem: bool = True,
            plot_cpu_breakdown: bool = False,
            plot_sys_swap: bool = False
        ):
            self.ax_cpu.clear()
            self.ax_mem.clear()
            self._setup_style()
            t = THEMES.get(self.theme_name, THEMES["Dark Fusion"])

            x_indices = list(range(len(data.timestamps)))
            self._legend_map.clear()
            self._current_data = data
            self._current_selected_pids = list(selected_pids or [])
            self._plot_sys_cpu = plot_sys_cpu
            self._plot_sys_mem = plot_sys_mem
            self._plot_cpu_breakdown = plot_cpu_breakdown
            self._plot_sys_swap = plot_sys_swap
            self._last_hover_idx = -1

            if not x_indices:
                self._cursor_line = None
                self.draw_idle()
                return

            # Vertical hover crosshair line (hidden initially, excluded from legend)
            self._cursor_line = self.ax_cpu.axvline(
                x=0, color=t["fg_muted"], linestyle=":", linewidth=1.5, alpha=0.7, visible=False, zorder=10
            )

            # 1. System Total CPU
            line_sys_cpu = None
            fill_sys_cpu = None
            if plot_sys_cpu and "%cpu_total" in data.system_metrics:
                cpu_series = data.system_metrics["%cpu_total"]
                line_sys_cpu, = self.ax_cpu.plot(x_indices, cpu_series, label="Sys CPU Total%", color=t["accent_cpu"], linewidth=2.0)
                fill_sys_cpu = self.ax_cpu.fill_between(x_indices, 0, cpu_series, color=t["accent_cpu"], alpha=0.1)

            # CPU Breakdown stacked area traces
            cpu_breakdown_labels = [
                ("%user", "CPU %user"),
                ("%sys", "CPU %sys"),
                ("%nice", "CPU %nice"),
                ("%irq", "CPU %irq"),
                ("%sirq", "CPU %sirq"),
                ("%iow", "CPU %iow"),
            ]
            cpu_breakdown_colors = ["#3b82f6", "#ef4444", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4"]

            breakdown_fills: Dict[Any, Any] = {}
            if plot_cpu_breakdown:
                current_bottom = [0.0] * len(x_indices)
                for idx, (metric_key, trace_label) in enumerate(cpu_breakdown_labels):
                    if metric_key in data.system_metrics:
                        vals = data.system_metrics[metric_key]
                        bd_color = cpu_breakdown_colors[idx % len(cpu_breakdown_colors)]
                        current_top = [b + v for b, v in zip(current_bottom, vals)]
                        line_bd, = self.ax_cpu.plot(x_indices, current_top, label=trace_label, color=bd_color, linewidth=1.2)
                        fill_bd = self.ax_cpu.fill_between(x_indices, current_bottom, current_top, color=bd_color, alpha=0.25)
                        breakdown_fills[line_bd] = fill_bd
                        current_bottom = current_top

            # 2. System RAM Used
            if plot_sys_mem and "mem_used_mb" in data.system_metrics:
                mem_series = data.system_metrics["mem_used_mb"]
                self.ax_mem.plot(x_indices, mem_series, label="Sys RAM Used", color=t["accent_mem"], linewidth=1.5, linestyle=":")

            # System Swap Used
            if plot_sys_swap and "swap_used_mb" in data.system_metrics:
                swap_series = data.system_metrics["swap_used_mb"]
                self.ax_mem.plot(x_indices, swap_series, label="Sys Swap Used", color="#f43f5e", linewidth=1.5, linestyle="-.")

            # 3. Selected PIDs
            colors = t["curve_colors"]
            if selected_pids:
                for idx, pid in enumerate(selected_pids):
                    m = data.get_pid_metrics(pid)
                    col = colors[idx % len(colors)]
                    p_label = f"PID {pid} ({m['args'][:18]})"
                    self.ax_cpu.plot(x_indices, m["cpu"], label=f"{p_label} %CPU", color=col, linewidth=1.8)
                    self.ax_mem.plot(x_indices, m["res_mb"], label=f"{p_label} RES", color=col, linewidth=1.2, linestyle="--")

            # X-axis Timestamps with spacing
            step = max(1, len(data.timestamps) // 10)
            tick_indices = list(range(0, len(data.timestamps), step))
            tick_labels = [data.timestamps[i] for i in tick_indices]
            self.ax_cpu.set_xticks(tick_indices)
            self.ax_cpu.set_xticklabels(tick_labels, rotation=25, ha='right', fontsize=7, color=t["fg_muted"])

            # Combined Interactive Legend
            lines_cpu, labels_cpu = self.ax_cpu.get_legend_handles_labels()
            lines_mem, labels_mem = self.ax_mem.get_legend_handles_labels()
            all_lines = lines_cpu + lines_mem
            all_labels = labels_cpu + labels_mem

            if all_lines:
                leg = self.ax_cpu.legend(
                    all_lines, all_labels,
                    loc="upper right", fontsize=7, facecolor=t["bg_window"], edgecolor=t["border"], labelcolor=t["fg_text"]
                )

                # Enable clicking legend lines or labels to toggle visibility
                leg_lines = leg.get_lines()
                leg_texts = leg.get_texts()
                for orig_line, leg_line, leg_text in zip(all_lines, leg_lines, leg_texts):
                    leg_line.set_picker(True)
                    leg_line.set_pickradius(8)
                    leg_text.set_picker(True)

                    fill = fill_sys_cpu if orig_line is line_sys_cpu else breakdown_fills.get(orig_line)
                    entry = {
                        "line": orig_line,
                        "fill": fill,
                        "leg_line": leg_line,
                        "leg_text": leg_text,
                        "label": leg_text.get_text()
                    }
                    self._legend_map[leg_line] = entry
                    self._legend_map[leg_text] = entry

            self.fig.tight_layout()
            self.draw_idle()

        def get_hover_tooltip_text(self, idx: int) -> str:
            """Generate styled HTML tooltip for a sample index."""
            if not self._current_data or idx < 0 or idx >= len(self._current_data.timestamps):
                return ""
            t = THEMES.get(self.theme_name, THEMES["Dark Fusion"])
            ts = self._current_data.timestamps[idx]
            rows = []

            if self._plot_sys_cpu and "%cpu_total" in self._current_data.system_metrics:
                cpu_val = self._current_data.system_metrics["%cpu_total"][idx]
                rows.append(f'<tr><td style="color:{t["accent_cpu"]};font-weight:bold;">Sys Total CPU%:</td><td style="color:{t["accent_cpu"]};text-align:right;font-weight:bold;padding-left:14px;font-family:monospace;">{cpu_val:.1f}%</td></tr>')

            if self._plot_cpu_breakdown:
                cpu_breakdown_labels = [
                    ("%user", "CPU %user"),
                    ("%sys", "CPU %sys"),
                    ("%nice", "CPU %nice"),
                    ("%irq", "CPU %irq"),
                    ("%sirq", "CPU %sirq"),
                    ("%iow", "CPU %iow"),
                ]
                cpu_breakdown_colors = ["#3b82f6", "#ef4444", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4"]
                for b_idx, (m_key, m_label) in enumerate(cpu_breakdown_labels):
                    if m_key in self._current_data.system_metrics:
                        b_val = self._current_data.system_metrics[m_key][idx]
                        b_col = cpu_breakdown_colors[b_idx % len(cpu_breakdown_colors)]
                        rows.append(f'<tr><td style="color:{b_col};padding-left:10px;">{m_label}:</td><td style="color:{b_col};text-align:right;padding-left:14px;font-family:monospace;">{b_val:.1f}%</td></tr>')

            if self._plot_sys_mem and "mem_used_mb" in self._current_data.system_metrics:
                mem_val = self._current_data.system_metrics["mem_used_mb"][idx]
                rows.append(f'<tr><td style="color:{t["accent_mem"]};font-weight:bold;">Sys RAM Used:</td><td style="color:{t["accent_mem"]};text-align:right;font-weight:bold;padding-left:14px;font-family:monospace;">{mem_val:.1f} MB</td></tr>')

            if getattr(self, "_plot_sys_swap", False) and "swap_used_mb" in self._current_data.system_metrics:
                swap_val = self._current_data.system_metrics["swap_used_mb"][idx]
                rows.append(f'<tr><td style="color:#f43f5e;font-weight:bold;">Sys Swap Used:</td><td style="color:#f43f5e;text-align:right;font-weight:bold;padding-left:14px;font-family:monospace;">{swap_val:.1f} MB</td></tr>')

            colors = t["curve_colors"]
            for p_idx, pid in enumerate(self._current_selected_pids):
                m = self._current_data.get_pid_metrics(pid)
                col = colors[p_idx % len(colors)]
                proc_name = m["args"][:35] + "..." if len(m["args"]) > 35 else m["args"]
                cpu_val = m["cpu"][idx] if idx < len(m["cpu"]) else 0.0
                res_val = m["res_mb"][idx] if idx < len(m["res_mb"]) else 0.0
                rows.append(
                    f'<tr><td style="color:{col};font-weight:bold;padding-right:12px;">PID {pid} ({proc_name}):</td>'
                    f'<td style="color:{t["fg_text"]};text-align:right;padding-left:14px;font-family:monospace;white-space:nowrap;">'
                    f'<span style="color:{t["accent_cpu"]};font-weight:bold;">{cpu_val:.1f}%</span>'
                    f' <span style="color:{t["fg_muted"]};">|</span> '
                    f'<span style="color:{t["accent_mem"]};font-weight:bold;">{res_val:.1f} MB</span>'
                    f'</td></tr>'
                )

            table_content = "".join(rows)
            return (
                f'<div style="background-color:{t["bg_card"]};color:{t["fg_text"]};'
                f'border:1px solid {t["border"]};border-radius:6px;padding:8px;'
                f'font-family:Segoe UI, sans-serif;font-size:11px;line-height:1.4;">'
                f'<div style="font-weight:bold;color:{t["fg_text"]};border-bottom:1px solid {t["border"]};padding-bottom:4px;margin-bottom:6px;">'
                f'⏱ Sample #{idx + 1} &bull; {ts}</div>'
                f'<table style="border-collapse:collapse;width:100%;font-size:11px;color:{t["fg_text"]};">{table_content}</table>'
                f'</div>'
            )

        def _on_legend_pick(self, event):
            """Handle clicking legend lines or text labels to toggle line visibility."""
            if not hasattr(event, "mouseevent") or getattr(event.mouseevent, "_legend_toggled", False):
                return

            artist = getattr(event, "artist", None)
            if artist in self._legend_map:
                event.mouseevent._legend_toggled = True
                entry = self._legend_map[artist]
                orig_line = entry["line"]
                new_visible = not orig_line.get_visible()
                orig_line.set_visible(new_visible)

                if entry.get("fill") is not None:
                    entry["fill"].set_visible(new_visible)

                alpha = 1.0 if new_visible else 0.25
                entry["leg_line"].set_alpha(alpha)
                entry["leg_text"].set_alpha(alpha)

                self.draw_idle()

        def _on_mouse_move(self, event):
            """Handle mouse hover for legend pointing hand and telemetry crosshair/tooltip."""
            # 1. Legend hit test
            hit_legend = False
            if self._legend_map and event.x is not None and event.y is not None:
                for artist in self._legend_map.keys():
                    contains, _ = artist.contains(event)
                    if contains:
                        hit_legend = True
                        break

            if hit_legend:
                self.setCursor(Qt.PointingHandCursor)
                if self._cursor_line and self._cursor_line.get_visible():
                    self._cursor_line.set_visible(False)
                    self.draw_idle()
                QToolTip.hideText()
                return

            # 2. Axes Hover test
            if event.inaxes in (self.ax_cpu, self.ax_mem) and event.xdata is not None and self._current_data:
                self.setCursor(Qt.CrossCursor)
                x_idx = int(round(event.xdata))
                x_idx = max(0, min(x_idx, len(self._current_data.timestamps) - 1))

                # Update crosshair
                if self._cursor_line:
                    self._cursor_line.set_xdata([x_idx, x_idx])
                    self._cursor_line.set_visible(True)

                if x_idx != self._last_hover_idx:
                    self._last_hover_idx = x_idx
                    self.draw_idle()

                # Show Qt ToolTip
                tooltip_html = self.get_hover_tooltip_text(x_idx)
                if tooltip_html:
                    if event.guiEvent and hasattr(event.guiEvent, 'globalPosition'):
                        g_pos = event.guiEvent.globalPosition().toPoint()
                    elif event.guiEvent and hasattr(event.guiEvent, 'globalPos'):
                        g_pos = event.guiEvent.globalPos()
                    else:
                        g_pos = self.mapToGlobal(QPoint(int(event.x or 0), int(self.height() - (event.y or 0))))
                    tip_pos = QPoint(g_pos.x() + 15, g_pos.y() + 15)
                    QToolTip.showText(tip_pos, tooltip_html, self)
                return

            # 3. Outside plot
            self.setCursor(Qt.ArrowCursor)
            if self._cursor_line and self._cursor_line.get_visible():
                self._cursor_line.set_visible(False)
                self.draw_idle()
            self._last_hover_idx = -1
            QToolTip.hideText()

        def _on_mouse_leave(self, event):
            """Hide crosshair and tooltip when cursor leaves canvas."""
            if self._cursor_line and self._cursor_line.get_visible():
                self._cursor_line.set_visible(False)
                self.draw_idle()
            self._last_hover_idx = -1
            QToolTip.hideText()



    class SortableTableWidgetItem(QTableWidgetItem):
        """Table widget item that sorts by explicit numeric or custom typed value."""

        def __init__(self, text: str, sort_value: Any = None):
            super().__init__(text)
            self.sort_value = sort_value if sort_value is not None else text

        def __lt__(self, other):
            if isinstance(other, SortableTableWidgetItem):
                try:
                    return self.sort_value < other.sort_value
                except TypeError:
                    return str(self.sort_value) < str(other.sort_value)
            return super().__lt__(other)


    class DropZoneLabel(QLabel):
        """Active drop target widget for drag-and-drop log files and directories."""

        def __init__(self, text: str, parent=None):
            super().__init__(text, parent)
            self.setAcceptDrops(True)

        def dragEnterEvent(self, event: QDragEnterEvent):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                win = self.window()
                if hasattr(win, '_get_drop_zone_qss'):
                    self.setStyleSheet(win._get_drop_zone_qss(active=True))

        def dragMoveEvent(self, event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dragLeaveEvent(self, event):
            win = self.window()
            if hasattr(win, '_get_drop_zone_qss'):
                self.setStyleSheet(win._get_drop_zone_qss(active=False))

        def dropEvent(self, event: QDropEvent):
            win = self.window()
            if hasattr(win, '_get_drop_zone_qss'):
                self.setStyleSheet(win._get_drop_zone_qss(active=False))
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths and hasattr(win, "handle_dropped_paths"):
                win.handle_dropped_paths(paths)


    class TopPlotMainWindow(QMainWindow):
        """Modern Qt6 Desktop UI for Top & Topmem Log Profiling."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Top Log Analyzer v2.0 - Automotive Telemetry Profiler")
            self.resize(1280, 840)
            self.setAcceptDrops(True)

            self.parser = LogParserV2()
            self.current_job: Optional[LogJob] = None
            self.current_parsed: Optional[ParsedLogV2] = None
            self.jobs: List[LogJob] = []
            self.current_theme: str = "Dark Fusion"

            self._setup_ui()
            self.set_theme(self.current_theme)

        def _get_drop_zone_qss(self, active: bool = False) -> str:
            """Return themed QSS for the drop zone label."""
            t = THEMES.get(self.current_theme, THEMES["Dark Fusion"])
            if active:
                return (
                    f"border: 2px dashed {t['accent_cpu']}; border-radius: 8px; "
                    f"padding: 18px 8px; background-color: rgba({hex_to_rgb_str(t['accent_cpu'])}, 0.1); "
                    f"color: {t['accent_cpu']}; font-size: 12px; font-weight: bold;"
                )
            return (
                f"border: 2px dashed {t['border']}; border-radius: 8px; "
                f"padding: 18px 8px; background-color: {t['bg_card']}; "
                f"color: {t['fg_muted']}; font-size: 12px; font-weight: bold;"
            )

        def _get_search_qss(self, state: str = "normal") -> str:
            """Return themed QSS for the search input. state: 'normal', 'valid_regex', 'invalid_regex'."""
            t = THEMES.get(self.current_theme, THEMES["Dark Fusion"])
            border_color = t["border"]
            text_color = t["fg_text"]
            if state == "valid_regex":
                border_color = t["accent_cpu"]
            elif state == "invalid_regex":
                border_color = "#ef4444"
                text_color = "#f87171"
            return (
                f"background-color: {t['bg_card']}; border: 1px solid {border_color}; "
                f"border-radius: 5px; padding: 4px 8px; color: {text_color};"
            )

        def _setup_ui(self):
            """Construct main window widgets and layout."""
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QHBoxLayout(central_widget)
            main_layout.setContentsMargins(8, 8, 8, 8)
            main_layout.setSpacing(8)

            splitter = QSplitter(Qt.Horizontal)
            main_layout.addWidget(splitter)

            # Left Panel: File Queue & Controls
            left_panel = QWidget()
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(4, 4, 4, 4)
            left_layout.setSpacing(6)

            # Drop Zone Banner
            self.drop_label = DropZoneLabel("📥 Drag & Drop .log files or folders here")
            self.drop_label.setAlignment(Qt.AlignCenter)
            self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=False))
            left_layout.addWidget(self.drop_label)

            # File Buttons
            btn_box = QHBoxLayout()
            self.btn_add_files = QPushButton("Add Files")
            self.btn_add_files.clicked.connect(self._on_add_files)
            self.btn_add_folder = QPushButton("Add Folder")
            self.btn_add_folder.clicked.connect(self._on_add_folder)
            self.btn_clear = QPushButton("Clear")
            self.btn_clear.clicked.connect(self._on_clear_jobs)

            btn_box.addWidget(self.btn_add_files)
            btn_box.addWidget(self.btn_add_folder)
            btn_box.addWidget(self.btn_clear)
            left_layout.addLayout(btn_box)

            # Sessions Queue List
            left_layout.addWidget(QLabel("Telemetry Sessions:"))
            self.session_list = QListWidget()
            self.session_list.currentItemChanged.connect(self._on_session_selected)
            left_layout.addWidget(self.session_list, stretch=1)

            # Quick Stats Card
            stats_box = QGroupBox("Session Overview")
            stats_layout = QVBoxLayout(stats_box)
            self.lbl_stats_samples = QLabel("Samples: -")
            self.lbl_stats_cpu = QLabel("Peak Sys CPU: -")
            self.lbl_stats_mem = QLabel("RAM Total: -")
            stats_layout.addWidget(self.lbl_stats_samples)
            stats_layout.addWidget(self.lbl_stats_cpu)
            stats_layout.addWidget(self.lbl_stats_mem)
            left_layout.addWidget(stats_box)

            splitter.addWidget(left_panel)

            # Right Panel: Visualization & Process Table
            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(4, 4, 4, 4)
            right_layout.setSpacing(6)

            # Top Toolbar
            tb_layout = QHBoxLayout()
            self.chk_sys_cpu = QCheckBox("System CPU%")
            self.chk_sys_cpu.setChecked(True)
            self.chk_sys_cpu.toggled.connect(self.update_plot)

            self.chk_sys_mem = QCheckBox("System RAM (MB)")
            self.chk_sys_mem.setChecked(True)
            self.chk_sys_mem.toggled.connect(self.update_plot)

            self.chk_cpu_breakdown = QCheckBox("CPU Breakdown")
            self.chk_cpu_breakdown.setChecked(False)
            self.chk_cpu_breakdown.toggled.connect(self.update_plot)

            self.chk_sys_swap = QCheckBox("System Swap (MB)")
            self.chk_sys_swap.setChecked(False)
            self.chk_sys_swap.toggled.connect(self.update_plot)

            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("Filter PID or process name...")
            self.search_input.textChanged.connect(self._filter_process_table)

            self.chk_regex = QCheckBox("Regex")
            self.chk_regex.setToolTip("Enable Regular Expression matching for process search")
            self.chk_regex.toggled.connect(lambda: self._filter_process_table(self.search_input.text()))

            self.btn_open_browser = QPushButton("🌐 Open in Browser (Plotly HTML)")
            self.btn_open_browser.clicked.connect(self.open_in_browser)

            self.btn_export_html = QPushButton("💾 Export HTML")
            self.btn_export_html.clicked.connect(lambda: self.export_html())

            self.btn_export_csv = QPushButton("📊 Export CSV")
            self.btn_export_csv.clicked.connect(self.export_csv)

            # Theme Selector Dropdown
            self.theme_combo = QComboBox()
            for t_name in THEMES.keys():
                self.theme_combo.addItem(t_name)
            self.theme_combo.setCurrentText("Dark Fusion")
            self.theme_combo.currentTextChanged.connect(self.set_theme)

            tb_layout.addWidget(self.chk_sys_cpu)
            tb_layout.addWidget(self.chk_sys_mem)
            tb_layout.addWidget(self.chk_cpu_breakdown)
            tb_layout.addWidget(self.chk_sys_swap)
            tb_layout.addWidget(self.search_input, stretch=1)
            tb_layout.addWidget(self.chk_regex)
            tb_layout.addWidget(self.btn_open_browser)
            tb_layout.addWidget(self.btn_export_html)
            tb_layout.addWidget(self.btn_export_csv)
            tb_layout.addWidget(QLabel("Theme:"))
            tb_layout.addWidget(self.theme_combo)
            right_layout.addLayout(tb_layout)

            # Center Plot Area: Native Matplotlib Canvas & Toolbar
            right_splitter = QSplitter(Qt.Vertical)

            canvas_box = QWidget()
            canvas_layout = QVBoxLayout(canvas_box)
            canvas_layout.setContentsMargins(0, 0, 0, 0)
            canvas_layout.setSpacing(2)

            self.plot_canvas = MplTelemetryCanvas(self)
            self.nav_toolbar = NavigationToolbar2QT(self.plot_canvas, self)
            canvas_layout.addWidget(self.nav_toolbar)
            canvas_layout.addWidget(self.plot_canvas)

            right_splitter.addWidget(canvas_box)

            # Process List Table
            proc_container = QWidget()
            proc_layout = QVBoxLayout(proc_container)
            proc_layout.setContentsMargins(0, 0, 0, 0)
            proc_layout.setSpacing(4)

            # Table Header Actions
            tbl_actions = QHBoxLayout()
            self.tbl_title = QLabel("Processes (Select checkboxes to plot in real-time):")
            tbl_actions.addWidget(self.tbl_title)
            tbl_actions.addStretch()

            btn_top5_cpu = QPushButton("Top 5 CPU")
            btn_top5_cpu.clicked.connect(lambda: self._select_preset("top5_cpu"))
            btn_top5_mem = QPushButton("Top 5 MEM")
            btn_top5_mem.clicked.connect(lambda: self._select_preset("top5_mem"))
            btn_select_all = QPushButton("Select All")
            btn_select_all.clicked.connect(lambda: self._set_all_selection(True))
            btn_clear_all = QPushButton("Clear All")
            btn_clear_all.clicked.connect(lambda: self._set_all_selection(False))

            tbl_actions.addWidget(btn_top5_cpu)
            tbl_actions.addWidget(btn_top5_mem)
            tbl_actions.addWidget(btn_select_all)
            tbl_actions.addWidget(btn_clear_all)
            proc_layout.addLayout(tbl_actions)

            self.process_table = QTableWidget()
            self.process_table.setColumnCount(9)
            self.process_table.setHorizontalHeaderLabels([
                "Plot", "PID", "Process / ARGS", "User", "Max CPU%", "Avg CPU%", "Peak RES (MB)", "Peak SHR (MB)", "%MEM"
            ])
            self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.process_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.process_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.process_table.setAlternatingRowColors(True)
            self.process_table.itemChanged.connect(self._on_table_item_changed)
            proc_layout.addWidget(self.process_table)

            right_splitter.addWidget(proc_container)
            right_splitter.setSizes([450, 270])

            right_layout.addWidget(right_splitter)
            splitter.addWidget(right_panel)
            splitter.setSizes([320, 960])

            # Status Bar & Progress Indicator
            self.progress_bar = QProgressBar()
            self.progress_bar.setFixedHeight(14)
            self.progress_bar.setFixedWidth(200)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setVisible(False)
            self.statusBar().addPermanentWidget(self.progress_bar)
            self.statusBar().showMessage("Ready | Drop log files to begin")

        def show_loading(self, message: str = "Processing log files...", current: int = 0, total: int = 0):
            """Display visual loading indicator, update progress, and set busy cursor."""
            if total > 0:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setValue(current)
                self.progress_bar.setFormat(f"%v / %m ({int(current/total*100)}%)")
            else:
                self.progress_bar.setRange(0, 0)
                self.progress_bar.setFormat("Processing...")

            self.progress_bar.setVisible(True)
            self.statusBar().showMessage(message)
            self.drop_label.setText(f"⏳ {message}")
            self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=True))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            QApplication.processEvents()

        def hide_loading(self, completion_message: Optional[str] = None):
            """Hide progress bar, restore default cursor and styling."""
            self.progress_bar.setVisible(False)
            self.drop_label.setText("📥 Drag & Drop .log files or folders here")
            self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=False))
            QApplication.restoreOverrideCursor()
            if completion_message:
                self.statusBar().showMessage(completion_message)
            QApplication.processEvents()

        def set_theme(self, theme_name: str):
            """Switch application and chart styling to the selected theme."""
            if theme_name not in THEMES:
                return
            self.current_theme = theme_name
            if hasattr(self, 'theme_combo') and self.theme_combo.currentText() != theme_name:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentText(theme_name)
                self.theme_combo.blockSignals(False)

            t = THEMES[theme_name]
            self.setStyleSheet(generate_qss(t))

            if hasattr(self, 'drop_label'):
                self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=False))
            if hasattr(self, 'nav_toolbar'):
                self.nav_toolbar.setStyleSheet(
                    f"background-color: {t['bg_card']}; color: {t['fg_text']}; border: none; padding: 2px;"
                )
            if hasattr(self, 'tbl_title'):
                self.tbl_title.setStyleSheet(f"font-weight: bold; color: {t['fg_text']};")
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {t['border']};
                        border-radius: 4px;
                        background-color: {t['bg_card']};
                        text-align: center; font-size: 10px; font-weight: bold;
                        color: {t['fg_text']};
                    }}
                    QProgressBar::chunk {{
                        background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {t['accent_cpu']}, stop:1 #06b6d4);
                        border-radius: 3px;
                    }}
                """)
            if hasattr(self, 'search_input'):
                self.search_input.setStyleSheet(self._get_search_qss("normal"))
            if hasattr(self, 'plot_canvas'):
                self.plot_canvas.set_theme(theme_name)
                self.update_plot()

        def dragEnterEvent(self, event: QDragEnterEvent):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=True))

        def dragMoveEvent(self, event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dragLeaveEvent(self, event):
            self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=False))

        def dropEvent(self, event: QDropEvent):
            self.drop_label.setStyleSheet(self._get_drop_zone_qss(active=False))
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                self.handle_dropped_paths(paths)

        def handle_dropped_paths(self, paths: List[str]):
            """Scan paths and load discovered sessions with loading indicator and queue deduplication."""
            self.show_loading("Scanning & indexing log files...")
            try:
                jobs = scan_log_paths(paths)
                if not jobs:
                    self.hide_loading()
                    QMessageBox.warning(self, "No Log Files", "No log files found in dropped items.")
                    return

                # De-duplicate against existing jobs in queue
                existing_by_label = {j.label: j for j in self.jobs}
                new_jobs = []
                for j in jobs:
                    if j.label in existing_by_label:
                        ej = existing_by_label[j.label]
                        if j.top_file and not ej.top_file:
                            ej.top_file = j.top_file
                        if j.topmen_file and not ej.topmen_file:
                            ej.topmen_file = j.topmen_file
                    else:
                        self.jobs.append(j)
                        new_jobs.append(j)

                self._update_session_list()
                target_job = new_jobs[0] if new_jobs else jobs[0]

                # Synchronize session list active row selection
                for r in range(self.session_list.count()):
                    item = self.session_list.item(r)
                    if item and getattr(item.data(Qt.UserRole), "label", None) == target_job.label:
                        self.session_list.setCurrentRow(r)
                        break

                self.load_job(target_job)
            finally:
                if self.progress_bar.isVisible():
                    self.hide_loading()

        def _on_add_files(self):
            files, _ = QFileDialog.getOpenFileNames(self, "Select Log Files", "", "Log Files (*.log);;All Files (*)")
            if files:
                self.handle_dropped_paths(files)

        def _on_add_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Logs")
            if folder:
                self.handle_dropped_paths([folder])

        def _on_clear_jobs(self):
            self.jobs.clear()
            self.current_job = None
            self.current_parsed = None
            self.session_list.clear()
            self.process_table.setRowCount(0)
            self.plot_canvas.ax_cpu.clear()
            self.plot_canvas.ax_mem.clear()
            self.plot_canvas.draw_idle()
            self.statusBar().showMessage("Queue cleared")

        def _update_session_list(self):
            self.session_list.clear()
            for job in self.jobs:
                item_text = job.label
                if job.top_file and job.topmen_file:
                    item_text += " [CPU + MEM]"
                elif job.top_file:
                    item_text += " [CPU]"
                elif job.topmen_file:
                    item_text += " [MEM]"
                
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, job)
                self.session_list.addItem(item)

        def _on_session_selected(self, current: QListWidgetItem, previous):
            if current:
                job = current.data(Qt.UserRole)
                if job:
                    self.load_job(job)

        def load_job(self, job: LogJob):
            """Parse and display telemetry for a selected LogJob with visual progress."""
            self.show_loading(f"Parsing telemetry: {job.label}...")
            try:
                self.current_job = job
                parsed = self.parser.parse_job(job)
                if not parsed:
                    self.hide_loading()
                    QMessageBox.critical(self, "Error", f"Failed to parse log session {job.label}")
                    return

                self.current_parsed = parsed
                self.populate_process_table(parsed)

                sample_count = len(parsed.snapshots)
                peak_cpu = max(parsed.system_metrics.get("%cpu_total", [0.0])) if parsed.system_metrics.get("%cpu_total") else 0.0
                total_ram = parsed.system_metrics.get("mem_total_mb", [0.0])[0] if parsed.system_metrics.get("mem_total_mb") else 0.0
                
                self.lbl_stats_samples.setText(f"Samples: {sample_count}")
                self.lbl_stats_cpu.setText(f"Peak Sys CPU: {peak_cpu:.1f}%")
                self.lbl_stats_mem.setText(f"RAM Total: {total_ram:.0f} MB")

                # Auto-select top 3 CPU processes
                top_cpu = parsed.get_top_pids_by_cpu(limit=3)
                top_pids = {p[0] for p in top_cpu}

                self.process_table.blockSignals(True)
                for row in range(self.process_table.rowCount()):
                    pid_item = self.process_table.item(row, 1)
                    if pid_item and int(pid_item.text()) in top_pids:
                        chk_item = self.process_table.item(row, 0)
                        if chk_item:
                            chk_item.setCheckState(Qt.Checked)
                self.process_table.blockSignals(False)

                self.update_plot()
                self.hide_loading(f"Ready | Loaded {job.label} ({sample_count} samples)")
            finally:
                if self.progress_bar.isVisible():
                    self.hide_loading()

        def populate_process_table(self, parsed: ParsedLogV2):
            """Fill the process table with all observed PIDs, enabling numeric sorting."""
            self.process_table.setSortingEnabled(False)
            self.process_table.blockSignals(True)
            self.process_table.setRowCount(0)

            ranked = parsed.get_top_pids_by_cpu(limit=len(parsed.get_all_pids()))

            for pid, args, max_cpu in ranked:
                m = parsed.get_pid_metrics(pid)
                row = self.process_table.rowCount()
                self.process_table.insertRow(row)

                # Col 0: Checkbox
                chk_item = SortableTableWidgetItem("", sort_value=0)
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk_item.setCheckState(Qt.Unchecked)
                self.process_table.setItem(row, 0, chk_item)

                # Col 1: PID
                pid_item = SortableTableWidgetItem(str(pid), sort_value=int(pid))
                pid_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 1, pid_item)

                # Col 2: ARGS
                self.process_table.setItem(row, 2, SortableTableWidgetItem(m["args"], sort_value=m["args"].lower()))

                # Col 3: User
                user_str = ""
                for s in parsed.snapshots:
                    if pid in s.processes:
                        user_str = s.processes[pid].user
                        break
                self.process_table.setItem(row, 3, SortableTableWidgetItem(user_str, sort_value=user_str.lower()))

                # Col 4: Max CPU%
                max_cpu_item = SortableTableWidgetItem(f"{m['max_cpu']:.1f}%", sort_value=float(m['max_cpu']))
                max_cpu_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 4, max_cpu_item)

                # Col 5: Avg CPU%
                avg_cpu_item = SortableTableWidgetItem(f"{m['avg_cpu']:.1f}%", sort_value=float(m['avg_cpu']))
                avg_cpu_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 5, avg_cpu_item)

                # Col 6: Peak RES (MB)
                res_item = SortableTableWidgetItem(f"{m['max_res_mb']:.1f}", sort_value=float(m['max_res_mb']))
                res_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 6, res_item)

                # Col 7: Peak SHR (MB)
                max_shr = max(m["shr_mb"]) if m["shr_mb"] else 0.0
                shr_item = SortableTableWidgetItem(f"{max_shr:.1f}", sort_value=float(max_shr))
                shr_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 7, shr_item)

                # Col 8: %MEM
                mem_pct = max(m["mem_pct"]) if m["mem_pct"] else 0.0
                mem_item = SortableTableWidgetItem(f"{mem_pct:.1f}%", sort_value=float(mem_pct))
                mem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.process_table.setItem(row, 8, mem_item)

            self.process_table.blockSignals(False)
            self.process_table.setSortingEnabled(True)

        def _on_table_item_changed(self, item: QTableWidgetItem):
            if item.column() == 0:
                self.update_plot()

        def _filter_process_table(self, query: Optional[str] = None):
            """Filter table rows by plain text or regex query."""
            if query is None:
                query = self.search_input.text()
            query = query.strip()

            use_regex = hasattr(self, 'chk_regex') and self.chk_regex.isChecked()
            compiled_pattern = None

            if query and use_regex:
                try:
                    compiled_pattern = re.compile(query, re.IGNORECASE)
                    self.search_input.setStyleSheet(self._get_search_qss("valid_regex"))
                except re.error:
                    self.search_input.setStyleSheet(self._get_search_qss("invalid_regex"))
                    self.statusBar().showMessage("Invalid regular expression pattern")
                    return
            else:
                self.search_input.setStyleSheet(self._get_search_qss("normal"))

            query_lower = query.lower()

            for r in range(self.process_table.rowCount()):
                pid_item = self.process_table.item(r, 1)
                name_item = self.process_table.item(r, 2)
                user_item = self.process_table.item(r, 3)

                pid_text = pid_item.text() if pid_item else ""
                name_text = name_item.text() if name_item else ""
                user_text = user_item.text() if user_item else ""

                if not query:
                    match = True
                elif use_regex and compiled_pattern:
                    match = bool(
                        compiled_pattern.search(pid_text) or
                        compiled_pattern.search(name_text) or
                        compiled_pattern.search(user_text)
                    )
                else:
                    combined = f"{pid_text} {name_text} {user_text}".lower()
                    match = query_lower in combined

                self.process_table.setRowHidden(r, not match)

        def _select_preset(self, preset: str):
            if not self.current_parsed:
                return
            if preset == "top5_cpu":
                top = {p[0] for p in self.current_parsed.get_top_pids_by_cpu(limit=5)}
            elif preset == "top5_mem":
                top = {p[0] for p in self.current_parsed.get_top_pids_by_mem(limit=5)}
            else:
                top = set()

            self.process_table.blockSignals(True)
            for r in range(self.process_table.rowCount()):
                pid = int(self.process_table.item(r, 1).text())
                chk = self.process_table.item(r, 0)
                chk.setCheckState(Qt.Checked if pid in top else Qt.Unchecked)
            self.process_table.blockSignals(False)
            self.update_plot()

        def _set_all_selection(self, checked: bool):
            self.process_table.blockSignals(True)
            state = Qt.Checked if checked else Qt.Unchecked
            for r in range(self.process_table.rowCount()):
                chk = self.process_table.item(r, 0)
                if chk:
                    chk.setCheckState(state)
            self.process_table.blockSignals(False)
            self.update_plot()

        def get_selected_pids(self) -> List[int]:
            """Return list of PIDs currently checked in the process table."""
            pids = []
            for r in range(self.process_table.rowCount()):
                chk = self.process_table.item(r, 0)
                if chk and chk.checkState() == Qt.Checked:
                    pid = int(self.process_table.item(r, 1).text())
                    pids.append(pid)
            return pids

        def update_plot(self):
            """Regenerate embedded Matplotlib telemetry plot."""
            if not self.current_parsed:
                return

            selected_pids = self.get_selected_pids()
            self.plot_canvas.plot_telemetry(
                data=self.current_parsed,
                selected_pids=selected_pids,
                plot_sys_cpu=self.chk_sys_cpu.isChecked(),
                plot_sys_mem=self.chk_sys_mem.isChecked(),
                plot_cpu_breakdown=self.chk_cpu_breakdown.isChecked() if hasattr(self, 'chk_cpu_breakdown') else False,
                plot_sys_swap=self.chk_sys_swap.isChecked() if hasattr(self, 'chk_sys_swap') else False
            )

        def open_in_browser(self):
            """Generate interactive Plotly report and open in default web browser."""
            if not self.current_parsed:
                QMessageBox.warning(self, "No Data", "Please load a log file first.")
                return
            import tempfile
            report_name = f"{self.current_job.label if self.current_job else 'top_plot'}_interactive.html"
            temp_path = os.path.join(tempfile.gettempdir(), report_name)
            self.export_html(file_path=temp_path)
            webbrowser.open(f"file:///{os.path.abspath(temp_path).replace(os.sep, '/')}")
            self.statusBar().showMessage(f"Opened interactive plot in web browser")

        def export_html(self, file_path: Optional[str] = None):
            """Export current visualization to a standalone HTML report."""
            if not self.current_parsed:
                QMessageBox.warning(self, "No Data", "Please load a log file first.")
                return

            if not file_path:
                default_name = f"{self.current_job.label}_telemetry_report.html" if self.current_job else "telemetry_report.html"
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Save Interactive HTML Report", default_name, "HTML Files (*.html)"
                )
                if not file_path:
                    return

            generator = PlotlyHtmlGenerator(self.current_parsed)
            generator.save_html(
                output_path=file_path,
                selected_pids=self.get_selected_pids(),
                plot_sys_cpu=self.chk_sys_cpu.isChecked(),
                plot_sys_mem=self.chk_sys_mem.isChecked(),
                plot_cpu_breakdown=self.chk_cpu_breakdown.isChecked() if hasattr(self, 'chk_cpu_breakdown') else False,
                plot_sys_swap=self.chk_sys_swap.isChecked() if hasattr(self, 'chk_sys_swap') else False,
                theme_name=self.current_theme
            )
            self.statusBar().showMessage(f"Report exported to {file_path}")

        def export_csv(self, file_path: Optional[str] = None):
            """Export current telemetry data to a CSV file."""
            if not self.current_parsed:
                QMessageBox.warning(self, "No Data", "Please load a log file first.")
                return

            if not file_path or not isinstance(file_path, str):
                default_name = f"{self.current_job.label}_telemetry.csv" if self.current_job else "telemetry.csv"
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Export Telemetry CSV", default_name, "CSV Files (*.csv)"
                )
                if not file_path:
                    return

            self.current_parsed.to_csv(file_path)
            self.statusBar().showMessage(f"Telemetry exported to {file_path}")


def main():
    """Main application entry point."""
    if not GUI_AVAILABLE:
        print("Error: PySide6 and matplotlib are required to run Top Log Analyzer v2.0 GUI.")
        sys.exit(1)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = TopPlotMainWindow()

    if len(sys.argv) > 1:
        window.handle_dropped_paths(sys.argv[1:])

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

