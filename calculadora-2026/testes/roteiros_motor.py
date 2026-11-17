"""Bateria de roteiros no motor (sem interface): invariantes contábeis e fiscais."""
import sys, os, itertools, random, traceback, json
APP = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
sys.path.insert(0, APP); os.chdir(APP)
from decimal import Decimal as D
import calculo, calculo_2027, descontos, comum

CFG = calculo.carregar_config()
CFG27 = calculo_2027.carregar_config()
COM = descontos.carregar_config()
CONDS = {c["codigo"]: c for c in descontos.condicoes_ativas(COM)}
LIM = COM["limites_politica"]
C = D("0.01")
falhas, n = [], [0]


def falha(tag, msg):
    falhas.append(f"[{tag}] {msg}")


def simular(ano="2026", estado="Rio De Janeiro", cidade="Capital", contrib=calculo.NAO_CONTRIBUINTE,
            finalidade=None, total=80000, cond=105, equipe="Equipe Interna", modo="percentual",
            pol=35, alvo=None, excs=(), ipis=(), frete="Calcular", mont="Calcular", fneg=0, mneg=0,
            km=30, dil_f=False, dil_m=False, dividir=False, divisao=None):
    motor, cfg = (calculo, CFG) if ano == "2026" else (calculo_2027, CFG27)
    sp_cap = estado == "São Paulo" and cidade == "Capital"
    e = dict(estado=estado, cidade=cidade, horario="Fora do comercial" if sp_cap else None,
             contribuinte=contrib, finalidade=finalidade if contrib == calculo.CONTRIBUINTE else None,
             frete_opcao=frete, montagem_opcao=mont, frete_negociado=fneg, montagem_negociada=mneg,
             km_ida_volta=0 if sp_cap else km, frete_aplicacao=calculo.PEDIDO, montagem_aplicacao=calculo.PEDIDO,
             diluir_frete=dil_f and frete != "Não contratar", diluir_montagem=dil_m and mont != "Não contratar")
    _, _, cond_pct = descontos.percentual_aplicado(CONDS[cond], COM)
    faixas = descontos.tabela_comissao(COM, equipe, divisao)
    lim = LIM[equipe] if not faixas else min(float(LIM[equipe]), float(faixas[-1][0]))
    pol_, r, aviso = descontos.resolver(e, cfg, motor, total, cond_pct, lim, modo, politica=pol, alvo=alvo,
                                         excecoes=[(v, p) for _, v, p in excs],
                                         ipi_itens=list(ipis), nomes_excecoes=[x for x, _, _ in excs])
    pol_comp = 0 if excs else pol_
    r.update(total_tabela=D(str(total)), cond_pct=cond_pct, politica_pct=pol_,
             erp=descontos.lancamentos_erp(r, pol_comp, COM))
    if dividir:
        r["divisao"] = descontos.dividir(r, COM, r["ipi_pct"], pol_comp)
    if faixas:
        r["comissao"] = descontos.comissao_estimada(faixas, total, cond_pct, pol_, [(v, p) for _, v, p in excs])
    return e, r, aviso, lim


