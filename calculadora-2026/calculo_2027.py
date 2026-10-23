# calculo_2027.py
# Regras de cálculo da NF-e a partir de 2027 (reforma tributária, lucro real).
#
# O que muda em relação a 2026:
#   - PIS/COFINS deixam de existir; entram CBS e IBS, cobrados "por fora"
#     (somados ao total da NF, fora do preço) sobre o valor sem ICMS.
#   - IPI vai a zero para a maior parte dos produtos (parâmetro).
#   - Crédito de CBS/IBS sobre o que pagamos à Salis e à montadora, quando
#     elas destacam o tributo na nota (parâmetro).
#   - Opção de incluir CBS/IBS na base do ICMS (entendimento de SP e PR).
# ICMS, DIFAL e FCP seguem como em 2026.
#
# Premissa: o "valor dos produtos" informado já é o preço de 2027
# (com ICMS e sem CBS/IBS).

import json
import os
from decimal import Decimal

from calculo import (CONSUMIDOR_FINAL, ITENS, NAO_CONTRIBUINTE, PASTA,
                     custo_frete, custo_montagem, d, pct)

CONFIG_PATH = os.path.join(PASTA, "config_2027.json")


def carregar_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar_config(cfg, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def pronto_para_uso(cfg):
    """(liberado, motivo)"""
    if cfg["impostos"].get("cbs") is None:
        return False, "Aguardando a alíquota de referência da CBS para 2027 (resolução do Senado)."
    if not cfg.get("liberado"):
        return False, "Alíquotas cadastradas, aguardando liberação pelo Adm Comercial."
    return True, ""


def calcular(e, cfg):
    imp, res = cfg["impostos"], cfg["resultado"]
    uf = cfg["estados"][e["estado"]]

    P = d(e["valor_produtos"])
    CBS = pct(imp.get("cbs") or 0)
    IBS = pct(imp.get("ibs") or 0)
    T = CBS + IBS
    IPI = pct(imp.get("ipi") or 0)
    I = pct(uf["icms_interestadual"])
    A = Decimal(1) if imp.get("cbs_ibs_na_base_icms") else Decimal(0)
    sem_ie = e["contribuinte"] == NAO_CONTRIBUINTE
    DIFAL = pct(uf["difal"]) if sem_ie else Decimal(0)
    FCP = pct(uf["fcp"]) if sem_ie else Decimal(0)
    consumidor_final = sem_ie or (e.get("finalidade") == CONSUMIDOR_FINAL
                                  and imp.get("icms_sobre_ipi_ie_uso_consumo"))
    icms_sobre_ipi = IPI > 0 and consumidor_final

    if res["empresa_tem_lucro"]:
        aliq_ir = pct(res["irpj"]) + pct(res["csll"])
        if res["aplicar_adicional_ir"]:
            aliq_ir += pct(res["adicional_ir"])
    else:
        aliq_ir = Decimal(0)
    margem = pct(res["margem_frete_montagem"])

    # Crédito de CBS/IBS sobre o valor pago ao fornecedor (tributo destacado por fora)
    cred_taxa = T / (1 + T)
    cred_frete = cred_taxa if imp.get("credito_cbs_frete") else Decimal(0)
    cred_mont = cred_taxa if imp.get("credito_cbs_montagem") else Decimal(0)

    sp_capital = e["estado"] == "São Paulo" and e["cidade"] == "Capital"
    sem_cobranca = sp_capital and cfg["frete"].get("sp_capital_sem_cobranca", True)

    def linha(liquido):
        """Valor da linha na NF (com ICMS por dentro) para a empresa ficar com `liquido`."""
        return liquido * (1 + A * T * I) / (1 - I)

    def preco(custo, credito):
        if sem_cobranca or custo == 0:
            return Decimal(0), Decimal(0)
        liquido = custo * (1 - credito) + custo * margem / (1 - aliq_ir)
        return linha(liquido), liquido

    frete_itens = e.get("frete_aplicacao") == ITENS
    liq_P = P * (1 - I) / (1 + A * T * I)

    def rodada(base):
        frete, aviso = custo_frete(base, e, cfg)
        mont, mont_pct, mont_km = custo_montagem(base, e, cfg)
        F, liq_F = preco(frete, cred_frete)
        M, liq_M = preco(mont, cred_mont)

        # Valor embutido E (despesas acessórias): guias de DIFAL/FCP e ICMS sobre o IPI
        E = liq_E = Decimal(0)
        for _ in range(200):
            soma = P + F + M + E
            ipi = soma * IPI
            base_icms = (soma + A * T * (liq_P + liq_F + liq_M + liq_E)
                         + (ipi if icms_sobre_ipi else 0))
            guias = (DIFAL + FCP) * base_icms
            necessario = guias + (I * ipi if icms_sobre_ipi else 0)
            novo_liq = necessario
            novo_E = linha(novo_liq) if necessario else Decimal(0)
            if abs(novo_E - E) < Decimal("0.0001"):
                E, liq_E = novo_E, novo_liq
                break
            E, liq_E = novo_E, novo_liq

        soma = P + F + M + E
        ipi = soma * IPI
        liq_total = liq_P + liq_F + liq_M + liq_E
        cbs, ibs = CBS * liq_total, IBS * liq_total
        base_icms = soma + A * T * liq_total + (ipi if icms_sobre_ipi else 0)
        return dict(
            frete_custo=frete, aviso=aviso, montagem_custo=mont,
            montagem_pct=mont_pct, montagem_km=mont_km,
            frete_final=F, montagem_final=M, difal_fcp_embutido=E,
            ipi=ipi, cbs=cbs, ibs=ibs, base_icms=base_icms,
            icms=I * base_icms, difal=DIFAL * base_icms, fcp=FCP * base_icms,
            total_nf=soma + ipi + cbs + ibs,
            valor_itens_nf=P + (F if frete_itens else 0),
            liq_F=liq_F, liq_M=liq_M, liq_E=liq_E,
        )

    valor_itens = P
    for iteracoes in range(1, 201):
        r = rodada(valor_itens)
        if abs(r["valor_itens_nf"] - valor_itens) < Decimal("0.001"):
            break
        valor_itens = r["valor_itens_nf"]

    # Resultado: o que fica (líquido de ICMS, com CBS/IBS neutros) menos o pago a terceiros
    receita_serv = r["frete_final"] + r["montagem_final"]
    if receita_serv > 0:
        resultado = (r["liq_F"] + r["liq_M"]
                     + r["frete_custo"] * cred_frete + r["montagem_custo"] * cred_mont
                     - r["frete_custo"] - r["montagem_custo"])
    elif sem_cobranca:
        resultado = -(r["frete_custo"] * (1 - cred_frete) + r["montagem_custo"] * (1 - cred_mont))
    else:
        resultado = Decimal(0)

    r.update(
        iteracoes=iteracoes,
        valor_produtos=P,
        frete_nf=Decimal(0) if frete_itens else r["frete_final"],
        despesas_acessorias_nf=r["montagem_final"] + r["difal_fcp_embutido"],
        sobra_difal=r["liq_E"] - r["difal"] - r["fcp"] - (I * r["ipi"] if icms_sobre_ipi else 0),
        resultado_estimado=resultado,
        multiplicador=(1 + A * T * I) / (1 - I),
        carga=I,
        sp_capital_absorvido=sem_cobranca,
        icms_extra=Decimal(0), pis_cofins_extra=Decimal(0),
    )
    return r
