import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. KONFIGURATION & SETUP ---
PERSONEN = ["Philipp", "Miri"] 
INTERVALL_MONATE = {
    "monatlich": 1, 
    "quartalsweise": 3, 
    "halbjährlich": 6, 
    "jährlich": 12
}

HAUPTKATEGORIEN = [
    "Wohnen & Haushalt", "Mobilität", "Lebensmittel", "Nebenkosten",
    "Versicherungen", "Abos & Medien", "Freizeit & Urlaub", "Kita",
    "Kredite", "Sonstiges"
]

st.set_page_config(page_title="Haus-Manager Pro", layout="wide", page_icon="🏦")

def fmt_eur(val):
    if val is None or pd.isna(val): return "0,00 €"
    return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

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

# --- 3. DATEN-LOGIK (INKL. HISTORIE & MIGRATION) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    new_history = []
    
    for index, row in df.iterrows():
        if pd.notnull(row['Nächste Fälligkeit']):
            current_due = row['Nächste Fälligkeit'].date() if hasattr(row['Nächste Fälligkeit'], 'date') else row['Nächste Fälligkeit']
            
            if current_due <= today:
                # 1. Eintrag für die Historie vormerken
                new_history.append({
                    "Datum": current_due.strftime('%Y-%m-%d'),
                    "Eigentümer": row.get('Eigentümer', ''),
                    "Typ": row.get('Typ', 'Ausgabe'),
                    "Kostenart": row.get('Kostenart', ''),
                    "Betrag": row.get('Betrag', 0.0)
                })
                
                # 2. Datum in die Zukunft schieben
                turnus = str(row['Intervall']).strip().lower()
                if turnus in INTERVALL_MONATE:
                    monate_plus = INTERVALL_MONATE[turnus]
                    new_date = pd.to_datetime(row['Nächste Fälligkeit'])
                    while new_date.date() <= today:
                        new_date = new_date + relativedelta(months=monate_plus)
                    df.at[index, 'Nächste Fälligkeit'] = new_date
                    updated = True
                    
    if updated:
        save_df = df.copy()
        save_df['Nächste Fälligkeit'] = save_df['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Nebenkosten", data=save_df)
        
        if new_history:
            try:
                hist_df = conn.read(worksheet="Historie", ttl="0m")
            except:
                hist_df = pd.DataFrame(columns=["Datum", "Eigentümer", "Typ", "Kostenart", "Betrag"])
            
            hist_df = pd.concat([hist_df, pd.DataFrame(new_history)], ignore_index=True)
            conn.update(worksheet="Historie", data=hist_df)
            
        st.toast("🔄 Termine verlängert & im Logbuch gespeichert!", icon="📖")
        
    return df

def load_data():
    try:
        data = conn.read(worksheet="Nebenkosten", ttl="0m")
        if data.empty:
            return pd.DataFrame(columns=["Eigentümer", "Typ", "Hauptkategorie", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])
        
        data.columns = [c.strip() for c in data.columns]
        
        if "Typ" not in data.columns: data["Typ"] = "Ausgabe"
        if "Hauptkategorie" not in data.columns: data["Hauptkategorie"] = "Sonstiges"
        
        data['Nächste Fälligkeit'] = pd.to_datetime(data['Nächste Fälligkeit'], errors='coerce')
        data = data.dropna(subset=['Nächste Fälligkeit'])
        
        return check_and_update_dates(data)
    except Exception as e:
        st.error(f"Datenfehler beim Laden: {e}")
        return pd.DataFrame(columns=["Eigentümer", "Typ", "Hauptkategorie", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 4. SIDEBAR (PROFIL & BACKUP) ---
with st.sidebar:
    st.title("👤 Profil")
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    
    st.divider()
    st.subheader("💾 Backup")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Daten als CSV herunterladen",
            data=csv,
            file_name=f'finanz_backup_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv',
            use_container_width=True
        )
    
    st.divider()
    if st.button("Abmelden", use_container_width=True):
        cookie_manager.delete("haushalts_auth")
        st.session_state["authenticated"] = False
        st.rerun()

# --- 5. TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "➕ Neu", "📋 Liste", "📖 Historie"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        ausgaben_df = df[df['Typ'] == "Ausgabe"].copy()
        einnahmen_df = df[df['Typ'] == "Einnahme"].copy()
        
        st.subheader(f"🔔 Anstehend für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        my_ausgaben = ausgaben_df[(ausgaben_df['Eigentümer'] == "Gemeinsam") | (ausgaben_df['Eigentümer'] == current_user)]
        due_soon = my_ausgaben[(my_ausgaben['Nächste Fälligkeit'] >= today_ts) & 
                               (my_ausgaben['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=14))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                icon = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{icon} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: {row['Kostenart']} — {fmt_eur(row['Betrag'])}")
        else:
            st.success("Keine Zahlungen in den nächsten 14 Tagen.")
            
        st.divider()

        shared_ausg = ausgaben_df[ausgaben_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        shared_einn = einnahmen_df[einnahmen_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        
        priv_ausg = ausgaben_df[ausgaben_df['Eigentümer'] == current_user]["Monatlich"].sum()
        priv_einn = einnahmen_df[einnahmen_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        total_income = priv_einn + (shared_einn / 2)
        total_expense = priv_ausg + (shared_ausg / 2)
        free_budget = total_income - total_expense

        st.subheader("💳 Dein Freies Budget (Monat)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Einnahmen", fmt_eur(total_income))
        col2.metric("Ausgaben", fmt_eur(total_expense))
        col3.metric("Freies Budget", fmt_eur(free_budget), delta=f"{free_budget:,.2f} €".replace(".", ","), delta_color="normal")

        st.divider()

        st.subheader("📊 Ausgaben-Analyse")
        gc1, gc2 = st.columns(2)
        
        with gc1:
            st.write("**Nach Hauptkategorien**")
            if not my_ausgaben.empty:
                pie_df = my_ausgaben.groupby("Hauptkategorie")["Monatlich"].sum().reset_index()
                fig_pie = px.pie(pie_df, values='Monatlich', names='Hauptkategorie', hole=0.4)
                fig_pie.update_layout(showlegend=True, height=350, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_pie, use_container_width=True)
                
        with gc2:
            st.write("**Größte Einzelposten**")
            if not my_ausgaben.empty:
                bar_df = my_ausgaben.groupby("Kostenart")["Monatlich"].sum().reset_index().sort_values("Monatlich", ascending=False).head(8)
                fig_bar = px.bar(bar_df, x="Monatlich", y="Kostenart", orientation='h', text_auto='.0f', color="Monatlich", color_continuous_scale="Blues")
                fig_bar.update_layout(showlegend=False, height=350, yaxis={'categoryorder':'total ascending'}, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_bar, use_container_width=True)
                
    else:
        st.info("Noch keine Daten vorhanden.")

# --- TAB 2: NEUER EINTRAG (FIXED) ---
with tab2:
    st.subheader("Transaktion hinzufügen")
    
    # FIX: Die Auswahl für Einnahme/Ausgabe steht jetzt AUSSERHALB des Formulars.
    # Dadurch reagiert Streamlit sofort auf deinen Klick.
    typ = st.radio("Was möchtest du eintragen?", ["Ausgabe", "Einnahme"], horizontal=True)
    st.write("---")
    
    with st.form("new_form", clear_on_submit=True):
        own = st.radio("Wem gehört es?", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        
        c1, c2 = st.columns(2)
        with c1:
            # Die Liste passt sich nun dynamisch an, je nachdem was oben geklickt wurde
            if typ == "Ausgabe":
                hauptkat = st.selectbox("Hauptkategorie", HAUPTKATEGORIEN)
            else:
                hauptkat = st.selectbox("Hauptkategorie", ["Gehalt", "Kindergeld", "Sonstige Einnahme"])
                
        with c2:
            kostenart = st.text_input("Genaue Bezeichnung", placeholder="z.B. Netflix, Strom, Gehalt...")
            
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        
        cc1, cc2 = st.columns(2)
        with cc1:
            turnus = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        with cc2:
            datum = st.date_input("Erste / Nächste Fälligkeit", datetime.now(), format="DD.MM.YYYY")
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag and kostenart:
                monat = float(betrag) / INTERVALL_MONATE[turnus]
                new_row = pd.DataFrame([{
                    "Eigentümer": own, 
                    "Typ": typ,
                    "Hauptkategorie": hauptkat,
                    "Kostenart": kostenart.strip(), 
                    "Betrag": float(betrag),
                    "Intervall": turnus, 
                    "Monatlich": float(monat), 
                    "Nächste Fälligkeit": pd.to_datetime(datum)
                }])
                updated = pd.concat([df, new_row], ignore_index=True)
                save = updated.copy()
                save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Nebenkosten", data=save)
                st.success(f"{typ} '{kostenart}' gespeichert!")
                st.rerun()
            else:
                st.error("Bitte Bezeichnung und Betrag angeben.")

# --- TAB 3: LISTE (EDITOR) ---
with tab3:
    st.subheader("Alle Einträge bearbeiten")
    if not df.empty:
        edited = st.data_editor(
            df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Typ": st.column_config.SelectboxColumn("Typ", options=["Ausgabe", "Einnahme"]),
                "Hauptkategorie": st.column_config.SelectboxColumn("Kategorie", options=HAUPTKATEGORIEN + ["Gehalt", "Kindergeld", "Sonstige Einnahme"]),
                "Betrag": st.column_config.NumberColumn("Betrag", format="%.2f €"),
                "Monatlich": st.column_config.NumberColumn("Monatlich", format="%.2f €"),
                "Nächste Fälligkeit": st.column_config.DateColumn("Fälligkeit", format="DD.MM.YYYY")
            }
        )
        if st.button("💾 Änderungen in Cloud speichern"):
            save = edited.copy()
            save['Monatlich'] = save.apply(lambda r: float(r['Betrag']) / INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
            save['Nächste Fälligkeit'] = pd.to_datetime(save['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Nebenkosten", data=save)
            st.success("Tabelle aktualisiert!")
            st.rerun()

# --- TAB 4: HISTORIE (LOGBUCH) ---
with tab4:
    st.subheader("📖 Logbuch der Zahlungen")
    st.write("Hier wird automatisch protokolliert, wenn eine Zahlung ihr Fälligkeitsdatum erreicht hat.")
    try:
        hist_df = conn.read(worksheet="Historie", ttl="0m")
        if not hist_df.empty:
            hist_df['Datum'] = pd.to_datetime(hist_df['Datum']).dt.strftime('%d.%m.%Y')
            st.dataframe(
                hist_df.sort_values("Datum", ascending=False), 
                use_container_width=True,
                column_config={"Betrag": st.column_config.NumberColumn("Betrag", format="%.2f €")}
            )
        else:
            st.info("Das Logbuch ist noch leer.")
    except:
        st.info("Das Logbuch wird beim ersten automatischen Termin-Update erstellt.")
