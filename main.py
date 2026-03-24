#!/usr/bin/env python3
"""
Copiloto de Productividad Ejecutiva
Gestión inteligente de cuentas, pendientes y oportunidades de venta.
"""
from rich.console import Console
from rich.panel import Panel

from assistant.agent import AccountCopilot

console = Console()

WELCOME = """\
[bold]Copiloto de Productividad Ejecutiva[/bold]
[dim]Powered by Claude Opus 4.6 · Memoria persistente entre sesiones[/dim]

Te ayudo a:
  • Controlar el estado de tus cuentas y contactos clave
  • Recordarte pendientes críticos y vencidos
  • Preparar briefings antes de reuniones
  • Identificar oportunidades de crecimiento en tu portafolio

[dim]Comandos: escribe con naturalidad · 'salir' para terminar · Ctrl+C para interrumpir[/dim]\
"""


def main() -> None:
    console.print()
    console.print(Panel(WELCOME, border_style="green", padding=(1, 2)))
    console.print()

    copilot = AccountCopilot()

    # Kick off with a dashboard briefing automatically
    console.print("[dim]Cargando tu dashboard...[/dim]\n")
    copilot.chat(
        "Buenos días. Carga el dashboard ejecutivo y dame el briefing del día: "
        "cuentas en riesgo, pendientes críticos o vencidos, y las oportunidades "
        "más relevantes del pipeline."
    )
    console.print()

    try:
        while True:
            try:
                user_input = console.input("[bold blue]Tú[/bold blue]: ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in ("salir", "exit", "quit", "q"):
                console.print("\n[dim]Hasta luego. Toda la información ha quedado guardada.[/dim]")
                break

            console.print()
            copilot.chat(user_input)
            console.print()

    except KeyboardInterrupt:
        console.print("\n\n[dim]Hasta luego. Toda la información ha quedado guardada.[/dim]")


if __name__ == "__main__":
    main()
