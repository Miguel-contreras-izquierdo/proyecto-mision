"""
Copiloto Ejecutivo — Dashboard Visual
Ejecutar: streamlit run dashboard.py
"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    sys.path.insert(0, str(Path(__file__).parent))
    from imports.import_sales import (
        process_dataframe, COLUMN_PATTERNS, detect_column,
        detect_wide_format, get_wide_format_info,
    )
    IMPORT_AVAILABLE = True
except Exception:
    IMPORT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Copiloto Ejecutivo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def load_json(filename: str) -> list:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_sales_df() -> pd.DataFrame:
    records = load_json("sales_history.json")
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["units"] = pd.to_numeric(df.get("units", 0), errors="coerce").fillna(0)
    df["period"] = df["period"].astype(str)
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRIORITY_ORDER = {"crítica": 0, "alta": 1, "media": 2, "baja": 3}
PRIORITY_COLOR = {
    "crítica": "#ef4444",
    "alta":    "#f97316",
    "media":   "#eab308",
    "baja":    "#22c55e",
}
STATUS_COLOR = {
    "activa":    "#22c55e",
    "en_riesgo": "#ef4444",
    "prospecto": "#3b82f6",
    "inactiva":  "#94a3b8",
    "perdida":   "#64748b",
}


def fmt_money(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val/1_000:.0f}K"
    return f"${val:,.0f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("📊 Copiloto Ejecutivo")
st.sidebar.caption("Dashboard de cuentas y ventas")

section = st.sidebar.radio(
    "Sección",
    ["📊 Resumen Ejecutivo", "📈 Ventas", "🏢 Cuentas", "⏰ Pendientes", "💡 Oportunidades"],
)
st.sidebar.divider()

# ---- Importar archivo de ventas ----
st.sidebar.subheader("📂 Importar ventas")
uploaded = st.sidebar.file_uploader("Sube un archivo Excel (.xlsx)", type=["xlsx"])

if uploaded and not IMPORT_AVAILABLE:
    st.sidebar.error("Módulo de importación no disponible.")
elif uploaded:
    try:
        df_raw = pd.read_excel(io.BytesIO(uploaded.read()), dtype=str)
        df_raw.columns = [str(c).strip() for c in df_raw.columns]
        cols = list(df_raw.columns)

        is_wide = detect_wide_format(df_raw)
        if is_wide:
            info = get_wide_format_info(df_raw)
            st.sidebar.info(
                f"📊 **Formato ancho detectado**\n\n"
                f"- {len(info['id_cols'])} columnas fijas: {', '.join(info['id_cols'])}\n"
                f"- {len(info['month_cols'])} periodos mensuales\n"
                f"- {len(info['agg_cols'])} columnas omitidas (YTD/MAT): "
                + (', '.join(info['agg_cols']) if info['agg_cols'] else '—')
            )
            with st.sidebar.expander("Columnas de periodo detectadas"):
                st.write(", ".join(info['month_cols']))
            with st.sidebar.expander("Columnas fijas — verificar mapeo"):
                auto_mapping = {f: detect_column(info['id_cols'], f) for f in ("account", "product", "sku", "brand", "rep")}
                custom_mapping = {}
                for field in ("account", "product", "sku", "brand", "rep"):
                    required = field == "account"
                    icon = "🔴" if (required and not auto_mapping[field]) else ("✅" if auto_mapping[field] else "⬜")
                    options = ["— ninguna —"] + info['id_cols']
                    default_idx = info['id_cols'].index(auto_mapping[field]) + 1 if auto_mapping[field] in info['id_cols'] else 0
                    selected = st.selectbox(f"{icon} {field}", options, index=default_idx, key=f"map_{field}")
                    custom_mapping[field] = selected if selected != "— ninguna —" else None
        else:
            st.sidebar.info("📋 **Formato largo detectado**")
            auto_mapping = {f: detect_column(cols, f) for f in COLUMN_PATTERNS}
            with st.sidebar.expander("Columnas detectadas", expanded=True):
                for field, col in auto_mapping.items():
                    required = field in ("account", "period", "amount")
                    icon = "🔴" if (required and not col) else ("✅" if col else "⬜")
                    st.write(f"{icon} **{field}** → {col or '—'}")
                st.caption("Corrige el mapeo si es necesario:")
                custom_mapping = {}
                for field in COLUMN_PATTERNS:
                    options = ["— ninguna —"] + cols
                    default_idx = cols.index(auto_mapping[field]) + 1 if auto_mapping[field] in cols else 0
                    selected = st.selectbox(field, options, index=default_idx, key=f"map_{field}")
                    custom_mapping[field] = selected if selected != "— ninguna —" else None

        if st.sidebar.button("✅ Importar y actualizar dashboard"):
            if is_wide:
                # Apply id column remapping before passing to process_dataframe
                rename = {v: k for k, v in custom_mapping.items() if v}
                df_to_import = df_raw.rename(columns=rename)
            else:
                rename = {v: k for k, v in custom_mapping.items() if v}
                df_to_import = df_raw.rename(columns=rename)

            try:
                summary = process_dataframe(df_to_import, uploaded.name)
                periods = summary["periods"]
                fmt = "ancho" if summary.get("wide_format") else "largo"
                st.sidebar.success(
                    f"✓ {summary['records']:,} registros importados ({fmt})\n\n"
                    f"📅 {periods[0]} → {periods[-1]}\n\n"
                    f"🏢 {summary['unique_accounts']} cuentas\n\n"
                    f"💰 ${summary['total_amount']:,.0f}"
                )
                st.cache_data.clear()
                st.rerun()
            except ValueError as e:
                st.sidebar.error(str(e))

    except Exception as e:
        st.sidebar.error(f"Error leyendo el archivo: {e}")

st.sidebar.divider()
st.sidebar.caption(f"Datos al {datetime.now().strftime('%d/%m/%Y %H:%M')}")
if st.sidebar.button("🔄 Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# 1. RESUMEN EJECUTIVO
# ---------------------------------------------------------------------------

if section == "📊 Resumen Ejecutivo":
    st.title("📊 Resumen Ejecutivo")

    accounts  = load_json("accounts.json")
    pendings  = load_json("pendings.json")
    opps      = load_json("opportunities.json")
    sales_df  = load_sales_df()

    today = date.today().isoformat()
    active_accounts = [a for a in accounts if a.get("status") == "activa"]
    open_pendings   = [p for p in pendings if p.get("status") == "pendiente"]
    critical        = [p for p in open_pendings if p.get("priority") == "crítica"]
    overdue         = [p for p in open_pendings if p.get("deadline", "9999") < today]
    active_opps     = [o for o in opps if o.get("status") == "activa"]
    total_arr       = sum(a.get("annual_value", 0) for a in active_accounts)
    pipeline        = sum(o.get("weighted_value", 0) for o in active_opps)

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Cuentas activas",     len(active_accounts))
    k2.metric("Facturación anual",   fmt_money(total_arr))
    k3.metric("Pendientes críticos", len(critical),  delta=f"{len(overdue)} vencidos", delta_color="inverse")
    k4.metric("Oportunidades",       len(active_opps))
    k5.metric("Pipeline ponderado",  fmt_money(pipeline))

    st.divider()
    col_left, col_right = st.columns(2)

    # Portfolio by status
    with col_left:
        st.subheader("Portafolio por estado")
        if accounts:
            status_counts = defaultdict(int)
            status_value  = defaultdict(float)
            for a in accounts:
                s = a.get("status", "desconocido")
                status_counts[s] += 1
                status_value[s]  += a.get("annual_value", 0)
            df_status = pd.DataFrame([
                {"Estado": s, "Cuentas": status_counts[s], "Valor anual": status_value[s]}
                for s in status_counts
            ])
            fig = px.bar(
                df_status, x="Estado", y="Valor anual", color="Estado",
                color_discrete_map=STATUS_COLOR, text_auto=".2s",
                labels={"Valor anual": "Valor anual ($)"},
            )
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin cuentas registradas aún.")

    # Top accounts by value
    with col_right:
        st.subheader("Top cuentas por valor anual")
        if active_accounts:
            top = sorted(active_accounts, key=lambda a: a.get("annual_value", 0), reverse=True)[:10]
            df_top = pd.DataFrame([
                {"Cuenta": a["name"], "Valor": a.get("annual_value", 0)}
                for a in top
            ])
            fig = px.bar(
                df_top, x="Valor", y="Cuenta", orientation="h",
                color="Valor", color_continuous_scale="Blues", text_auto=".2s",
            )
            fig.update_layout(showlegend=False, coloraxis_showscale=False,
                              yaxis={"categoryorder": "total ascending"},
                              margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin cuentas registradas aún.")

    # Alerts
    st.subheader("⚠️ Alertas")
    at_risk = [a for a in accounts if a.get("status") == "en_riesgo"]
    if at_risk or overdue:
        if at_risk:
            for a in at_risk:
                st.error(f"🔴 **Cuenta en riesgo:** {a['name']} — Contacto: {a.get('contact_name', '—')}")
        if overdue:
            for p in overdue[:5]:
                st.warning(f"⏰ **Vencido:** {p['title']} · {p['account_name']} · deadline {p.get('deadline', '?')}")
    else:
        st.success("Sin alertas críticas en este momento.")

# ---------------------------------------------------------------------------
# 2. VENTAS
# ---------------------------------------------------------------------------

elif section == "📈 Ventas":
    st.title("📈 Histórico de Ventas")
    df = load_sales_df()

    if df.empty:
        st.warning("No hay datos de ventas importados.")
        st.code("python3 imports/import_sales.py imports/TU_ARCHIVO.xlsx")
        st.stop()

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    all_accounts = sorted(df["account_name"].dropna().unique())
    all_brands   = sorted(df["brand"].dropna().replace("", pd.NA).dropna().unique()) if "brand" in df else []
    all_periods  = sorted(df["period"].unique())

    selected_accounts = col_f1.multiselect("Cuentas", all_accounts, placeholder="Todas")
    selected_brands   = col_f2.multiselect("Marcas", all_brands, placeholder="Todas") if all_brands else []
    period_range      = col_f3.select_slider(
        "Período", options=all_periods,
        value=(all_periods[0], all_periods[-1]),
    ) if len(all_periods) >= 2 else (all_periods[0], all_periods[0])

    mask = (df["period"] >= period_range[0]) & (df["period"] <= period_range[1])
    if selected_accounts:
        mask &= df["account_name"].isin(selected_accounts)
    if selected_brands and "brand" in df.columns:
        mask &= df["brand"].isin(selected_brands)
    dff = df[mask]

    if dff.empty:
        st.warning("Sin datos para los filtros seleccionados.")
        st.stop()

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Venta total",      fmt_money(dff["amount"].sum()))
    k2.metric("Cuentas",          dff["account_name"].nunique())
    k3.metric("Unidades",         f"{int(dff['units'].sum()):,}" if "units" in dff else "—")
    k4.metric("Períodos",         dff["period"].nunique())

    st.divider()

    # Trend line
    st.subheader("Tendencia de ventas por período")
    trend = dff.groupby("period")["amount"].sum().reset_index()
    trend.columns = ["Período", "Venta"]
    trend["Δ%"] = trend["Venta"].pct_change() * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend["Período"], y=trend["Venta"], mode="lines+markers+text",
        text=trend["Venta"].apply(fmt_money), textposition="top center",
        line=dict(color="#3b82f6", width=3), marker=dict(size=8),
        name="Venta",
    ))
    fig.update_layout(margin=dict(t=20, b=20), xaxis_title="Período", yaxis_title="Venta ($)")
    st.plotly_chart(fig, use_container_width=True)

    col_l, col_r = st.columns(2)

    # By account
    with col_l:
        st.subheader("Venta por cuenta")
        by_account = dff.groupby("account_name")["amount"].sum().reset_index()
        by_account.columns = ["Cuenta", "Venta"]
        by_account = by_account.sort_values("Venta", ascending=True).tail(15)
        fig = px.bar(
            by_account, x="Venta", y="Cuenta", orientation="h",
            color="Venta", color_continuous_scale="Blues", text_auto=".2s",
        )
        fig.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    # By brand/product
    with col_r:
        if "brand" in dff.columns and dff["brand"].notna().any():
            st.subheader("Venta por marca")
            by_brand = dff.groupby("brand")["amount"].sum().reset_index()
            by_brand.columns = ["Marca", "Venta"]
            by_brand = by_brand[by_brand["Marca"].str.strip() != ""].sort_values("Venta", ascending=False).head(10)
            fig = px.pie(by_brand, values="Venta", names="Marca", hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        elif "product" in dff.columns:
            st.subheader("Top productos")
            by_prod = dff.groupby("product")["amount"].sum().reset_index()
            by_prod.columns = ["Producto", "Venta"]
            by_prod = by_prod.sort_values("Venta", ascending=False).head(10)
            st.dataframe(by_prod, use_container_width=True, hide_index=True)

    # Period-over-period heatmap (accounts × periods)
    if len(all_periods) > 1 and dff["account_name"].nunique() <= 30:
        st.subheader("Mapa de calor: venta por cuenta y período")
        pivot = dff.pivot_table(values="amount", index="account_name",
                                columns="period", aggfunc="sum", fill_value=0)
        fig = px.imshow(
            pivot, text_auto=".2s", aspect="auto",
            color_continuous_scale="Blues",
            labels=dict(x="Período", y="Cuenta", color="Venta ($)"),
        )
        fig.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# 3. CUENTAS
# ---------------------------------------------------------------------------

elif section == "🏢 Cuentas":
    st.title("🏢 Cuentas")
    accounts = load_json("accounts.json")

    if not accounts:
        st.info("Sin cuentas registradas. Usa el copiloto para agregarlas.")
        st.stop()

    # Filters
    col1, col2 = st.columns(2)
    status_opts = ["todas"] + sorted({a.get("status", "") for a in accounts})
    seg_opts    = ["todos"] + sorted({a.get("segment", "") for a in accounts if a.get("segment")})
    sel_status  = col1.selectbox("Estado", status_opts)
    sel_seg     = col2.selectbox("Segmento", seg_opts)

    filtered = accounts
    if sel_status != "todas":
        filtered = [a for a in filtered if a.get("status") == sel_status]
    if sel_seg != "todos":
        filtered = [a for a in filtered if a.get("segment") == sel_seg]

    filtered = sorted(filtered, key=lambda a: a.get("annual_value", 0), reverse=True)

    # Table
    rows = []
    for a in filtered:
        rows.append({
            "Cuenta":         a["name"],
            "Contacto":       a.get("contact_name", "—"),
            "Segmento":       a.get("segment", "—"),
            "Industria":      a.get("industry", "—"),
            "Estado":         a.get("status", "—"),
            "Valor anual ($)": a.get("annual_value", 0),
        })
    df_accounts = pd.DataFrame(rows)
    st.dataframe(
        df_accounts.style.format({"Valor anual ($)": "${:,.0f}"}),
        use_container_width=True, hide_index=True,
    )

    # Detail expander
    st.subheader("Detalle de cuenta")
    names = [a["name"] for a in filtered]
    if names:
        selected = st.selectbox("Selecciona una cuenta", names)
        account = next((a for a in filtered if a["name"] == selected), None)
        if account:
            pendings  = [p for p in load_json("pendings.json")
                         if p.get("account_id") == account["id"] and p.get("status") == "pendiente"]
            notes     = sorted([n for n in load_json("notes.json")
                                if n.get("account_id") == account["id"]],
                               key=lambda n: n["created_at"], reverse=True)[:8]
            opps      = [o for o in load_json("opportunities.json")
                         if o.get("account_id") == account["id"] and o.get("status") == "activa"]

            c1, c2, c3 = st.columns(3)
            c1.metric("Valor anual",  fmt_money(account.get("annual_value", 0)))
            c2.metric("Pendientes",   len(pendings))
            c3.metric("Oportunidades", len(opps))

            with st.expander("📋 Pendientes", expanded=bool(pendings)):
                if pendings:
                    today = date.today().isoformat()
                    for p in sorted(pendings, key=lambda x: PRIORITY_ORDER.get(x.get("priority", "baja"), 4)):
                        color = PRIORITY_COLOR.get(p.get("priority", "baja"), "#94a3b8")
                        overdue = p.get("deadline") and p["deadline"] < today
                        icon = "🔴" if overdue else "🟡"
                        st.markdown(
                            f"{icon} **{p['title']}** "
                            f"<span style='color:{color}'>● {p.get('priority','')}</span> "
                            f"· deadline: {p.get('deadline','—')} · ID: `{p['id']}`",
                            unsafe_allow_html=True,
                        )
                else:
                    st.write("Sin pendientes.")

            with st.expander("📝 Notas recientes"):
                if notes:
                    for n in notes:
                        st.markdown(f"**{n['created_at'][:10]}** · _{n.get('note_type','')}_")
                        st.write(n.get("content", ""))
                        st.divider()
                else:
                    st.write("Sin notas registradas.")

            with st.expander("💡 Oportunidades"):
                if opps:
                    for o in opps:
                        st.markdown(
                            f"**{o['title']}** · Potencial: {fmt_money(o.get('potential_value', 0))} "
                            f"· Ponderado: {fmt_money(o.get('weighted_value', 0))} "
                            f"· Prob: {int(o.get('probability', 0)*100)}%"
                        )
                        if o.get("next_step"):
                            st.caption(f"Próximo paso: {o['next_step']}")
                else:
                    st.write("Sin oportunidades registradas.")

# ---------------------------------------------------------------------------
# 4. PENDIENTES
# ---------------------------------------------------------------------------

elif section == "⏰ Pendientes":
    st.title("⏰ Pendientes")
    pendings = load_json("pendings.json")
    today    = date.today().isoformat()
    open_p   = [p for p in pendings if p.get("status") == "pendiente"]

    if not open_p:
        st.success("¡Sin pendientes abiertos!")
        st.stop()

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total abiertos", len(open_p))
    k2.metric("Críticos",       len([p for p in open_p if p.get("priority") == "crítica"]))
    k3.metric("Vencidos",       len([p for p in open_p if p.get("deadline", "9999") < today]))
    k4.metric("Esta semana",    len([p for p in open_p if p.get("deadline", "9999") <= today]))

    # By priority chart
    st.subheader("Pendientes por prioridad")
    prio_counts = defaultdict(int)
    for p in open_p:
        prio_counts[p.get("priority", "sin definir")] += 1
    df_prio = pd.DataFrame([{"Prioridad": k, "Cantidad": v} for k, v in prio_counts.items()])
    df_prio["order"] = df_prio["Prioridad"].map(PRIORITY_ORDER).fillna(9)
    df_prio = df_prio.sort_values("order")
    fig = px.bar(
        df_prio, x="Prioridad", y="Cantidad",
        color="Prioridad", color_discrete_map=PRIORITY_COLOR,
        text_auto=True,
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # Full table
    st.subheader("Lista completa")
    rows = []
    for p in sorted(open_p, key=lambda x: (PRIORITY_ORDER.get(x.get("priority", "baja"), 4),
                                            x.get("deadline") or "9999")):
        rows.append({
            "ID":       p["id"],
            "Cuenta":   p.get("account_name", "—"),
            "Pendiente": p["title"],
            "Prioridad": p.get("priority", "—"),
            "Deadline":  p.get("deadline", "—"),
            "Vencido":   "⚠️" if p.get("deadline") and p["deadline"] < today else "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 5. OPORTUNIDADES
# ---------------------------------------------------------------------------

elif section == "💡 Oportunidades":
    st.title("💡 Oportunidades de Crecimiento")
    opps     = load_json("opportunities.json")
    active   = [o for o in opps if o.get("status") == "activa"]
    sales_df = load_sales_df()

    if active:
        # KPIs
        total_potential = sum(o.get("potential_value", 0) for o in active)
        weighted        = sum(o.get("weighted_value", 0) for o in active)
        k1, k2, k3 = st.columns(3)
        k1.metric("Oportunidades activas", len(active))
        k2.metric("Potencial total",        fmt_money(total_potential))
        k3.metric("Pipeline ponderado",     fmt_money(weighted))

        st.subheader("Pipeline por cuenta")
        df_opps = pd.DataFrame([{
            "Cuenta":     o["account_name"],
            "Oportunidad": o["title"],
            "Potencial":  o.get("potential_value", 0),
            "Ponderado":  o.get("weighted_value", 0),
            "Probabilidad": f"{int(o.get('probability', 0)*100)}%",
            "Cierre":     o.get("deadline", "—"),
            "Próximo paso": o.get("next_step", "—"),
        } for o in sorted(active, key=lambda x: x.get("weighted_value", 0), reverse=True)])

        st.dataframe(
            df_opps.style.format({"Potencial": "${:,.0f}", "Ponderado": "${:,.0f}"}),
            use_container_width=True, hide_index=True,
        )

        # Waterfall por cuenta
        st.subheader("Potencial por cuenta")
        by_account = defaultdict(float)
        for o in active:
            by_account[o["account_name"]] += o.get("potential_value", 0)
        df_bar = pd.DataFrame([{"Cuenta": k, "Potencial": v}
                                for k, v in sorted(by_account.items(), key=lambda x: x[1], reverse=True)])
        fig = px.bar(df_bar, x="Cuenta", y="Potencial", text_auto=".2s",
                     color="Potencial", color_continuous_scale="Greens")
        fig.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin oportunidades registradas. Usa el copiloto para agregarlas.")

    # Cross-sell from sales data
    if not sales_df.empty and "brand" in sales_df.columns:
        st.subheader("📦 Gaps de penetración por marca (cross-sell)")
        st.caption("Marcas presentes en el portafolio pero no en ciertas cuentas")
        all_brands   = set(sales_df["brand"].dropna().replace("", pd.NA).dropna().unique())
        account_brands = sales_df.groupby("account_name")["brand"].apply(set).to_dict()
        gaps = []
        for acc, brands in account_brands.items():
            missing = all_brands - brands - {""}
            if missing:
                total = sales_df[sales_df["account_name"] == acc]["amount"].sum()
                gaps.append({
                    "Cuenta": acc,
                    "Venta actual ($)": total,
                    "Marcas activas": len(brands - {""}),
                    "Marcas faltantes": len(missing),
                    "Oportunidad cross-sell": ", ".join(sorted(missing)[:5]),
                })
        if gaps:
            df_gaps = pd.DataFrame(gaps).sort_values("Venta actual ($)", ascending=False)
            st.dataframe(
                df_gaps.style.format({"Venta actual ($)": "${:,.0f}"}),
                use_container_width=True, hide_index=True,
            )
