# calculadora-minimal-nfe.py
# Calculadora Comercial Minimal — NF-e, regras de 2026 (lucro real).
#
# Arquivos:
#   calculo.py   -> regras de cálculo (não tem percentuais fixos)
#   config.json  -> todos os percentuais e tabelas (editáveis pela tela do Adm)
#   servicos.py  -> gravação no GitHub e registro na planilha do SharePoint
# Senhas e chaves ficam nos Secrets do Streamlit Cloud (ver LEIA-ME.md).

import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

import servicos
from calculo import (FINALIDADE_REVENDA, FINALIDADE_USO, MODO_DESTACADO,
                     MODO_DILUIDO, calcular, carregar_config, salvar_config)

st.set_page_config(page_title="Calculadora Comercial - Minimal", layout="wide")

st.markdown("""
    <style>
    body { background-color: #f6f8fa; }
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4 { color: #000000; font-family: 'Helvetica Neue', sans-serif; }
    [data-baseweb="radio"] > div {
        background-color: #ffffff; border-radius: 6px; padding: 0.25rem 0.5rem;
    }
    [data-baseweb="radio"] label span { color: #558699; font-weight: 500; }
    [data-baseweb="radio"] input:checked + div {
        background-color: #558699 !important; color: #ffffff !important;
    }
    .stNumberInput input[type="number"] {
        border: 1px solid #558699 !important; border-radius: 6px !important;
        height: 2.5rem !important; padding: 0 0.75rem !important;
        line-height: 1.2rem !important; background-color: #f8fafc;
    }
    .stSelectbox div[data-baseweb="select"] > div {
        border: 1px solid #558699 !important; border-radius: 6px !important;
        height: 2.5rem !important; padding: 0 0.75rem !important;
        line-height: 1.2rem !important; display: flex; align-items: center;
        background-color: #f8fafc;
    }
    </style>
""", unsafe_allow_html=True)

if "cfg" not in st.session_state:
    st.session_state.cfg = carregar_config()
cfg = st.session_state.cfg
SENHA_ADM = servicos.senha_adm(st)


def formatar(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(fracao):
    return f"{fracao * 100:.2f}%".replace(".", ",")


# ==================================================================
# Parâmetros (Adm)
# ==================================================================
with st.sidebar:
    st.header("⚙️ Parâmetros (Adm)")
    if not SENHA_ADM:
        st.info("Cadastre ADM_SENHA nos Secrets do app para liberar esta área e o PDF do Adm.")
    senha = st.text_input("Senha", type="password", disabled=not SENHA_ADM)
    if SENHA_ADM and senha == SENHA_ADM:
        novo = json.loads(json.dumps(cfg))  # cópia

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
            "Cliente sem IE: ICMS sobre o IPI e o DIFAL/FCP embutido",
            value=imp.get("icms_sobre_ipi_e_difal_sem_ie", True))
        imp["icms_sobre_ipi_ie_uso_consumo"] = st.checkbox(
            "Cliente com IE para uso e consumo: ICMS sobre o IPI",
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
            "icms_interestadual": "ICMS inter.",
            "difal": "DIFAL",
            "fcp": "FCP",
            "salis_capital": "Salis Capital",
            "salis_interior": "Salis Interior",
        })
        novo["estados"] = {
            uf_nome: {k: (None if pd.isna(v) else float(v)) for k, v in linha.items()}
            for uf_nome, linha in df.iterrows()
        }

        if st.button("Salvar parâmetros", type="primary"):
            st.session_state.cfg = novo
            try:
                salvar_config(novo)
            except OSError:
                pass
            ok, msg = servicos.salvar_config_github(st, novo)
            if ok:
                st.success(msg)
            else:
                st.warning(msg + " Os parâmetros valem até o app reiniciar; "
                           "baixe o config.json abaixo e envie ao GitHub para torná-los permanentes.")
        st.download_button("Baixar config.json (backup)",
                           data=json.dumps(novo, ensure_ascii=False, indent=2),
                           file_name="config.json", mime="application/json")
    elif senha:
        st.error("Senha incorreta.")

# ==================================================================
# Formulário
# ==================================================================
st.image("logo_minimal.png", width=140)
st.title("Calculadora Comercial - Minimal Design")

