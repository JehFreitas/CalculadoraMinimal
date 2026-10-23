# app.py
# Calculadora Comercial Minimal — ponto de entrada (Streamlit).
#
# Menu lateral com quatro cálculos:
#   NF-e Minimal 2026 / 2027                 -> tela_nfe.py   (calculo.py, calculo_2027.py)
#   Venda Assistida Cavaletti 2026 / 2027    -> tela_cavaletti.py (cavaletti.py)
# Parâmetros: config.json, config_2027.json, config_cavaletti.json (editáveis pelo Adm).
# Senhas e chaves: Secrets do Streamlit Cloud (ver LEIA-ME.md).

import streamlit as st

import comum
import tela_cavaletti
import tela_nfe

st.set_page_config(page_title="Calculadora Comercial - Minimal", layout="wide")
st.markdown(comum.CSS, unsafe_allow_html=True)


def nfe_2026():
    tela_nfe.render("2026")


def nfe_2027():
    tela_nfe.render("2027")


def cav_2026():
    tela_cavaletti.render("2026")


def cav_2027():
    tela_cavaletti.render("2027")


paginas = st.navigation({
    "NF-e Minimal": [
        st.Page(nfe_2026, title="Cálculo 2026", icon="🧾", url_path="calculo-2026", default=True),
        st.Page(nfe_2027, title="Cálculo 2027", icon="🔒", url_path="calculo-2027"),
    ],
    "Venda Assistida Cavaletti": [
        st.Page(cav_2026, title="Cavaletti 2026", icon="🪑", url_path="cavaletti-2026"),
        st.Page(cav_2027, title="Cavaletti 2027", icon="🔒", url_path="cavaletti-2027"),
    ],
})

# ---------------- Área do Adm (vale para todas as telas) ----------------
with st.sidebar:
    st.divider()
    senha_cfg = comum.senha_adm()
    if comum.adm_logado():
        st.success("Adm Comercial conectado")
        if st.button("Sair da área do Adm"):
            st.session_state.adm_ok = False
            st.rerun()
    elif senha_cfg:
        with st.expander("🔐 Área do Adm Comercial"):
            senha = st.text_input("Senha", type="password", key="senha_adm_input")
            if st.button("Entrar"):
                if senha == senha_cfg:
                    st.session_state.adm_ok = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
    else:
        st.caption("Cadastre ADM_SENHA nos Secrets do app para liberar a área do Adm.")

paginas.run()