def checar(tag, ano="2026", **kw):
    n[0] += 1
    try:
        e, r, aviso, lim = simular(ano=ano, **kw)
    except Exception as ex:
        falha(tag, "EXCEÇÃO " + repr(ex) + " " + traceback.format_exc().splitlines()[-3])
        return None
    sem_ie = e["contribuinte"] == calculo.NAO_CONTRIBUINTE
    P, E, F, M = r["valor_produtos"], r["difal_fcp_embutido"], r["frete_final"], r["montagem_final"]
    extra = (r.get("cbs", 0) + r.get("ibs", 0)) if ano == "2027" else 0
    # 1. composição do total
    if abs(P + E + F + M + r["ipi"] + extra - r["total_nf"]) > C:
        falha(tag, f"total ≠ itens+embutido+frete+montagem+IPI ({P+E+F+M+r['ipi']+extra} vs {r['total_nf']})")
    # 2. IPI sobre a base
    if abs((P + E + F + M) * r["ipi_pct"] / 100 - r["ipi"]) > C:
        falha(tag, f"IPI {r['ipi']} ≠ base×{r['ipi_pct']}%")
    # 3. embutido cobre as guias (2026)
    if ano == "2026" and abs(r["sobra_difal"]) > C:
        falha(tag, f"sobra DIFAL {r['sobra_difal']}")
    uf = CFG["estados"][e["estado"]]
    if ano == "2026" and sem_ie:
        g = r["total_nf"] * D(str(uf["difal"] + uf["fcp"])) / 100
        if abs(g - r["difal"] - r["fcp"]) > C:
            falha(tag, f"guias {r['difal']+r['fcp']} ≠ alíquota×NF {g}")
    if not sem_ie and E and not r.get("uso_consumo") and ano == "2026":
        falha(tag, f"contribuinte com embutido {E}")
    # 4. resultado frete/montagem (margem 0 → ~0)
    if ano == "2026" and not r["sp_capital_absorvido"] and abs(r["resultado_estimado"]) > C:
        falha(tag, f"resultado frete/montagem {r['resultado_estimado']} (esperado 0)")
    # 5. SP Capital: nada cobrado
    if e["estado"] == "São Paulo" and e["cidade"] == "Capital" and (F or M):
        falha(tag, f"SP Capital cobrando frete {F} / montagem {M}")
    # 6. não negativos
    for c in ("valor_produtos", "frete_final", "montagem_final", "ipi", "total_nf", "difal_fcp_embutido"):
        if r[c] < 0:
            falha(tag, f"{c} negativo {r[c]}")
    # 7. convergência
    if r.get("iteracoes", 1) >= 200:
        falha(tag, "não convergiu (200 iterações)")
    # 8. identidade Focco (Totais)
    erp = r["erp"]
    cond_val = r["total_tabela"] * r["cond_pct"] / 100
    valor_pol = r["total_tabela"] + cond_val - P
    desc_t = (-cond_val if cond_val < 0 else 0) + valor_pol
    frete_campo = 0 if erp["frete_diluido"] else erp["frete"]
    acr = (cond_val if cond_val > 0 else 0) + erp["montagem"] + erp["difal"] + erp["fcp"] + \
        (erp["frete"] if erp["frete_diluido"] else 0)
    foc = r["total_tabela"] - desc_t + acr + frete_campo + r["ipi"] + extra
    if abs(foc - r["total_nf"]) > C:
        falha(tag, f"Totais Focco {foc:.2f} ≠ Valor Total {r['total_nf']:.2f}")
    if abs(erp["difal"] + erp["fcp"] - E) > C:
        falha(tag, f"lançamento DIFAL+FCP {erp['difal']+erp['fcp']} ≠ embutido {E}")
    # 9. frete pelo mínimo / Salis
    if kw.get("frete", "Calcular") == "Calcular" and e["estado"] != "São Paulo" and ano == "2026":
        pc = uf["salis_capital" if e["cidade"] == "Capital" else "salis_interior"]
        if pc is None:
            if not r["aviso"]:
                falha(tag, "UF sem Salis sem aviso")
        else:
            esp = max(r["valor_itens_nf"], D(30000)) * D(str(pc)) / 100
            if abs(esp - r["frete_custo"]) > C:
                falha(tag, f"custo frete {r['frete_custo']:.2f} ≠ {esp:.2f}")
    # 10. montagem
    if kw.get("mont", "Calcular") == "Calcular" and ano == "2026":
        km = 0 if (e["estado"] == "São Paulo" and e["cidade"] == "Capital") else D(str(kw.get("km", 30)))
        esp = r["valor_itens_nf"] * D("0.035") + km * D("3.5")
        if abs(esp - r["montagem_custo"]) > C:
            falha(tag, f"custo montagem {r['montagem_custo']:.2f} ≠ {esp:.2f}")
    # 11. política dentro do limite
    if r["politica_pct"] > D(str(lim)) + D("0.0000001"):
        if not aviso:
            falha(tag, f"política {r['politica_pct']} acima do limite {lim} sem aviso")
    # 12. modo valor final
    if kw.get("modo") == "valor_final":
        alvo = D(str(kw["alvo"]))
        if aviso is None and abs(r["total_nf"] - alvo) > C:
            falha(tag, f"valor final {r['total_nf']:.2f} ≠ alvo {alvo}")
        if aviso and "menor Valor Total" in aviso and r["total_nf"] <= alvo:
            falha(tag, "aviso de inviável mas total ≤ alvo")
    # 13. divisão
    dv = r.get("divisao")
    if dv:
        if abs(dv["servico"] - r["total_nf"] * D("0.4")) > C:
            falha(tag, "serviço ≠ 40%")
        if abs(dv["total_produtos"] - dv["produtos"]) > C:
            falha(tag, f"pedido de produtos {dv['total_produtos']:.2f} ≠ {dv['produtos']:.2f}")
        if dv["negativo"] != (dv["reducao_liquida"] < 0):
            falha(tag, "flag negativo inconsistente")
    return e, r, aviso


