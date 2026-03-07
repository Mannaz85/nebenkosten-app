import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. MODERNES DESIGN (CSS) ---
st.set_page_config(page_title="Haus-Manager Pro", layout="wide", page_icon="🏦")

# Wir injizieren etwas CSS für abgerundete Ecken und Schatten
st.markdown("""
    <style>
    /* Hintergrund und Karten-Design */
    .stApp {
        background-color: #f8f9fa;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 15px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
    }
    /* Tab-Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #ffffff;
        border-radius: 10px 10px 0px 0px;
        gap: 1px;
        padding: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #636EFA !important;
        color: white !important;
    }
    /* Buttons abrunden */
    .stButton>button {
        border-radius: 10px;
        border: none;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0px 4px 15px rgba(0,0,0,0.1);
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

# --- 3. SICHERHEIT (LOGIN) ---
def get_manager(): return stx.CookieManager()
cookie_manager = get_manager()

def check_password():
    if st.session_state.get("authenticated"): return True
    auth_cookie = cookie_manager.get("haushalts_auth")
    if "password" in st.secrets and auth_cookie == st.secrets["password"]:
        st.session_state["authenticated"] = True
        return True
    
    st.markdown("<h1 style='text-align: center;'>🏦 Haus-Manager</h1>", unsafe_allow_html=True)
    with st.container():
        _, col, _ = st.columns([1,2,1])
        with col:
            with st.form("Login"):
                pwd_input = st.text_input("Passwort", type="password")
                rem = st.checkbox("30 Tage angemeldet bleiben", value=True)
                if st.form_submit_button("Anmelden", use_container_width=True):
                    if "password" in st.secrets and pwd_input == st.secrets["password"]:
                        st.session_state["authenticated"] = True
                        if rem: cookie_manager.set("haushalts_auth", pwd_input, expires_at=datetime.now() + timedelta(days=30))
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
        st.toast("📅 Termine aktualisiert!", icon="🔄")
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
    current_user = st.selectbox("Nutzer", PERSONEN)
    st.divider()
    if not df.empty:
        st.download_button("💾 Backup CSV", df.to_csv(index=False).encode('utf-8'), "backup.csv", "text/csv", use_container_width=True)
    if st.button("🚪 Logout", use_container_width=True):
        cookie_manager.delete("haushalts_auth"); st.session_state["authenticated"] = False; st.rerun()

# --- 6. TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "➕ Neu", "📋 Liste", "📖 Historie"])

with tab1:
    if not df.empty:
        # BUDGET BERECHNUNG
        aus_df = df[df['Typ'] == "Ausgabe"]; ein_df = df[df['Typ'] == "Einnahme"]
        sh_aus = aus_df[aus_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        sh_ein = ein_df[ein_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum() / 2
        pr_aus = aus_df[aus_df['Eigentümer'] == current_user]["Monatlich"].sum()
        pr_ein = ein_df[ein_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        inc = pr_ein + sh_ein; load = pr_aus + (sh_aus / 2); free = inc - load

        # MODERN METRICS
        st.subheader("💳 Finanzieller Überblick")
        m1, m2, m3 = st.columns(3)
        m1.metric("Einnahmen", fmt_eur(inc))
        m2.metric("Ausgaben", fmt_eur(load))
        m3.metric("Freies Budget", fmt_eur(free), delta=f"{free:,.2f} €", delta_color="normal")

        with st.expander("🔍 Kosten-Details (Monatlich)"):
            d1, d2, d3 = st.columns(3)
            d1.write(f"**Privat {current_user}**\n{fmt_eur(pr_aus)}")
            d2.write(f"**Anteil Haus (50%)**\n{fmt_eur(sh_aus/2)}")
            d3.write(f"**Haus Gesamt (100%)**\n{fmt_eur(sh_aus)}")

        st.divider()

        # TERMINE ALS CARDS
        st.subheader("🔔 Nächste Termine")
        t_ts = pd.Timestamp(datetime.now().date())
        my_aus = aus_df[(aus_df['Eigentümer'] == "Gemeinsam") | (aus_df['Eigentümer'] == current_user)]
        due = my_aus[(my_aus['Nächste Fälligkeit'] >= t_ts) & (my_aus['Nächste Fälligkeit'] <= t_ts + pd.Timedelta(days=14))].sort_values("Nächste Fälligkeit")
        
        if not due.empty:
            cols = st.columns(len(due[:4]))
            for i, (_, r) in enumerate(due[:4].iterrows()):
                with cols[i]:
                    st.info(f"**{r['Nächste Fälligkeit'].strftime('%d.%m.')}**\n{r['Kostenart']}\n{fmt_eur(r['Betrag'])}")
        else: st.success("Alles erledigt!")

        st.divider()

        # CHARTS
        st.subheader("📊 Analyse")
        c1, c2 = st.columns(2)
        with c1:
            if not my_aus.empty:
                fig = px.pie(my_aus.groupby("Hauptkategorie")["Monatlich"].sum().reset_index(), values='Monatlich', names='Hauptkategorie', hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            if not my_aus.empty:
                bar = px.bar(my_aus.groupby("Kostenart")["Monatlich"].sum().reset_index().sort_values("Monatlich", ascending=False).head(5), x="Monatlich", y="Kostenart", orientation='h', color_discrete_sequence=['#636EFA'])
                bar.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300, yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(bar, use_container_width=True)

with tab2:
    st.subheader("➕ Neue Transaktion")
    typ = st.radio("Was?", ["Ausgabe", "Einnahme"], horizontal=True)
    with st.form("new", clear_on_submit=True):
        o = st.radio("Besitzer", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        c1, c2 = st.columns(2)
        with c1: kat = st.selectbox("Kategorie", HAUPTKATEGORIEN if typ=="Ausgabe" else ["Gehalt", "Kindergeld", "Zinsen"])
        with c2: name = st.text_input("Bezeichnung")
        val = st.number_input("Betrag €", min_value=0.0, step=0.01)
        cc1, cc2 = st.columns(2)
        with cc1: tur = st.selectbox("Intervall", list(INTERVALL_MONATE.keys()))
        with cc2: d = st.date_input("Datum", datetime.now(), format="DD.MM.YYYY")
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if val and name:
                new = pd.DataFrame([{"Eigentümer":o, "Typ":typ, "Hauptkategorie":kat, "Kostenart":name, "Betrag":float(val), "Intervall":tur, "Monatlich":float(val)/INTERVALL_MONATE[tur], "Nächste Fälligkeit":pd.to_datetime(d)}])
                upd = pd.concat([df, new], ignore_index=True); s = upd.copy(); s['Nächste Fälligkeit'] = s['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Nebenkosten", data=s); st.rerun()

with tab3:
    if not df.empty:
        st.subheader("📋 Liste bearbeiten")
        ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 Speichern"):
            s = ed.copy(); s['Monatlich'] = s.apply(lambda r: float(r['Betrag'])/INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
            s['Nächste Fälligkeit'] = pd.to_datetime(s['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Nebenkosten", data=s); st.rerun()

with tab4:
    st.subheader("📖 Historie")
    try:
        h = conn.read(worksheet="Historie", ttl="0m")
        if not h.empty: st.dataframe(h.sort_values("Datum", ascending=False), use_container_width=True)
    except: st.info("Noch leer.")
