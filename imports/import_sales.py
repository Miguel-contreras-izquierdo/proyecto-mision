#!/usr/bin/env python3
"""
Importador de histórico de ventas (CLI).
Uso: python3 imports/import_sales.py imports/1.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from imports.data_processing import (
    COLUMN_PATTERNS, detect_column, detect_wide_format,
    get_wide_format_info, process_dataframe,
)

console = Console()


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
    mapping = {field: detect_column(cols, field) for field in COLUMN_PATTERNS}

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


def import_file(filepath: str) -> None:
    path = Path(filepath)
    if not path.exists():
        console.print(f"[red]Archivo no encontrado: {path}[/red]")
        sys.exit(1)

    console.print(f"\n[bold green]Leyendo:[/bold green] {path.name}")
    df = pd.read_excel(path, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    is_wide = detect_wide_format(df)
    if is_wide:
        info = get_wide_format_info(df)
        console.print(f"[bold cyan]Formato ancho detectado[/bold cyan]")
        console.print(f"  Columnas fijas  : {', '.join(info['id_cols'])}")
        console.print(f"  Periodos        : {len(info['month_cols'])} columnas")
        if info["agg_cols"]:
            console.print(f"  Omitidas (YTD/MAT): {', '.join(info['agg_cols'])}")
    else:
        show_file_preview(df)
        mapping = build_mapping(df)
        missing = [f for f in ("account", "period", "amount") if not mapping.get(f)]
        if missing:
            console.print(f"[red]Faltan columnas requeridas: {missing}. Importación cancelada.[/red]")
            sys.exit(1)
        # Apply manual mapping
        rename = {v: k for k, v in mapping.items() if v}
        df = df.rename(columns=rename)

    try:
        summary = process_dataframe(df, path.name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    periods = summary["periods"]
    fmt = "ancho" if summary.get("wide_format") else "largo"
    console.print(f"\n[bold green]✓ Importación exitosa[/bold green] ([dim]{fmt}[/dim])")
    console.print(f"  Registros importados : [bold]{summary['records']:,}[/bold]")
    console.print(f"  Errores omitidos     : {summary['errors']}")
    console.print(f"  Cuentas únicas       : [bold]{summary['unique_accounts']}[/bold]")
    console.print(f"  Período              : {periods[0]} → {periods[-1]}")
    console.print(f"  Venta total          : [bold]${summary['total_amount']:,.0f}[/bold]")
    console.print("\n[dim]Ya puedes abrir el copiloto (python3 main.py) y pedir análisis de ventas.[/dim]\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Uso: python3 imports/import_sales.py imports/TU_ARCHIVO.xlsx[/yellow]")
        sys.exit(1)
    import_file(sys.argv[1])
