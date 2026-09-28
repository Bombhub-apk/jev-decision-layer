import os
import sys
import json
import time
import webbrowser
from pathlib import Path
from datetime import datetime
from jev_ledger_store import LedgerError, append_record, load_ledger

LEDGER_PATH = Path(os.path.expanduser("~/.gemini/antigravity/jev_usage_ledger.json"))
RATE_PER_MILLION_INPUT = 0.042  # TypeSafe Jev pricing: $0.042 per 1M input tokens, output is free ($0.00)
STANDARD_LLM_INPUT_RATE = 3.00   # Comparison: Average frontier LLM input rate ($3.00 / 1M)
STANDARD_LLM_OUTPUT_RATE = 15.00 # Comparison: Average frontier LLM output rate ($15.00 / 1M)

# Benchmark Baseline Constants for Architectural Decision Tasks:
# Standard Frontier LLM Prompt-and-Parse baseline per decision:
# 1. Full context + system instructions + code state: ~6,500 input tokens
# 2. Reasoning scratchpad + Chain-of-Thought + JSON schema response: ~550 output tokens
# 3. Autoregressive round-trip latency: ~4,200 ms
# Jev System One:
# 1. Isolated state + discrete criteria: ~350-450 input tokens
# 2. Direct categorical probabilities (output tokens are 100% free!): ~40 output tokens
# 3. Non-autoregressive classification latency: ~210 ms
BASELINE_LLM_INPUT_TOKENS_PER_CALL = 6500
BASELINE_LLM_OUTPUT_TOKENS_PER_CALL = 550
BASELINE_LLM_LATENCY_MS = 4200.0  # 4.2 seconds
JEV_AVERAGE_LATENCY_MS = 210.0    # 0.21 seconds

CLIENT_CONFIGS = {
    "antigravity": {
        "name": "Antigravity",
        "icon": "⚡",
        "color": "#6366f1",
        "border": "border-indigo-500/40",
        "bg": "bg-indigo-500/10",
        "text": "text-indigo-400"
    },
    "codex": {
        "name": "Codex",
        "icon": "🤖",
        "color": "#10b981",
        "border": "border-emerald-500/40",
        "bg": "bg-emerald-500/10",
        "text": "text-emerald-400"
    },
    "claude-code": {
        "name": "Claude Code",
        "icon": "🔮",
        "color": "#ec4899",
        "border": "border-pink-500/40",
        "bg": "bg-pink-500/10",
        "text": "text-pink-400"
    },
    "terminal": {
        "name": "Terminal CLI",
        "icon": "💻",
        "color": "#38bdf8",
        "border": "border-sky-500/40",
        "bg": "bg-sky-500/10",
        "text": "text-sky-400"
    }
}

def _client_details(value):
    if not isinstance(value, str) or not value.strip():
        return None, None
    display_name = value.strip()[:100]
    normalized = display_name.lower().replace("_", "-")
    if normalized in CLIENT_CONFIGS:
        return normalized, None
    return "other", display_name


def _detect_client_details(explicit: str = None):
    client, name = _client_details(explicit)
    if client:
        return client, name

    env_override = os.environ.get("JEV_CLIENT", "")
    client, name = _client_details(env_override)
    if client:
        return client, name

    # Check Antigravity environment
    if os.environ.get("ANTIGRAVITY_AGENT") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID"):
        return "antigravity", None
        
    # Check Claude Code environment
    if os.environ.get("CLAUDE_CODE") or os.environ.get("CLAUDE_PROJECT_ROOT") or any("claude" in k.lower() for k in os.environ.keys()):
        return "claude-code", None
        
    # Check Codex environment
    cwd = os.getcwd().lower()
    if "codex" in cwd or any("codex" in k.lower() for k in os.environ.keys()):
        return "codex", None
        
    return "terminal", None


def detect_client(explicit: str = None) -> str:
    """Return a known client id or ``other`` for an explicitly named new agent."""
    return _detect_client_details(explicit)[0]

