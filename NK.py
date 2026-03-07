import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURATION ---
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftpflicht"
]
INTERVALL_MAP = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}

st.set_page_config(page_title="NK-App Cloud", layout="centered")

# Verbindung zur Cloud (Google Sheets)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    data = conn.read(worksheet="Nebenkosten", ttl="0m")
    # Sicherstellen, dass das Datum als Datetime-Objekt vorliegt
    if not data.empty:
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
    return data

df = load_data()

st.title("🏠 Haus-Manager")

# Mobile Navigation
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste"])

# --- TAB 1: STATUS & KOSTEN (10 TAGE CHECK) ---
with tab1:
    if not df.empty:
        st.subheader("🔔 Fälligkeiten (nächste 10 Tage)")
        today = datetime.now().date()
        
        # Filter: Überfällig & die nächsten 10 Tage
        # Wir arbeiten mit einer Kopie für die Anzeige
        df_status = df.copy()
        df_status['Datum_Check'] = df_status['Nächste Fälligkeit'].dt.date
        
        overdue = df_status[df_status['Datum_Check'] < today]
        due_soon = df_status[(df_status['Datum_Check'] >= today) & 
                           (df_status['Datum_Check'] <= today + timedelta(days=10))]

        if not overdue.empty:
            for _, row in overdue.iterrows():
                # Deutsches Datumsformat: %d.%m.%Y
                datum_de = row['Datum_Check'].strftime('%d.%m.%Y')
                st.error(f"⚠️ ÜBERFÄLLIG: {row['Kostenart']} ({datum_de})")
        
        if not due_soon.empty:
            for _, row in due_soon.iterrows():
                datum_de = row['Datum_Check'].strftime('%d.%m.%Y')
                st.warning(f"⏰ Fällig am {datum_de}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        
        if overdue.empty and due_soon.empty:
            st.success("✅ Keine Zahlungen in den nächsten 10 Tagen fällig.")

        st.divider()

        # --- KOSTEN-ÜBERSICHT (PRO PERSON) ---
        st.subheader("💰 Monatliche Kosten")
        gesamt = df["Monatlich"].sum()
        jeder = gesamt / 2
        
        c1, c2 = st.columns(2)
        # Metriken mit deutscher Formatierung (Komma als Dezimaltrenner)
        c1.metric("Gesamt / Monat", f"{gesamt:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        c2.metric("Pro Person", f"{jeder:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        
        st.subheader("Verteilung")
        fig = px.pie(df, values='Monatlich', names='Kostenart', hole=.4)
        fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Noch keine Daten vorhanden.")

# --- TAB 2: OPTIMIERTE EINGABE ---
with tab2:
    st.subheader("Neuer Eintrag")
    with st.form("add_form", clear_on_submit=True):
        art = st.selectbox("Kostenart", KATEGORIEN)
        
        # Feld ist leer beim Start durch value=None
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="Hier Betrag eingeben...")
        
        intervall = st.selectbox("Turnus", list(INTERVALL_MAP.keys()))
        # Datumsauswahl im deutschen Sprachraum oft standardmäßig korrekt, 
        # hier wird das gewählte Datum beim Speichern formatiert.
        datum = st.date_input("Nächste Zahlung", datetime.now())
        
        if st.form_submit_button("✅ In Cloud speichern", use_container_width=True):
            if betrag is not None:
                monatlich = betrag / INTERVALL_MAP[intervall]
                new_entry = pd.DataFrame([{
                    "Kostenart": art, "Betrag": betrag, "Intervall": intervall, 
                    "Monatlich": monatlich, "Nächste Fälligkeit": datum
                }])
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                conn.update(worksheet="Nebenkosten", data=updated_df)
                st.success(f"Gespeichert: {betrag:,.2f} € für {art}")
                st.rerun()
            else:
                st.error("Bitte gib einen Betrag ein.")

# --- TAB 3: LISTE MIT DEUTSCHEM FORMAT ---
with tab3:
    st.subheader("Alle Einträge")
    if not df.empty:
        # Konfiguration für deutsches Format in der Tabelle
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Betrag": st.column_config.NumberColumn("Betrag", format="%.2f €"),
                "Monatlich": st.column_config.NumberColumn("Monatlich", format="%.2f €"),
                "Nächste Fälligkeit": st.column_config.DateColumn(
                    "Nächste Fälligkeit",
                    format="DD.MM.YYYY"  # Erzwingt deutsches Datumsformat in der Liste
                )
            }
        )
        if st.button("Änderungen synchronisieren"):
            conn.update(worksheet="Nebenkosten", data=edited_df)
            st.success("Cloud aktualisiert!")
            st.rerun()
