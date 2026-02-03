import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import datetime
import os
import plotly.express as px
import io

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Tippytea | Business Intelligence", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #f3f6f1 0%, #e1e8d5 100%); }
    .login-card { background: white; padding: 3rem; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); border-top: 8px solid #2e7d32; text-align: center; }
    div.stButton > button { background-color: #2e7d32 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 3.5rem; width: 100%; border: none !important; }
    div.stButton > button:hover { background-color: #1b5e20 !important; transform: scale(1.02); }
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)


# --- 2. FUNCIONES DE CONVERSIÓN A EXCEL ---
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    return output.getvalue()


def limpiar_monto(valor):
    if pd.isna(valor) or str(valor).strip() in ["-", "", "0"]: return 0.0
    if isinstance(valor, str):
        v = valor.strip().replace('.', '').replace(',', '.')
        try:
            return float(v)
        except:
            return 0.0
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


# --- 3. SEGURIDAD ---
credentials = {
    "usernames": {
        "martin_admin": {"name": "Martín Tippytea", "password": "Tippytea2025*"},
        "Jennys_Contabilidad": {"name": "Jenny Contabilidad", "password": "Tippytea2026+"}
    }
}
stauth.Hasher.hash_passwords(credentials)
authenticator = stauth.Authenticate(credentials, "tippy_excel_v6", "auth_key_999", cookie_expiry_days=30)

if not st.session_state.get("authentication_status"):
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.image("https://tippytea.com/wp-content/uploads/2021/07/logo-tippytea.png", width=220)
        authenticator.login(location='main')
        st.markdown('</div>', unsafe_allow_html=True)

if st.session_state["authentication_status"]:
    authenticator.logout('Cerrar Sesión', 'sidebar')

    FILE_MOVS = 'movimientos_kardex.csv'
    FILE_EXTRA = 'productos_nuevos.csv'

    df_base = cargar_base_inicial()
    if os.path.exists(FILE_EXTRA):
        df_base = pd.concat([df_base, pd.read_csv(FILE_EXTRA)], ignore_index=True)

    if os.path.exists(FILE_MOVS):
        df_movs = pd.read_csv(FILE_MOVS)
    else:
        df_movs = pd.DataFrame(columns=['Fecha', 'Codigo', 'Producto', 'Tipo', 'Cantidad', 'Unidad', 'Usuario'])

    # --- CÁLCULOS ---
    if not df_movs.empty:
        df_movs['Ajuste'] = df_movs.apply(lambda x: x['Cantidad'] if x['Tipo'] == 'Entrada' else -x['Cantidad'], axis=1)
        resumen = df_movs.groupby('Codigo')['Ajuste'].sum().reset_index()
        df_final = pd.merge(df_base, resumen, on='Codigo', how='left').fillna(0)
        df_final['Stock_Actual'] = df_final['Stock_Inicial'] + df_final['Ajuste']
        codigos_movidos = df_movs['Codigo'].unique()
        df_solo_movidos = df_final[df_final['Codigo'].isin(codigos_movidos)]
    else:
        df_final = df_base.copy()
        df_final['Stock_Actual'] = df_final['Stock_Inicial']
        df_solo_movidos = pd.DataFrame()

    tab1, tab2, tab3 = st.tabs(["📋 Gestión de Stock", "📈 Análisis Contable", "⚙️ Configuración"])

   # --- TAB 1: GESTIÓN ---
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
                        pnom = s.split(" | ")[1]
                        unit = df_base[df_base['Codigo'] == cid]['Unidad'].values[0]
                        st.number_input(f"{pnom} ({unit})", key=f"val_{cid}", min_value=0.0)
                    
                    if st.form_submit_button("Guardar"):
                        nuevos = []
                        for s in sel:
                            cid = s.split(" | ")[0]
                            nuevos.append({
                                'Fecha': fecha, 
                                'Codigo': cid, 
                                'Producto': s.split(" | ")[1],
                                'Tipo': tipo, 
                                'Cantidad': st.session_state[f"val_{cid}"],
                                'Unidad': df_base[df_base['Codigo'] == cid]['Unidad'].values[0],
                                'Usuario': st.session_state['username']
                            })
                        df_movs = pd.concat([df_movs, pd.DataFrame(nuevos)], ignore_index=True)
                        df_movs.to_csv(FILE_MOVS, index=False)
                        st.success("¡Registrado!")
                        st.rerun()

        # --- NUEVA SECCIÓN: LISTADO DE ÚLTIMOS MOVIMIENTOS CON STOCK ---
        st.divider()
        st.markdown("### 📑 Resumen de Transacciones")
        
        if not df_movs.empty:
            # Creamos una copia para el reporte visual
            reporte = df_movs.copy()
            
            # Cruzamos con df_final para obtener el Stock Actual
            reporte = reporte.merge(df_final[['Codigo', 'Stock_Inicial', 'Stock_Actual']], on='Codigo', how='left')
            
            # Calculamos el Stock Antes del movimiento específico
            # Stock_Antes = Stock_Actual - (Suma de todos los ajustes hasta ese momento)
            # Para simplificar la vista del usuario:
            reporte['Movimiento'] = reporte.apply(lambda x: f"+ {x['Cantidad']}" if x['Tipo'] == 'Entrada' else f"- {x['Cantidad']}", axis=1)
            
            # Ordenamos para mostrar lo más reciente arriba
            reporte_vista = reporte[['Fecha', 'Producto', 'Stock_Inicial', 'Movimiento', 'Stock_Actual', 'Usuario']].sort_index(ascending=False)
            
            # Renombramos columnas para que Jenny lo entienda claro
            reporte_vista.columns = ['Fecha', 'Producto', 'S. Inicial (Excel)', 'Movimiento', 'S. Final (Actual)', 'Responsable']
            
            st.dataframe(reporte_vista, use_container_width=True, hide_index=True)
        else:
            st.info("No hay movimientos registrados todavía.")

        st.divider()
        st.markdown("### 📦 Inventario General")
        st.dataframe(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']], use_container_width=True, hide_index=True)

    # --- TAB 2: ANÁLISIS CONTABLE ---
    with tab2:
        st.markdown("### 📊 Auditoría y Descargas Excel")

        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Items Totales", len(df_final))
        c_m2.metric("Items con Movimiento", len(df_solo_movidos))
        c_m3.metric("Alertas Stock Bajo", len(df_final[df_final['Stock_Actual'] < 50]))

        st.divider()

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            st.subheader("🔍 Buscador de Stock")
            q = st.text_input("Producto o Código:")
            if q:
                res = df_final[
                    df_final['Producto'].str.contains(q, case=False) | df_final['Codigo'].str.contains(q, case=False)]
                st.table(res[['Codigo', 'Producto', 'Stock_Actual', 'Unidad']])

            if not df_movs.empty:
                fig = px.bar(df_movs.groupby(['Producto', 'Tipo'])['Cantidad'].sum().reset_index(),
                             x='Producto', y='Cantidad', color='Tipo', barmode='group',
                             title="Entradas vs Salidas",
                             color_discrete_map={'Entrada': '#2e7d32', 'Salida': '#e74c3c'})
                st.plotly_chart(fig, use_container_width=True)

        with col_a2:
            st.subheader("📥 Exportar a Excel")
            # BOTONES DE DESCARGA EN EXCEL
            excel_all = to_excel(df_final[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']])
            st.download_button(label="📥 Descargar Inventario (.xlsx)", data=excel_all,
                               file_name=f"Inventario_Total_{datetime.now().strftime('%d_%m')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            if not df_solo_movidos.empty:
                excel_mov = to_excel(df_solo_movidos[['Codigo', 'Producto', 'Unidad', 'Stock_Actual']])
                st.download_button(label="📥 Descargar Solo Movidos (.xlsx)", data=excel_mov,
                                   file_name=f"Productos_Movidos_{datetime.now().strftime('%d_%m')}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.subheader("📝 Historial de Movimientos")
        st.dataframe(df_movs[['Fecha', 'Producto', 'Tipo', 'Cantidad', 'Usuario']].sort_index(ascending=False),
                     use_container_width=True)

    # --- TAB 3: CONFIGURACIÓN ---
    with tab3:
        st.subheader("⚙️ Mantenimiento")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            with st.form("n_i"):
                nc, np, nu = st.text_input("Código"), st.text_input("Nombre"), st.selectbox("Unidad",
                                                                                            ["gr", "und", "kg", "caja",
                                                                                             "litro"])
                ni = st.number_input("Stock Inicial", min_value=0.0)
                if st.form_submit_button("Añadir Item"):
                    pd.DataFrame([{'Codigo': nc, 'Producto': np, 'Unidad': nu, 'Stock_Inicial': ni}]).to_csv(FILE_EXTRA,
                                                                                                             mode='a',
                                                                                                             header=not os.path.exists(
                                                                                                                 FILE_EXTRA),
                                                                                                             index=False)
                    st.success("Añadido");
                    st.rerun()

        with col_c2:
            if st.button("↩️ Deshacer Último Registro"):
                if os.path.exists(FILE_MOVS):
                    df_t = pd.read_csv(FILE_MOVS)
                    if not df_t.empty:
                        df_t.drop(df_t.index[-1]).to_csv(FILE_MOVS, index=False);
                        st.rerun()

            st.divider()
            if st.button("🔴 RESET TOTAL"):

                if os.path.exists(FILE_MOVS): os.remove(FILE_MOVS); st.rerun()
