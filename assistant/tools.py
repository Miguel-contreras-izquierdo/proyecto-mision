"""Tool definitions and handlers for the executive account copilot."""
import json
from datetime import datetime, date

from .sales_analysis import (
    analyze_account_sales,
    get_portfolio_trends,
    get_at_risk_accounts,
    get_growth_opportunities,
)
from .storage import (
    load_accounts, save_accounts, find_account,
    load_pendings, save_pendings,
    load_notes, save_notes,
    load_opportunities, save_opportunities,
    new_id, now,
)

# ---------------------------------------------------------------------------
# Tool schemas (passed to the Claude API)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "create_or_update_account",
        "description": (
            "Registra una nueva cuenta o actualiza una existente. "
            "Úsala cuando el ejecutivo mencione un cliente, empresa o cuenta nueva, "
            "o cuando quiera actualizar datos de contacto, valor, segmento o estado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre de la empresa / cuenta cliente"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Nombre del contacto principal"
                },
                "contact_role": {
                    "type": "string",
                    "description": "Cargo del contacto (ej: CEO, Director Comercial)"
                },
                "contact_email": {"type": "string"},
                "contact_phone": {"type": "string"},
                "segment": {
                    "type": "string",
                    "enum": ["Enterprise", "Mid-Market", "SMB", "Startup", "Gobierno"],
                    "description": "Segmento de la cuenta"
                },
                "annual_value": {
                    "type": "number",
                    "description": "Valor anual de la cuenta en la moneda local"
                },
                "status": {
                    "type": "string",
                    "enum": ["prospecto", "activa", "en_riesgo", "inactiva", "perdida"],
                    "description": "Estado actual de la relación comercial"
                },
                "industry": {
                    "type": "string",
                    "description": "Industria o sector (ej: Retail, Financiero, Salud)"
                },
                "description": {
                    "type": "string",
                    "description": "Contexto general de la cuenta, historia de la relación"
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_accounts",
        "description": (
            "Lista las cuentas registradas con filtros opcionales. "
            "Úsala para obtener una visión general del portafolio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["prospecto", "activa", "en_riesgo", "inactiva", "perdida", "todas"],
                },
                "segment": {"type": "string"},
                "sort_by": {
                    "type": "string",
                    "enum": ["annual_value", "name", "status", "updated_at"],
                    "description": "Campo por el cual ordenar. Por defecto: annual_value descendente"
                },
            },
        },
    },
    {
        "name": "add_pending",
        "description": (
            "Agrega un pendiente o acción de seguimiento a una cuenta. "
            "Úsala cuando el ejecutivo mencione algo que debe hacer para esa cuenta: "
            "llamar, enviar propuesta, hacer demo, seguimiento, renovación, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "Nombre de la cuenta (puede ser parcial)"
                },
                "title": {
                    "type": "string",
                    "description": "Acción concisa a realizar"
                },
                "description": {
                    "type": "string",
                    "description": "Contexto adicional o detalle de la acción"
                },
                "priority": {
                    "type": "string",
                    "enum": ["crítica", "alta", "media", "baja"],
                    "description": "crítica=hoy, alta=esta semana, media=este mes, baja=cuando se pueda"
                },
                "deadline": {
                    "type": "string",
                    "description": "Fecha límite YYYY-MM-DD"
                },
            },
            "required": ["account_name", "title", "priority"],
        },
    },
    {
        "name": "list_pendings",
        "description": (
            "Lista los pendientes registrados. Sin filtros devuelve todos los pendientes activos "
            "ordenados por prioridad y fecha límite. Úsala para el briefing del día o semana."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "Filtrar por cuenta específica (opcional)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["crítica", "alta", "media", "baja", "todas"],
                },
                "overdue_only": {
                    "type": "boolean",
                    "description": "Si True, muestra solo los vencidos o que vencen hoy"
                },
            },
        },
    },
    {
        "name": "complete_pending",
        "description": "Marca un pendiente como completado cuando el ejecutivo indica que ya lo realizó.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pending_id": {"type": "string", "description": "ID del pendiente"},
                "completion_notes": {
                    "type": "string",
                    "description": "Resultado o notas sobre lo realizado (opcional pero recomendado)"
                },
            },
            "required": ["pending_id"],
        },
    },
    {
        "name": "add_note",
        "description": (
            "Registra una nota o novedad en el historial de la cuenta: reunión realizada, "
            "llamada, email importante, propuesta enviada, cambio de contacto, etc. "
            "Úsala para mantener el CRM actualizado con lo que el ejecutivo comparte."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {"type": "string"},
                "content": {
                    "type": "string",
                    "description": "Descripción completa de lo ocurrido o lo que se registra"
                },
                "note_type": {
                    "type": "string",
                    "enum": ["reunión", "llamada", "email", "propuesta", "seguimiento", "alerta", "otro"],
                },
            },
            "required": ["account_name", "content", "note_type"],
        },
    },
    {
        "name": "register_opportunity",
        "description": (
            "Registra o actualiza una oportunidad de crecimiento o venta en una cuenta: "
            "renovación, upsell, cross-sell, expansión, nuevo producto, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {"type": "string"},
                "title": {
                    "type": "string",
                    "description": "Nombre de la oportunidad (ej: 'Upsell módulo Analytics', 'Renovación contrato Q2')"
                },
                "description": {"type": "string"},
                "potential_value": {
                    "type": "number",
                    "description": "Valor potencial incremental estimado"
                },
                "probability": {
                    "type": "number",
                    "description": "Probabilidad de cierre 0.0-1.0"
                },
                "next_step": {
                    "type": "string",
                    "description": "Próxima acción concreta para avanzar esta oportunidad"
                },
                "deadline": {
                    "type": "string",
                    "description": "Fecha objetivo de cierre YYYY-MM-DD"
                },
            },
            "required": ["account_name", "title", "potential_value"],
        },
    },
    {
        "name": "get_account_summary",
        "description": (
            "Obtiene el resumen completo de una cuenta: datos, pendientes, notas recientes "
            "y oportunidades. Úsala antes de una reunión o cuando el ejecutivo quiera "
            "ponerse al día con una cuenta específica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "Nombre de la cuenta (puede ser parcial)"
                },
            },
            "required": ["account_name"],
        },
    },
    {
        "name": "get_executive_dashboard",
        "description": (
            "Genera el dashboard ejecutivo: resumen del portafolio, pendientes críticos/vencidos, "
            "oportunidades activas y alertas. Úsala al inicio del día/semana o cuando el ejecutivo "
            "quiera una visión general de su situación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "analyze_account_sales",
        "description": (
            "Analiza el histórico de ventas de una cuenta específica: tendencia por periodo, "
            "productos top, ventas por marca y comparación con el periodo anterior. "
            "Úsala cuando el ejecutivo quiera entender el comportamiento de una cuenta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "Nombre de la cuenta a analizar (puede ser parcial)",
                },
            },
            "required": ["account_name"],
        },
    },
    {
        "name": "get_portfolio_trends",
        "description": (
            "Muestra la tendencia de ventas de todo el portafolio por periodo: evolución mensual, "
            "cuentas top del último periodo y cambios. Úsala para análisis ejecutivo general."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_at_risk_accounts",
        "description": (
            "Identifica cuentas con caída de ventas respecto al periodo anterior. "
            "Úsala para priorizar visitas de rescate y acciones correctivas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decline_threshold_pct": {
                    "type": "number",
                    "description": "Umbral de caída para considerar cuenta en riesgo (default: -20%)",
                },
            },
        },
    },
    {
        "name": "get_growth_opportunities",
        "description": (
            "Detecta oportunidades de crecimiento: cuentas con marcas no penetradas (cross-sell), "
            "cuentas con crecimiento consistente y marcas con mayor potencial. "
            "Úsala para construir el plan de crecimiento."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def execute_tool(name: str, input_data: dict) -> str:
    handlers = {
        "create_or_update_account": _create_or_update_account,
        "list_accounts":             _list_accounts,
        "add_pending":               _add_pending,
        "list_pendings":             _list_pendings,
        "complete_pending":          _complete_pending,
        "add_note":                  _add_note,
        "register_opportunity":      _register_opportunity,
        "get_account_summary":       _get_account_summary,
        "get_executive_dashboard":   _get_executive_dashboard,
        # Sales analysis (require imported sales history)
        "analyze_account_sales":     lambda **kw: analyze_account_sales(**kw),
        "get_portfolio_trends":      lambda **kw: get_portfolio_trends(),
        "get_at_risk_accounts":      lambda **kw: get_at_risk_accounts(**kw),
        "get_growth_opportunities":  lambda **kw: get_growth_opportunities(),
    }
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Herramienta '{name}' no encontrada"})
    try:
        result = handler(**input_data)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# --- Handlers ---

def _create_or_update_account(
    name: str,
    contact_name: str = "",
    contact_role: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    segment: str = "",
    annual_value: float = 0,
    status: str = "activa",
    industry: str = "",
    description: str = "",
) -> dict:
    accounts = load_accounts()
    existing = next((a for a in accounts if a["name"].lower() == name.lower()), None)

    if existing:
        fields = dict(
            contact_name=contact_name, contact_role=contact_role,
            contact_email=contact_email, contact_phone=contact_phone,
            segment=segment, annual_value=annual_value, status=status,
            industry=industry, description=description,
        )
        for k, v in fields.items():
            if v:
                existing[k] = v
        existing["updated_at"] = now()
        save_accounts(accounts)
        return {"success": True, "action": "updated", "account_id": existing["id"], "name": existing["name"]}

    account = {
        "id": new_id(),
        "name": name,
        "contact_name": contact_name,
        "contact_role": contact_role,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "segment": segment,
        "annual_value": annual_value,
        "status": status,
        "industry": industry,
        "description": description,
        "created_at": now(),
        "updated_at": now(),
    }
    accounts.append(account)
    save_accounts(accounts)
    return {"success": True, "action": "created", "account_id": account["id"], "name": account["name"]}


def _list_accounts(status: str = "todas", segment: str = "", sort_by: str = "annual_value") -> dict:
    accounts = load_accounts()
    filtered = accounts

    if status != "todas":
        filtered = [a for a in filtered if a.get("status") == status]
    if segment:
        filtered = [a for a in filtered if a.get("segment", "").lower() == segment.lower()]

    reverse = sort_by in ("annual_value", "updated_at")
    filtered.sort(key=lambda a: (a.get(sort_by) or 0) if sort_by == "annual_value"
                  else (a.get(sort_by) or ""), reverse=reverse)

    return {"total": len(filtered), "accounts": filtered}


def _add_pending(
    account_name: str,
    title: str,
    priority: str,
    description: str = "",
    deadline: str = None,
) -> dict:
    account = find_account(account_name)
    if not account:
        return {"error": f"Cuenta '{account_name}' no encontrada. Regístrala primero."}

    pendings = load_pendings()
    pending = {
        "id": new_id(),
        "account_id": account["id"],
        "account_name": account["name"],
        "title": title,
        "description": description,
        "priority": priority,
        "deadline": deadline,
        "status": "pendiente",
        "created_at": now(),
        "completed_at": None,
        "completion_notes": "",
    }
    pendings.append(pending)
    save_pendings(pendings)
    return {"success": True, "pending_id": pending["id"], "account": account["name"], "title": title}


def _list_pendings(
    account_name: str = None,
    priority: str = None,
    overdue_only: bool = False,
) -> dict:
    pendings = load_pendings()
    today = date.today().isoformat()

    filtered = [p for p in pendings if p.get("status") == "pendiente"]

    if account_name:
        acct = find_account(account_name)
        if acct:
            filtered = [p for p in filtered if p["account_id"] == acct["id"]]
        else:
            filtered = [p for p in filtered if account_name.lower() in p["account_name"].lower()]

    if priority and priority != "todas":
        filtered = [p for p in filtered if p.get("priority") == priority]

    if overdue_only:
        filtered = [p for p in filtered if p.get("deadline") and p["deadline"] <= today]

    priority_order = {"crítica": 0, "alta": 1, "media": 2, "baja": 3}
    filtered.sort(key=lambda p: (
        priority_order.get(p.get("priority", "baja"), 4),
        p.get("deadline") or "9999-12-31",
    ))

    # Flag overdue items
    for p in filtered:
        p["is_overdue"] = bool(p.get("deadline") and p["deadline"] < today)

    return {"total": len(filtered), "pendings": filtered}


def _complete_pending(pending_id: str, completion_notes: str = "") -> dict:
    pendings = load_pendings()
    for p in pendings:
        if p["id"] == pending_id:
            p["status"] = "completado"
            p["completed_at"] = now()
            p["completion_notes"] = completion_notes
            save_pendings(pendings)
            return {"success": True, "message": f"Pendiente '{p['title']}' marcado como completado"}
    return {"error": f"Pendiente {pending_id} no encontrado"}


def _add_note(account_name: str, content: str, note_type: str) -> dict:
    account = find_account(account_name)
    if not account:
        return {"error": f"Cuenta '{account_name}' no encontrada"}

    notes = load_notes()
    note = {
        "id": new_id(),
        "account_id": account["id"],
        "account_name": account["name"],
        "content": content,
        "note_type": note_type,
        "created_at": now(),
    }
    notes.append(note)
    save_notes(notes)

    # Bump account updated_at
    accounts = load_accounts()
    for a in accounts:
        if a["id"] == account["id"]:
            a["updated_at"] = now()
    from .storage import save_accounts as _sa
    _sa(accounts)

    return {"success": True, "note_id": note["id"], "account": account["name"]}


def _register_opportunity(
    account_name: str,
    title: str,
    potential_value: float,
    description: str = "",
    probability: float = 0.5,
    next_step: str = "",
    deadline: str = None,
) -> dict:
    account = find_account(account_name)
    if not account:
        return {"error": f"Cuenta '{account_name}' no encontrada"}

    opps = load_opportunities()
    opp = {
        "id": new_id(),
        "account_id": account["id"],
        "account_name": account["name"],
        "title": title,
        "description": description,
        "potential_value": potential_value,
        "probability": probability,
        "weighted_value": round(potential_value * probability, 2),
        "next_step": next_step,
        "deadline": deadline,
        "status": "activa",
        "created_at": now(),
        "updated_at": now(),
    }
    opps.append(opp)
    save_opportunities(opps)
    return {
        "success": True,
        "opportunity_id": opp["id"],
        "account": account["name"],
        "weighted_value": opp["weighted_value"],
    }


def _get_account_summary(account_name: str) -> dict:
    account = find_account(account_name)
    if not account:
        return {"error": f"Cuenta '{account_name}' no encontrada"}

    acc_id = account["id"]
    today = date.today().isoformat()

    pendings = [p for p in load_pendings()
                if p["account_id"] == acc_id and p["status"] == "pendiente"]
    priority_order = {"crítica": 0, "alta": 1, "media": 2, "baja": 3}
    pendings.sort(key=lambda p: (priority_order.get(p.get("priority", "baja"), 4),
                                  p.get("deadline") or "9999"))
    for p in pendings:
        p["is_overdue"] = bool(p.get("deadline") and p["deadline"] < today)

    notes = sorted(
        [n for n in load_notes() if n["account_id"] == acc_id],
        key=lambda n: n["created_at"],
        reverse=True,
    )[:10]  # last 10 notes

    opps = [o for o in load_opportunities()
            if o["account_id"] == acc_id and o["status"] == "activa"]

    return {
        "account": account,
        "pending_count": len(pendings),
        "pendings": pendings,
        "recent_notes": notes,
        "opportunities": opps,
        "total_opportunity_value": sum(o["potential_value"] for o in opps),
        "weighted_pipeline": sum(o["weighted_value"] for o in opps),
    }


def _get_executive_dashboard() -> dict:
    today = date.today().isoformat()
    accounts = load_accounts()
    pendings = load_pendings()
    opps = load_opportunities()

    active_accounts = [a for a in accounts if a.get("status") == "activa"]
    at_risk = [a for a in accounts if a.get("status") == "en_riesgo"]
    prospects = [a for a in accounts if a.get("status") == "prospecto"]

    open_pendings = [p for p in pendings if p.get("status") == "pendiente"]
    critical = [p for p in open_pendings if p.get("priority") == "crítica"]
    overdue = [p for p in open_pendings if p.get("deadline") and p["deadline"] < today]
    high = [p for p in open_pendings if p.get("priority") == "alta"]

    active_opps = [o for o in opps if o.get("status") == "activa"]
    total_pipeline = sum(o["potential_value"] for o in active_opps)
    weighted_pipeline = sum(o["weighted_value"] for o in active_opps)

    # Accounts with no activity last 30 days
    from datetime import datetime, timedelta
    threshold = (datetime.now() - timedelta(days=30)).isoformat()
    neglected = [
        a for a in active_accounts
        if (a.get("updated_at") or a.get("created_at", "")) < threshold
    ]

    return {
        "today": today,
        "portfolio_summary": {
            "total_accounts": len(accounts),
            "active": len(active_accounts),
            "at_risk": len(at_risk),
            "prospects": len(prospects),
            "total_annual_value": sum(a.get("annual_value", 0) for a in active_accounts),
        },
        "pending_summary": {
            "total_open": len(open_pendings),
            "critical": critical,
            "overdue": overdue,
            "high_priority": high,
        },
        "pipeline_summary": {
            "active_opportunities": len(active_opps),
            "total_potential": total_pipeline,
            "weighted_pipeline": weighted_pipeline,
            "opportunities": sorted(active_opps, key=lambda o: o["weighted_value"], reverse=True)[:5],
        },
        "alerts": {
            "at_risk_accounts": at_risk,
            "neglected_accounts": neglected,
        },
    }
