import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex", layout="wide", page_icon="🍵")

# NOMBRE EXACTO DE TU ARCHIVO EN GITHUB
FILE_MOVS = "movimientos_kardex.csv"

def inicializar_archivo_movs():
    columnas = ['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=columnas).to_csv(FILE_MOVS, index=False)

inicializar_archivo_movs()

# --- FUNCIONES DE APOYO ---
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

# --- 2. SEGURIDAD (EQUIPO ACTUALIZADO) ---
credentials = {"usernames": {
    "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
    "jennys_contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"},
    "ali_planta": {"name": "Ali Planta", "password": "Tippytea2026*"}
}}

# IMPORTANTE: El cookie_name debe ser único para evitar errores de sesión
authenticator = stauth.Authenticate(credentials, "tippy_kardex_v3", "auth_key_9988", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=200)
        authenticator.login(location='main')

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')
    
    df_base = cargar_base_inicial()
    df_movs = pd.read_csv(FILE_MOVS)

    # --- CÁLCULO DE STOCKS ---
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Ajuste'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else -x['Cantidad'], axis=1)
        resumen = df_movs.groupby('Codigo')['Ajuste'].sum().reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Ajuste']
    else:
        df_final = df_base.copy()
        df_final['Stock_Actual'] = df_final['Stock_Inicial']

    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📈 Análisis Contable", "⚙️ Mantenimiento"])

    with tab1:
        st.markdown(f"### 🛠️ Registro de Movimientos - **{st.session_state['name']}**")
        with st.expander("Registrar Entradas / Salidas", expanded=True):
            df_base['L'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Buscar productos para registrar:", df_base['L'])
            if sel:
                with st.form("f_mov"):
                    c1, c2 = st.columns(2)
                    tipo = c1.radio("Operación:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"{s.split(' | ')[1]} ({df_base[df_base['Codigo']==cid]['Unidad'].values[0]})", key=f"val_{cid}", min_value=0.0)
                    
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
                        st.success("¡Movimientos registrados!")
                        st.rerun()

        st.markdown("### 📑 Historial Completo")
        # Buscador por código de producto para Jenny
        busqueda = st.text_input("🔍 Buscar por Código o Producto en el historial:")
        if busqueda:
            df_mostrar = df_movs[df_movs.apply(lambda row: busqueda.lower() in str(row).lower(), axis=1)]
        else:
            df_mostrar = df_movs
            
        st.dataframe(df_mostrar.sort_index(ascending=False), use_container_width=True)

    with tab2:
        st.markdown("### 📊 Reportes")
        if not df_movs.empty:
            st.download_button("📥 Descargar Inventario Actual (.xlsx)", data=to_excel(df_final), file_name="Inventario_Tippytea.xlsx")
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', barmode='group')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos suficientes.")

    with tab3:
        st.subheader("🛠️ Corregir Registros (ID Único)")
        if not df_movs.empty:
            df_edit = df_movs.copy()
            df_edit['ID_Selector'] = df_edit.index.astype(str) + " | " + df_edit['Producto'] + " (" + df_edit['Fecha'] + ")"
            
            seleccion = st.selectbox("Selecciona la fila exacta a arreglar:", df_edit['ID_Selector'])
            idx_to_edit = int(seleccion.split(" | ")[0])
            registro = df_movs.iloc[idx_to_edit]

            with st.form("form_edit"):
                st.write(f"Editando Registro #{idx_to_edit}")
                new_fecha = st.text_input("Fecha", value=registro['Fecha'])
                new_tipo = st.selectbox("Tipo", ["Salida", "Entrada"], index=0 if registro['Tipo']=="Salida" else 1)
                new_cant = st.number_input("Cantidad", value=float(registro['Cantidad']))
                
                if st.form_submit_button("Actualizar Registro"):
                    df_movs.at[idx_to_edit, 'Fecha'] = new_fecha
                    df_movs.at[idx_to_edit, 'Tipo'] = new_tipo
                    df_movs.at[idx_to_edit, 'Cantidad'] = new_cant
                    df_movs.at[idx_to_edit, 'Usuario'] = f"{st.session_state['username']} (Editó)"
                    df_movs.to_csv(FILE_MOVS, index=False)
                    st.success("Cambios guardados.")
                    st.rerun()
            
            st.divider()
            if st.button("🗑️ Eliminar último registro"):
                df_rev = df_movs.drop(df_movs.index[-1])
                df_rev.to_csv(FILE_MOVS, index=False)
                st.warning("Eliminado."); st.rerun()
