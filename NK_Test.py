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

# --- 3. COOKIE & AUTH LOGIK ---
@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()
time.sleep(0.1) 

def check_auth_and_user():
    if not st.session_state.get("authenticated"):
        auth_cookie = cookie_manager.get("haushalts_auth")
        if auth_cookie and "password" in st.secrets and auth_cookie == st.secrets["password"]:
            st.session_state["authenticated"] = True
    
    if "current_user" not in st.session_state:
        saved_user = cookie_manager.get("haushalts_user")
        if saved_user in PERSONEN:
            st.session_state["current_user"] = saved_user
        else:
            st.session_state["current_user"] = PERSONEN[0]

check_auth_and_user()

if not st.session_state.get("authenticated"):
    st.markdown("<h2 style='text-align: center;'>🏦 Haus-Manager Login</h2>", unsafe_allow_html=True)
    _, col, _ = st.columns([1,2,1])
    with col:
        with st.form("Login"):
            pwd_input = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                if "password" in st.secrets and pwd_input == st.secrets["password"]:
                    st.session_state["authenticated"] = True
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

# --- 6. HAUPTSEITE (TABS) ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste", "📖 Log"])

with tab1:
    if not df
