import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io
import glob

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex Pro", layout="wide", page_icon="🍵")

# Función mejorada para encontrar tu archivo de movimientos
def encontrar_archivo_datos():
    # Busca cualquier archivo que tenga estas palabras clave
    patrones = ["*movimientos*", "*kardex*", "Copia*"]
    for patron in patrones:
        archivos = glob.glob(patron + ".csv")
        if archivos:
            return archivos[0]
    return "movimientos_kardex.csv"

FILE_MOVS = encontrar_archivo_datos()
FILE_EXTRA_PRODS = "productos_extra.csv"

def inicializar_archivos():
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']).to_csv(FILE_MOVS, index=False)
    if not os.path.exists(FILE_EXTRA_PRODS):
        pd.DataFrame(columns=['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']).to_csv(FILE_EXTRA_PRODS, index=False)

inicializar_archivos()

# --- FUNCIONES DE LIMPIEZA ---
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
def cargar_base_completa():
    file_path = 'Inventarios - Planta.csv'
    df_base = pd.DataFrame()
    if os.path.exists(file_path):
        # Saltamos 5 filas por el formato del reporte de Tippytea
        df = pd.read_csv(file_path, skiprows=5)
        df.columns = df.columns.str.strip()
        col_conteo = 'Conteo 02-02-2026'
        
        # Intentamos obtener columnas necesarias
        target_cols = ['Codigo', 'Nombre', 'Unidad', col_conteo]
        if all(c in df.columns for c in target_cols):
            df_base = df[target_cols].copy()
        else:
            df_base = df.iloc[:, [0, 1, 2, 3]].copy()
            
        df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
        df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
        df_base['Codigo'] = df_base['Codigo'].astype(str).str.strip()
        df_base = df_base.dropna(subset=['Producto'])

    if os.path.exists(FILE_EXTRA_PRODS):
        df_extra = pd.read_csv(FILE_EXTRA_PRODS)
        df_extra['Codigo'] = df_extra['Codigo'].astype(str).str.strip()
        df_base = pd.concat([df_base, df_extra], ignore_index=True)
    return df_base

# --- 2. SEGURIDAD ---
credentials = {"usernames": {
    "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
    "jennys_contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"},
    "ali_planta": {"name": "Ali Planta", "password": "Tippytea2026*"}
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
    df_base = cargar_base_completa()
    
    # LECTURA INTELIGENTE (Detecta si es coma o punto y coma automáticamente)
    try:
        df_movs = pd.read_csv(FILE_MOVS, sep=None, engine='python')
        # Limpiar datos cargados
        df_movs['Codigo'] = df_movs['Codigo'].astype(str).str.strip()
        if 'Tipo' in df_movs.columns:
            df_movs['Tipo'] = df_movs['Tipo'].str.strip().str.capitalize()
    except:
        df_movs = pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

    # --- CÁLCULO DE STOCK ACTUAL ---
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Entradas'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else 0, axis=1)
        df_movs['Salidas'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Salida' else 0, axis=1)
        
        resumen = df_movs.groupby('Codigo').agg({'Entradas': 'sum', 'Salidas': 'sum'}).reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Entradas'] - df_final['Salidas']
    else:
        df_final = df_base.copy()
        df_final['Entradas'], df_final['Salidas'], df_final['Stock_Actual'] = 0, 0, df_final['Stock_Inicial']

    # --- INTERFAZ ---
    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📈 Análisis Contable", "⚙️ Correcciones"])

    with tab1:
        st.subheader(f"Inventario y Movimientos | {st.session_state['name']}")
        
        # TABLA DE ACTIVIDAD SOLICITADA
        st.markdown("### 🔍 Resumen de Productos con Movimientos")
        df_actividad = df_final[(df_final['Entradas'] > 0) | (df_final['Salidas'] > 0)].copy()
        
        if not df_actividad.empty:
            st.dataframe(df_actividad[['Codigo', 'Producto', 'Stock_Inicial', 'Entradas', 'Salidas', 'Stock_Actual']], 
                         use_container_width=True, hide_index=True)
        else:
            st.warning(f"No se detectaron movimientos en el archivo cargado ({FILE_MOVS}).")

        st.divider()

        # REGISTRO
        with st.expander("➕ REGISTRAR MOVIMIENTOS", expanded=True):
            df_base['L'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Seleccionar productos:", df_base['L'])
            if sel:
                with st.form("f_mov"):
                    c1, c2 = st.columns(2)
                    tipo = c1.radio("Operación:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"Cantidad para {s.split(' | ')[1]}:", key=f"val_{cid}", min_value=0.0)
                    if st.form_submit_button("Guardar"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                           'Tipo': tipo, 'Cantidad': float(st.session_state[f"val_{cid}"]),
                                           'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                           'Usuario': st.session_state['username']})
                        # Guardamos limpiando columnas temporales
                        pd.concat([df_movs.drop(columns=['Entradas','Salidas'], errors='ignore'), pd.DataFrame(nuevos)], ignore_index=True).to_csv(FILE_MOVS, index=False)
                        st.cache_data.clear(); st.success("¡Datos guardados!"); st.rerun()

        # HISTORIAL
        st.markdown("### 📑 Historial Completo de Movimientos")
        if not df_movs.empty:
            st.dataframe(df_movs[['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']].sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Reportes y Descargas")
        if not df_movs.empty:
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', barmode='group')
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            c1.download_button("📥 Descargar Inventario Excel", data=to_excel(df_final), file_name="Inventario_Final.xlsx")
            c2.download_button("📥 Descargar Kardex Excel", data=to_excel(df_movs), file_name="Kardex_Completo.xlsx")

    with tab3:
        st.subheader("⚙️ Correcciones")
        # Mantener funciones de corrección del código anterior...
