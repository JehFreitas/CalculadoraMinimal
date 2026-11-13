# tela_nfe.py
# Tela do cálculo de NF-e Minimal (2026 e 2027).

import json

import pandas as pd
import streamlit as st

import calculo
import calculo_2027
import comum
import consulta
import descontos
import servicos
from calculo import (CONSUMIDOR_FINAL, CONTRIBUINTE, ITENS, NAO_CONTRIBUINTE, PEDIDO,
                     REPRESENTANTES)
from comum import formatar, md

OPCOES = ["Calcular", "Informar valor negociado", "Não contratar"]
MODO_PCT = "Informar o % da política"
MODO_ALVO = "Informar o valor final desejado"
MODO_COM = "Escolher a comissão desejada"
CHAVE_COM = "cfg_comercial"

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


def parametros_comerciais(pid):
    """Condições de pagamento e limites da política (vale para 2026 e 2027)."""
    com = st.session_state[CHAVE_COM]
    with st.sidebar.expander("⚙️ Condições de pagamento e política", expanded=False):
        novo = json.loads(json.dumps(com))
        par = novo["calculo_condicao"]
        st.subheader("Cálculo da condição")
        par["custo_capital_mensal"] = st.number_input(
            "Custo do capital (% ao mês)", value=float(par["custo_capital_mensal"]), step=0.1, key=f"{pid}_c_cap")
        par["tempo_fabricacao_dias"] = st.number_input(
            "Tempo de fabricação (dias)", value=int(par["tempo_fabricacao_dias"]), step=1, key=f"{pid}_c_fab")
        par["prazo_sinal_dias"] = st.number_input(
            "Prazo do sinal / antecipado (dias)", value=int(par["prazo_sinal_dias"]), step=1, key=f"{pid}_c_sin")
        par["ponto_zero_ddf"] = st.number_input(
            "Ponto 0 (DDF)", value=int(par["ponto_zero_ddf"]), step=1, key=f"{pid}_c_p0",
            help="Condição de referência, sem desconto nem acréscimo. Hoje: (1X) 30 DDF.")
        par["arredondamento"] = st.number_input(
            "Arredondar para múltiplos de (%)", value=float(par["arredondamento"]), step=0.25, key=f"{pid}_c_arr")

        novo["divisao_servico_pct"] = st.number_input(
            "Divisão: % do pedido de serviço", value=float(novo.get("divisao_servico_pct", 40)), step=1.0,
            key=f"{pid}_c_serv", help="Parte do Valor Total que vai para o pedido de serviço. O restante fica no de produtos.")

        st.subheader("Limite da política por equipe (%)")
        lim = pd.DataFrame({"Equipe": list(novo["limites_politica"].keys()),
                            "Limite (%)": list(novo["limites_politica"].values())})
        lim = st.data_editor(lim, num_rows="dynamic", hide_index=True, key=f"{pid}_c_lim")
        novo["limites_politica"] = {str(r["Equipe"]).strip(): float(r["Limite (%)"])
                                    for _, r in lim.iterrows() if str(r["Equipe"]).strip() and not pd.isna(r["Limite (%)"])}
        novo["politica_desconta_acrescimos_aos_itens"] = st.checkbox(
            "A política do ERP desconta também os acréscimos aos itens (DIFAL/FCP)",
            value=novo.get("politica_desconta_acrescimos_aos_itens", False), key=f"{pid}_c_desc",
            help="Marque se o teste no ERP mostrar que o desconto da política reduz os acréscimos "
                 "lançados aos itens. A calculadora passa a informar o DIFAL/FCP já compensado.")

        st.subheader("Condições")
        st.caption("Parcelas: prazo em DDF (ou SINAL) e % da parcela, separadas por ponto e vírgula. "
                   "Ex.: SINAL:50; 30:50")
        linhas = []
        for c in novo["condicoes"]:
            pm, calc, ap = descontos.percentual_condicao(c["parcelas"], par)
            linhas.append({"Ativa": c.get("ativa", True), "Código": c["codigo"], "Descrição": c["descricao"],
                           "Parcelas": descontos.parcelas_texto(c["parcelas"]),
                           "Prazo médio": round(float(pm or 0), 1), "Calculado (%)": round(float(calc), 2),
                           "Aplicado (%)": float(ap), "No Focco (%)": c.get("percentual_erp"),
                           "Exclusiva de cliente": c.get("exclusiva_cliente", ""),
                           "Usar % do Focco": bool(c.get("usar_percentual_erp", False)),
                           "Situação": descontos.situacao_condicao(c, com)[1],
                           "Observação": c.get("obs", "")})
        st.caption("O vendedor só vê as condições com situação Disponível: ativas, não exclusivas de cliente "
                   "e com o % do Focco igual ao calculado (sem política no Focco = 0%), ou marcadas "
                   "para usar o % do Focco. "
                   "As demais ele pede ao ADM Comercial.")
        df = st.data_editor(pd.DataFrame(linhas), num_rows="dynamic", hide_index=True, key=f"{pid}_c_cond",
                            disabled=["Prazo médio", "Calculado (%)", "Aplicado (%)", "Situação"])
        novo["condicoes"] = [
            dict(codigo=int(r["Código"]), descricao=str(r["Descrição"]).strip(),
                 parcelas=descontos.parcelas_de_texto(r["Parcelas"]), ativa=bool(r["Ativa"]),
                 percentual_erp=None if pd.isna(r["No Focco (%)"]) else float(r["No Focco (%)"]),
                 exclusiva_cliente="" if pd.isna(r["Exclusiva de cliente"]) else str(r["Exclusiva de cliente"]).strip(),
                 usar_percentual_erp=bool(r["Usar % do Focco"]) if not pd.isna(r["Usar % do Focco"]) else False,
                 obs="" if pd.isna(r["Observação"]) else str(r["Observação"]))
            for _, r in df.iterrows() if not pd.isna(r["Código"]) and str(r["Descrição"]).strip()]

        if st.button("Salvar condições e política", type="primary", key=f"{pid}_c_salvar"):
            comum.salvar_parametros(CHAVE_COM, novo, descontos.salvar_config, "config_comercial.json")
        comum.botao_backup(novo, "config_comercial.json")


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
    if CHAVE_COM not in ss:
        ss[CHAVE_COM] = descontos.carregar_config()
    k = lambda nome: f"{pid}_{nome}"   # chaves dos campos desta tela

    if comum.adm_logado():
        parametros(ano, pid, chave_cfg)
        parametros_comerciais(pid)
        cfg = ss[chave_cfg]
    com = ss[CHAVE_COM]
    conds = {c["codigo"]: c for c in descontos.condicoes_ativas(com)}
    limites = com["limites_politica"]

    def limite_efetivo(equipe, faixas):
        """Limite da equipe e, quando há tabela de comissão, o maior desconto permitido na divisão."""
        lim_eq = limites.get(equipe)
        if lim_eq is None or not faixas:
            return lim_eq
        return min(float(lim_eq), float(faixas[-1][0]))

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
        st.subheader("3. Produtos, condição e desconto")
        st.number_input("Total Itens — valor de tabela, sem descontos (com ICMS embutido) *"
                        + (" — preço de 2027, sem CBS/IBS" if ano == "2027" else ""),
                        min_value=0.0, value=None, format="%.2f", key=k("total_tabela"),
                        help="Campo Total Itens da tela de Totais do orçamento, antes de condição e política.")
        st.selectbox("Condição de pagamento *", list(conds.keys()), index=None, key=k("condicao"),
                     format_func=lambda cod: descontos.rotulo_condicao(conds[cod], com),
                     placeholder="Selecione",
                     help="Só aparecem as condições cadastradas no Focco com o % conferido. "
                          "Se a condição não estiver na lista, peça o cálculo ao ADM Comercial.")
        st.caption("A condição não está na lista? Peça o cálculo ao ADM Comercial antes de seguir.")
        c1, c2 = st.columns(2)
        c1.selectbox("Equipe do vendedor *", list(limites.keys()), index=None, key=k("equipe"),
                     placeholder="Selecione",
                     format_func=lambda eq: f"{eq} (política até {limites[eq]:g}%)".replace(".", ","))
        cm = com.get("comissao") or {}
        tem_tab = ss.get(k("equipe")) in cm.get("equipes", [])
        if tem_tab:
            c1.selectbox("Divisão de venda" + (" *" if ss.get(k("modo_pol")) == MODO_COM else " (opcional)"),
                         list(cm["divisoes"].keys()), index=None, key=k("divisao_venda"),
                         placeholder="Selecione",
                         help="Opcional. Informada, a calculadora mostra a comissão estimada. "
                              "Obrigatória para escolher pela comissão.")
        faixas = descontos.tabela_comissao(com, ss.get(k("equipe")), ss.get(k("divisao_venda")))
        modos = [MODO_PCT] + ([MODO_COM] if tem_tab else []) + [MODO_ALVO]
        if ss.get(k("modo_pol")) not in modos:
            ss[k("modo_pol")] = None
        c2.radio("Desconto da política *", modos, index=None, key=k("modo_pol"))
        limite = limite_efetivo(ss.get(k("equipe")), faixas)
        if ss.get(k("modo_pol")) == MODO_COM and not faixas:
            st.caption("Selecione a divisão de venda para escolher a comissão.")
        if ss.get(k("modo_pol")) == MODO_COM and faixas:
            st.selectbox("Comissão desejada *", list(range(len(faixas))), index=None, key=k("faixa"),
                         format_func=lambda i: descontos.rotulo_faixa(faixas, i), placeholder="Selecione",
                         help="A política fica no maior desconto da faixa escolhida (até o limite da equipe).")
        if ss.get(k("modo_pol")) == MODO_PCT:
            st.number_input("Desconto da política (%) *", min_value=0.0, max_value=100.0,
                            value=None, step=0.0001, format="%.4f", key=k("politica"),
                            help="Aplicado sobre os itens já com a condição de pagamento, como no ERP.")
        elif ss.get(k("modo_pol")) == MODO_ALVO:
            st.number_input("Valor total da NF desejado (R$) *", min_value=0.0, value=None,
                            format="%.2f", key=k("alvo"),
                            help="A calculadora encontra o % da política. Frete, montagem e DIFAL/FCP "
                                 "não são reduzidos para caber no valor, e o limite da equipe é respeitado.")
        st.checkbox("Alguns itens têm desconto diferente", key=k("tem_exc"),
                    help="Informe só os itens que fogem da regra. Os demais levam o desconto acima.")
        if ss.get(k("tem_exc")):
            st.caption("Valor do item = valor unitário de tabela × quantidade, sem desconto. "
                       "Os itens que não estão na lista levam o desconto padrão acima.")
            base_exc = pd.DataFrame({"Item": pd.Series(dtype="str"),
                                     "Valor de tabela (R$)": pd.Series(dtype="float"),
                                     "Desconto (%)": pd.Series(dtype="float")})
            st.data_editor(base_exc, num_rows="dynamic", hide_index=True, key=k("exc_editor"),
                           column_config={
                               "Item": st.column_config.TextColumn("Item (nº ou descrição)"),
                               "Valor de tabela (R$)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                               "Desconto (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0,
                                                                              format="%.4f")})

    with st.container(border=True):
        st.subheader("4. Frete e montagem")
        c1, c2 = st.columns(2)
        with c1:
            st.radio("Frete *", OPCOES, index=None, key=k("frete_opcao"))
            if ss.get(k("frete_opcao")) == "Informar valor negociado":
                st.number_input("Valor negociado do frete *", min_value=0.0, value=None,
                                format="%.2f", key=k("frete_negociado"))
        with c2:
            st.radio("Montagem *", OPCOES, index=None, key=k("montagem_opcao"))
            if ss.get(k("montagem_opcao")) == "Informar valor negociado":
                st.number_input("Valor negociado da montagem *", min_value=0.0, value=None,
                                format="%.2f", key=k("montagem_negociada"))
            if ss.get(k("montagem_opcao")) == "Calcular" and estado and cidade and not sp_capital:
                st.number_input("Distância ida e volta (km) de Barueri-SP *", min_value=0.0,
                                value=None, format="%.0f", key=k("km_ida_volta"))
        st.caption("Frete: sempre ao pedido, no campo de frete da NF · Montagem: sempre ao pedido, "
                   "em despesas acessórias"
                   + (" · DIFAL/FCP: sempre embutido nos itens" if ss.get(k("contribuinte")) == NAO_CONTRIBUINTE else "")
                   + ".")
        if sem_cobranca:
            st.caption("SP Capital: frete e montagem não são cobrados do cliente.")
        if ano == "2026":
            pct_s = com.get("divisao_servico_pct", 40)
            st.checkbox(f"Dividir em pedido de produtos ({100 - pct_s:g}%) e pedido de serviço ({pct_s:g}%)",
                        key=k("dividir"),
                        help="O orçamento é montado normalmente. Depois o ADM Comercial cria o pedido de "
                             "serviço e ajusta o pedido de produtos com os valores calculados aqui.")

    def excecoes_atuais():
        if not ss.get(k("tem_exc")):
            return []
        est = ss.get(k("exc_editor")) or {}
        linhas = [dict(l) for l in est.get("added_rows", [])]
        for i, mud in (est.get("edited_rows") or {}).items():
            if int(i) < len(linhas):
                linhas[int(i)].update(mud)
        apagar = set(est.get("deleted_rows") or [])
        out = []
        for i, l in enumerate(linhas):
            if i in apagar:
                continue
            v, pct_i = l.get("Valor de tabela (R$)"), l.get("Desconto (%)")
            if v is None and pct_i is None and not l.get("Item"):
                continue
            out.append(dict(item=str(l.get("Item") or f"Item {i + 1}"), valor=v, pct=pct_i))
        return out

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
        if not ss.get(k("total_tabela")):
            f.append("Total Itens")
        if ss.get(k("condicao")) is None:
            f.append("Condição de pagamento")
        if not ss.get(k("equipe")):
            f.append("Equipe do vendedor")
        if not ss.get(k("modo_pol")):
            f.append("Desconto da política")
        elif ss.get(k("modo_pol")) == MODO_PCT and ss.get(k("politica")) is None:
            f.append("Desconto da política (%)")
        elif ss.get(k("modo_pol")) == MODO_ALVO and not ss.get(k("alvo")):
            f.append("Valor total desejado")
        elif ss.get(k("modo_pol")) == MODO_COM and ss.get(k("faixa")) is None:
            f.append("Comissão desejada")
        cm_ = com.get("comissao") or {}
        if ss.get(k("modo_pol")) == MODO_COM and not ss.get(k("divisao_venda")):
            f.append("Divisão de venda")
        lim = limite_efetivo(ss.get(k("equipe")),
                             descontos.tabela_comissao(com, ss.get(k("equipe")), ss.get(k("divisao_venda"))))
        exc = excecoes_atuais()
        if ss.get(k("tem_exc")):
            if not exc:
                f.append("Itens com desconto diferente (ou desmarque a opção)")
            if any(x["valor"] is None or x["pct"] is None for x in exc):
                f.append("Valor e desconto de cada item com desconto diferente")
            if lim is not None and any(x["pct"] is not None and x["pct"] > lim for x in exc):
                f.append(f"Desconto de cada item dentro do limite da equipe ({lim:g}%)".replace(".", ","))
            if sum((x["valor"] or 0) for x in exc) > (ss.get(k("total_tabela")) or 0) + 0.005:
                f.append("Soma dos itens com desconto diferente até o Total Itens")
        if (ss.get(k("modo_pol")) == MODO_PCT and lim is not None and ss.get(k("politica")) is not None
                and ss.get(k("politica")) > lim):
            f.append(f"Desconto da política dentro do limite da equipe ({lim:g}%)".replace(".", ","))
        if not ss.get(k("frete_opcao")):
            f.append("Frete")
        elif ss.get(k("frete_opcao")) == "Informar valor negociado" and not ss.get(k("frete_negociado")):
            f.append("Valor negociado do frete")
        if not ss.get(k("montagem_opcao")):
            f.append("Montagem")
        elif ss.get(k("montagem_opcao")) == "Informar valor negociado" and not ss.get(k("montagem_negociada")):
            f.append("Valor negociado da montagem")
        if ss.get(k("montagem_opcao")) == "Calcular" and not sp_capital and not ss.get(k("km_ida_volta")):
            f.append("Distância ida e volta (km)")
        return f

    def entradas_atuais():
        contrib = ss.get(k("contribuinte"))
        modo = ss.get(k("modo_pol"))
        return dict(
            total_tabela=ss.get(k("total_tabela")) or 0, condicao=ss.get(k("condicao")),
            equipe=ss.get(k("equipe")), modo_pol=modo,
            politica=ss.get(k("politica")) if modo == MODO_PCT else None,
            divisao_venda=ss.get(k("divisao_venda")) if ss.get(k("equipe")) in (com.get("comissao") or {}).get("equipes", []) else None,
            faixa=ss.get(k("faixa")) if modo == MODO_COM else None,
            alvo=ss.get(k("alvo")) if modo == MODO_ALVO else None,
            excecoes=excecoes_atuais(),
            estado=ss.get(k("estado")),
            cidade=ss.get(k("cidade")),
            horario="Fora do comercial" if sp_capital else None,   # SP Capital: custo a 4%
            contribuinte=contrib,
            finalidade=ss.get(k("finalidade")) if contrib == CONTRIBUINTE else None,
            frete_opcao=ss.get(k("frete_opcao")), montagem_opcao=ss.get(k("montagem_opcao")),
            frete_negociado=ss.get(k("frete_negociado")) or 0,
            montagem_negociada=ss.get(k("montagem_negociada")) or 0,
            km_ida_volta=(ss.get(k("km_ida_volta")) or 0) if not sp_capital else 0,
            frete_aplicacao=PEDIDO,
            montagem_aplicacao=PEDIDO,
            dividir=bool(ss.get(k("dividir"))) and ano == "2026",
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
            cond = conds[e["condicao"]]
            pm, calc_c, cond_pct = descontos.percentual_aplicado(cond, com)
            faixas = descontos.tabela_comissao(com, e["equipe"], e["divisao_venda"])
            lim_ef = limite_efetivo(e["equipe"], faixas)
            pol_in = e["politica"]
            if e["modo_pol"] == MODO_COM:
                pol_in = min(float(faixas[e["faixa"]][0]), float(lim_ef))
            pol, r, aviso_pol = descontos.resolver(
                e, cfg, motor, e["total_tabela"], cond_pct, lim_ef,
                "valor_final" if e["modo_pol"] == MODO_ALVO else "percentual",
                politica=pol_in, alvo=e["alvo"],
                excecoes=[(x["valor"], x["pct"]) for x in e["excecoes"]])
            pol_ef = descontos.politica_efetiva(e["total_tabela"], cond_pct, r["valor_produtos"])
            # Teste no Focco: a política da capa incide sobre o que é lançado aos itens;
            # a política lançada em cada item (exceções) não incide. Só compensa no 1º caso.
            pol_comp = 0 if e["excecoes"] else pol
            r.update(total_tabela=calculo.d(e["total_tabela"]), cond_pct=cond_pct, cond_prazo=pm,
                     cond_rotulo=f"{cond['codigo']} - {cond['descricao']}", politica_pct=pol,
                     limite=lim_ef, aviso_politica=aviso_pol,
                     politica_efetiva=pol_ef, erp=descontos.lancamentos_erp(r, pol_comp, com))
            if e["dividir"]:
                dv = descontos.dividir(r, com, cfg["impostos"]["ipi"], pol_comp)
                prop = dv["total_produtos"] / r["total_nf"] if r["total_nf"] else 0
                dv.update(guia_difal=r["difal"] * prop, guia_fcp=r["fcp"] * prop)
                r["divisao"] = dv
            if faixas:
                # Comissão: % da faixa de cada item (média ponderada pelos produtos) sobre o
                # valor líquido da nota sem IPI (pedido dividido: NF-e sem IPI + NFS-e).
                adic = (com.get("comissao") or {}).get("adicional_divisao", 0) if e["dividir"] else 0
                _, cpct, fora = descontos.comissao_estimada(
                    faixas, e["total_tabela"], cond_pct, pol,
                    [(x["valor"], x["pct"]) for x in e["excecoes"]], adic)
                dvc = r.get("divisao")
                base_c = (dvc["total_produtos"] - dvc["ipi_produtos"] + dvc["servico"]) if dvc \
                    else r["total_nf"] - r["ipi"]
                r["comissao"] = dict(valor=base_c * cpct / 100, pct=cpct, fora=fora, adicional=adic, base=base_c)
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
    if r["difal_fcp_embutido"]:
        linhas_nf.append((f"  · {rot_emb}", r["difal_fcp_embutido"]))
    if r["frete_nf"]:
        linhas_nf.append(("Frete (vFrete)", r["frete_nf"]))
    if r["despesas_acessorias_nf"]:
        linhas_nf.append(("Despesas acessórias · montagem (vOutro)", r["despesas_acessorias_nf"]))
    linhas_nf.append(("Valor do IPI", r["ipi"]))
    if ano == "2027":
        linhas_nf += [("CBS (por fora)", r["cbs"]), ("IBS (por fora)", r["ibs"])]
    linhas_nf.append(("Valor total da NF", r["total_nf"]))

    pc = lambda v: f"{float(v):.4f}".rstrip("0").rstrip(".").replace(".", ",") + "%"
    cond_txt = ("desconto de " if r["cond_pct"] < 0 else "acréscimo de " if r["cond_pct"] > 0 else "") \
        + (pc(abs(r["cond_pct"])) if r["cond_pct"] else "sem desconto")
    valor_cond = r["total_tabela"] * r["cond_pct"] / 100
    valor_pol = r["total_tabela"] + valor_cond - r["valor_produtos"]
    excs = e.get("excecoes") or []
    rot_pol = (f"Política {pc(r['politica_pct'])}" if not excs else
               f"Política: padrão {pc(r['politica_pct'])} e {len(excs)} item(ns) com desconto diferente "
               f"(média {pc(r['politica_efetiva'])})")
    linhas_desc = [("Total Itens (tabela)", r["total_tabela"]),
                   (f"Condição {r['cond_rotulo']} ({cond_txt})", valor_cond),
                   (rot_pol, -valor_pol),
                   ("Valor dos produtos", r["valor_produtos"])]
    erp = r["erp"]
    linhas_erp = [(f"Condição de pagamento: {r['cond_rotulo']}", None),
                  ((f"Desconto Política: {r['politica_pct']:.4f}%".replace(".", ",") + " (aplicável aos itens)")
                   if not excs else
                   (f"Política (700/1/3) em cada item: {r['politica_pct']:.4f}%".replace(".", ",")
                    + " · Desconto Política da capa: 0%"), None),
                  *[(f"   exceção: {x['item']} — Política (700/1/3) {float(x['pct']):.4f}%".replace(".", ","), None)
                    for x in excs],
                  ("Valor de frete (Entrega › Transporte)", erp["frete"]),
                  ("Acréscimo MONTAGEM (valor, aplicável ao pedido)", erp["montagem"])]
    if erp["difal"] or erp["fcp"]:
        if erp["embutido_sem_guia"]:
            linhas_erp.append(("Acréscimo DIFAL (valor, aplicável aos itens) · ICMS sobre IPI", erp["difal"]))
        else:
            linhas_erp.append(("Acréscimo DIFAL (valor, aplicável aos itens)", erp["difal"]))
            if erp["fcp"]:
                linhas_erp.append(("Acréscimo FUNDO DE COMBATE À POBREZA (valor, aplicável aos itens)", erp["fcp"]))
    linhas_erp.append(("Valor Total esperado no ERP", r["total_nf"]))

    with st.container(border=True):
        st.subheader("Condição e desconto")
        if r.get("aviso_politica"):
            st.warning(r["aviso_politica"])
        for titulo, valor in linhas_desc:
            st.write(md(f"{titulo}: {formatar(valor)}"))
        cmr = r.get("comissao")
        if cmr:
            st.write(md(f"Faixa de comissão ({e['divisao_venda']}): **"
                        + f"{float(cmr['pct']):g}%".replace(".", ",") + "**"
                        + (f" (inclui {float(cmr['adicional']):g}% pela divisão)".replace(".", ",") if cmr["adicional"] else "")
                        + (" · média das faixas dos itens" if e.get("excecoes") else "")))
            if cmr["fora"]:
                st.warning("Algum desconto está acima da tabela de comissão desta divisão de venda.")
        st.caption(f"Prazo médio da condição: {float(r['cond_prazo']):.1f} dias · "
                   f"limite da política: {float(r['limite']):g}%".replace(".", ",")
                   + (f" (equipe {e['equipe']}" + (f", {e['divisao_venda']})" if e.get("divisao_venda") else ")")))

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

    with st.container(border=True):
        st.subheader("Lançar no orçamento (ERP)")
        for titulo, valor in linhas_erp:
            st.write(md(titulo if valor is None else
                        (f"**{titulo}: {formatar(valor)}**" if titulo.startswith("Valor Total")
                         else f"{titulo}: {formatar(valor)}")))
        st.caption("O ERP arredonda item a item: o Valor Total pode diferir alguns centavos.")

    dv = r.get("divisao")
    linhas_div = []
    if dv:
        linhas_div = [(f"1. Pedido de serviço ({float(dv['pct_servico']):g}% do Valor Total) — sem ICMS, IPI, "
                       "acréscimos ou descontos", dv["servico"]),
                      ("2. Pedido de produtos: retirar o acréscimo MONTAGEM", dv["retirar_montagem"])]
        if dv["retirar_difal"]:
            linhas_div.append(("   retirar o acréscimo DIFAL", dv["retirar_difal"]))
        if dv["retirar_fcp"]:
            linhas_div.append(("   retirar o acréscimo FUNDO DE COMBATE À POBREZA", dv["retirar_fcp"]))
        linhas_div += [("   manter frete, condição de pagamento e política", None),
                       ("   incluir desconto em valor, aplicável aos itens", dv["desconto_itens"]),
                       ("   IPI do pedido de produtos", dv["ipi_produtos"]),
                       (f"   Valor Total do pedido de produtos ({100 - float(dv['pct_servico']):g}%)", dv["total_produtos"])]
        guia_orig = r["difal"] + r["fcp"]
        guia_div = dv["guia_difal"] + dv["guia_fcp"]
        linhas_efeito = [("IPI: orçamento original", r["ipi"]), ("IPI: pedido de produtos", dv["ipi_produtos"])]
        if guia_orig:
            linhas_efeito += [("Guias DIFAL + FCP: orçamento original", guia_orig),
                              ("Guias DIFAL + FCP: pedido de produtos", guia_div)]
        linhas_efeito.append(("Diferença que fica com a empresa (IPI + guias), antes do ISS",
                              (r["ipi"] - dv["ipi_produtos"]) + (guia_orig - guia_div)))
    if dv and not comum.adm_logado():
        with st.container(border=True):
            st.subheader("Após a divisão (para informar o cliente)")
            st.write(md(f"Total NFe (produtos): **{formatar(dv['total_produtos'])}**"))
            st.write(md(f"Total NFSe (serviço): **{formatar(dv['servico'])}**"))
            st.caption("Monte o orçamento normalmente, com os valores acima. "
                       "O ADM Comercial faz a divisão depois.")
    elif dv:
        with st.container(border=True):
            st.subheader("Divisão em pedido de produtos e de serviço (ADM Comercial)")
            if dv["negativo"]:
                st.warning("Os produtos e o frete, sem os acréscimos, ficam abaixo da parte de produtos: "
                           "o pedido de produtos precisaria de acréscimo, não de desconto. Confira com o ADM.")
            for titulo, valor in linhas_div:
                st.write(md(titulo.strip() if valor is None else f"{titulo.strip()}: {formatar(valor)}"))
            st.caption("Montagem, DIFAL e FCP ficam cobertos pelo pedido de serviço. "
                       + ("O desconto já considera que a política do ERP incide sobre o que é lançado aos itens."
                          if com.get("politica_desconta_acrescimos_aos_itens") else ""))
            st.markdown("**Efeito da divisão**")
            for titulo, valor in linhas_efeito:
                st.write(md(f"{titulo}: {formatar(valor)}"))
            st.caption("Frete e montagem: custos considerados sobre o orçamento original (a confirmar).")

    if desatualizado:
        return

    versao = f"NF-e {ano}"
    cab = [("Data:", meta["data"].strftime("%d/%m/%Y") if meta["data"] else ""),
           ("Vendedor:", meta["vendedor"]), ("Cliente:", meta["cliente"]),
           ("CNPJ:", meta["cnpj"]), ("Orçamento:", meta["orcamento"]),
           ("Destino:", f"{e['estado']} · {e['cidade']}"),
           ("Perfil fiscal:", e["contribuinte"] + (f" · {e['finalidade']}" if e["finalidade"] else "")),
           ("Condição:", f"{r['cond_rotulo']} ({cond_txt})"),
           ("Política:", f"{r['politica_pct']:.4f}%".replace(".", ",") + f" · equipe {e['equipe']}"
                         + (f" · valor desejado {formatar(e['alvo'])}" if e.get("alvo") else "")),
           *([("Itens com desconto diferente:", " · ".join(
               f"{x['item']}: {formatar(x['valor'])} a " + f"{float(x['pct']):.4f}%".replace(".", ",")
               for x in e["excecoes"]))] if e.get("excecoes") else []),
           ("Frete:", e["frete_opcao"]),
           ("Montagem:", e["montagem_opcao"])]
    if e["km_ida_volta"]:
        cab.append(("Distância:", f"{e['km_ida_volta']:.0f} km"))

    def pdf(admin):
        blocos = [("Condição e desconto", linhas_desc),
                  ("Resumo da Nota Fiscal (NFe)", linhas_nf),
                  ("Lançar no orçamento (ERP)", [(t, v) for t, v in linhas_erp if v is not None])]
        notas = []
        if dv and not admin:
            blocos.append(("Após a divisão", [("Total NFe (produtos)", dv["total_produtos"]),
                                              ("Total NFSe (serviço)", dv["servico"])]))
        if admin and dv:
            blocos.append(("Divisão em pedido de produtos e de serviço",
                           [(t.strip(), v) for t, v in linhas_div if v is not None]))
            blocos.append(("Efeito da divisão", linhas_efeito))
        if admin:
            if sem_ie:
                if dv:
                    blocos.append(("Guias (sobre o pedido de produtos)",
                                   [("Guia DIFAL", dv["guia_difal"]), ("Guia FCP", dv["guia_fcp"])]))
                else:
                    blocos.append(("Guias", [("Guia DIFAL", r["difal"]), ("Guia FCP", r["fcp"])]))
            blocos.append(("Custos e conferência", [
                ("A pagar à transportadora", r["frete_custo"]),
                ("A pagar à montadora", r["montagem_custo"]),
                ("  · parte percentual", r["montagem_pct"]),
                ("  · deslocamento", r["montagem_km"]),
                ("Resultado frete/montagem (antes do IR)", r["resultado_estimado"]),
            ]))
            if r["difal_fcp_embutido"]:
                linhas = [("Embutido nos itens", r["difal_fcp_embutido"])]
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
            n(r["total_tabela"]), r["cond_rotulo"], n(r["cond_pct"]), e["equipe"],
            {MODO_ALVO: "Valor final", MODO_COM: "Comissão"}.get(e["modo_pol"], "Percentual"),
            round(float(r["politica_pct"]), 4), n(e["alvo"]) if e.get("alvo") else "",
            "Sim" if dv else "Não", n(dv["servico"]) if dv else "", n(dv["desconto_itens"]) if dv else "",
            n(dv["total_produtos"]) if dv else "",
            "; ".join(f"{x['item']}: {x['valor']:.2f} a {x['pct']:.4f}%" for x in e.get("excecoes") or []),
            e.get("divisao_venda") or "", n(r["comissao"]["pct"]) if r.get("comissao") else "",
        ]
        pdf_adm = pdf(True)
        assunto = f"Simulação {versao} · {meta['orcamento']} · {meta['cliente']} · {meta['vendedor']}"
        corpo = (f"<p>Simulação enviada pela Calculadora Comercial ({versao}) em {quando}.</p>"
                 "<table cellpadding='4'>"
                 + "".join(f"<tr><td>{t.strip()}</td><td><b>{formatar(v)}</b></td></tr>" for t, v in linhas_nf)
                 + f"<tr><td>A pagar à transportadora</td><td>{formatar(r['frete_custo'])}</td></tr>"
                 f"<tr><td>A pagar à montadora</td><td>{formatar(r['montagem_custo'])}</td></tr>"
                 "</table>"
                 + ("<p><b>Divisão em pedido de produtos e de serviço solicitada.</b></p><table cellpadding='4'>"
                    + "".join(f"<tr><td>{t.strip()}</td><td><b>{formatar(v)}</b></td></tr>"
                              for t, v in linhas_div if v is not None) + "</table>" if dv else "")
                 + "<p>O PDF do Adm Comercial é protegido por senha.</p>")
        return linha, assunto, corpo, [(f"ADM_{base}.pdf", pdf_adm), (f"{base}.pdf", pdf(False))], pdf_adm

    comum.bloco_envio(sim, meta, "nfe", montar_envio, base)
