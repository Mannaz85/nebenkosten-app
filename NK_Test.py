import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx
import time

# --- 1. SETUP & DESIGN ---
st.set_page_config(page_title="Haus-Manager Pro", layout="wide", page_icon="🏦")

st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        border: 1px solid #d1d5db;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .metric-label { color: #374151; font-size: 14px; margin-bottom: 5px; font-weight: bold; }
    .stButton>button { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KONFIGURATION ---
PERSONEN = ["Philipp", "Miri"] 
INTERVALL_MONATE = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}
HAUPTKATEGORIEN = ["Wohnen & Haushalt", "Mobilität", "Lebensmittel", "Versicherungen", "Abos & Medien", "Freizeit & Urlaub", "Sparen", "Sonstiges"]

def fmt_eur(val):
    if val is None or pd.isna(val): return "0,00 €"
    return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 3. COOKIE & SILENT AUTH LOGIK ---
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()
time.sleep(0.2) # Wichtig: Zeit für den Browser-Handshake

def check_auth_and_user():
    # 1. Silent Auto-Login via Cookie
    auth_cookie = cookie_manager.get("haushalts_auth")
    if auth_cookie and "password" in st.secrets:
        if auth_cookie == st.secrets["password"]:
            st.session_state["authenticated"] = True
    
    # 2. Letzten Nutzer vom Gerät abrufen
    if "current_user" not in st.session_state:
        saved_user = cookie_manager.get("haushalts_user")
        if saved_user in PERSONEN:
            st.session_state["current_user"] = saved_user
        else:
            st.session_state["current_user"] = PERSONEN[0]

check_auth_and_user()

# Login-Screen nur anzeigen, wenn kein gültiger Cookie/Session existiert
if not st.session_state.get("authenticated"):
    st.markdown("<h2 style='text-align: center;'>🏦 Haus-Manager</h2>", unsafe_allow_html=True)
    _, col, _ = st.columns([1,2,1])
    with col:
        with st.form("Login"):
            pwd_input = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                if "password" in st.secrets and pwd_input == st.secrets["password"]:
                    st.session_state["authenticated"] = True
                    # Cookie für 30 Tage setzen
                    cookie_manager.set("haushalts_auth", pwd_input, expires_at=datetime.now() + timedelta(days=30))
                    st.rerun()
                else:
                    st.error("Passwort falsch!")
    st.stop()

