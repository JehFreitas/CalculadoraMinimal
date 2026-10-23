# tela_nfe.py
# Tela do cálculo de NF-e Minimal (2026 e 2027).

import json

import pandas as pd
import streamlit as st

import calculo
import calculo_2027
import comum
import consulta
import servicos
from calculo import (CONSUMIDOR_FINAL, CONTRIBUINTE, ITENS, NAO_CONTRIBUINTE, PEDIDO,
                     REPRESENTANTES)
from comum import formatar, md

OPCOES = ["Calcular", "Informar valor negociado", "Não contratar"]

MODULOS = {
    "2026": dict(motor=calculo, arquivo="config.json", titulo="Cálculo NF-e 2026",
                 subtitulo="Regras de 2026 · lucro real"),
    "2027": dict(motor=calculo_2027, arquivo="config_2027.json", titulo="Cálculo NF-e 2027",
                 subtitulo="Reforma tributária: CBS e IBS no lugar de PIS/COFINS · lucro real"),
}


# ==================================================================
# Parâmetros (Adm)
# ==================================================================
def _editor_comum(novo, pid):
    st.subheader("Lucro e IR")
    res = novo["resultado"]
    res["margem_frete_montagem"] = st.number_input(
        "Margem líquida sobre frete e montagem (%)", value=float(res["margem_frete_montagem"]),
        step=0.5, help="0 = repassa só o custo e os impostos.", key=f"{pid}_p_margem")
    res["empresa_tem_lucro"] = st.checkbox(
        "Empresa com lucro no exercício (aplicar IRPJ/CSLL sobre a margem)",
        value=res["empresa_tem_lucro"], key=f"{pid}_p_lucro")
    res["aplicar_adicional_ir"] = st.checkbox(
        "Aplicar adicional de IR (10%)", value=res["aplicar_adicional_ir"], key=f"{pid}_p_adic")
    c1, c2, c3 = st.columns(3)
    res["irpj"] = c1.number_input("IRPJ (%)", value=float(res["irpj"]), key=f"{pid}_p_irpj")
    res["adicional_ir"] = c2.number_input("Adicional (%)", value=float(res["adicional_ir"]), key=f"{pid}_p_ad")
    res["csll"] = c3.number_input("CSLL (%)", value=float(res["csll"]), key=f"{pid}_p_csll")

    st.subheader("Frete")
    fr = novo["frete"]
    fr["pedido_minimo"] = st.number_input("Pedido mínimo Salis (R$)", value=float(fr["pedido_minimo"]), key=f"{pid}_p_min")
    fr["sp_capital_fora_horario"] = st.number_input(
        "SP Capital (%)", value=float(fr["sp_capital_fora_horario"]), key=f"{pid}_p_spc",
        help="Custo registrado para SP Capital (frete não cobrado do cliente).")
    fr["sp_interior"] = st.number_input("SP Interior (%)", value=float(fr["sp_interior"]), key=f"{pid}_p_spi")
    fr["sp_capital_sem_cobranca"] = st.checkbox(
        "Não cobrar frete e montagem em SP Capital", value=fr["sp_capital_sem_cobranca"], key=f"{pid}_p_spsem")

    st.subheader("Montagem")
    mo = novo["montagem"]
    mo["percentual"] = st.number_input("Montagem (% dos produtos)", value=float(mo["percentual"]), key=f"{pid}_p_mpct")
    mo["valor_km"] = st.number_input("Valor por km (R$)", value=float(mo["valor_km"]), key=f"{pid}_p_km")

    st.subheader("Tabela por estado (%)")
    df = pd.DataFrame.from_dict(novo["estados"], orient="index")
    df.index.name = "UF"
    df = st.data_editor(df, key=f"{pid}_p_estados", column_config={
        "icms_interestadual": "ICMS inter.", "difal": "DIFAL", "fcp": "FCP",
        "salis_capital": "Salis Capital", "salis_interior": "Salis Interior"})
    novo["estados"] = {uf: {k: (None if pd.isna(v) else float(v)) for k, v in linha.items()}
                       for uf, linha in df.iterrows()}