UFS = list(CFG["estados"])
roteiros = []
# A. todas as UFs × capital/interior × contribuinte/não × finalidade (108+ roteiros)
for uf in UFS:
    for cid in ("Capital", "Interior"):
        for ct, fin in ((calculo.NAO_CONTRIBUINTE, None), (calculo.CONTRIBUINTE, "Revenda / industrialização"),
                        (calculo.CONTRIBUINTE, calculo.CONSUMIDOR_FINAL)):
            roteiros.append((f"UF {uf}/{cid}/{ct[:4]}/{(fin or '')[:6]}", dict(estado=uf, cidade=cid, contrib=ct, finalidade=fin)))
# B. frete/montagem: calcular, negociado, não contratar × diluído
opts = ["Calcular", "Informar valor negociado", "Não contratar"]
for fo, mo, df, dm in itertools.product(opts, opts, (False, True), (False, True)):
    roteiros.append((f"FM {fo[:4]}/{mo[:4]}/dilF{int(df)}/dilM{int(dm)}",
                     dict(frete=fo, mont=mo, fneg=3500, mneg=8500, dil_f=df, dil_m=dm)))
# C. condições (todas)
for c in CONDS:
    roteiros.append((f"COND {c}", dict(cond=c)))
# D. política: 0, limite de cada equipe, acima do limite
for eq, lim in LIM.items():
    for p in (0, 10, lim, lim + 1):
        roteiros.append((f"POL {eq} {p}", dict(equipe=eq, pol=p)))
# E. valor final: viável, igual ao total sem desconto, acima, inviável, com frete/montagem negociados
for alvo in (67451.55, 48000, 80000, 120000, 30000, 1, 95000.37):
    roteiros.append((f"ALVO {alvo}", dict(modo="valor_final", alvo=alvo)))
    roteiros.append((f"ALVO {alvo} neg+dil", dict(modo="valor_final", alvo=alvo, frete="Informar valor negociado",
                                                fneg=2000, mont="Informar valor negociado", mneg=8500, dil_m=True)))
    roteiros.append((f"ALVO {alvo} SPcap", dict(modo="valor_final", alvo=alvo, estado="São Paulo", cidade="Capital")))
# F. exceções e IPI por item
roteiros += [
    ("EXC 1 item", dict(excs=[("A", 10000, 45)])),
    ("EXC 2 itens", dict(excs=[("A", 10000, 45), ("B", 5000, 0)])),
    ("EXC = total", dict(excs=[("A", 80000, 20)])),
    ("EXC valor final", dict(modo="valor_final", alvo=60000, excs=[("A", 10000, 40)])),
    ("IPI 5%", dict(ipis=[("PLUG", 2000, 5)])),
    ("IPI 0%", dict(ipis=[("X", 80000, 0)])),
    ("IPI 6.5 + exc mesmo nome", dict(excs=[("PLUG", 2000, 10)], ipis=[("PLUG", 2000, 6.5)])),
    ("IPI 15% valor final", dict(modo="valor_final", alvo=60000, ipis=[("Y", 40000, 15)])),
    ("IPI nome caixa diferente", dict(excs=[("Plug ", 2000, 10)], ipis=[("plug", 2000, 6.5)])),
]
# G. divisão
for p in (0, 20, 35, 45):
    for fo in ("Calcular", "Não contratar"):
        roteiros.append((f"DIV pol {p} frete {fo[:4]}", dict(dividir=True, pol=p, frete=fo)))
