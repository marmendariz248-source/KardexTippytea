import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io
import requests

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex Seguro", layout="wide", page_icon="🍵")

# URL de los Secrets
try:
    SHEET_URL = st.secrets["gsheet_url"]
    CSV_URL = SHEET_URL.replace("/edit?usp=sharing", "/export?format=csv")
except:
    st.error("Configura la URL en los Secrets de Streamlit")

# --- FUNCIONES DE APOYO ---
def cargar_movimientos_google():
    try:
        # Leemos directamente el CSV público de Google para evitar errores de conexión
        return pd.read_csv(CSV_URL)
    except:
        return pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
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
credentials = {
    "usernames": {
        "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
        "jennys_contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"}
    }
}
# Nota: En producción, usa contraseñas ya hasheadas.
stauth.Hasher.hash_passwords(credentials)
authenticator = stauth.Authenticate(credentials, "tippy_v8", "auth_key_888", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=220)
        authenticator.login(location='main')

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')
    
    df_base = cargar_base_inicial()
    df_movs = cargar_movimientos_google()

    # --- CÁLCULOS ---
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
            df_base['Lookup'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Buscar productos:", df_base['Lookup'])
            if sel:
                with st.form("f_mov"):
                    c_f1, c_f2 = st.columns(2)
                    tipo = c_f1.radio("Tipo:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c_f2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"{s.split(' | ')[1]}", key=f"val_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar en Nube"):
                        # Creamos el reporte de movimientos nuevo
                        nuevos_datos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos_datos.append([
                                str(fecha), cid, s.split(" | ")[1], tipo, 
                                st.session_state[f"val_{cid}"], 
                                df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                st.session_state['username']
                            ])
                        
                        # INSTRUCCIÓN PARA MARTÍN:
                        st.info("Para escribir en Google Sheets con seguridad total, usa el botón de descarga y pega en tu Drive o usa una API Key.")
                        # Por ahora, para no trabar la app con errores de permisos:
                        df_temp = pd.DataFrame(nuevos_datos, columns=df_movs.columns)
                        df_movs = pd.concat([df_movs, df_temp], ignore_index=True)
                        # Guardamos localmente para la sesión actual
                        df_movs.to_csv("movimientos_kardex.csv", index=False)
                        st.success("Registrado localmente. ¡Descarga el Excel al final para tu respaldo!")
                        st.rerun()

        st.markdown("### 📑 Resumen de Transacciones (Stock Inicial -> Final)")
        if not df_movs.empty:
            reporte = df_movs.copy().merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            reporte['Movimiento'] = reporte.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            # Reordenar columnas para que se vea: Inicial, Movimiento, Final
            reporte_vista = reporte[['Fecha', 'Producto', 'Stock_Inicial', 'Movimiento', 'Stock_Actual', 'Usuario']].sort_index(ascending=False)
            st.dataframe(reporte_vista.head(15), use_container_width=True, hide_index=True)

        st.markdown("### 📦 Inventario Completo")
        st.dataframe(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']], use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("📥 Descargar Reportes en Excel")
        col1, col2 = st.columns(2)
        with col1:
            # DESCARGA INVENTARIO COMPLETO
            st.download_button(
                label="📥 Descargar Inventario (.xlsx)",
                data=to_excel(df_final[['Codigo','Producto','Unidad','Stock_Actual']]),
                file_name=f"Inventario_Tippytea_{datetime.now().strftime('%d_%m')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            # DESCARGA HISTORIAL DE MOVIMIENTOS CON STOCK
            if not df_movs.empty:
                st.download_button(
                    label="📥 Descargar Historial Movimientos (.xlsx)",
                    data=to_excel(reporte_vista),
                    file_name=f"Movimientos_Tippytea_{datetime.now().strftime('%d_%m')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    with tab3:
        st.subheader("⚙️ Mantenimiento")
        if st.button("↩️ Deshacer Último"):
            if os.path.exists("movimientos_kardex.csv"):
                df_t = pd.read_csv("movimientos_kardex.csv")
                if not df_t.empty:
                    df_t.drop(df_t.index[-1]).to_csv("movimientos_kardex.csv", index=False)
                    st.rerun()
