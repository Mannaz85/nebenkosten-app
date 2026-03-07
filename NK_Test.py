import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. KONFIGURATION ---
PERSONEN = ["Philipp", "Miri"] 
INTERVALL_MONATE = {
    "monatlich": 1, 
    "quartalsweise": 3, 
    "halbjährlich": 6, 
    "jährlich": 12
}

st.set_page_config(page_title="Haus-Manager Pro", layout="centered")

# --- 2. SICHERHEIT (LOGIN & COOKIES) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

def check_password():
    if st.session_state.get("authenticated"):
        return True
    auth_cookie = cookie_manager.get("haushalts_auth")
    if "password" in st.secrets and auth_cookie == st.secrets["password"]:
        st.session_state["authenticated"] = True
        return True
    st.title("🔐 Haus-Manager Login")
    with st.container(border=True):
        pwd_input = st.text_input("Passwort", type="password")
        remember_me = st.checkbox("30 Tage angemeldet bleiben", value=True)
        if st.button("Anmelden", use_container_width=True):
            if "password" in st.secrets and pwd_input == st.secrets["password"]:
                st.session_state["authenticated"] = True
                if remember_me:
                    expires_at = datetime.now() + timedelta(days=30)
                    cookie_manager.set("haushalts_auth", pwd_input, expires_at=expires_at)
                st.rerun()
            else:
                st.error("Passwort falsch!")
    return False

if not check_password():
    st.stop()

# --- 3. DATEN-LOGIK (MIT AUTO-UPDATE FIX) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    # Wir nehmen "heute" als Zeitstempel ohne Uhrzeit
    today = datetime.now().date()
    updated = False
    
    for index, row in df.iterrows():
        # Falls das Datum erreicht oder überschritten ist (<= statt <)
        if pd.notnull(row['Nächste Fälligkeit']):
            current_due_date = row['Nächste Fälligkeit'].date()
            
            if current_due_date <= today:
                # Intervall-Text säubern (Leerzeichen weg, alles klein)
                turnus = str(row['Intervall']).strip().lower()
                
                if turnus in INTERVALL_MONATE:
                    monate_plus = INTERVALL_MONATE[turnus]
                    new_date = row['Nächste Fälligkeit']
                    
                    # Datum so lange erhöhen, bis es wirklich in der Zukunft liegt
                    while new_date.date() <= today:
                        new_date = new_date + relativedelta(months=monate_plus)
                    
                    df.at[index, 'Nächste Fälligkeit'] = new_date
                    updated = True
    
    if updated:
        # Kopie für Google Sheets (Datum als Text speichern)
        save_df = df.copy()
        save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        st.toast("🔄 Fälligkeiten wurden aktualisiert!", icon="📅")
    
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty:
            return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        
        # Spaltennamen säubern (verhindert KeyErrors durch Leerzeichen)
        data.columns = [c.strip() for c in data.columns]
        
        # Datum konvertieren
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        
        # Sofort prüfen, ob etwas aktualisiert werden muss
        return check_and_update_dates(data)
    except Exception as e:
        st.error(f"Datenfehler: {e}")
        return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("👤 Profil")
    current_user = st.selectbox("Wer bist du?", PERSONEN)
    if st.button("Abmelden"):
        cookie_manager.delete("haushalts_auth")
        st.session_state["authenticated"] = False
        st.rerun()

# --- 5. TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste"])

# TAB 1: DASHBOARD
with tab1:
    if not df.empty:
        st.subheader(f"Anstehend für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        
        # Filter: Eigene Kosten & Gemeinsame
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        # Zeige alles, was in den nächsten 14 Tagen kommt
        due_soon = my_df[(my_df['Nächste Fälligkeit'] >= today_ts) & 
                         (my_df['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=14))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                icon = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{icon} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: {row['Kostenart']} ({row['Betrag']:.2f} €)")
        else:
            st.success("Aktuell keine dringenden Zahlungen.")

# TAB 2: NEU (SMART SEARCH)
with tab2:
    st.subheader("Eintrag hinzufügen")
    existing_cats = sorted(df['Kostenart'].unique().tolist()) if not df.empty else []
    
    if "selected_art" not in st.session_state: st.session_state.selected_art = ""
    
    art_input = st.text_input("Kostenart", value=st.session_state.selected_art, placeholder="Tippen zum Suchen...")
    
    if art_input and not any(art_input.lower() == c.lower() for c in existing_cats):
        matches = [c for c in existing_cats if art_input.lower() in c.lower()]
        if matches:
            cols = st.columns(len(matches[:3]))
            for i, m in enumerate(matches[:3]):
                if cols[i].button(m, key=f"m_{i}"):
                    st.session_state.selected_art = m
                    st.rerun()

    with st.form("new_form", clear_on_submit=True):
        own = st.radio("Wer?", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        betrag = st.number_input("Betrag €", min_value=0.0, step=0.01, value=None)
        turnus = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        datum = st.date_input("Erste Fälligkeit", datetime.now())
        
        if st.form_submit_button("Speichern", use_container_width=True):
            final_art = art_input if art_input else st.session_state.selected_art
            if betrag and final_art:
                monat = float(betrag) / INTERVALL_MONATE[turnus]
                new_row = pd.DataFrame([{"Eigentümer": own, "Kostenart": final_art, "Betrag": float(betrag),
                                         "Intervall": turnus, "Monatlich": float(monat), "Nächste Fälligkeit": datum}])
                # Speichern und sofort neu laden
                updated = pd.concat([df, new_row], ignore_index=True)
                save = updated.copy()
                save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].astype(str)
                conn.update(worksheet="Nebenkosten", data=save)
                st.session_state.selected_art = ""
                st.rerun()

# TAB 3: LISTE
with tab3:
    if not df.empty:
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Synchronisieren"):
            save = edited.copy()
            save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].astype(str)
            conn.update(worksheet="Nebenkosten", data=save)
            st.rerun()
