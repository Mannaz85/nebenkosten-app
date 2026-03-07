import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. MOBIL-OPTIMIERTES DESIGN (CSS FIX) ---
st.set_page_config(page_title="Haus-Manager Pro", layout="wide", page_icon="🏦")

st.markdown("""
    <style>
    /* Hintergrund-Fix für Lesbarkeit */
    .stApp {
        background-color: transparent;
    }
    /* Metriken: Hintergrund und Textfarbe festlegen */
    div[data-testid="stMetric"] {
        background-color: #f0f2f6 !important;
        border: 1px solid #d1d5db !important;
        padding: 15px !important;
        border-radius: 12px !important;
    }
    /* Text in Metriken erzwingen (Fix für Weiß-auf-Weiß) */
    [data-testid="stMetricLabel"] > div {
        color: #374151 !important; /* Dunkelgrau */
    }
    [data-testid="stMetricValue"] > div {
        color: #111827 !important; /* Fast Schwarz */
    }
    /* Info-Boxen am Handy besser lesbar */
    .stAlert {
        border-radius: 10px;
        border: none;
    }
    /* Tabs am Handy */
    .stTabs [data-baseweb="tab"] {
        font-size: 14px;
        padding: 8px;
    }
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
    
    st.markdown("<h2 style='text-align: center;'>🏦 Haus-Manager</h2>", unsafe_allow_html=True)
    with st.container():
        _, col, _ = st.columns([1,3,1])
        with col:
            with st.form("Login"):
                pwd_input = st.text_input("Passwort", type="password")
                if st.form_submit_button("Anmelden", use_container_width=True):
                    if "password" in st.secrets and pwd_input == st.secrets["password"]:
                        st.session_state["authenticated"] = True
                        cookie_manager.set("haushalts_auth", pwd_input, expires_at=datetime.now() + timedelta(days=30))
                        st.rerun()
                    else: st.error("Passwort falsch!")
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

# --- 5. TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste", "📖 Log"])

with tab1:
    if not df.empty:
        # BUDGET BERECHNUNG
        aus_df = df[df['Typ'] == "Ausgabe"]; ein_df = df[df['Typ'] == "Einnahme"]
        sh_aus = aus_df[aus_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        sh_ein = ein_df[ein_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum() / 2
        pr_aus = aus_df[aus_df['Eigentümer'] == current_user]["Monatlich"].sum()
        pr_ein = ein_df[ein_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        inc = pr_ein + sh_ein; load = pr_aus + (sh_aus / 2); free = inc - load

        # KENNZAHLEN (Dunkler Text erzwungen)
        st.subheader("Finanz-Check")
        m1, m2, m3 = st.columns(3)
        m1.metric("Einnahmen", fmt_eur(inc))
        m2.metric("Ausgaben", fmt_eur(load))
        m3.metric("Über", fmt_eur(free))

        with st.expander("🔍 Details"):
            st.write(f"Privat: {fmt_eur(pr_aus)} | Haus (50%): {fmt_eur(sh_aus/2)}")

        st.divider()

        # TERMINE
        st.subheader("🔔 Nächste Termine")
        t_ts = pd.Timestamp(datetime.now().date())
        my_aus = aus_df[(aus_df['Eigentümer'] == "Gemeinsam") | (aus_df['Eigentümer'] == current_user)]
        due = my_aus[(my_aus['Nächste Fälligkeit'] >= t_ts) & (my_aus['Nächste Fälligkeit'] <= t_ts + pd.Timedelta(days=14))].sort_values("Nächste Fälligkeit")
        
        if not due.empty:
            for _, r in due.iterrows():
                st.warning(f"**{r['Nächste Fälligkeit'].strftime('%d.%m.')}**: {r['Kostenart']} ({fmt_eur(r['Betrag'])})")
        else: st.success("Alles im Plan!")

        st.divider()

        # CHARTS (STATISCH - Nicht mehr veränderbar)
        st.subheader("📊 Analyse")
        c1, c2 = st.columns(2)
        # Konfiguration für statische Plots
        chart_config = {'staticPlot': True, 'displayModeBar': False}
        
        with c1:
            if not my_aus.empty:
                fig = px.pie(my_aus.groupby("Hauptkategorie")["Monatlich"].sum().reset_index(), values='Monatlich', names='Hauptkategorie', hole=0.5)
                fig.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=300, showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config=chart_config)
        with c2:
            if not my_aus.empty:
                bar = px.bar(my_aus.groupby("Kostenart")["Monatlich"].sum().reset_index().sort_values("Monatlich", ascending=False).head(5), x="Monatlich", y="Kostenart", orientation='h')
                bar.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=300, yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(bar, use_container_width=True, config=chart_config)

# (Restliche Tabs bleiben funktional gleich, nur die Anzeige wurde optimiert)
with tab2:
    st.subheader("➕ Neu")
    t = st.radio("Typ", ["Ausgabe", "Einnahme"], horizontal=True)
    with st.form("new_entry"):
        o = st.radio("Wer?", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        k = st.selectbox("Kategorie", HAUPTKATEGORIEN if t=="Ausgabe" else ["Gehalt", "Zinsen"])
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
    ed = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    if st.button("💾 Liste Synchronisieren"):
        s = ed.copy(); s['Monatlich'] = s.apply(lambda r: float(r['Betrag'])/INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
        s['Nächste Fälligkeit'] = pd.to_datetime(s['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=s); st.rerun()

with tab4:
    st.subheader("📖 Logbuch")
    try:
        h = conn.read(worksheet="Historie", ttl="0m")
        if not h.empty: st.dataframe(h.sort_values("Datum", ascending=False), use_container_width=True)
    except: st.info("Noch kein Verlauf.")
