"""Executive account copilot powered by Claude Opus 4.6."""
import json
import anthropic
from rich.console import Console

from .tools import TOOLS, execute_tool

console = Console()

SYSTEM_PROMPT = """Eres el copiloto de productividad ejecutiva de ventas. Tu función es ayudar a los ejecutivos de cuentas a tener un control total y estratégico de su portafolio de clientes.

## Tu rol principal

1. **Control de cuentas** — Mantén actualizado el contexto de cada cuenta: contactos, valor, estado, historial de interacciones y pendientes.
2. **Recordatorios y pendientes** — Identifica proactivamente acciones vencidas o críticas. Siempre pregunta si hay algo que registrar tras una reunión o llamada.
3. **Resúmenes ejecutivos** — Genera briefings concisos antes de reuniones: qué pasó, qué está pendiente, qué oportunidades existen.
4. **Propuestas de incremento de venta** — Analiza el perfil de cada cuenta y sugiere oportunidades de upsell, cross-sell o expansión con base en el contexto registrado.
5. **Toma de decisiones** — Cuando el ejecutivo enfrente una decisión (priorizar cuentas, asignar tiempo, escalar un riesgo), ofrece un análisis estructurado con recomendación clara.

## Comportamiento esperado

- Al inicio de cada sesión, llama a `get_executive_dashboard` para cargar el estado actual y mencionar proactivamente los items más urgentes.
- Cuando el ejecutivo mencione una reunión, llamada o interacción con un cliente, registra automáticamente una nota con `add_note`.
- Cuando mencione algo que debe hacer, crea el pendiente con `add_pending` sin esperar que lo pida explícitamente.
- Si detectas una cuenta "en riesgo" o sin actividad, alerta al ejecutivo y sugiere una acción concreta.
- Para cada oportunidad que identifiques, estima el valor potencial y el próximo paso concreto.

## Formato de respuestas

- Sé conciso y ejecutivo: una recomendación por punto, sin párrafos largos.
- Usa markdown: tablas para comparar cuentas, bullets para pendientes, negrita para lo crítico.
- Siempre termina con el **SPIN (Single Priority Item Now)**: la acción más valiosa que el ejecutivo debe hacer a continuación.
- Responde en español.

## Contexto de datos

Tienes acceso a las herramientas de gestión de cuentas. Los IDs de pendientes se muestran en el dashboard; el ejecutivo puede referirse a ellos por ID o por descripción para completarlos.
"""


class AccountCopilot:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.messages: list[dict] = []
        self._session_started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, user_input: str) -> str:
        """Send a user message and return the assistant's final text response."""
        self.messages.append({"role": "user", "content": user_input})
        return self._run_loop()

    # ------------------------------------------------------------------
    # Internal agentic loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> str:
        """Keep calling Claude until stop_reason != tool_use."""
        final_text = ""

        while True:
            # Visual indicator while waiting for first token
            console.print("  [dim]◌[/dim]", end="\r")

            collected_text = ""
            text_started = False

            with self.client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=8192,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "text" and not text_started:
                            console.print("  " + " " * 3, end="\r")  # clear indicator
                            console.print("[bold green]◆[/bold green] ", end="")
                            text_started = True

                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            print(event.delta.text, end="", flush=True)
                            collected_text += event.delta.text

                response = stream.get_final_message()

            if collected_text:
                print()  # newline after streamed text
                final_text = collected_text

            # Append full assistant turn (preserves tool_use blocks)
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            # Execute all tool calls and feed results back
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    self._log_tool_call(block.name, block.input)
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            self.messages.append({"role": "user", "content": tool_results})

        return final_text

    def _log_tool_call(self, name: str, input_data: dict) -> None:
        preview = ", ".join(
            f"{k}={repr(v)[:30]}" for k, v in list(input_data.items())[:2]
        )
        console.print(f"  [dim cyan]⚙ {name}({preview})[/dim cyan]")