roteiros.append(("DIV contribuinte", dict(dividir=True, contrib=calculo.CONTRIBUINTE, finalidade="Revenda / industrialização")))
roteiros.append(("DIV SP cap", dict(dividir=True, estado="São Paulo", cidade="Capital")))
roteiros.append(("DIV pedido pequeno", dict(dividir=True, total=1000, pol=0)))
roteiros.append(("DIV frete dil", dict(dividir=True, dil_f=True, dil_m=True)))
# H. comissão
for dvs in COM["comissao"]["divisoes"]:
    for p in (0, 15, 16, 30, 31, 40, 45):
        roteiros.append((f"COM {dvs} {p}", dict(divisao=dvs, pol=p)))
# I. extremos
roteiros += [
    ("EXT total 0,01", dict(total=0.01, pol=0)),
    ("EXT total 1", dict(total=1)),
    ("EXT total 29.999", dict(total=29999, pol=0)),
    ("EXT total 30.000", dict(total=30000, pol=0)),
    ("EXT 50 milhões", dict(total=50_000_000)),
    ("EXT km 0", dict(km=0)),
    ("EXT km 10.000", dict(km=10000)),
    ("EXT negociado 1 centavo", dict(frete="Informar valor negociado", fneg=0.01, mont="Informar valor negociado", mneg=0.01)),
    ("EXT negociado > pedido", dict(total=1000, frete="Informar valor negociado", fneg=50000)),
    ("EXT política 100", dict(equipe="Equipe PJ", pol=100)),
    ("EXT política negativa", dict(pol=-5)),
    ("EXT Roraima sem Salis", dict(estado="Roraima", cidade="Capital")),
    ("EXT DF interior sem Salis", dict(estado="DF", cidade="Interior")),
    ("EXT SP interior abaixo mínimo", dict(estado="São Paulo", cidade="Interior", total=5000, pol=0)),
    ("EXT SP capital dil", dict(estado="São Paulo", cidade="Capital", dil_f=True, dil_m=True)),
]
# J. 2027 (mesmos casos principais)
for uf in ("Rio De Janeiro", "São Paulo", "Bahia", "Roraima"):
    for ct in (calculo.NAO_CONTRIBUINTE, calculo.CONTRIBUINTE):
        roteiros.append((f"2027 {uf} {ct[:4]}", dict(ano="2027", estado=uf, contrib=ct, finalidade="Revenda / industrialização")))
roteiros.append(("2027 valor final", dict(ano="2027", modo="valor_final", alvo=60000)))
roteiros.append(("2027 dil", dict(ano="2027", dil_f=True, dil_m=True)))
# K. aleatórios
random.seed(7)
for i in range(150):
    kw = dict(estado=random.choice(UFS), cidade=random.choice(["Capital", "Interior"]),
              contrib=random.choice([calculo.NAO_CONTRIBUINTE, calculo.CONTRIBUINTE]),
              finalidade=random.choice(["Revenda / industrialização", calculo.CONSUMIDOR_FINAL]),
              total=round(random.uniform(500, 2_000_000), 2), cond=random.choice(list(CONDS)),
              equipe=random.choice(list(LIM)), frete=random.choice(opts), mont=random.choice(opts),
              fneg=round(random.uniform(1, 20000), 2), mneg=round(random.uniform(1, 20000), 2),
              km=random.randint(0, 3000), dil_f=random.random() < .4, dil_m=random.random() < .4,
              dividir=random.random() < .3)
    if random.random() < .5:
        kw.update(modo="valor_final", alvo=round(kw["total"] * random.uniform(.4, 1.3), 2))
    else:
        kw.update(pol=round(random.uniform(0, LIM[kw["equipe"]]), 4))
    roteiros.append((f"RND{i}", kw))

