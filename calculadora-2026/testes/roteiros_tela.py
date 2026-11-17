"""Roteiros na interface (Streamlit AppTest) com consulta de CNPJ e rota simuladas."""
import sys, os, glob, traceback
APP = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
OUT = "/tmp/roteiros_tela"
os.makedirs(OUT, exist_ok=True)
for f in glob.glob(OUT + "/*.pdf"):
    os.remove(f)
sys.path.insert(0, APP); os.chdir(APP)
from streamlit.testing.v1 import AppTest
import consulta


def cnpj(base12):
    def dv(nums, pesos):
        s = sum(int(a) * b for a, b in zip(nums, pesos)) % 11
        return "0" if s < 2 else str(11 - s)
    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


C_RS, C_ALERTA, C_FALHA, C_SEMEND, C_ENTREGA, C_INATIVA = (cnpj(x) for x in (
    "926656110001", "111111110001", "222222220001", "333333330001", "444444440001", "555555550001"))

WRAP = OUT + "/wrap_ui.py"
open(WRAP, "w").write(f'''
import sys, os
sys.path.insert(0, "{APP}"); os.chdir("{APP}")
import comum, consulta, servicos
if not getattr(comum, "_patched", False):
    _o = comum.gerar_pdf
    def g(*a, **kw):
        b = _o(*a, **kw)
        nome = "adm" if kw.get("senha") else "vendedor"
        open("{OUT}/" + os.environ.get("TAG","x") + "_" + nome + ".pdf", "wb").write(b)
        return b
    comum.gerar_pdf = g; comum._patched = True
    def fake(c, token=None):
        c = consulta.so_digitos(c)
        base = dict(ok=True, fonte="teste", data_hora="17/11/2026 10:00", cnae="2110600", cnae_texto="Fab",
                    cnae_alerta=None, razao_social="CLIENTE RS", situacao="Ativa", uf="RS",
                    estado="Rio Grande Do Sul", municipio="Porto Alegre", cidade="Capital", simples="Não",
                    suframa=False, contribuinte_ie=True, ie_texto="096 (RS)",
                    endereco="Avenida do Lami, 6133 · Porto Alegre/RS")
        if c == "{C_ALERTA}":
            base.update(razao_social="CONSTRUTORA", cnae="4120400", cnae_alerta="41 – Construção de edifícios",
                        estado="Rio De Janeiro", uf="RJ", municipio="Rio de Janeiro",
                        endereco="Rua X, 1 · Rio de Janeiro/RJ")
        elif c == "{C_FALHA}":
            return dict(ok=False, erro="Consulta indisponível.")
        elif c == "{C_SEMEND}":
            base.update(endereco="", contribuinte_ie=None, ie_texto="")
        elif c == "{C_ENTREGA}":
            base.update(razao_social="FILIAL CAMPINAS", estado="São Paulo", uf="SP", municipio="Campinas",
                        cidade="Interior", endereco="Rua Filial, 100 · Campinas/SP")
        elif c == "{C_INATIVA}":
            base.update(situacao="Baixada")
        return base
    consulta.consultar = fake
    def rota(st, d):
        if os.environ.get("ROTA") == "falha":
            return None, "Não foi possível calcular a rota."
        return (2247.0 if "Porto Alegre" in d else 190.0 if "Campinas" in d else 60.0), "Rota até " + d
    servicos.distancia_km = rota
    def envio(st, valores, assunto, corpo, anexos, tipo="nfe"):
        for nome, b in anexos:
            open("{OUT}/" + os.environ.get("TAG","x") + "_anexo_" + nome.replace("/", "_"), "wb").write(b)
        return True, "ok", True, "ok"
    servicos.enviar_e_salvar = envio
exec(open("{APP}/app.py").read())
''')

P = "nfe2026_"
falhas, total = [], [0]


def textos(at):
    out = []
    for grupo in (at.markdown, at.caption, at.warning, at.error, at.info, at.success):
        out += [str(x.value) for x in grupo]
    return "\n".join(out)


def nova(adm=False, rota="ok", tag="x"):
    os.environ["TAG"], os.environ["ROTA"] = tag, rota
    at = AppTest.from_file(WRAP, default_timeout=90)
    at.secrets["ADM_SENHA"] = "x"
    at.run()
    if adm:
        at.session_state["adm_ok"] = True
        at.run()
    return at


