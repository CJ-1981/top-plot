# ⚡ Top Log Analyzer — Standalone Web & Desktop Edition

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-success?style=flat-square&logo=github)](https://CJ-1981.github.io/top-plot/)
[![Version](https://img.shields.io/badge/Version-v2.1.0-blue.svg?style=flat-square)](https://github.com/CJ-1981/top-plot)
[![Build Date](https://img.shields.io/badge/Build-2026--10--28-informational.svg?style=flat-square)](https://github.com/CJ-1981/top-plot)
[![Plotly](https://img.shields.io/badge/Visualizations-Plotly.js-orange?style=flat-square&logo=plotly)](https://plotly.com/)
[![Offline Ready](https://img.shields.io/badge/Runtime-100%25%20Offline%20Single--File-brightgreen?style=flat-square)](https://github.com/CJ-1981/top-plot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

An advanced, zero-dependency, single-file telemetry analyzer for Linux, Android, and automotive embedded system `top` and `/proc/meminfo` logs (Current Release: **v2.1.0**, Build: `2026-10-28`). 

Available both as a **100% offline standalone web application** (running entirely client-side inside your browser with zero server and zero network requests) and as a **rich native Qt desktop application**.

---

## 🌐 Live Demo & Instant Access

👉 **[Launch Top Log Analyzer Web Edition](https://CJ-1981.github.io/top-plot/)**

- **Instant 1-Click Demo**: Click **"🚀 Load Demo Log"** to immediately explore an interactive automotive telemetry dataset.
- **Air-Gapped & Offline Ready**: Download [`top_log_analyzer_standalone.html`](top_log_analyzer_standalone.html) or [`index.html`](index.html), copy it to a USB drive or isolated test bench, and double-click to open in Chrome, Edge, Firefox, or Safari.

---

## 📸 Screenshots

### Dark Fusion Theme
![Top Log Analyzer - Dark Fusion](docs/images/standalone_dark_fusion.png)

### Light Mode Theme
![Top Log Analyzer - Light Mode](docs/images/standalone_light_mode.png)

### Interactive Regex Filtering & Process Telemetry Table
![Interactive Process Table](docs/images/standalone_features_search.png)

---

## 🚀 Key Features

### 1. 📂 Intelligent Multi-File Drop & Virtual Path Isolation
- **Automotive Log Pairing**: Automatically identifies and merges paired `log_top@<timestamp>` (CPU metrics) and `log_topmen@<timestamp>` (Memory metrics) into a unified timeline.
- **Parent Folder Disambiguation**: When dropping directory hierarchies (e.g. `Run_01/log_top...` and `Run_02/log_top...`), relative paths via `webkitRelativePath` ensure logs with identical filenames are never mixed or overwritten.
- **Multi-Drop Virtual Paths**: Dropping repeated batches with identical names automatically partitions files into isolated virtual containers (`Drop 1/`, `Drop 2/`, ...).
- **Inline Session Renaming (✏️)**: Click the rename icon next to any active session pill to quickly customize session labels on the fly.
- **Individual Session Removal (✕)**: Remove specific sessions directly from their pills without disrupting or reloading remaining datasets.
- **Workspace Clear All (🗑️ Clear All)**: Reset the workspace, clear all loaded sessions, purge plots, and return to the upload zone with a single click.
- **Global Drag & Drop Zone**: Drop single files, multiple selections, or entire folders anywhere on the window.

### 2. ⚡ Batch Export All (Web & Desktop)
Export all loaded sessions simultaneously in one seamless operation:
- **Desktop Application (PyQt6)**:
  - Generates comprehensive datasets: CSV metrics, structured JSON, 150 DPI high-resolution PNG charts, and standalone interactive HTML reports.
  - Flexibility to save exports **next to the original log files** or export all sessions into a **custom selected directory**.
- **Standalone Web Edition**:
  - **Direct Folder Export (HTML5 File System Access API)**: On supported browsers (Chrome, Edge), select an export folder once to stream all CSV, JSON, PNG, and HTML reports directly to disk without individual download prompts.
  - **Zero-Dependency ZIP Archive**: For Firefox, Safari, or restricted environments, bundles all session telemetry reports into a single `.zip` file using a 100% pure vanilla JavaScript deflate/store engine and custom CRC-32 checksum calculation.

### 3. 📈 Interactive Dual Y-Axis Telemetry & System Analytics
- **Dual Y-Axes**: Synchronized visualization of CPU Usage (`%`) on the primary left axis and Physical Memory (`RES MB`) on the secondary right axis.
- **System CPU Breakdown**: Detailed system-level CPU traces including User (`usr`), System (`sys`), IO Wait (`io`), Nice (`nic`), and IRQ (`irq`).
- **Swap & Shared Memory Tracking**: Trace process swap usage (`SWAP MB`) and shared memory (`SHR MB`) alongside Resident (`RES`) and Virtual (`VIRT`) allocations.
- **`/proc/meminfo` System Memory Alignment**: Tracks system-wide memory pressure, correlating `MemTotal`, `MemFree`, `MemAvailable`, `Buffers`, `Cached`, and `SReclaimable`.
- **Uncapped Hover Cards**: Full, untruncated process arguments and package names with instant metric readouts and cursor crosshairs.
- **Timeline RangeSlider**: Pan and zoom smoothly across hours of high-frequency log samples with mini-overview maps.
- **Interactive Annotations**: Double-click or trigger annotation markers to pinpoint thermal throttling, crashes, or system spikes.

### 4. 🔬 Point-in-Time Process Snapshot Drilldown
- Click any point on the telemetry timeline to open a modal inspection window detailing the exact system state at that microsecond:
  - Overall system CPU state and memory saturation.
  - Complete process table with instant regex search and CSV export for that specific snapshot.

### 5. 🎨 5 High-Contrast Color Themes
Switch dynamically between curated, WCAG-compliant color palettes with perfect SVG contrast:
- 🌌 **Dark Fusion** (Default deep slate & vibrant emerald/amber)
- ☀️ **Light Mode** (Crisp paper white with deep jewel curves)
- 🌆 **Midnight Neon** (Vibrant cyber neon on obsidian)
- 🌲 **Solarized Dark** (Precision palette for extended analysis)
- 🎨 **Monokai** (Classic developer theme with neon accents)

### 6. 🗃️ Process Control & Filter Table
- **Numeric Column Sorting**: Sort by PID, Max CPU%, Avg CPU%, Peak RES (MB), Max SHR (MB), and Max MEM%.
- **Regex & Free-Text Filter**: Instantly isolate processes with standard text queries or full regular expressions (`google|system|mediaserver`).
- **Batch Action Buttons**: Instant 1-click presets for **Top 5 CPU**, **Top 5 MEM**, **Select All**, and **Clear All**.

---

## 📁 Repository Structure

```
├── index.html                        # GitHub Pages entry point (self-contained app)
├── top_log_analyzer_standalone.html  # Standalone single-file HTML distributable
├── docs/
│   └── images/                       # Screenshots and visual assets
├── README.md                         # Documentation
└── LICENSE                           # MIT License
```

---

## 📄 Supported Log Formats

- **Automotive Paired Logs**: `log_top@...` and `log_topmen@...` pairs (parsed and aligned automatically)
- **Standard Linux `top`**: `top -b` snapshot logs
- **Android `top`**: Output from `adb shell top -b -d 1`
- **Linux `/proc/meminfo`**: Periodic memory dumps matched to timeline timestamps

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
