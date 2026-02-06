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
FILE_EXTRA_PRODS = "productos_extra.csv"

def inicializar_archivos():
    if not os.path.exists(FILE_MOVS):
        pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario']).to_csv(FILE_MOVS, index=False)
    if not os.path.exists(FILE_EXTRA_PRODS):
        pd.DataFrame(columns=['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']).to_csv(FILE_EXTRA_PRODS, index=False)

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
    file_path = 'Inventarios - Planta.csv'
    df_base = pd.DataFrame()
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, skiprows=5)
        df.columns = df.columns.str.strip()
        col_conteo = 'Conteo 02-02-2026'
        df_base = df[['Codigo', 'Nombre', 'Unidad', col_conteo]].copy()
        df_base.columns = ['Codigo', 'Producto', 'Unidad', 'Stock_Inicial']
        df_base['Stock_Inicial'] = df_base['Stock_Inicial'].apply(limpiar_monto)
        df_base = df_base.dropna(subset=['Producto'])

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

    # --- CÁLCULO DE STOCK ACTUAL ---
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
        st.subheader(f"Bienvenido, {st.session_state['name']}")
        
        # 1. TABLA DE INVENTARIO ACTUAL (LA QUE SE HABÍA IDO)
        st.markdown("### 🏬 Inventario Actualizado")
        busqueda_inv = st.text_input("🔍 Buscar en inventario (Código o Nombre):", key="search_inv")
        df_display_inv = df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']].copy()
        if busqueda_inv:
            df_display_inv = df_display_inv[df_display_inv.apply(lambda r: busqueda_inv.lower() in str(r).lower(), axis=1)]
        st.dataframe(df_display_inv, use_container_width=True, hide_index=True)

        st.divider()

        # 2. REGISTRO DE MOVIMIENTOS
        with st.expander("➕ Registrar Nuevo Movimiento", expanded=False):
            df_base['L'] = df_base['Codigo'].astype(str) + " | " + df_base['Producto']
            sel = st.multiselect("Seleccionar productos:", df_base['L'])
            if sel:
                with st.form("f_mov"):
                    c1, c2 = st.columns(2)
                    tipo = c1.radio("Operación:", ["Salida", "Entrada"], horizontal=True)
                    fecha = c2.date_input("Fecha:", datetime.now())
                    for s in sel:
                        cid = s.split(" | ")[0]
                        st.number_input(f"Cantidad para: {s.split(' | ')[1]}", key=f"val_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({
                                'Fecha': str(fecha), 'Codigo': cid, 'Producto': s.split(" | ")[1],
                                'Tipo': tipo, 'Cantidad': float(st.session_state[f"val_{cid}"]),
                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                'Usuario': st.session_state['username']
                            })
                        pd.concat([df_movs, pd.DataFrame(nuevos)], ignore_index=True).to_csv(FILE_MOVS, index=False)
                        st.success("Guardado!"); st.rerun()

        st.markdown("### 📑 Historial de Movimientos")
        if not df_movs.empty:
            st.dataframe(df_movs.sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 📊 Análisis de Movimientos")
        if not df_movs.empty:
            # Gráfico con mejores colores
            fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(), 
                         x='Producto', y='Cantidad', color='Tipo', 
                         barmode='group',
                         color_discrete_map={'Entrada': '#2ecc71', 'Salida': '#e74c3c'}) # Verde y Rojo
            st.plotly_chart(fig, use_container_width=True)
            
            st.download_button("📥 Descargar Reporte Excel", data=to_excel(df_final), file_name="Inventario_Tippytea.xlsx")

    with tab3:
        st.subheader("⚙️ Mantenimiento del Sistema")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("#### ✨ Producto Nuevo")
            with st.form("n_prod_form"):
                nc = st.text_input("Código")
                nn = st.text_input("Nombre")
                nu = st.selectbox("Unidad", ["gr", "uni", "kg", "ml"])
                ns = st.number_input("Stock Inicial", min_value=0.0)
                if st.form_submit_button("Crear"):
                    if nc and nn:
                        df_ex = pd.read_csv(FILE_EXTRA_PRODS)
                        pd.concat([df_ex, pd.DataFrame([{'Codigo':nc,'Producto':nn,'Unidad':nu,'Stock_Inicial':ns}])], ignore_index=True).to_csv(FILE_EXTRA_PRODS, index=False)
                        st.cache_data.clear(); st.success("Creado!"); st.rerun()

        with c2:
            st.markdown("#### 🛠️ Corregir Registro")
            if not df_movs.empty:
                df_edit = df_movs.copy()
                df_edit['Label'] = df_edit.index.astype(str) + " - " + df_edit['Producto']
                sel_edit = st.selectbox("Elegir para corregir:", df_edit['Label'])
                idx = int(sel_edit.split(" - ")[0])
                with st.form("edit_form"):
                    new_f = st.text_input("Fecha", value=df_movs.iloc[idx]['Fecha'])
                    new_c = st.number_input("Cantidad", value=float(df_movs.iloc[idx]['Cantidad']))
                    if st.form_submit_button("Actualizar"):
                        df_movs.at[idx, 'Fecha'] = new_f
                        df_movs.at[idx, 'Cantidad'] = new_c
                        df_movs.to_csv(FILE_MOVS, index=False)
                        st.success("Corregido!"); st.rerun()

        st.divider()
        if st.button("🗑️ Borrar ÚLTIMO Registro Completo"):
            if not df_movs.empty:
                df_movs.drop(df_movs.index[-1]).to_csv(FILE_MOVS, index=False)
                st.warning("Eliminado."); st.rerun()
