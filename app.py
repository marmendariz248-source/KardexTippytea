import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Business Intelligence", layout="wide", page_icon="🍵")

# Estilo visual original (Tippytea Green)
st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #f3f6f1 0%, #dce5d1 100%); }
    .login-card { background: white; padding: 2rem; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #2e7d32; text-align: center; }
    div.stButton > button { background-color: #2e7d32 !important; color: white !important; border-radius: 10px !important; font-weight: bold !important; width: 100%; }
    </style>
""", unsafe_allow_html=True)

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

# --- CONEXIÓN DE LECTURA SEGURA ---
def cargar_movimientos_nube():
    sheet_id = st.secrets["gsheet_id"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    try:
        return pd.read_csv(url)
    except:
        return pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

# --- 2. SEGURIDAD ---
credentials = {"usernames": {
    "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
    "jennys_contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"}
}}
stauth.Hasher.hash_passwords(credentials)
authenticator = stauth.Authenticate(credentials, "tippy_v10", "auth_key_1010", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=200)
        authenticator.login(location='main')
        st.markdown('</div>', unsafe_allow_html=True)

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')
    
    df_base = cargar_base_inicial()
    df_movs = cargar_movimientos_nube()

    # --- LÓGICA DE STOCKS ---
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Ajuste'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else -x['Cantidad'], axis=1)
        resumen = df_movs.groupby('Codigo')['Ajuste'].sum().reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Ajuste']
    else:
        df_final = df_base.copy()
        df_final['Stock_Actual'] = df_final['Stock_Inicial']

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
                    
                    if st.form_submit_button("Guardar Movimiento"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                           'Tipo': tipo, 'Cantidad': float(st.session_state[f"v_{cid}"]),
                                           'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                           'Usuario': st.session_state['username']})
                        
                        # ACTUALIZACIÓN LOCAL + AVISO
                        df_upd = pd.concat([df_movs, pd.DataFrame(nuevos)], ignore_index=True)
                        df_upd.to_csv("movimientos_temporales.csv", index=False)
                        st.success("¡Movimiento registrado en la sesión!")
                        st.info("Para persistir cambios en la nube, descarga el historial al final del día.")
                        st.rerun()

        st.markdown("### 📑 Resumen Detallado (Inicial | Movimiento | Final)")
        if not df_movs.empty:
            reporte_det = df_movs.copy().merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            reporte_det['Mov.'] = reporte_det.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            reporte_det = reporte_det[['Fecha', 'Producto', 'Stock_Inicial', 'Mov.', 'Stock_Actual', 'Usuario']].sort_index(ascending=False)
            st.dataframe(reporte_det.head(10), use_container_width=True, hide_index=True)
        
        st.markdown("### 📦 Stock Actualizado")
        st.dataframe(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']], use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Análisis de Movimientos")
        if not df_movs.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                # Gráfica restaurada
                fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                             x='Producto', y='Cantidad', color='Tipo', barmode='group',
                             title="Volumen de Movimientos por Producto",
                             color_discrete_map={'Entrada':'#2e7d32', 'Salida':'#e74c3c'})
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("📥 Exportar Reportes")
                st.download_button("📥 Inventario Completo (.xlsx)", data=to_excel(df_final[['Codigo','Producto','Unidad','Stock_Actual']]), file_name="Inventario_Tippytea.xlsx")
                st.download_button("📥 Historial de Movimientos (.xlsx)", data=to_excel(reporte_det if not df_movs.empty else df_movs), file_name="Kardex_Movimientos.xlsx")
        else:
            st.info("No hay datos para mostrar gráficas aún.")

    with tab3:
        st.subheader("⚙️ Configuración del Sistema")
        if st.button("↩️ Deshacer Último Registro"):
            if not df_movs.empty:
                st.warning("Opción disponible al conectar API de escritura.")
