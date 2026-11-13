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
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from xml.sax.saxutils import escape

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


def numero_br(texto):
    """Lê um número digitado ou colado em qualquer formato comum:
    42.671,46 · 42671,46 · 42671.46 · R$ 42.671,46 · 1.234.567 · 18,8532. None se não der."""
    if texto is None:
        return None
    t = str(texto).strip().replace("R$", "").replace(" ", "").replace("\u00a0", "").replace("%", "")
    if not t:
        return None
    neg = t.startswith("-")
    t = t.lstrip("+-")
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mil = "." if dec == "," else ","
        t = t.replace(mil, "").replace(dec, ".")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", "") if (len(partes) > 2) else t.replace(",", ".")
    elif "." in t:
        partes = t.split(".")
        # ponto como separador de milhar: vários pontos, ou um só com 3 dígitos depois e parte inteira > 0
        if len(partes) > 2 or (len(partes[-1]) == 3 and partes[0] not in ("", "0")):
            t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def fmt_br(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def campo_numero(rotulo, chave, casas=2, minimo=0.0, maximo=None, help=None, placeholder=None, container=None):
    """Campo de texto para valores em formato brasileiro (ponto no milhar, vírgula no decimal).
    Aceita valores colados em qualquer formato e reescreve no padrão. O número fica em
    st.session_state[chave] (float ou None); o texto, em chave + '_txt'."""
    ss = st.session_state
    tk = chave + "_txt"
    if ss.get(chave) is not None and not ss.get(tk):
        ss[tk] = fmt_br(float(ss[chave]), casas)

    def ao_mudar():
        txt = ss.get(tk) or ""
        if maximo is not None and maximo <= 100 and txt.count(".") == 1 and "," not in txt:
            txt = txt.replace(".", ",")          # percentual: ponto sozinho é decimal (18.8532)
        v = numero_br(txt)
        if v is not None and (v < minimo or (maximo is not None and v > maximo)):
            v = None
        ss[chave] = v
        if v is not None:
            ss[tk] = fmt_br(v, casas)

    (container or st).text_input(rotulo, key=tk, on_change=ao_mudar, help=help,
                                 placeholder=placeholder or ("0," + "0" * casas))
    if (ss.get(tk) or "").strip() and ss.get(chave) is None:
        (container or st).caption(":red[Valor não reconhecido. Exemplo: "
                                  + ("42.671,46" if casas == 2 else "18,8532") + "]")
    return ss.get(chave)


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
COR = colors.HexColor("#558699")        # azul Minimal (mesmo da tela)
COR_ESCURA = colors.HexColor("#33606F")
COR_CLARA = colors.HexColor("#EAF1F4")
CINZA = colors.HexColor("#6B7280")
LINHA = colors.HexColor("#D5DEE2")
VERDE = colors.HexColor("#22A447")      # etiquetas como no Focco
VERMELHO = colors.HexColor("#E8473F")
CONTATO = "Dúvidas: Custos · custos@minimaldesign.com.br"

_E = getSampleStyleSheet()
_TXT = ParagraphStyle("txt", parent=_E["Normal"], fontName="Helvetica", fontSize=9, leading=11.5)
_TXT_B = ParagraphStyle("txtb", parent=_TXT, fontName="Helvetica-Bold")
_DIR = ParagraphStyle("dir", parent=_TXT, alignment=2)
_DIR_B = ParagraphStyle("dirb", parent=_DIR, fontName="Helvetica-Bold")
_ROT = ParagraphStyle("rot", parent=_TXT, fontSize=7.5, leading=9, textColor=CINZA)
_SEC = ParagraphStyle("sec", parent=_TXT, fontName="Helvetica-Bold", fontSize=13, leading=16,
                      textColor=COR_ESCURA, spaceBefore=4, spaceAfter=6)
_NOTA = ParagraphStyle("nota", parent=_TXT, fontSize=7.5, leading=9.5, textColor=CINZA)
_ETQ = ParagraphStyle("etq", parent=_TXT, fontName="Helvetica-Bold", fontSize=8, leading=9,
                      textColor=colors.white, alignment=1)

LARGURA = A4[0] - 2 * 40


def _p(texto, estilo=_TXT):
    return Paragraph(escape(str(texto)), estilo)


def _destaque(rotulo):
    r = rotulo.strip().lower()
    return r.startswith(("valor total", "valor dos produtos", "total nfe", "total nfse"))


def _quadro(titulo, linhas):
    """Bloco: faixa com o título e linhas rótulo | valor (valor alinhado à direita)."""
    dados = [[_p(titulo, ParagraphStyle("t", parent=_TXT_B, textColor=colors.white)), ""]]
    estilo = [("SPAN", (0, 0), (1, 0)), ("BACKGROUND", (0, 0), (-1, 0), COR),
              ("BOX", (0, 0), (-1, -1), 0.6, LINHA),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]
    for rot, val in linhas:
        lin = len(dados)
        if val is None:
            dados.append([_p(rot.strip()), ""])
            estilo.append(("SPAN", (0, lin), (1, lin)))
        else:
            forte = _destaque(rot)
            texto = val if isinstance(val, str) else (
                "− " + formatar(-val) if val < 0 else formatar(val))
            recuo = rot.startswith(" ")
            st_rot = ParagraphStyle("r", parent=_TXT_B if forte else _TXT, leftIndent=10 if recuo else 0,
                                    textColor=CINZA if recuo else colors.black)
            dados.append([_p(rot.strip().lstrip("· ").strip() if recuo else rot.strip(), st_rot),
                          _p(texto, _DIR_B if forte else _DIR)])
            if forte:
                estilo.append(("BACKGROUND", (0, lin), (-1, lin), COR_CLARA))
        if lin > 1:
            estilo.append(("LINEABOVE", (0, lin), (-1, lin), 0.4, LINHA))
    t = Table(dados, colWidths=[LARGURA * 0.72, LARGURA * 0.28])
    t.setStyle(TableStyle(estilo))
    return KeepTogether([t, Spacer(1, 10)])


def _dados_orcamento(cabecalho_linhas):
    """Grade com os dados do orçamento, duas colunas de pares rótulo/valor."""
    itens = [(r.rstrip(": ").strip(), v) for r, v in cabecalho_linhas]
    curtos = [x for x in itens if len(str(x[1])) <= 42]
    longos = [x for x in itens if len(str(x[1])) > 42]
    celulas = [[_p(r, _ROT), _p(v or "-", _TXT_B)] for r, v in curtos]
    if len(celulas) % 2:
        celulas.append(["", ""])
    dados = [celulas[i] + celulas[i + 1] for i in range(0, len(celulas), 2)]
    w = LARGURA / 2
    estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, -1), COR_CLARA),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
              ("LEFTPADDING", (0, 0), (-1, -1), 8)]
    for r, v in longos:
        lin = len(dados)
        dados.append([_p(r, _ROT), _p(v, _TXT_B), "", ""])
        estilo.append(("SPAN", (1, lin), (3, lin)))
    t = Table(dados, colWidths=[w * 0.32, w * 0.68, w * 0.32, w * 0.68])
    t.setStyle(TableStyle(estilo))
    return [t, Spacer(1, 12)]


