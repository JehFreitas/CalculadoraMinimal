# tela_cavaletti.py
# Tela da Venda Assistida Cavaletti (2026 e 2027).

import json

import pandas as pd
import streamlit as st

import cavaletti
import comum
import consulta
import servicos
from comum import fmt_pct, formatar, md

COLS = ["Descrição", "Custo unitário sem IPI (R$)", "IPI (%)", "Entrega e montagem por unidade (R$)", "Quantidade"]


def parametros(ano, pid):
    cfg = st.session_state["cfg_cavaletti"]
    with st.sidebar.expander(f"⚙️ Parâmetros · Cavaletti {ano}", expanded=False):
        novo = json.loads(json.dumps(cfg))
        p = novo[ano]
        st.subheader("Impostos da NF de serviço")
        if ano == "2026":
            p["pis_cofins"] = st.number_input("PIS/COFINS (%)", value=float(p["pis_cofins"]), step=0.05, key=f"{pid}_p_pc")
            p["pis_cofins_sobre_iss"] = st.checkbox("PIS/COFINS calculado com o ISS na base",
                                                    value=p.get("pis_cofins_sobre_iss", True), key=f"{pid}_p_pciss")
        else:
            definida = p.get("cbs") is not None
            ok = st.checkbox("Alíquota da CBS definida", value=definida, key=f"{pid}_p_cbsdef")
            p["cbs"] = st.number_input("CBS (%)", value=float(p.get("cbs") or 8.7), step=0.05,
                                       key=f"{pid}_p_cbs") if ok else None
            p["ibs"] = st.number_input("IBS (%)", value=float(p.get("ibs") or 0), step=0.05, key=f"{pid}_p_ibs")
            p["ipi_zero"] = st.checkbox("IPI zero nos produtos do fabricante", value=p.get("ipi_zero", True),
                                        key=f"{pid}_p_ipi0")
        p["iss"] = st.number_input("ISS (%)", value=float(p["iss"]), step=0.5, key=f"{pid}_p_iss")
        st.subheader("Comissão e IR")
        p["comissao_vendedor"] = st.number_input("Comissão do vendedor (% do líquido dos serviços)",
                                                 value=float(p["comissao_vendedor"]), key=f"{pid}_p_com")
        p["empresa_tem_lucro"] = st.checkbox("Empresa com lucro no exercício (IRPJ/CSLL)",
                                             value=p.get("empresa_tem_lucro", False), key=f"{pid}_p_lucro")
        p["aplicar_adicional_ir"] = st.checkbox("Aplicar adicional de IR (10%)",
                                                value=p.get("aplicar_adicional_ir", False), key=f"{pid}_p_adic")
        c1, c2, c3 = st.columns(3)
        p["irpj"] = c1.number_input("IRPJ (%)", value=float(p["irpj"]), key=f"{pid}_p_irpj")
        p["adicional_ir"] = c2.number_input("Adicional (%)", value=float(p["adicional_ir"]), key=f"{pid}_p_ad")
        p["csll"] = c3.number_input("CSLL (%)", value=float(p["csll"]), key=f"{pid}_p_csll")
        if ano == "2027":
            p["liberado"] = st.checkbox("Liberar este cálculo para o Comercial", value=p.get("liberado", False),
                                        key=f"{pid}_p_lib", disabled=p.get("cbs") is None)
            if p.get("cbs") is None:
                p["liberado"] = False

        st.subheader("Tabela de RT (vale para 2026 e 2027)")
        df = pd.DataFrame(novo["tabela_rt"]).rename(columns={
            "servico_minimo": "NF de serviço a partir de (%)", "rt_maximo": "RT máximo (%)"})
        df = st.data_editor(df, num_rows="dynamic", key=f"{pid}_p_rt", hide_index=True)
        novo["tabela_rt"] = [{"servico_minimo": float(a), "rt_maximo": float(b)}
                             for a, b in df.dropna().itertuples(index=False)]

        if st.button("Salvar parâmetros", type="primary", key=f"{pid}_p_salvar"):
            comum.salvar_parametros("cfg_cavaletti", novo, cavaletti.salvar_config, "config_cavaletti.json")
        comum.botao_backup(novo, "config_cavaletti.json")


