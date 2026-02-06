import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN INICIAL ---
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

# Función para exportar a Excel (Requiere openpyxl)
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte_Tippytea')
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
    # Cargar Excel de Planta
    if os.path.exists(FILE_PLANTA):
        try:
            df = pd.read_csv(FILE_PLANTA, skiprows=5)
            df.columns = df.columns.str.strip()
            col_stock = [c for c in df.columns if 'Conteo' in c]
            if col_stock:
                df_base = df[['Codigo', 'Nombre', 'Unidad', col_stock[0]]].copy()
            else:
                df_base = df.iloc[:, [0, 1, 2, 3]].copy()
            df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
            df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
        except: pass
    
    # Cargar Productos Agregados Manualmente
    if os.path.exists(FILE_EXTRA_PRODS):
        try:
            df_ex = pd.read_csv(FILE_EXTRA_PRODS, sep=';')
            df_ex.columns = df_ex.columns.str.strip()
            df_base = pd.concat([df_base, df_ex], ignore_index=True)
        except: pass
        
    df_base['Codigo'] = df_base['Codigo'].astype(str).str.strip()
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
    
    # Lectura de Movimientos
    try:
        df_movs = pd.read_csv(FILE_MOVS, sep=';', engine='python')
        df_movs.columns = df_movs.columns.str.strip()
        df_movs['Tipo'] = df_movs['Tipo'].str.strip().str.capitalize()
    except:
        df_movs = pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

    # --- CÁLCULOS ---
    if not df_movs.empty:
        df_movs['Cantidad'] = pd.to_numeric(df_movs['Cantidad'], errors='coerce').fillna(0)
        df_movs['Entradas'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else 0, axis=1)
        df_movs['Salidas'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Salida' else 0, axis=1)
        resumen = df_movs.groupby('Codigo').agg({'Entradas':'sum', 'Salidas':'sum'}).reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Entradas'] - df_final['Salidas']
    else:
        df_final = df_base.copy()
        df_final['Entradas'], df_final['Salidas'], df_final['Stock_Actual'] = 0, 0, df_final['Stock_Inicial']

    # --- INTERFAZ TABS ---
    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📊 Reportes y Descargas", "⚙️ Correcciones"])

    with tab1:
        st.subheader(f"Inventario Planta | {st.session_state['name']}")
        
        # 1. Resumen actividad
        st.markdown("### 🔍 Productos con Movimiento")
        df_act = df_final[(df_final['Entradas'] > 0) | (df_final['Salidas'] > 0)]
        st.dataframe(df_act[['Codigo', 'Producto', 'Stock_Inicial', 'Entradas', 'Salidas', 'Stock_Actual']], 
                     use_container_width=True, hide_index=True)

        st.divider()
        
        # 2. Registrar
        with st.expander("➕ REGISTRAR MOVIMIENTO", expanded=True):
            df_base['Label'] = df_base['Codigo'] + " | " + df_base['Producto']
            sel = st.multiselect("Buscar y seleccionar productos:", df_base['Label'])
            if sel:
                with st.form("f_registro"):
                    c1, c2 = st.columns(2)
                    t_op = c1.radio("Tipo:", ["Salida", "Entrada"], horizontal=True)
                    f_op = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        st.number_input(f"Cantidad para {s.split(' | ')[1]}:", key=f"val_{s}", min_value=0.0)
                    if st.form_submit_button("Guardar Movimientos"):
                        nuevos_datos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nom = s.split(" | ")[1]
                            nuevos_datos.append({'Fecha': str(f_op), 'Codigo': cid, 'Producto': nom,
                                                'Tipo': t_op, 'Cantidad': float(st.session_state[f"val_{s}"]),
                                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                                'Usuario': st.session_state['username']})
                        df_save = pd.concat([df_movs.drop(columns=['Entradas','Salidas'], errors='ignore'), pd.DataFrame(nuevos_datos)], ignore_index=True)
                        df_save.to_csv(FILE_MOVS, index=False, sep=';')
                        st.cache_data.clear(); st.success("¡Registrado!"); st.rerun()

        # 3. Historial con Buscador
        st.markdown("### 📑 Historial de Movimientos")
        busqueda = st.text_input("🔍 Buscar en el historial (por nombre, fecha, etc):")
        if not df_movs.empty:
            df_h = df_movs[['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']].copy()
            if busqueda:
                df_h = df_h[df_h.apply(lambda row: busqueda.lower() in row.astype(str).str.lower().values, axis=1)]
            st.dataframe(df_h.sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("📊 Análisis y Exportación de Datos")
        
        # Gráfico
        if not df_movs.empty:
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', barmode='group',
                         color_discrete_map={'Entrada': '#2ecc71', 'Salida': '#e74c3c'})
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # BOTONES DE DESCARGA (LOS DOS ESTÁN AQUÍ)
        st.markdown("### 📥 Descargar Reportes")
        col_d1, col_d2 = st.columns(2)
        
        # Botón 1: Inventario
        df_inv_desc = df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Inicial', 'Entradas', 'Salidas', 'Stock_Actual']].copy()
        col_d1.download_button(
            label="📥 Descargar Inventario Actualizado (.xlsx)",
            data=to_excel(df_inv_desc),
            file_name=f"Inventario_Tippytea_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Botón 2: Movimientos
        if not df_movs.empty:
            df_mov_desc = df_movs[['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']].copy()
            col_d2.download_button(
                label="📥 Descargar Historial (Kardex) (.xlsx)",
                data=to_excel(df_mov_desc),
                file_name=f"Kardex_Tippytea_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with tab3:
        st.subheader("⚙️ Panel de Correcciones")
        
        # A. Corregir Movimiento
        st.markdown("#### 🛠️ Modificar o Borrar Registro")
        if not df_movs.empty:
            df_movs['ID_CORR'] = df_movs.index.astype(str) + " - " + df_movs['Producto'] + " (" + df_movs['Tipo'] + ")"
            op_c = st.selectbox("Seleccione registro:", df_movs['ID_CORR'].iloc[::-1])
            idx_c = int(op_c.split(" - ")[0])
            with st.form("form_corr"):
                new_cant = st.number_input("Cantidad Correcta:", value=float(df_movs.iloc[idx_c]['Cantidad']))
                new_tipo = st.selectbox("Tipo Correcto:", ["Salida", "Entrada"], index=0 if df_movs.iloc[idx_c]['Tipo']=="Salida" else 1)
                c1, c2 = st.columns(2)
                if c1.form_submit_button("✅ Actualizar"):
                    df_movs.at[idx_c, 'Cantidad'] = new_cant
                    df_movs.at[idx_c, 'Tipo'] = new_tipo
                    df_movs.drop(columns=['ID_CORR','Entradas','Salidas'], errors='ignore').to_csv(FILE_MOVS, index=False, sep=';')
                    st.cache_data.clear(); st.rerun()
                if c2.form_submit_button("🗑️ Eliminar"):
                    df_movs.drop(idx_c).drop(columns=['ID_CORR','Entradas','Salidas'], errors='ignore').to_csv(FILE_MOVS, index=False, sep=';')
                    st.cache_data.clear(); st.rerun()

        st.divider()

        # B. Agregar Producto Nuevo
        st.markdown("#### ✨ Agregar Producto Nuevo al Listado")
        with st.form("form_n_prod"):
            ncod = st.text_input("Código")
            nnom = st.text_input("Nombre")
            nuni = st.selectbox("Unidad", ["gr", "kg", "uni", "ml"])
            nstock = st.number_input("Stock Inicial", min_value=0.0)
            if st.form_submit_button("Crear Producto"):
                if ncod and nnom:
                    df_ex_p = pd.read_csv(FILE_EXTRA_PRODS, sep=';') if os.path.exists(FILE_EXTRA_PRODS) else pd.DataFrame(columns=['Codigo','Producto','Unidad','Stock_Inicial'])
                    df_new_p = pd.DataFrame([{'Codigo':ncod, 'Producto':nnom, 'Unidad':nuni, 'Stock_Inicial':nstock}])
                    pd.concat([df_ex_p, df_new_p], ignore_index=True).to_csv(FILE_EXTRA_PRODS, index=False, sep=';')
                    st.cache_data.clear(); st.success(f"Producto {nnom} creado."); st.rerun()
