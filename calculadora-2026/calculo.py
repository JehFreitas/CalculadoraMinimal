# calculo.py
# Regras de cálculo da Calculadora Comercial Minimal — regras de 2026 (lucro real).
# Nenhum percentual fica aqui: tudo vem do config.json.

import json
import os
from decimal import Decimal, getcontext

getcontext().prec = 28

PASTA = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PASTA, "config.json")

# Onde cada acréscimo entra na NF
PEDIDO = "Ao pedido (destacado em NF)"
ITENS = "Aos itens"

CONTRIBUINTE = "Contribuinte do ICMS"
NAO_CONTRIBUINTE = "Não contribuinte (mesmo com IE)"

REPRESENTANTES = "Representantes"
CONSUMIDOR_FINAL = "Consumidor final"


def carregar_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar_config(cfg, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def d(valor):
    return Decimal(str(valor or 0))


def pct(valor):
    """Converte percentual do config (ex.: 9.25) em fração (0.0925)."""
    return d(valor) / 100


# ------------------------------------------------------------------
# Custos pagos a terceiros (base = valor dos produtos na NF, vProd)
# ------------------------------------------------------------------
def custo_frete(base, e, cfg):
    fr = cfg["frete"]
    if e["frete_opcao"] == "Não contratar":
        return Decimal(0), None
    if e["frete_opcao"] == "Informar valor negociado":
        return d(e["frete_negociado"]), None

    minimo = d(fr["pedido_minimo"])
    if e["estado"] == "São Paulo":
        if e["cidade"] == "Capital":
            chave = "sp_capital_comercial" if e.get("horario") != "Fora do comercial" else "sp_capital_fora_horario"
            return base * pct(fr[chave]), None
        return max(base, minimo) * pct(fr["sp_interior"]), None

    uf = cfg["estados"].get(e["estado"], {})
    percentual = uf.get("salis_capital" if e["cidade"] == "Capital" else "salis_interior")
    if percentual is None:
        return Decimal(0), f"Salis não atende {e['estado']} - {e['cidade']}."
    return max(base, minimo) * pct(percentual), None


def custo_montagem(base, e, cfg):
    """(total, parte percentual, parte km)"""
    mo = cfg["montagem"]
    if e["montagem_opcao"] == "Não contratar":
        return Decimal(0), Decimal(0), Decimal(0)
    if e["montagem_opcao"] == "Informar valor negociado":
        return d(e["montagem_negociada"]), Decimal(0), Decimal(0)
    parte_pct = base * pct(mo["percentual"])
    parte_km = Decimal(0)
    if not (e["estado"] == "São Paulo" and e["cidade"] == "Capital"):
        parte_km = d(e["km_ida_volta"]) * d(mo["valor_km"])
    return parte_pct + parte_km, parte_pct, parte_km


# ------------------------------------------------------------------
# Cálculo principal
# ------------------------------------------------------------------
def calcular(e, cfg):
    """
    e: entradas do formulário. Campos de aplicação:
      e["frete_aplicacao"], e["montagem_aplicacao"] ∈ {PEDIDO, ITENS}
    O valor embutido (DIFAL/FCP ou ICMS sobre IPI) vai SEMPRE aos itens.
    """
    imp, res = cfg["impostos"], cfg["resultado"]
    uf = cfg["estados"][e["estado"]]

    P = d(e["valor_produtos"])
    IPI = pct(imp["ipi"])
    IPI_DENTRO = IPI / (1 + IPI)
    PC = pct(imp["pis_cofins"])
    ICMS = pct(uf["icms_interestadual"])
    sem_ie = e["contribuinte"] == NAO_CONTRIBUINTE
    DIFAL = pct(uf["difal"]) if sem_ie else Decimal(0)
    FCP = pct(uf["fcp"]) if sem_ie else Decimal(0)

    # Carga sobre frete/montagem cobrados: ICMS + PIS/COFINS (base sem ICMS)
    carga = ICMS + PC * (1 - ICMS)

    if res["empresa_tem_lucro"]:
        aliq_ir = pct(res["irpj"]) + pct(res["csll"])
        if res["aplicar_adicional_ir"]:
            aliq_ir += pct(res["adicional_ir"])
    else:
        aliq_ir = Decimal(0)
    margem = pct(res["margem_frete_montagem"])

    cred_frete = PC if imp["credito_pis_cofins_frete"] else Decimal(0)
    cred_mont = PC if imp["credito_pis_cofins_montagem"] else Decimal(0)

    sp_capital = e["estado"] == "São Paulo" and e["cidade"] == "Capital"
    sem_cobranca = sp_capital and cfg["frete"].get("sp_capital_sem_cobranca", True)

    def preco(custo, credito):
        """Valor a cobrar para que, após impostos e créditos, sobre custo + margem líquida."""
        if sem_cobranca or custo == 0:
            return Decimal(0)
        lucro_antes_ir = custo * margem / (1 - aliq_ir)
        return (custo * (1 - credito) + lucro_antes_ir) / (1 - carga)

    # Valor embutido E (sempre nos itens) para cobrir impostos fora do preço:
    #   - não contribuinte: guias de DIFAL/FCP;
    #   - contribuinte consumidor final: ICMS sobre o IPI (opção do Adm).
    # E vira valor de produto, então também gera:
    #   - PIS/COFINS sobre E                       (flag b)
    #   - ICMS sobre o IPI e sobre E               (flag a)
    #   E·k = (DIFAL+FCP)·NF + a·ICMS·IPI,   k = 1 − a·ICMS − b·PC·(1 − a·ICMS)
    uso_consumo = (not sem_ie and e.get("finalidade") == CONSUMIDOR_FINAL
                   and imp.get("icms_sobre_ipi_ie_uso_consumo"))
    a_flag = imp.get("icms_sobre_ipi_e_difal_sem_ie") if sem_ie else uso_consumo
    a = Decimal(1) if a_flag else Decimal(0)
    b = Decimal(1) if ((sem_ie or uso_consumo) and imp.get("pis_cofins_sobre_difal_embutido", True)) else Decimal(0)
    k = 1 - a * ICMS - b * PC * (1 - a * ICMS)

    def montar_nf(frete_final, mont_final):
        soma = P + frete_final + mont_final
        if sem_ie:
            total = soma / (1 - IPI_DENTRO - (DIFAL + FCP + a * ICMS * IPI_DENTRO) / k)
            ipi = total * IPI_DENTRO
            embutido = (total * (DIFAL + FCP) + a * ICMS * ipi) / k
            icms_extra = a * ICMS * (ipi + embutido)
            pis_extra = b * PC * (embutido - a * ICMS * embutido)
        elif uso_consumo:
            embutido = ICMS * IPI * soma / (k - ICMS * IPI)
            ipi = (soma + embutido) * IPI
            total = soma + embutido + ipi
            icms_extra = ICMS * (ipi + embutido)
            pis_extra = b * PC * (embutido - ICMS * embutido)
        else:
            ipi = soma * IPI
            total = soma + ipi
            embutido = icms_extra = pis_extra = Decimal(0)
        return dict(total_nf=total, ipi=ipi, difal=total * DIFAL, fcp=total * FCP,
                    difal_fcp_embutido=embutido, icms_extra=icms_extra,
                    pis_cofins_extra=pis_extra)

    frete_itens = e["frete_aplicacao"] == ITENS
    mont_itens = e["montagem_aplicacao"] == ITENS

    def rodada(base):
        frete, aviso = custo_frete(base, e, cfg)
        mont, mont_pct, mont_km = custo_montagem(base, e, cfg)
        f_final = preco(frete, cred_frete)
        m_final = preco(mont, cred_mont)
        nf = montar_nf(f_final, m_final)
        itens = (P + nf["difal_fcp_embutido"]
                 + (f_final if frete_itens else 0) + (m_final if mont_itens else 0))
        return dict(frete_custo=frete, aviso=aviso, montagem_custo=mont,
                    montagem_pct=mont_pct, montagem_km=mont_km,
                    frete_final=f_final, montagem_final=m_final,
                    valor_itens_nf=itens, **nf)

    # O valor dos itens na NF (vProd) é a base da Salis e da montadora, e ele
    # depende do próprio frete/montagem/embutido: repetimos até estabilizar.
    valor_itens = P
    for iteracoes in range(1, 201):
        r = rodada(valor_itens)
        novo = r["valor_itens_nf"]
        if abs(novo - valor_itens) < Decimal("0.001"):
            break
        valor_itens = novo

    receita_serv = r["frete_final"] + r["montagem_final"]
    resultado = Decimal(0)
    if receita_serv > 0:
        resultado = (receita_serv * (1 - carga)
                     + r["frete_custo"] * cred_frete + r["montagem_custo"] * cred_mont
                     - r["frete_custo"] - r["montagem_custo"])
    elif sem_cobranca:
        resultado = -(r["frete_custo"] * (1 - cred_frete) + r["montagem_custo"] * (1 - cred_mont))

    r["sobra_difal"] = (r["difal_fcp_embutido"] - r["difal"] - r["fcp"]
                        - r["icms_extra"] - r["pis_cofins_extra"])

    pc_com = pct(e.get("comissao_pct"))
    r.update(
        iteracoes=iteracoes,
        valor_produtos=P,
        frete_nf=Decimal(0) if frete_itens else r["frete_final"],                 # vFrete
        despesas_acessorias_nf=Decimal(0) if mont_itens else r["montagem_final"],  # vOutro
        multiplicador=1 / (1 - carga),
        carga=carga,
        resultado_estimado=resultado,
        comissao_pct=pc_com,
        comissao_correta=P * pc_com,
        comissao_sistema=r["valor_itens_nf"] * pc_com,
        comissao_diferenca=(r["valor_itens_nf"] - P) * pc_com,
        sp_capital_absorvido=sem_cobranca,
        uso_consumo=bool(uso_consumo),
    )
    return r
