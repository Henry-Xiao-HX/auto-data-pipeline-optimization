"""
Commit Performance Benchmark Dashboard Server
==============================================
Loads benchmark data from TSV and serves an interactive HTML dashboard.

Usage:
    python dashboard.py                                 # serve from infra_results.tsv on port 8000
    python dashboard.py --input results.csv             # load from CSV
    python dashboard.py --input results.json            # load from JSON
    python dashboard.py --port 8080                     # custom port
    python dashboard.py --output my_dash.html           # save to file instead of serving

TSV format expected:
    commit\tefficiency_score\tlatency_sec\tcost_usd\tmemory_gb\tstatus\tdescription

CSV format expected:
    commit,efficiency_score,latency_sec,cost_usd,memory_gb,status,description

JSON format expected:
    [{"commit": "abc1234", "efficiency_score": 4489642.83, ...}, ...]
"""

import argparse
import json
import csv
import sys
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse



# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_tsv(path: str) -> list[dict]:
    """Load benchmark data from TSV file."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append({
                "commit":           row["commit"].strip(),
                "efficiency_score": float(row["efficiency_score"]),
                "latency_sec":      float(row["latency_sec"]),
                "cost_usd":         float(row["cost_usd"]),
                "memory_gb":        float(row["memory_gb"]),
                "status":           row["status"].strip().strip("*"),
                "description":      row["description"].strip(),
            })
    return rows


def load_csv(path: str) -> list[dict]:
    """Load benchmark data from CSV file."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "commit":           row["commit"].strip(),
                "efficiency_score": float(row["efficiency_score"]),
                "latency_sec":      float(row["latency_sec"]),
                "cost_usd":         float(row["cost_usd"]),
                "memory_gb":        float(row["memory_gb"]),
                "status":           row["status"].strip().strip("*"),
                "description":      row["description"].strip(),
            })
    return rows


def load_json(path: str) -> list[dict]:
    """Load benchmark data from JSON file."""
    with open(path) as f:
        raw = json.load(f)
    return [{
        "commit":           r["commit"],
        "efficiency_score": float(r["efficiency_score"]),
        "latency_sec":      float(r["latency_sec"]),
        "cost_usd":         float(r["cost_usd"]),
        "memory_gb":        float(r["memory_gb"]),
        "status":           str(r["status"]).strip("*"),
        "description":      r["description"],
    } for r in raw]


# ---------------------------------------------------------------------------
# Derived stats
# ---------------------------------------------------------------------------

def compute_stats(data: list[dict]) -> dict:
    best    = max(data, key=lambda d: d["efficiency_score"])
    worst   = min(data, key=lambda d: d["efficiency_score"])
    avg_lat = sum(d["latency_sec"] for d in data) / len(data)
    kept    = sum(1 for d in data if d["status"] == "keep")
    scores  = [d["efficiency_score"] for d in data]
    y_min   = max(0, min(scores) * 0.93)
    y_max   = max(scores) * 1.01
    return dict(best=best, worst=worst, avg_lat=avg_lat, kept=kept,
                y_min=y_min, y_max=y_max)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def score_color(score: float, best_score: float) -> str:
    if score == best_score:
        return "#38bdf8"
    if score > 4_480_000:
        return "#4ade80"
    if score > 4_400_000:
        return "#a78bfa"
    return "#f87171"


def lat_color(lat: float) -> str:
    if lat >= 0.9:
        return "#f87171"
    if lat >= 0.3:
        return "#fbbf24"
    return "#94a3b8"


def bar_color(score: float, best_score: float) -> str:
    return score_color(score, best_score)


def build_table_rows(data: list[dict], best_score: float) -> str:
    rows = []
    for d in data:
        is_best = d["efficiency_score"] == best_score
        row_cls = ' class="best"' if is_best else ""
        badge   = '<span class="best-badge">★ best</span>' if is_best else ""
        sc      = score_color(d["efficiency_score"], best_score)
        lc      = lat_color(d["latency_sec"])
        score_m = f"{d['efficiency_score']/1e6:.3f}M"
        status_html = (
            '<span class="status-keep"><span class="dot-keep"></span>keep</span>'
            if d["status"] == "keep"
            else '<span class="status-discard"><span class="dot-discard"></span>discard</span>'
        )
        desc = d["description"].replace("<", "&lt;").replace(">", "&gt;")
        rows.append(f"""
        <tr{row_cls}>
          <td><span class="commit-hash">{d['commit']}</span>{badge}</td>
          <td style="color:{sc};font-weight:500">{score_m}</td>
          <td style="color:{lc}">{d['latency_sec']:.1f}</td>
          <td>${d['cost_usd']:.4f}</td>
          <td>{d['memory_gb']:.1f}</td>
          <td>{status_html}</td>
          <td class="desc">{desc}</td>
        </tr>""")
    return "\n".join(rows)