def render(ano):
    pid = f"cav{ano}"
    ss = st.session_state
    if "cfg_cavaletti" not in ss:
        ss["cfg_cavaletti"] = cavaletti.carregar_config()
    k = lambda nome: f"{pid}_{nome}"

    if comum.adm_logado():
        parametros(ano, pid)
    cfg = ss["cfg_cavaletti"]

    comum.cabecalho(f"Venda Assistida Cavaletti {ano}",
                    "NF de produto emitida pela Cavaletti · NF de serviço emitida pela Minimal · lucro real"
                    + (" · CBS/IBS no lugar de PIS/COFINS" if ano == "2027" else ""))
    liberado, motivo = cavaletti.pronto_para_uso(cfg, ano)
    if not liberado:
        comum.aviso_bloqueado(motivo)
    pode_calcular = liberado or comum.adm_logado()

    def consultar_cnpj():
        dados = consulta.consultar(ss.get(k("cnpj"), ""), servicos.token_cnpja(st))
        ss[k("consulta")] = dados
        if dados.get("ok") and not ss.get(k("cliente")):
            ss[k("cliente")] = dados.get("razao_social", "")

    with st.container(border=True):
        st.subheader("1. Cliente")
        c1, c2 = st.columns(2)
        c1.date_input("Data", format="DD/MM/YYYY", key=k("data"))
        c2.text_input("Vendedor", key=k("vendedor"))
        c1.text_input("Cliente", key=k("cliente"))
        c2.text_input("Orçamento", key=k("orcamento"))
        c1, c2, c3 = st.columns([2, 1, 2], vertical_alignment="bottom")
        c1.text_input("CNPJ do cliente (opcional)", key=k("cnpj"), placeholder="00.000.000/0000-00")
        c2.button("🔎 Consultar", on_click=consultar_cnpj, width="stretch", key=k("btn_cnpj"))
        c3.text_input("Arquiteto (RT), se houver", key=k("arquiteto"))
        cons = ss.get(k("consulta"))
        if cons:
            if cons.get("ok"):
                st.caption(f"{cons['razao_social']} · {cons['municipio']}/{cons['uf']} · "
                           f"consulta em {cons['data_hora']}")
            else:
                st.caption(cons.get("erro", ""))

    with st.container(border=True):
        st.subheader("2. Produtos (tabela Cavaletti)")
        st.caption("Preço do fabricante sem IPI. Inclua uma linha por produto."
                   + (" Em 2027 o IPI é considerado zero." if ano == "2027" and cfg[ano].get("ipi_zero", True) else ""))
        if k("itens_df") not in ss:
            ss[k("itens_df")] = pd.DataFrame([{COLS[0]: "", COLS[1]: None, COLS[2]: 3.25, COLS[3]: None, COLS[4]: None}])
        itens_df = st.data_editor(
            ss[k("itens_df")], num_rows="dynamic", hide_index=True, width="stretch", key=k("itens"),
            column_config={
                COLS[1]: st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                COLS[2]: st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f"),
                COLS[3]: st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                COLS[4]: st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            })

    with st.container(border=True):
        st.subheader("3. Faturamento e RT")
        c1, c2, c3 = st.columns(3)
        c1.number_input("% da NF de produto (Cavaletti) *", min_value=1.0, max_value=100.0, value=None,
                        format="%.2f", key=k("share"),
                        help="Participação da NF de produto no total do pedido. O restante é a NF de serviço da Minimal.")
        c2.number_input("Desconto para pagamento à vista (%)", min_value=0.0, max_value=100.0, value=0.0,
                        format="%.2f", key=k("desconto"))
        c3.number_input("RT do arquiteto (%)", min_value=0.0, max_value=100.0, value=0.0,
                        format="%.2f", key=k("rt"))
        share = ss.get(k("share"))
        if share:
            from decimal import Decimal
            servico = (Decimal(100) - Decimal(str(share))) / 100
            maximo = cavaletti.rt_maximo(cfg, servico)
            st.caption(f"NF de serviço (Minimal): {fmt_pct(servico)} do pedido · RT máximo permitido: {fmt_pct(maximo)}")

    def itens_validos(df):
        itens = []
        for _, row in df.iterrows():
            custo, qtd = row.get(COLS[1]), row.get(COLS[4])
            if pd.isna(custo) or pd.isna(qtd) or not custo or not qtd:
                continue
            itens.append(dict(descricao=str(row.get(COLS[0]) or ""), custo=float(custo),
                              ipi=0.0 if pd.isna(row.get(COLS[2])) else float(row.get(COLS[2])),
                              entrega=0.0 if pd.isna(row.get(COLS[3])) else float(row.get(COLS[3])),
                              qtd=float(qtd)))
        return itens

    def entradas_atuais():
        return dict(itens=itens_validos(itens_df), share_produto=ss.get(k("share")) or 0,
                    desconto_avista=ss.get(k("desconto")) or 0, rt=ss.get(k("rt")) or 0)

    def meta_atual():
        return dict(vendedor=ss.get(k("vendedor"), ""), cliente=ss.get(k("cliente"), ""),
                    orcamento=ss.get(k("orcamento"), ""), arquiteto=ss.get(k("arquiteto"), ""))

    rotulo = "Calcular" if liberado else "Simular (Adm)"
    if st.button(rotulo, type="primary", key=k("calcular"), disabled=not pode_calcular):
        e = entradas_atuais()
        falta = []
        if not e["itens"]:
            falta.append("ao menos um produto com custo e quantidade")
        if not e["share_produto"]:
            falta.append("% da NF de produto")
        if falta:
            st.error("Preencha: " + ", ".join(falta) + ".")
            ss.pop(k("sim"), None)
        else:
            r = cavaletti.calcular(e, cfg, ano)
            if r["rt_acima"]:
                st.error(f"RT de {fmt_pct(r['rt_pct'])} acima do máximo permitido para essa divisão "
                         f"({fmt_pct(r['rt_max'])}). Ajuste a % da NF de produto ou o RT.")
                ss.pop(k("sim"), None)
            else:
                ss[k("sim")] = dict(entrada=e, meta=dict(meta_atual(), data=ss.get(k("data")),
                                                         cnpj=consulta.formatar_cnpj(ss.get(k("cnpj"), ""))),
                                    r=r, enviado=None, liberado=liberado)

    if k("sim") not in ss:
        return

    sim = ss[k("sim")]
    e, meta, r = sim["entrada"], sim["meta"], sim["r"]
    desatualizado = e != entradas_atuais() or any(meta[c] != v for c, v in meta_atual().items())

    linhas_pedido = [
        (f"NF de produto · Cavaletti ({fmt_pct(r['share_produto'])})", r["nf_produto"]),
        (f"  · IPI incluído", r["ipi_nf"]),
        (f"NF de serviço · Minimal ({fmt_pct(r['share_servico'])})", r["nf_servico"]),
    ]
    if ano == "2027":
        linhas_pedido += [("  · CBS (por fora)", r["cbs"]), ("  · IBS (por fora)", r["ibs"]),
                          ("  · total da NF de serviço", r["nf_servico_total"])]
    linhas_pedido += [("Valor total do pedido", r["total_cliente"]),
                      (f"Valor unitário médio ({r['qtd_total']:.0f} un.)", r["valor_unitario"])]
    linhas_servico = [(f"RT do arquiteto ({fmt_pct(r['rt_pct'])})", r["rt"]),
                      ("ISS", r["iss"])]
    if ano == "2026":
        linhas_servico.append(("PIS/COFINS", r["pis_cofins"]))
    linhas_servico += [("Valor líquido dos serviços", r["liquido"]),
                       (f"Comissão do vendedor ({fmt_pct(comum_pct(cfg[ano]['comissao_vendedor']))} do líquido)",
                        r["comissao"]),
                       ("Comissionamento empresa", r["empresa"])]
    if r["ir"]:
        linhas_servico += [("IRPJ/CSLL estimado", r["ir"]), ("Resultado da empresa", r["resultado_empresa"])]

    with st.container(border=True):
        st.subheader("Resumo do pedido")
        if not sim["liberado"]:
            st.caption("🔒 Simulação do Adm: cálculo ainda não liberado para o Comercial.")
        if desatualizado:
            st.warning("Os dados do formulário mudaram depois deste cálculo. Clique em **Calcular** de novo.")
        for t, v in linhas_pedido:
            st.write(md(f"{t}: **{formatar(v)}**" if t == "Valor total do pedido" else f"{t}: {formatar(v)}"))
        st.markdown("**NF de serviço: RT, impostos e comissão**")
        for t, v in linhas_servico:
            st.write(md(f"{t}: {formatar(v)}"))
        st.caption(md(f"Comissão equivale a {fmt_pct(r['comissao_sobre_pedido'])} do pedido total."))
        if ano == "2027":
            st.caption("A NF de produto da Cavaletti em 2027 também terá CBS/IBS próprios, destacados "
                       "pelo fabricante, que não estão neste total.")

    if desatualizado:
        return

    versao = f"Venda Assistida Cavaletti {ano}"
    cab = [("Data:", meta["data"].strftime("%d/%m/%Y") if meta["data"] else ""),
           ("Vendedor:", meta["vendedor"]), ("Cliente:", meta["cliente"]), ("CNPJ:", meta["cnpj"]),
           ("Orçamento:", meta["orcamento"]), ("Arquiteto (RT):", meta["arquiteto"] or "-"),
           ("Desconto à vista:", fmt_pct(comum_pct(e["desconto_avista"])))]
    itens_bloco = [(f"{l['descricao'] or 'Item'} · {l['qtd']:.0f} un.", l["bruto"]) for l in r["linhas"]]

    def pdf(admin):
        blocos = [("Produtos (custo + IPI + entrega/montagem)", itens_bloco),
                  ("Pedido", linhas_pedido)]
        if admin:
            blocos.append(("NF de serviço: RT, impostos e comissão", linhas_servico))
        else:
            blocos.append(("RT", [(f"RT do arquiteto ({fmt_pct(r['rt_pct'])})", r["rt"])]))
        return comum.gerar_pdf(versao + (" · Adm Comercial" if admin else ""), cab, blocos,
                               senha=comum.senha_adm() if admin else None)

    base = comum.nome_base(meta)
    st.download_button("📄 Baixar PDF do Resultado", data=pdf(False), file_name=f"{base}.pdf",
                       mime="application/pdf", key=k("pdf"))
    if not sim["liberado"]:
        return

    def montar_envio(quando):
        n = comum.n
        linha = [quando, versao, meta["data"].strftime("%d/%m/%Y") if meta["data"] else "",
                 meta["vendedor"], meta["cliente"], meta["cnpj"], meta["orcamento"], "",
                 meta["arquiteto"], "; ".join(f"{l['descricao'] or 'Item'} ({l['qtd']:.0f})" for l in r["linhas"]),
                 n(r["qtd_total"]), n(e["desconto_avista"]), n(r["share_produto"] * 100),
                 n(r["share_servico"] * 100), n(r["nf_produto"]), n(r["ipi_nf"]), n(r["nf_servico"]),
                 n(r["cbs"]), n(r["ibs"]), n(r["total_cliente"]), n(r["rt_pct"] * 100), n(r["rt"]),
                 n(r["iss"]), n(r["pis_cofins"]), n(r["liquido"]), n(r["comissao"]), n(r["empresa"])]
        pdf_adm = pdf(True)
        assunto = f"Simulação {versao} · {meta['orcamento']} · {meta['cliente']} · {meta['vendedor']}"
        corpo = (f"<p>Simulação enviada pela Calculadora Comercial ({versao}) em {quando}.</p>"
                 "<table cellpadding='4'>"
                 + "".join(f"<tr><td>{t.strip()}</td><td><b>{formatar(v)}</b></td></tr>"
                           for t, v in linhas_pedido + linhas_servico)
                 + "</table><p>O PDF do Adm Comercial é protegido por senha.</p>")
        return linha, assunto, corpo, [(f"ADM_{base}.pdf", pdf_adm), (f"{base}.pdf", pdf(False))], pdf_adm

    comum.bloco_envio(sim, meta, "va", montar_envio, base)


def comum_pct(v):
    from decimal import Decimal
    return Decimal(str(v or 0)) / 100