BASE = dict(vendedor="Vendedor Teste", cliente="Cliente", orcamento="9999", estado="Rio De Janeiro",
            cidade="Capital", contribuinte=consulta and "Não contribuinte (mesmo com IE)", total_tabela=80000.0,
            condicao=105, equipe="Equipe Interna", modo_pol="Informar o % da política", politica=35.0,
            frete_opcao="Calcular", montagem_opcao="Calcular", km_ida_volta=30.0)


def preencher(at, **v):
    dados = dict(BASE); dados.update(v)
    for kk, vv in dados.items():
        if vv is None:
            continue
        at.session_state[P + kk] = vv
        at.run()       # um por vez: campos dependentes só aparecem depois do anterior
    return at


def calcular(at):
    at.button(key=P + "calcular").click().run()
    return at


def caso(nome, fn):
    total[0] += 1
    try:
        msg = fn()
        if msg:
            falhas.append(f"[{nome}] {msg}")
    except Exception as ex:
        falhas.append(f"[{nome}] EXCEÇÃO {ex!r} {traceback.format_exc().splitlines()[-3:]}")


def exc(at):
    return "; ".join(e.message for e in at.exception)


def ok_calc(at, tag, adm=False):
    if at.exception:
        return "exceção: " + exc(at)
    if at.error:
        return "erro inesperado: " + " | ".join(e.value for e in at.error)
    if P + "sim" not in at.session_state:
        return "sem resultado"
    if not os.path.exists(f"{OUT}/{tag}_vendedor.pdf"):
        return "PDF do vendedor não gerado"
    if adm:
        bt = [b for b in at.button if str(b.key).startswith("enviar_")]
        if not bt:
            return "sem botão de envio"
        bt[0].click().run()
        if at.exception:
            return "exceção no envio: " + exc(at)
        if not os.path.exists(f"{OUT}/{tag}_adm.pdf"):
            return "PDF do ADM não gerado no envio"
        if not glob.glob(f"{OUT}/{tag}_anexo_ADM_*.pdf"):
            return "PDF do ADM não anexado"
    return None


def r(at):
    return at.session_state[P + "sim"]["r"]


# ---------------- roteiros ----------------
def u01():
    at = calcular(nova())
    t = " ".join(e.value for e in at.error)
    for c in ("Estado de destino", "Cidade de destino", "Contribuinte", "Total Itens", "Condição de pagamento",
              "Equipe", "Desconto da política", "Frete", "Montagem"):
        if c not in t:
            return f"campo obrigatório não listado: {c} (erro: {t[:200]})"


def u02():
    at = calcular(preencher(nova(tag="u02"), ))
    m = ok_calc(at, "u02", adm=True)
    if m: return m
    if abs(float(r(at)["total_nf"]) - 67451.55) > 0.01:
        return f"total {r(at)['total_nf']} ≠ 67.451,55"
    if "Visível só com a Área restrita" in textos(at):
        return "bloco do ADM aparece para vendedor"


def u03():
    at = calcular(preencher(nova(adm=True, tag="u03")))
    return ok_calc(at, "u03", adm=True)


def u04():
    at = calcular(preencher(nova(tag="u04"), dividir=True))
    m = ok_calc(at, "u04")
    if m: return m
    if "Visível só com a Área restrita" in textos(at) or "SERVIÇO" in " ".join(x.value for x in at.markdown if "Desconto SERVIÇO" in x.value):
        return "divisão (ADM) visível ao vendedor"


def u05():
    at = calcular(preencher(nova(adm=True, tag="u05"), dividir=True))
    m = ok_calc(at, "u05", adm=True)
    if m: return m
    if "Visível só com a Área restrita" not in textos(at):
        return "divisão não aparece para o ADM"


def u06():
    at = calcular(preencher(nova(), politica=50.0))
    if not any("limite" in e.value for e in at.error):
        return "política 50% na Equipe Interna não bloqueada"


