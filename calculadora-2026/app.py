# app.py
# Calculadora Comercial Minimal — NF-e, versão 2026 (lucro real).
#
#   calculo.py   -> regras de cálculo (sem percentuais fixos)
#   config.json  -> percentuais e tabelas (editáveis pela tela do Adm)
#   consulta.py  -> consulta do cliente pelo CNPJ
#   servicos.py  -> GitHub, planilha do SharePoint e e-mail ao ADM Comercial
# Senhas e chaves ficam nos Secrets do Streamlit Cloud (ver LEIA-ME.md).

import io
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

import consulta
import servicos
from calculo import (CONSUMIDOR_FINAL, CONTRIBUINTE, ITENS, NAO_CONTRIBUINTE, PASTA,
                     PEDIDO, REPRESENTANTES, calcular, carregar_config, salvar_config)

LOGO = os.path.join(PASTA, "logo_minimal.png")
FUSO = ZoneInfo("America/Sao_Paulo")

st.set_page_config(page_title="Calculadora Comercial 2026 - Minimal", layout="wide")

st.markdown("""
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
""", unsafe_allow_html=True)

if "cfg" not in st.session_state:
    st.session_state.cfg = carregar_config()
cfg = st.session_state.cfg
SENHA_ADM = servicos.senha_adm(st)
ss = st.session_state


