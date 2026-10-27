#!/usr/bin/env python
"""
TDD Test Suite for Top Plot Analyzer Version 2.0
"""

import pytest

def test_parse_memory_mb():
    """Test memory string parsing to MB float."""
    from top_plot_v2 import parse_memory_mb

    assert parse_memory_mb("569M") == pytest.approx(569.0)
    assert parse_memory_mb("19G") == pytest.approx(19 * 1024.0)
    assert parse_memory_mb("1024K") == pytest.approx(1.0)
    assert parse_memory_mb("4.9M") == pytest.approx(4.9)
    assert parse_memory_mb("0") == pytest.approx(0.0)
    assert parse_memory_mb("") == pytest.approx(0.0)
    assert parse_memory_mb(None) == pytest.approx(0.0)


def test_parse_process_row():
    """Test parsing a single process table row."""
    from top_plot_v2 import parse_process_row, ProcessRecord

    line1 = " 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps"
    rec1 = parse_process_row(line1)
    assert rec1 is not None
    assert rec1.pid == 4146
    assert rec1.user == "u10_a157"
    assert rec1.res_mb == pytest.approx(569.0)
    assert rec1.shr_mb == pytest.approx(328.0)
    assert rec1.state == "S"
    assert rec1.cpu == pytest.approx(93.1)
    assert rec1.mem_pct == pytest.approx(7.6)
    assert rec1.args == "com.google.android.apps.maps"

    line2 = "15358 root         30  10  10G 5.4M 4.7M R  3.4   0.0   0:00.06 logcat_ecarx -f /data/log.txt"
    rec2 = parse_process_row(line2)
    assert rec2 is not None
    assert rec2.pid == 15358
    assert rec2.args == "logcat_ecarx -f /data/log.txt"

    # Non-process lines should return None
    assert parse_process_row("Tasks: 568 total, 2 running") is None
    assert parse_process_row("PID USER PR NI VIRT RES SHR S[%CPU] %MEM TIME+ ARGS") is None
    assert parse_process_row("") is None


def test_log_parser_v2_snippet():
    """Test LogParserV2 on a multi-sample snippet with CPU and per-PID data."""
    from top_plot_v2 import LogParserV2

    sample_snippet = """20260917_17-33-01
top_cpu:
Tasks: 568 total,   2 running, 566 sleeping,   0 stopped,   0 zombie
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
 Swap:  4194300K total,   255488K used,  3938812K free,  2436928K cached
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S  3.4   5.5   1:40.49 system_server
 6864 u10_a160     20   0  18G 198M 125M S  6.8   2.6   2:36.19 com.android.vending:background

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
"""

    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)
    
    assert parsed is not None
    assert len(parsed.snapshots) == 2
    
    # Check timestamps
    assert parsed.timestamps == ["20260917_17-33-01", "20260917_17-33-11"]
    
    # Check system CPU summary extraction
    assert "%cpu_total" in parsed.system_metrics
    assert len(parsed.system_metrics["%cpu_total"]) == 2
    # First sample: 800 - 528 = 272%
    assert parsed.system_metrics["%cpu_total"][0] == pytest.approx(272.0)
    # Second sample: 800 - 322 = 478%
    assert parsed.system_metrics["%cpu_total"][1] == pytest.approx(478.0)
    
    # Check memory summary extraction (in MB)
    assert "mem_used_mb" in parsed.system_metrics
    assert parsed.system_metrics["mem_used_mb"][0] == pytest.approx(6227624 / 1024.0)

    # Check PID extraction
    assert 4146 in parsed.get_all_pids()
    assert 2078 in parsed.get_all_pids()
    assert 6864 in parsed.get_all_pids()
    
    # Check PID time series
    p4146_data = parsed.get_pid_metrics(4146)
    assert p4146_data["args"] == "com.google.android.apps.maps"
    assert p4146_data["cpu"] == [93.1, 62.5]
    assert p4146_data["res_mb"] == [pytest.approx(569.0), pytest.approx(566.0)]
    assert p4146_data["max_cpu"] == pytest.approx(93.1)

    # Check top PIDs ranking
    top_cpu = parsed.get_top_pids_by_cpu(limit=2)
    assert len(top_cpu) == 2
    assert top_cpu[0][0] == 4146  # PID 4146 had peak 93.1%
    assert top_cpu[1][0] == 6864  # PID 6864 had peak 84.3%


def test_parser_real_log_samples():
    """Verify parsing real log samples under log_samples/ directory."""
    import os
    from top_plot_v2 import LogParserV2

    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    assert os.path.exists(samples_dir), "log_samples directory must exist"

    sample_top_1 = os.path.join(samples_dir, "log_top@20260917_17-33-01-008-Batch_3.log")
    sample_topmen_1 = os.path.join(samples_dir, "log_topmen@20260917_17-33-01-008-Batch_3.log")

    parser = LogParserV2()

    # Test top log
    parsed_top = parser.parse_file(sample_top_1, encoding="utf-8")
    assert parsed_top is not None
    assert len(parsed_top.snapshots) > 10
    assert len(parsed_top.timestamps) == len(parsed_top.snapshots)
    assert "%cpu_total" in parsed_top.system_metrics
    assert len(parsed_top.system_metrics["%cpu_total"]) == len(parsed_top.snapshots)

    # Verify PIDs extracted from real file
    all_pids = parsed_top.get_all_pids()
    assert len(all_pids) > 20
    assert 4146 in all_pids  # Google Maps
    assert 2078 in all_pids  # system_server

    maps_metrics = parsed_top.get_pid_metrics(4146)
    assert "maps" in maps_metrics["args"].lower()
    assert maps_metrics["max_cpu"] > 50.0  # Maps peaked above 90%
    assert maps_metrics["max_res_mb"] > 100.0  # Maps RES was > 500MB

    # Test topmen log with /proc/meminfo
    parsed_topmen = parser.parse_file(sample_topmen_1, encoding="utf-8")
    assert parsed_topmen is not None
    assert len(parsed_topmen.snapshots) > 10
    
    # Should have meminfo metrics
    assert "meminfo_MemAvailable_mb" in parsed_topmen.system_metrics
    assert len(parsed_topmen.system_metrics["meminfo_MemAvailable_mb"]) > 0
    assert parsed_topmen.system_metrics["meminfo_MemAvailable_mb"][0] > 1000.0  # > 1GB available


def test_plotly_html_generator():
    """Test generating interactive HTML plot with Plotly for selected PIDs."""
    from top_plot_v2 import LogParserV2, PlotlyHtmlGenerator

    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S  3.4   5.5   1:40.49 system_server

20260917_17-33-11
top_cpu:
  Mem:  7594756K total,  6340152K used,  1254604K free,    15396K buffers
800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S 12.0   5.5   1:41.00 system_server
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)

    generator = PlotlyHtmlGenerator(parsed)
    # Generate HTML with PID 4146 selected
    html_content = generator.generate_html(selected_pids=[4146], plot_sys_cpu=True, plot_sys_mem=True)

    assert html_content is not None
    assert "<html" in html_content.lower() or "<div" in html_content.lower()
    assert "com.google.android.apps.maps" in html_content
    assert "plotly" in html_content.lower()


