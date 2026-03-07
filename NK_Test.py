import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURATION ---
# Hier eure echten Namen eintragen!
PERSONEN = ["Philipp", "Miri"] 
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftpflicht", "Sonstiges"
]
INTERVALL_MAP = {"monatlich": 1, "quartalsweise": 3, "halbjährlich": 6, "jährlich": 12}

st.set_page_config(page_title="Haus & Privat App", layout="centered")

# Verbindung zur Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    data = conn.read(worksheet="Nebenkosten", ttl="0m")
    if not data.empty:
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
    return data

df = load_data()

# --- SIDEBAR: LOGIN ---
with st.sidebar:
    st.title("🔑 Login")
    current_user = st.selectbox("Wer nutzt die App gerade?", PERSONEN)
    st.info(f"Angemeldet als: {current_user}")
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]

st.title("🏠 Finanz-Manager")

tab1, tab2, tab3 = st.tabs(["📊 Mein Status", "➕ Neu", "📋 Alle Kosten"])

# --- TAB 1: STATUS & KOSTEN ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        
        # FIX: Wir nutzen pd.Timestamp für absolute Kompatibilität
        today = pd.Timestamp(datetime.now().date())
        
        # Daten kopieren und sicherstellen, dass alles Timestamps sind
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        my_df['Nächste Fälligkeit'] = pd.to_datetime(my_df['Nächste Fälligkeit'])
        
        # Zeitfenster berechnen (heute minus 30 Tage bis heute plus 10 Tage)
        start_date = today - pd.Timedelta(days=30)
        end_date = today + pd.Timedelta(days=10)
        
        # Der Vergleich funktioniert jetzt, da beide Seiten Timestamps sind
        due_10 = my_df[(my_df['Nächste Fälligkeit'] >= start_date) & 
                       (my_df['Nächste Fälligkeit'] <= end_date)]
        
        if not due_10.empty:
            for _, row in due_10.sort_values('Nächste Fälligkeit').iterrows():
                prefix = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                # Anzeige im deutschen Format
                datum_de = row['Nächste Fälligkeit'].strftime('%d.%m.%Y')
                
                if row['Nächste Fälligkeit'] < today:
                    st.error(f"{prefix} ÜBERFÄLLIG: {row['Kostenart']} ({datum_de})")
                else:
                    st.warning(f"{prefix} {datum_de}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        else:
            st.success("Keine dringenden Zahlungen.")
        # --- INDIVIDUELLE BERECHNUNG ---
        st.subheader("💰 Deine monatliche Last")
        
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        my_share_of_shared = shared_total / 2
        my_private_total = df[df['Eigentümer'] == current_user]["Monatlich"].sum()
        total_personal_burden = my_share_of_shared + my_private_total
        
        c1, c2, c3 = st.columns(3)
        # Formatierung mit Tausenderpunkt und Komma
        def fmt(val):
            return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        c1.metric("Anteil Haus", fmt(my_share_of_shared))
        c2.metric("Deine Privaten", fmt(my_private_total))
        c3.metric("GESAMT", fmt(total_personal_burden))
        
        st.subheader("Kostenverteilung (Gesamt)")
        fig = px.pie(df, values='Monatlich', names='Eigentümer', color='Eigentümer',
                     color_discrete_map={'Gemeinsam':'#00CC96', current_user:'#636EFA', other_user:'#EF553B'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Noch keine Daten vorhanden.")

# --- TAB 2: OPTIMIERTE EINGABE ---
with tab2:
    st.subheader("Eintrag hinzufügen")
    with st.form("add_form", clear_on_submit=True):
        owner = st.radio("Für wen?", ["Gemeinsam", current_user, other_user], horizontal=True)
        art = st.selectbox("Kostenart", KATEGORIEN)
        
        # Betrag-Feld (leer beim Start)
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        
        intervall = st.selectbox("Turnus", list(INTERVALL_MAP.keys()))
        
        # --- DATUMSFELD IN DEUTSCHEM FORMAT ---
        datum = st.date_input(
            "Nächste Zahlung", 
            value=datetime.now(),
            format="DD.MM.YYYY"  # Dies erzwingt die Anzeige TT.MM.JJJJ im Widget
        )
        
        # Der wichtige Submit-Button (muss eingerückt bleiben!)
        submitted = st.form_submit_button("✅ Speichern", use_container_width=True)
        
        if submitted:
            if betrag is not None:
                monatlich = betrag / INTERVALL_MAP[intervall]
                new_entry = pd.DataFrame([{
                    "Eigentümer": owner, 
                    "Kostenart": art, 
                    "Betrag": betrag, 
                    "Intervall": intervall, 
                    "Monatlich": monatlich, 
                    "Nächste Fälligkeit": datum
                }])
                
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                conn.update(worksheet="Nebenkosten", data=updated_df)
                st.success(f"Gespeichert für {owner}!")
                st.rerun()
            else:
                st.error("Bitte gib einen Betrag ein.")
