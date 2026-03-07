import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. KONFIGURATION ---
PERSONEN = ["Philipp", "Miri"]  # Hier eure Namen anpassen
INTERVALL_MONATE = {
    "monatlich": 1, 
    "quartalsweise": 3, 
    "halbjährlich": 6, 
    "jährlich": 12
}

st.set_page_config(page_title="Haus-Manager Pro", layout="centered")

# Hilfsfunktion für Euro-Anzeige (1.234,56 €)
def fmt_eur(val):
    if val is None or pd.isna(val): return "0,00 €"
    return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 2. SICHERHEIT (PASSWORT & COOKIES) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

def check_password():
    if st.session_state.get("authenticated"):
        return True
    
    # Cookie auslesen
    auth_cookie = cookie_manager.get("haushalts_auth")
    if "password" in st.secrets and auth_cookie == st.secrets["password"]:
        st.session_state["authenticated"] = True
        return True

    st.title("🔐 Haus-Manager Login")
    with st.container(border=True):
        st.write("Bitte gib das Passwort ein:")
        pwd_input = st.text_input("Passwort", type="password", label_visibility="collapsed")
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

# --- 3. DATEN-LOGIK (AUTO-UPDATE & LADEN) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    
    for index, row in df.iterrows():
        if pd.notnull(row['Nächste Fälligkeit']):
            # Sicherstellen, dass wir mit einem Datumsobjekt arbeiten
            current_due = row['Nächste Fälligkeit'].date() if hasattr(row['Nächste Fälligkeit'], 'date') else row['Nächste Fälligkeit']
            
            # Falls Termin HEUTE oder in der VERGANGENHEIT liegt
            if current_due <= today:
                turnus = str(row['Intervall']).strip().lower()
                if turnus in INTERVALL_MONATE:
                    monate_plus = INTERVALL_MONATE[turnus]
                    new_date = pd.to_datetime(row['Nächste Fälligkeit'])
                    
                    # Datum erhöhen bis es in der Zukunft liegt
                    while new_date.date() <= today:
                        new_date = new_date + relativedelta(months=monate_plus)
                    
                    df.at[index, 'Nächste Fälligkeit'] = new_date
                    updated = True
    
    if updated:
        save_df = df.copy()
        save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        st.toast("🔄 Termine automatisch aktualisiert!", icon="📅")
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty:
            return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        
        # Spalten säubern (Groß/Kleinschreibung & Leerzeichen)
        data.columns = [c.strip() for c in data.columns]
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        
        # Kaputte Zeilen ohne Datum entfernen
        data = data.dropna(subset=['Nächste Fälligkeit'])
        
        # Automatische Termin-Aktualisierung prüfen
        return check_and_update_dates(data)
    except Exception as e:
        st.error(f"Fehler beim Laden der Cloud-Daten: {e}")
        return pd.DataFrame(columns=["Eigentümer", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("👤 Dein Profil")
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]
    st.divider()
    if st.button("Abmelden"):
        cookie_manager.delete("haushalts_auth")
        st.session_state["authenticated"] = False
        st.rerun()

# --- 5. HAUPTSEITE (TABS) ---
st.title("🏠 Haus & Privat Manager")
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Alle Kosten"])

# --- TAB 1: STATUS & DASHBOARD ---
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        
        # Filter für relevante Kosten (Gemeinsam + Eigene)
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        due_soon = my_df[(my_df['Nächste Fälligkeit'] >= today_ts) & 
                         (my_df['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=14))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                icon = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{icon} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: **{row['Kostenart']}** — {fmt_eur(row['Betrag'])}")
        else:
            st.success("Keine Zahlungen in den nächsten 14 Tagen.")

        st.divider()

        # Berechnungen der Last
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        p1_priv = df[df['Eigentümer'] == PERSONEN[0]]["Monatlich"].sum()
        p2_priv = df[df['Eigentümer'] == PERSONEN[1]]["Monatlich"].sum()
        
        p1_total = (shared_total / 2) + p1_priv
        p2_total = (shared_total / 2) + p2_priv
        
        curr_priv = p1_priv if current_user == PERSONEN[0] else p2_priv
        curr_total = p1_total if current_user == PERSONEN[0] else p2_total

        st.subheader("💰 Deine monatliche Last")
        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus (50%)", fmt_eur(shared_total/2))
        c2.metric("Deine Privaten", fmt_eur(curr_priv))
        c3.metric("GESAMT", fmt_eur(curr_total))

        st.divider()
        st.subheader("⚖️ Wer trägt wie viel?")
        compare_df = pd.DataFrame({"Person": PERSONEN, "Euro": [p1_total, p2_total]})
        fig = px.bar(compare_df, x="Person", y="Euro", color="Person", text_auto='.2f',
                     color_discrete_map={PERSONEN[0]: '#636EFA', PERSONEN[1]: '#EF553B'})
        fig.update_layout(showlegend=False, height=350, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
        
        diff = abs(p1_total - p2_total)
        st.caption(f"Differenz zwischen euch: {fmt_eur(diff)} pro Monat.")
    else:
        st.info("Noch keine Daten vorhanden. Nutze Tab 'Neu', um Kosten einzutragen.")

# --- TAB 2: NEUER EINTRAG (SMART SEARCH) ---
with tab2:
    st.subheader("Neuen Posten hinzufügen")
    
    # Kategorien aus Bestand laden
    existing_cats = sorted(df['Kostenart'].unique().tolist()) if not df.empty else []
    
    if "selected_art" not in st.session_state: 
        st.session_state.selected_art = ""
    
    # Suchfeld (Reagiert sofort am Handy)
    art_input = st.text_input("Kostenart suchen oder eintippen", 
                              value=st.session_state.selected_art, 
                              placeholder="z.B. Strom, Kita, Versicherung...")
    
    # Vorschläge einblenden
    if art_input and not any(art_input.lower() == c.lower() for c in existing_cats):
        matches = [c for c in existing_cats if art_input.lower() in c.lower()]
        if matches:
            st.write("💡 Meintest du:")
            cols = st.columns(len(matches[:3]))
            for i, m in enumerate(matches[:3]):
                if cols[i].button(m, key=f"sug_{i}", use_container_width=True):
                    st.session_state.selected_art = m
                    st.rerun()

    # Das Formular für die restlichen Daten
    with st.form("main_entry_form", clear_on_submit=True):
        owner = st.radio("Eigentümer", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        turnus = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        datum = st.date_input("Erste Fälligkeit", datetime.now())
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            final_name = art_input.strip() if art_input else st.session_state.selected_art
            
            if betrag and final_name:
                monat = float(betrag) / INTERVALL_MONATE[turnus]
                # Datum als Timestamp für Pandas-Kompatibilität
                new_row = pd.DataFrame([{
                    "Eigentümer": owner, 
                    "Kostenart": final_name, 
                    "Betrag": float(betrag),
                    "Intervall": turnus, 
                    "Monatlich": float(monat), 
                    "Nächste Fälligkeit": pd.to_datetime(datum)
                }])
                
                # In die Cloud schieben
                updated = pd.concat([df, new_row], ignore_index=True)
                save = updated.copy()
                save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                
                conn.update(worksheet="Nebenkosten", data=save)
                st.session_state.selected_art = ""
                st.success(f"'{final_name}' wurde gespeichert!")
                st.rerun()
            else:
                st.error("Bitte Kategorie und Betrag angeben.")

# --- TAB 3: ALLE KOSTEN (EDITOR) ---
with tab3:
    st.subheader("Vollständige Übersicht")
    if not df.empty:
        st.info("Tippe in eine Zelle zum Ändern oder lösche Zeilen mit der 'Entf'-Taste.")
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Betrag": st.column_config.NumberColumn(format="%.2f €"),
                "Monatlich": st.column_config.NumberColumn(format="%.2f €"),
                "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")
            }
        )
        
        if st.button("💾 Änderungen in Cloud speichern"):
            save = edited_df.copy()
            # Vor dem Speichern sicherstellen, dass Monatlich neu berechnet wurde (falls Betrag/Intervall geändert wurde)
            save['Monatlich'] = save.apply(lambda r: float(r['Betrag']) / INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
            save['Nächste Fälligkeit'] = pd.to_datetime(save['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
            
            conn.update(worksheet="Nebenkosten", data=save)
            st.success("Cloud-Tabelle erfolgreich aktualisiert!")
            st.rerun()