def test_scan_log_paths():
    """Test folder and file drag-and-drop ingestion scanner."""
    import os
    from top_plot_v2 import scan_log_paths, LogJob

    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    
    # 1. Dropping the samples folder
    jobs = scan_log_paths([samples_dir])
    assert len(jobs) >= 2  # Batch_3 and Batch_37

    batch3_job = next((j for j in jobs if "Batch_3" in j.label), None)
    assert batch3_job is not None
    assert batch3_job.top_file is not None
    assert "log_top@" in batch3_job.top_file
    assert batch3_job.topmen_file is not None
    assert "log_topmen@" in batch3_job.topmen_file

    # 2. Dropping individual file
    file_jobs = scan_log_paths([batch3_job.top_file])
    assert len(file_jobs) == 1
    assert file_jobs[0].top_file == batch3_job.top_file
    # Automatic pairing: should discover the paired topmen file in the same directory!
    assert file_jobs[0].topmen_file == batch3_job.topmen_file


def test_parse_job_merging_top_and_topmen():
    """Test merging paired top and topmen files into a unified dataset."""
    import os
    from top_plot_v2 import scan_log_paths, LogParserV2

    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    jobs = scan_log_paths([samples_dir])
    batch3_job = next(j for j in jobs if "Batch_3" in j.label)

    parser = LogParserV2()
    unified_data = parser.parse_job(batch3_job)

    assert unified_data is not None
    assert len(unified_data.snapshots) > 10

    # System metrics should have BOTH CPU and Meminfo
    assert "%cpu_total" in unified_data.system_metrics
    assert "meminfo_MemAvailable_mb" in unified_data.system_metrics

    # Processes should have both CPU peak and memory info
    maps = unified_data.get_pid_metrics(4146)
    assert maps["max_cpu"] > 50.0
    assert maps["max_res_mb"] > 100.0


def test_qt_main_window_headless():
    """Test Qt Main Window creation, drag-drop processing, and table population in headless mode."""
    import os
    import tempfile
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from top_plot_v2 import TopPlotMainWindow, scan_log_paths

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = TopPlotMainWindow()
    assert window is not None
    assert "Top Log Analyzer" in window.windowTitle()

    # Test loading real sample session
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    jobs = scan_log_paths([samples_dir])
    assert len(jobs) > 0

    # Load first job
    window.load_job(jobs[0])

    # Verify table has processes
    assert window.process_table.rowCount() > 10

    # Verify PID selection
    selected_pids = window.get_selected_pids()
    assert len(selected_pids) > 0  # Default top PIDs should be auto-selected

    # Test HTML export
    with tempfile.TemporaryDirectory() as td:
        export_file = os.path.join(td, "test_report.html")
        window.export_html(export_file)
        assert os.path.exists(export_file)
        assert os.path.getsize(export_file) > 1000

    # Verify embedded canvas exists and has plotted data
    assert hasattr(window, "plot_canvas")
    assert window.plot_canvas is not None
    # Check that lines were drawn on ax_cpu
    assert len(window.plot_canvas.ax_cpu.lines) > 0


def test_loading_indicator():
    """Test loading and processing visual indicator in Qt UI."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication, QProgressBar
    from top_plot_v2 import TopPlotMainWindow

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = TopPlotMainWindow()
    window.show()
    assert hasattr(window, "progress_bar")
    assert isinstance(window.progress_bar, QProgressBar)
    assert not window.progress_bar.isVisible()

    # Trigger show_loading
    window.show_loading("Parsing 2 log files...", 0, 100)
    assert window.progress_bar.isVisible()
    assert "Parsing" in window.statusBar().currentMessage()

    # Trigger hide_loading
    window.hide_loading("Ready | 2 files loaded")
    assert not window.progress_bar.isVisible()
    assert "Ready | 2 files loaded" in window.statusBar().currentMessage()


def test_process_table_sorting_numeric():
    """Test numeric sorting on process table columns (CPU%, RES MB)."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from top_plot_v2 import TopPlotMainWindow, scan_log_paths

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = TopPlotMainWindow()
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    jobs = scan_log_paths([samples_dir])
    window.load_job(jobs[0])

    table = window.process_table
    assert table.isSortingEnabled()

    # Sort by Max CPU% (Column 4) descending
    table.sortItems(4, Qt.DescendingOrder)
    top_cpu_val = float(table.item(0, 4).text().replace("%", ""))
    second_cpu_val = float(table.item(1, 4).text().replace("%", ""))
    assert top_cpu_val >= second_cpu_val
    assert top_cpu_val > 50.0  # Peak should be ~93%

    # Sort by Peak RES MB (Column 6) descending
    table.sortItems(6, Qt.DescendingOrder)
    top_res_val = float(table.item(0, 6).text())
    second_res_val = float(table.item(1, 6).text())
    assert top_res_val >= second_res_val
    assert top_res_val > 200.0  # Peak RES should be > 500MB


def test_process_table_regex_filter():
    """Test free text search and regex filtering on process table."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from top_plot_v2 import TopPlotMainWindow, scan_log_paths

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = TopPlotMainWindow()
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    jobs = scan_log_paths([samples_dir])
    window.load_job(jobs[0])

    table = window.process_table
    assert hasattr(window, "chk_regex")

    # 1. Plain text filter without regex
    window.chk_regex.setChecked(False)
    window.search_input.setText("maps")
    visible_rows = [r for r in range(table.rowCount()) if not table.isRowHidden(r)]
    assert len(visible_rows) > 0
    for r in visible_rows:
        text = (table.item(r, 1).text() + " " + table.item(r, 2).text()).lower()
        assert "maps" in text

    # 2. Regex filter: (maps|system_server)
    window.chk_regex.setChecked(True)
    window.search_input.setText(r"(maps|system_server)")
    visible_rows = [r for r in range(table.rowCount()) if not table.isRowHidden(r)]
    assert len(visible_rows) >= 2
    for r in visible_rows:
        text = (table.item(r, 1).text() + " " + table.item(r, 2).text()).lower()
        assert ("maps" in text) or ("system_server" in text)

    # 3. Invalid regex handling (should not crash)
    window.search_input.setText("[unclosed_bracket")
    # Should catch re.error gracefully without crashing


def test_theme_switching():
    """Test dynamic switching between multiple visual color themes."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication, QComboBox
    from top_plot_v2 import TopPlotMainWindow, scan_log_paths, THEMES

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = TopPlotMainWindow()
    assert hasattr(window, "theme_combo")
    assert isinstance(window.theme_combo, QComboBox)
    assert window.theme_combo.count() >= 4

    # Default theme
    assert window.current_theme in THEMES

    # Switch to Light Mode
    window.set_theme("Light Mode")
    assert window.current_theme == "Light Mode"
    assert window.plot_canvas.theme_name == "Light Mode"

    # Switch to Midnight Neon
    window.set_theme("Midnight Neon")
    assert window.current_theme == "Midnight Neon"
    assert window.plot_canvas.theme_name == "Midnight Neon"

    # Switch back to Dark Fusion
    window.set_theme("Dark Fusion")
    assert window.current_theme == "Dark Fusion"


def test_html_export_theme_and_interactive_table():
    """Test that HTML export adapts to color themes and embeds an interactive process table."""
    from top_plot_v2 import LogParserV2, PlotlyHtmlGenerator

    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S  3.4   5.5   1:40.49 system_server
 6864 u10_a160     20   0  18G 198M 125M S  6.8   2.6   2:36.19 com.android.vending:background