def _legacy_init_ledger():
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists() or LEDGER_PATH.stat().st_size == 0:
        initial_records = [
            {
                "timestamp": "2026-09-27T19:03:00",
                "client": "codex",
                "model": "jev-1.13.0",
                "question_types": ["choice", "noul", "score"],
                "input_tokens": 1624,
                "output_tokens": 89,
                "confidence": 0.95,
                "summary": "Codex Live Review: Architectural gates and helper packaging",
                "cost_usd": round((1624 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:08:35",
                "client": "antigravity",
                "model": "jev-1.13.0",
                "question_types": ["choice"],
                "input_tokens": 398,
                "output_tokens": 42,
                "confidence": 1.0,
                "summary": "Choice: Three.js for 3D product configurator (100%)",
                "cost_usd": round((398 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:08:51",
                "client": "antigravity",
                "model": "jev-1.13.0",
                "question_types": ["choice"],
                "input_tokens": 321,
                "output_tokens": 41,
                "confidence": 0.94,
                "summary": "Choice: Three.js (96%), Unity (4%), Blender (0%)",
                "cost_usd": round((321 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:11:57",
                "client": "antigravity",
                "model": "jev-1.13.0",
                "question_types": ["choice"],
                "input_tokens": 324,
                "output_tokens": 42,
                "confidence": 1.0,
                "summary": "Verified Three.js 3D configurator decision",
                "cost_usd": round((324 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:14:43",
                "client": "terminal",
                "model": "jev-1.13.0",
                "question_types": ["choice"],
                "input_tokens": 348,
                "output_tokens": 40,
                "confidence": 0.99,
                "summary": "Choice: Node-WebSockets for real-time multiplayer chat",
                "cost_usd": round((348 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:35:46",
                "client": "terminal",
                "model": "jev-1.13.0",
                "question_types": ["noul"],
                "input_tokens": 286,
                "output_tokens": 38,
                "confidence": 0.47,
                "summary": "Noul Gate: Is this code safe to merge? (Prob: 0.47)",
                "cost_usd": round((286 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            },
            {
                "timestamp": "2026-09-27T19:35:49",
                "client": "terminal",
                "model": "jev-1.13.0",
                "question_types": ["score"],
                "input_tokens": 269,
                "output_tokens": 44,
                "confidence": 0.66,
                "summary": "Score: System response latency rating (1.77 / 2.0)",
                "cost_usd": round((269 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
            }
        ]
        LEDGER_PATH.write_text(json.dumps(initial_records, indent=2), encoding="utf-8")
    else:
        # Migrate old records if client is missing
        try:
            records = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
            modified = False
            for r in records:
                if "client" not in r:
                    r["client"] = "antigravity" if "3D product" in r.get("summary", "") else "terminal"
                    modified = True
            # Also ensure Codex record is present if not already there
            has_codex = any(r.get("client") == "codex" for r in records)
            if not has_codex:
                records.insert(0, {
                    "timestamp": "2026-09-27T19:03:00",
                    "client": "codex",
                    "model": "jev-1.13.0",
                    "question_types": ["choice", "noul", "score"],
                    "input_tokens": 1624,
                    "output_tokens": 89,
                    "confidence": 0.95,
                    "summary": "Codex Live Review: Architectural gates and helper packaging",
                    "cost_usd": round((1624 / 1_000_000) * RATE_PER_MILLION_INPUT, 6)
                })
                modified = True
            if modified:
                LEDGER_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
        except Exception:
            pass

def _legacy_log_call(model: str, question_types: list, input_tokens: int, output_tokens: int, confidence: float, summary: str, client: str = None):
    init_ledger()
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = []
    
    detected_client = detect_client(client)
    cost = (input_tokens / 1_000_000.0) * RATE_PER_MILLION_INPUT
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "client": detected_client,
        "model": model,
        "question_types": question_types,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "confidence": round(confidence, 2) if confidence is not None else 1.0,
        "summary": summary,
        "cost_usd": round(cost, 6)
    }
    data.append(entry)
    LEDGER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _legacy_get_metrics(filter_client: str = None):
    init_ledger()
    try:
        records = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        records = []
    
    if filter_client and filter_client.lower() != "all":
        records = [r for r in records if r.get("client", "terminal") == filter_client.lower()]

    total_calls = len(records)
    total_input = sum(r.get("input_tokens", 0) for r in records)
    total_output = sum(r.get("output_tokens", 0) for r in records)
    total_tokens = total_input + total_output
    total_cost = sum(r.get("cost_usd", 0.0) for r in records)
    
    # Accurate Token Savings Calculations:
    baseline_tokens_in = total_calls * BASELINE_LLM_INPUT_TOKENS_PER_CALL
    baseline_tokens_out = total_calls * BASELINE_LLM_OUTPUT_TOKENS_PER_CALL
    baseline_total_tokens = baseline_tokens_in + baseline_tokens_out
    
    tokens_saved = max(0, baseline_total_tokens - total_tokens)
    token_saving_pct = (tokens_saved / baseline_total_tokens * 100.0) if baseline_total_tokens else 0.0
    
    # Accurate Cost Savings Calculations:
    baseline_cost_usd = (baseline_tokens_in / 1_000_000.0 * STANDARD_LLM_INPUT_RATE) + (baseline_tokens_out / 1_000_000.0 * STANDARD_LLM_OUTPUT_RATE)
    cost_saved_usd = max(0.0, baseline_cost_usd - total_cost)
    cost_saving_pct = (cost_saved_usd / baseline_cost_usd * 100.0) if baseline_cost_usd else 0.0
    roi_multiplier = (baseline_cost_usd / total_cost) if total_cost > 0 else 1.0

    # Speed & Latency Impact:
    baseline_time_sec = (total_calls * BASELINE_LLM_LATENCY_MS) / 1000.0
    jev_time_sec = (total_calls * JEV_AVERAGE_LATENCY_MS) / 1000.0
    time_saved_sec = max(0.0, baseline_time_sec - jev_time_sec)
    speedup_factor = (BASELINE_LLM_LATENCY_MS / JEV_AVERAGE_LATENCY_MS) if JEV_AVERAGE_LATENCY_MS > 0 else 20.0

    # Quantity & Context Preservation Impact:
    context_bloat_prevented = max(0, baseline_tokens_in - total_input)
    cost_per_heavy_call = (BASELINE_LLM_INPUT_TOKENS_PER_CALL / 1_000_000.0 * STANDARD_LLM_INPUT_RATE) + (BASELINE_LLM_OUTPUT_TOKENS_PER_CALL / 1_000_000.0 * STANDARD_LLM_OUTPUT_RATE)
    avg_jev_call_cost = (total_cost / total_calls) if total_calls > 0 else ((380 / 1_000_000.0) * RATE_PER_MILLION_INPUT)
    throughput_ratio = int(cost_per_heavy_call / avg_jev_call_cost) if avg_jev_call_cost > 0 else 1700

    type_counts = {"choice": 0, "noul": 0, "score": 0}
    client_counts = {k: 0 for k in CLIENT_CONFIGS}
    
    for r in records:
        c = r.get("client", "terminal").lower()
        client_counts[c] = client_counts.get(c, 0) + 1
        for qt in r.get("question_types", []):
            qt_low = qt.lower()
            if qt_low in type_counts:
                type_counts[qt_low] += 1
            else:
                type_counts[qt_low] = type_counts.get(qt_low, 0) + 1
                
    confidences = [r.get("confidence", 1.0) for r in records if r.get("confidence") is not None]
    avg_conf = (sum(confidences) / len(confidences)) if confidences else 1.0

    return {
        "total_calls": total_calls,
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "baseline_tokens_in": baseline_tokens_in,
        "baseline_tokens_out": baseline_tokens_out,
        "baseline_total_tokens": baseline_total_tokens,
        "tokens_saved": tokens_saved,
        "token_saving_pct": round(token_saving_pct, 1),
        "baseline_cost_usd": baseline_cost_usd,
        "cost_saved_usd": cost_saved_usd,
        "cost_saving_pct": round(cost_saving_pct, 2),
        "roi_multiplier": round(roi_multiplier, 1),
        "baseline_time_sec": round(baseline_time_sec, 2),
        "jev_time_sec": round(jev_time_sec, 2),
        "time_saved_sec": round(time_saved_sec, 1),
        "speedup_factor": round(speedup_factor, 1),
        "context_bloat_prevented": context_bloat_prevented,
        "throughput_ratio": throughput_ratio,
        "type_counts": type_counts,
        "client_counts": client_counts,
        "avg_confidence": avg_conf,
        "records": records
    }

def _legacy_print_impact_card(client_filter: str = None):
    metrics = get_metrics(client_filter)
    
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        
    w = 82
    line_double = "=" * w
    line_single = "-" * w
    
    filter_label = f" [{client_filter.upper()} FOCUS]" if client_filter and client_filter.lower() != "all" else " [ALL AGENTS AGGREGATE]"
    
    print("\n" + line_double)
    print(f"   ⚡ JEV SYSTEM ONE: TOKEN SAVINGS, SPEED, QUALITY & ROI IMPACT REPORT{filter_label}")
    print(line_double)
    
    # 1. Executive Summary & Token Savings
    print(" 📊 1. TOKEN SAVINGS & FINANCIAL ROI (صرفه‌جویی توکن و بازده مالی):")
    print(f"  • Total System One Decisions   : {metrics['total_calls']} decisions executed")
    print(f"  • Standard LLM Baseline Tokens : {metrics['baseline_total_tokens']:,} tokens (Input: {metrics['baseline_tokens_in']:,} | Output: {metrics['baseline_tokens_out']:,})")
    print(f"  • Actual Jev Tokens Burned     : {metrics['total_tokens']:,} tokens (Input: {metrics['total_input']:,} | Output: {metrics['total_output']:,} [Free!])")
    print(f"  • 🟢 NET TOKENS SAVED          : {metrics['tokens_saved']:,} TOKENS ({metrics['token_saving_pct']}% Token Reduction!)")
    print(f"  • Standard LLM Baseline Cost   : ${metrics['baseline_cost_usd']:.4f} USD (@ $3.00/1M In, $15.00/1M Out)")
    print(f"  • Actual Spend on Jev          : ${metrics['total_cost']:.6f} USD (@ $0.042/1M In, $0.00 Out)")
    print(f"  • 💰 NET FINANCIAL SAVINGS     : ${metrics['cost_saved_usd']:.4f} USD ({metrics['cost_saving_pct']}% Cost Reduction | {metrics['roi_multiplier']:,}x ROI)")
    print(line_single)
    
    # 2. Speed Impact
    print(" 🚀 2. SPEED & DEVELOPER LATENCY IMPACT (تاثیر در سرعت و زمان انتظار):")
    print(f"  • Average Latency per Decision : ~{JEV_AVERAGE_LATENCY_MS:.0f} ms (Non-autoregressive fast classification)")
    print(f"  • Standard LLM Decision Delay  : ~{BASELINE_LLM_LATENCY_MS:.0f} ms (Prompt-and-Parse with Chain-of-Thought)")
    print(f"  • Speedup Multiplier           : {metrics['speedup_factor']}x FASTER per decision")
    print(f"  • Cumulative Wait Time Saved   : ~{metrics['time_saved_sec']} seconds saved of developer/agent idle blocking")
    print(line_single)
    
    # 3. Quality & Reliability Impact
    print(" 🎯 3. CODE QUALITY & ACCURACY IMPACT (کیفیت، دقت و حذف توهم):")
    print(f"  • Mathematical Certainty       : 100% ZERO-HALLUCINATION bounded discrete output")
    print(f"  • Calibrated Confidence Score  : {metrics['avg_confidence']*100:.1f}% average statistical certainty")
    print(f"  • Syntax / Schema Failures     : 0 (No broken JSON tags, no missing fields, no parse retries)")
    print(f"  • Decision Drift Prevention    : Categorical softmax probabilities eliminate prompt-injection jitter")
    print(line_single)
    
    # 4. Quantity & Context Window Capacity
    print(" 📦 4. QUANTITY & CONTEXT PRESERVATION (کمیت، مقیاس‌پذیری و حفظ کانتکست):")
    print(f"  • Context Bloat Prevented      : {metrics['context_bloat_prevented']:,} tokens kept out of agent conversation")
    print(f"  • 'Lost in the Middle' Guard   : Main agent context window remains 100% clean for source code")
    print(f"  • Capacity Throughput Ratio    : 1 Standard LLM decision cost = {metrics['throughput_ratio']:,} Jev Decisions!")
    print(line_double)
    print(" Commands:")
    print("  • jev impact --json    : Output structured JSON metrics")
    print("  • jev panel --web      : View interactive charts, gauges and animation dashboard")
    print("  • jev choice -s \"...\"  : Run an instant System One choice decision")
    print(line_double + "\n")

def _legacy_print_terminal_card(client_filter: str = None):
    metrics = get_metrics(client_filter)
    
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        
    w = 74
    line_double = "=" * w
    line_single = "-" * w
    
    filter_label = f" [FILTER: {client_filter.upper()}]" if client_filter and client_filter.lower() != "all" else " [ALL AGENTS AGGREGATE]"
    
    print("\n" + line_double)
    print(f"   ⚡ JEV (SYSTEM ONE) MULTI-AGENT WALLET & USAGE DASHBOARD{filter_label}")
    print(line_double)
    print(f" Total Decisions      : {metrics['total_calls']}")
    print(f" Total Tokens Burned  : {metrics['total_tokens']:,} (Input: {metrics['total_input']:,} | Output: {metrics['total_output']:,})")
    print(f" 🟢 Net Tokens Saved  : {metrics['tokens_saved']:,} tokens ({metrics['token_saving_pct']}% reduction vs LLMs)")
    print(f" Actual Spend (Jev)   : ${metrics['total_cost']:.6f} USD (@ $0.042 / 1M tokens)")
    print(f" 💰 Cost Savings      : ${metrics['cost_saved_usd']:.4f} USD ({metrics['cost_saving_pct']}% saved | {metrics['roi_multiplier']:,}x ROI)")
    print(f" 🚀 Latency Speedup   : {metrics['speedup_factor']}x faster (~{metrics['time_saved_sec']}s developer wait saved)")
    print(f" Calibrated Confidence: {metrics['avg_confidence']*100:.1f}% (Zero-Hallucination)")
    print(line_single)
    
    # Key Pool Display
    try:
        import jev_key_manager
        keys_list = jev_key_manager.list_keys()
        cfg = jev_key_manager.load_config()
        strat = cfg.get("strategy", "round_robin").upper()
        print(f" 🔑 API KEY ROTATION POOL [{strat}]:")
        for k in keys_list:
            ptr = " [->]" if k["is_next"] else "     "
            stat = f"[{k['status'].upper()}]"
            print(f" {ptr} {k['name']:<10} {k['masked']:<22} {stat:<10} | Calls: {k['calls']:>2} | Tokens: {k['tokens']:>5}")
        print(line_single)
    except Exception:
        pass
        
    print(" 🤖 USAGE BREAKDOWN BY AGENT CLIENT:")
    tot_clients = sum(metrics['client_counts'].values()) or 1
    for cl_key, cl_cfg in CLIENT_CONFIGS.items():
        c_count = metrics['client_counts'].get(cl_key, 0)
        c_pct = (c_count / tot_clients) * 100
        bar = "#" * int(c_pct / 5)
        print(f"  {cl_cfg['icon']} {cl_cfg['name']:<14} : {c_count:>2} calls ({c_pct:>5.1f}%) [{bar:<20}]")
        
    print(line_single)
    print(" 📊 USAGE BREAKDOWN BY QUESTION TYPE:")
    tot_types = sum(metrics['type_counts'].values()) or 1
    for q_type, count in metrics['type_counts'].items():
        pct = (count / tot_types) * 100
        bar = "#" * int(pct / 5)
        print(f"  - {q_type.upper():<12} : {count:>2} calls ({pct:>5.1f}%) [{bar:<20}]")
        
    print(line_single)
    print(" 📜 RECENT MULTI-AGENT DECISION STREAM:")
    recent = metrics["records"][-5:]
    for idx, r in enumerate(reversed(recent), 1):
        ts = r.get("timestamp", "").replace("T", " ")
        cl = r.get("client", "terminal")
        cl_icon = CLIENT_CONFIGS.get(cl, {}).get("icon", "💻")
        cl_name = CLIENT_CONFIGS.get(cl, {}).get("name", "Terminal")
        conf = r.get("confidence", 1.0)
        summary = r.get("summary", "Decision completed")[:34]
        print(f"  {idx}. {cl_icon} [{cl_name:<10}] Conf: {conf*100:>3.0f}% | {summary}")
        
    print(line_double)
    print(" Tips: Run 'jev impact' for the full Speed/Quality/Quantity report!")
    print("       Run 'jev panel --web' for the high-end interactive UI with animations!")
    print(line_double + "\n")

def _legacy_open_web_dashboard():
    # Pass all data to HTML for instant client-side interactive filtering and smooth animations
    init_ledger()
    records = []
    try:
        records = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
        
    import jev_key_manager
    keys_list = jev_key_manager.list_keys()
    loaded_key_config = jev_key_manager.load_config()
    loaded_strategy = loaded_key_config.get("strategy")
    key_config = {"strategy": loaded_strategy if loaded_strategy in ("round_robin", "single") else "unknown"}
    html_path = LEDGER_PATH.parent / "jev_dashboard.html"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jev AI - Multi-Agent System One Control Center</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        dark: {{
                            bg: '#090d16',
                            card: '#111827',
                            border: '#1f2937',
                            subtle: '#374151'
                        }}
                    }},
                    animation: {{
                        'pulse-glow': 'pulseGlow 2.5s infinite ease-in-out',
                        'fade-slide': 'fadeSlideUp 0.4s ease-out forwards',
                    }},
                    keyframes: {{
                        pulseGlow: {{
                            '0%, 100%': {{ opacity: 0.4, transform: 'scale(1)' }},
                            '50%': {{ opacity: 0.8, transform: 'scale(1.03)' }}
                        }},
                        fadeSlideUp: {{
                            '0%': {{ opacity: 0, transform: 'translateY(12px)' }},
                            '100%': {{ opacity: 1, transform: 'translateY(0)' }}
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #090d16 55%, #05070c 100%);
            min-height: 100vh;
            color: #f3f4f6;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        .glass-panel {{
            background: rgba(17, 24, 39, 0.75);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .glass-panel:hover {{
            border-color: rgba(99, 102, 241, 0.35);
            transform: translateY(-2px);
        }}
        .custom-scroll::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        .custom-scroll::-webkit-scrollbar-thumb {{
            background: #374151;
            border-radius: 999px;
        }}
    </style>
</head>
<body class="p-4 sm:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

        <!-- Top Navigation & Header -->
        <header class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-gray-800">
            <div>
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                        <span class="text-xl">⚡</span>
                    </div>
                    <div>
                        <h1 class="text-2xl font-black tracking-tight text-white flex items-center gap-2">
                            Jev <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">SYSTEM ONE</span>
                            <span class="text-sm font-normal text-gray-400">Multi-Agent Control & Wallet Panel</span>
                        </h1>
                        <p class="text-xs text-gray-400">TypeSafe AI • Fast Non-Autoregressive Decision Engine</p>
                    </div>
                </div>
            </div>

            <div class="flex items-center gap-3">
                <span class="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    API Live & Connected
                </span>
                <button onclick="refreshData()" class="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors border border-gray-700 flex items-center gap-1.5">
                    <span>↻</span> Refresh
                </button>
            </div>
        </header>

        <!-- Multi-Client Filter Tabs -->
        <div class="flex flex-wrap items-center gap-2 p-1.5 rounded-xl bg-gray-900/80 border border-gray-800">
            <span class="text-xs font-medium text-gray-400 px-3">Agent Filter:</span>
            <button onclick="filterByClient('all')" id="btn-all" class="filter-tab px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition-all">
                🌟 All Agents (مجموع)
            </button>
            <button onclick="filterByClient('antigravity')" id="btn-antigravity" class="filter-tab px-4 py-1.5 rounded-lg text-xs font-semibold bg-gray-800 text-gray-400 hover:text-white transition-all">
                ⚡ Antigravity
            </button>
            <button onclick="filterByClient('codex')" id="btn-codex" class="filter-tab px-4 py-1.5 rounded-lg text-xs font-semibold bg-gray-800 text-gray-400 hover:text-white transition-all">
                🤖 Codex
            </button>
            <button onclick="filterByClient('claude-code')" id="btn-claude-code" class="filter-tab px-4 py-1.5 rounded-lg text-xs font-semibold bg-gray-800 text-gray-400 hover:text-white transition-all">
                🔮 Claude Code
            </button>
            <button onclick="filterByClient('terminal')" id="btn-terminal" class="filter-tab px-4 py-1.5 rounded-lg text-xs font-semibold bg-gray-800 text-gray-400 hover:text-white transition-all">
                💻 Terminal / CLI
            </button>
        </div>

        <!-- Metric Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <!-- Card 1: Total Calls -->
            <div class="glass-panel p-5 rounded-2xl relative overflow-hidden group">
                <div class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Total Decisions</div>
                <div id="metric-calls" class="text-3xl font-extrabold text-white">0</div>
                <div class="text-xs text-gray-400 mt-2 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                    <span id="metric-calls-sub">Bounded Cognitive Choices</span>
                </div>
            </div>

            <!-- Card 2: Tokens Burned -->
            <div class="glass-panel p-5 rounded-2xl relative overflow-hidden group">
                <div class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Token Consumption</div>
                <div id="metric-tokens" class="text-3xl font-extrabold text-white">0</div>
                <div class="text-xs text-gray-400 mt-2 flex items-center justify-between">
                    <span id="metric-in-out">In: 0 | Out: 0</span>
                    <span class="text-emerald-400 font-medium">Free Outputs!</span>
                </div>
            </div>

            <!-- Card 3: Wallet Spend -->
            <div class="glass-panel p-5 rounded-2xl relative overflow-hidden group">
                <div class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Estimated Spend</div>
                <div id="metric-cost" class="text-3xl font-extrabold text-emerald-400">$0.000000</div>
                <div class="text-xs text-gray-400 mt-2 flex items-center gap-1.5">
                    <span>Rate: $0.042 / 1M In Tokens</span>
                </div>
            </div>

            <!-- Card 4: Calibrated Confidence -->
            <div class="glass-panel p-5 rounded-2xl relative overflow-hidden group">
                <div class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Confidence Score</div>
                <div id="metric-conf" class="text-3xl font-extrabold text-purple-400">0%</div>
                <div class="text-xs text-gray-400 mt-2 flex items-center justify-between">
                    <span>Statistical Calibration</span>
                    <span class="text-xs text-indigo-400 font-semibold">Zero-Hallucination</span>
                </div>
            </div>
        </div>

        <!-- NEW: Comprehensive Impact & Value Engine Section (Speed, Quality, Quantity & Token Savings) -->
        <div class="space-y-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <span class="px-2 py-0.5 rounded text-xs font-bold bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-300 border border-emerald-500/30">
                        IMPACT & ROI ENGINE
                    </span>
                    <h2 class="text-sm font-bold text-gray-200 uppercase tracking-wider">Project Value: Speed, Quality, Quantity & Token Savings</h2>
                </div>
                <span class="text-xs text-gray-400 hidden sm:inline">Benchmark: Frontier LLM Prompt-and-Parse</span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <!-- Impact Card 1: Token Savings -->
                <div class="glass-panel p-5 rounded-2xl border-l-4 border-l-emerald-500 bg-gradient-to-b from-gray-900 to-emerald-950/20">
                    <div class="flex justify-between items-start">
                        <span class="text-xs font-bold text-emerald-400 uppercase tracking-wider">🎯 Token Reduction</span>
                        <span id="impact-tokens-pct" class="text-xs px-2 py-0.5 rounded-full font-bold bg-emerald-500/20 text-emerald-300">92.4%</span>
                    </div>
                    <div id="impact-tokens-saved" class="text-2xl font-black text-white mt-2">0</div>
                    <div class="text-xs text-gray-400 mt-1">Tokens Saved vs Standard LLMs</div>
                    <div class="mt-3 pt-3 border-t border-gray-800/80 space-y-1.5 text-[11px] text-gray-400">
                        <div class="flex justify-between">
                            <span>Standard LLM:</span>
                            <span id="impact-tokens-base" class="font-mono text-gray-300">0</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Jev Actual:</span>
                            <span id="impact-tokens-jev" class="font-mono text-emerald-400 font-bold">0</span>
                        </div>
                    </div>
                </div>

                <!-- Impact Card 2: Speed Multiplier -->
                <div class="glass-panel p-5 rounded-2xl border-l-4 border-l-indigo-500 bg-gradient-to-b from-gray-900 to-indigo-950/20">
                    <div class="flex justify-between items-start">
                        <span class="text-xs font-bold text-indigo-400 uppercase tracking-wider">🚀 Speed & Latency</span>
                        <span class="text-xs px-2 py-0.5 rounded-full font-bold bg-indigo-500/20 text-indigo-300">20x FASTER</span>
                    </div>
                    <div id="impact-speedup" class="text-2xl font-black text-white mt-2">20.0x</div>
                    <div class="text-xs text-gray-400 mt-1">Decision Velocity Multiplier</div>
                    <div class="mt-3 pt-3 border-t border-gray-800/80 space-y-1.5 text-[11px] text-gray-400">
                        <div class="flex justify-between">
                            <span>Developer Wait Saved:</span>
                            <span id="impact-time-saved" class="font-mono text-indigo-300 font-bold">0.0s</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Per-Call Latency:</span>
                            <span class="font-mono text-gray-300">~210ms vs ~4.2s</span>
                        </div>
                    </div>
                </div>

                <!-- Impact Card 3: Quality & Zero Hallucination -->
                <div class="glass-panel p-5 rounded-2xl border-l-4 border-l-purple-500 bg-gradient-to-b from-gray-900 to-purple-950/20">
                    <div class="flex justify-between items-start">
                        <span class="text-xs font-bold text-purple-400 uppercase tracking-wider">🛡️ Decision Quality</span>
                        <span class="text-xs px-2 py-0.5 rounded-full font-bold bg-purple-500/20 text-purple-300">100% RELIABLE</span>
                    </div>
                    <div class="text-2xl font-black text-white mt-2">0 Hallucinations</div>
                    <div class="text-xs text-gray-400 mt-1">Bounded Discrete State Spaces</div>
                    <div class="mt-3 pt-3 border-t border-gray-800/80 space-y-1.5 text-[11px] text-gray-400">
                        <div class="flex justify-between">
                            <span>Schema Parse Errors:</span>
                            <span class="font-mono text-emerald-400 font-bold">0 (Zero Retries)</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Statistical Calibration:</span>
                            <span id="impact-quality-conf" class="font-mono text-purple-300 font-bold">0%</span>
                        </div>
                    </div>
                </div>

                <!-- Impact Card 4: Quantity & Context Preservation -->
                <div class="glass-panel p-5 rounded-2xl border-l-4 border-l-sky-500 bg-gradient-to-b from-gray-900 to-sky-950/20">
                    <div class="flex justify-between items-start">
                        <span class="text-xs font-bold text-sky-400 uppercase tracking-wider">📦 Context & Capacity</span>
                        <span class="text-xs px-2 py-0.5 rounded-full font-bold bg-sky-500/20 text-sky-300">CLEAN MEMORY</span>
                    </div>
                    <div id="impact-context-preserved" class="text-2xl font-black text-white mt-2">0</div>
                    <div class="text-xs text-gray-400 mt-1">Context Window Bloat Stripped</div>
                    <div class="mt-3 pt-3 border-t border-gray-800/80 space-y-1.5 text-[11px] text-gray-400">
                        <div class="flex justify-between">
                            <span>"Lost in Middle" Guard:</span>
                            <span class="font-mono text-sky-300 font-bold">Active (100%)</span>
                        </div>
                        <div class="flex justify-between">
                            <span>Throughput Multiplier:</span>
                            <span id="impact-throughput" class="font-mono text-emerald-400 font-bold">1 LLM = ~1,350 Jev</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts & Efficiency Section -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <!-- Client Distribution Chart (4 cols) -->
            <div class="lg:col-span-4 glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <div>
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider mb-1">Agent Environment Share</h3>
                    <p class="text-xs text-gray-400 mb-4">Volume breakdown across connected coding assistants</p>
                </div>
                <div class="relative h-56 flex items-center justify-center">
                    <canvas id="clientChart"></canvas>
                </div>
                <div class="pt-4 border-t border-gray-800 text-center text-xs text-gray-400">
                    Auto-detected based on execution context
                </div>
            </div>

            <!-- Question Type Chart (4 cols) -->
            <div class="lg:col-span-4 glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <div>
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider mb-1">Decision Primitives</h3>
                    <p class="text-xs text-gray-400 mb-4">Choice vs Noul vs Score distribution</p>
                </div>
                <div class="relative h-56 flex items-center justify-center">
                    <canvas id="typeChart"></canvas>
                </div>
                <div class="pt-4 border-t border-gray-800 text-center text-xs text-gray-400">
                    Optimized primitive routing
                </div>
            </div>

            <!-- Cost Savings & Financial ROI (4 cols) -->
            <div class="lg:col-span-4 glass-panel p-6 rounded-2xl flex flex-col justify-between bg-gradient-to-br from-gray-900 to-indigo-950/40">
                <div>
                    <span class="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">FINANCIAL ROI</span>
                    <h3 class="text-lg font-black text-white mt-3">Estimated Cost Savings</h3>
                    <p class="text-xs text-gray-400 mt-1">Comparing Jev System One vs Frontier LLM calls</p>
                </div>

                <div class="my-6">
                    <div id="metric-savings" class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-200">$0.0000</div>
                    <div class="text-xs text-gray-400 mt-2 leading-relaxed">
                        ⚡ <strong>Cost Reduction:</strong> <span id="metric-cost-pct" class="text-emerald-400 font-bold">99.9%</span> cheaper<br>
                        📈 <strong>ROI Multiplier:</strong> <span id="metric-roi-mult" class="text-indigo-300 font-bold">~1,350x</span> value leverage
                    </div>
                </div>

                <div class="p-3.5 rounded-xl bg-gray-900/90 border border-gray-800 text-xs text-gray-300 space-y-1">
                    <div class="flex justify-between"><span>Jev Rate:</span> <span class="font-bold text-indigo-400">$0.042 / 1M In (Free Out)</span></div>
                    <div class="flex justify-between"><span>Frontier LLM:</span> <span class="font-bold text-gray-400">$3.00 In / $15.00 Out</span></div>
                </div>
            </div>
        </div>

        <!-- Key Pool & Rotation Management Section -->
        <div class="glass-panel p-6 rounded-2xl">
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🔑</span> TypeSafe API Key Pool & Rotation
                    </h3>
                    <p class="text-xs text-gray-400">Automatic round-robin rotation, failover, and token consumption per key</p>
                </div>
                <div class="flex items-center gap-2 text-xs font-semibold px-3 py-1 rounded-lg bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                    <span>Strategy:</span>
                    <span class="uppercase tracking-wider text-white">{key_config.get('strategy', 'round_robin')}</span>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="key-pool-grid">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- Multi-Agent Decisions Table -->
        <div class="glass-panel p-6 rounded-2xl">
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-5">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>📜</span> Multi-Agent Decision Ledger
                    </h3>
                    <p class="text-xs text-gray-400">Audit trail of all decisions, probabilities, and confidence scores</p>
                </div>
                <div class="text-xs text-gray-400" id="table-count">Showing 0 decisions</div>
            </div>

            <div class="overflow-x-auto custom-scroll">
                <table class="w-full text-left border-collapse text-xs">
                    <thead>
                        <tr class="border-b border-gray-800 text-gray-400 uppercase text-[10px] tracking-wider">
                            <th class="py-3 px-3">Timestamp</th>
                            <th class="py-3 px-3">Agent Client</th>
                            <th class="py-3 px-3">Model</th>
                            <th class="py-3 px-3">Primitive</th>
                            <th class="py-3 px-3">Confidence</th>
                            <th class="py-3 px-3">Tokens (In/Out)</th>
                            <th class="py-3 px-3">Cost</th>
                            <th class="py-3 px-3">Decision Summary</th>
                        </tr>
                    </thead>
                    <tbody id="decision-table-body" class="divide-y divide-gray-800/60 text-gray-300">
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <!-- Live Data & Scripting -->
    <script>
        const RAW_RECORDS = {json.dumps(records)};
        const CLIENT_CONFIGS = {json.dumps(CLIENT_CONFIGS)};
        const KEY_POOL = {json.dumps(keys_list)};
        const KEY_CONFIG = {json.dumps(key_config)};
        const RATE_INPUT = {RATE_PER_MILLION_INPUT};
        const STD_RATE_IN = {STANDARD_LLM_INPUT_RATE};
        const STD_RATE_OUT = {STANDARD_LLM_OUTPUT_RATE};
        const BASELINE_IN = {BASELINE_LLM_INPUT_TOKENS_PER_CALL};
        const BASELINE_OUT = {BASELINE_LLM_OUTPUT_TOKENS_PER_CALL};
        const BASELINE_LATENCY = {BASELINE_LLM_LATENCY_MS};
        const JEV_LATENCY = {JEV_AVERAGE_LATENCY_MS};

        let activeFilter = 'all';
        let clientChart = null;
        let typeChart = null;

        function renderKeyPool() {{
            const grid = document.getElementById('key-pool-grid');
            if (!grid) return;
            grid.innerHTML = '';
            KEY_POOL.forEach(k => {{
                const isNext = k.is_next;
                const card = document.createElement('div');
                card.className = `p-4 rounded-xl border transition-all ${{isNext ? 'bg-indigo-950/30 border-indigo-500/50 shadow-lg shadow-indigo-500/10' : 'bg-gray-900/60 border-gray-800'}}`;
                card.innerHTML = `
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex items-center gap-2">
                            <span class="font-bold text-white text-sm capitalize">${{k.name}}</span>
                            ${{k.is_active_target ? '<span class="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">PRIMARY</span>' : ''}}
                            ${{isNext ? '<span class="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/30 text-indigo-300 border border-indigo-500/50 font-bold animate-pulse">NEXT IN ROTATION</span>' : ''}}
                        </div>
                        <span class="text-[10px] px-2 py-0.5 rounded-full font-semibold ${{k.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'}} uppercase">
                            ${{k.status}}
                        </span>
                    </div>
                    <div class="font-mono text-xs text-gray-400 mb-3 bg-gray-950/60 px-2.5 py-1.5 rounded-lg border border-gray-800 flex justify-between">
                        <span>${{k.masked}}</span>
                        <span class="text-gray-500 text-[10px]">TypeSafe Key</span>
                    </div>
                    <div class="flex justify-between items-center text-xs text-gray-400 pt-2 border-t border-gray-800/80">
                        <span>Total Decisions: <strong class="text-white">${{k.calls}}</strong></span>
                        <span>Tokens: <strong class="text-indigo-400">${{k.tokens.toLocaleString()}}</strong></span>
                    </div>
                `;
                grid.appendChild(card);
            }});
        }}

        function filterByClient(clientKey) {{
            activeFilter = clientKey;
            
            // Update Tab styles
            document.querySelectorAll('.filter-tab').forEach(tab => {{
                tab.classList.remove('bg-indigo-600', 'text-white');
                tab.classList.add('bg-gray-800', 'text-gray-400');
            }});
            const activeBtn = document.getElementById('btn-' + clientKey);
            if (activeBtn) {{
                activeBtn.classList.remove('bg-gray-800', 'text-gray-400');
                activeBtn.classList.add('bg-indigo-600', 'text-white');
            }}

            renderDashboard();
        }}

        function renderDashboard() {{
            const filtered = activeFilter === 'all' 
                ? RAW_RECORDS 
                : RAW_RECORDS.filter(r => (r.client || 'terminal') === activeFilter);

            // Metrics
            const totalCalls = filtered.length;
            const totalInput = filtered.reduce((acc, r) => acc + (r.input_tokens || 0), 0);
            const totalOutput = filtered.reduce((acc, r) => acc + (r.output_tokens || 0), 0);
            const totalTokens = totalInput + totalOutput;
            const totalCost = filtered.reduce((acc, r) => acc + (r.cost_usd || 0.0), 0.0);
            
            // Calculations
            const baseTokensIn = totalCalls * BASELINE_IN;
            const baseTokensOut = totalCalls * BASELINE_OUT;
            const baseTotalTokens = baseTokensIn + baseTokensOut;
            const tokensSaved = Math.max(0, baseTotalTokens - totalTokens);
            const tokenSavingPct = baseTotalTokens > 0 ? ((tokensSaved / baseTotalTokens) * 100).toFixed(1) : 0;

            const baseCost = (baseTokensIn / 1000000 * STD_RATE_IN) + (baseTokensOut / 1000000 * STD_RATE_OUT);
            const savings = Math.max(0, baseCost - totalCost);
            const costSavingPct = baseCost > 0 ? ((savings / baseCost) * 100).toFixed(2) : 0;
            const roiMult = totalCost > 0 ? Math.round(baseCost / totalCost) : 1350;

            const timeSaved = Math.max(0, ((totalCalls * BASELINE_LATENCY) - (totalCalls * JEV_LATENCY)) / 1000).toFixed(1);
            const contextBloatSaved = Math.max(0, baseTokensIn - totalInput);
            const throughputRatio = totalCost > 0 ? Math.round(baseCost / (totalCost / (totalCalls || 1))) : 1350;

            const confs = filtered.map(r => r.confidence !== undefined ? r.confidence : 1.0);
            const avgConf = confs.length ? (confs.reduce((a, b) => a + b, 0) / confs.length) : 1.0;

            // DOM updates
            document.getElementById('metric-calls').innerText = totalCalls;
            document.getElementById('metric-calls-sub').innerText = activeFilter === 'all' ? 'All Connected Clients' : (CLIENT_CONFIGS[activeFilter]?.name || activeFilter);
            document.getElementById('metric-tokens').innerText = totalTokens.toLocaleString();
            document.getElementById('metric-in-out').innerText = `In: ${{totalInput.toLocaleString()}} | Out: ${{totalOutput.toLocaleString()}}`;
            document.getElementById('metric-cost').innerText = '$' + totalCost.toFixed(6);
            document.getElementById('metric-conf').innerText = Math.round(avgConf * 100) + '%';
            document.getElementById('metric-savings').innerText = '$' + savings.toFixed(4);
            document.getElementById('metric-cost-pct').innerText = costSavingPct + '%';
            document.getElementById('metric-roi-mult').innerText = `~${{roiMult.toLocaleString()}}x`;
            document.getElementById('table-count').innerText = `Showing ${{filtered.length}} of ${{RAW_RECORDS.length}} decisions`;

            // Impact Section Updates
            document.getElementById('impact-tokens-saved').innerText = tokensSaved.toLocaleString();
            document.getElementById('impact-tokens-pct').innerText = tokenSavingPct + '%';
            document.getElementById('impact-tokens-base').innerText = baseTotalTokens.toLocaleString();
            document.getElementById('impact-tokens-jev').innerText = totalTokens.toLocaleString();

            document.getElementById('impact-time-saved').innerText = timeSaved + 's';
            document.getElementById('impact-quality-conf').innerText = Math.round(avgConf * 100) + '%';
            document.getElementById('impact-context-preserved').innerText = contextBloatSaved.toLocaleString();
            document.getElementById('impact-throughput').innerText = `1 LLM = ~${{throughputRatio.toLocaleString()}} Jev`;

            // Table
            const tbody = document.getElementById('decision-table-body');
            tbody.innerHTML = '';
            [...filtered].reverse().forEach(r => {{
                const cl = r.client || 'terminal';
                const clCfg = CLIENT_CONFIGS[cl] || {{ name: cl, icon: '💻', border: 'border-gray-500/40', bg: 'bg-gray-500/10', text: 'text-gray-400' }};
                const timeStr = (r.timestamp || '').replace('T', ' ').slice(0, 19);
                const confPct = Math.round((r.confidence !== undefined ? r.confidence : 1.0) * 100);
                const types = (r.question_types || []).map(t => `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-800 text-indigo-300 border border-gray-700 uppercase">${{t}}</span>`).join(' ');

                const tr = document.createElement('tr');
                tr.className = 'hover:bg-gray-800/40 transition-colors';
                tr.innerHTML = `
                    <td class="py-3 px-3 font-mono text-gray-400">${{timeStr}}</td>
                    <td class="py-3 px-3">
                        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium ${{clCfg.bg}} ${{clCfg.text}} border ${{clCfg.border}}">
                            <span>${{clCfg.icon}}</span> ${{clCfg.name}}
                        </span>
                    </td>
                    <td class="py-3 px-3 font-mono text-gray-400">${{r.model || 'jev-latest'}}</td>
                    <td class="py-3 px-3">${{types}}</td>
                    <td class="py-3 px-3">
                        <div class="flex items-center gap-2">
                            <span class="font-bold text-white">${{confPct}}%</span>
                            <div class="w-12 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                                <div class="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 rounded-full" style="width: ${{confPct}}%"></div>
                            </div>
                        </div>
                    </td>
                    <td class="py-3 px-3 font-mono text-gray-400">${{(r.input_tokens || 0) + (r.output_tokens || 0)}}</td>
                    <td class="py-3 px-3 font-mono text-emerald-400">$${{(r.cost_usd || 0.0).toFixed(6)}}</td>
                    <td class="py-3 px-3 text-gray-200 max-w-xs truncate font-medium">${{r.summary || 'Completed decision'}}</td>
                `;
                tbody.appendChild(tr);
            }});

            updateCharts(filtered);
        }}

        function updateCharts(filtered) {{
            // 1. Client Distribution
            const clientCounts = {{}};
            Object.keys(CLIENT_CONFIGS).forEach(k => clientCounts[k] = 0);
            RAW_RECORDS.forEach(r => {{
                const c = r.client || 'terminal';
                clientCounts[c] = (clientCounts[c] || 0) + 1;
            }});

            const clientCtx = document.getElementById('clientChart').getContext('2d');
            if (clientChart) clientChart.destroy();
            clientChart = new Chart(clientCtx, {{
                type: 'doughnut',
                data: {{
                    labels: Object.keys(CLIENT_CONFIGS).map(k => CLIENT_CONFIGS[k].name),
                    datasets: [{{
                        data: Object.keys(CLIENT_CONFIGS).map(k => clientCounts[k]),
                        backgroundColor: ['#6366f1', '#10b981', '#ec4899', '#38bdf8'],
                        borderWidth: 0,
                        hoverOffset: 6
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {{ duration: 700, easing: 'easeOutQuart' }},
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ color: '#9ca3af', font: {{ size: 10 }}, boxWidth: 12 }} }}
                    }}
                }}
            }});

            // 2. Type Distribution for currently filtered items
            const typeCounts = {{ choice: 0, noul: 0, score: 0 }};
            filtered.forEach(r => {{
                (r.question_types || []).forEach(t => {{
                    const tl = t.toLowerCase();
                    if (typeCounts[tl] !== undefined) typeCounts[tl]++;
                }});
            }});

            const typeCtx = document.getElementById('typeChart').getContext('2d');
            if (typeChart) typeChart.destroy();
            typeChart = new Chart(typeCtx, {{
                type: 'bar',
                data: {{
                    labels: ['Choice', 'Noul (Binary)', 'Score (Graded)'],
                    datasets: [{{
                        label: 'Decision Calls',
                        data: [typeCounts.choice, typeCounts.noul, typeCounts.score],
                        backgroundColor: ['#6366f1', '#10b981', '#f59e0b'],
                        borderRadius: 6,
                        borderSkipped: false
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {{ duration: 700, easing: 'easeOutQuart' }},
                    scales: {{
                        y: {{ beginAtZero: true, grid: {{ color: '#1f2937' }}, ticks: {{ color: '#9ca3af', stepSize: 1 }} }},
                        x: {{ grid: {{ display: false }}, ticks: {{ color: '#9ca3af' }} }}
                    }},
                    plugins: {{
                        legend: {{ display: false }}
                    }}
                }}
            }});
        }}

        function refreshData() {{
            window.location.reload();
        }}

        // Initial Load
        renderKeyPool();
        renderDashboard();
    </script>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")
    print(f"Opening enhanced multi-agent dashboard: {html_path}")
    webbrowser.open(html_path.as_uri())

def init_ledger():
    """Ensure a valid durable ledger exists, recovering without discarding bad bytes."""
    _records, state = load_ledger(LEDGER_PATH, create=True)
    return state


def _is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _token_value(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _safe_comparison(value):
    """Keep only an explicitly paired, provider-reported baseline data shape."""
    if not isinstance(value, dict) or value.get("equivalent") is not True:
        return None
    comparison_id = value.get("comparison_id")
    baseline = value.get("baseline")
    if not isinstance(comparison_id, str) or not comparison_id.strip() or not isinstance(baseline, dict):
        return None
    if baseline.get("usage_source") != "provider":
        return None
    input_tokens = _token_value(baseline.get("input_tokens"))
    output_tokens = _token_value(baseline.get("output_tokens"))
    provider = baseline.get("provider")
    model = baseline.get("model")
    if input_tokens is None or output_tokens is None:
        return None
    if not isinstance(provider, str) or not provider.strip() or not isinstance(model, str) or not model.strip():
        return None

    safe_baseline = {
        "provider": provider.strip()[:120],
        "model": model.strip()[:120],
        "usage_source": "provider",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    baseline_cost = baseline.get("cost_usd")
    cost_source = baseline.get("cost_source")
    if _is_finite_number(baseline_cost) and baseline_cost >= 0 and cost_source in (
        "provider_reported",
        "calculated_from_pricing_snapshot",
    ):
        safe_baseline["cost_usd"] = round(float(baseline_cost), 10)
        safe_baseline["cost_source"] = cost_source

    pricing = baseline.get("pricing_snapshot")
    if isinstance(pricing, dict):
        safe_pricing = {
            "provider": str(pricing.get("provider", ""))[:120],
            "source": str(pricing.get("source", ""))[:300],
            "checked_on": str(pricing.get("checked_on", ""))[:40],
        }
        for rate_field in ("input_usd_per_million", "output_usd_per_million"):
            rate = pricing.get(rate_field)
            if _is_finite_number(rate) and rate >= 0:
                safe_pricing[rate_field] = float(rate)
        if "input_usd_per_million" in safe_pricing and "output_usd_per_million" in safe_pricing:
            safe_baseline["pricing_snapshot"] = safe_pricing
            if "cost_usd" not in safe_baseline:
                computed_cost = (
                    input_tokens * safe_pricing["input_usd_per_million"]
                    + output_tokens * safe_pricing["output_usd_per_million"]
                ) / 1_000_000.0
                safe_baseline["cost_usd"] = round(computed_cost, 10)
                safe_baseline["cost_source"] = "calculated_from_pricing_snapshot"

    return {
        "comparison_id": comparison_id.strip()[:160],
        "equivalent": True,
        "baseline": safe_baseline,
    }


def _normalized_record_client(record):
    client, _name = _client_details(record.get("client", "terminal"))
    return client or "terminal"


def _paired_savings(records, comparison_scope=None):
    occurrence_counts = {}
    for record in comparison_scope if comparison_scope is not None else records:
        comparison = record.get("comparison")
        comparison_id = comparison.get("comparison_id") if isinstance(comparison, dict) else None
        if isinstance(comparison_id, str) and comparison_id.strip():
            occurrence_counts[comparison_id] = occurrence_counts.get(comparison_id, 0) + 1
    pairs_by_id = {}
    for record in records:
        comparison = record.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("equivalent") is not True:
            continue
        comparison_id = comparison.get("comparison_id")
        if not isinstance(comparison_id, str) or not comparison_id.strip():
            continue
        if occurrence_counts.get(comparison_id, 0) != 1:
            continue
        baseline = comparison.get("baseline")
        if not isinstance(comparison_id, str) or not isinstance(baseline, dict):
            continue
        if record.get("usage_source") != "provider" or baseline.get("usage_source") != "provider":
            continue
        jev_input = _token_value(record.get("input_tokens"))
        jev_output = _token_value(record.get("output_tokens"))
        base_input = _token_value(baseline.get("input_tokens"))
        base_output = _token_value(baseline.get("output_tokens"))
        if None in (jev_input, jev_output, base_input, base_output):
            continue
        pairs_by_id.setdefault(comparison_id, []).append((record, baseline))

    valid_pairs = [rows[0] for rows in pairs_by_id.values() if len(rows) == 1]
    token_deltas = [
        baseline["input_tokens"] + baseline["output_tokens"]
        - record["input_tokens"] - record["output_tokens"]
        for record, baseline in valid_pairs
    ]
    priced_pairs = [
        (record, baseline)
        for record, baseline in valid_pairs
        if _is_finite_number(record.get("cost_usd"))
        and record["cost_usd"] >= 0
        and record.get("cost_source") in ("provider_reported", "estimated_from_provider_usage")
        and _is_finite_number(baseline.get("cost_usd"))
        and baseline["cost_usd"] >= 0
        and baseline.get("cost_source") in ("provider_reported", "calculated_from_pricing_snapshot")
    ]
    baseline_tokens = sum(pair[1]["input_tokens"] + pair[1]["output_tokens"] for pair in valid_pairs)
    baseline_cost = sum(pair[1]["cost_usd"] for pair in priced_pairs) if priced_pairs else None
    token_delta = sum(token_deltas) if token_deltas else None
    cost_delta = (
        sum(baseline["cost_usd"] - record["cost_usd"] for record, baseline in priced_pairs)
        if priced_pairs
        else None
    )
    return {
        "tokens_saved": token_delta,
        "token_saving_pct": token_delta / baseline_tokens if token_delta is not None and baseline_tokens else None,
        "baseline_tokens": baseline_tokens if valid_pairs else None,
        "baseline_cost_usd": baseline_cost,
        "cost_saved_usd": cost_delta,
        "cost_saving_pct": cost_delta / baseline_cost if cost_delta is not None and baseline_cost else None,
        "paired_comparisons": len(valid_pairs),
        "paired_priced_comparisons": len(priced_pairs),
    }


def log_call(
    model: str,
    question_types: list,
    input_tokens: int = None,
    output_tokens: int = None,
    confidence: float = None,
    summary: str = "Decision completed",
    client: str = None,
    duration_ms: float = None,
    attempt_count: int = None,
    request_id: str = None,
    comparison: dict = None,
):
    """Append a completed provider response with explicit measurement provenance."""
    input_value = _token_value(input_tokens)
    output_value = _token_value(output_tokens)
    client_id, client_name = _detect_client_details(client)
    safe_confidence = confidence if _is_finite_number(confidence) and 0 <= confidence <= 1 else None
    duration_value = duration_ms if _is_finite_number(duration_ms) and duration_ms >= 0 else None
    attempts_value = attempt_count if isinstance(attempt_count, int) and attempt_count > 0 else None
    cost = (input_value / 1_000_000.0) * RATE_PER_MILLION_INPUT if input_value is not None else None
    entry = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "record_origin": "runtime",
        "client": client_id,
        "model": str(model) if model else None,
        "question_types": [str(value).lower() for value in question_types],
        "input_tokens": input_value,
        "output_tokens": output_value,
        "usage_source": "provider" if input_value is not None or output_value is not None else "unavailable",
        "confidence": round(safe_confidence, 4) if safe_confidence is not None else None,
        "summary": str(summary)[:240],
        "cost_usd": round(cost, 10) if cost is not None else None,
        "cost_source": "estimated_from_provider_usage" if cost is not None else None,
        "pricing_snapshot": {
            "provider": "TypeSafe AI",
            "input_usd_per_million": RATE_PER_MILLION_INPUT,
            "output_usd_per_million": 0.0,
            "source": "https://typesafe.ai/blog/introducing-system-one-models-and-jev",
            "checked_on": "2026-09-27",
        },
        "duration_ms": round(duration_value, 2) if duration_value is not None else None,
        "attempt_count": attempts_value,
        "request_id": str(request_id)[:160] if request_id else None,
    }
    if client_name:
        entry["client_name"] = client_name
    safe_comparison = _safe_comparison(comparison)
    if safe_comparison:
        entry["comparison"] = safe_comparison
    append_record(LEDGER_PATH, entry)


def _legacy_init_ledger():
    """Compatibility alias; never seed sample rows or rewrite existing history."""
    return init_ledger()


def _legacy_log_call(model, question_types, input_tokens, output_tokens, confidence, summary, client=None):
    """Compatibility alias routed through the same durable writer."""
    return log_call(
        model=model,
        question_types=question_types,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        confidence=confidence,
        summary=summary,
        client=client,
    )


def get_metrics(filter_client: str = None):
    """Return measured runtime facts; comparisons without an observed baseline stay unavailable."""
    all_records, ledger_state = load_ledger(LEDGER_PATH, create=True)

    all_runtime_records = [r for r in all_records if r.get("record_origin") == "runtime"]
    if filter_client and filter_client.lower() != "all":
        requested_client, _requested_name = _client_details(filter_client)
        requested_client = requested_client or "terminal"
        all_records = [r for r in all_records if _normalized_record_client(r) == requested_client]

    records = [r for r in all_records if r.get("record_origin") == "runtime"]
    unverified_records = [r for r in all_records if r.get("record_origin") != "runtime"]

    def reported_sum(field):
        values = [r.get(field) for r in records if _is_finite_number(r.get(field)) and r.get(field) >= 0]
        if values:
            return sum(values)
        return 0 if not records and not unverified_records else None

    complete_usage = [r for r in records if _is_finite_number(r.get("input_tokens")) and _is_finite_number(r.get("output_tokens"))]
    total_input = reported_sum("input_tokens")
    total_output = reported_sum("output_tokens")
    total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in complete_usage) if complete_usage else (0 if not records and not unverified_records else None)
    priced_records = [r for r in records if _is_finite_number(r.get("cost_usd")) and r.get("cost_usd") >= 0]
    total_cost = sum(r["cost_usd"] for r in priced_records) if priced_records else (0.0 if not records and not unverified_records else None)
    latencies = [r["duration_ms"] for r in records if _is_finite_number(r.get("duration_ms")) and r["duration_ms"] >= 0]
    confidences = [r["confidence"] for r in records if _is_finite_number(r.get("confidence")) and 0 <= r["confidence"] <= 1]

    type_counts = {}
    client_counts = {key: 0 for key in CLIENT_CONFIGS}
    client_counts["other"] = 0
    for record in records:
        client = _normalized_record_client(record)
        client_counts[client] = client_counts.get(client, 0) + 1
        for question_type in record.get("question_types", []):
            normalized = str(question_type).lower()
            type_counts[normalized] = type_counts.get(normalized, 0) + 1

    savings = _paired_savings(records, all_runtime_records)
    return {
        "total_calls": len(records),
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "usage_complete_calls": len(complete_usage),
        "usage_reported_calls": sum(1 for r in records if r.get("usage_source") == "provider"),
        "priced_calls": len(priced_records),
        "legacy_unverified_calls": len(unverified_records),
        "avg_confidence": sum(confidences) / len(confidences) if confidences else None,
        "confidence_samples": len(confidences),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "latency_samples": len(latencies),
        "type_counts": type_counts,
        "client_counts": client_counts,
        "records": records,
        "unverified_records": unverified_records,
        "all_records": all_records,
        "ledger_recovery_warning": ledger_state["has_recovery_artifacts"],
        **savings,
        "roi_multiplier": None,
        "speedup_factor": None,
        "time_saved_sec": None,
        "context_bloat_prevented": None,
        "throughput_ratio": None,
    }


def print_impact_card(client_filter: str = None):
    metrics = get_metrics(client_filter)
    label = client_filter if client_filter and client_filter.lower() != "all" else "همهٔ عامل‌ها"
    print(f"\nJev — گزارش مصرف واقعی ({label})")
    print("-" * 56)
    print(f"درخواست‌های اجراشده در این نسخه: {metrics['total_calls']}")
    print(f"ورودی گزارش‌شده از provider: {metrics['total_input'] if metrics['total_input'] is not None else 'ناموجود'}")
    print(f"خروجی گزارش‌شده از provider: {metrics['total_output'] if metrics['total_output'] is not None else 'ناموجود'}")
    print(f"هزینهٔ تخمینی Jev: {('$%.8f' % metrics['total_cost']) if metrics['total_cost'] is not None else 'ناموجود'} (محاسبه از ورودی ثبت‌شده و snapshot نرخ)")
    print(f"تأخیر p50 / p95: {metrics['latency_p50_ms'] if metrics['latency_p50_ms'] is not None else 'ناموجود'} / {metrics['latency_p95_ms'] if metrics['latency_p95_ms'] is not None else 'ناموجود'} ms (n={metrics['latency_samples']})")
    confidence = metrics["avg_confidence"]
    print(f"میانگین confidence صریح: {confidence * 100:.1f}% (n={metrics['confidence_samples']})" if confidence is not None else "میانگین confidence صریح: ناموجود")
    print(f"رکورد قدیمی بدون منشأ قابل‌تأیید: {metrics['legacy_unverified_calls']}")
    if metrics.get("tokens_saved") is not None:
        pct = (metrics["token_saving_pct"] * 100) if metrics.get("token_saving_pct") else 0
        print(f"🟢 صرفه‌جویی توکن اندازه‌گیری‌شده: {metrics['tokens_saved']:,} توکن ({pct:.1f}% کاهش | پایه: {metrics['paired_comparisons']} تصمیم هم‌ارز)")
        if metrics.get("cost_saved_usd") is not None:
            cost_pct = (metrics["cost_saving_pct"] * 100) if metrics.get("cost_saving_pct") else 0
            print(f"💰 صرفه‌جویی هزینه برآوردشده: ${metrics['cost_saved_usd']:.4f} ({cost_pct:.1f}% کاهش نسبت به مدل‌های مرجع)")
    else:
        print("مقایسهٔ صرفه‌جویی/ROI: ناموجود؛ baseline هم‌ارز و اندازه‌گیری‌شده تعریف نشده است.")
    print("نرخ Jev در snapshot فعلی: $0.042 / 1M input tokens؛ خروجی رایگان (منبع رسمی TypeSafe).")
    print("\nبرای پنل تصویری: jev panel --web\n")


def print_terminal_card(client_filter: str = None):
    metrics = get_metrics(client_filter)
    print_impact_card(client_filter)
    try:
        import jev_key_manager
        keys = jev_key_manager.list_keys()
        config = jev_key_manager.load_config()
        strategy = config.get("strategy", "unknown")
        print(f"🔑 وضعیت key pool ({strategy}):")
        for key in keys:
            active = " · active" if key.get("is_active_target") else ""
            next_key = " · next" if key.get("is_next") else ""
            print(f"  {key.get('name', 'unnamed')}: {key.get('masked', '****')} · {key.get('status', 'unknown')}{active}{next_key}")
    except Exception:
        print("وضعیت key pool در دسترس نیست.")
    print("\nتوزیع کلاینت‌ها:")
    total = metrics["total_calls"]
    for key, config in CLIENT_CONFIGS.items():
        count = metrics["client_counts"].get(key, 0)
        share = (count / total * 100) if total else 0
        print(f"  {config['name']}: {count} ({share:.1f}%)")
    print("\nرویدادهای اخیر:")
    for record in reversed(metrics["records"][-5:]):
        confidence = record.get("confidence")
        confidence_label = f"{confidence * 100:.0f}%" if _is_finite_number(confidence) else "ناموجود"
        summary = str(record.get("summary") or "ثبت بدون خلاصه")[:70]
        print(f"  {record.get('timestamp', '')} · {record.get('client', 'terminal')} · confidence {confidence_label} · {summary}")


def open_web_dashboard(port: int = 0):
    """Run the bilingual, read-only dashboard against the live usage ledger."""
    import jev_dashboard_server

    return jev_dashboard_server.serve_dashboard(port=port)


# Keep historic private entrypoints safe for any out-of-tree callers that may
# still import them: all reporting and dashboard paths use verified behavior.
_legacy_get_metrics = get_metrics
_legacy_print_impact_card = print_impact_card
_legacy_print_terminal_card = print_terminal_card
_legacy_open_web_dashboard = open_web_dashboard


if __name__ == "__main__":
    init_ledger()
    client_arg = None
    if len(sys.argv) > 1 and sys.argv[1] in ("--web", "-w"):
        open_web_dashboard()
    elif len(sys.argv) > 1 and sys.argv[1] in ("--impact", "-i"):
        print_impact_card()
    elif len(sys.argv) > 1 and sys.argv[1].startswith("--client="):
        client_arg = sys.argv[1].split("=", 1)[1]
        print_terminal_card(client_arg)
    elif len(sys.argv) > 2 and sys.argv[1] in ("--client", "-c"):
        client_arg = sys.argv[2]
        print_terminal_card(client_arg)
    else:
        print_terminal_card()
