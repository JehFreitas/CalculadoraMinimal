# descontos.py
# Condição de pagamento e desconto da política, como no ERP.
#
# Ordem (igual ao FoccoERP):
#   itens de tabela (Total Itens)
#   × (1 + % da condição de pagamento)          desconto (−) ou acréscimo (+)
#   × (1 − % da política)                        sobre o valor já com a condição
#   = valor dos produtos na NF (base de frete, montagem e DIFAL)
#
# % da condição: método da planilha "Revisão Acréscimos e Descontos" (aba Revisão do Cálculo):
#   prazo médio = Σ (prazo da parcela + tempo de fabricação) × % da parcela
#                 (sinal/antecipado entra com o prazo do sinal, −23 dias)
#   custo diário = (1 + custo do capital mensal) ^ (1/30) − 1
#   % calculado = (1 + custo diário) ^ (prazo médio − prazo médio do ponto 0) − 1
#                 ponto 0 = (1X) 30 DDF → 30 + 30 = 60 dias
#   % aplicado  = % calculado arredondado ao múltiplo de 0,5% mais próximo

import json
import os
from decimal import ROUND_HALF_UP, Decimal

from calculo import PASTA, d

CONFIG_PATH = os.path.join(PASTA, "config_comercial.json")
CASAS_POLITICA = Decimal("0.0001")   # o ERP aceita a política com 4 casas (ex.: 24,6122%)