20260917_17-33-11
top_cpu:
  Mem:  7594756K total,  6340152K used,  1254604K free,    15396K buffers
800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 6864 u10_a160     20   0  18G 198M 125M S 84.3   2.6   2:44.43 com.android.vending:background
 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 com.google.android.apps.maps
 2078 system       18  -2  21G 408M 279M S 12.0   5.5   1:41.00 system_server
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)
    generator = PlotlyHtmlGenerator(parsed)

    # 1. Test Light Mode export
    html_light = generator.generate_html(selected_pids=[4146], theme_name="Light Mode")
    assert "#f8fafc" in html_light or "plotly_white" in html_light
    assert 'data-theme="Light Mode"' in html_light or "Light Mode" in html_light

    # 2. Test Midnight Neon export
    html_neon = generator.generate_html(selected_pids=[4146], theme_name="Midnight Neon")
    assert "#0a0e17" in html_neon or "#111827" in html_neon

    # 3. Test interactive process table presence & columns
    assert 'id="processTable"' in html_neon or 'id="process-table"' in html_neon
    assert "<table" in html_neon
    assert "com.google.android.apps.maps" in html_neon
    assert "system_server" in html_neon
    assert "4146" in html_neon
    assert "2078" in html_neon

    # 4. Table controls: search box, checkboxes, quick filter buttons
    assert 'id="processSearch"' in html_neon or 'id="tableSearch"' in html_neon
    assert 'type="checkbox"' in html_neon
    assert "Top 5 CPU" in html_neon
    assert "Clear All" in html_neon

    # 5. Client-side JS interactivity for Plotly restyle and table sorting
    assert "Plotly.restyle" in html_neon
    assert "sortTable" in html_neon or "addEventListener" in html_neon

    # 6. Verify legend font color adaptation for Light Mode (must not be white font on white background)
    import json
    assert ".legend text" in html_light or "g.legend text" in html_light
    
    # Check that themeLayouts in JS dynamically updates legend font color for Light Mode
    idx_layouts = html_light.find("const themeLayouts = ")
    assert idx_layouts != -1
    idx_layouts_end = html_light.find("};", idx_layouts)
    layouts_json_str = html_light[idx_layouts + len("const themeLayouts = "):idx_layouts_end + 1]
    layouts_obj = json.loads(layouts_json_str)
    
    assert "Light Mode" in layouts_obj
    light_layout = layouts_obj["Light Mode"]
    assert "legend" in light_layout
    assert light_layout["legend"]["font"]["color"] == "#0f172a"


def test_qt_legend_click_to_hide_plot():
    """Test clicking a legend item in Qt MplTelemetryCanvas toggles plot visibility."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from matplotlib.backend_bases import MouseEvent, PickEvent
    from top_plot_v2 import LogParserV2, MplTelemetryCanvas

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)

    canvas = MplTelemetryCanvas()
    canvas.plot_telemetry(parsed, selected_pids=[4146], plot_sys_cpu=True, plot_sys_mem=True)

    # Verify legend exists
    legend = canvas.ax_cpu.get_legend()
    assert legend is not None

    # Check legend lines and texts
    leg_lines = legend.get_lines()
    leg_texts = legend.get_texts()
    assert len(leg_lines) >= 3  # Sys CPU, Sys RAM, PID 4146 CPU, PID 4146 RES
    
    # Verify pickers are enabled
    for ll in leg_lines:
        assert ll.get_picker() is not None and ll.get_picker() is not False
    for lt in leg_texts:
        assert lt.get_picker() is not None and lt.get_picker() is not False

    # Simulate picking the first legend entry (Sys CPU Total%)
    first_text = leg_texts[0]
    entry = canvas._legend_map[first_text]
    orig_line = entry["line"]
    fill_coll = entry.get("fill")

    # Initial state: visible
    assert orig_line.get_visible() is True
    if fill_coll:
        assert fill_coll.get_visible() is True
    assert first_text.get_alpha() in (None, 1.0)

    # Simulate click pick event
    mouse_event = MouseEvent('button_press_event', canvas, 0, 0)
    pick_event = PickEvent('pick_event', canvas, mouse_event, first_text)
    canvas.callbacks.process('pick_event', pick_event)

    # After 1st click: should be hidden and legend dimmed
    assert orig_line.get_visible() is False
    if fill_coll:
        assert fill_coll.get_visible() is False
    assert first_text.get_alpha() == pytest.approx(0.25, abs=0.05)

    # Simulate 2nd click to unhide
    mouse_event2 = MouseEvent('button_press_event', canvas, 0, 0)
    pick_event2 = PickEvent('pick_event', canvas, mouse_event2, first_text)
    canvas.callbacks.process('pick_event', pick_event2)

    # After 2nd click: should be visible again and opacity restored
    assert orig_line.get_visible() is True
    if fill_coll:
        assert fill_coll.get_visible() is True
    assert first_text.get_alpha() == pytest.approx(1.0, abs=0.05)


def test_html_hover_namelength_untruncated():
    """Test that HTML export sets hoverlabel namelength=-1 so process names are not truncated."""
    from top_plot_v2 import LogParserV2, PlotlyHtmlGenerator

    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)
    gen = PlotlyHtmlGenerator(parsed)

    fig = gen.create_figure(selected_pids=[4146])
    assert hasattr(fig.layout, "hoverlabel")
    assert fig.layout.hoverlabel.namelength == -1

    html_content = gen.generate_html(selected_pids=[4146])
    assert '"namelength": -1' in html_content or '"namelength":-1' in html_content


def test_qt_canvas_hover_tooltip():
    """Test Qt MplTelemetryCanvas mouse hover crosshair and telemetry tooltip card."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from matplotlib.backend_bases import MouseEvent, LocationEvent
    from top_plot_v2 import LogParserV2, MplTelemetryCanvas

    app = QApplication.instance() or QApplication([])

    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)

    canvas = MplTelemetryCanvas()
    canvas.plot_telemetry(parsed, selected_pids=[4146], plot_sys_cpu=True, plot_sys_mem=True)

    # 1. Verify cursor line exists
    assert hasattr(canvas, "_cursor_line")
    assert canvas._cursor_line is not None

    # 2. Simulate mouse movement over the axes at sample index 0
    move_event = MouseEvent('motion_notify_event', canvas, x=100, y=100)
    move_event.inaxes = canvas.ax_cpu
    move_event.xdata = 0.0
    move_event.ydata = 50.0

    canvas.callbacks.process('motion_notify_event', move_event)

    # Cursor line should now be visible and positioned at x=0
    assert canvas._cursor_line.get_visible() is True
    assert canvas._cursor_line.get_xdata()[0] == 0

    # Hover tooltip content should contain timestamp and PID info
    tooltip_html = canvas.get_hover_tooltip_text(0)
    assert "20260917_17-33-01" in tooltip_html
    assert "4146" in tooltip_html
    assert "maps" in tooltip_html

    # 3. Simulate mouse leaving canvas
    leave_event = LocationEvent('figure_leave_event', canvas, x=0, y=0)
    canvas.callbacks.process('figure_leave_event', leave_event)

    # Cursor line should become hidden
    assert canvas._cursor_line.get_visible() is False


def test_qt_hover_tooltip_numbers_font_color():
    """Verify that Qt hover tooltip numbers have explicit theme font colors in Dark Fusion, Monokai, etc."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from top_plot_v2 import LogParserV2, MplTelemetryCanvas, THEMES, generate_qss

    app = QApplication.instance() or QApplication([])
    sample_snippet = """20260917_17-33-01
