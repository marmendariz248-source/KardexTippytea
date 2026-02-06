import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex Pro", layout="wide", page_icon="🍵")

FILE_MOVS = "movimientos_kardex.csv"
FILE_EXTRA_PRODS = "productos_extra.csv"
FILE_PLANTA = "Inventarios - Planta.csv"

def inicializar_archivos():
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']).to_csv(FILE_MOVS, index=False, sep=';')
    if not os.path.exists(FILE_EXTRA_PRODS):
        pd.DataFrame(columns=['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']).to_csv(FILE_EXTRA_PRODS, index=False, sep=';')

inicializar_archivos()

# --- FUNCIONES ---
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
    df_base = pd.DataFrame(columns=['Codigo', 'Producto', 'Unidad', 'Stock_Inicial'])
    if os.path.exists(FILE_PLANTA):
        try:
            df = pd.read_csv(FILE_PLANTA, skiprows=5)
            df.columns = df.columns.str.strip()
            # Buscamos la columna de stock (la del 02-02-2026)
            col_stock = [c for c in df.columns if 'Conteo' in c]
            if col_stock:
                df_base = df[['Codigo', 'Nombre', 'Unidad', col_stock[0]]].copy()
            else:
                df_base = df.iloc[:, [0, 1, 2, 3]].copy()
            
            df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
            df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
            df_base['Codigo'] = df_base['Codigo'].astype(str).str.strip()
        except:
            pass

    if os.path.exists(FILE_EXTRA_PRODS):
        try:
            df_extra = pd.read_csv(FILE_EXTRA_PRODS, sep=None, engine='python')
            df_extra['Codigo'] = df_extra['Codigo'].astype(str).str.strip()
            df_base = pd.concat([df_base, df_extra], ignore_index=True)
        except:
            pass
    return df_base.drop_duplicates(subset=['Codigo'])

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
    
    # LEER MOVIMIENTOS (Detecta ; o , automáticamente)
    try:
        df_movs = pd.read_csv(FILE_MOVS, sep=None, engine='python')
        df_movs['Codigo'] = df_movs['Codigo'].astype(str).str.strip()
    except:
        df_movs = pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

    # --- CÁLCULOS ---
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Entradas'] = df_movs.apply(lambda x: x['Cantidad'] if str(x['Tipo']).lower() == 'entrada' else 0, axis=1)
        df_movs['Salidas'] = df_movs.apply(lambda x: x['Cantidad'] if str(x['Tipo']).lower() == 'salida' else 0, axis=1)
        
        resumen = df_movs.groupby('Codigo').agg({'Entradas':'sum', 'Salidas':'sum'}).reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Entradas'] - df_final['Salidas']
    else:
        df_final = df_base.copy()
        df_final['Entradas'], df_final['Salidas'], df_final['Stock_Actual'] = 0, 0, df_final['Stock_Inicial']

    # --- PESTAÑAS ---
    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📊 Reportes", "⚙️ Correcciones"])

    with tab1:
        st.subheader(f"Inventario Planta | {st.session_state['name']}")
        
        # TABLA DE ACTIVIDAD (REQUERIDA)
        st.markdown("### 🔍 Productos con Movimientos Recientes")
        df_actividad = df_final[(df_final['Entradas'] > 0) | (df_final['Salidas'] > 0)].copy()
        if not df_actividad.empty:
            st.dataframe(df_actividad[['Codigo', 'Producto', 'Stock_Inicial', 'Entradas', 'Salidas', 'Stock_Actual']], 
                         use_container_width=True, hide_index=True)
        else:
            st.info("No hay movimientos registrados en este archivo aún.")

        st.divider()
        
        # REGISTRO
        with st.expander("➕ REGISTRAR MOVIMIENTO", expanded=True):
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
                        # Guardar manteniendo el formato original
                        df_updated = pd.concat([df_movs.drop(columns=['Entradas','Salidas'], errors='ignore'), pd.DataFrame(nuevos)], ignore_index=True)
                        df_updated.to_csv(FILE_MOVS, index=False, sep=';')
                        st.cache_data.clear(); st.success("¡Guardado!"); st.rerun()

        # HISTORIAL COMPLETO
        st.markdown("### 📑 Historial de todos los Movimientos")
        bus_h = st.text_input("Filtrar historial:")
        if not df_movs.empty:
            df_h = df_movs[['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']].copy()
            if bus_h:
                df_h = df_h[df_h.apply(lambda r: bus_h.lower() in str(r).lower(), axis=1)]
            st.dataframe(df_h.sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Análisis de Stock")
        if not df_movs.empty:
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', barmode='group')
            st.plotly_chart(fig, use_container_width=True)
        
        c1, c2 = st.columns(2)
        c1.download_button("📥 Descargar Stock Actual (.xlsx)", data=to_excel(df_final), file_name="Inventario_Tippytea.xlsx")
        c2.download_button("📥 Descargar Kardex (.xlsx)", data=to_excel(df_movs), file_name="Historial_Kardex.xlsx")

    with tab3:
        st.subheader("⚙️ Panel de Correcciones")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### ✨ Producto Nuevo")
            with st.form("n_p"):
                nc, nn = st.text_input("Código"), st.text_input("Nombre")
                nu = st.selectbox("Unidad", ["gr", "uni", "kg", "ml"])
                ns = st.number_input("Stock Inicial", min_value=0.0)
                if st.form_submit_button("Crear"):
                    df_ex = pd.read_csv(FILE_EXTRA_PRODS, sep=None, engine='python') if os.path.exists(FILE_EXTRA_PRODS) else pd.DataFrame()
                    pd.concat([df_ex, pd.DataFrame([{'Codigo':nc,'Producto':nn,'Unidad':nu,'Stock_Inicial':ns}])], ignore_index=True).to_csv(FILE_EXTRA_PRODS, index=False, sep=';')
                    st.cache_data.clear(); st.rerun()
        
        if st.button("🗑️ DESHACER ÚLTIMA CARGA"):
            if not df_movs.empty:
                df_movs.drop(df_movs.index[-1]).drop(columns=['Entradas','Salidas'], errors='ignore').to_csv(FILE_MOVS, index=False, sep=';')
                st.cache_data.clear(); st.rerun()
