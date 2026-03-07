import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. KONFIGURATION ---
PERSONEN = ["User 1", "User 2"]
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftpflicht", "Sonstiges"
]
# Mapping für die automatische Berechnung (Monate)
INTERVALL_MONATE = {
    "monatlich": 1, 
    "quartalsweise": 3, 
    "halbjährlich": 6, 
    "jährlich": 12
}

st.set_page_config(page_title="Haus & Privat App", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

# --- NEU: FUNKTION ZUM AUTOMATISCHEN WEITERSCHALTEN ---
def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    
    for index, row in df.iterrows():
        # Falls das Datum in der Vergangenheit liegt
        if pd.notnull(row['Nächste Fälligkeit']) and row['Nächste Fälligkeit'].date() < today:
            turnus = row['Intervall'].lower()
            if turnus in INTERVALL_MONATE:
                monate_plus = INTERVALL_MONATE[turnus]
                # Datum so lange erhöhen, bis es in der Zukunft liegt
                current_date = row['Nächste Fälligkeit']
                while current_date.date() < today:
                    current_date = current_date + relativedelta(months=monate_plus)
                
                df.at[index, 'Nächste Fälligkeit'] = current_date
                updated = True
    
    if updated:
        # Kopie zum Speichern (Datum als String für Google Sheets)
        save_df = df.copy()
        save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        st.toast("📅 Termine wurden automatisch aktualisiert!", icon="🔄")
    
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty or len(data.columns) < 2:
            return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        # Automatische Aktualisierung der Termine beim Laden
        data = check_and_update_dates(data)
        return data
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 2. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.title("🔑 Login")
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]

st.title("🏠 Finanz-Manager")
tab1, tab2, tab3 = st.tabs(["📊 Mein Status", "➕ Neu", "📋 Alle Kosten"])

# --- 3. TAB 1: STATUS ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        end_date = today_ts + pd.Timedelta(days=10)
        
        # Nur die nächsten 10 Tage anzeigen (Überfälliges wurde ja gerade weggeschaltet)
        due_soon = my_df[(my_df['Nächste Fälligkeit'] >= today_ts) & 
                         (my_df['Nächste Fälligkeit'] <= end_date)]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                prefix = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                datum_de = row['Nächste Fälligkeit'].strftime('%d.%m.%Y')
                st.warning(f"{prefix} {datum_de}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        else:
            st.success("Keine Zahlungen in den nächsten 10 Tagen.")

        st.divider()

        # --- BERECHNUNG ---
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        my_private_total = df[df['Eigentümer'] == current_user]["Monatlich"].sum()
        total_burden = (shared_total / 2) + my_private_total
        
        def fmt(val):
            return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus", fmt(shared_total/2))
        c2.metric("Deine Privaten", fmt(my_private_total))
        c3.metric("GESAMT", fmt(total_burden))
        
        fig = px.pie(df, values='Monatlich', names='Eigentümer', color='Eigentümer',
                     color_discrete_map={'Gemeinsam':'#00CC96', PERSONEN[0]:'#636EFA', PERSONEN[1]:'#EF553B'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Noch keine Daten vorhanden.")

# --- 4. TAB 2: NEUER EINTRAG ---
with tab2:
    st.subheader("Eintrag hinzufügen")
    with st.form("add_form", clear_on_submit=True):
        owner = st.radio("Für wen?", ["Gemeinsam", current_user, other_user], horizontal=True)
        art = st.selectbox("Kostenart", KATEGORIEN)
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        intervall = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now(), format="DD.MM.YYYY")
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag is not None:
                monatlich = betrag / INTERVALL_MONATE[intervall]
                new_entry = pd.DataFrame([{
                    "Eigentümer": owner, "Kostenart": art, "Betrag": float(betrag), 
                    "Intervall": intervall, "Monatlich": float(monatlich), "Nächste Fälligkeit": datum
                }])
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                # Datum für Cloud als String
                save_df = updated_df.copy()
                save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
                conn.update(worksheet="Nebenkosten", data=save_df)
                st.success(f"Gespeichert!")
                st.rerun()

# --- 5. TAB 3: ALLE KOSTEN (LISTE) ---
with tab3:
    st.subheader("Vollständige Liste")
    if not df.empty:
        edited_df = st.data_editor(
            df, num_rows="dynamic", use_container_width=True,
            column_config={
                "Betrag": st.column_config.NumberColumn(format="%.2f €"),
                "Monatlich": st.column_config.NumberColumn(format="%.2f €"),
                "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")
            }
        )
        if st.button("Änderungen synchronisieren"):
            save_df = edited_df.copy()
            save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
            conn.update(worksheet="Nebenkosten", data=save_df)
            st.success("Synchronisiert!")
            st.rerun()