def carregar_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar_config(cfg, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------
# Condição de pagamento
# ------------------------------------------------------------------
def _prazo(p, par):
    return d(par["prazo_sinal_dias"]) if str(p).upper() in ("SINAL", "ANTECIPADO", "A VISTA") else d(p)


def prazo_medio(parcelas, par):
    """parcelas: [[prazo em DDF ou "SINAL", % da parcela], ...]"""
    total = sum(d(pc) for _, pc in parcelas)
    if total <= 0:
        return None
    fab = d(par["tempo_fabricacao_dias"])
    return sum((_prazo(p, par) + fab) * d(pc) for p, pc in parcelas) / total


def percentual_condicao(parcelas, par):
    """(prazo médio, % calculado, % aplicado) — percentuais em %, negativos = desconto."""
    pm = prazo_medio(parcelas, par)
    if pm is None:
        return None, Decimal(0), Decimal(0)
    diario = (1 + float(par["custo_capital_mensal"]) / 100) ** (1 / 30) - 1
    ponto0 = d(par["ponto_zero_ddf"]) + d(par["tempo_fabricacao_dias"])
    calc = Decimal(str(((1 + diario) ** float(pm - ponto0) - 1) * 100))
    passo = d(par["arredondamento"])
    aplicado = (calc / passo).quantize(Decimal(1), ROUND_HALF_UP) * passo if passo else calc
    return pm, calc, aplicado + 0   # + 0 evita "-0"


def percentual_aplicado(c, com):
    """% usado no cálculo: o calculado, ou o do Focco quando o ADM decidiu mantê-lo."""
    pm, calc, ap = percentual_condicao(c["parcelas"], com["calculo_condicao"])
    if c.get("usar_percentual_erp") and c.get("percentual_erp") is not None:
        ap = d(c["percentual_erp"])
    return pm, calc, ap


def situacao_condicao(c, com):
    """(disponível para o vendedor?, motivo). Só entra a condição ativa, não exclusiva de cliente
    e cujo % no Focco (sem política = 0%) é igual ao calculado."""
    if not c.get("ativa", True):
        return False, "Inativa"
    if c.get("exclusiva_cliente"):
        return False, "Exclusiva de cliente"
    if c.get("percentual_erp") is None:
        return False, "% no Focco não confirmado"
    if c.get("usar_percentual_erp"):
        return True, "Disponível (% do Focco)"
    _, _, ap = percentual_condicao(c["parcelas"], com["calculo_condicao"])
    if abs(ap - d(c["percentual_erp"])) > Decimal("0.0001"):
        return False, "% do Focco diferente do calculado"
    return True, "Disponível"


def condicoes_ativas(com):
    return [c for c in com["condicoes"] if situacao_condicao(c, com)[0]]


def rotulo_condicao(c, com):
    _, _, ap = percentual_aplicado(c, com)
    sinal = "desconto" if ap < 0 else "acréscimo" if ap > 0 else "sem desconto"
    pct = f" {abs(ap):.2f}%".replace(".", ",") if ap else ""
    return f"{c['codigo']} - {c['descricao']} ({sinal}{pct})"


def parcelas_texto(parcelas):
    return "; ".join(f"{p}:{str(pc).replace('.', ',')}" for p, pc in parcelas)


def parcelas_de_texto(txt):
    """'SINAL:50; 30:50' -> [['SINAL', 50.0], [30, 50.0]]"""
    out = []
    for parte in str(txt or "").split(";"):
        if ":" not in parte:
            continue
        p, pc = (x.strip() for x in parte.split(":", 1))
        p = "SINAL" if p.upper() in ("SINAL", "ANTECIPADO", "A VISTA") else int(float(p.replace(",", ".")))
        out.append([p, float(pc.replace(",", ".").replace("%", ""))])
    return out


# ------------------------------------------------------------------
# Política
# ------------------------------------------------------------------
def valor_produtos(total_tabela, cond_pct, pol_pct, excecoes=()):
    """
    Itens × (1 + condição) × (1 − política), item a item (como o Focco).
    excecoes: [(valor de tabela do item já × quantidade, % de política do item)];
    os demais itens (Total Itens − soma das exceções) levam a política padrão.
    """
    exc_val = sum((d(v) for v, _ in excecoes), Decimal(0))
    liquido = (d(total_tabela) - exc_val) * (1 - d(pol_pct) / 100)
    liquido += sum((d(v) * (1 - d(p) / 100) for v, p in excecoes), Decimal(0))
    return liquido * (1 + d(cond_pct) / 100)


def politica_efetiva(total_tabela, cond_pct, valor_prod):
    """Desconto médio da política sobre os itens (já com a condição), em %."""
    base = d(total_tabela) * (1 + d(cond_pct) / 100)
    return (1 - d(valor_prod) / base) * 100 if base else Decimal(0)


def resolver(e, cfg, motor, total_tabela, cond_pct, limite, modo, politica=None, alvo=None, excecoes=()):
    """
    Calcula a NF a partir do Total Itens de tabela.
    modo "percentual": usa a política informada (até o limite).
    modo "valor_final": encontra a política que leva o Valor Total da NF ao alvo.
        Frete, montagem e DIFAL/FCP são sempre calculados normalmente; só a política muda.
        Nunca passa do limite nem fica abaixo de 0%.
    excecoes: itens com política própria (fixa); a política calculada vale para os demais.
    Retorna (politica_pct, resultado, aviso).
    """
    limite = d(limite)

    def calc(pol):
        ent = dict(e, valor_produtos=valor_produtos(total_tabela, cond_pct, pol, excecoes))
        return motor.calcular(ent, cfg)

    if modo == "percentual":
        pol = d(politica)
        aviso = None
        if pol > limite:
            aviso = f"Desconto da política acima do limite da equipe ({limite}%)."
        return pol, calc(pol), aviso

    alvo = d(alvo)
    r0 = calc(Decimal(0))
    if r0["total_nf"] <= alvo:
        aviso = None
        if r0["total_nf"] < alvo - Decimal("0.01"):
            aviso = ("O valor desejado é maior que o total sem desconto da política. "
                     "A política fica em 0% e nada é acrescentado para completar.")
        return Decimal(0), r0, aviso
    rmax = calc(limite)
    if rmax["total_nf"] > alvo:
        menor = f"R$ {rmax['total_nf']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        lim_txt = f"{limite:f}".rstrip("0").rstrip(".").replace(".", ",")
        return limite, rmax, ("Não é possível chegar ao valor desejado dentro do limite da política "
                              f"({lim_txt}%). O menor Valor Total possível é {menor}.")
    lo, hi = Decimal(0), limite          # total cai quando a política sobe
    for _ in range(60):
        meio = (lo + hi) / 2
        if calc(meio)["total_nf"] > alvo:
            lo = meio
        else:
            hi = meio
    pol = ((lo + hi) / 2).quantize(CASAS_POLITICA, ROUND_HALF_UP)
    pol = min(pol, limite)
    return pol, calc(pol), None


def lancamentos_erp(r, pol_pct, com):
    """Valores para lançar no orçamento. DIFAL e FCP separados, na proporção das guias."""
    E = r["difal_fcp_embutido"]
    guias = r["difal"] + r["fcp"]
    difal_l = E * r["difal"] / guias if guias else E
    fcp_l = E - difal_l
    if com.get("politica_desconta_acrescimos_aos_itens") and pol_pct:
        fator = 1 - d(pol_pct) / 100
        difal_l, fcp_l = difal_l / fator, fcp_l / fator
    return dict(frete=r["frete_nf"], montagem=r["despesas_acessorias_nf"], difal=difal_l, fcp=fcp_l,
                embutido_sem_guia=(guias == 0 and E > 0))


# ------------------------------------------------------------------
# Divisão em pedido de produtos e pedido de serviço (feita pelo ADM Comercial)
# ------------------------------------------------------------------
def dividir(r, com, ipi_pct, pol_pct):
    """
    Política da empresa: o orçamento (Valor Total da NF) é dividido em
      - pedido de serviço = % de serviço × total (sem ICMS, IPI, acréscimos ou descontos);
      - pedido de produtos = o restante.
    No pedido de produtos saem os acréscimos de montagem, DIFAL e FCP (cobertos pelo serviço);
    frete, condição e política continuam. Falta um desconto em valor aos itens que faça
    o pedido de produtos fechar no restante:
      (itens líquidos − desconto + frete) × (1 + IPI) = total de produtos
    Se a política do ERP incide sobre o que é lançado aos itens, o desconto lançado é
    aumentado para que o efeito líquido seja o necessário.
    """
    total = r["total_nf"]
    pct_serv = d(com.get("divisao_servico_pct", 40)) / 100
    servico = total * pct_serv
    produtos = total - servico
    ipi = d(ipi_pct) / 100
    itens = r["valor_produtos"]                 # já com condição e política, sem DIFAL/FCP
    frete = r["frete_nf"]
    reducao = itens + frete - produtos / (1 + ipi)
    lancar = reducao
    if com.get("politica_desconta_acrescimos_aos_itens") and pol_pct:
        lancar = reducao / (1 - d(pol_pct) / 100)
    base_prod = itens - reducao + frete
    ipi_prod = base_prod * ipi
    erp = r["erp"]
    return dict(pct_servico=pct_serv * 100, servico=servico, produtos=produtos,
                desconto_itens=lancar, reducao_liquida=reducao,
                itens_produtos=itens - reducao, ipi_produtos=ipi_prod,
                total_produtos=base_prod + ipi_prod,
                retirar_montagem=erp["montagem"], retirar_difal=erp["difal"], retirar_fcp=erp["fcp"],
                negativo=reducao < 0)


# ------------------------------------------------------------------
# Comissão por faixa de desconto (tabela 2023)
# ------------------------------------------------------------------
def tabela_comissao(com, equipe, divisao):
    cm = com.get("comissao") or {}
    if equipe not in cm.get("equipes", []) or divisao not in cm.get("divisoes", {}):
        return None
    return sorted(cm["divisoes"][divisao], key=lambda f: f[0])


def faixa_comissao(faixas, pol_pct):
    """% de comissão para a política informada; None = acima da tabela (não permitido)."""
    p = d(pol_pct)
    for maximo, comissao in faixas:
        if p <= d(maximo):
            return d(comissao)
    return None


def rotulo_faixa(faixas, i):
    minimo = 0 if i == 0 else faixas[i - 1][0] + 1
    maximo, comissao = faixas[i]
    return f"{comissao:g}% de comissão (desconto de {minimo:g}% a {maximo:g}%)".replace(".", ",")


def comissao_estimada(faixas, total_tabela, cond_pct, pol_pct, excecoes=(), adicional=0):
    """Comissão sobre o valor dos produtos, item a item pela faixa de cada desconto.
    Retorna (valor, % médio, algum item fora da tabela?)."""
    fator = 1 + d(cond_pct) / 100
    partes = [(d(total_tabela) - sum((d(v) for v, _ in excecoes), Decimal(0)), d(pol_pct))]
    partes += [(d(v), d(p)) for v, p in excecoes]
    valor = base = Decimal(0)
    fora = False
    for v, p in partes:
        liquido = v * fator * (1 - p / 100)
        taxa = faixa_comissao(faixas, p)
        if taxa is None:
            fora = True
            taxa = Decimal(0)
        valor += liquido * (taxa + d(adicional)) / 100
        base += liquido
    return valor, (valor / base * 100 if base else Decimal(0)), fora