def generate_html(data: list[dict], title: str = "Commit Performance Benchmarks") -> str:
    stats      = compute_stats(data)
    best_score = stats["best"]["efficiency_score"]
    n          = len(data)
    kept       = stats["kept"]

    # JS arrays
    js_labels  = json.dumps([d["commit"] for d in data])
    js_scores  = json.dumps([d["efficiency_score"] for d in data])
    js_lats    = json.dumps([d["latency_sec"] for d in data])
    js_bar_clr = json.dumps([bar_color(d["efficiency_score"], best_score) for d in data])
    js_pt_clr  = json.dumps([
        "#38bdf8" if d["efficiency_score"] == best_score
        else ("#f87171" if d["latency_sec"] >= 0.9 else "#fbbf24" if d["latency_sec"] >= 0.3 else "#a78bfa")
        for d in data
    ])
    js_pt_r    = json.dumps([6 if d["efficiency_score"] == best_score else 4 for d in data])

    table_rows = build_table_rows(data, best_score)
    y_min      = stats["y_min"]
    y_max      = stats["y_max"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d0f14; font-family: 'Courier New', monospace; color: #c9d1e0; padding: 24px; min-height: 100vh; }}
  h1.page-title {{ font-size: 14px; font-weight: 500; color: #e2e8f0; letter-spacing: .08em; text-transform: uppercase; }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; border-bottom: 1px solid #1e2535; padding-bottom: 16px; }}
  .badge {{ font-size: 11px; background: #0f2a3f; color: #38bdf8; padding: 4px 10px; border-radius: 4px; border: 1px solid #1a4a6b; }}
  .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .metric {{ background: #111520; border: 1px solid #1e2535; border-radius: 8px; padding: 14px 16px; }}
  .metric .label {{ font-size: 10px; color: #64748b; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 6px; }}
  .metric .value {{ font-size: 20px; font-weight: 500; }}
  .blue {{ color: #38bdf8; }} .green {{ color: #4ade80; }} .purple {{ color: #a78bfa; }} .amber {{ color: #fbbf24; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-card, .table-card {{ background: #111520; border: 1px solid #1e2535; border-radius: 8px; padding: 16px; }}
  .chart-card h3, .table-card h3 {{ font-size: 10px; color: #64748b; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 14px; }}
  .table-card {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  th {{ font-size: 10px; color: #475569; letter-spacing: .07em; text-transform: uppercase; font-weight: 500; padding: 6px 10px; text-align: left; border-bottom: 1px solid #1e2535; white-space: nowrap; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #141928; color: #94a3b8; vertical-align: middle; white-space: nowrap; }}
  tr.best td {{ color: #e2e8f0; background: #0a1e30; }}
  tr.best td:first-child {{ border-left: 2px solid #38bdf8; }}
  tr:not(.best):hover td {{ background: #12192a; }}
  .commit-hash {{ color: #38bdf8; font-family: monospace; }}
  .best-badge {{ display: inline-block; font-size: 9px; background: #0a2040; color: #38bdf8; border: 1px solid #1a4a6b; border-radius: 3px; padding: 1px 5px; margin-left: 6px; }}
  .status-keep {{ display: inline-flex; align-items: center; gap: 5px; color: #4ade80; font-size: 11px; }}
  .status-discard {{ display: inline-flex; align-items: center; gap: 5px; color: #f87171; font-size: 11px; }}
  .dot-keep {{ width: 7px; height: 7px; border-radius: 50%; background: #4ade80; flex-shrink: 0; }}
  .dot-discard {{ width: 7px; height: 7px; border-radius: 50%; background: #f87171; flex-shrink: 0; }}
  .desc {{ color: #64748b; font-size: 11px; }}
  tr.best .desc {{ color: #94a3b8; }}
  @media (max-width: 700px) {{
    .metrics {{ grid-template-columns: repeat(2, 1fr); }}
    .charts {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1 class="page-title">▸ commit performance benchmarks</h1>
  <span class="badge">{n} commits &middot; {kept} kept</span>
</div>

<div class="metrics">
  <div class="metric">
    <div class="label">Best efficiency</div>
    <div class="value blue">{best_score/1e6:.3f}M</div>
  </div>
  <div class="metric">
    <div class="label">Avg latency</div>
    <div class="value purple">{stats['avg_lat']:.2f}s</div>
  </div>
  <div class="metric">
    <div class="label">Worst commit</div>
    <div class="value amber">{stats['worst']['commit']}</div>
  </div>
  <div class="metric">
    <div class="label">Commits kept</div>
    <div class="value green">{kept} / {n}</div>
  </div>
</div>

<div class="charts">
  <div class="chart-card">
    <h3>Efficiency score by commit</h3>
    <div style="position:relative;width:100%;height:240px;">
      <canvas id="barChart"></canvas>
    </div>
  </div>
  <div class="chart-card">
    <h3>Latency trend (sec)</h3>
    <div style="position:relative;width:100%;height:240px;">
      <canvas id="lineChart"></canvas>
    </div>
  </div>
</div>

<div class="table-card">
  <h3>Commit breakdown</h3>
  <table>
    <thead>
      <tr>
        <th>Commit</th><th>Efficiency</th><th>Latency (s)</th>
        <th>Cost (USD)</th><th>Memory (GB)</th><th>Status</th><th>Description</th>
      </tr>
    </thead>
    <tbody>
{table_rows}
    </tbody>
  </table>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels   = {js_labels};
const scores   = {js_scores};
const lats     = {js_lats};
const barClr   = {js_bar_clr};
const ptClr    = {js_pt_clr};
const ptR      = {js_pt_r};

const GRID = '#1a2030';
const TICK = {{ color: '#475569', font: {{ size: 9 }} }};
const TIP  = {{ backgroundColor:'#111520', borderColor:'#1e2535', borderWidth:1,
               titleColor:'#94a3b8', bodyColor:'#e2e8f0', padding:8 }};

new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label:'Efficiency', data:scores,
           backgroundColor:barClr, borderRadius:2, borderWidth:0 }}] }},
  options: {{
    responsive:true, maintainAspectRatio:false,
    plugins: {{ legend:{{display:false}}, tooltip:{{ ...TIP,
      callbacks:{{ label: ctx => ' ' + (ctx.parsed.y/1e6).toFixed(3)+'M' }} }} }},
    scales: {{
      x: {{ ticks:{{ ...TICK, maxRotation:45, autoSkip:false }},
            grid:{{ color:GRID, lineWidth:.5 }}, border:{{ color:'#1e2535' }} }},
      y: {{ min:{y_min:.0f}, max:{y_max:.0f},
            ticks:{{ ...TICK, callback: v => (v/1e6).toFixed(1)+'M' }},
            grid:{{ color:GRID, lineWidth:.5 }}, border:{{ color:'#1e2535' }} }}
    }}
  }}
}});

new Chart(document.getElementById('lineChart'), {{
  type: 'line',
  data: {{ labels, datasets: [{{
    label:'Latency (s)', data:lats,
    borderColor:'#a78bfa', backgroundColor:'rgba(167,139,250,0.07)',
    borderWidth:2, fill:true, tension:0.3,
    pointBackgroundColor:ptClr, pointRadius:ptR, pointBorderWidth:0,
  }}] }},
  options: {{
    responsive:true, maintainAspectRatio:false,
    plugins: {{ legend:{{display:false}}, tooltip:{{ ...TIP,
      callbacks:{{ label: ctx => ' ' + ctx.parsed.y.toFixed(1)+'s' }} }} }},
    scales: {{
      x: {{ ticks:{{ ...TICK, maxRotation:45, autoSkip:false }},
            grid:{{ color:GRID, lineWidth:.5 }}, border:{{ color:'#1e2535' }} }},
      y: {{ min:0, max:1.1,
            ticks:{{ ...TICK, callback: v => v.toFixed(1)+'s' }},
            grid:{{ color:GRID, lineWidth:.5 }}, border:{{ color:'#1e2535' }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves the dashboard HTML."""
    
    html_content = ""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == "/" or parsed_path.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.html_content.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def serve_dashboard(html: str, port: int = 8000):
    """Start HTTP server to serve the dashboard."""
    DashboardHandler.html_content = html
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    
    url = f"http://localhost:{port}"
    print(f"Dashboard server running at {url}")
    print("Press Ctrl+C to stop the server")
    
    # Open browser automatically
    webbrowser.open(url)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Serve or generate commit benchmark dashboard.")
    parser.add_argument("--input",  "-i", help="Path to input TSV/CSV/JSON file (default: infra_results.tsv)")
    parser.add_argument("--output", "-o", help="Output HTML file path (if specified, saves to file instead of serving)")
    parser.add_argument("--port",   "-p", type=int, default=8000, help="Port for HTTP server (default: 8000)")
    parser.add_argument("--title",  "-t", default="Commit Performance Benchmarks", help="Dashboard page title")
    args = parser.parse_args()

    # Determine input file
    input_file = args.input if args.input else "infra_results.tsv"
    p = Path(input_file)
    
    if not p.exists():
        print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    
    # Load data based on file extension
    suffix = p.suffix.lower()
    if suffix == ".json":
        data = load_json(str(p))
    elif suffix == ".csv":
        data = load_csv(str(p))
    elif suffix == ".tsv":
        data = load_tsv(str(p))
    else:
        print("Error: input must be a .tsv, .csv, or .json file.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loaded {len(data)} commits from {input_file}")

    # Generate HTML
    html = generate_html(data, title=args.title)

    # Either save to file or serve via HTTP
    if args.output:
        out = Path(args.output)
        out.write_text(html, encoding="utf-8")
        print(f"Dashboard written to: {out.resolve()}")
    else:
        serve_dashboard(html, port=args.port)


if __name__ == "__main__":
    main()