def parametros(ano, pid, chave_cfg):
    mod = MODULOS[ano]
    cfg = st.session_state[chave_cfg]
    with st.sidebar.expander(f"⚙️ Parâmetros · NF-e {ano}", expanded=False):
        novo = json.loads(json.dumps(cfg))
        imp = novo["impostos"]
        st.subheader("Impostos")
        if ano == "2026":
            imp["ipi"] = st.number_input("IPI (%)", value=float(imp["ipi"]), step=0.05, key=f"{pid}_p_ipi")
            imp["pis_cofins"] = st.number_input("PIS/COFINS (%)", value=float(imp["pis_cofins"]), step=0.05, key=f"{pid}_p_pc")
            imp["credito_pis_cofins_frete"] = st.checkbox(
                "Crédito de PIS/COFINS sobre o frete", value=imp["credito_pis_cofins_frete"], key=f"{pid}_p_cf")
            imp["credito_pis_cofins_montagem"] = st.checkbox(
                "Crédito de PIS/COFINS sobre a montagem", value=imp["credito_pis_cofins_montagem"], key=f"{pid}_p_cm")
            imp["pis_cofins_sobre_difal_embutido"] = st.checkbox(
                "PIS/COFINS sobre o valor embutido (DIFAL/FCP e ICMS s/ IPI)",
                value=imp.get("pis_cofins_sobre_difal_embutido", True), key=f"{pid}_p_pce")
            imp["icms_sobre_ipi_e_difal_sem_ie"] = st.checkbox(
                "Não contribuinte: ICMS sobre o IPI e o DIFAL/FCP embutido",
                value=imp.get("icms_sobre_ipi_e_difal_sem_ie", True), key=f"{pid}_p_ie")
        else:
            definida = imp.get("cbs") is not None
            cbs_ok = st.checkbox("Alíquota da CBS definida", value=definida, key=f"{pid}_p_cbsdef")
            imp["cbs"] = (st.number_input("CBS (%)", value=float(imp.get("cbs") or 8.7), step=0.05,
                                          key=f"{pid}_p_cbs") if cbs_ok else None)
            imp["ibs"] = st.number_input("IBS (%)", value=float(imp.get("ibs") or 0), step=0.05, key=f"{pid}_p_ibs")
            imp["ipi"] = st.number_input("IPI (%)", value=float(imp.get("ipi") or 0), step=0.05, key=f"{pid}_p_ipi",
                                         help="Zero em 2027, salvo produtos com incentivo na Zona Franca.")
            imp["cbs_ibs_na_base_icms"] = st.checkbox(
                "CBS/IBS na base do ICMS (entendimento de SP e PR)",
                value=imp.get("cbs_ibs_na_base_icms", True), key=f"{pid}_p_base")
            imp["credito_cbs_frete"] = st.checkbox(
                "Crédito de CBS/IBS sobre o frete", value=imp.get("credito_cbs_frete", True), key=f"{pid}_p_cf")
            imp["credito_cbs_montagem"] = st.checkbox(
                "Crédito de CBS/IBS sobre a montagem", value=imp.get("credito_cbs_montagem", True), key=f"{pid}_p_cm")
        imp["icms_sobre_ipi_ie_uso_consumo"] = st.checkbox(
            "Contribuinte consumidor final: ICMS sobre o IPI",
            value=imp.get("icms_sobre_ipi_ie_uso_consumo", False), key=f"{pid}_p_uc")
        if ano == "2027":
            novo["liberado"] = st.checkbox("Liberar este cálculo para o Comercial",
                                           value=novo.get("liberado", False), key=f"{pid}_p_lib",
                                           disabled=imp.get("cbs") is None)
            if imp.get("cbs") is None:
                novo["liberado"] = False

        _editor_comum(novo, pid)

        if st.button("Salvar parâmetros", type="primary", key=f"{pid}_p_salvar"):
            comum.salvar_parametros(chave_cfg, novo, mod["motor"].salvar_config, mod["arquivo"])
        comum.botao_backup(novo, mod["arquivo"])