for tag, kw in roteiros:
    checar(tag, **kw)

# L. monotonicidade: política maior → total menor
for uf in ("Rio De Janeiro", "Bahia", "São Paulo"):
    prev = None
    for p in range(0, 46, 5):
        r = simular(estado=uf, pol=p)[1]["total_nf"]
        n[0] += 1
        if prev is not None and r >= prev:
            falha(f"MONO {uf}", f"total não cai de {p-5}% para {p}% ({prev} → {r})")
        prev = r

# M. leitura de números colados
casos_num = {"42.671,46": 42671.46, "42671,46": 42671.46, "42671.46": 42671.46, "R$ 42.671,46": 42671.46,
             "1.234.567": 1234567, "18,8532": 18.8532, "1,234,567.89": 1234567.89, "1.000": 1000,
             "0.500": 0.5, "100": 100, "-5": -5, "abc": None, "": None, "12,5%": 12.5, " 3 500,00 ": 3500.0,
             "1.5": 1.5, "48.000,02": 48000.02, "R$ 1.360,00": 1360.0, "2,": 2.0, ",5": 0.5,
             "1.234": 1234, "1.23": 1.23, "1.2345": 1.2345, "10.000.00": None, "1,5,6": None, "1.234.567,89": 1234567.89, "1,234.56": 1234.56, "1.23.456": None, "12.34,5": None, "0,0000001": 1e-7}
for txt, esp in casos_num.items():
    n[0] += 1
    v = comum.numero_br(txt)
    if (v is None) != (esp is None) or (v is not None and abs(v - esp) > 1e-9):
        falha("NUM", f"numero_br({txt!r}) = {v}, esperado {esp}")


# N. Venda assistida Cavaletti (bloqueada para vendedores, testada mesmo assim)
import cavaletti
CCAV = cavaletti.carregar_config()
for ano in ("2026", "2027"):
    cfgc = json.loads(json.dumps(CCAV))
    if cfgc["2027"].get("cbs") is None:
        cfgc["2027"]["cbs"] = 8.8
    for share in (50, 60, 70, 80, 85, 100):
        for rt in (0, 5, 10, 15, 20):
            for desc in (0, 5):
                n[0] += 1
                tag = f"CAV {ano} share{share} rt{rt} desc{desc}"
                itens = [dict(descricao="Cadeira", custo=1000, ipi=3.25, entrega=50, qtd=10),
                         dict(descricao="Mesa", custo=2500.5, ipi=0, entrega=0, qtd=1)]
                try:
                    rc = cavaletti.calcular(dict(itens=itens, share_produto=share, desconto_avista=desc, rt=rt), cfgc, ano)
                except Exception as ex:
                    falha(tag, repr(ex)); continue
                if abs(rc["nf_produto"] + rc["nf_servico"] + rc["cbs"] + rc["ibs"] - rc["total_cliente"]) > C:
                    falha(tag, "total cliente ≠ NF produto + NF serviço")
                if abs(rc["nf_produto"] / rc["total"] - D(share) / 100) > D("0.000001"):
                    falha(tag, "participação da NF de produto errada")
                if abs(rc["nf_servico"] - rc["rt"] - rc["impostos"] - rc["liquido"]) > C:
                    falha(tag, "líquido ≠ serviço − RT − impostos")
                srv = 100 - share
                esp_max = max([f["rt_maximo"] for f in CCAV["tabela_rt"] if srv >= f["servico_minimo"]] or [0])
                if rc["rt_acima"] != (rt > esp_max):
                    falha(tag, f"RT acima={rc['rt_acima']} mas máximo {esp_max}%")
                if rc["liquido"] < 0 and not rc["rt_acima"]:
                    falha(tag, f"líquido negativo {rc['liquido']:.2f} com RT dentro do permitido")

print(f"{n[0]} roteiros no motor; {len(falhas)} falhas")
for f in falhas:
    print(" ", f)
