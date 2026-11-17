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
    e: entradas do formulário.
    Frete: sempre ao pedido, em campo próprio (vFrete).
    Montagem: sempre ao pedido, em despesas acessórias (vOutro).
    Valor embutido (DIFAL/FCP ou ICMS sobre IPI): sempre aos itens (vProd).
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

    # Valor embutido E (sempre aos itens) para cobrir impostos fora do preço:
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


    dil_f = bool(e.get("diluir_frete"))
    dil_m = bool(e.get("diluir_montagem"))

    def rodada(base):
        frete, aviso = custo_frete(base, e, cfg)
        mont, mont_pct, mont_km = custo_montagem(base, e, cfg)
        f_final = preco(frete, cred_frete)
        m_final = preco(mont, cred_mont)
        nf = montar_nf(f_final, m_final)
        itens = P + nf["difal_fcp_embutido"]
        # frete e/ou montagem lançados aos itens entram no vProd (base do frete e da montagem)
        itens += (f_final if dil_f else 0) + (m_final if dil_m else 0)
        return dict(frete_custo=frete, aviso=aviso, montagem_custo=mont,
                    montagem_pct=mont_pct, montagem_km=mont_km,
                    frete_final=f_final, montagem_final=m_final,
                    valor_itens_nf=itens, **nf)

    # O valor dos itens na NF (vProd) é a base da Salis e da montadora; com o DIFAL
    # embutido nos itens, ele depende do próprio cálculo: repetimos até estabilizar.
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

    if e.get("divisao_params") and receita_serv >= 0:
        return _dividido(r, e, cfg, dict(P=P, IPI=IPI, ICMS=ICMS, DIFAL=DIFAL, FCP=FCP, a=a, carga=carga,
                                         cred_mont=cred_mont, cred_frete=cred_frete, margem=margem, aliq_ir=aliq_ir,
                                         sem_cobranca=sem_cobranca, iteracoes=iteracoes))

    r.update(
        iteracoes=iteracoes,
        valor_produtos=P,
        frete_nf=r["frete_final"],                 # vFrete
        despesas_acessorias_nf=r["montagem_final"],  # vOutro
        multiplicador=1 / (1 - carga),
        carga=carga,
        resultado_estimado=resultado,
        sp_capital_absorvido=sem_cobranca,
        uso_consumo=bool(uso_consumo),
        diluido_frete=dil_f, diluido_montagem=dil_m,
    )
    return r


def _dividido(r0, e, cfg, k):
    """
    Pedido dividido em produto x serviço (decidido no orçamento).
    Os produtos, o frete, o IPI e o ICMS seguem o cálculo normal (a economia de IPI e ICMS da
    divisão fica com a empresa). Os acréscimos são refeitos pelo que de fato acontece:
      - montagem vai para a NFS-e: preço = custo × (1 − crédito) ÷ (1 − ISS − PIS/COFINS do serviço);
      - DIFAL/FCP cobre só as guias da NF-e de produtos (+ ICMS sobre o IPI dela), e o valor
        acrescentado é receita de serviço: E' × (1 − ISS − PIS/COFINS) = guias + ICMS sobre IPI.
    Custos da Salis e da montadora: os mesmos do pedido sem divisão (conservador).
    """
    dp = e["divisao_params"]
    s_pct = d(dp["pct_servico"]) / 100
    carga_s = d(dp["iss"]) / 100 + d(dp["pis_cofins"]) / 100
    P, IPI = k["P"], k["IPI"]
    F = r0["frete_final"]
    if k["sem_cobranca"] or r0["montagem_custo"] == 0:
        M = Decimal(0)
    else:
        c = r0["montagem_custo"]
        M = (c * (1 - k["cred_mont"]) + c * k["margem"] / (1 - k["aliq_ir"])) / (1 - carga_s)
    E = Decimal(0)
    for _ in range(200):
        T = (P + F + M + E) * (1 + IPI)
        T_prod = T * (1 - s_pct)
        ipi_prod = T_prod * IPI / (1 + IPI)
        necessario = (k["DIFAL"] + k["FCP"]) * T_prod + k["a"] * k["ICMS"] * ipi_prod
        novo = necessario / (1 - carga_s) if necessario else Decimal(0)
        if abs(novo - E) < Decimal("0.00001"):
            E = novo
            break
        E = novo
    T = (P + F + M + E) * (1 + IPI)
    T_prod = T * (1 - s_pct)
    dil_f, dil_m = bool(e.get("diluir_frete")), bool(e.get("diluir_montagem"))
    r = dict(r0)
    sem = {c: r0[c] for c in ("total_nf", "ipi", "difal", "fcp", "difal_fcp_embutido", "montagem_final",
                              "frete_final", "valor_itens_nf")}
    # resultado de frete (NF-e) e montagem (NFS-e): receita líquida de impostos + créditos − custos
    fc, mc = r0["frete_custo"], r0["montagem_custo"]
    if k["sem_cobranca"]:
        res = -(fc * (1 - k["cred_frete"]) + mc * (1 - k["cred_mont"]))
    else:
        res = Decimal(0)
        if F:
            res += F * (1 - k["carga"]) + fc * k["cred_frete"] - fc
        if M:
            res += M * (1 - carga_s) + mc * k["cred_mont"] - mc
    r.update(
        montagem_final=M, difal_fcp_embutido=E, ipi=(P + F + M + E) * IPI, total_nf=T,
        difal=k["DIFAL"] * T_prod, fcp=k["FCP"] * T_prod,
        valor_itens_nf=P + E + (F if dil_f else 0) + (M if dil_m else 0),
        icms_extra=Decimal(0), pis_cofins_extra=Decimal(0), sobra_difal=Decimal(0),
        iteracoes=k["iteracoes"], valor_produtos=P, frete_nf=F, despesas_acessorias_nf=M,
        multiplicador=1 / (1 - k["carga"]), carga=k["carga"],
        resultado_estimado=res,
        sp_capital_absorvido=k["sem_cobranca"], uso_consumo=bool(r0.get("uso_consumo")),
        diluido_frete=dil_f, diluido_montagem=dil_m,
        dividido=True, sem_divisao=sem, carga_servico=carga_s,
    )
    return r