top_cpu:
  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers
800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps
"""
    parser = LogParserV2()
    parsed = parser.parse_string(sample_snippet)

    canvas = MplTelemetryCanvas()
    canvas.plot_telemetry(parsed, selected_pids=[4146], plot_sys_cpu=True, plot_sys_mem=True)

    for theme_name in ["Dark Fusion", "Monokai", "Light Mode", "Midnight Neon", "Solarized Dark"]:
        theme = THEMES[theme_name]
        canvas.set_theme(theme_name)
        tip_html = canvas.get_hover_tooltip_text(0)

        # 1. Check QToolTip QSS rule
        qss = generate_qss(theme)
        assert "QToolTip" in qss
        assert f"color: {theme['fg_text']}" in qss
        assert f"background-color: {theme['bg_card']}" in qss

        # 2. Check that numeric values in tooltip HTML have explicit font colors
        # Ensure numbers aren't inside naked unstyled <td> elements where Qt defaults to black
        assert "color:" in tip_html
        # System CPU% and Memory values must have explicit color matching theme accents
        assert f"color:{theme['accent_cpu']}" in tip_html
        assert f"color:{theme['accent_mem']}" in tip_html
        # Process numbers (CPU% and RES MB) must have explicit color styling
        assert f"93.1%" in tip_html
        assert f"569.0 MB" in tip_html
        # Verify color is explicitly applied to the numbers, e.g. via accent_cpu/accent_mem or fg_text
        assert f'<span style="color:{theme["accent_cpu"]}' in tip_html or f'<td style="color:{theme["fg_text"]}' in tip_html


def test_build_standalone_app():
    """Test building zero-dependency standalone web app HTML with in-browser log parsing."""
    import os
    import tempfile
    from top_plot_v2 import build_standalone_app

    with tempfile.TemporaryDirectory() as tmpdir:
        out_html = os.path.join(tmpdir, "standalone_app.html")
        res_path = build_standalone_app(out_html)

        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 100000  # Contains Plotly JS bundle

        with open(res_path, "r", encoding="utf-8") as f:
            html = f.read()

        # 1. Drag & drop file upload UI
        assert 'id="dropZone"' in html
        assert 'type="file"' in html

        # 2. In-browser client-side JS log parser
        assert "function parseMemoryMb" in html
        assert "function parseTopLog" in html

        # 3. Interactive components
        assert "Plotly.newPlot" in html
        assert 'id="processTable"' in html
        assert 'id="processSearch"' in html
        assert "Top 5 CPU" in html
        assert "Light Mode" in html
        assert "Midnight Neon" in html
        assert "namelength" in html
        # 4. Dynamic theme switching & trace recoloring
        assert "applyThemeToPlot" in html
        assert "Plotly.react" in html
        assert "hexToRgba" in html
        assert ".legend text" in html
        assert ".legend rect" in html


def test_standalone_html_themes_recolor_e2e():
    """Verify that standalone HTML dynamically recolors traces and maintains contrast across all 5 themes."""
    import os
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
    except ImportError:
        pytest.skip("Selenium not available for E2E browser test")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1000")

    html_path = os.path.abspath("top_log_analyzer_standalone.html")
    if not os.path.exists(html_path):
        from top_plot_v2 import build_standalone_app
        build_standalone_app(html_path)

    file_url = f"file:///{html_path.replace(os.sep, '/')}"

    try:
        driver = webdriver.Edge(options=options)
    except Exception:
        pytest.skip("Edge webdriver not available in headless environment")

    try:
        import time
        from top_plot_v2 import THEMES
        driver.get(file_url)
        time.sleep(1)

        # Click Load Demo Log
        driver.find_element(By.ID, "btnLoadDemo").click()
        time.sleep(0.8)

        for theme_name in ["Dark Fusion", "Light Mode", "Midnight Neon", "Solarized Dark", "Monokai"]:
            t = THEMES[theme_name]
            theme_select = Select(driver.find_element(By.ID, "htmlThemeSelect"))
            theme_select.select_by_value(theme_name)
            time.sleep(0.3)

            driver.execute_script("""
                const plotDiv = document.getElementById('telemetry_plot');
                Plotly.Fx.hover(plotDiv, [{ curveNumber: 0, pointNumber: 0 }]);
            """)
            time.sleep(0.2)

            info = driver.execute_script("""
                const plotDiv = document.getElementById('telemetry_plot');
                const hoverlayer = document.querySelector('#telemetry_plot .hoverlayer');
                const bgPath = hoverlayer ? hoverlayer.querySelector('path') : null;
                const legendTexts = Array.from(document.querySelectorAll('#telemetry_plot .infolayer .legend text'));
                return {
                    trace0_color: plotDiv.data[0].line.color,
                    trace1_color: plotDiv.data[1].line.color,
                    trace2_color: plotDiv.data[2].line.color,
                    hoverBg: bgPath ? window.getComputedStyle(bgPath).fill : null,
                    legendFill: legendTexts.length ? window.getComputedStyle(legendTexts[0]).fill : null
                };
            """)

            assert info['trace0_color'].lower() == t['accent_cpu'].lower()
            assert info['trace1_color'].lower() == t['accent_mem'].lower()
            assert info['trace2_color'].lower() == t['curve_colors'][0].lower()
            assert info['hoverBg'] is not None
            assert info['legendFill'] is not None
    finally:
        driver.quit()


def test_qt_theme_aware_widgets():
    """Verify that all Qt widgets use theme-derived colors, not hardcoded hex."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import top_plot_v2 as tp
    import pytest
    if not tp.GUI_AVAILABLE:
        pytest.skip("PySide6 not available")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = tp.TopPlotMainWindow()

    for theme_name in tp.THEMES:
        win.set_theme(theme_name)
        t = tp.THEMES[theme_name]

        # DropZoneLabel should contain theme border color
        drop_style = win.drop_label.styleSheet()
        assert t["border"] in drop_style or t["fg_muted"] in drop_style, \
            f"DropZone not themed for {theme_name}: {drop_style[:80]}"

        # Navigation toolbar should contain theme bg_card
        nav_style = win.nav_toolbar.styleSheet()
        assert t["bg_card"] in nav_style or t["bg_header"] in nav_style, \
            f"NavToolbar not themed for {theme_name}: {nav_style[:80]}"

        # Table title label (search for it via objectName or parent)
        # Verify search input doesn't have hardcoded colors
        search_style = win.search_input.styleSheet()
        if search_style:
            assert "#1f2937" not in search_style or theme_name == "Dark Fusion", \
                f"Search input has hardcoded dark fusion colors in {theme_name}"

    win.close()