with st.form("formulario"):
    c1, c2 = st.columns(2)
    data = c1.date_input("Data", format="DD/MM/YYYY")
    vendedor = c2.text_input("Vendedor")
    cliente = c1.text_input("Cliente")
    orcamento = c2.text_input("Orçamento")
    valor_produtos = st.number_input(
        "Valor dos produtos, já com desconto (com ICMS embutido)", min_value=0.0, format="%.2f")
    estado = st.selectbox("Estado de destino (UF)", list(cfg["estados"].keys()))
    cidade = st.selectbox("Cidade de destino", ["Capital", "Interior"])
    horario = st.radio("Horário da entrega", ["Comercial", "Fora do comercial"])
    tem_ie = st.radio("Cliente possui inscrição estadual?", ["Sim", "Não"])
    finalidade = st.radio(
        "Se possui IE, o cliente compra para:", [FINALIDADE_REVENDA, FINALIDADE_USO],
        help="Use o mesmo critério do pedido no sistema (consumidor final). Ignorado se o cliente não tem IE.")
    modo_acrescimo = st.radio(
        "Forma de aplicação do acréscimo *", [MODO_DESTACADO, MODO_DILUIDO], index=None,
        help="Deve ser a mesma opção escolhida no pedido do sistema.")
    frete_opcao = st.radio("Frete", ["Calcular", "Informar valor negociado", "Não contratar"])
    montagem_opcao = st.radio("Montagem", ["Calcular", "Informar valor negociado", "Não contratar"])
    frete_negociado = st.number_input("Valor negociado do frete (se aplicável)", min_value=0.0, format="%.2f")
    montagem_negociada = st.number_input("Valor negociado da montagem (se aplicável)", min_value=0.0, format="%.2f")
    km_ida_volta = st.number_input(
        "Distância ida e volta (km) de Barueri-SP (montagem calculada fora de SP Capital)",
        min_value=0.0, format="%.2f")
    comissao_pct = st.number_input(
        "% de comissão (opcional)", min_value=0.0, max_value=100.0, format="%.2f",
        help="Percentual da faixa indicada pelo sistema após os descontos.")
    submit = st.form_submit_button("Calcular")

if submit:
    if modo_acrescimo is None:
        st.error("Escolha a forma de aplicação do acréscimo antes de calcular.")
        st.stop()

    entrada = dict(
        valor_produtos=valor_produtos, estado=estado, cidade=cidade, horario=horario,
        tem_ie=tem_ie, finalidade=finalidade if tem_ie == "Sim" else None,
        modo_acrescimo=modo_acrescimo, frete_opcao=frete_opcao, montagem_opcao=montagem_opcao,
        frete_negociado=frete_negociado, montagem_negociada=montagem_negociada,
        km_ida_volta=km_ida_volta, comissao_pct=comissao_pct,
    )
    r = calcular(entrada, cfg)
    meta = dict(data=data, vendedor=vendedor, cliente=cliente, orcamento=orcamento)

    def n(v):
        return round(float(v), 2)

    registro = [
        datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
        data.strftime("%d/%m/%Y"), vendedor, cliente, orcamento, "",
        estado, cidade, tem_ie, entrada["finalidade"] or "-", modo_acrescimo,
        n(r["valor_produtos"]), n(r["frete_custo"]), n(r["montagem_custo"]),
        n(r["frete_final"]), n(r["montagem_final"]), n(r["difal_fcp_embutido"]),
        n(r["difal"]), n(r["fcp"]), n(r["ipi"]), n(r["valor_itens_nf"]), n(r["total_nf"]),
        n(r["resultado_estimado"]), n(comissao_pct), n(r["comissao_correta"]),
        n(r["comissao_sistema"]), n(r["comissao_diferenca"]),
    ]
    ok, msg = servicos.registrar_sharepoint(st, registro)
    st.session_state.sim = dict(entrada=entrada, meta=meta, r=r,
                                registro=registro, registro_ok=ok, registro_msg=msg)

