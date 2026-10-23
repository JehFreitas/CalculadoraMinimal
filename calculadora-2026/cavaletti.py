# cavaletti.py
# Venda Assistida Cavaletti: o fabricante emite a NF de produto direto ao cliente
# e a Minimal emite a NF de serviço. Mesma lógica da planilha usada com a Frisokar,
# ajustada para o lucro real.
#
#   NF de produto (fabricante) = (custo + IPI + entrega/montagem) × qtd × (1 − desconto à vista)
#   Total do pedido             = NF de produto ÷ % da NF de produto
#   NF de serviço (Minimal)     = Total − NF de produto
#   RT do arquiteto             = (Total − IPI da NF de produto) × % RT
#   Impostos da NF de serviço   = 2026: PIS/COFINS + ISS · 2027: ISS (CBS/IBS por fora)
#   Valor líquido dos serviços  = NF de serviço − RT − impostos
#   Comissão do vendedor        = líquido × % comissão (o restante fica para a empresa)

import json
import os
from decimal import Decimal

from calculo import PASTA, d, pct

CONFIG_PATH = os.path.join(PASTA, "config_cavaletti.json")


def carregar_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar_config(cfg, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def pronto_para_uso(cfg, ano):
    p = cfg[ano]
    if ano == "2027" and p.get("cbs") is None:
        return False, "Aguardando a alíquota de referência da CBS para 2027 (resolução do Senado)."
    if ano == "2027" and not p.get("liberado"):
        return False, "Alíquotas cadastradas, aguardando liberação pelo Adm Comercial."
    return True, ""


def rt_maximo(cfg, share_servico):
    """Maior % de RT permitido para a participação da NF de serviço no pedido."""
    maximo = Decimal(0)
    for faixa in sorted(cfg["tabela_rt"], key=lambda x: x["servico_minimo"]):
        if share_servico + Decimal("0.00001") >= pct(faixa["servico_minimo"]):
            maximo = pct(faixa["rt_maximo"])
    return maximo


def calcular(e, cfg, ano):
    """
    e["itens"]: lista de dicts {descricao, custo, ipi, entrega, qtd}
      custo   = preço unitário do fabricante, sem IPI
      ipi     = % de IPI do item (2027: zerado se ipi_zero)
      entrega = custo unitário de retirada, entrega e montagem
    e["share_produto"] (%), e["desconto_avista"] (%), e["rt"] (%)
    """
    p = cfg[ano]
    desc = pct(e.get("desconto_avista"))
    ipi_zero = ano == "2027" and p.get("ipi_zero", True)

    linhas = []
    base_total = ipi_total = entrega_total = qtd_total = Decimal(0)
    for it in e["itens"]:
        qtd = d(it.get("qtd"))
        base = d(it.get("custo")) * qtd
        ipi = Decimal(0) if ipi_zero else base * pct(it.get("ipi"))
        entrega = d(it.get("entrega")) * qtd
        linhas.append(dict(descricao=it.get("descricao") or "", qtd=qtd, base=base,
                           ipi=ipi, entrega=entrega, bruto=base + ipi + entrega))
        base_total += base
        ipi_total += ipi
        entrega_total += entrega
        qtd_total += qtd

    nf_produto = (base_total + ipi_total + entrega_total) * (1 - desc)
    ipi_nf = ipi_total * (1 - desc)
    share = pct(e["share_produto"])
    total = nf_produto / share if share else Decimal(0)
    nf_servico = total - nf_produto
    share_servico = 1 - share

    rt_pct = pct(e.get("rt"))
    rt_max = rt_maximo(cfg, share_servico)
    rt = (total - ipi_nf) * rt_pct

    iss = nf_servico * pct(p["iss"])
    if ano == "2026":
        base_pc = nf_servico if p.get("pis_cofins_sobre_iss", True) else nf_servico - iss
        pis_cofins = base_pc * pct(p["pis_cofins"])
        cbs = ibs = Decimal(0)
    else:
        pis_cofins = Decimal(0)
        base_cbs = nf_servico - iss          # ISS fora da base da CBS/IBS na transição
        cbs = base_cbs * pct(p.get("cbs") or 0)
        ibs = base_cbs * pct(p.get("ibs") or 0)
    impostos = iss + pis_cofins
    liquido = nf_servico - rt - impostos

    comissao = liquido * pct(p["comissao_vendedor"])
    empresa = liquido - comissao
    if p.get("empresa_tem_lucro"):
        aliq_ir = pct(p["irpj"]) + pct(p["csll"]) + (pct(p["adicional_ir"]) if p.get("aplicar_adicional_ir") else 0)
    else:
        aliq_ir = Decimal(0)
    ir = max(empresa, Decimal(0)) * aliq_ir

    nf_servico_total = nf_servico + cbs + ibs
    total_cliente = nf_produto + nf_servico_total
    return dict(
        linhas=linhas, qtd_total=qtd_total, base_total=base_total, ipi_nf=ipi_nf,
        entrega_total=entrega_total * (1 - desc), nf_produto=nf_produto,
        nf_servico=nf_servico, nf_servico_total=nf_servico_total, total=total,
        total_cliente=total_cliente, share_produto=share, share_servico=share_servico,
        valor_unitario=(total_cliente / qtd_total) if qtd_total else Decimal(0),
        rt_pct=rt_pct, rt_max=rt_max, rt_acima=rt_pct > rt_max + Decimal("0.0000001"), rt=rt,
        iss=iss, pis_cofins=pis_cofins, cbs=cbs, ibs=ibs, impostos=impostos,
        liquido=liquido, comissao=comissao, empresa=empresa, ir=ir,
        resultado_empresa=empresa - ir,
        comissao_sobre_pedido=(comissao / total_cliente) if total_cliente else Decimal(0),
    )
