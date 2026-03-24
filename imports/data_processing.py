"""
Pure data processing functions for sales imports.
No CLI dependencies (rich) — safe to import in Streamlit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
SALES_FILE = DATA_DIR / "sales_history.json"

# ---------------------------------------------------------------------------
# Column patterns
# ---------------------------------------------------------------------------

COLUMN_PATTERNS: dict[str, list[str]] = {
    "account": [
        "cliente", "cuenta", "account", "farmacia", "nombre cliente",
        "razon social", "razón social", "cadena", "canal", "cliente cadena",
        "distribuidor",
    ],
    "period": [
        "mes", "periodo", "período", "fecha", "month", "date", "año mes",
        "año-mes", "periodo venta", "mes venta",
    ],
    "product": [
        "producto", "descripcion", "descripción", "product", "articulo",
        "artículo", "nombre producto", "desc producto", "descripcion sku",
        "nombre sku",
    ],
    "sku": [
        "sku", "clave", "codigo", "código", "code", "clave producto",
        "ean", "codigo ean", "código ean", "gtin", "sap",
    ],
    "brand": [
        "marca", "laboratorio", "lab", "brand", "fabricante", "linea", "línea",
    ],
    "units": [
        "unidades", "cantidad", "piezas", "units", "qty", "quantity",
        "cajas", "bultos",
    ],
    "amount": [
        "venta", "importe", "monto", "total", "amount", "valor", "ventas",
        "precio", "facturacion", "facturación", "ingreso",
    ],
    "rep": [
        "visitador", "representante", "vendedor", "rep", "asesor",
        "promotor", "agente",
    ],
}

# ---------------------------------------------------------------------------
# Wide-format helpers
# ---------------------------------------------------------------------------

_MONTH_NAMES_ES = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

_MES_MAP = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04",
    "may": "05", "jun": "06", "jul": "07", "ago": "08",
    "sep": "09", "oct": "10", "nov": "11", "dic": "12",
}


def detect_column(df_columns: list[str], field: str) -> Optional[str]:
    """Return the original column name matching a logical field, or None."""
    cols_lower = {c.lower().strip(): c for c in df_columns}
    for pattern in COLUMN_PATTERNS[field]:
        if pattern in cols_lower:
            return cols_lower[pattern]
    return None


def _is_period_col(col: str) -> bool:
    """Return True if the column name looks like a time period or YTD/MAT."""
    c = col.lower().strip()
    if c in ("ytd", "mat"):
        return True
    if re.match(r"\d{4}-\d{1,2}$", c):
        return True
    if re.match(r"\d{1,2}[-/]\d{2,4}$", c):
        return True
    if any(c.startswith(m) for m in _MONTH_NAMES_ES):
        return True
    return False


def detect_wide_format(df: pd.DataFrame) -> bool:
    """Return True if the DataFrame looks like a wide (pivoted) sales file."""
    period_cols = [c for c in df.columns if _is_period_col(str(c))]
    return len(period_cols) >= 3


def get_wide_format_info(df: pd.DataFrame) -> dict:
    """Return metadata about wide-format columns."""
    period_cols = [c for c in df.columns if _is_period_col(str(c))]
    agg_cols = [c for c in period_cols if str(c).lower().strip() in ("ytd", "mat")]
    month_cols = [c for c in period_cols if str(c).lower().strip() not in ("ytd", "mat")]
    id_cols = [c for c in df.columns if not _is_period_col(str(c))]
    return {"id_cols": id_cols, "month_cols": month_cols, "agg_cols": agg_cols}


def melt_wide_format(df: pd.DataFrame) -> pd.DataFrame:
    """Unpivot a wide-format DataFrame into long format, dropping YTD/MAT columns."""
    info = get_wide_format_info(df)
    return df.melt(
        id_vars=info["id_cols"],
        value_vars=info["month_cols"],
        var_name="period",
        value_name="amount",
    )


def normalize_period(val) -> str:
    """Normalize period to YYYY-MM, handling Spanish month names."""
    if pd.isna(val):
        return "desconocido"
    s = str(val).strip()
    sl = s.lower()

    m = re.match(r"([a-záéíóú]+)[-/\s](\d{2,4})$", sl)
    if m:
        mes_raw, year_raw = m.group(1)[:3], m.group(2)
        year = f"20{year_raw}" if len(year_raw) == 2 else year_raw
        num = _MES_MAP.get(mes_raw)
        if num:
            return f"{year}-{num}"

    try:
        ts = pd.to_datetime(s)
        return ts.strftime("%Y-%m")
    except Exception:
        return s


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

def process_dataframe(df: pd.DataFrame, filename: str) -> dict:
    """
    Process a DataFrame and save records to data/sales_history.json.
    Automatically detects and handles wide format.
    Returns summary dict. Raises ValueError on missing required columns.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    wide = detect_wide_format(df)
    if wide:
        df = melt_wide_format(df)

    mapping = {field: detect_column(list(df.columns), field) for field in COLUMN_PATTERNS}

    if wide:
        if not mapping.get("period"):
            mapping["period"] = "period"
        if not mapping.get("amount"):
            mapping["amount"] = "amount"

    missing = [f for f in ("account", "period", "amount") if not mapping.get(f)]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")

    records = []
    errors = 0
    for _, row in df.iterrows():
        try:
            amount_raw = str(row.get(mapping["amount"], "0")).replace(",", "").replace("$", "").strip()
            amount = float(amount_raw) if amount_raw and amount_raw not in ("nan", "") else 0.0

            units_raw = row.get(mapping.get("units", ""), "") if mapping.get("units") else ""
            units = int(float(str(units_raw).replace(",", "").strip())) if str(units_raw) not in ("", "nan") else 0

            record = {
                "account_name": str(row.get(mapping["account"], "")).strip(),
                "period":       normalize_period(row.get(mapping["period"])),
                "product":      str(row.get(mapping.get("product", ""), "")).strip() if mapping.get("product") else "",
                "sku":          str(row.get(mapping.get("sku", ""), "")).strip() if mapping.get("sku") else "",
                "brand":        str(row.get(mapping.get("brand", ""), "")).strip() if mapping.get("brand") else "",
                "units":        units,
                "amount":       amount,
                "rep":          str(row.get(mapping.get("rep", ""), "")).strip() if mapping.get("rep") else "",
            }
            if record["account_name"] and record["account_name"] != "nan":
                records.append(record)
        except Exception:
            errors += 1

    if not records:
        raise ValueError("No se encontraron registros válidos en el archivo.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if SALES_FILE.exists():
        existing = json.loads(SALES_FILE.read_text(encoding="utf-8"))

    existing = [r for r in existing if r.get("_source") != filename]
    for r in records:
        r["_source"] = filename
    existing.extend(records)
    SALES_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    df_rec = pd.DataFrame(records)
    periods = sorted(df_rec["period"].unique().tolist())
    return {
        "records": len(records),
        "errors": errors,
        "unique_accounts": int(df_rec["account_name"].nunique()),
        "periods": periods,
        "total_amount": float(df_rec["amount"].sum()),
        "mapping": mapping,
        "wide_format": wide,
    }