# --- 4. DATEN-LOGIK ---
conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    new_hist = []
    for index, row in df.iterrows():
        if pd.notnull(row['Nächste Fälligkeit']):
            curr_due = row['Nächste Fälligkeit'].date() if hasattr(row['Nächste Fälligkeit'], 'date') else row['Nächste Fälligkeit']
            if curr_due <= today:
                new_hist.append({"Datum": curr_due.strftime('%Y-%m-%d'), "Eigentümer": row.get('Eigentümer',''), "Typ": row.get('Typ','Ausgabe'), "Kostenart": row.get('Kostenart',''), "Betrag": row.get('Betrag',0.0)})
                turnus = str(row['Intervall']).strip().lower()
                if turnus in INTERVALL_MONATE:
                    new_date = pd.to_datetime(row['Nächste Fälligkeit'])
                    while new_date.date() <= today: new_date = new_date + relativedelta(months=INTERVALL_MONATE[turnus])
                    df.at[index, 'Nächste Fälligkeit'] = new_date
                    updated = True
    if updated:
        save_df = df.copy(); save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        if new_hist:
            try: h_df = conn.read(worksheet="Historie", ttl="0m")
            except: h_df = pd.DataFrame(columns=["Datum", "Eigentümer", "Typ", "Kostenart", "Betrag"])
            h_df = pd.concat([h_df, pd.DataFrame(new_hist)], ignore_index=True)
            conn.update(worksheet="Historie", data=h_df)
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty: return pd.DataFrame(columns=["Eigentümer", "Typ", "Hauptkategorie", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        data.columns = [c.strip() for c in data.columns]
        if "Typ" not in data.columns: data["Typ"] = "Ausgabe"
        if "Hauptkategorie" not in data.columns: data["Hauptkategorie"] = "Sonstiges"
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        return check_and_update_dates(data)
    except: return pd.DataFrame(columns=["Eigentümer", "Typ", "Hauptkategorie", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("👤 Profil")
    try:
        default_idx = PERSONEN.index(st.session_state["current_user"])
    except:
        default_idx = 0
    current_user = st.selectbox("Wer bist du?", PERSONEN, index=default_idx)
    
    if current_user != st.session_state.get("current_user"):
        st.session_state["current_user"] = current_user
        cookie_manager.set("haushalts_user", current_user, expires_at=datetime.now() + timedelta(days=90))
    
    st.divider()
    if not df.empty:
        st.download_button("💾 Backup CSV", df.to_csv(index=False).encode('utf-8'), "finanz_backup.csv", "text/csv", use_container_width=True)
    if st.button("🚪 Logout", use_container_width=True):
        cookie_manager.delete("haushalts_auth")
        st.session_state["authenticated"] = False
        st.rerun()

# --- 6. HAUPTSEITE ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste", "📖 Log"])

with tab1:
    if not df.empty:
        aus_df = df[df['Typ'] == "Ausgabe"]; ein_df = df[df['Typ'] == "Einnahme"]
        st.subheader("🔔 Fälligkeiten")
        t_ts = pd.Timestamp(datetime.now().date())
        my_aus = aus_df[(aus_df['Eigentümer'] == "Gemeinsam") | (aus_df['Eigentümer'] == current_user)]
        due = my_aus[(my_aus['Nächste Fälligkeit'] >= t_ts) & (my_aus['Nächste Fälligkeit'] <= t_ts + pd.Timedelta(days=14))].sort_values("Nächste Fälligkeit")
        
        if not due.empty:
            for _, r in due.iterrows():
                st.warning(f"**{r['Nächste Fälligkeit'].strftime('%d.%m.')}**: {r['Kostenart']} ({fmt_eur(r['Betrag'])})")
        else: st.success("Alles erledigt!")
        
        st.divider()
        st.subheader("👫 Gemeinsame Kosten (Monat)")
        sh_aus_total = aus_df[aus_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        c_sh1, c_sh2 = st.columns(2)
        with c_sh1:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Gesamt Haus</p><h2 style="color: #111827; margin:0;">{fmt_eur(sh_aus_total)}</h2></div>', unsafe_allow_html=True)
        with c_sh2:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Pro Nase (50%)</p><h2 style="color: #111827; margin:0;">{fmt_eur(sh_aus_total/2)}</h2></div>', unsafe_allow_html=True)

        st.divider()
        st.subheader(f"💰 Finanz-Check: {current_user}")
        sh_ein_half = ein_df[ein_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum() / 2
        pr_aus = aus_df[aus_df['Eigentümer'] == current_user]["Monatlich"].sum()
        pr_ein = ein_df[ein_df['Eigentümer'] == current_user]["Monatlich"].sum()
        inc = pr_ein + sh_ein_half; exp = pr_aus + (sh_aus_total / 2); free = inc - exp
        color = "#28a745" if free > 0 else "#dc3545" if free < 0 else "#111827"

        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1: st.markdown(f'<div class="metric-card"><p class="metric-label">Einnahmen</p><h2 style="color: #111827; margin:0;">{fmt_eur(inc)}</h2></div>', unsafe_allow_html=True)
        with c_f2: st.markdown(f'<div class="metric-card"><p class="metric-label">Ausgaben</p><h2 style="color: #111827; margin:0;">{fmt_eur(exp)}</h2></div>', unsafe_allow_html=True)
        with c_f3: st.markdown(f'<div class="metric-card"><p class="metric-label">Freies Budget</p><h2 style="color: {color}; margin:0;">{fmt_eur(free)}</h2></div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("📊 Ausgaben-Verteilung")
        if not my_aus.empty:
            fig = px.pie(my_aus.groupby("Hauptkategorie")["Monatlich"].sum().reset_index(), values='Monatlich', names='Hauptkategorie', hole=0.5)
            fig.update_layout(margin=dict(t=30, b=20, l=10, r=10), height=400, showlegend=True)
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True, 'displayModeBar': False})

with tab2:
    st.subheader("➕ Neu")
    t = st.radio("Typ", ["Ausgabe", "Einnahme"], horizontal=True)
    with st.form("new_entry", clear_on_submit=True):
        o = st.radio("Wer?", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        k = st.selectbox("Kategorie", HAUPTKATEGORIEN if t=="Ausgabe" else ["Gehalt", "Zinsen", "Sonstiges"])
        n = st.text_input("Bezeichnung")
        v = st.number_input("Betrag €", step=0.01)
        tur = st.selectbox("Intervall", list(INTERVALL_MONATE.keys()))
        d = st.date_input("Datum", format="DD.MM.YYYY")
        if st.form_submit_button("Speichern", use_container_width=True):
            if v and n:
                monat = float(v)/INTERVALL_MONATE[tur]
                new = pd.DataFrame([{"Eigentümer":o, "Typ":t, "Hauptkategorie":k, "Kostenart":n, "Betrag":float(v), "Intervall":tur, "Monatlich":monat, "Nächste Fälligkeit":pd.to_datetime(d)}])
                upd = pd.concat([df, new], ignore_index=True); s = upd.copy(); s['Nächste Fälligkeit'] = s['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Nebenkosten", data=s); st.success("Gespeichert!"); st.rerun()

with tab3:
    st.subheader("📋 Liste")
    ed = st.data_editor(df, use_container_width=True, num_rows="dynamic", column_config={"Betrag": st.column_config.NumberColumn(format="%.2f €"), "Monatlich": st.column_config.NumberColumn(format="%.2f €"), "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")})
    if st.button("💾 Speichern"):
        s = ed.copy(); s['Monatlich'] = s.apply(lambda r: float(r['Betrag'])/INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
        s['Nächste Fälligkeit'] = pd.to_datetime(s['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=s); st.rerun()

with tab4:
    st.subheader("📖 Logbuch")
    try:
        h = conn.read(worksheet="Historie", ttl="0m")
        if not h.empty: st.dataframe(h.sort_values("Datum", ascending=False), use_container_width=True)
    except: st.info("Noch leer.")
