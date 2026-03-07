import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. KONFIGURATION ---
PERSONEN = ["User 1", "User 2"]  # Trage hier eure Namen ein
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftpflicht", "Sonstiges"
]
INTERVALL_MAP = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}

st.set_page_config(page_title="Haus & Privat App", layout="centered")

# Verbindung zur Cloud (Google Sheets)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty or len(data.columns) < 2:
            return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        # Datum sicher konvertieren
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        return data
    except:
        return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 2. SIDEBAR: LOGIN ---
with st.sidebar:
    st.title("🔑 Login")
    current_user = st.selectbox("Wer nutzt die App gerade?", PERSONEN)
    st.info(f"Angemeldet als: {current_user}")
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]

st.title("🏠 Finanz-Manager")

tab1, tab2, tab3 = st.tabs(["📊 Mein Status", "➕ Neu", "📋 Alle Kosten"])

# --- 3. TAB 1: STATUS & INDIVIDUELLE KOSTEN ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today = pd.Timestamp(datetime.now().date())
        
        # Daten filtern: Gemeinsame Kosten ODER eigene private Sachen
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        
        # Zeitfenster: Letzte 30 Tage (um Überfälliges zu sehen) bis nächste 10 Tage
        start_date = today - pd.Timedelta(days=30)
        end_date = today + pd.Timedelta(days=10)
        
        due_10 = my_df[(my_df['Nächste Fälligkeit'] >= start_date) & 
                       (my_df['Nächste Fälligkeit'] <= end_date)]
        
        if not due_10.empty:
            for _, row in due_10.sort_values('Nächste Fälligkeit').iterrows():
                prefix = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                datum_de = row['Nächste Fälligkeit'].strftime('%d.%m.%Y')
                if row['Nächste Fälligkeit'] < today:
                    st.error(f"{prefix} ÜBERFÄLLIG: {row['Kostenart']} ({datum_de})")
                else:
                    st.warning(f"{prefix} {datum_de}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        else:
            st.success("Keine Zahlungen in den nächsten 10 Tagen.")

        st.divider()

        # --- INDIVIDUELLE BERECHNUNG ---
        st.subheader("💰 Deine monatliche Last")
        
        # Berechnung der Anteile
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        my_share_of_shared = shared_total / 2
        my_private_total = df[df['Eigentümer'] == current_user]["Monatlich"].sum()
        total_personal_burden = my_share_of_shared + my_private_total
        
        def fmt(val):
            return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus", fmt(my_share_of_shared))
        c2.metric("Deine Privaten", fmt(my_private_total))
        c3.metric("GESAMT", fmt(total_personal_burden))
        
        st.subheader("Kostenverteilung (Gesamt)")
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
        intervall = st.selectbox("Turnus", list(INTERVALL_MAP.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now(), format="DD.MM.YYYY")
        
        submitted = st.form_submit_button("✅ Speichern", use_container_width=True)
        
        if submitted:
            if betrag is not None:
                monatlich = betrag / INTERVALL_MAP[intervall]
                new_entry = pd.DataFrame([{
                    "Eigentümer": owner, "Kostenart": art, "Betrag": float(betrag), 
                    "Intervall": intervall, "Monatlich": float(monatlich), "Nächste Fälligkeit": datum
                }])
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                # Als String speichern für Google Sheets Stabilität
                save_df = updated_df.copy()
                save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
                conn.update(worksheet="Nebenkosten", data=save_df)
                st.success(f"Gespeichert für {owner}!")
                st.rerun()
            else:
                st.error("Bitte Betrag eingeben.")

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
        if st.button("Änderungen in Cloud speichern"):
            save_df = edited_df.copy()
            save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].astype(str)
            conn.update(worksheet="Nebenkosten", data=save_df)
            st.success("Synchronisiert!")
            st.rerun()
