import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Tippytea | Kardex", layout="wide", page_icon="🍵")

# Nombres de archivos
FILE_MOVS = "movimientos_kardex.csv"
FILE_EXTRA_PRODS = "productos_extra.csv" 

def inicializar_archivos():
    # Asegura archivo de Movimientos (Donde están tus 40 registros)
    columnas_movs = ['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=columnas_movs).to_csv(FILE_MOVS, index=False)
    
    # Asegura archivo de Productos Extra (Se crea solo si no existe)
    columnas_extra = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
    if not os.path.exists(FILE_EXTRA_PRODS):
        pd.DataFrame(columns=columnas_extra).to_csv(FILE_EXTRA_PRODS, index=False)

inicializar_archivos()

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
def cargar_base_completa():
    # Cargar base original desde el CSV de Planta
    file_path = 'Inventarios - Planta.csv'
    df_base = pd.DataFrame()
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, skiprows=5)
        df.columns = df.columns.str.strip()
        # Ajustado a tu columna de conteo específica
        col_conteo = 'Conteo 02-02-2026'
        df_base = df[['Codigo', 'Nombre', 'Unidad', col_conteo]].copy()
        df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
        df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
        df_base = df_base.dropna(subset=['Producto'])

    # Unir con productos nuevos (los creados desde la app)
    if os.path.exists(FILE_EXTRA_PRODS):
        df_extra = pd.read_csv(FILE_EXTRA_PRODS)
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
        st.markdown(f"### 🛠️ Registro - Usuario: **{st.session_state['name']}**")
        with st.expander("Registrar Entradas / Salidas", expanded=True):
            df_base['L'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Seleccionar productos:", df_base['L'])
            if sel:
                with st.form("f_mov"):
                    c1, c2 = st.columns(2)
                    tipo = c1.radio("Operación:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"{s.split(' | ')[1]}", key=f"val_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar Movimiento"):
                        nuevos_m = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos_m.append({
                                'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                'Tipo': tipo, 'Cantidad': float(st.session_state[f"val_{cid}"]),
                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                'Usuario': st.session_state['username']
                            })
                        df_updated = pd.concat([df_movs, pd.DataFrame(nuevos_m)], ignore_index=True)
                        df_updated.to_csv(FILE_MOVS, index=False)
                        st.success("¡Registrado con éxito!")
                        st.rerun()

        st.markdown("### 📑 Historial de Movimientos")
        busqueda = st.text_input("🔍 Buscar por Código o Producto:")
        if not df_movs.empty:
            reporte_det = df_movs.copy().merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            reporte_det['Mov.'] = reporte_det.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            reporte_det = reporte_det[['Fecha', 'Codigo', 'Producto', 'Stock_Inicial', 'Mov.', 'Stock_Actual', 'Usuario']]
            if busqueda:
                reporte_det = reporte_det[reporte_det.apply(lambda row: busqueda.lower() in str(row).lower(), axis=1)]
            st.dataframe(reporte_det.sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Reportes")
        if not df_movs.empty:
            c1, c2 = st.columns(2)
            c1.download_button("📥 Inventario Actual (.xlsx)", data=to_excel(df_final[['Codigo','Producto','Unidad','Stock_Actual']]), file_name="Inventario.xlsx")
            c2.download_button("📥 Historial Filtrado (.xlsx)", data=to_excel(reporte_det), file_name="Historial.xlsx")
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', barmode='group')
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("⚙️ Panel de Mantenimiento")
        
        # AGREGAR PRODUCTO NUEVO
        with st.expander("✨ Dar de alta un producto nuevo"):
            st.info("Esto añadirá el producto a la lista de gestión sin borrar los existentes.")
            with st.form("form_nuevo"):
                nc = st.text_input("Código")
                nn = st.text_input("Nombre")
                nu = st.selectbox("Unidad", ["gr", "uni", "kg", "ml"])
                ns = st.number_input("Stock Inicial", min_value=0.0)
                if st.form_submit_button("Confirmar Producto"):
                    if nc and nn:
                        df_ex = pd.read_csv(FILE_EXTRA_PRODS)
                        new_p = pd.DataFrame([{'Codigo': nc, 'Producto': nn, 'Unidad': nu, 'Stock_Inicial': ns}])
                        pd.concat([df_ex, new_p], ignore_index=True).to_csv(FILE_EXTRA_PRODS, index=False)
                        st.cache_data.clear()
                        st.success(f"Producto {nn} listo.")
                        st.rerun()

        st.divider()
        st.markdown("#### 🛠️ Corregir Datos")
        if not df_movs.empty:
            df_edit = df_movs.copy()
            df_edit['Sel'] = df_edit.index.astype(str) + " | " + df_edit['Producto']
            op_edit = st.selectbox("Registro a editar:", df_edit['Sel'])
            idx_edit = int(op_edit.split(" | ")[0])
            row = df_movs.iloc[idx_edit]
            
            with st.form("edit_f"):
                e_f = st.text_input("Fecha", value=row['Fecha'])
                e_c = st.number_input("Cantidad", value=float(row['Cantidad']))
                if st.form_submit_button("Guardar Cambios"):
                    df_movs.at[idx_edit, 'Fecha'] = e_f
                    df_movs.at[idx_edit, 'Cantidad'] = e_c
                    df_movs.to_csv(FILE_MOVS, index=False)
                    st.success("Información actualizada.")
                    st.rerun()
        
        if st.button("↩️ Deshacer Último Registro"):
            if not df_movs.empty:
                pd.read_csv(FILE_MOVS).drop(df_movs.index[-1]).to_csv(FILE_MOVS, index=False)
                st.warning("Eliminado."); st.rerun()