def test_cpu_breakdown_traces_in_plotly():
    """Verify CPU breakdown traces (%user, %sys, etc.) appear in Plotly figure."""
    import top_plot_v2 as tp
    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", cpu_metrics={"%cpu_total": 600.0, "%user": 200.0, "%sys": 150.0, "%nice": 50.0, "%idle": 200.0, "%irq": 10.0, "%sirq": 5.0, "%iow": 15.0, "%cpu_capacity": 800.0}),
        tp.Snapshot(timestamp="T2", cpu_metrics={"%cpu_total": 500.0, "%user": 180.0, "%sys": 120.0, "%nice": 40.0, "%idle": 300.0, "%irq": 8.0, "%sirq": 4.0, "%iow": 10.0, "%cpu_capacity": 800.0}),
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    fig = gen.create_figure(plot_cpu_breakdown=True)
    trace_names = [t.name for t in fig.data]
    assert "CPU %user" in trace_names, f"Missing CPU %user trace. Found: {trace_names}"
    assert "CPU %sys" in trace_names, f"Missing CPU %sys trace. Found: {trace_names}"
    assert "CPU %iow" in trace_names, f"Missing CPU %iow trace. Found: {trace_names}"


def test_cpu_breakdown_in_html_and_standalone():
    """Verify CPU Breakdown controls and traces exist in generated HTML and standalone app."""
    import tempfile
    import os
    import top_plot_v2 as tp

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", cpu_metrics={"%cpu_total": 600.0, "%user": 200.0, "%sys": 150.0, "%nice": 50.0, "%idle": 200.0, "%irq": 10.0, "%sirq": 5.0, "%iow": 15.0, "%cpu_capacity": 800.0}),
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    html_content = gen.generate_html(plot_cpu_breakdown=True)
    assert "chkCpuBreakdown" in html_content
    assert "CPU Breakdown" in html_content

    with tempfile.TemporaryDirectory() as tmpdir:
        standalone_path = os.path.join(tmpdir, "app.html")
        tp.build_standalone_app(standalone_path)
        with open(standalone_path, "r", encoding="utf-8") as f:
            app_html = f.read()
        assert "chkCpuBreakdown" in app_html
        assert "CPU Breakdown" in app_html


def test_qt_cpu_breakdown():
    """Verify Qt canvas and main window support CPU breakdown toggle."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import top_plot_v2 as tp
    import pytest
    if not tp.GUI_AVAILABLE:
        pytest.skip("PySide6 not available")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", cpu_metrics={"%cpu_total": 600.0, "%user": 200.0, "%sys": 150.0, "%nice": 50.0, "%idle": 200.0, "%irq": 10.0, "%sirq": 5.0, "%iow": 15.0, "%cpu_capacity": 800.0}),
        tp.Snapshot(timestamp="T2", cpu_metrics={"%cpu_total": 500.0, "%user": 180.0, "%sys": 120.0, "%nice": 40.0, "%idle": 300.0, "%irq": 8.0, "%sirq": 4.0, "%iow": 10.0, "%cpu_capacity": 800.0}),
    ])
    canvas = tp.MplTelemetryCanvas()
    canvas.plot_telemetry(data, plot_cpu_breakdown=True)
    legend = canvas.ax_cpu.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert "CPU %user" in labels
    assert "CPU %sys" in labels
    assert "CPU %iow" in labels

    # Also test main window has chk_cpu_breakdown
    win = tp.TopPlotMainWindow()
    assert hasattr(win, "chk_cpu_breakdown")
    assert win.chk_cpu_breakdown.text() == "CPU Breakdown"
    assert not win.chk_cpu_breakdown.isChecked()
    win.close()


def test_swap_trace_in_plotly():
    """Verify swap usage trace appears when swap data is present."""
    import top_plot_v2 as tp
    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", mem_metrics={"swap_used_mb": 250.0, "swap_total_mb": 4096.0, "mem_used_mb": 5000.0}),
        tp.Snapshot(timestamp="T2", mem_metrics={"swap_used_mb": 300.0, "swap_total_mb": 4096.0, "mem_used_mb": 5100.0}),
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    fig = gen.create_figure(plot_sys_swap=True)
    trace_names = [t.name for t in fig.data]
    assert "System Swap Used (MB)" in trace_names, f"Missing swap trace. Found: {trace_names}"


def test_swap_in_html_and_standalone():
    """Verify Swap controls and traces exist in generated HTML and standalone app."""
    import tempfile
    import os
    import top_plot_v2 as tp

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", mem_metrics={"swap_used_mb": 250.0, "swap_total_mb": 4096.0, "mem_used_mb": 5000.0}),
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    html_content = gen.generate_html(plot_sys_swap=True)
    assert "chkSysSwap" in html_content
    assert "System Swap MB" in html_content

    with tempfile.TemporaryDirectory() as tmpdir:
        standalone_path = os.path.join(tmpdir, "app.html")
        tp.build_standalone_app(standalone_path)
        with open(standalone_path, "r", encoding="utf-8") as f:
            app_html = f.read()
        assert "chkSysSwap" in app_html
        assert "System Swap MB" in app_html


def test_qt_swap():
    """Verify Qt canvas and main window support Swap toggle."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import top_plot_v2 as tp
    import pytest
    if not tp.GUI_AVAILABLE:
        pytest.skip("PySide6 not available")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", mem_metrics={"swap_used_mb": 250.0, "swap_total_mb": 4096.0, "mem_used_mb": 5000.0}),
        tp.Snapshot(timestamp="T2", mem_metrics={"swap_used_mb": 300.0, "swap_total_mb": 4096.0, "mem_used_mb": 5100.0}),
    ])
    canvas = tp.MplTelemetryCanvas()
    canvas.plot_telemetry(data, plot_sys_swap=True)
    legend = canvas.ax_cpu.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert "Sys Swap Used" in labels

    # Also test main window has chk_sys_swap
    win = tp.TopPlotMainWindow()
    assert hasattr(win, "chk_sys_swap")
    assert win.chk_sys_swap.text() == "System Swap (MB)"
    assert not win.chk_sys_swap.isChecked()
    win.close()


def test_shr_column_in_table():
    """Verify SHR column exists in the Qt process table."""
    import top_plot_v2 as tp
    import pytest
    if not tp.GUI_AVAILABLE:
        pytest.skip("PySide6 not available")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = tp.TopPlotMainWindow()
    headers = [win.process_table.horizontalHeaderItem(i).text()
               for i in range(win.process_table.columnCount())]
    assert "Peak SHR (MB)" in headers, f"SHR column missing. Headers: {headers}"
    assert win.process_table.columnCount() == 9
    win.close()


def test_shr_data_in_qt_process_table():
    """Verify SHR data is correctly populated into column 7 of Qt process table."""
    import top_plot_v2 as tp
    import pytest
    if not tp.GUI_AVAILABLE:
        pytest.skip("PySide6 not available")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = tp.TopPlotMainWindow()

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(
            timestamp="T1",
            processes={
                100: tp.ProcessRecord(pid=100, user="u1", virt_mb=100.0, res_mb=50.0, shr_mb=32.5, state="S", cpu=10.0, mem_pct=2.5, time_plus="0:01", args="app1")
            }
        )
    ])
    win.populate_process_table(data)
    assert win.process_table.rowCount() == 1
    # Check column 6: Peak RES
    assert win.process_table.item(0, 6).text() == "50.0"
    # Check column 7: Peak SHR
    assert win.process_table.item(0, 7).text() == "32.5"
    assert win.process_table.item(0, 7).sort_value == 32.5
    # Check column 8: %MEM
    assert win.process_table.item(0, 8).text() == "2.5%"
    assert win.process_table.item(0, 8).sort_value == 2.5
    win.close()


