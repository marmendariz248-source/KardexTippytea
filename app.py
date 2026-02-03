import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex", layout="wide", page_icon="🍵")

FILE_MOVS = "movimientos_kardex.csv"

# Función para asegurar que el archivo de movimientos exista con sus columnas
def inicializar_archivo_movs():
    columnas = ['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=columnas).to_csv(FILE_MOVS, index=False)
    else:
        # Verificar que tenga las columnas necesarias
        try:
            df_temp = pd.read_csv(FILE_MOVS)
            if 'Cantidad' not in df_temp.columns:
                pd.DataFrame(columns=columnas).to_csv(FILE_MOVS, index=False)
        except:
            pd.DataFrame(columns=columnas).to_csv(FILE_MOVS, index=False)

inicializar_archivo_movs()

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
authenticator = stauth.Authenticate(credentials, "tippy_v12", "auth_key_1212", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=200)
        authenticator.login(location='main')

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')
    
    df_base = cargar_base_inicial()
    df_movs = pd.read_csv(FILE_MOVS)

    # --- CÁLCULO DE STOCKS (CORREGIDO) ---
    if not df_movs.empty and 'Cantidad' in df_movs.columns:
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
                        st.number_input(f"{s.split(' | ')[1]}", key=f"val_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar Movimiento"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({
                                'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                'Tipo': tipo, 'Cantidad': float(st.session_state[f"val_{cid}"]),
                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                'Usuario': st.session_state['username']
                            })
                        df_updated = pd.concat([df_movs, pd.DataFrame(nuevos)], ignore_index=True)
                        df_updated.to_csv(FILE_MOVS, index=False)
                        st.success("¡Guardado correctamente!")
                        st.rerun()

        st.markdown("### 📑 Resumen Detallado (Inicial | Movimiento | Final)")
        if not df_movs.empty:
            reporte_det = df_movs.copy().merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            reporte_det['Mov.'] = reporte_det.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            reporte_det = reporte_det[['Fecha', 'Producto', 'Stock_Inicial', 'Mov.', 'Stock_Actual', 'Usuario']].sort_index(ascending=False)
            st.dataframe(reporte_det.head(15), use_container_width=True, hide_index=True)
        
        st.markdown("### 📦 Stock Actualizado")
        st.dataframe(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']], use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Análisis Contable")
        if not df_movs.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                             x='Producto', y='Cantidad', color='Tipo', barmode='group',
                             color_discrete_map={'Entrada':'#2e7d32', 'Salida':'#e74c3c'})
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("📥 Descargar Reportes")
                st.download_button("📥 Inventario Completo (.xlsx)", data=to_excel(df_final[['Codigo','Producto','Unidad','Stock_Actual']]), file_name="Inventario.xlsx")
                st.download_button("📥 Historial Movimientos (.xlsx)", data=to_excel(reporte_det), file_name="Historial.xlsx")
        else:
            st.info("No hay movimientos registrados para mostrar análisis.")

    with tab3:
        st.subheader("⚙️ Mantenimiento")
        if st.button("↩️ Deshacer Último Registro"):
            if not df_movs.empty:
                df_rev = df_movs.drop(df_movs.index[-1])
                df_rev.to_csv(FILE_MOVS, index=False)
                st.warning("Último registro eliminado."); st.rerun()
