import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Business Intelligence", layout="wide", page_icon="🍵")

# Estilo visual original
st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #f3f6f1 0%, #dce5d1 100%); }
    .login-card { background: white; padding: 3rem; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); border-top: 8px solid #2e7d32; text-align: center; }
    div.stButton > button { background-color: #2e7d32 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 3.5rem; width: 100%; }
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# Conexión nativa
conn = st.connection("gsheets", type=GSheetsConnection)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

def limpiar_monto(valor):
    if pd.isna(valor) or str(valor).strip() in ["-", "", "0"]: return 0.0
    if isinstance(valor, str):
        v = valor.strip().replace('.', '').replace(',', '.')
        try: return float(v)
        except: return 0.0
    return float(valor)

@st.cache_data
def cargar_base_inicial():
    file_path = 'Inventarios - Planta.csv'
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, skiprows=5)
        df.columns = df.columns.str.strip()
        col_conteo = 'Conteo 02-02-2026'
        df_base = df[['Codigo', 'Nombre', 'Unidad', col_conteo]].copy()
        df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
        df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
        return df_base.dropna(subset=['Producto'])
    return pd.DataFrame()

# --- 2. SEGURIDAD ---
credentials = {"usernames": {
    "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
    "jennys_contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"}
}}
stauth.Hasher.hash_passwords(credentials)
authenticator = stauth.Authenticate(credentials, "tippy_v9", "auth_key_999", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=220)
        authenticator.login(location='main')
        st.markdown('</div>', unsafe_allow_html=True)

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')
    
    # Cargar datos
    df_base = cargar_base_inicial()
    try:
        df_movs = conn.read(ttl=0)
        # Limpiar posibles filas vacías de Google Sheets
        df_movs = df_movs.dropna(subset=['Codigo'])
    except:
        df_movs = pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

    # Cálculos de Stock
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Ajuste'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else -x['Cantidad'], axis=1)
        resumen = df_movs.groupby('Codigo')['Ajuste'].sum().reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Ajuste']
        df_solo_movidos = df_final[df_final['Codigo'].isin(df_movs['Codigo'].unique())]
    else:
        df_final = df_base.copy()
        df_final['Stock_Actual'] = df_final['Stock_Inicial']
        df_solo_movidos = pd.DataFrame()

    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📈 Análisis Contable", "⚙️ Configuración"])

    with tab1:
        st.markdown("### 🛠️ Registro de Movimientos")
        with st.expander("Registrar Entradas / Salidas", expanded=True):
            df_base['L'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Buscar productos:", df_base['L'])
            if sel:
                with st.form("f_mov"):
                    c1, c2 = st.columns(2)
                    tipo = c1.radio("Operación:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"{s.split(' | ')[1]}", key=f"v_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar en Nube"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({
                                'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                'Tipo': tipo, 'Cantidad': float(st.session_state[f"v_{cid}"]),
                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                'Usuario': st.session_state['username']
                            })
                        df_upd = pd.concat([df_movs, pd.DataFrame(nuevos)], ignore_index=True)
                        conn.update(data=df_upd)
                        st.success("¡Registrado en Google Sheets!"); st.rerun()

        st.markdown("### 📑 Resumen Detallado (Inicial | Movimiento | Final)")
        if not df_movs.empty:
            reporte_det = df_movs.copy().merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            reporte_det['Mov.'] = reporte_det.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            reporte_det = reporte_det[['Fecha', 'Producto', 'Stock_Inicial', 'Mov.', 'Stock_Actual', 'Usuario']].sort_index(ascending=False)
            st.dataframe(reporte_det.head(10), use_container_width=True, hide_index=True)
        
        st.markdown("### 📦 Inventario General")
        st.dataframe(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']], use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Auditoría de Movimientos")
        if not df_movs.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                             x='Producto', y='Cantidad', color='Tipo', barmode='group',
                             color_discrete_map={'Entrada':'#2e7d32', 'Salida':'#e74c3c'})
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("📥 Descargas Excel")
                st.download_button("📥 Inventario Completo", data=to_excel(df_final[['Codigo','Producto','Unidad','Stock_Actual']]), file_name="Inventario_Tippytea.xlsx")
                st.download_button("📥 Historial de Movimientos", data=to_excel(reporte_det), file_name="Kardex_Movimientos.xlsx")
                st.subheader("🚨 Stock Crítico (<50)")
                st.dataframe(df_final[df_final['Stock_Actual'] < 50][['Producto', 'Stock_Actual']], hide_index=True)
        else:
            st.info("No hay datos suficientes para el análisis.")

    with tab3:
        st.subheader("⚙️ Mantenimiento")
        if st.button("↩️ Deshacer Último Registro"):
            if not df_movs.empty:
                df_rev = df_movs.drop(df_movs.index[-1])
                conn.update(data=df_rev)
                st.warning("Último movimiento eliminado de la nube"); st.rerun()