def test_get_pid_metrics_max_shr():
    """Verify get_pid_metrics returns max_shr_mb."""
    import top_plot_v2 as tp
    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(
            timestamp="T1",
            processes={
                100: tp.ProcessRecord(pid=100, user="u1", virt_mb=100.0, res_mb=50.0, shr_mb=32.5, state="S", cpu=10.0, mem_pct=2.5, time_plus="0:01", args="app1")
            }
        ),
        tp.Snapshot(
            timestamp="T2",
            processes={
                100: tp.ProcessRecord(pid=100, user="u1", virt_mb=100.0, res_mb=50.0, shr_mb=45.0, state="S", cpu=10.0, mem_pct=2.5, time_plus="0:02", args="app1")
            }
        ),
    ])
    metrics = data.get_pid_metrics(100)
    assert metrics["max_shr_mb"] == 45.0
    assert metrics["shr_mb"] == [32.5, 45.0]


def test_shr_in_html_and_standalone():
    """Verify SHR column exists in generated HTML and standalone app."""
    import os
    import tempfile
    import top_plot_v2 as tp

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(
            timestamp="T1",
            processes={
                100: tp.ProcessRecord(pid=100, user="u1", virt_mb=100.0, res_mb=50.0, shr_mb=25.0, state="S", cpu=10.0, mem_pct=2.0, time_plus="0:01", args="app1")
            }
        )
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    html_content = gen.generate_html()
    assert "Peak SHR (MB)" in html_content
    assert "25.0 MB" in html_content

    with tempfile.TemporaryDirectory() as tmpdir:
        standalone_path = os.path.join(tmpdir, "app.html")
        tp.build_standalone_app(standalone_path)
        with open(standalone_path, "r", encoding="utf-8") as f:
            app_html = f.read()
        assert "Peak SHR (MB)" in app_html
        assert "max_shr_mb" in app_html or "shr_mb" in app_html


def test_csv_export():
    """Verify CSV export produces correct tabular output."""
    import top_plot_v2 as tp
    import tempfile, os, csv

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(
            timestamp="T1",
            cpu_metrics={"%cpu_total": 300.0},
            mem_metrics={"mem_used_mb": 5000.0},
            processes={100: tp.ProcessRecord(pid=100, user="root", virt_mb=1.0, res_mb=45.0, shr_mb=10.0, state="S", cpu=50.0, mem_pct=1.2, args="test_proc")}
        ),
        tp.Snapshot(
            timestamp="T2",
            cpu_metrics={"%cpu_total": 250.0},
            mem_metrics={"mem_used_mb": 5100.0},
            processes={100: tp.ProcessRecord(pid=100, user="root", virt_mb=1.0, res_mb=48.0, shr_mb=11.0, state="S", cpu=40.0, mem_pct=1.3, args="test_proc")}
        ),
    ])

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp_path = f.name
    try:
        result_path = data.to_csv(tmp_path)
        assert os.path.exists(result_path)
        with open(result_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert "Timestamp" in header
        assert "System_CPU%" in header
        assert any("100" in col for col in header)
    finally:
        os.unlink(tmp_path)


def test_json_export():
    """Verify JSON export produces structured telemetry output."""
    import top_plot_v2 as tp
    import tempfile, os, json

    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(
            timestamp="T1",
            cpu_metrics={"%cpu_total": 300.0},
            mem_metrics={"mem_used_mb": 5000.0},
            processes={100: tp.ProcessRecord(pid=100, user="root", virt_mb=1.0, res_mb=45.0, shr_mb=10.0, state="S", cpu=50.0, mem_pct=1.2, args="test_proc")}
        ),
    ])

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp_path = f.name
    try:
        result_path = data.to_json(tmp_path)
        assert os.path.exists(result_path)
        with open(result_path, "r", encoding="utf-8") as f:
            out_data = json.load(f)
        assert "timestamps" in out_data
        assert "system_metrics" in out_data
        assert "processes" in out_data
        assert "100" in out_data["processes"]
        assert out_data["processes"]["100"]["args"] == "test_proc"
        assert out_data["processes"]["100"]["max_cpu"] == 50.0
    finally:
        os.unlink(tmp_path)


