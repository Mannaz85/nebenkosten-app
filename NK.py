import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- CONFIGURATION ---
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftplicht"
]
INTERVALL_MAP = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}

st.set_page_config(page_title="NK-App Cloud", layout="centered")

# Verbindung zur Cloud (Google Sheets)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # Lädt die Daten frisch aus der Cloud
    return conn.read(worksheet="Nebenkosten", ttl="0m")

# Daten initial laden
df = load_data()

st.title("🏠 Haus-Manager Cloud")

# Mobile Navigation über Tabs
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        # Monatliche Kosten berechnen
        gesamt = df["Monatlich"].sum()
        jeder = gesamt / 2
        
        c1, c2 = st.columns(2)
        c1.metric("Gesamt / Monat", f"{gesamt:.2f} €")
        c2.metric("pro Nase / Monat", f"{jeder:.2f} €")
        
        st.divider()
        st.subheader("Verteilung")
        fig = px.pie(df, values='Monatlich', names='Kostenart', hole=.4)
        fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Noch keine Daten in der Cloud.")

# --- TAB 2: EINTRAGEN ---
with tab2:
    st.subheader("Neuer Eintrag")
    with st.form("add_form", clear_on_submit=True):
        art = st.selectbox("Kostenart", KATEGORIEN)
        betrag = st.number_input("Betrag in €", min_value=0.0, step=1.0)
        intervall = st.selectbox("Turnus", list(INTERVALL_MAP.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now())
        
        if st.form_submit_button("✅ In Cloud speichern", use_container_width=True):
            monatlich = betrag / INTERVALL_MAP[intervall]
            new_entry = pd.DataFrame([{
                "Kostenart": art, "Betrag": betrag, "Intervall": intervall, 
                "Monatlich": monatlich, "Nächste Fälligkeit": str(datum)
            }])
            # Bestehende Daten mit neuem Eintrag kombinieren und hochladen
            updated_df = pd.concat([df, new_entry], ignore_index=True)
            conn.update(worksheet="Nebenkosten", data=updated_df)
            st.success("Gespeichert!")
            st.rerun()

# --- TAB 3: VERWALTEN ---
with tab3:
    st.subheader("Alle Einträge")
    if not df.empty:
        # Editierbare Tabelle zum Löschen oder Ändern
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Monatlich": st.column_config.NumberColumn(format="%.2f €"),
                "Betrag": st.column_config.NumberColumn(format="%.2f €"),
            }
        )
        if st.button("Änderungen synchronisieren"):
            conn.update(worksheet="Nebenkosten", data=edited_df)
            st.success("Cloud aktualisiert!")
            st.rerun()
    else:
        st.write("Die Liste ist leer.")