# ==================================================================
# Resultado (fica na tela mesmo depois de baixar os PDFs)
# ==================================================================
if "sim" in st.session_state:
    sim = st.session_state.sim
    e, meta, r = sim["entrada"], sim["meta"], sim["r"]
    diluido = e["modo_acrescimo"] == MODO_DILUIDO
    sem_ie = e["tem_ie"] == "Não"

    if r["aviso"]:
        st.warning(r["aviso"])

    st.subheader("Resumo da Nota Fiscal")
    st.caption(e["modo_acrescimo"])
    rotulo_emb = "DIFAL/FCP embutido" if sem_ie else "ICMS sobre IPI embutido (uso e consumo)"
    if diluido:
        linhas_nf = [
            ("Valor dos produtos na NF (com acréscimos)", r["valor_itens_nf"]),
            ("  · produtos", r["valor_produtos"]),
            ("  · frete diluído", r["frete_final"]),
            ("  · montagem diluída", r["montagem_final"]),
        ]
        if r["difal_fcp_embutido"]:
            linhas_nf.append((f"  · {rotulo_emb} diluído", r["difal_fcp_embutido"]))
        linhas_nf += [("Valor do IPI", r["ipi"]), ("Valor da NF", r["total_nf"])]
    else:
        linhas_nf = [
            ("Valor dos produtos", r["valor_produtos"]),
            ("Valor do frete", r["frete_nf"]),
            ("Valor da montagem", r["montagem_final"]),
        ]
        if r["difal_fcp_embutido"]:
            linhas_nf.append((rotulo_emb, r["difal_fcp_embutido"]))
        linhas_nf += [
            ("Despesas acessórias", r["despesas_acessorias_nf"]),
            ("Valor do IPI", r["ipi"]),
            ("Valor da NF", r["total_nf"]),
        ]
    for titulo, valor in linhas_nf:
        st.write(f"{titulo}: {formatar(valor)}")
    if sem_ie:
        st.write(f"Guia DIFAL: {formatar(r['difal'])} · Guia FCP: {formatar(r['fcp'])}")

    if r["comissao_pct"]:
        st.write(f"Comissão sobre os produtos: {formatar(r['comissao_correta'])}")
        if diluido:
            st.warning(
                f"Acréscimo diluído: o sistema calculará a comissão sobre {formatar(r['valor_itens_nf'])} "
                f"({formatar(r['comissao_sistema'])}). Diferença a ajustar: {formatar(r['comissao_diferenca'])}.")

    if r["sp_capital_absorvido"]:
        st.info(f"SP Capital: frete e montagem não são cobrados do cliente. "
                f"Custo absorvido pela empresa: {formatar(-r['resultado_estimado'])}.")
    elif r["resultado_estimado"] < -1:
        st.error(f"Atenção: frete e montagem geram resultado negativo de {formatar(r['resultado_estimado'])}.")

    if not sim["registro_ok"]:
        st.caption(f"⚠️ {sim['registro_msg']} Baixe a linha e cole na planilha:")
        st.download_button("Baixar registro da simulação (CSV)",
                           data=servicos.linha_csv(sim["registro"]),
                           file_name=f"registro_{meta['orcamento'] or 'simulacao'}.csv",
                           mime="text/csv")
    else:
        st.caption(f"✅ {sim['registro_msg']}")

    # ---------------------------------------------------------------
    # PDFs
    # ---------------------------------------------------------------
    def gerar_pdf(admin=False):
        buffer = io.BytesIO()
        if admin:
            encrypt = StandardEncryption(userPassword=SENHA_ADM, ownerPassword=SENHA_ADM,
                                         canPrint=1, canModify=0, canCopy=0, canAnnotate=0)
            c = canvas.Canvas(buffer, pagesize=A4, encrypt=encrypt)
        else:
            c = canvas.Canvas(buffer, pagesize=A4)

        azul = (0.333, 0.525, 0.6)
        c.drawImage("logo_minimal.png", 40, 805, width=70, preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(*azul)
        c.drawString(150, 830, "Calculadora Comercial - Minimal Design")

        y = 800
        cab = [
            ("Data:", meta["data"].strftime("%d/%m/%Y")), ("Vendedor:", meta["vendedor"]),
            ("Cliente:", meta["cliente"]), ("Orçamento:", meta["orcamento"]),
            ("Estado:", e["estado"]), ("Localização:", e["cidade"]),
            ("Distância:", f"{e['km_ida_volta']:.0f} km"), ("Horário:", e["horario"]),
            ("Inscrição Estadual:", e["tem_ie"]),
        ]
        if e["finalidade"]:
            cab.append(("Finalidade:", e["finalidade"]))
        cab += [("Acréscimo:", e["modo_acrescimo"]),
                ("Valor dos Produtos:", formatar(r["valor_produtos"]))]
        for titulo, valor in cab:
            y -= 15
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*azul)
            c.drawString(40, y, titulo)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)
            c.drawString(160, y, str(valor))

        def bloco(titulo, linhas):
            nonlocal y
            y -= 25
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*azul)
            c.drawString(40, y, titulo)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)
            for t, v in linhas:
                y -= 15
                c.drawString(40, y, f"{t.strip()}: {formatar(v)}")

        bloco("Resumo da Nota Fiscal (NFe)", linhas_nf)
        if sem_ie:
            bloco("Guias", [("Guia DIFAL", r["difal"]), ("Guia FCP", r["fcp"])])

        if admin:
            bloco("Custos e conferência (Adm)", [
                ("Frete pago à transportadora", r["frete_custo"]),
                ("Montagem paga à montadora", r["montagem_custo"]),
                ("  · parte percentual", r["montagem_pct"]),
                ("  · deslocamento", r["montagem_km"]),
                ("Resultado frete/montagem (antes do IR)", r["resultado_estimado"]),
            ])
            if r["difal_fcp_embutido"]:
                bloco("Valor embutido (Adm)", [
                    ("Embutido na NF", r["difal_fcp_embutido"]),
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
            y -= 20
            c.drawString(40, y, f"Multiplicador: {r['multiplicador']:.4f} (carga {fmt_pct(r['carga'])})")
            if diluido:
                y -= 15
                c.drawString(40, y, f"Cálculo circular resolvido em {r['iteracoes']} iterações")

        c.save()
        buffer.seek(0)
        return buffer

    nome_cliente = meta["cliente"].strip().replace(" ", "_") or "Cliente"
    nome_orcamento = meta["orcamento"].strip().replace(" ", "_") or "Orcamento"
    file_name = f"Simulacao_{nome_cliente}_{nome_orcamento}.pdf"

    st.download_button("📄 Baixar PDF do Resultado", data=gerar_pdf(False),
                       file_name=file_name, mime="application/pdf")
    if SENHA_ADM:
        st.download_button("📄 Baixar PDF do Adm Comercial", data=gerar_pdf(True),
                           file_name=f"ADM_{file_name}", mime="application/pdf")
    else:
        st.caption("PDF do Adm indisponível: cadastre ADM_SENHA nos Secrets do app.")
