import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. DESIGN & CSS (MOBIL-OPTIMIERT) ---
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

# --- 3. SICHERHEIT ---
def get_manager(): return stx.CookieManager()
cookie_manager = get_manager()

def check_password():
    if st.session_state.get("authenticated"): return True
    auth_cookie = cookie_manager.get("haushalts_auth")
    if "password" in st.secrets and auth_cookie == st.secrets["password"]:
        st.session_state["authenticated"] = True
        return True
    st.markdown("<h2 style='text-align: center;'>🏦 Haus-Manager Login</h2>", unsafe_allow_html=True)
    with st.container():
        _, col, _ = st.columns([1,2,1])
        with col:
            with st.form("Login"):
                pwd_input = st.text_input("Passwort", type="password")
                if st.form_submit_button("Anmelden", use_container_width=True):
                    if "password" in st.secrets and pwd_input == st.secrets["password"]:
                        st.session_state["authenticated"] = True
                        cookie_manager.set("haushalts_auth", pwd_input, expires_at=datetime.now() + timedelta(days=30))
                        st.rerun()
                    else: st.error("Falsch!")
    return False

if not check_password(): st.stop()

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
    current_user = st.selectbox("Wer bist du?", PERSONEN)
    st.divider()
    if not df.empty:
        st.download_button("💾 Backup CSV", df.to_csv(index=False).encode('utf-8'), "finanz_backup.csv", "text/csv", use_container_width=True)
    if st.button("🚪 Logout", use_container_width=True):
        cookie_manager.delete("haushalts_auth"); st.session_state["authenticated"] = False; st.rerun()

# --- 6. HAUPTSEITE (TABS) ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste", "📖 Log"])

with tab1:
    if not df.empty:
        aus_df = df[df['Typ'] == "Ausgabe"]; ein_df = df[df['Typ'] == "Einnahme"]
        
        # 1. FÄLLIGKEITEN (UMBENANNT)
        st.subheader("🔔 Fälligkeiten")
        t_ts = pd.Timestamp(datetime.now().date())
        my_aus = aus_df[(aus_df['Eigentümer'] == "Gemeinsam") | (aus_df['Eigentümer'] == current_user)]
        due = my_aus[(my_aus['Nächste Fälligkeit'] >= t_ts) & (my_aus['Nächste Fälligkeit'] <= t_ts + pd.Timedelta(days=14))].sort_values("Nächste Fälligkeit")
        
        if not due.empty:
            for _, r in due.iterrows():
                st.warning(f"**{r['Nächste Fälligkeit'].strftime('%d.%m.')}**: {r['Kostenart']} ({fmt_eur(r['Betrag'])})")
        else: st.success("Keine anstehenden Zahlungen.")
        
        st.divider()

        # 2. MONATLICHE GEMEINSAME KOSTEN
        st.subheader("👫 Gemeinsame Kosten (Monat)")
        sh_aus_total = aus_df[aus_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        c_sh1, c_sh2 = st.columns(2)
        with c_sh1:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Gesamt Haus</p><h2 style="color: #111827; margin:0;">{fmt_eur(sh_aus_total)}</h2></div>', unsafe_allow_html=True)
        with c_sh2:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Pro Nase (50%)</p><h2 style="color: #111827; margin:0;">{fmt_eur(sh_aus_total/2)}</h2></div>', unsafe_allow_html=True)

        st.divider()

        # 3. FINANZ-CHECK (DYNAMISCHE FARBEN)
        st.subheader(f"💰 Finanz-Check: {current_user}")
        sh_ein_half = ein_df[ein_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum() / 2
        pr_aus = aus_df[aus_df['Eigentümer'] == current_user]["Monatlich"].sum()
        pr_ein = ein_df[ein_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        total_inc = pr_ein + sh_ein_half
        total_exp = pr_aus + (sh_aus_total / 2)
        free_budget = total_inc - total_exp

        # Farblogik
        budget_color = "#28a745" if free_budget > 0 else "#dc3545" if free_budget < 0 else "#111827"

        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Deine Einnahmen</p><h2 style="color: #111827; margin:0;">{fmt_eur(total_inc)}</h2></div>', unsafe_allow_html=True)
        with c_f2:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Deine Ausgaben</p><h2 style="color: #111827; margin:0;">{fmt_eur(total_exp)}</h2></div>', unsafe_allow_html=True)
        with c_f3:
            st.markdown(f'<div class="metric-card"><p class="metric-label">Freies Budget</p><h2 style="color: {budget_color}; margin:0;">{fmt_eur(free_budget)}</h2></div>', unsafe_allow_html=True)

        st.divider()

        # 4. ANALYSE (PIE CHART MIT LEGENDE)
        st.subheader("📊 Ausgaben-Verteilung")
        if not my_aus.empty:
            fig = px.pie(my_aus.groupby("Hauptkategorie")["Monatlich"].sum().reset_index(), 
                         values='Monatlich', names='Hauptkategorie', hole=0.5)
            fig.update_layout(margin=dict(t=30, b=20, l=10, r=10), height=400, showlegend=True)
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True, 'displayModeBar': False})

# (Tab 2, 3 und 4 bleiben funktional identisch für Datensicherheit)
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
                new = pd.DataFrame([{"Eigentümer":o, "Typ":t, "Hauptkategorie":k, "Kostenart":n, "Betrag":float(v), "Intervall":tur, "Monatlich":float(v)/INTERVALL_MONATE[tur], "Nächste Fälligkeit":pd.to_datetime(d)}])
                upd = pd.concat([df, new], ignore_index=True); s = upd.copy(); s['Nächste Fälligkeit'] = s['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Nebenkosten", data=s); st.rerun()

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
    except: st.info("Kein Verlauf.")