def formatar(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md(texto):
    """Escapa o "$" de "R$" para o Streamlit não tratar o trecho como fórmula."""
    return texto.replace("$", "\\$")


def fmt_pct(fracao):
    return f"{fracao * 100:.2f}%".replace(".", ",")


def agora():
    return datetime.now(FUSO).strftime("%d/%m/%Y %H:%M")


# ==================================================================
# Parâmetros (Adm)
# ==================================================================
with st.sidebar:
    st.header("⚙️ Parâmetros (Adm)")
    if not SENHA_ADM:
        st.info("Cadastre ADM_SENHA nos Secrets do app para liberar esta área.")
    senha = st.text_input("Senha", type="password", disabled=not SENHA_ADM)
    if SENHA_ADM and senha == SENHA_ADM:
        novo = json.loads(json.dumps(cfg))

        st.subheader("Impostos")
        imp = novo["impostos"]
        imp["ipi"] = st.number_input("IPI (%)", value=float(imp["ipi"]), step=0.05)
        imp["pis_cofins"] = st.number_input("PIS/COFINS (%)", value=float(imp["pis_cofins"]), step=0.05)
        imp["credito_pis_cofins_frete"] = st.checkbox(
            "Crédito de PIS/COFINS sobre o frete", value=imp["credito_pis_cofins_frete"])
        imp["credito_pis_cofins_montagem"] = st.checkbox(
            "Crédito de PIS/COFINS sobre a montagem", value=imp["credito_pis_cofins_montagem"])
        imp["pis_cofins_sobre_difal_embutido"] = st.checkbox(
            "PIS/COFINS sobre o valor embutido (DIFAL/FCP e ICMS s/ IPI)",
            value=imp.get("pis_cofins_sobre_difal_embutido", True))
        imp["icms_sobre_ipi_e_difal_sem_ie"] = st.checkbox(
            "Não contribuinte: ICMS sobre o IPI e o DIFAL/FCP embutido",
            value=imp.get("icms_sobre_ipi_e_difal_sem_ie", True))
        imp["icms_sobre_ipi_ie_uso_consumo"] = st.checkbox(
            "Contribuinte consumidor final: ICMS sobre o IPI",
            value=imp.get("icms_sobre_ipi_ie_uso_consumo", False))

        st.subheader("Lucro e IR")
        res = novo["resultado"]
        res["margem_frete_montagem"] = st.number_input(
            "Margem líquida sobre frete e montagem (%)",
            value=float(res["margem_frete_montagem"]), step=0.5,
            help="0 = repassa só o custo e os impostos.")
        res["empresa_tem_lucro"] = st.checkbox(
            "Empresa com lucro no exercício (aplicar IRPJ/CSLL sobre a margem)",
            value=res["empresa_tem_lucro"])
        res["aplicar_adicional_ir"] = st.checkbox(
            "Aplicar adicional de IR (10%)", value=res["aplicar_adicional_ir"])
        c1, c2, c3 = st.columns(3)
        res["irpj"] = c1.number_input("IRPJ (%)", value=float(res["irpj"]))
        res["adicional_ir"] = c2.number_input("Adicional (%)", value=float(res["adicional_ir"]))
        res["csll"] = c3.number_input("CSLL (%)", value=float(res["csll"]))

        st.subheader("Frete")
        fr = novo["frete"]
        fr["pedido_minimo"] = st.number_input("Pedido mínimo Salis (R$)", value=float(fr["pedido_minimo"]))
        fr["sp_capital_comercial"] = st.number_input("SP Capital, horário comercial (%)", value=float(fr["sp_capital_comercial"]))
        fr["sp_capital_fora_horario"] = st.number_input("SP Capital, fora do horário (%)", value=float(fr["sp_capital_fora_horario"]))
        fr["sp_interior"] = st.number_input("SP Interior (%)", value=float(fr["sp_interior"]))
        fr["sp_capital_sem_cobranca"] = st.checkbox(
            "Não cobrar frete e montagem em SP Capital", value=fr["sp_capital_sem_cobranca"])

        st.subheader("Montagem")
        mo = novo["montagem"]
        mo["percentual"] = st.number_input("Montagem (% dos produtos)", value=float(mo["percentual"]))
        mo["valor_km"] = st.number_input("Valor por km (R$)", value=float(mo["valor_km"]))

        st.subheader("Tabela por estado (%)")
        df = pd.DataFrame.from_dict(novo["estados"], orient="index")
        df.index.name = "UF"
        df = st.data_editor(df, column_config={
            "icms_interestadual": "ICMS inter.", "difal": "DIFAL", "fcp": "FCP",
            "salis_capital": "Salis Capital", "salis_interior": "Salis Interior",
        })
        novo["estados"] = {
            uf_nome: {k: (None if pd.isna(v) else float(v)) for k, v in linha.items()}
            for uf_nome, linha in df.iterrows()
        }

        if st.button("Salvar parâmetros", type="primary"):
            ss.cfg = novo
            try:
                salvar_config(novo)
            except OSError:
                pass
            ok, msg = servicos.salvar_config_github(st, novo)
            if ok:
                st.success(msg)
            else:
                st.warning(msg + " Os parâmetros valem até o app reiniciar; baixe o "
                           "config.json abaixo e envie ao GitHub para torná-los permanentes.")
        st.download_button("Baixar config.json (backup)",
                           data=json.dumps(novo, ensure_ascii=False, indent=2),
                           file_name="config.json", mime="application/json")
    elif senha:
        st.error("Senha incorreta.")


# ==================================================================
# Consulta pelo CNPJ
# ==================================================================
def consultar_cnpj():
    dados = consulta.consultar(ss.get("cnpj", ""), servicos.token_cnpja(st))
    dados["cnpj"] = consulta.so_digitos(ss.get("cnpj", ""))
    ss.consulta = dados
    if not dados.get("ok"):
        return
    if dados.get("estado") in cfg["estados"]:
        ss.estado = dados["estado"]
    if dados.get("cidade"):
        ss.cidade = dados["cidade"]
    if dados.get("contribuinte_ie") is not None:
        ss.contribuinte = CONTRIBUINTE if dados["contribuinte_ie"] else NAO_CONTRIBUINTE
    if not ss.get("cliente") and dados.get("razao_social"):
        ss.cliente = dados["razao_social"]


st.image(LOGO, width=140)
st.title("Calculadora Comercial - Minimal Design")
st.caption("Versão 2026 · lucro real")

# ---------------- 1. Cliente ----------------
with st.container(border=True):
    st.subheader("1. Cliente")
    c1, c2 = st.columns(2)
    data = c1.date_input("Data", format="DD/MM/YYYY", key="data")
    c2.text_input("Vendedor", key="vendedor")
    c1.text_input("Cliente", key="cliente")
    c2.text_input("Orçamento", key="orcamento")

    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    c1.text_input("CNPJ do cliente", key="cnpj", placeholder="00.000.000/0000-00",
                  help="A consulta preenche UF, cidade e, quando disponível, se o cliente é contribuinte.")
    c2.button("🔎 Consultar CNPJ", on_click=consultar_cnpj, width="stretch")

    cons = ss.get("consulta")
    if cons and cons.get("cnpj") != consulta.so_digitos(ss.get("cnpj", "")):
        cons = None
    if cons:
        if not cons.get("ok"):
            st.warning(cons.get("erro", "Consulta indisponível.") + " Preencha os campos abaixo.")
        else:
            linhas = [
                f"**{cons['razao_social']}**",
                f"{cons['municipio']}/{cons['uf']} · situação: {cons['situacao'] or '—'} · "
                f"Simples Nacional: {cons['simples'] or '—'}",
            ]
            if cons.get("ie_texto"):
                linhas.append(f"Inscrição estadual: {cons['ie_texto']}")
            linhas.append(f"Consulta em {cons['data_hora']} · {cons['fonte']}")
            st.success("  \n".join(linhas))
            if cons.get("situacao") and "ativa" not in cons["situacao"].lower():
                st.warning(f"Situação cadastral: {cons['situacao']}. Confirme com o Adm antes de seguir.")
            if cons.get("suframa"):
                st.warning("Cliente com inscrição na SUFRAMA (Zona Franca / Área de Livre Comércio). "
                           "Os benefícios de ICMS e IPI não são tratados pela calculadora: "
                           "consulte o Adm Comercial antes de enviar a proposta.")
            if cons.get("contribuinte_ie") is None:
                st.info(f"A consulta gratuita não informa a inscrição estadual. Confira se o cliente é "
                        f"contribuinte no [Cadastro de Contribuintes (CCC)]({consulta.LINK_CCC}) "
                        f"ou no [Sintegra]({consulta.LINK_SINTEGRA}) e marque abaixo. "
                        f"CNPJ: {consulta.formatar_cnpj(cons['cnpj'])}")

# ---------------- 2. Destino e perfil fiscal ----------------
with st.container(border=True):
    st.subheader("2. Destino e perfil fiscal")
    c1, c2 = st.columns(2)
    c1.selectbox("Estado de destino (UF) *", list(cfg["estados"].keys()), index=None,
                 key="estado", placeholder="Selecione")
    c2.radio("Cidade de destino *", ["Capital", "Interior"], index=None, key="cidade", horizontal=True)
    st.radio("O cliente é: *", [CONTRIBUINTE, NAO_CONTRIBUINTE], index=None, key="contribuinte",
             horizontal=True,
             help="Não contribuinte inclui clientes que têm IE mas não são contribuintes do ICMS.")
    if ss.get("contribuinte") == CONTRIBUINTE:
        st.radio("Finalidade da compra: *", [REPRESENTANTES, CONSUMIDOR_FINAL], index=None,
                 key="finalidade", horizontal=True,
                 help="Representantes: compra para revenda ou industrialização. "
                      "Consumidor final: compra para uso e consumo.")

estado = ss.get("estado")
cidade = ss.get("cidade")
sp_capital = estado == "São Paulo" and cidade == "Capital"
sem_cobranca = sp_capital and cfg["frete"].get("sp_capital_sem_cobranca", True)

# ---------------- 3. Produtos, frete e montagem ----------------
with st.container(border=True):
    st.subheader("3. Produtos, frete e montagem")
    st.number_input("Valor dos produtos, já com desconto (com ICMS embutido) *",
                    min_value=0.0, value=None, format="%.2f", key="valor_produtos")

    OPCOES = ["Calcular", "Informar valor negociado", "Não contratar"]
    c1, c2 = st.columns(2)
    with c1:
        st.radio("Frete *", OPCOES, index=None, key="frete_opcao")
        if ss.get("frete_opcao") == "Informar valor negociado":
            st.number_input("Valor negociado do frete *", min_value=0.0, value=None,
                            format="%.2f", key="frete_negociado")
        if ss.get("frete_opcao") == "Calcular" and sp_capital:
            st.radio("Horário da entrega *", ["Comercial", "Fora do comercial"], index=None,
                     key="horario", horizontal=True,
                     help="SP Capital: a Salis cobra 3% no horário comercial e 4% fora dele.")
        if ss.get("frete_opcao") != "Não contratar" and not sem_cobranca:
            st.radio("Frete aplicado: *", [PEDIDO, ITENS], index=None, key="frete_aplicacao",
                     help="Ao pedido: campo de frete da NF. "
                          "Aos itens: somado ao valor dos produtos. Use a mesma escolha do pedido no ERP.")
    with c2:
        st.radio("Montagem *", OPCOES, index=None, key="montagem_opcao")
        if ss.get("montagem_opcao") == "Informar valor negociado":
            st.number_input("Valor negociado da montagem *", min_value=0.0, value=None,
                            format="%.2f", key="montagem_negociada")
        if ss.get("montagem_opcao") == "Calcular" and estado and cidade and not sp_capital:
            st.number_input("Distância ida e volta (km) de Barueri-SP *", min_value=0.0,
                            value=None, format="%.0f", key="km_ida_volta")
        if ss.get("montagem_opcao") != "Não contratar" and not sem_cobranca:
            st.radio("Montagem aplicada: *", [PEDIDO, ITENS], index=None, key="montagem_aplicacao",
                     help="Ao pedido: despesas acessórias da NF. "
                          "Aos itens: somado ao valor dos produtos. Use a mesma escolha do pedido no ERP.")

    if ss.get("contribuinte") == NAO_CONTRIBUINTE:
        st.caption("DIFAL/FCP: sempre aplicado aos itens.")
    elif ss.get("finalidade") == CONSUMIDOR_FINAL:
        st.caption("ICMS sobre o IPI (consumidor final), quando aplicável: sempre aos itens.")
    if sem_cobranca:
        st.caption("SP Capital: frete e montagem não são cobrados do cliente.")

    st.number_input("% de comissão (opcional)", min_value=0.0, max_value=100.0, value=None,
                    format="%.2f", key="comissao_pct",
                    help="Percentual da faixa indicada pelo sistema após os descontos.")


# ==================================================================
# Validação e cálculo
# ==================================================================
def faltando():
    f = []
    if not ss.get("estado"):
        f.append("Estado de destino")
    if not ss.get("cidade"):
        f.append("Cidade de destino")
    if not ss.get("contribuinte"):
        f.append("Contribuinte ou não contribuinte")
    if ss.get("contribuinte") == CONTRIBUINTE and not ss.get("finalidade"):
        f.append("Finalidade da compra")
    if not ss.get("valor_produtos"):
        f.append("Valor dos produtos")
    for serv, rot in (("frete", "Frete"), ("montagem", "Montagem")):
        op = ss.get(f"{serv}_opcao")
        if not op:
            f.append(rot)
            continue
        if op == "Informar valor negociado":
            neg = "frete_negociado" if serv == "frete" else "montagem_negociada"
            if not ss.get(neg):
                f.append(f"Valor negociado da {rot.lower()}" if serv == "montagem" else "Valor negociado do frete")
        if op != "Não contratar" and not sem_cobranca and not ss.get(f"{serv}_aplicacao"):
            f.append(f"{rot}: aplicado ao pedido ou aos itens")
    if ss.get("frete_opcao") == "Calcular" and sp_capital and not ss.get("horario"):
        f.append("Horário da entrega")
    if ss.get("montagem_opcao") == "Calcular" and not sp_capital and not ss.get("km_ida_volta"):
        f.append("Distância ida e volta (km)")
    return f


def entradas_atuais():
    contrib = ss.get("contribuinte")
    return dict(
        valor_produtos=ss.get("valor_produtos") or 0, estado=ss.get("estado"), cidade=ss.get("cidade"),
        horario=ss.get("horario") if (sp_capital and ss.get("frete_opcao") == "Calcular") else None,
        contribuinte=contrib,
        finalidade=ss.get("finalidade") if contrib == CONTRIBUINTE else None,
        frete_opcao=ss.get("frete_opcao"), montagem_opcao=ss.get("montagem_opcao"),
        frete_negociado=ss.get("frete_negociado") or 0,
        montagem_negociada=ss.get("montagem_negociada") or 0,
        km_ida_volta=(ss.get("km_ida_volta") or 0) if not sp_capital else 0,
        frete_aplicacao=ss.get("frete_aplicacao") if not sem_cobranca else PEDIDO,
        montagem_aplicacao=ss.get("montagem_aplicacao") if not sem_cobranca else PEDIDO,
        comissao_pct=ss.get("comissao_pct") or 0,
    )


def origem_dados(e):
    cons = ss.get("consulta")
    if not cons or not cons.get("ok") or cons.get("cnpj") != consulta.so_digitos(ss.get("cnpj", "")):
        return "Manual", "Manual", "", ""
    local = ("Consulta" if (cons.get("estado") == e["estado"] and cons.get("cidade") == e["cidade"])
             else "Consulta alterada pelo vendedor")
    if cons.get("contribuinte_ie") is None:
        contrib = "Manual"
    else:
        esperado = CONTRIBUINTE if cons["contribuinte_ie"] else NAO_CONTRIBUINTE
        contrib = "Consulta" if esperado == e["contribuinte"] else "Consulta alterada pelo vendedor"
    return local, contrib, cons["data_hora"], cons["fonte"]


if st.button("Calcular", type="primary"):
    falta = faltando()
    if falta:
        st.error("Preencha os campos obrigatórios: " + ", ".join(falta) + ".")
        ss.pop("sim", None)
    else:
        e = entradas_atuais()
        r = calcular(e, cfg)
        cons = ss.get("consulta") if (ss.get("consulta") or {}).get("ok") else {}
        meta = dict(data=ss.get("data"), vendedor=ss.get("vendedor", ""), cliente=ss.get("cliente", ""),
                    orcamento=ss.get("orcamento", ""), cnpj=consulta.formatar_cnpj(ss.get("cnpj", "")),
                    razao_social=cons.get("razao_social", "") if cons.get("cnpj") == consulta.so_digitos(ss.get("cnpj", "")) else "",
                    simples=cons.get("simples", "") if cons else "",
                    suframa=("Sim" if cons.get("suframa") else ("Não" if cons.get("suframa") is False else "")) if cons else "")
        ss.sim = dict(entrada=e, meta=meta, r=r, origem=origem_dados(e), enviado=None)


# ==================================================================
# Resultado
# ==================================================================
if "sim" in ss:
    sim = ss.sim
    e, meta, r = sim["entrada"], sim["meta"], sim["r"]
    desatualizado = (e != entradas_atuais() or meta["vendedor"] != ss.get("vendedor", "")
                     or meta["cliente"] != ss.get("cliente", "") or meta["orcamento"] != ss.get("orcamento", ""))
    sem_ie = e["contribuinte"] == NAO_CONTRIBUINTE

    rot_emb = "DIFAL/FCP embutido" if sem_ie else "ICMS sobre IPI embutido (consumidor final)"
    linhas_nf = [("Valor dos itens na NF (vProd)", r["valor_itens_nf"]),
                 ("  · produtos", r["valor_produtos"])]
    if e["frete_aplicacao"] == ITENS and r["frete_final"]:
        linhas_nf.append(("  · frete aplicado aos itens", r["frete_final"]))
    if e["montagem_aplicacao"] == ITENS and r["montagem_final"]:
        linhas_nf.append(("  · montagem aplicada aos itens", r["montagem_final"]))
    if r["difal_fcp_embutido"]:
        linhas_nf.append((f"  · {rot_emb}", r["difal_fcp_embutido"]))
    if r["frete_nf"]:
        linhas_nf.append(("Frete destacado (vFrete)", r["frete_nf"]))
    if r["despesas_acessorias_nf"]:
        linhas_nf.append(("Montagem em despesas acessórias (vOutro)", r["despesas_acessorias_nf"]))
    linhas_nf += [("Valor do IPI", r["ipi"]), ("Valor total da NF", r["total_nf"])]

    with st.container(border=True):
        st.subheader("Resumo da Nota Fiscal")
        if desatualizado:
            st.warning("Os dados do formulário mudaram depois deste cálculo. Clique em **Calcular** de novo.")
        if r["aviso"]:
            st.warning(r["aviso"])
        for titulo, valor in linhas_nf:
            st.write(md(f"{titulo}: **{formatar(valor)}**" if titulo == "Valor total da NF"
                        else f"{titulo}: {formatar(valor)}"))
        if sem_ie:
            st.write(md(f"Guia DIFAL: {formatar(r['difal'])} · Guia FCP: {formatar(r['fcp'])}"))

        if r["comissao_pct"]:
            st.write(md(f"Comissão sobre os produtos: {formatar(r['comissao_correta'])}"))
            if r["comissao_diferenca"] > 0.005:
                st.warning(md(
                    f"O sistema calculará a comissão sobre {formatar(r['valor_itens_nf'])} "
                    f"({formatar(r['comissao_sistema'])}). Diferença a ajustar: "
                    f"{formatar(r['comissao_diferenca'])}."))
        if r["sp_capital_absorvido"]:
            st.info(md(f"SP Capital: frete e montagem não são cobrados do cliente. "
                       f"Custo absorvido pela empresa: {formatar(-r['resultado_estimado'])}."))
        elif r["resultado_estimado"] < -1:
            st.error(md(f"Atenção: frete e montagem geram resultado negativo de "
                        f"{formatar(r['resultado_estimado'])}."))

    # ---------------- PDFs ----------------
    def gerar_pdf(admin=False):
        buffer = io.BytesIO()
        if admin and SENHA_ADM:
            enc = StandardEncryption(userPassword=SENHA_ADM, ownerPassword=SENHA_ADM,
                                     canPrint=1, canModify=0, canCopy=0, canAnnotate=0)
            c = canvas.Canvas(buffer, pagesize=A4, encrypt=enc)
        else:
            c = canvas.Canvas(buffer, pagesize=A4)
        azul = (0.333, 0.525, 0.6)
        c.drawImage(LOGO, 40, 805, width=70, preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(*azul)
        c.drawString(150, 830, "Calculadora Comercial - Minimal Design")
        c.setFont("Helvetica", 9)
        c.drawString(150, 816, "Versão 2026" + (" · Adm Comercial" if admin else ""))

        y = 795
        cab = [("Data:", meta["data"].strftime("%d/%m/%Y") if meta["data"] else ""),
               ("Vendedor:", meta["vendedor"]), ("Cliente:", meta["cliente"]),
               ("CNPJ:", meta["cnpj"]), ("Orçamento:", meta["orcamento"]),
               ("Destino:", f"{e['estado']} · {e['cidade']}"),
               ("Perfil fiscal:", e["contribuinte"] + (f" · {e['finalidade']}" if e["finalidade"] else "")),
               ("Frete:", f"{e['frete_opcao']} · {e['frete_aplicacao']}"),
               ("Montagem:", f"{e['montagem_opcao']} · {e['montagem_aplicacao']}")]
        if e["km_ida_volta"]:
            cab.append(("Distância:", f"{e['km_ida_volta']:.0f} km"))
        if e["horario"]:
            cab.append(("Horário:", e["horario"]))
        for titulo, valor in cab:
            y -= 14
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*azul)
            c.drawString(40, y, titulo)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)
            c.drawString(140, y, str(valor))

        def bloco(titulo, linhas):
            nonlocal y
            y -= 22
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*azul)
            c.drawString(40, y, titulo)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)
            for t, v in linhas:
                y -= 14
                c.drawString(40, y, f"{t.strip()}: {formatar(v)}")

        bloco("Resumo da Nota Fiscal (NFe)", linhas_nf)
        if sem_ie:
            bloco("Guias", [("Guia DIFAL", r["difal"]), ("Guia FCP", r["fcp"])])
        if admin:
            bloco("Custos e conferência", [
                ("A pagar à transportadora", r["frete_custo"]),
                ("A pagar à montadora", r["montagem_custo"]),
                ("  · parte percentual", r["montagem_pct"]),
                ("  · deslocamento", r["montagem_km"]),
                ("Resultado frete/montagem (antes do IR)", r["resultado_estimado"]),
            ])
            if r["difal_fcp_embutido"]:
                bloco("Valor embutido", [
                    ("Embutido nos itens", r["difal_fcp_embutido"]),
                    ("ICMS sobre IPI e embutido", r["icms_extra"]),
                    ("PIS/COFINS sobre o embutido", r["pis_cofins_extra"]),
                    ("Sobra do embutido (deve ser zero)", r["sobra_difal"]),
                ])
            if r["comissao_pct"]:
                bloco(f"Comissão ({fmt_pct(r['comissao_pct'])})", [
                    ("Correta, sobre os produtos", r["comissao_correta"]),
                    ("Calculada pelo sistema sobre o vProd", r["comissao_sistema"]),
                    ("Diferença a ajustar", r["comissao_diferenca"]),
                ])
            loc, contrib, dh, fonte = sim["origem"]
            y -= 22
            c.setFont("Helvetica", 9)
            c.drawString(40, y, f"Origem UF/cidade: {loc} · Origem contribuinte: {contrib}"
                         + (f" · Consulta {dh} ({fonte})" if dh else ""))
            y -= 12
            c.drawString(40, y, f"Multiplicador: {r['multiplicador']:.4f} (carga {fmt_pct(r['carga'])}) · "
                         f"cálculo resolvido em {r['iteracoes']} rodada(s)")
        c.save()
        return buffer.getvalue()

    nome_cliente = (meta["cliente"] or "Cliente").strip().replace(" ", "_")
    nome_orc = (meta["orcamento"] or "Orcamento").strip().replace(" ", "_")
    arq = f"Simulacao_{nome_cliente}_{nome_orc}.pdf"

    def n(v):
        return round(float(v), 2)

    def registro(data_envio):
        loc, contrib, dh, fonte = sim["origem"]
        return [
            data_envio, meta["data"].strftime("%d/%m/%Y") if meta["data"] else "",
            meta["vendedor"], meta["cliente"], meta["cnpj"], meta["razao_social"],
            meta["orcamento"], "", loc, contrib, dh, fonte, meta["simples"], meta["suframa"],
            e["estado"], e["cidade"], e["contribuinte"], e["finalidade"] or "-",
            e["frete_aplicacao"] if e["frete_opcao"] != "Não contratar" else "-",
            e["montagem_aplicacao"] if e["montagem_opcao"] != "Não contratar" else "-",
            n(r["valor_produtos"]), n(r["frete_custo"]), n(r["montagem_custo"]),
            n(r["frete_final"]), n(r["montagem_final"]), n(r["difal_fcp_embutido"]),
            n(r["difal"]), n(r["fcp"]), n(r["ipi"]), n(r["valor_itens_nf"]), n(r["total_nf"]),
            n(r["resultado_estimado"]), n(r["comissao_pct"] * 100), n(r["comissao_correta"]),
            n(r["comissao_sistema"]), n(r["comissao_diferenca"]),
        ]

    if not desatualizado:
        st.download_button("📄 Baixar PDF do Resultado", data=gerar_pdf(False),
                           file_name=arq, mime="application/pdf")

        with st.container(border=True):
            st.subheader("Enviar ao ADM Comercial")
            if sim["enviado"]:
                st.success(f"✅ Simulação enviada e salva em {sim['enviado']}.")
            else:
                falta_envio = [rot for chave, rot in (("vendedor", "Vendedor"), ("cliente", "Cliente"),
                                                      ("orcamento", "Orçamento")) if not meta[chave]]
                if falta_envio:
                    st.caption("Para enviar, preencha: " + ", ".join(falta_envio) + " e calcule de novo.")
                if st.button("📨 Enviar simulação ao ADM Comercial e salvar",
                             disabled=bool(falta_envio)):
                    quando = agora()
                    linha = registro(quando)
                    pdf_adm = gerar_pdf(True)
                    assunto = f"Simulação {meta['orcamento']} · {meta['cliente']} · {meta['vendedor']}"
                    corpo = (f"<p>Simulação enviada pela Calculadora Comercial 2026 em {quando}.</p>"
                             f"<table cellpadding='4'>"
                             + "".join(f"<tr><td>{t.strip()}</td><td><b>{formatar(v)}</b></td></tr>"
                                       for t, v in linhas_nf)
                             + f"<tr><td>A pagar à transportadora</td><td>{formatar(r['frete_custo'])}</td></tr>"
                             f"<tr><td>A pagar à montadora</td><td>{formatar(r['montagem_custo'])}</td></tr>"
                             f"</table><p>O PDF do Adm Comercial é protegido por senha.</p>")
                    anexos = [(f"ADM_{arq}", pdf_adm), (arq, gerar_pdf(False))]
                    ok_p, msg_p, ok_e, msg_e = servicos.enviar_e_salvar(st, linha, assunto, corpo, anexos)
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
                                               data=servicos.linha_csv(t["linha"]),
                                               file_name=f"registro_{nome_orc}.csv", mime="text/csv")
                        if not t["ok_e"]:
                            c2.download_button("Baixar PDF do Adm Comercial", data=t["pdf_adm"],
                                               file_name=f"ADM_{arq}", mime="application/pdf")
