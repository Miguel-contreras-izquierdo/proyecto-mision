"""Sales history analysis functions using the imported sales data."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
SALES_FILE = DATA_DIR / "sales_history.json"


def _load_sales() -> list[dict]:
    if not SALES_FILE.exists():
        return []
    try:
        return json.loads(SALES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _group_by(records: list[dict], key: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r.get(key, "")].append(r)
    return dict(groups)


# ---------------------------------------------------------------------------
# Public analysis functions
# ---------------------------------------------------------------------------

def analyze_account_sales(account_name: str) -> dict[str, Any]:
    """Full sales breakdown for a single account."""
    records = _load_sales()
    if not records:
        return {"error": "No hay histórico de ventas importado. Usa import_sales.py primero."}

    name_lower = account_name.lower()
    account_records = [
        r for r in records
        if name_lower in r.get("account_name", "").lower()
    ]
    if not account_records:
        return {"error": f"No hay ventas registradas para '{account_name}'"}

    matched_name = account_records[0]["account_name"]

    # By period
    by_period: dict[str, float] = defaultdict(float)
    by_period_units: dict[str, int] = defaultdict(int)
    for r in account_records:
        by_period[r["period"]] += r.get("amount", 0)
        by_period_units[r["period"]] += r.get("units", 0)

    sorted_periods = sorted(by_period.keys())

    # Trend: compare last period vs previous
    trend_pct = None
    if len(sorted_periods) >= 2:
        last = by_period[sorted_periods[-1]]
        prev = by_period[sorted_periods[-2]]
        if prev > 0:
            trend_pct = round((last - prev) / prev * 100, 1)

    # By product
    by_product: dict[str, float] = defaultdict(float)
    for r in account_records:
        prod = r.get("product") or r.get("sku") or "Sin descripción"
        by_product[prod] += r.get("amount", 0)

    top_products = sorted(by_product.items(), key=lambda x: x[1], reverse=True)[:10]

    # By brand
    by_brand: dict[str, float] = defaultdict(float)
    for r in account_records:
        brand = r.get("brand") or "Sin marca"
        by_brand[brand] += r.get("amount", 0)

    return {
        "account_name": matched_name,
        "total_records": len(account_records),
        "total_amount": round(sum(r.get("amount", 0) for r in account_records), 2),
        "total_units": sum(r.get("units", 0) for r in account_records),
        "periods_covered": sorted_periods,
        "sales_by_period": {p: round(by_period[p], 2) for p in sorted_periods},
        "units_by_period": dict(by_period_units),
        "latest_period": sorted_periods[-1] if sorted_periods else None,
        "latest_amount": round(by_period[sorted_periods[-1]], 2) if sorted_periods else 0,
        "trend_vs_previous_period_pct": trend_pct,
        "top_products": [{"product": p, "amount": round(a, 2)} for p, a in top_products],
        "sales_by_brand": {b: round(v, 2) for b, v in sorted(by_brand.items(), key=lambda x: x[1], reverse=True)},
    }


def get_portfolio_trends() -> dict[str, Any]:
    """Period-over-period comparison across all accounts."""
    records = _load_sales()
    if not records:
        return {"error": "No hay histórico de ventas importado."}

    by_period: dict[str, float] = defaultdict(float)
    by_account_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for r in records:
        p = r["period"]
        a = r.get("account_name", "")
        amt = r.get("amount", 0)
        by_period[p] += amt
        by_account_period[a][p] += amt

    sorted_periods = sorted(by_period.keys())

    # MoM / YoY trend
    trend = []
    for i, p in enumerate(sorted_periods):
        entry: dict[str, Any] = {"period": p, "total": round(by_period[p], 2)}
        if i > 0:
            prev = by_period[sorted_periods[i - 1]]
            entry["change_pct"] = round((by_period[p] - prev) / prev * 100, 1) if prev else None
        trend.append(entry)

    # Top accounts last period
    last_period = sorted_periods[-1] if sorted_periods else None
    top_accounts = []
    if last_period:
        top_accounts = sorted(
            [{"account": a, "amount": round(v.get(last_period, 0), 2)}
             for a, v in by_account_period.items()],
            key=lambda x: x["amount"], reverse=True
        )[:10]

    return {
        "periods": sorted_periods,
        "trend": trend,
        "last_period": last_period,
        "top_accounts_last_period": top_accounts,
        "total_accounts_with_sales": len(by_account_period),
    }


def get_at_risk_accounts(decline_threshold_pct: float = -20.0) -> dict[str, Any]:
    """Accounts with declining sales vs previous period."""
    records = _load_sales()
    if not records:
        return {"error": "No hay histórico de ventas importado."}

    by_account_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        by_account_period[r.get("account_name", "")][r["period"]] += r.get("amount", 0)

    at_risk = []
    growing = []

    for account, periods_data in by_account_period.items():
        sorted_p = sorted(periods_data.keys())
        if len(sorted_p) < 2:
            continue
        last = periods_data[sorted_p[-1]]
        prev = periods_data[sorted_p[-2]]
        if prev == 0:
            continue
        change_pct = (last - prev) / prev * 100
        entry = {
            "account": account,
            "last_period": sorted_p[-1],
            "last_amount": round(last, 2),
            "prev_amount": round(prev, 2),
            "change_pct": round(change_pct, 1),
        }
        if change_pct <= decline_threshold_pct:
            at_risk.append(entry)
        elif change_pct >= 10:
            growing.append(entry)

    at_risk.sort(key=lambda x: x["change_pct"])
    growing.sort(key=lambda x: x["change_pct"], reverse=True)

    return {
        "decline_threshold_pct": decline_threshold_pct,
        "at_risk_count": len(at_risk),
        "at_risk_accounts": at_risk[:15],
        "growing_count": len(growing),
        "growing_accounts": growing[:10],
    }


def get_growth_opportunities() -> dict[str, Any]:
    """Accounts/brands with growth potential based on historical patterns."""
    records = _load_sales()
    if not records:
        return {"error": "No hay histórico de ventas importado."}

    # Brands with low penetration in high-value accounts
    by_account: dict[str, float] = defaultdict(float)
    account_brands: dict[str, set] = defaultdict(set)
    brand_totals: dict[str, float] = defaultdict(float)

    for r in records:
        acc = r.get("account_name", "")
        brand = r.get("brand") or "Sin marca"
        amt = r.get("amount", 0)
        by_account[acc] += amt
        account_brands[acc].add(brand)
        brand_totals[brand] += amt

    all_brands = set(brand_totals.keys()) - {"Sin marca", ""}
    top_accounts = sorted(by_account.items(), key=lambda x: x[1], reverse=True)[:20]

    gaps = []
    for acc, total in top_accounts:
        missing_brands = all_brands - account_brands.get(acc, set())
        if missing_brands:
            gaps.append({
                "account": acc,
                "account_total": round(total, 2),
                "brands_active": sorted(account_brands.get(acc, set())),
                "brands_missing": sorted(missing_brands),
                "cross_sell_opportunities": len(missing_brands),
            })

    # Accounts with consistent growth (3+ periods)
    by_account_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        by_account_period[r.get("account_name", "")][r["period"]] += r.get("amount", 0)

    consistent_growth = []
    for acc, pdata in by_account_period.items():
        sp = sorted(pdata.keys())
        if len(sp) < 3:
            continue
        last3 = [pdata[p] for p in sp[-3:]]
        if last3[0] < last3[1] < last3[2]:
            growth_rate = (last3[2] - last3[0]) / last3[0] * 100 if last3[0] else 0
            consistent_growth.append({
                "account": acc,
                "growth_pct_3_periods": round(growth_rate, 1),
                "last_amount": round(last3[2], 2),
            })
    consistent_growth.sort(key=lambda x: x["growth_pct_3_periods"], reverse=True)

    return {
        "cross_sell_gaps": gaps[:10],
        "consistent_growth_accounts": consistent_growth[:10],
        "total_brands": len(all_brands),
        "top_brands_by_revenue": [
            {"brand": b, "total": round(v, 2)}
            for b, v in sorted(brand_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
    }