def u07():
    at = calcular(preencher(nova(tag="u07"), modo_pol="Informar o valor final desejado", politica=None, alvo=60000.0))
    m = ok_calc(at, "u07")
    if m: return m
    if abs(float(r(at)["total_nf"]) - 60000) > 0.01:
        return f"valor final {r(at)['total_nf']} ≠ 60.000"


def u08():
    at = calcular(preencher(nova(tag="u08"), modo_pol="Informar o valor final desejado", politica=None, alvo=20000.0))
    if "menor Valor Total" not in textos(at):
        return "alvo inviável sem aviso do menor Valor Total"


def u09():
    at = calcular(preencher(nova(tag="u09"), modo_pol="Informar o valor final desejado", politica=None, alvo=200000.0))
    if "maior que o total sem desconto" not in textos(at):
        return "alvo acima do total sem aviso"


def u10():
    at = calcular(preencher(nova(), modo_pol="Escolher a comissão desejada", politica=None))
    if not any("Divisão de venda" in e.value for e in at.error):
        return "comissão sem divisão de venda não bloqueada"


def u11():
    at = preencher(nova(tag="u11"), modo_pol="Escolher a comissão desejada", politica=None, divisao_venda="Sem RT", faixa=2)
    at = calcular(at)
    m = ok_calc(at, "u11")
    if m: return m
    if float(r(at)["politica_pct"]) != 30:
        return f"faixa 3 (até 30%) deu política {r(at)['politica_pct']}"


def u12():
    at = calcular(preencher(nova(), frete_opcao="Informar valor negociado", montagem_opcao="Informar valor negociado"))
    t = " ".join(e.value for e in at.error)
    for c in ("Valor negociado do frete", "Print da cotação do frete", "Valor negociado da montagem",
              "Print da cotação da montagem"):
        if c not in t:
            return f"faltou exigir: {c}"


def u13():
    at = calcular(preencher(nova(tag="u13"), estado="São Paulo", cidade="Capital", km_ida_volta=None))
    m = ok_calc(at, "u13")
    if m: return m
    if r(at)["frete_final"] or r(at)["montagem_final"]:
        return "SP Capital cobrando frete/montagem"


def u14():
    at = preencher(nova(), cidade="Interior")
    at.session_state[P + "km_ida_volta"] = None
    at.run()
    at = calcular(at)
    if not any("Distância" in e.value for e in at.error):
        return "km vazio sem bloqueio"


def com_cnpj(at, c):
    at.text_input(key=P + "cnpj").set_value(c).run()
    at.button(key=P + "btn_cnpj").click().run()
    return at


