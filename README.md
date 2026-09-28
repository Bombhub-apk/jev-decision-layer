# ⚡ Jev Decision Layer & Reactive Telemetry Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)]()
[![Optimization](https://img.shields.io/badge/Agents-Antigravity%20%7C%20Codex%20%7C%20Claude-teal.svg)]()

> High-speed deterministic **System One** decision layer, token optimization telemetry, multi-key rotation hub, and live glassmorphic observability dashboard for AI agent swarms (**Google Antigravity**, **OpenAI Codex**, and **Claude Code**).

---

## 🌟 Key Capabilities

- ⚡ **Ultra-Fast Cognitive Decisions**: Offloads bounded categorical judgments, architectural choices, and tool routing to TypeSafe Jev with sub-250ms latency.
- 💰 **Measured Token & Cost Savings**: Saves **74.7% – 90%+** in tokens and **99.8%** in costs compared to invoking general-purpose foundation models ($0.042 / 1M input tokens vs $3.00–$15.00 / 1M tokens; output tokens are free).
- 🔑 **Multi-Key Pool Hub**:
  - Load balancing across multiple API keys with configurable strategies (`round_robin` or `single`).
  - Automatic failover handling with strict status distinction between `auth_failed` (401/403) and `rate_limited` (429).
  - Web UI modal and CLI commands for adding, editing, toggling, and monitoring keys.
- 📊 **Live Reactive Glassmorphic Dashboard**:
  - Live background polling (3s heartbeat) with zero layout shifts.
  - Animated smooth number roll-ups and glowing card borders.
  - Native bilingual typography in Persian (`Vazirmatn`, `Estedad`) and English (`Outfit`, `JetBrains Mono`) with instant LTR/RTL switching.
  - Granular agent breakdown badges (**Antigravity**, **Codex**, **Claude Code**, and **Terminal CLI**).
- 🛡️ **Atomic & Resilient Ledger Store**:
  - Windows file locking (`msvcrt.locking`) preventing concurrent write collisions.
  - Automatic backup (`.bak`) and corruption quarantine (`.corrupt-*`).
  - Provenance tracking with calibrated paired comparison verification.

---

## 🚀 Quick Start

### Installation

#### Windows (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/Bombhub-apk/jev-decision-layer.git
cd jev-decision-layer

# Run the installer (sets up requirements and PATH)
.\install.ps1
```

#### Linux / macOS
```bash
# Clone the repository
git clone https://github.com/Bombhub-apk/jev-decision-layer.git
cd jev-decision-layer

chmod +x install.sh jev.sh
./install.sh
```

---

## 🔑 Configuration & API Keys

Add your first API key using the CLI:

```bash
# Add a key to the pool
jev key add primary typesafe_your_api_key_here

# Check key status
jev key list

# Switch rotation strategy (round_robin or single)
jev key strategy round_robin
```

Or configure via `jev_keys.json` (see `jev_keys.example.json`):

```json
{
  "strategy": "round_robin",
  "active_key_name": "primary",
  "current_index": 0,
  "keys": [
    {
      "name": "primary",
      "key": "typesafe_your_api_key_here",
      "status": "active"
    }
  ]
}
```

---

## 💻 CLI Commands

### 1. Run Live Test
Test connection, latency, and Softmax probability calibration:
```bash
jev test
```

### 2. View Telemetry & Savings in Terminal
Display provider-verified token usage, p50/p95 latency, and ROI:
```bash
jev impact
```

### 3. Launch the Live Web Dashboard
Start the local loopback server and open the reactive glassmorphism dashboard:
```bash
jev panel --web
# or
jev stats --web
```

### 4. Direct Decisions
Invoke a single discrete decision directly from terminal or scripts:
```bash
jev decide "Which UI framework is best for 3D web visualizations?" --choices "Three.js,Babylon.js,A-Frame"
```

---

## 🧩 Multi-Agent Integration

### Google Antigravity & OpenAI Codex
Export the client identifier in your workflow or launch scripts:

```bash
# Linux / macOS
export JEV_CLIENT="antigravity"

# Windows PowerShell
$env:JEV_CLIENT = "antigravity"
```

The system automatically attributes decisions, token reductions, and latency metrics to the active agent in the dashboard.

---

## 📂 Repository Structure

```text
jev-decision-layer/
├── bin/
│   ├── jev_cli.py              # CLI engine & subcommands
│   ├── jev_key_manager.py      # Multi-key rotation pool & failover
│   ├── jev_dashboard_server.py  # Loopback HTTP server & REST API
│   ├── jev_dashboard_ui.py      # Glassmorphic single-page app
│   ├── jev_ledger_store.py     # Atomic locking & persistent storage
│   ├── jev_tracker.py          # Metrics, ROI, & provenance engine
│   └── assets/fonts/           # Offline Vazirmatn, Estedad, & Outfit
├── jev_dashboard.html          # Standalone offline dashboard
├── jev_keys.example.json       # Sanitized key pool configuration template
├── requirements.txt            # Python dependencies (typesafe-sdk, pyyaml)
├── install.ps1                 # Windows one-click installer
├── install.sh                  # Linux/macOS one-click installer
├── jev.cmd                     # Windows terminal wrapper
├── jev.sh                      # Unix shell wrapper
├── LICENSE                     # MIT License
└── README.md                   # Documentation
```

---

## 🛡️ Security & Privacy

- **Zero Credential Leaks**: Secret keys are masked in CLI listings and web UI (`apikey_2...fdfa42`).
- **Loopback Protection**: The dashboard server strictly binds to local loopback (`127.0.0.1` / `::1`) with origin validation.
- **Git Protection**: `jev_keys.json` and `jev_usage_ledger.json` are excluded via `.gitignore` to prevent committing secrets to public source control.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Copyright (c) 2026 Ethan Carter / Bombhub-apk.
