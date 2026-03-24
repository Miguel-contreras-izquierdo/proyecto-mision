# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Copiloto de Productividad Ejecutiva** — An AI-powered personal assistant for sales executives to manage their account portfolio. Uses Claude Opus 4.6 with adaptive thinking, streaming, and tool use.

Core capabilities: account management, pending/follow-up tracking, meeting briefings, upsell/cross-sell opportunity identification.

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run the copilot (interactive CLI)
python3 main.py

# Dashboard visual (Streamlit)
streamlit run dashboard.py

# Import sales data from Excel
python3 imports/import_sales.py ruta/al/archivo.xlsx
```

## Architecture

```
main.py                   # Entry point: welcome screen + REPL
assistant/
  agent.py                # AccountCopilot class — streaming agentic loop
  tools.py                # Tool schemas (TOOLS list) + execute_tool() dispatcher + all handlers
  storage.py              # JSON persistence helpers (load/save for accounts, pendings, notes, opps)
  sales_analysis.py       # Portfolio analytics: sales history, trends, at-risk, growth opportunities
dashboard.py              # Streamlit dashboard — 5 sections (Summary, Sales, Accounts, Pendings, Opps)
imports/
  import_sales.py         # Excel importer with flexible Spanish/English column detection
data/                     # Runtime data (gitignored)
  accounts.json           # {id, name, contact_name, contact_role, contact_email, contact_phone, segment, status, value, notes[], created_at, updated_at}
  pendings.json           # {id, account_id, description, priority, due_date, status, created_at, completed_at}
  notes.json              # {id, account_id, content, type, created_at}
  opportunities.json      # {id, account_id, title, type, value, probability, stage, created_at}
  sales_history.json      # {account_id, date, product, brand, amount, units} (populated by importer)
```

## Key Design Decisions

- **Agentic loop**: `agent.py` uses `client.messages.stream()` + `stream.get_final_message()` in a `while True` loop that continues until `stop_reason != "tool_use"`.
- **Adaptive thinking**: `thinking={"type": "adaptive"}` is enabled on every call so Claude reasons deeply on complex prioritization/decision requests without a fixed budget.
- **Persistent memory**: All data lives in JSON files under `data/`. The session starts with an automatic `get_executive_dashboard` call to inject current state into context.
- **Tool execution**: All 13 tools are client-side Python functions. `execute_tool()` in `tools.py` dispatches by name and returns JSON strings.
- **Python 3.9 compatibility**: Use `from __future__ import annotations` + `Optional[T]` instead of `T | None`.

## Tool Reference

| Tool | Purpose |
|------|---------|
| `create_or_update_account` | Register/update client account |
| `list_accounts` | Portfolio overview with filters |
| `add_pending` | Add follow-up action to an account |
| `list_pendings` | View pending items (all or per account) |
| `complete_pending` | Mark pending as done |
| `add_note` | Log interaction to account timeline |
| `register_opportunity` | Track upsell/cross-sell opportunity |
| `get_account_summary` | Full briefing for one account |
| `get_executive_dashboard` | Full portfolio snapshot with alerts |
| `analyze_account_sales` | Historical sales breakdown by period/product/brand for one account |
| `get_portfolio_trends` | Cross-account trends with MoM changes |
| `get_at_risk_accounts` | Detect accounts with declining sales |
| `get_growth_opportunities` | Identify cross-sell gaps and consistent growth accounts |

## Adding New Tools

1. Add the JSON schema entry to `TOOLS` list in `assistant/tools.py`
2. Add the handler function `_my_tool(...)` in the same file
3. Register it in the `handlers` dict inside `execute_tool()`