def u15():
    at = com_cnpj(nova(tag="u15"), C_RS)
    preencher(at, estado=None, cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    at = calcular(at)
    if not any("Confirmação do endereço" in e.value for e in at.error):
        return "não exigiu confirmar o endereço"
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    ni = at.number_input(key=P + "km_ida_volta")
    if not ni.disabled or ni.value != 2247:
        return f"km não travado/calculado (disabled={ni.disabled}, valor={ni.value})"
    at = calcular(at)
    m = ok_calc(at, "u15", adm=True)
    if m: return m
    if at.session_state[P + "estado"] != "Rio Grande Do Sul":
        return "UF não veio da consulta"


def u16():
    at = com_cnpj(nova(tag="u16"), C_RS)
    preencher(at, estado=None, cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    opts = at.radio(key=P + "end_confirma").options
    at.radio(key=P + "end_confirma").set_value(opts[1]).run()
    at = calcular(at)
    t = " ".join(e.value for e in at.error)
    if "CNPJ do local de entrega" not in t:
        return "não exigiu CNPJ de entrega"
    at.text_input(key=P + "cnpj_entrega").set_value(C_ENTREGA).run()
    at.button(key=P + "btn_cnpj_entrega").click().run()
    if at.session_state[P + "estado"] != "São Paulo" or at.session_state[P + "cidade"] != "Interior":
        return "destino não seguiu a entrega"
    ni = at.number_input(key=P + "km_ida_volta")
    if not ni.disabled or ni.value != 190:
        return f"km da entrega não recalculado (disabled={ni.disabled}, valor={ni.value})"
    at = calcular(at)
    return ok_calc(at, "u16", adm=True)


def u17():
    at = preencher(nova(), total_tabela=None)
    for txt, esp in (("80000.00", 80000), ("80.000,00", 80000), ("R$ 80.000,00", 80000), ("80000,5", 80000.5)):
        at.text_input(key=P + "total_tabela_txt").set_value(txt).run()
        if at.session_state[P + "total_tabela"] != esp:
            return f"colar {txt!r} → {at.session_state[P + 'total_tabela']}"
        if "não reconhecido" in textos(at):
            return f"colar {txt!r} mostrou 'não reconhecido'"
    at.text_input(key=P + "total_tabela_txt").set_value("abc").run()
    if "não reconhecido" not in textos(at):
        return "texto inválido sem aviso"
    at = calcular(at)
    if not any("Total Itens" in e.value for e in at.error):
        return "Total Itens inválido não bloqueou"


def u18():
    at = preencher(nova(), politica=None)
    for txt, esp in (("18.8532", 18.8532), ("13,5141318", 13.5141318), ("35", 35.0), ("4,8636185", 4.8636185)):
        at.text_input(key=P + "politica_txt").set_value(txt).run()
        v = at.session_state[P + "politica"]
        if v is None or abs(v - esp) > 1e-9:
            return f"política {txt!r} → {v}"
    at.text_input(key=P + "politica_txt").set_value("101").run()
    if "não reconhecido" not in textos(at):
        return "política 101% aceita sem aviso"


def u19():
    at = calcular(preencher(nova(tag="u19")))
    at.session_state[P + "politica"] = 30.0
    at.run()
    if not at.warning or not any("mudaram" in w.value for w in at.warning):
        return "resultado não marcado como desatualizado após mudar a política"


def u20():
    at = calcular(preencher(nova(), contribuinte="Contribuinte do ICMS"))
    if not any("Finalidade" in e.value for e in at.error):
        return "finalidade não exigida"


def u21():
    at = com_cnpj(nova(rota="falha", tag="u21"), C_RS)
    preencher(at, estado=None, cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    ni = at.number_input(key=P + "km_ida_volta")
    if ni.disabled:
        return "rota falhou mas o km ficou travado"
    if not any(b.key == P + "btn_km" for b in at.button):
        return "sem botão para tentar de novo"
    ni.set_value(500.0).run()
    at = calcular(at)
    return ok_calc(at, "u21")


def u22():
    at = com_cnpj(nova(), C_ALERTA)
    if at.session_state[P + "contribuinte"] is not None:
        return "CNAE de alerta com IE marcou contribuinte automaticamente"
    if "Financeiro" not in textos(at) or "CCC" not in textos(at):
        return "alerta sem Financeiro/CCC"


def u23():
    at = com_cnpj(nova(tag="u23"), C_FALHA)
    if "Consulta indisponível" not in textos(at):
        return "falha da consulta sem aviso"
    at = calcular(preencher(at))
    return ok_calc(at, "u23")


def u24():
    at = calcular(preencher(nova(adm=True, tag="u24"), lanc_frete="Diluído aos itens", lanc_montagem="Diluído aos itens"))
    m = ok_calc(at, "u24", adm=True)
    if m: return m
    erp = r(at)["erp"]
    if not (erp["frete_diluido"] and erp["montagem_diluida"]):
        return "diluição não aplicada"


def u25():
    at = calcular(preencher(nova(tag="u25"), estado="Roraima"))
    if "Salis não atende" not in textos(at):
        return "Roraima sem aviso de Salis"


def u26():
    at = com_cnpj(nova(tag="u26"), C_SEMEND)
    if any(x.key == P + "end_confirma" for x in at.radio):
        return "pediu confirmação sem endereço"
    if "CCC" not in textos(at):
        return "IE ausente sem link do CCC"
    at = calcular(preencher(at))
    return ok_calc(at, "u26")


def u27():
    at = com_cnpj(nova(), C_INATIVA)
    if "Baixada" not in textos(at):
        return "situação inativa sem aviso"


def u28():
    # Montagem 'Calcular' com CNPJ, mas depois trocar para negociado: km não deve ser exigido
    at = com_cnpj(nova(), C_RS)
    preencher(at, estado=None, cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None, montagem_opcao="Não contratar")
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    at = calcular(at)
    if any("Distância" in e.value for e in at.error):
        return "km exigido sem montagem"


def u29():
    # Trocar o CNPJ depois de calcular: a consulta antiga não pode valer para o novo
    at = com_cnpj(nova(), C_RS)
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    at.text_input(key=P + "cnpj").set_value(C_ENTREGA).run()
    if "CLIENTE RS" in textos(at):
        return "dados do CNPJ anterior continuam na tela"


def u30():
    # Página 2027 para vendedor: bloqueada se não estiver pronta
    at = nova()
    at.switch_page("app.py") if False else None
    return None


def u30():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    at = nova()
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    if at.session_state[P + "data"] != hoje:
        return f"Data {at.session_state[P + 'data']} ≠ hoje em Brasília {hoje}"


def u31():
    import subprocess
    at = calcular(preencher(nova(tag="u31"), politica=None, lanc_frete="Diluído aos itens"))
    at.text_input(key=P + "politica_txt").set_value("13,5141318").run()
    at = calcular(at)
    m = ok_calc(at, "u31")
    if m: return m
    t = subprocess.run(["pdftotext", "-layout", f"{OUT}/u31_vendedor.pdf", "-"], capture_output=True, text=True).stdout
    if "13,5141318%" not in t:
        return "política com 7 casas não aparece no PDF"
    if "0000%" in t:
        return "PDF com zeros à direita no percentual"
    if "FRETE - DILUIDO AOS ITENS" not in t:
        return "frete diluído fora do quadro do Focco"
    if abs(float(r(at)["politica_pct"]) - 13.5141318) > 1e-9:
        return "política perdeu casas"


def u32():
    at = com_cnpj(nova(), C_RS)
    preencher(at, estado=None, cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    at.radio(key=P + "montagem_opcao").set_value("Não contratar").run()
    at.radio(key=P + "montagem_opcao").set_value("Calcular").run()
    ni = at.number_input(key=P + "km_ida_volta")
    if not ni.disabled or ni.value != 2247:
        return f"km perdeu a trava ao trocar a montagem (disabled={ni.disabled}, valor={ni.value})"


def u33():
    # vendedor troca a UF manualmente depois de confirmar o endereço: deve bloquear
    at = com_cnpj(nova(tag="u33"), C_RS)
    preencher(at, estado="Bahia", cidade=None, contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    if not any("diferente do endereço de entrega" in e.value for e in at.error):
        return "UF diferente do endereço sem aviso"
    at = calcular(at)
    if P + "sim" in at.session_state or not any("igual ao do endereço" in e.value for e in at.error):
        return "UF diferente do endereço não bloqueou o cálculo"
    at.session_state[P + "estado"] = "Rio Grande Do Sul"; at.run()
    at = calcular(at)
    return ok_calc(at, "u33")


def u34():
    at = com_cnpj(nova(tag="u34"), C_RS)
    preencher(at, estado=None, cidade="Interior", contribuinte="Contribuinte do ICMS", finalidade="Representantes",
              km_ida_volta=None)
    at.radio(key=P + "end_confirma").set_value("Sim, entrega e faturamento neste endereço").run()
    if not any("foi marcado Interior" in w.value for w in at.warning):
        return "cidade diferente da consulta sem aviso"
    at = calcular(at)
    if P + "sim" not in at.session_state:
        return "cidade diferente bloqueou (deveria só avisar)"


CASOS = [(f"U{i:02d}", f) for i, f in enumerate([u01, u02, u03, u04, u05, u06, u07, u08, u09, u10, u11, u12, u13,
                                                  u14, u15, u16, u17, u18, u19, u20, u21, u22, u23, u24, u25, u26,
                                                  u27, u28, u29, u30, u31, u32, u33, u34], 1)]
only = sys.argv[1:] or None
for nome, fn in CASOS:
    if only and nome not in only:
        continue
    caso(nome, fn)
    print(nome, "ok" if not falhas or not falhas[-1].startswith(f"[{nome}]") else falhas[-1], flush=True)
print(f"\n{total[0]} roteiros na interface; {len(falhas)} falhas")
for f in falhas:
    print(" ", f)
