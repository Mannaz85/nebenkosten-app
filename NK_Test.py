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
    "Wohnen & Haushalt", "Mobilität", "Lebensmittel", 
    "Versicherungen", "Abos & Medien", "Freizeit & Urlaub", 
    "Sparen", "Sonstiges"
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

# --- 3. DATEN-LOGIK (AUTO-UPDATE & LADEN) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def check_and_update_dates(df):
    today = datetime.now().date()
    updated = False
    new_history = []
    
    for index, row in df.iterrows():
        if pd.notnull(row['Nächste Fälligkeit']):
            current_due = row['Nächste Fälligkeit'].date() if hasattr(row['Nächste Fälligkeit'], 'date') else row['Nächste Fälligkeit']
            if current_due <= today:
                new_history.append({
                    "Datum": current_due.strftime('%Y-%m-%d'),
                    "Eigentümer": row.get('Eigentümer', ''),
                    "Typ": row.get('Typ', 'Ausgabe'),
                    "Kostenart": row.get('Kostenart', ''),
                    "Betrag": row.get('Betrag', 0.0)
                })
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
        st.toast("🔄 Termine verlängert & Logbuch aktualisiert!", icon="📖")
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
        st.error(f"Datenfehler: {e}")
        return pd.DataFrame(columns=["Eigentümer", "Typ", "Hauptkategorie", "Kostenart", "Betrag", "Intervall", "Monatlich", "Nächste Fälligkeit"])

df = load_data()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("👤 Profil")
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    st.divider()
    st.subheader("💾 Backup")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Daten als CSV exportieren", data=csv, file_name=f'finanz_backup.csv', mime='text/csv', use_container_width=True)
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
        
        # A. TERMINE
        st.subheader(f"🔔 Anstehend für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        my_ausgaben = ausgaben_df[(ausgaben_df['Eigentümer'] == "Gemeinsam") | (ausgaben_df['Eigentümer'] == current_user)]
        due_soon = my_ausgaben[(my_ausgaben['Nächste Fälligkeit'] >= today_ts) & (my_ausgaben['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=14))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                icon = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{icon} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: {row['Kostenart']} — {fmt_eur(row['Betrag'])}")
        else:
            st.success("Keine Zahlungen in den nächsten 2 Wochen.")
            
        st.divider()

        # B. BUDGET & AUFSCHLÜSSELUNG (NEU)
        shared_ausg_full = ausgaben_df[ausgaben_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        priv_ausg_current = ausgaben_df[ausgaben_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        shared_einn_half = einnahmen_df[einnahmen_df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum() / 2
        priv_einn_current = einnahmen_df[einnahmen_df['Eigentümer'] == current_user]["Monatlich"].sum()
        
        total_income = priv_einn_current + shared_einn_half
        total_load = priv_ausg_current + (shared_ausg_full / 2)
        free_budget = total_income - total_load

        # Metriken für das freie Budget
        st.subheader("💳 Dein Freies Budget")
        m1, m2, m3 = st.columns(3)
        m1.metric("Einnahmen (inkl. 50% Haus)", fmt_eur(total_income))
        m2.metric("Ausgaben (inkl. 50% Haus)", fmt_eur(total_load))
        m3.metric("Verfügbar", fmt_eur(free_budget))

        # Detaillierte Ausgaben-Metriken (Die gewünschte Aufteilung)
        with st.expander("🔍 Kosten-Details (Monatlich)", expanded=True):
            d1, d2, d3 = st.columns(3)
            d1.write("**Privat**")
            d1.write(f"Nur {current_user}: {fmt_eur(priv_ausg_current)}")
            
            d2.write("**Gemeinsam (Dein Anteil)**")
            d2.write(f"50% Haus-Kosten: {fmt_eur(shared_ausg_full/2)}")
            
            d3.write("**Haus Gesamt**")
            d3.write(f"100% Haus-Kosten: {fmt_eur(shared_ausg_full)}")

        st.divider()

        # C. GRAFIKEN
        st.subheader("📊 Ausgaben-Analyse")
        gc1, gc2 = st.columns(2)
        with gc1:
            st.write("**Nach Hauptkategorien**")
            if not my_ausgaben.empty:
                pie_df = my_ausgaben.groupby("Hauptkategorie")["Monatlich"].sum().reset_index()
                fig_pie = px.pie(pie_df, values='Monatlich', names='Hauptkategorie', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
        with gc2:
            st.write("**Größte Posten**")
            if not my_ausgaben.empty:
                bar_df = my_ausgaben.groupby("Kostenart")["Monatlich"].sum().reset_index().sort_values("Monatlich", ascending=False).head(8)
                fig_bar = px.bar(bar_df, x="Monatlich", y="Kostenart", orientation='h', text_auto='.0f')
                st.plotly_chart(fig_bar, use_container_width=True)

# --- TAB 2: NEUER EINTRAG ---
with tab2:
    st.subheader("Transaktion hinzufügen")
    typ = st.radio("Typ", ["Ausgabe", "Einnahme"], horizontal=True)
    st.write("---")
    with st.form("new_form", clear_on_submit=True):
        own = st.radio("Besitzer", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True)
        c1, c2 = st.columns(2)
        with c1:
            kat_list = HAUPTKATEGORIEN if typ == "Ausgabe" else ["Gehalt", "Kindergeld", "Sonstige Einnahme"]
            hauptkat = st.selectbox("Hauptkategorie", kat_list)
        with c2:
            kostenart = st.text_input("Name", placeholder="z.B. Miete, Gehalt...")
        betrag = st.number_input("Betrag €", min_value=0.0, step=0.01, value=None)
        cc1, cc2 = st.columns(2)
        with cc1: turnus = st.selectbox("Intervall", list(INTERVALL_MONATE.keys()))
        with cc2: datum = st.date_input("Datum", datetime.now(), format="DD.MM.YYYY")
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag and kostenart:
                monat = float(betrag) / INTERVALL_MONATE[turnus]
                new_row = pd.DataFrame([{"Eigentümer": own, "Typ": typ, "Hauptkategorie": hauptkat, "Kostenart": kostenart.strip(), "Betrag": float(betrag), "Intervall": turnus, "Monatlich": float(monat), "Nächste Fälligkeit": pd.to_datetime(datum)}])
                updated = pd.concat([df, new_row], ignore_index=True)
                save = updated.copy()
                save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Nebenkosten", data=save)
                st.success(f"Gespeichert!")
                st.rerun()

# --- TAB 3: LISTE ---
with tab3:
    st.subheader("Bearbeiten")
    if not df.empty:
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, column_config={"Betrag": st.column_config.NumberColumn(format="%.2f €"), "Monatlich": st.column_config.NumberColumn(format="%.2f €"), "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")})
        if st.button("💾 Cloud speichern"):
            save = edited.copy()
            save['Monatlich'] = save.apply(lambda r: float(r['Betrag']) / INTERVALL_MONATE.get(str(r['Intervall']).lower(), 1), axis=1)
            save['Nächste Fälligkeit'] = pd.to_datetime(save['Nächste Fälligkeit']).dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Nebenkosten", data=save)
            st.rerun()

# --- TAB 4: HISTORIE ---
with tab4:
    st.subheader("📖 Logbuch")
    try:
        hist_df = conn.read(worksheet="Historie", ttl="0m")
        if not hist_df.empty:
            st.dataframe(hist_df.sort_values("Datum", ascending=False), use_container_width=True)
    except: st.info("Noch keine Historie.")
