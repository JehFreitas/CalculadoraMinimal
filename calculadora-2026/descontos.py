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


def situacao_condicao(c, com):
    """(disponível para o vendedor?, motivo). Só entra a condição ativa, não exclusiva de cliente
    e cujo % no Focco (sem política = 0%) é igual ao calculado."""
    if not c.get("ativa", True):
        return False, "Inativa"
    if c.get("exclusiva_cliente"):
        return False, "Exclusiva de cliente"
    if c.get("percentual_erp") is None:
        return False, "% no Focco não confirmado"
    _, _, ap = percentual_condicao(c["parcelas"], com["calculo_condicao"])
    if abs(ap - d(c["percentual_erp"])) > Decimal("0.0001"):
        return False, "% do Focco diferente do calculado"
    return True, "Disponível"


def condicoes_ativas(com):
    return [c for c in com["condicoes"] if situacao_condicao(c, com)[0]]


def rotulo_condicao(c, com):
    _, _, ap = percentual_condicao(c["parcelas"], com["calculo_condicao"])
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
def valor_produtos(total_tabela, cond_pct, pol_pct):
    return d(total_tabela) * (1 + d(cond_pct) / 100) * (1 - d(pol_pct) / 100)


def resolver(e, cfg, motor, total_tabela, cond_pct, limite, modo, politica=None, alvo=None):
    """
    Calcula a NF a partir do Total Itens de tabela.
    modo "percentual": usa a política informada (até o limite).
    modo "valor_final": encontra a política que leva o Valor Total da NF ao alvo.
        Frete, montagem e DIFAL/FCP são sempre calculados normalmente; só a política muda.
        Nunca passa do limite nem fica abaixo de 0%.
    Retorna (politica_pct, resultado, aviso).
    """
    limite = d(limite)

    def calc(pol):
        ent = dict(e, valor_produtos=valor_produtos(total_tabela, cond_pct, pol))
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
        return limite, rmax, ("Não é possível chegar ao valor desejado dentro do limite da política "
                              f"({limite}%). O menor total possível é o mostrado abaixo.")
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
