import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURATION ---
PERSONEN = ["User 1", "User 2"] # Hier eure echten Namen eintragen!
KATEGORIEN = [
    "Müllgebühren", "Schornsteinfeger", "Strom", "Wohngebäude", 
    "Internet", "Haus", "Wasser", "KFZ-Versicherung", 
    "KFZ-Steuer", "Gas", "Streaming", "Kita Essen", 
    "Elternbeitrag", "GEZ", "Privathaftpflicht", "Fahrrad/Leasing", "Sonstiges"
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

# --- SIDEBAR: WER BIST DU? ---
with st.sidebar:
    st.title("🔑 Login")
    current_user = st.selectbox("Wer nutzt die App gerade?", PERSONEN)
    st.info(f"Angemeldet als: {current_user}")
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]

st.title("🏠 Finanz-Manager")

tab1, tab2, tab3 = st.tabs(["📊 Mein Status", "➕ Neu", "📋 Alle Kosten"])

# --- TAB 1: STATUS & INDIVIDUELLE KOSTEN ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today = datetime.now().date()
        
        # Daten filtern: Nur Gemeinsame ODER eigene Sachen
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        my_df['Datum_Check'] = my_df['Nächste Fälligkeit'].dt.date
        
        due_10 = my_df[(my_df['Datum_Check'] >= today - timedelta(days=30)) & 
                       (my_df['Datum_Check'] <= today + timedelta(days=10))]
        
        if not due_10.empty:
            for _, row in due_10.sort_values('Datum_Check').iterrows():
                prefix = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                datum_de = row['Datum_Check'].strftime('%d.%m.%Y')
                if row['Datum_Check'] < today:
                    st.error(f"{prefix} ÜBERFÄLLIG: {row['Kostenart']} ({datum_de})")
                else:
                    st.warning(f"{prefix} {datum_de}: {row['Kostenart']} — {row['Betrag']:,.2f} €")
        else:
            st.success("Keine dringenden Zahlungen.")

        st.divider()

        # --- INDIVIDUELLE BERECHNUNG ---
        st.subheader("💰 Deine monatliche Last")
        
        # 1. Gemeinsame Kosten (geteilt durch 2)
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        my_share_of_shared = shared_total / 2
        
        # 2. Rein private Kosten (100% für den User)
        my_private_total = df[df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        # Gesamtsumme für den User
        total_personal_burden = my_share_of_shared + my_private_total
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus", f"{my_share_of_shared:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        c2.metric("Deine Privaten", f"{my_private_total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        c3.metric("GESAMT", f"{total_personal_burden:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."), delta_color="inverse")
        
        # Hinweis zum Gravelbike (18% Option) - falls als privater Posten eingetragen
        if "Fahrrad" in my_df['Kostenart'].values:
            st.caption("ℹ️ Tipp: Dein Gravelbike-Leasing ist in deinen privaten Kosten enthalten.")

        st.subheader("Kostenverteilung (Gesamt)")
        fig = px.pie(df, values='Monatlich', names='Eigentümer', color='Eigentümer',
                     color_discrete_map={'Gemeinsam':'#00CC96', current_user:'#636EFA', other_user:'#EF553B'})
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: NEUER EINTRAG ---
with tab2:
    st.subheader("Eintrag hinzufügen")
    with st.form("add_form", clear_on_submit=True):
        owner = st.radio("Für wen ist dieser Posten?", ["Gemeinsam", current_user, other_user], horizontal=True)
        art = st.selectbox("Kostenart", KATEGORIEN)
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        intervall = st.selectbox("Turnus", list(INTERVALL_MAP.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now())
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag is not None:
                monatlich = betrag / INTERVALL_MAP[intervall]
                new_entry = pd.DataFrame([{
                    "Eigentümer": owner, "Kostenart": art, "Betrag": betrag, 
                    "Intervall": intervall, "Monatlich": monatlich, "Nächste Fälligkeit": datum
                }])
                updated_df = pd.concat([df, new_entry], ignore_index=True)
                conn.update(worksheet="Nebenkosten", data=updated_df)
                st.success(f"Gespeichert für {owner}!")
                st.rerun()

# --- TAB 3: LISTE ---
with tab3:
    st.subheader("Vollständige Liste")
    # Zeigt alle Daten an, damit beide alles sehen können (Transparenz)
    edited_df = st.data_editor(
        df, num_rows="dynamic", use_container_width=True,
        column_config={
            "Betrag": st.column_config.NumberColumn(format="%.2f €"),
            "Monatlich": st.column_config.NumberColumn(format="%.2f €"),
            "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")
        }
    )
    if st.button("Änderungen in Cloud speichern"):
        conn.update(worksheet="Nebenkosten", data=edited_df)
        st.success("Synchronisiert!")
        st.rerun()
