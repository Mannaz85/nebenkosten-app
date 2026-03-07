import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import extra_streamlit_components as stx

# --- 1. GRUNDKONFIGURATION ---
# Trage hier eure Namen ein (müssen exakt so in der Google Tabelle stehen)
PERSONEN = ["Philipp", "Miri"] 

INTERVALL_MONATE = {
    "monatlich": 1, 
    "quartalsweise": 3, 
    "halbjährlich": 6, 
    "jährlich": 12
}

st.set_page_config(page_title="Haus-Manager Pro", layout="centered")

# --- 2. SICHERHEIT (PASSWORT & COOKIES) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

def check_password():
    if st.session_state.get("authenticated"):
        return True

    # Cookie-Check
    auth_cookie = cookie_manager.get("haushalts_auth")
    if "password" in st.secrets and auth_cookie == st.secrets["password"]:
        st.session_state["authenticated"] = True
        return True

    # Login-Maske
    st.title("🔐 Haus-Manager Login")
    with st.container(border=True):
        st.write("Bitte Passwort eingeben:")
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
                st.error("Passwort falsch oder in Secrets nicht konfiguriert.")
    return False

if not check_password():
    st.stop()

# --- 3. DATEN-LOGIK ---
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
        st.toast("📅 Termine automatisch verlängert!", icon="🔄")
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

# Hilfsfunktion für Euro-Formatierung
def fmt_eur(val):
    return f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("👤 Profil")
    current_user = st.selectbox("Wer nutzt die App?", PERSONEN)
    other_user = PERSONEN[1] if current_user == PERSONEN[0] else PERSONEN[0]
    st.divider()
    if st.button("Abmelden"):
        cookie_manager.delete("haushalts_auth")
        st.session_state["authenticated"] = False
        st.rerun()

# --- 5. HAUPTSEITE (TABS) ---
st.title("🏠 Finanz-Manager")
tab1, tab2, tab3 = st.tabs(["📊 Status", "➕ Neu", "📋 Liste"])

# TAB 1: DASHBOARD
with tab1:
    if not df.empty:
        st.subheader(f"🔔 Termine für {current_user}")
        today_ts = pd.Timestamp(datetime.now().date())
        my_df = df[(df['Eigentümer'] == "Gemeinsam") | (df['Eigentümer'] == current_user)].copy()
        due_soon = my_df[(my_df['Nächste fälligkeit'] >= today_ts) & 
                         (my_df['Nächste Fälligkeit'] <= today_ts + pd.Timedelta(days=10))]
        
        if not due_soon.empty:
            for _, row in due_soon.sort_values('Nächste Fälligkeit').iterrows():
                icon = "👫" if row['Eigentümer'] == "Gemeinsam" else "👤"
                st.warning(f"{icon} {row['Nächste Fälligkeit'].strftime('%d.%m.')}: {row['Kostenart']} — {fmt_eur(row['Betrag'])}")
        else:
            st.success("Keine Zahlungen in den nächsten 10 Tagen.")

        st.divider()
        
        # Berechnung der Last
        shared_total = df[df['Eigentümer'] == "Gemeinsam"]["Monatlich"].sum()
        p1_priv = df[df['Eigentümer'] == PERSONEN[0]]["Monatlich"].sum()
        p2_priv = df[df['Eigentümer'] == PERSONEN[1]]["Monatlich"].sum()
        
        p1_total, p2_total = (shared_total/2 + p1_priv), (shared_total/2 + p2_priv)
        curr_total = p1_total if current_user == PERSONEN[0] else p2_total
        curr_priv = p1_priv if current_user == PERSONEN[0] else p2_priv

        c1, c2, c3 = st.columns(3)
        c1.metric("Anteil Haus", fmt_eur(shared_total/2))
        c2.metric("Deine Privaten", fmt_eur(curr_priv))
        c3.metric("DEINE LAST", fmt_eur(curr_total))

        st.divider()
        st.subheader("⚖️ Vergleich der Belastung")
        compare_df = pd.DataFrame({"Person": PERSONEN, "Monatlich": [p1_total, p2_total]})
        fig = px.bar(compare_df, x="Person", y="Monatlich", color="Person", text_auto='.2f',
                     color_discrete_map={PERSONEN[0]: '#636EFA', PERSONEN[1]: '#EF553B'})
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

# TAB 2: NEUER EINTRAG
with tab2:
    st.subheader("Eintrag hinzufügen")
    existing_cats = sorted(df['Kostenart'].unique().tolist()) if not df.empty else ["Strom", "Wasser"]
    with st.form("add_form", clear_on_submit=True):
        owner = st.radio("Für wen?", ["Gemeinsam", PERSONEN[0], PERSONEN[1]], horizontal=True, 
                         index=0 if current_user == PERSONEN[0] else 1)
        
        c_sel, c_new = st.columns(2)
        with c_sel:
            sel = st.selectbox("Kategorie", existing_cats + ["+ Neu..."])
        with c_new:
            art = st.text_input("Name", placeholder="Kategoriename") if sel == "+ Neu..." else sel
            
        betrag = st.number_input("Betrag in €", min_value=0.0, step=0.01, value=None, placeholder="0,00")
        turnus = st.selectbox("Turnus", list(INTERVALL_MONATE.keys()))
        datum = st.date_input("Nächste Zahlung", datetime.now(), format="DD.MM.YYYY")
        
        if st.form_submit_button("✅ Speichern", use_container_width=True):
            if betrag and art:
                monat = betrag / INTERVALL_MONATE[turnus]
                new_row = pd.DataFrame([{"Eigentümer": owner, "Kostenart": art, "Betrag": float(betrag),
                                         "Intervall": turnus, "Monatlich": float(monat), "Nächste Fälligkeit": datum}])
                updated = pd.concat([df, new_row], ignore_index=True)
                save = updated.copy()
                save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].astype(str)
                conn.update(worksheet="Nebenkosten", data=save)
                st.success("Gespeichert!")
                st.rerun()

# TAB 3: LISTE
with tab3:
    st.subheader("Alle Kosten")
    if not df.empty:
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                column_config={
                                    "Betrag": st.column_config.NumberColumn(format="%.2f €"),
                                    "Monatlich": st.column_config.NumberColumn(format="%.2f €"),
                                    "Nächste Fälligkeit": st.column_config.DateColumn(format="DD.MM.YYYY")
                                })
        if st.button("Änderungen synchronisieren"):
            save = edited.copy()
            save['Nächste Fälligkeit'] = save['Nächste Fälligkeit'].astype(str)
            conn.update(worksheet="Nebenkosten", data=save)
            st.success("Cloud aktualisiert!")
            st.rerun()
