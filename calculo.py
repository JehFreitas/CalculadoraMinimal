# calculo.py
# Regras de cálculo da Calculadora Comercial Minimal — regras de 2026 (lucro real).
# Nenhum percentual fica aqui: tudo vem do config.json.

import json
import os
from decimal import Decimal, getcontext

getcontext().prec = 28

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

MODO_DESTACADO = "Acréscimo aplicado ao pedido (destacado em NF)"
MODO_DILUIDO = "Acréscimo aplicado aos itens"

FINALIDADE_REVENDA = "Revenda ou industrialização"
FINALIDADE_USO = "Uso e consumo"


def carregar_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar_config(cfg, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def d(valor):
    return Decimal(str(valor))


def pct(valor):
    """Converte percentual do config (ex.: 9.25) em fração (0.0925)."""
    return d(valor) / 100


# ------------------------------------------------------------------
# Custos pagos a terceiros
# ------------------------------------------------------------------
def custo_frete(base, e, cfg):
    """Valor pago à transportadora. `base` é o valor sobre o qual a Salis cobra."""
    fr = cfg["frete"]
    if e["frete_opcao"] == "Não contratar":
        return Decimal(0), None
    if e["frete_opcao"] == "Informar valor negociado":
        return d(e["frete_negociado"]), None

    minimo = d(fr["pedido_minimo"])
    if e["estado"] == "São Paulo":
        if e["cidade"] == "Capital":
            chave = "sp_capital_comercial" if e["horario"] == "Comercial" else "sp_capital_fora_horario"
            return base * pct(fr[chave]), None
        return max(base, minimo) * pct(fr["sp_interior"]), None

    uf = cfg["estados"].get(e["estado"], {})
    percentual = uf.get("salis_capital" if e["cidade"] == "Capital" else "salis_interior")
    if percentual is None:
        return Decimal(0), f"Salis não atende {e['estado']} - {e['cidade']}."
    return max(base, minimo) * pct(percentual), None


def custo_montagem(base, e, cfg):
    """Valor pago à montadora: (total, parte percentual, parte km)."""
    mo = cfg["montagem"]
    if e["montagem_opcao"] == "Não contratar":
        return Decimal(0), Decimal(0), Decimal(0)
    if e["montagem_opcao"] == "Informar valor negociado":
        v = d(e["montagem_negociada"])
        return v, Decimal(0), Decimal(0)
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
    e: dicionário com as entradas do formulário.
    Retorna um dicionário com todos os valores da simulação.
    """
    imp, res = cfg["impostos"], cfg["resultado"]
    uf = cfg["estados"][e["estado"]]

    P = d(e["valor_produtos"])
    IPI = pct(imp["ipi"])
    IPI_DENTRO = IPI / (1 + IPI)
    PC = pct(imp["pis_cofins"])
    ICMS = pct(uf["icms_interestadual"])
    sem_ie = e["tem_ie"] == "Não"
    DIFAL = pct(uf["difal"]) if sem_ie else Decimal(0)
    FCP = pct(uf["fcp"]) if sem_ie else Decimal(0)

    # Carga sobre o valor cobrado de frete/montagem: ICMS + PIS/COFINS (base sem ICMS)
    carga = ICMS + PC * (1 - ICMS)

    # IRPJ/CSLL só afetam a margem (se houver). Sem lucro no exercício: não incidem.
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

    # Valor embutido E na NF (despesa acessória ou diluído nos itens) para cobrir
    # impostos que não estão no preço dos produtos:
    #   - cliente sem IE: guias de DIFAL/FCP;
    #   - cliente com IE para uso e consumo: ICMS sobre o IPI (ponto D).
    # Como E entra na NF como receita/valor de produto, ele também gera:
    #   - PIS/COFINS sobre o próprio E                    (flag b)
    #   - ICMS sobre o IPI e sobre o próprio E            (flag a)
    #   E·k = (DIFAL+FCP)·NF + a·ICMS·IPI,   k = 1 − a·ICMS − b·PC·(1 − a·ICMS)
    uso_consumo = (not sem_ie and e.get("finalidade") == FINALIDADE_USO
                   and imp.get("icms_sobre_ipi_ie_uso_consumo"))
    a_flag = imp.get("icms_sobre_ipi_e_difal_sem_ie") if sem_ie else uso_consumo
    a = Decimal(1) if a_flag else Decimal(0)
    b = Decimal(1) if ((sem_ie or uso_consumo) and imp.get("pis_cofins_sobre_difal_embutido", True)) else Decimal(0)
    k = 1 - a * ICMS - b * PC * (1 - a * ICMS)

    def montar_nf(frete_final, mont_final):
        soma = P + frete_final + mont_final
        if sem_ie:
            # NF = soma + IPI + embutido, com IPI = NF·IPI/(1+IPI)
            total = soma / (1 - IPI_DENTRO - (DIFAL + FCP + a * ICMS * IPI_DENTRO) / k)
            ipi = total * IPI_DENTRO
            embutido = (total * (DIFAL + FCP) + a * ICMS * ipi) / k
            icms_extra = a * ICMS * (ipi + embutido)
            pis_extra = b * PC * (embutido - a * ICMS * embutido)
        elif uso_consumo:
            # Cliente com IE, uso e consumo: o IPI integra a base do ICMS.
            # E·k = ICMS·IPI·(soma + E)  →  E = ICMS·IPI·soma / (k − ICMS·IPI)
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

    def rodada(base_terceiros):
        frete, aviso = custo_frete(base_terceiros, e, cfg)
        mont, mont_pct, mont_km = custo_montagem(base_terceiros, e, cfg)
        f_final = preco(frete, cred_frete)
        m_final = preco(mont, cred_mont)
        nf = montar_nf(f_final, m_final)
        return dict(frete_custo=frete, aviso=aviso, montagem_custo=mont,
                    montagem_pct=mont_pct, montagem_km=mont_km,
                    frete_final=f_final, montagem_final=m_final, **nf)

    modo = e["modo_acrescimo"]
    iteracoes = 1
    if modo == MODO_DESTACADO:
        r = rodada(P)
        valor_itens = P
    else:
        # Diluído nos itens: o valor dos produtos na NF passa a incluir frete,
        # montagem e o DIFAL/FCP embutido. Como a transportadora e a montadora cobram %
        # sobre esse valor, o cálculo é circular: repetimos até estabilizar.
        valor_itens = P
        for iteracoes in range(1, 201):
            base = valor_itens
            if cfg["frete"].get("base_terceiros") == "valor_total_nf":
                base = valor_itens * (1 + IPI)
            r = rodada(base)
            novo = r["total_nf"] - r["ipi"]
            if abs(novo - valor_itens) < Decimal("0.001"):
                valor_itens = novo
                break
            valor_itens = novo

    # Resultado estimado da operação de frete/montagem (antes do IR)
    receita_serv = r["frete_final"] + r["montagem_final"]
    resultado = Decimal(0)
    if receita_serv > 0:
        resultado = (receita_serv * (1 - carga)
                     + r["frete_custo"] * cred_frete + r["montagem_custo"] * cred_mont
                     - r["frete_custo"] - r["montagem_custo"])
    elif sem_cobranca:
        resultado = -(r["frete_custo"] * (1 - cred_frete) + r["montagem_custo"] * (1 - cred_mont))

    # Conferência do embutido: deve cobrir guias + impostos extras (≈ 0)
    r["sobra_difal"] = (r["difal_fcp_embutido"] - r["difal"] - r["fcp"]
                        - r["icms_extra"] - r["pis_cofins_extra"])

    # Comissão: sempre sobre os produtos, sem acréscimos.
    pc_com = pct(e.get("comissao_pct") or 0)
    comissao_correta = P * pc_com
    comissao_sistema = valor_itens * pc_com  # o ERP calcula sobre o vProd
    r.update(
        comissao_pct=pc_com,
        comissao_correta=comissao_correta,
        comissao_sistema=comissao_sistema,
        comissao_diferenca=comissao_sistema - comissao_correta,
        sp_capital_absorvido=sem_cobranca,
        uso_consumo=bool(uso_consumo),
    )

    r.update(
        modo=modo,
        iteracoes=iteracoes,
        valor_produtos=P,
        valor_itens_nf=valor_itens,  # valor dos produtos como sai na NF
        multiplicador=1 / (1 - carga),
        carga=carga,
        resultado_estimado=resultado,
    )
    if modo == MODO_DESTACADO:
        r["frete_nf"] = r["frete_final"]
        r["despesas_acessorias_nf"] = r["montagem_final"] + r["difal_fcp_embutido"]
    else:
        r["frete_nf"] = Decimal(0)
        r["despesas_acessorias_nf"] = Decimal(0)
    return r