def test_export_controls_in_standalone_and_qt():
    """Verify CSV and JSON export buttons in standalone app and Qt window."""
    import os
    import tempfile
    import top_plot_v2 as tp

    with tempfile.TemporaryDirectory() as tmpdir:
        standalone_path = os.path.join(tmpdir, "app.html")
        tp.build_standalone_app(standalone_path)
        with open(standalone_path, "r", encoding="utf-8") as f:
            app_html = f.read()
        assert "btnDownloadCsv" in app_html
        assert "btnDownloadJson" in app_html
        assert "downloadCSV" in app_html
        assert "downloadJSON" in app_html

    if tp.GUI_AVAILABLE:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        win = tp.TopPlotMainWindow()
        assert hasattr(win, "btn_export_csv")
        assert hasattr(win, "export_csv")
        data = tp.ParsedLogV2(snapshots=[
            tp.Snapshot(
                timestamp="T1",
                cpu_metrics={"%cpu_total": 100.0},
                mem_metrics={"mem_used_mb": 2000.0},
                processes={10: tp.ProcessRecord(pid=10, user="system", virt_mb=10.0, res_mb=5.0, shr_mb=2.0, state="S", cpu=12.0, mem_pct=0.5, args="proc_a")}
            )
        ])
        win.current_parsed = data
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            q_csv_path = f.name
        try:
            win.export_csv(file_path=q_csv_path)
            assert os.path.exists(q_csv_path)
            with open(q_csv_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "proc_a" in content
        finally:
            if os.path.exists(q_csv_path):
                os.unlink(q_csv_path)


def test_standalone_html_has_spinner_and_toast():
    """Verify standalone HTML contains loading spinner and toast notification elements."""
    import top_plot_v2 as tp
    import tempfile, os
    out = os.path.join(tempfile.gettempdir(), "test_spinner.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "loading-spinner" in content, "Missing loading spinner CSS/HTML"
    assert "loadingOverlay" in content, "Missing loadingOverlay element"
    assert "showSpinner" in content, "Missing showSpinner function"
    assert "hideSpinner" in content, "Missing hideSpinner function"
    assert "showToast" in content, "Missing showToast function"
    assert "toastContainer" in content or "toast-container" in content, "Missing toast container"
    assert "toast-error" in content, "Missing toast-error class"
    assert "toast-success" in content, "Missing toast-success class"
    assert "Failed to parse:" in content, "Missing parse error feedback handling"
    os.unlink(out)


def test_standalone_html_has_png_export_button():
    """Verify standalone HTML contains PNG export button."""
    import top_plot_v2 as tp
    import tempfile, os
    out = os.path.join(tempfile.gettempdir(), "test_png.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "btnExportPng" in content or "downloadPNG" in content, "Missing PNG export button/function"
    assert "Plotly.downloadImage" in content, "Missing Plotly.downloadImage invocation"
    os.unlink(out)


def test_standalone_html_has_meminfo_panel():
    """Verify standalone HTML contains /proc/meminfo panel."""
    import top_plot_v2 as tp
    import tempfile, os
    out = os.path.join(tempfile.gettempdir(), "test_meminfo.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "meminfoPanel" in content or "meminfo-panel" in content, "Missing meminfo panel"
    assert "buildMeminfoPanel" in content, "Missing buildMeminfoPanel function"
    os.unlink(out)


def test_generate_html_has_meminfo_panel():
    """Verify generate_html contains /proc/meminfo panel when meminfo exists."""
    import top_plot_v2 as tp
    import os
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    sample_topmen_1 = os.path.join(samples_dir, "log_topmen@20260917_17-33-01-008-Batch_3.log")
    parser = tp.LogParserV2()
    parsed = parser.parse_file(sample_topmen_1, encoding="utf-8")
    assert parsed is not None
    generator = tp.PlotlyHtmlGenerator(parsed)
    html_content = generator.generate_html()
    assert "meminfoPanel" in html_content or "meminfo-panel" in html_content, "Missing meminfo panel in generate_html"
    assert "MemAvailable" in html_content, "Missing MemAvailable metric in meminfo panel"


def test_standalone_js_meminfo_parsing_and_merging():
    """Verify that standalone JS correctly parses /proc/meminfo and merges it."""
    import top_plot_v2 as tp
    import pytest
    import tempfile, os, subprocess, json, shutil

    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("Node.js not available for JS parser test")

    out = os.path.join(tempfile.gettempdir(), "test_js_meminfo.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        html = f.read()
    os.unlink(out)

    mock_prefix = """
global.document = {
    getElementById: () => ({ style: {}, querySelector: () => null, querySelectorAll: () => [], appendChild: () => {}, addEventListener: () => {} }),
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: { getAttribute: () => 'Dark Fusion' }
};
global.window = {
    addEventListener: () => {}
};
global.FileReader = class {};
"""

    script_start = html.rfind("<script>")
    script_end = html.rfind("</script>")
    js_code = html[script_start + len("<script>"):script_end]

    test_harness = """
const testLines = [
  "20260917_17-33-01",
  "MemTotal:        7594756 kB",
  "MemFree:         1367888 kB",
  "MemAvailable:    3766552 kB",
  "Buffers:           15396 kB",
  "Cached:          2436920 kB",
  "  Mem:  7594756K total,  6227624K used,  1367132K free,    15396K buffers",
  "800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 maps",
  "",
  "20260917_17-33-11",
  "MemTotal:        7594756 kB",
  "MemFree:         1200000 kB",
  "MemAvailable:    3500000 kB",
  "Buffers:           16000 kB",
  "Cached:          2500000 kB",
  "  Mem:  7594756K total,  6340152K used,  1254604K free,    15396K buffers",
  "800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 maps"
].join("\\n");

const parsed = parseTopLog(testLines, "test_session");
const merged = mergeTopAndTopmen(parsed, parsed, "merged_session");
console.log(JSON.stringify({
    hasMeminfo: !!parsed.meminfo,
    memKeys: Object.keys(parsed.meminfo),
    memAvailable: parsed.meminfo["MemAvailable"],
    mergedMemAvailable: merged.meminfo["MemAvailable"],
    snapshotsCount: parsed.snapshots ? parsed.snapshots.length : 0
}));
"""

    temp_js = os.path.join(tempfile.gettempdir(), "test_runner_meminfo.js")
    with open(temp_js, "w", encoding="utf-8") as f:
        f.write(mock_prefix + "\n" + js_code + "\n" + test_harness)

    try:
        proc = subprocess.run([node_path, temp_js], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip().split("\n")[-1])
        assert res["hasMeminfo"]
        assert "MemAvailable" in res["memKeys"]
        assert len(res["memAvailable"]) == 2
        assert abs(res["memAvailable"][0] - (3766552 / 1024.0)) < 0.01
        assert abs(res["mergedMemAvailable"][0] - (3766552 / 1024.0)) < 0.01
        assert res["snapshotsCount"] == 2
    finally:
        if os.path.exists(temp_js):
            os.unlink(temp_js)


def test_standalone_html_has_drilldown():
    """Verify standalone HTML contains process drill-down modal."""
    import top_plot_v2 as tp
    import tempfile, os
    out = os.path.join(tempfile.gettempdir(), "test_drilldown.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "drillDownModal" in content, "Missing drill-down modal"
    assert "showDrillDown" in content, "Missing showDrillDown function"
    assert "drillPlot" in content, "Missing drillPlot element"
    assert "cursor: pointer" in content or "cursor:pointer" in content, "Missing clickable cursor for PID badge"
    os.unlink(out)


def test_generate_html_has_drilldown():
    """Verify generate_html contains process drill-down modal."""
    import top_plot_v2 as tp
    import os
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    sample_topmen_1 = os.path.join(samples_dir, "log_topmen@20260917_17-33-01-008-Batch_3.log")
    parser = tp.LogParserV2()
    parsed = parser.parse_file(sample_topmen_1, encoding="utf-8")
    assert parsed is not None
    generator = tp.PlotlyHtmlGenerator(parsed)
    html_content = generator.generate_html()
    assert "drillDownModal" in html_content, "Missing drillDownModal in generate_html"
    assert "showDrillDown" in html_content, "Missing showDrillDown function in generate_html"
    assert "drillPlot" in html_content, "Missing drillPlot element in generate_html"
    assert "cursor: pointer" in html_content or "cursor:pointer" in html_content, "Missing clickable cursor in generate_html"


def test_standalone_js_drilldown_modal_execution():
    """Verify that standalone JS showDrillDown correctly generates 4 traces and handles close."""
    import top_plot_v2 as tp
    import pytest
    import tempfile, os, subprocess, json, shutil

    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("Node.js not available for JS drilldown test")

    out = os.path.join(tempfile.gettempdir(), "test_js_drilldown.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        html = f.read()
    os.unlink(out)

    mock_prefix = """
global.lastPlotCall = null;
global.Plotly = {
    newPlot: (divId, traces, layout, opts) => {
        global.lastPlotCall = { divId, traces, layout };
    }
};
const elements = {
    drillDownModal: { style: { display: 'none' }, addEventListener: () => {} },
    drillDownTitle: { textContent: '' },
    drillDownBadge: { textContent: '' },
    drillPlot: {},
    btnDrillClose: { addEventListener: (ev, fn) => { elements.btnDrillClose._cb = fn; } }
};
global.document = {
    getElementById: (id) => elements[id] || { style: {}, querySelector: () => null, querySelectorAll: () => [], appendChild: () => {}, addEventListener: () => {} },
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: { getAttribute: () => 'Dark Fusion' }
};
global.window = {
    addEventListener: (ev, fn) => {
        if (!global.window._listeners) global.window._listeners = {};
        global.window._listeners[ev] = fn;
    }
};
global.FileReader = class {};
"""

    script_start = html.rfind("<script>")
    script_end = html.rfind("</script>")
    js_code = html[script_start + len("<script>"):script_end]

    test_harness = """
const testLog = [
  "20260917_17-33-01",
  "800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps",
  "",
  "20260917_17-33-11",
  "800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 com.google.android.apps.maps"
].join("\\n");

const parsed = parseTopLog(testLog, "demo_session");
loadedSessions["demo_session"] = parsed;
activeSessionKey = "demo_session";

showDrillDown(4146);

const titleText = elements.drillDownTitle.textContent;
const modalDisplayAfterShow = elements.drillDownModal.style.display;
const tracesCount = global.lastPlotCall ? global.lastPlotCall.traces.length : 0;
const traceNames = global.lastPlotCall ? global.lastPlotCall.traces.map(t => t.name) : [];
const hasDualAxes = global.lastPlotCall ? (!!global.lastPlotCall.layout.yaxis && !!global.lastPlotCall.layout.yaxis2) : false;

closeDrillDown();
const modalDisplayAfterClose = elements.drillDownModal.style.display;

console.log(JSON.stringify({
    titleText,
    modalDisplayAfterShow,
    tracesCount,
    traceNames,
    hasDualAxes,
    modalDisplayAfterClose
}));
"""

    temp_js = os.path.join(tempfile.gettempdir(), "test_runner_drilldown.js")
    with open(temp_js, "w", encoding="utf-8") as f:
        f.write(mock_prefix + "\n" + js_code + "\n" + test_harness)

    try:
        proc = subprocess.run([node_path, temp_js], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip().split("\n")[-1])
        assert "4146" in res["titleText"]
        assert "maps" in res["titleText"]
        assert res["modalDisplayAfterShow"] == "flex"
        assert res["tracesCount"] == 4
        assert "CPU%" in res["traceNames"]
        assert "MEM%" in res["traceNames"]
        assert "RES (MB)" in res["traceNames"]
        assert "SHR (MB)" in res["traceNames"]
        assert res["hasDualAxes"] is True
        assert res["modalDisplayAfterClose"] == "none"
    finally:
        if os.path.exists(temp_js):
            os.unlink(temp_js)


def test_plotly_rangeslider():
    """Verify Plotly figure has range slider enabled."""
    import top_plot_v2 as tp
    data = tp.ParsedLogV2(snapshots=[
        tp.Snapshot(timestamp="T1", cpu_metrics={"%cpu_total": 300.0}),
        tp.Snapshot(timestamp="T2", cpu_metrics={"%cpu_total": 250.0}),
    ])
    gen = tp.PlotlyHtmlGenerator(data)
    fig = gen.create_figure()
    xaxis = fig.layout.xaxis
    assert xaxis.rangeslider is not None, "Missing rangeslider"
    assert xaxis.rangeslider.visible is True, "Rangeslider not visible"
    assert xaxis.rangeslider.thickness == 0.08, "Rangeslider thickness mismatch"


def test_standalone_and_html_theme_rangeslider():
    """Verify standalone app and generated HTML have rangeslider and theme update preserves it."""
    import top_plot_v2 as tp
    import tempfile, os

    # Test standalone HTML content
    out = os.path.join(tempfile.gettempdir(), "test_standalone_rangeslider.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    os.unlink(out)

    assert "rangeslider:" in content, "Missing rangeslider in standalone app"
    assert "visible: true" in content or "visible:true" in content

    # Test generate_html
    samples_dir = os.path.join(os.path.dirname(__file__), "log_samples")
    sample_topmen_1 = os.path.join(samples_dir, "log_topmen@20260917_17-33-01-008-Batch_3.log")
    parser = tp.LogParserV2()
    parsed = parser.parse_file(sample_topmen_1, encoding="utf-8")
    assert parsed is not None
    generator = tp.PlotlyHtmlGenerator(parsed)
    html_content = generator.generate_html()

    assert "rangeslider" in html_content, "Missing rangeslider in generate_html"


def test_standalone_js_rangeslider_execution():
    """Verify that standalone JS renderSession creates rangeslider and applyThemeToPlot preserves it."""
    import top_plot_v2 as tp
    import pytest
    import tempfile, os, subprocess, json, shutil

    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("Node.js not available for JS rangeslider test")

    out = os.path.join(tempfile.gettempdir(), "test_js_rangeslider.html")
    tp.build_standalone_app(out)
    with open(out, "r", encoding="utf-8") as f:
        html = f.read()
    os.unlink(out)

    mock_prefix = """
global.lastPlotCall = null;
global.lastReactCall = null;
const defaultElem = () => ({
    style: {},
    checked: true,
    textContent: '',
    innerHTML: '',
    classList: { toggle: () => {}, add: () => {}, remove: () => {} },
    getAttribute: () => '',
    setAttribute: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    appendChild: () => {},
    addEventListener: () => {}
});

const elements = {
    currentSessionTitle: defaultElem(),
    snapshotBadge: defaultElem(),
    processBadge: defaultElem(),
    telemetryView: defaultElem(),
    telemetry_plot: { data: [], layout: {} },
    chkSysMem: defaultElem(),
    chkSysCpu: defaultElem(),
    chkSysSwap: defaultElem(),
    chkCpuBreakdown: defaultElem(),
    processTableBody: defaultElem(),
    tableRowCount: defaultElem(),
    thMasterCheck: defaultElem()
};
global.Plotly = {
    newPlot: (divId, traces, layout, opts) => {
        const div = elements[divId] || elements.telemetry_plot;
        div.data = traces;
        div.layout = layout;
        global.lastPlotCall = { divId, traces, layout };
    },
    react: (div, traces, layout) => {
        div.data = traces;
        div.layout = layout;
        global.lastReactCall = { div, traces, layout };
    }
};
global.document = {
    createElement: () => defaultElem(),
    getElementById: (id) => elements[id] || defaultElem(),
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: {
        getAttribute: () => global._currTheme || 'Dark Fusion',
        setAttribute: (k, v) => { global._currTheme = v; }
    }
};
global.window = {
    addEventListener: () => {}
};
global.FileReader = class {};
"""

    script_start = html.rfind("<script>")
    script_end = html.rfind("</script>")
    js_code = html[script_start + len("<script>"):script_end]

    test_harness = """
const testLog = [
  "20260917_17-33-01",
  "800%cpu  59%user  79%nice  62%sys 528%idle   0%iow  14%irq   3%sirq  55%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 569M 328M S 93.1   7.6  11:05.20 com.google.android.apps.maps",
  "",
  "20260917_17-33-11",
  "800%cpu  97%user 144%nice 103%sys 322%idle  25%iow  16%irq   3%sirq  91%host",
  "  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS",
  " 4146 u10_a157     20   0  19G 566M 328M S 62.5   7.6  11:12.68 com.google.android.apps.maps"
].join("\\n");

const parsed = parseTopLog(testLog, "demo_session");
loadedSessions["demo_session"] = parsed;
renderSession("demo_session");

const initialSlider = global.lastPlotCall ? global.lastPlotCall.layout.xaxis.rangeslider : null;

applyThemeToPlot("Light Mode");

const lightSlider = global.lastReactCall ? global.lastReactCall.layout.xaxis.rangeslider : null;

console.log(JSON.stringify({
    initialSlider,
    lightSlider
}));
"""

    temp_js = os.path.join(tempfile.gettempdir(), "test_runner_rangeslider.js")
    with open(temp_js, "w", encoding="utf-8") as f:
        f.write(mock_prefix + "\n" + js_code + "\n" + test_harness)

    try:
        proc = subprocess.run([node_path, temp_js], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip().split("\n")[-1])
        assert res["initialSlider"] is not None
        assert res["initialSlider"]["visible"] is True
        assert res["initialSlider"]["thickness"] == 0.08
        assert res["initialSlider"]["bgcolor"] == "#1f2937"
        assert res["initialSlider"]["bordercolor"] == "#374151"

        assert res["lightSlider"] is not None
        assert res["lightSlider"]["visible"] is True
        assert res["lightSlider"]["thickness"] == 0.08
        assert res["lightSlider"]["bgcolor"] == "#ffffff"
        assert res["lightSlider"]["bordercolor"] == "#cbd5e1"
    finally:
        if os.path.exists(temp_js):
            os.unlink(temp_js)