# ==================================================================
# Tela
# ==================================================================
def render(ano):
    mod = MODULOS[ano]
    motor = mod["motor"]
    pid = f"nfe{ano}"
    chave_cfg = f"cfg_{pid}"
    ss = st.session_state
    if chave_cfg not in ss:
        ss[chave_cfg] = motor.carregar_config()
    cfg = ss[chave_cfg]
    k = lambda nome: f"{pid}_{nome}"   # chaves dos campos desta tela

    if comum.adm_logado():
        parametros(ano, pid, chave_cfg)
        cfg = ss[chave_cfg]

    comum.cabecalho(mod["titulo"], mod["subtitulo"])
    liberado, motivo = (True, "") if ano == "2026" else motor.pronto_para_uso(cfg)
    if not liberado:
        comum.aviso_bloqueado(motivo)
    pode_calcular = liberado or comum.adm_logado()

    # ---------------- Consulta pelo CNPJ ----------------
    def consultar_cnpj():
        dados = consulta.consultar(ss.get(k("cnpj"), ""), servicos.token_cnpja(st))
        dados["cnpj"] = consulta.so_digitos(ss.get(k("cnpj"), ""))
        ss[k("consulta")] = dados
        if not dados.get("ok"):
            return
        if dados.get("estado") in cfg["estados"]:
            ss[k("estado")] = dados["estado"]
        if dados.get("cidade"):
            ss[k("cidade")] = dados["cidade"]
        if dados.get("contribuinte_ie") is not None:
            ss[k("contribuinte")] = CONTRIBUINTE if dados["contribuinte_ie"] else NAO_CONTRIBUINTE
        if not ss.get(k("cliente")) and dados.get("razao_social"):
            ss[k("cliente")] = dados["razao_social"]

    with st.container(border=True):
        st.subheader("1. Cliente")
        c1, c2 = st.columns(2)
        c1.date_input("Data", format="DD/MM/YYYY", key=k("data"))
        c2.text_input("Vendedor", key=k("vendedor"))
        c1.text_input("Cliente", key=k("cliente"))
        c2.text_input("Orçamento", key=k("orcamento"))
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.text_input("CNPJ do cliente", key=k("cnpj"), placeholder="00.000.000/0000-00",
                      help="A consulta preenche UF, cidade e se o cliente é contribuinte.")
        c2.button("🔎 Consultar CNPJ", on_click=consultar_cnpj, width="stretch", key=k("btn_cnpj"))

        cons = ss.get(k("consulta"))
        if cons and cons.get("cnpj") != consulta.so_digitos(ss.get(k("cnpj"), "")):
            cons = None
        if cons:
            if not cons.get("ok"):
                st.warning(cons.get("erro", "Consulta indisponível.") + " Preencha os campos abaixo.")
            else:
                linhas = [f"**{cons['razao_social']}**",
                          f"{cons['municipio']}/{cons['uf']} · situação: {cons['situacao'] or '—'} · "
                          f"Simples Nacional: {cons['simples'] or '—'}"]
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
                    st.info(f"A consulta não trouxe a inscrição estadual. Confira se o cliente é "
                            f"contribuinte no [Cadastro de Contribuintes (CCC)]({consulta.LINK_CCC}) "
                            f"ou no [Sintegra]({consulta.LINK_SINTEGRA}) e marque abaixo. "
                            f"CNPJ: {consulta.formatar_cnpj(cons['cnpj'])}")

    with st.container(border=True):
        st.subheader("2. Destino e perfil fiscal")
        c1, c2 = st.columns(2)
        c1.selectbox("Estado de destino (UF) *", list(cfg["estados"].keys()), index=None,
                     key=k("estado"), placeholder="Selecione")
        c2.radio("Cidade de destino *", ["Capital", "Interior"], index=None, key=k("cidade"), horizontal=True)
        st.radio("O cliente é: *", [CONTRIBUINTE, NAO_CONTRIBUINTE], index=None, key=k("contribuinte"),
                 horizontal=True,
                 help="Não contribuinte inclui clientes que têm IE mas não são contribuintes do ICMS.")
        if ss.get(k("contribuinte")) == CONTRIBUINTE:
            st.radio("Finalidade da compra: *", [REPRESENTANTES, CONSUMIDOR_FINAL], index=None,
                     key=k("finalidade"), horizontal=True,
                     help="Representantes: compra para revenda ou industrialização. "
                          "Consumidor final: compra para uso e consumo.")

    estado, cidade = ss.get(k("estado")), ss.get(k("cidade"))
    sp_capital = estado == "São Paulo" and cidade == "Capital"
    sem_cobranca = sp_capital and cfg["frete"].get("sp_capital_sem_cobranca", True)

    with st.container(border=True):
        st.subheader("3. Produtos, frete e montagem")
        st.number_input("Valor dos produtos, já com desconto (com ICMS embutido) *"
                        + (" — preço de 2027, sem CBS/IBS" if ano == "2027" else ""),
                        min_value=0.0, value=None, format="%.2f", key=k("valor_produtos"))
        c1, c2 = st.columns(2)
        with c1:
            st.radio("Frete *", OPCOES, index=None, key=k("frete_opcao"))
            if ss.get(k("frete_opcao")) == "Informar valor negociado":
                st.number_input("Valor negociado do frete *", min_value=0.0, value=None,
                                format="%.2f", key=k("frete_negociado"))
            if ss.get(k("frete_opcao")) != "Não contratar" and not sem_cobranca:
                st.radio("Frete aplicado: *", [PEDIDO, ITENS], index=None, key=k("frete_aplicacao"),
                         help="Ao pedido: campo de frete da NF. Aos itens: somado ao valor dos produtos. "
                              "Use a mesma escolha do pedido no ERP.")
        with c2:
            st.radio("Montagem *", OPCOES, index=None, key=k("montagem_opcao"))
            if ss.get(k("montagem_opcao")) == "Informar valor negociado":
                st.number_input("Valor negociado da montagem *", min_value=0.0, value=None,
                                format="%.2f", key=k("montagem_negociada"))
            if ss.get(k("montagem_opcao")) == "Calcular" and estado and cidade and not sp_capital:
                st.number_input("Distância ida e volta (km) de Barueri-SP *", min_value=0.0,
                                value=None, format="%.0f", key=k("km_ida_volta"))
        st.caption("Montagem" + (" e DIFAL/FCP" if ss.get(k("contribuinte")) == NAO_CONTRIBUINTE else "")
                   + ": sempre ao pedido, em despesas acessórias.")
        if sem_cobranca:
            st.caption("SP Capital: frete e montagem não são cobrados do cliente.")

    # ---------------- Validação e cálculo ----------------
    def faltando():
        f = []
        if not ss.get(k("estado")):
            f.append("Estado de destino")
        if not ss.get(k("cidade")):
            f.append("Cidade de destino")
        if not ss.get(k("contribuinte")):
            f.append("Contribuinte ou não contribuinte")
        if ss.get(k("contribuinte")) == CONTRIBUINTE and not ss.get(k("finalidade")):
            f.append("Finalidade da compra")
        if not ss.get(k("valor_produtos")):
            f.append("Valor dos produtos")
        if not ss.get(k("frete_opcao")):
            f.append("Frete")
        elif ss.get(k("frete_opcao")) == "Informar valor negociado" and not ss.get(k("frete_negociado")):
            f.append("Valor negociado do frete")
        if (ss.get(k("frete_opcao")) and ss.get(k("frete_opcao")) != "Não contratar"
                and not sem_cobranca and not ss.get(k("frete_aplicacao"))):
            f.append("Frete: aplicado ao pedido ou aos itens")
        if not ss.get(k("montagem_opcao")):
            f.append("Montagem")
        elif ss.get(k("montagem_opcao")) == "Informar valor negociado" and not ss.get(k("montagem_negociada")):
            f.append("Valor negociado da montagem")
        if ss.get(k("montagem_opcao")) == "Calcular" and not sp_capital and not ss.get(k("km_ida_volta")):
            f.append("Distância ida e volta (km)")
        return f

    def entradas_atuais():
        contrib = ss.get(k("contribuinte"))
        return dict(
            valor_produtos=ss.get(k("valor_produtos")) or 0, estado=ss.get(k("estado")),
            cidade=ss.get(k("cidade")),
            horario="Fora do comercial" if sp_capital else None,   # SP Capital: custo a 4%
            contribuinte=contrib,
            finalidade=ss.get(k("finalidade")) if contrib == CONTRIBUINTE else None,
            frete_opcao=ss.get(k("frete_opcao")), montagem_opcao=ss.get(k("montagem_opcao")),
            frete_negociado=ss.get(k("frete_negociado")) or 0,
            montagem_negociada=ss.get(k("montagem_negociada")) or 0,
            km_ida_volta=(ss.get(k("km_ida_volta")) or 0) if not sp_capital else 0,
            frete_aplicacao=ss.get(k("frete_aplicacao")) if not sem_cobranca else PEDIDO,
            montagem_aplicacao=PEDIDO,
        )

    def meta_atual():
        return dict(vendedor=ss.get(k("vendedor"), ""), cliente=ss.get(k("cliente"), ""),
                    orcamento=ss.get(k("orcamento"), ""))

    def origem_dados(e):
        cons = ss.get(k("consulta"))
        if not cons or not cons.get("ok") or cons.get("cnpj") != consulta.so_digitos(ss.get(k("cnpj"), "")):
            return "Manual", "Manual", "", ""
        local = ("Consulta" if (cons.get("estado") == e["estado"] and cons.get("cidade") == e["cidade"])
                 else "Consulta alterada pelo vendedor")
        if cons.get("contribuinte_ie") is None:
            contrib = "Manual"
        else:
            esperado = CONTRIBUINTE if cons["contribuinte_ie"] else NAO_CONTRIBUINTE
            contrib = "Consulta" if esperado == e["contribuinte"] else "Consulta alterada pelo vendedor"
        return local, contrib, cons["data_hora"], cons["fonte"]

    rotulo = "Calcular" if liberado else "Simular (Adm)"
    if st.button(rotulo, type="primary", key=k("calcular"), disabled=not pode_calcular):
        falta = faltando()
        if falta:
            st.error("Preencha os campos obrigatórios: " + ", ".join(falta) + ".")
            ss.pop(k("sim"), None)
        else:
            e = entradas_atuais()
            r = motor.calcular(e, cfg)
            cons = ss.get(k("consulta")) or {}
            mesmo = cons.get("ok") and cons.get("cnpj") == consulta.so_digitos(ss.get(k("cnpj"), ""))
            meta = dict(meta_atual(), data=ss.get(k("data")),
                        cnpj=consulta.formatar_cnpj(ss.get(k("cnpj"), "")),
                        razao_social=cons.get("razao_social", "") if mesmo else "",
                        simples=cons.get("simples", "") if mesmo else "",
                        suframa=(("Sim" if cons.get("suframa") else "Não" if cons.get("suframa") is False else "")
                                 if mesmo else ""))
            ss[k("sim")] = dict(entrada=e, meta=meta, r=r, origem=origem_dados(e), enviado=None,
                                liberado=liberado)

    if k("sim") not in ss:
        return

    # ---------------- Resultado ----------------
    sim = ss[k("sim")]
    e, meta, r = sim["entrada"], sim["meta"], sim["r"]
    desatualizado = e != entradas_atuais() or any(meta[c] != v for c, v in meta_atual().items())
    sem_ie = e["contribuinte"] == NAO_CONTRIBUINTE

    rot_emb = "DIFAL/FCP embutido" if sem_ie else "ICMS sobre IPI embutido (consumidor final)"
    linhas_nf = [("Valor dos itens na NF (vProd)", r["valor_itens_nf"]),
                 ("  · produtos", r["valor_produtos"])]
    if e["frete_aplicacao"] == ITENS and r["frete_final"]:
        linhas_nf.append(("  · frete aplicado aos itens", r["frete_final"]))
    if r["frete_nf"]:
        linhas_nf.append(("Frete destacado (vFrete)", r["frete_nf"]))
    if r["despesas_acessorias_nf"]:
        linhas_nf.append(("Despesas acessórias (vOutro)", r["despesas_acessorias_nf"]))
        if r["montagem_final"]:
            linhas_nf.append(("  · montagem", r["montagem_final"]))
        if r["difal_fcp_embutido"]:
            linhas_nf.append((f"  · {rot_emb}", r["difal_fcp_embutido"]))
    linhas_nf.append(("Valor do IPI", r["ipi"]))
    if ano == "2027":
        linhas_nf += [("CBS (por fora)", r["cbs"]), ("IBS (por fora)", r["ibs"])]
    linhas_nf.append(("Valor total da NF", r["total_nf"]))

    with st.container(border=True):
        st.subheader("Resumo da Nota Fiscal")
        if not sim["liberado"]:
            st.caption("🔒 Simulação do Adm: cálculo ainda não liberado para o Comercial.")
        if desatualizado:
            st.warning("Os dados do formulário mudaram depois deste cálculo. Clique em **Calcular** de novo.")
        if r["aviso"]:
            st.warning(r["aviso"])
        for titulo, valor in linhas_nf:
            st.write(md(f"{titulo}: **{formatar(valor)}**" if titulo == "Valor total da NF"
                        else f"{titulo}: {formatar(valor)}"))
        if r["sp_capital_absorvido"]:
            st.info(md(f"SP Capital: frete e montagem não são cobrados do cliente. "
                       f"Custo absorvido pela empresa: {formatar(-r['resultado_estimado'])}."))
        elif r["resultado_estimado"] < -1:
            st.error(md(f"Atenção: frete e montagem geram resultado negativo de "
                        f"{formatar(r['resultado_estimado'])}."))

    if desatualizado:
        return

    versao = f"NF-e {ano}"
    cab = [("Data:", meta["data"].strftime("%d/%m/%Y") if meta["data"] else ""),
           ("Vendedor:", meta["vendedor"]), ("Cliente:", meta["cliente"]),
           ("CNPJ:", meta["cnpj"]), ("Orçamento:", meta["orcamento"]),
           ("Destino:", f"{e['estado']} · {e['cidade']}"),
           ("Perfil fiscal:", e["contribuinte"] + (f" · {e['finalidade']}" if e["finalidade"] else "")),
           ("Frete:", f"{e['frete_opcao']}" + (f" · {e['frete_aplicacao']}" if e["frete_opcao"] != "Não contratar" else "")),
           ("Montagem:", e["montagem_opcao"])]
    if e["km_ida_volta"]:
        cab.append(("Distância:", f"{e['km_ida_volta']:.0f} km"))

    def pdf(admin):
        blocos = [("Resumo da Nota Fiscal (NFe)", linhas_nf)]
        notas = []
        if admin:
            if sem_ie:
                blocos.append(("Guias", [("Guia DIFAL", r["difal"]), ("Guia FCP", r["fcp"])]))
            blocos.append(("Custos e conferência", [
                ("A pagar à transportadora", r["frete_custo"]),
                ("A pagar à montadora", r["montagem_custo"]),
                ("  · parte percentual", r["montagem_pct"]),
                ("  · deslocamento", r["montagem_km"]),
                ("Resultado frete/montagem (antes do IR)", r["resultado_estimado"]),
            ]))
            if r["difal_fcp_embutido"]:
                linhas = [("Embutido em despesas acessórias", r["difal_fcp_embutido"])]
                if ano == "2026":
                    linhas += [("ICMS sobre IPI e embutido", r["icms_extra"]),
                               ("PIS/COFINS sobre o embutido", r["pis_cofins_extra"])]
                linhas.append(("Sobra do embutido (deve ser zero)", r["sobra_difal"]))
                blocos.append(("Valor embutido", linhas))
            loc, contrib, dh, fonte = sim["origem"]
            notas = [f"Origem UF/cidade: {loc} · Origem contribuinte: {contrib}"
                     + (f" · Consulta {dh} ({fonte})" if dh else ""),
                     f"Cálculo resolvido em {r['iteracoes']} rodada(s)."]
        return comum.gerar_pdf(versao + (" · Adm Comercial" if admin else ""), cab, blocos, notas,
                               senha=comum.senha_adm() if admin else None)

    base = comum.nome_base(meta)
    st.download_button("📄 Baixar PDF do Resultado", data=pdf(False), file_name=f"{base}.pdf",
                       mime="application/pdf", key=k("pdf"))

    if not sim["liberado"]:
        return

    def montar_envio(quando):
        loc, contrib, dh, fonte = sim["origem"]
        n = comum.n
        linha = [
            quando, versao, meta["data"].strftime("%d/%m/%Y") if meta["data"] else "",
            meta["vendedor"], meta["cliente"], meta["cnpj"], meta["razao_social"],
            meta["orcamento"], "", loc, contrib, dh, fonte, meta["simples"], meta["suframa"],
            e["estado"], e["cidade"], e["contribuinte"], e["finalidade"] or "-",
            e["frete_aplicacao"] if e["frete_opcao"] != "Não contratar" else "-",
            n(r["valor_produtos"]), n(r["frete_custo"]), n(r["montagem_custo"]),
            n(r["frete_final"]), n(r["montagem_final"]), n(r["difal_fcp_embutido"]),
            n(r["despesas_acessorias_nf"]), n(r["difal"]), n(r["fcp"]), n(r["ipi"]),
            n(r.get("cbs", 0)), n(r.get("ibs", 0)), n(r["valor_itens_nf"]), n(r["total_nf"]),
            n(r["resultado_estimado"]),
        ]
        pdf_adm = pdf(True)
        assunto = f"Simulação {versao} · {meta['orcamento']} · {meta['cliente']} · {meta['vendedor']}"
        corpo = (f"<p>Simulação enviada pela Calculadora Comercial ({versao}) em {quando}.</p>"
                 "<table cellpadding='4'>"
                 + "".join(f"<tr><td>{t.strip()}</td><td><b>{formatar(v)}</b></td></tr>" for t, v in linhas_nf)
                 + f"<tr><td>A pagar à transportadora</td><td>{formatar(r['frete_custo'])}</td></tr>"
                 f"<tr><td>A pagar à montadora</td><td>{formatar(r['montagem_custo'])}</td></tr>"
                 "</table><p>O PDF do Adm Comercial é protegido por senha.</p>")
        return linha, assunto, corpo, [(f"ADM_{base}.pdf", pdf_adm), (f"{base}.pdf", pdf(False))], pdf_adm

    comum.bloco_envio(sim, meta, "nfe", montar_envio, base)
