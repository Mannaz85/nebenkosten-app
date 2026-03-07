import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. SICHERHEIT (PASSWORT) ---
def check_password():
    """Gibt True zurück, wenn das Passwort korrekt ist."""
    if "password" not in st.secrets:
        st.error("Passwort in den Secrets nicht gesetzt!")
        return False
    
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    with st.sidebar:
        st.title("🔒 Login")
        pwd_input = st.text_input("App-Passwort", type="password")
        if st.button("Anmelden"):
            if pwd_input == st.secrets["password"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Falsches Passwort!")
    return False

# App stoppen, wenn nicht eingeloggt
if not check_password():
    st.info("Bitte melde dich in der Seitenleiste an, um deine Daten zu sehen.")
    st.stop()

# --- 2. KONFIGURATION & DATEN ---
PERSONEN = ["Philipp", "Miri"]
INTERVALL_MONATE = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}

conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    for index, row in df.iterrows():
        if pd.notnull(row['Nächste Fälligkeit']) and row['Nächste Fälligkeit'].date() < today:
            turnus = str(row['Intervall']).lower()
            if turnus in INTERVALL_MONATE:
                monate_plus = INTERVALL_MONATE[turnus]
                current_date = row['Nächste Fälligkeit']
                while current_date.date() < today:
                    current_date = current_date + relativedelta(months=monate_plus)
                df.at[index, 'Nächste Fälligkeit'] = current_date
                updated = True
    if updated:
        save_df = df.copy()
        save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        st.toast("📅 Termine aktualisiert!", icon="🔄")
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty or len(data.columns) < 2:
            return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        return check_and_update_dates(data)
    except:
        return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 3. UI LAYOUT ---
with st.sidebar:
    st.divider()
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]
    if st.button("Abmelden"):
        st.session_state["authenticated"] = False
        st.rerun()

st.title("🏠 Finanz-Manager")
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        due_soon = my_df[(my_df['Nächste Fälligkeit'] >= today_ts) & (my_df['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=10))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                prefix = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{prefix} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        else:
            st.success("Keine Zahlungen in den nächsten 10 Tagen.")

        st.divider()
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        my_private = df[df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus", f"{shared_total/2:,.2f} €")
        c2.metric("Deine Privaten", f"{my_private:,.2f} €")
        c3.metric("GESAMT", f"{(shared_total/2)+my_private:,.2f} €")

# --- TAB 2: NEUER EINTRAG (DYNAMISCHE KATEGORIEN) ---
with tab2:
    st.subheader("Eintrag hinzufügen")
    
    # Vorhandene Kategorien aus der Spalte lesen
    if not df.empty:
        existing_cats = sorted(df['Kostenart'].unique().tolist())
    else:
        existing_cats = ["Miete", "Strom", "Internet"] # Start-Kategorien

    with st.form("add_form", clear_on_submit=True):
        owner = st.radio("Für wen?", ["Gemeinsam", current_user, other_user], horizontal=True)
        
        col_cat, col_new = st.columns([1, 1])
        with col_cat:
            art_select = st.selectbox("Kategorie wählen", existing_cats + ["+ Neue Kategorie..."])
        with col_new:
            if art_select == "+ Neue Kategorie...":
                art_final = st.text_input("Name der neuen Kategorie", placeholder="z.B. Fitnessstudio")
            else:
                art_final = art_select

        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        intervall = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now(), format="DD.MM.YYYY")
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag and art_final:
                monatlich = betrag / INTERVALL_MONATE[intervall]
                new_entry = pd.DataFrame([{"Eigentümer": owner, "Kostenart": art_final, "Betrag": float(betrag), 
                                           "Intervall": intervall, "Monatlich": float(monatlich), "Nächste Fälligkeit": datum}])
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                save_df = updated_df.copy()
                save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
                conn.update(worksheet="Nebenkosten", data=save_df)
                st.success(f"Gespeichert: {art_final}")
                st.rerun()
            else:
                st.error("Bitte Betrag und Kategorie angeben.")

# --- TAB 3: LISTE ---
with tab3:
    st.subheader("Vollständige Liste")
    if not df.empty:
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Änderungen synchronisieren"):
            save_df = edited_df.copy()
            save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
            conn.update(worksheet="Nebenkosten", data=save_df)
            st.success("Synchronisiert!")
            st.rerun()
