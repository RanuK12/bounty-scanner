# 🎯 Bounty Scanner

Multi-source bounty scanner for developers. Scan GitHub, Algora, Opire and Warpspeed for open bounties — all from your CLI.

## Features

- 🔍 Scan **4 sources**: GitHub Issues, Algora, Opire, Warpspeed
- 📊 Clean table output with bounty amounts, status, and links
- 🎨 Colored terminal output
- 🌐 Proxy/stealth support for rate-limited sources
- 🐍 Pure Python, no external services

## Quick Start

```bash
pip install -r requirements.txt
python bounty_scanner.py
```

## Usage

```bash
# Scan all sources
python bounty_scanner.py

# Scan specific sources
python bounty_scanner.py --sources github,algora

# Filter by minimum bounty
python bounty_scanner.py --min-bounty 100

# Filter by language/tag
python bounty_scanner.py --tag python

# Output as JSON
python bounty_scanner.py --format json

# Use stealth browser for blocked sources (requires Camofox)
python bounty_scanner.py --stealth
```

## Output

| Source    | Title                    | Bounty | Link                        |
|-----------|--------------------------|--------|-----------------------------|
| GitHub    | Fix admin role bug       | $780   | https://github.com/...      |
| Algora    | Add dark mode toggle     | $500   | https://app.algora.io/...   |
| Opire      | Refactor auth middleware  | $250   | https://opire.dev/...       |
| Warpspeed | Optimize DB queries      | $300   | https://warpspeed.com/...   |

## Stack

- Python 3.10+
- `requests`, `beautifulsoup4`, `rich` (terminal UI)
- No external APIs — scrapes directly from public pages

---

Built by [Ranuk IT Solutions](https://ranuk.dev) — tools for developers who ship.
