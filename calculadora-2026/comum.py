# comum.py
# Funções de tela compartilhadas pelos cálculos (formatação, PDF, área do Adm, envio).

import io
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

import servicos
from calculo import PASTA

LOGO = os.path.join(PASTA, "logo_minimal.png")
FUSO = ZoneInfo("America/Sao_Paulo")
AZUL = (0.333, 0.525, 0.6)

CSS = """
    <style>
    body { background-color: #f6f8fa; }
    .block-container { padding-top: 2rem; max-width: 1100px; }
    h1, h2, h3, h4 { color: #000000; font-family: 'Helvetica Neue', sans-serif; }
    [data-baseweb="radio"] label span { color: #33606f; font-weight: 500; }
    .stNumberInput input[type="number"], .stTextInput input {
        border: 1px solid #558699 !important; border-radius: 6px !important;
        background-color: #f8fafc;
    }
    .stSelectbox div[data-baseweb="select"] > div {
        border: 1px solid #558699 !important; border-radius: 6px !important;
        background-color: #f8fafc;
    }
    </style>
"""


def formatar(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md(texto):
    """Escapa o "$" de "R$" para o Streamlit não tratar o trecho como fórmula."""
    return texto.replace("$", "\\$")


def fmt_pct(fracao):
    return f"{fracao * 100:.2f}%".replace(".", ",")


def agora():
    return datetime.now(FUSO).strftime("%d/%m/%Y %H:%M")


def n(v):
    return round(float(v), 2)


def senha_adm():
    return servicos.senha_adm(st)


def adm_logado():
    return bool(st.session_state.get("adm_ok"))


def cabecalho(titulo, subtitulo):
    st.image(LOGO, width=140)
    st.title(titulo)
    st.caption(subtitulo)


def aviso_bloqueado(motivo):
    st.warning(f"🔒 **Cálculo bloqueado para uso.** {motivo}  \n"
               "A tela fica disponível para conferência. Somente o Adm Comercial pode simular "
               "até a liberação.")


# ------------------------------------------------------------------
# Parâmetros: salvar (memória, arquivo e GitHub)
# ------------------------------------------------------------------
def salvar_parametros(chave_ss, novo, salvar_local, arquivo):
    st.session_state[chave_ss] = novo
    try:
        salvar_local(novo)
    except OSError:
        pass
    ok, msg = servicos.salvar_config_github(st, novo, arquivo)
    if ok:
        st.success(msg)
    else:
        st.warning(msg + " Os parâmetros valem até o app reiniciar; baixe o arquivo "
                   "abaixo e envie ao GitHub para torná-los permanentes.")


def botao_backup(novo, arquivo):
    st.download_button(f"Baixar {arquivo} (backup)",
                       data=json.dumps(novo, ensure_ascii=False, indent=2),
                       file_name=arquivo, mime="application/json")


# ------------------------------------------------------------------
# PDF
# ------------------------------------------------------------------
def gerar_pdf(titulo_versao, cabecalho_linhas, blocos, notas=(), senha=None):
    """
    cabecalho_linhas: [(rótulo, valor texto)]
    blocos: [(título, [(rótulo, valor Decimal ou texto)])]
    """
    buffer = io.BytesIO()
    if senha:
        enc = StandardEncryption(userPassword=senha, ownerPassword=senha,
                                 canPrint=1, canModify=0, canCopy=0, canAnnotate=0)
        c = canvas.Canvas(buffer, pagesize=A4, encrypt=enc)
    else:
        c = canvas.Canvas(buffer, pagesize=A4)
    c.drawImage(LOGO, 40, 805, width=70, preserveAspectRatio=True, mask='auto')
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(*AZUL)
    c.drawString(150, 830, "Calculadora Comercial - Minimal Design")
    c.setFont("Helvetica", 9)
    c.drawString(150, 816, titulo_versao)

    y = [795]

    def nova_linha(passo):
        y[0] -= passo
        if y[0] < 60:
            c.showPage()
            y[0] = 800

    for rot, val in cabecalho_linhas:
        nova_linha(14)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(*AZUL)
        c.drawString(40, y[0], rot)
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(160, y[0], str(val))

    for titulo, linhas in blocos:
        nova_linha(22)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(*AZUL)
        c.drawString(40, y[0], titulo)
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0, 0, 0)
        for rot, val in linhas:
            nova_linha(14)
            texto = val if isinstance(val, str) else formatar(val)
            c.drawString(40, y[0], f"{rot.strip()}: {texto}")

    if notas:
        nova_linha(10)
        c.setFont("Helvetica", 8)
        for t in notas:
            nova_linha(11)
            c.drawString(40, y[0], t)
    c.save()
    return buffer.getvalue()


# ------------------------------------------------------------------
# Envio ao ADM Comercial
# ------------------------------------------------------------------
def bloco_envio(sim, meta, tipo, montar_envio, nome_arquivo):
    """
    sim: dicionário da simulação em st.session_state (guarda 'enviado' e 'tentativa')
    montar_envio(quando) -> (linha_planilha, assunto, corpo_html, anexos, pdf_adm)
    """
    with st.container(border=True):
        st.subheader("Enviar ao ADM Comercial")
        if sim.get("enviado"):
            st.success(f"✅ Simulação enviada e salva em {sim['enviado']}.")
            return
        falta = [rot for chave, rot in (("vendedor", "Vendedor"), ("cliente", "Cliente"),
                                        ("orcamento", "Orçamento")) if not meta.get(chave)]
        if falta:
            st.caption("Para enviar, preencha: " + ", ".join(falta) + " e calcule de novo.")
        if st.button("📨 Enviar simulação ao ADM Comercial e salvar", disabled=bool(falta),
                     key=f"enviar_{tipo}_{nome_arquivo}"):
            quando = agora()
            linha, assunto, corpo, anexos, pdf_adm = montar_envio(quando)
            ok_p, msg_p, ok_e, msg_e = servicos.enviar_e_salvar(st, linha, assunto, corpo, anexos, tipo)
            sim["tentativa"] = dict(ok_p=ok_p, msg_p=msg_p, ok_e=ok_e, msg_e=msg_e,
                                    linha=linha, pdf_adm=pdf_adm)
            if ok_p and ok_e:
                sim["enviado"] = quando
                st.rerun()

        t = sim.get("tentativa")
        if t:
            msgs = [(t["ok_p"], t["msg_p"])]
            if t["msg_e"] != t["msg_p"]:
                msgs.append((t["ok_e"], t["msg_e"]))
            for ok, msg in msgs:
                (st.success if ok else st.warning)(msg)
            if not (t["ok_p"] and t["ok_e"]):
                st.caption("Enquanto o envio automático não estiver disponível, baixe os arquivos "
                           "e envie ao ADM Comercial:")
                c1, c2 = st.columns(2)
                if not t["ok_p"]:
                    c1.download_button("Baixar registro da simulação (CSV)",
                                       data=servicos.linha_csv(t["linha"], tipo),
                                       file_name=f"registro_{nome_arquivo}.csv", mime="text/csv")
                if not t["ok_e"]:
                    c2.download_button("Baixar PDF do Adm Comercial", data=t["pdf_adm"],
                                       file_name=f"ADM_{nome_arquivo}.pdf", mime="application/pdf")


def nome_base(meta):
    cli = (meta.get("cliente") or "Cliente").strip().replace(" ", "_").replace("/", "-")
    orc = (meta.get("orcamento") or "Orcamento").strip().replace(" ", "_").replace("/", "-")
    return f"Simulacao_{cli}_{orc}"
