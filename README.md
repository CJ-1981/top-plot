# ⚡ Top Log Analyzer — Standalone Web Edition

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-success?style=flat-square&logo=github)](https://CJ-1981.github.io/top-plot/)
[![Plotly](https://img.shields.io/badge/Visualizations-Plotly.js-orange?style=flat-square&logo=plotly)](https://plotly.com/)
[![Offline Ready](https://img.shields.io/badge/Runtime-100%25%20Offline%20Single--File-blue?style=flat-square)](https://github.com/CJ-1981/top-plot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

An advanced, zero-dependency, single-file telemetry analyzer for Linux, Android, and automotive embedded system `top` logs. 

All log parsing, metric correlation, and dual-axis chart rendering run **100% client-side** directly in your web browser. No server, no Python, and no external network connections required.

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

### 1. 📂 Intelligent Multi-File & Paired Log Drag & Drop
- **Automotive Log Pairing**: Automatically identifies and merges paired `log_top@<timestamp>` (CPU metrics) and `log_topmen@<timestamp>` (Memory metrics) into a unified timeline.
- **Multi-Session Management**: Drop multiple independent files or batches simultaneously to navigate between sessions using dynamic session pills.
- **Global Drop Zone**: Drop files anywhere on the browser window to load logs instantly without accidental page navigation.

### 2. 📈 Interactive Dual Y-Axis Telemetry Charts
- **Dual Y-Axes**: Synchronized visualization of CPU Usage (`%`) on the primary left axis and Physical Memory (`RES MB`) on the secondary right axis.
- **Uncapped Hover Cards**: Full, untruncated process arguments and package names (e.g. `com.google.android.apps.maps`) with instant metric readouts.
- **Interactive Legend Controls**: Click any legend handle or label to interactively hide, dim, or highlight plot curves.
- **Hover Crosshair Tracking**: Unified tooltip and guide line tracking nearest sample indices.

### 3. 🎨 5 High-Contrast Color Themes
Switch dynamically between curated, WCAG-compliant color palettes with perfect SVG contrast:
- 🌌 **Dark Fusion** (Default deep slate & vibrant emerald/amber)
- ☀️ **Light Mode** (Crisp paper white with deep jewel curves)
- 🌆 **Midnight Neon** (Vibrant cyber neon on obsidian)
- 🌲 **Solarized Dark** (Precision palette for extended analysis)
- 🎨 **Monokai** (Classic developer theme with neon accents)

### 4. 🗃️ Process Control & Filter Table
- **Numeric Column Sorting**: Sort by PID, Max CPU%, Avg CPU%, Peak RES (MB), and Max MEM%.
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

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