def _pct4(v):
    return f"{float(v):.4f}".replace(".", ",") + "%"


def _num(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pagina_focco(f):
    """Quadros no formato das telas do Focco: Descontos e Acréscimos, Totais e Entrega."""
    out = [PageBreak(), _p("Lançar no orçamento do Focco", _SEC),
           _p("Os quadros abaixo seguem as telas do Focco. Digite cada valor no campo indicado e "
              "confira os totais antes de salvar o orçamento.", _NOTA), Spacer(1, 8)]

    # Descontos e Acréscimos
    cab = ["Tipo", "Descrição", "Valor", "Tipo Valor", "Aplicação"]
    dados = [[_p(c, _TXT_B) if c not in ("Valor",) else _p(c, _DIR_B) for c in cab]]
    estilo = [("LINEBELOW", (0, 0), (-1, 0), 0.8, COR_ESCURA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    for tipo, desc, valor, tipo_valor, aplic in f["lancamentos"]:
        lin = len(dados)
        etq = Table([[_p(tipo, _ETQ)]], colWidths=[62], rowHeights=[14])
        etq.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), VERDE if tipo == "Desconto" else VERMELHO),
                                 ("ROUNDEDCORNERS", [3, 3, 3, 3]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
        v = _pct4(valor) if tipo_valor == "Percentual" else _num(valor)
        dados.append([etq, _p(desc), _p(v, _DIR_B), _p(tipo_valor), _p(aplic)])
        if lin > 1:
            estilo.append(("LINEABOVE", (0, lin), (-1, lin), 0.4, LINHA))
    t = Table(dados, colWidths=[72, LARGURA - 72 - 82 - 70 - 105, 82, 70, 105])
    t.setStyle(TableStyle(estilo))
    out += [_titulo_quadro("Descontos e Acréscimos"), t]
    for nota in f.get("notas_lancamentos", ()):
        out += [Spacer(1, 3), _p(nota, _NOTA)]
    if f.get("politica_itens"):
        out += [Spacer(1, 8), _titulo_quadro("Política em cada item (700/1/3)")]
        d2 = [[_p("Item", _TXT_B), _p("Política", _DIR_B)]] + \
             [[_p(i), _p(_pct4(p), _DIR_B)] for i, p in f["politica_itens"]]
        t2 = Table(d2, colWidths=[LARGURA - 100, 100])
        t2.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, COR_ESCURA),
                                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA)]))
        out.append(t2)
    out.append(Spacer(1, 16))

    # Totais e Entrega lado a lado
    tot = [[_p(r, _DIR), _p("R$", _TXT_B), _p(_num(v), _DIR_B)] for r, v in f["totais"][:-1]]
    r_fim, v_fim = f["totais"][-1]
    tot.append([_p(r_fim, _DIR_B), _p("R$", _TXT_B), _p(_num(v_fim), _DIR_B)])
    tt = Table(tot, colWidths=[110, 24, 96])
    tt.setStyle(TableStyle([("LINEABOVE", (0, len(tot) - 1), (-1, len(tot) - 1), 0.8, COR_ESCURA),
                            ("BACKGROUND", (0, len(tot) - 1), (-1, len(tot) - 1), COR_CLARA),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    ent = []
    for rot, val in f["entrega"]:
        caixa = Table([[_p(val if isinstance(val, str) else _num(val),
                           _TXT if isinstance(val, str) else _DIR_B)]], colWidths=[200])
        caixa.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINHA),
                                   ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        ent += [[_p(rot, _ROT)], [caixa], [Spacer(1, 4)]]
    te = Table(ent, colWidths=[210])
    te.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    meio = 14
    lado = Table([[_titulo_quadro("Totais", 245), "", _titulo_quadro("Entrega › Transporte", 230)],
                  [tt, "", te]],
                 colWidths=[LARGURA - 230 - meio, meio, 230])
    lado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [lado]
    for nota in f.get("notas_totais", ()):
        out += [Spacer(1, 6), _p(nota, _NOTA)]
    return out


def _titulo_quadro(texto, largura=None):
    t = Table([[_p(texto, ParagraphStyle("tq", parent=_TXT_B, fontSize=10.5, textColor=COR_ESCURA))]],
              colWidths=[largura or LARGURA])
    t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, 0), 3, COR), ("BACKGROUND", (0, 0), (-1, -1), COR_CLARA),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def gerar_pdf(titulo_versao, cabecalho_linhas, blocos, notas=(), senha=None, focco=None, blocos_finais=()):
    """
    cabecalho_linhas: [(rótulo, valor texto)]
    blocos: [(título, [(rótulo, valor Decimal ou texto ou None)])]  — primeira página
    focco: quadros para lançar no Focco (segunda página), ver _pagina_focco
    blocos_finais: blocos depois dos quadros do Focco (detalhes do Adm)
    """
    buffer = io.BytesIO()
    enc = None
    if senha:
        enc = StandardEncryption(userPassword=senha, ownerPassword=senha,
                                 canPrint=1, canModify=0, canCopy=0, canAnnotate=0)
    adm = "Adm Comercial" in titulo_versao
    gerado = agora()

    def moldura(c, doc):
        c.saveState()
        w, h = A4
        c.drawImage(LOGO, 34, h - 72, width=48, height=48, preserveAspectRatio=True, mask="auto")
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(92, h - 46, "Calculadora Comercial")
        c.setFont("Helvetica", 9)
        c.setFillColor(CINZA)
        c.drawString(92, h - 60, titulo_versao)
        if adm:
            c.setFillColor(COR_ESCURA)
            c.roundRect(w - 140, h - 56, 100, 18, 4, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(w - 90, h - 50, "USO INTERNO")
        c.setStrokeColor(COR)
        c.setLineWidth(2)
        c.line(40, h - 80, w - 40, h - 80)
        c.setStrokeColor(LINHA)
        c.setLineWidth(0.6)
        c.line(40, 42, w - 40, 42)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(CINZA)
        c.drawString(40, 30, f"Simulação gerada em {gerado} · {CONTATO}")
        c.drawRightString(w - 40, 30, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=96,
                            bottomMargin=56, encrypt=enc, title="Calculadora Comercial - Minimal Design",
                            author="Minimal Design")
    hist = _dados_orcamento(cabecalho_linhas)
    for titulo, linhas in blocos:
        hist.append(_quadro(titulo, linhas))
    if focco:
        hist += _pagina_focco(focco)
    if blocos_finais:
        hist += [PageBreak(), _p("Detalhes para o ADM Comercial", _SEC)]
        for titulo, linhas in blocos_finais:
            hist.append(_quadro(titulo, linhas))
    for t in notas:
        hist.append(_p(t, _NOTA))
    doc.build(hist, onFirstPage=moldura, onLaterPages=moldura)
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
