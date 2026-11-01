import os
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "football_cache.sqlite3"
API_BASE = "https://v3.football.api-sports.io"

st.set_page_config(
    page_title="Mi Predictor de Fútbol",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def secret(name, default=""):
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return os.getenv(name, default)

def check_password():
    expected = secret("APP_PASSWORD", "")
    if not expected:
        st.error("Falta configurar APP_PASSWORD en los secretos del alojamiento. La app queda bloqueada por seguridad.")
        st.stop()
    if st.session_state.get("authenticated", False):
        return True
    st.title("⚽ Mi Predictor de Fútbol")
    st.caption("Acceso privado")
    with st.form("login_form"):
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted:
        if password and password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()

check_password()

st.title("⚽ Mi Predictor de Fútbol")
st.caption("Versión privada · análisis estadístico orientativo · no garantiza resultados")

with st.sidebar:
    st.header("Configuración")
    if st.button("Cerrar sesión"):
        st.session_state["authenticated"] = False
        st.rerun()
    selected_date = st.date_input("Fecha de partidos", value=date.today())
    st.caption("Los datos dependen de la cobertura y los límites del proveedor.")

api_key = secret("API_FOOTBALL_KEY", "")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS api_cache (
            cache_key TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS imported_matches (
            imported_at TEXT, source TEXT, home_team TEXT, away_team TEXT,
            date TEXT, home_goals REAL, away_goals REAL, home_corners REAL,
            away_corners REAL, home_cards REAL, away_cards REAL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS predictions (
            created_at TEXT, match_date TEXT, competition TEXT, home_team TEXT,
            away_team TEXT, home_xg REAL, away_xg REAL, market TEXT,
            probability REAL, odds REAL, result TEXT
        )""")

init_db()

def cache_get(key, ttl_seconds=3600):
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT created_at, payload FROM api_cache WHERE cache_key=?", (key,)).fetchone()
    if not row:
        return None
    try:
        created = datetime.fromisoformat(row[0])
        if (datetime.now() - created).total_seconds() > ttl_seconds:
            return None
        return __import__("json").loads(row[1])
    except Exception:
        return None

def cache_set(key, rows):
    import json
    payload = json.dumps(rows, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR REPLACE INTO api_cache(cache_key, created_at, payload) VALUES(?,?,?)",
                    (key, datetime.now().isoformat(), payload))

def api_get(endpoint, params=None, ttl=3600):
    if not api_key:
        return None, "No se ha configurado API_FOOTBALL_KEY en los secretos del alojamiento."
    params = params or {}
    cache_key = endpoint + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    cached = cache_get(cache_key, ttl)
    if cached is not None:
        return cached, None
    try:
        response = requests.get(
            f"{API_BASE}/{endpoint.lstrip('/')}",
            headers={"x-apisports-key": api_key},
            params=params,
            timeout=25
        )
        if response.status_code == 401:
            return None, "La clave de API no es válida o no está autorizada."
        if response.status_code == 429:
            return None, "Se ha alcanzado el límite de peticiones del proveedor. Espera o revisa tu plan."
        response.raise_for_status()
        data = response.json()
        if data.get("errors"):
            return None, f"Error del proveedor: {data['errors']}"
        rows = data.get("response", [])
        cache_set(cache_key, rows)
        return rows, None
    except requests.RequestException as exc:
        return None, f"No se pudo consultar la fuente de datos: {exc}"

def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def probabilities(home_lambda, away_lambda, max_goals=10):
    matrix = [[poisson_pmf(i, home_lambda) * poisson_pmf(j, away_lambda)
               for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    result = {
        "Más de 0.5 goles": 0.0, "Más de 1.5 goles": 0.0,
        "Más de 2.5 goles": 0.0, "Más de 3.5 goles": 0.0,
        "Ambos marcan": 0.0, "Victoria local": 0.0,
        "Empate": 0.0, "Victoria visitante": 0.0,
    }
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            if h + a >= 1: result["Más de 0.5 goles"] += p
            if h + a >= 2: result["Más de 1.5 goles"] += p
            if h + a >= 3: result["Más de 2.5 goles"] += p
            if h + a >= 4: result["Más de 3.5 goles"] += p
            if h > 0 and a > 0: result["Ambos marcan"] += p
            if h > a: result["Victoria local"] += p
            elif h == a: result["Empate"] += p
            else: result["Victoria visitante"] += p
    return result, matrix

def recent_team(team_id):
    rows, err = api_get("fixtures", {"team": team_id, "last": 10, "status": "FT"}, ttl=6*3600)
    if err:
        return None, err
    out = []
    for item in rows or []:
        goals = item.get("goals") or {}
        teams = item.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        gh, ga = goals.get("home"), goals.get("away")
        if gh is None or ga is None:
            continue
        is_home = home.get("id") == team_id
        out.append({
            "date": (item.get("fixture") or {}).get("date", ""),
            "home_name": home.get("name", ""), "away_name": away.get("name", ""),
            "home_goals": gh, "away_goals": ga,
            "team_goals": gh if is_home else ga,
            "team_conceded": ga if is_home else gh,
            "is_home": is_home,
        })
    return out, None

def estimate_goals(home_recent, away_recent):
    if not home_recent or not away_recent:
        return None
    h_scored = sum(x["team_goals"] for x in home_recent) / len(home_recent)
    h_conceded = sum(x["team_conceded"] for x in home_recent) / len(home_recent)
    a_scored = sum(x["team_goals"] for x in away_recent) / len(away_recent)
    a_conceded = sum(x["team_conceded"] for x in away_recent) / len(away_recent)
    # Estimación simple: no sustituye un modelo calibrado por liga.
    home_xg = max(0.15, (0.65*h_scored + 0.35*a_conceded) * 1.08)
    away_xg = max(0.15, (0.65*a_scored + 0.35*h_conceded))
    return home_xg, away_xg

def pct(x):
    return f"{100*x:.1f}%"

def odds_prob(odds):
    return 1 / odds if odds and odds > 1 else None

if not api_key:
    st.warning("La aplicación está protegida, pero todavía no tiene una fuente de estadísticas configurada.")
    st.markdown("El administrador debe añadir `API_FOOTBALL_KEY` a los secretos del alojamiento. No introduzcas aquí claves privadas.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Partidos y predicciones", "Historial", "Importar CSV"])

with tab1:
    st.subheader("Partidos disponibles")
    with st.spinner("Consultando calendario..."):
        fixtures, error = api_get("fixtures", {"date": selected_date.isoformat(), "timezone": "Europe/Madrid"}, ttl=900)
    if error:
        st.error(error)
    elif not fixtures:
        st.info("No aparecen partidos para esta fecha con la cobertura actual.")
    else:
        matches = []
        for item in fixtures:
            fx = item.get("fixture") or {}
            teams = item.get("teams") or {}
            league = item.get("league") or {}
            status = fx.get("status") or {}
            goals = item.get("goals") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            matches.append({
                "id": fx.get("id"),
                "hora": (fx.get("date") or "")[11:16],
                "competicion": league.get("name", ""),
                "local": home.get("name", ""), "visitante": away.get("name", ""),
                "estado": status.get("long", ""),
                "marcador": f"{goals.get('home') if goals.get('home') is not None else '-'} - {goals.get('away') if goals.get('away') is not None else '-'}",
                "home_id": home.get("id"), "away_id": away.get("id"),
            })
        df = pd.DataFrame(matches)
        st.dataframe(df[["hora", "competicion", "local", "visitante", "estado", "marcador"]],
                     use_container_width=True, hide_index=True)
        choices = {f"{m['hora']} · {m['competicion']} · {m['local']} - {m['visitante']}": m for m in matches}
        selected = st.selectbox("Elige un partido", list(choices.keys()))
        match = choices[selected]
        if st.button("Analizar partido", type="primary", use_container_width=True):
            left, right = st.columns(2)
            with left:
                with st.spinner(f"Analizando {match['local']}..."):
                    hr, he = recent_team(match["home_id"])
            with right:
                with st.spinner(f"Analizando {match['visitante']}..."):
                    ar, ae = recent_team(match["away_id"])
            if he or ae:
                st.error(he or ae)
            else:
                xg = estimate_goals(hr, ar)
                if not xg:
                    st.warning("No hay suficientes resultados para estimar este partido.")
                else:
                    hxg, axg = xg
                    probs, matrix = probabilities(hxg, axg)
                    m1, m2, m3 = st.columns(3)
                    m1.metric(f"Goles esperados · {match['local']}", f"{hxg:.2f}")
                    m2.metric(f"Goles esperados · {match['visitante']}", f"{axg:.2f}")
                    m3.metric("Total esperado", f"{hxg+axg:.2f}")
                    st.subheader("Probabilidades estimadas")
                    pdf = pd.DataFrame([
                        {"Mercado": k, "Probabilidad": pct(v), "Cuota justa teórica": f"{1/v:.2f}" if v > 0 else "—"}
                        for k, v in probs.items()
                    ])
                    st.dataframe(pdf, use_container_width=True, hide_index=True)
                    scores = []
                    for h in range(len(matrix)):
                        for a in range(len(matrix[h])):
                            scores.append((matrix[h][a], f"{h}-{a}"))
                    scores.sort(reverse=True)
                    st.write("**Resultados exactos más probables (orientativos):** " + " · ".join(f"{s} ({pct(p)})" for p,s in scores[:5]))
                    st.subheader("Comparador de cuotas")
                    market = st.selectbox("Mercado a comparar", list(probs.keys()))
                    odds = st.number_input("Cuota decimal", min_value=1.01, max_value=100.0, value=1.80, step=0.01)
                    p = probs[market]
                    implied = odds_prob(odds)
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Modelo", pct(p))
                    col2.metric("Probabilidad implícita", pct(implied))
                    col3.metric("Diferencia", f"{(p-implied)*100:+.1f} puntos")
                    if p > implied + 0.05:
                        st.info("El modelo detecta una diferencia positiva, pero el cálculo es básico y no demuestra que exista valor real.")
                    else:
                        st.warning("No aparece una ventaja clara según este modelo.")
                    if st.button("Guardar esta predicción", use_container_width=True):
                        with sqlite3.connect(DB_PATH) as con:
                            con.execute("""INSERT INTO predictions
                                (created_at, match_date, competition, home_team, away_team, home_xg, away_xg, market, probability, odds, result)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                (datetime.now().isoformat(), selected_date.isoformat(), match["competicion"],
                                 match["local"], match["visitante"], hxg, axg, market, p, odds, "Pendiente"))
                        st.success("Predicción guardada en el historial local del servidor.")
                    hist = []
                    for item in (hr or []) + (ar or []):
                        hist.append({"Fecha": item["date"][:10], "Local": item["home_name"],
                                     "Marcador": f"{item['home_goals']} - {item['away_goals']}",
                                     "Visitante": item["away_name"]})
                    st.subheader("Resultados recientes utilizados")
                    st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
                    st.caption("Modelo Poisson básico sobre resultados recientes. No incluye de forma completa xG, lesiones, alineaciones, árbitros ni contexto táctico.")

with tab2:
    st.subheader("Predicciones guardadas")
    with sqlite3.connect(DB_PATH) as con:
        saved = pd.read_sql_query("SELECT * FROM predictions ORDER BY created_at DESC LIMIT 300", con)
    if saved.empty:
        st.info("Todavía no has guardado ninguna predicción.")
    else:
        st.dataframe(saved, use_container_width=True, hide_index=True)
        csv = saved.to_csv(index=False).encode("utf-8")
        st.download_button("Descargar historial CSV", csv, "historial_predicciones.csv", "text/csv", use_container_width=True)

with tab3:
    st.subheader("Importar datos autorizados en CSV")
    st.write("Columnas mínimas: `home_team, away_team, date, home_goals, away_goals`. Opcionales: `home_corners, away_corners, home_cards, away_cards`.")
    uploaded = st.file_uploader("Selecciona un archivo CSV", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            required = {"home_team", "away_team", "date", "home_goals", "away_goals"}
            if not required.issubset(df.columns):
                st.error("Faltan columnas: " + ", ".join(sorted(required - set(df.columns))))
            else:
                df["imported_at"] = datetime.now().isoformat()
                df["source"] = uploaded.name
                with sqlite3.connect(DB_PATH) as con:
                    df.to_sql("imported_matches", con, if_exists="append", index=False)
                st.success(f"Importadas {len(df)} filas.")
        except Exception as exc:
            st.error(f"No se pudo importar el archivo: {exc}")
    with sqlite3.connect(DB_PATH) as con:
        local = pd.read_sql_query("SELECT * FROM imported_matches ORDER BY imported_at DESC LIMIT 300", con)
    if not local.empty:
        st.dataframe(local, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"Consulta de esta sesión: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} · Los datos se actualizan al consultar y al vencer la caché.")
