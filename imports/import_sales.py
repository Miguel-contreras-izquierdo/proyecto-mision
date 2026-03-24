#!/usr/bin/env python3
"""
Importador de histórico de ventas.
Uso: python3 imports/import_sales.py imports/1.xlsx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

DATA_DIR = Path(__file__).parent.parent / "data"
SALES_FILE = DATA_DIR / "sales_history.json"

console = Console()

# Patrones de columnas en español/inglés que buscamos
COLUMN_PATTERNS = {
    "account": [
        "cliente", "cuenta", "account", "farmacia", "nombre cliente",
        "razon social", "razón social", "distribuidor",
    ],
    "period": [
        "mes", "periodo", "período", "fecha", "month", "date", "año mes",
        "año-mes", "periodo venta", "mes venta",
    ],
    "product": [
        "producto", "descripcion", "descripción", "product", "articulo",
        "artículo", "nombre producto", "desc producto",
    ],
    "sku": ["sku", "clave", "codigo", "código", "code", "clave producto"],
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


def detect_column(df_columns: list[str], field: str) -> str | None:
    """Try to find the column name for a given logical field."""
    cols_lower = {c.lower().strip(): c for c in df_columns}
    for pattern in COLUMN_PATTERNS[field]:
        if pattern in cols_lower:
            return cols_lower[pattern]
    return None


def show_file_preview(df: pd.DataFrame) -> None:
    console.print("\n[bold]Columnas encontradas en el archivo:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Columna original")
    table.add_column("Auto-detectada como")

    for i, col in enumerate(df.columns):
        detected = next(
            (field for field, pats in COLUMN_PATTERNS.items()
             if col.lower().strip() in pats),
            "—"
        )
        table.add_row(str(i + 1), str(col), detected)
    console.print(table)

    console.print(f"\n[dim]Primeras 3 filas de datos:[/dim]")
    console.print(df.head(3).to_string(index=False))
    console.print()


def build_mapping(df: pd.DataFrame) -> dict[str, str]:
    """Auto-detect column mapping, ask user to confirm/correct."""
    cols = list(df.columns)
    mapping = {}

    for field in COLUMN_PATTERNS:
        detected = detect_column(cols, field)
        mapping[field] = detected

    console.print("\n[bold]Mapeo de columnas detectado:[/bold]")
    required = {"account", "period", "amount"}

    for field, col in mapping.items():
        label = f"[bold]{field}[/bold]" if field in required else field
        status = f"[green]{col}[/green]" if col else "[yellow]No detectada[/yellow]"
        console.print(f"  {label} → {status}")

    console.print()
    if not Confirm.ask("¿El mapeo es correcto? (puedes editarlo si no)"):
        for field in COLUMN_PATTERNS:
            current = mapping.get(field) or "ninguna"
            options = ", ".join(cols)
            console.print(f"\nColumnas disponibles: [dim]{options}[/dim]")
            val = Prompt.ask(
                f"Columna para [bold]{field}[/bold] (Enter para dejar '{current}')",
                default=mapping.get(field) or "",
            )
            if val.strip():
                mapping[field] = val.strip()

    return mapping


def normalize_period(val) -> str:
    """Normalize period to YYYY-MM format."""
    if pd.isna(val):
        return "desconocido"
    try:
        ts = pd.to_datetime(val)
        return ts.strftime("%Y-%m")
    except Exception:
        return str(val).strip()


def process_dataframe(df: pd.DataFrame, filename: str) -> dict:
    """
    Process an already-loaded DataFrame and save records to sales_history.json.
    Returns a summary dict with keys: records, errors, unique_accounts, periods, total_amount.
    Raises ValueError if required columns are missing or no valid records found.
    """
    df.columns = [str(c).strip() for c in df.columns]
    mapping = {field: detect_column(list(df.columns), field) for field in COLUMN_PATTERNS}

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
    existing = []
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
        "unique_accounts": df_rec["account_name"].nunique(),
        "periods": periods,
        "total_amount": df_rec["amount"].sum(),
        "mapping": mapping,
    }


def import_file(filepath: str) -> None:
    path = Path(filepath)
    if not path.exists():
        console.print(f"[red]Archivo no encontrado: {path}[/red]")
        sys.exit(1)

    console.print(f"\n[bold green]Leyendo:[/bold green] {path.name}")
    df = pd.read_excel(path, dtype=str)
    show_file_preview(df)
    mapping = build_mapping(df)

    missing = [f for f in ("account", "period", "amount") if not mapping.get(f)]
    if missing:
        console.print(f"[red]Faltan columnas requeridas: {missing}. Importación cancelada.[/red]")
        sys.exit(1)

    # Apply confirmed mapping and reuse process_dataframe
    df.columns = [str(c).strip() for c in df.columns]
    try:
        summary = process_dataframe(df, path.name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    periods = summary["periods"]
    console.print(f"\n[bold green]✓ Importación exitosa[/bold green]")
    console.print(f"  Registros importados : [bold]{summary['records']:,}[/bold]")
    console.print(f"  Errores omitidos     : {summary['errors']}")
    console.print(f"  Cuentas únicas       : [bold]{summary['unique_accounts']}[/bold]")
    console.print(f"  Período              : {periods[0]} → {periods[-1]}")
    console.print(f"  Venta total          : [bold]${summary['total_amount']:,.0f}[/bold]")
    console.print(f"\n  Guardado en: [dim]{SALES_FILE}[/dim]")
    console.print("\n[dim]Ya puedes abrir el copiloto (python3 main.py) y pedir análisis de ventas.[/dim]\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Uso: python3 imports/import_sales.py imports/TU_ARCHIVO.xlsx[/yellow]")
        sys.exit(1)
    import_file(sys.argv[1])
