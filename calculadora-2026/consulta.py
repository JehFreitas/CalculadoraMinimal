# consulta.py
# Consulta de dados do cliente pelo CNPJ.
#
# Ordem das fontes:
#   1. CNPJá API comercial (se houver token em st.secrets["cnpja"]["token"]):
#      traz também a inscrição estadual → indica contribuinte do ICMS.
#   2. CNPJá API pública (gratuita, sem IE).
#   3. BrasilAPI (gratuita, sem IE) — reserva se a CNPJá falhar.

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TIMEOUT = 15

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "DF", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio De Janeiro", "RN": "Rio Grande Do Norte", "RS": "Rio Grande Do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}

CAPITAIS = {
    "AC": "Rio Branco", "AL": "Maceió", "AP": "Macapá", "AM": "Manaus", "BA": "Salvador",
    "CE": "Fortaleza", "DF": "Brasília", "ES": "Vitória", "GO": "Goiânia", "MA": "São Luís",
    "MT": "Cuiabá", "MS": "Campo Grande", "MG": "Belo Horizonte", "PA": "Belém",
    "PB": "João Pessoa", "PR": "Curitiba", "PE": "Recife", "PI": "Teresina",
    "RJ": "Rio de Janeiro", "RN": "Natal", "RS": "Porto Alegre", "RO": "Porto Velho",
    "RR": "Boa Vista", "SC": "Florianópolis", "SP": "São Paulo", "SE": "Aracaju",
    "TO": "Palmas",
}

LINK_CCC = "https://dfe-portal.svrs.rs.gov.br/NFE/CCC"
LINK_SINTEGRA = "http://www.sintegra.gov.br/"


def so_digitos(cnpj):
    return re.sub(r"\D", "", cnpj or "")


def cnpj_valido(cnpj):
    c = so_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    def dv(base, pesos):
        s = sum(int(x) * p for x, p in zip(base, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    return c[12] == dv(c[:12], p1) and c[13] == dv(c[:13], p2)


def formatar_cnpj(cnpj):
    c = so_digitos(cnpj)
    if len(c) != 14:
        return cnpj or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def _normalizar(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def capital_ou_interior(uf, cidade):
    if uf == "DF":
        return "Capital"
    cap = CAPITAIS.get(uf)
    if not cap or not cidade:
        return None
    return "Capital" if _normalizar(cidade) == _normalizar(cap) else "Interior"


def _agora():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")


def _de_cnpja(j, fonte, com_ie):
    comp = j.get("company") or {}
    end = j.get("address") or {}
    uf = (end.get("state") or "").upper()
    cidade = end.get("city") or ""
    simples = (comp.get("simples") or {}).get("optant")
    simei = (comp.get("simei") or {}).get("optant")
    status = (j.get("status") or {}).get("text") or ""

    suframa = None
    sf = j.get("suframa")
    if isinstance(sf, list):
        suframa = any((s.get("approved") is not False) and
                      "cancel" not in str((s.get("status") or {}).get("text", "")).lower()
                      for s in sf) if sf else False

    ie = None
    ie_txt = ""
    if com_ie and isinstance(j.get("registrations"), list):
        regs = [r for r in j["registrations"] if (r.get("state") or "").upper() == uf] or j["registrations"]
        ativas = [r for r in regs if r.get("enabled")]
        ie = bool(ativas)
        if ativas:
            ie_txt = ", ".join(f"{r.get('number')} ({r.get('state')})" for r in ativas)
        elif regs:
            ie_txt = "IE não habilitada: " + ", ".join(
                f"{r.get('number')} ({(r.get('status') or {}).get('text', '')})" for r in regs)
        else:
            ie_txt = "Sem inscrição estadual"

    return dict(
        ok=bool(uf), fonte=fonte, data_hora=_agora(),
        razao_social=comp.get("name") or "", situacao=status,
        uf=uf, estado=UF_NOME.get(uf), municipio=cidade,
        cidade=capital_ou_interior(uf, cidade),
        simples=("MEI" if simei else ("Sim" if simples else ("Não" if simples is not None else ""))),
        suframa=suframa, contribuinte_ie=ie, ie_texto=ie_txt,
    )


def _de_brasilapi(j):
    uf = (j.get("uf") or "").upper()
    cidade = j.get("municipio") or ""
    simples = j.get("opcao_pelo_simples")
    mei = j.get("opcao_pelo_mei")
    return dict(
        ok=bool(uf), fonte="BrasilAPI (gratuita)", data_hora=_agora(),
        razao_social=j.get("razao_social") or "", situacao=j.get("descricao_situacao_cadastral") or "",
        uf=uf, estado=UF_NOME.get(uf), municipio=cidade.title(),
        cidade=capital_ou_interior(uf, cidade),
        simples=("MEI" if mei else ("Sim" if simples else ("Não" if simples is not None else ""))),
        suframa=None, contribuinte_ie=None, ie_texto="",
    )


def consultar(cnpj, token=None):
    """Retorna um dicionário com os dados encontrados, ou {'ok': False, 'erro': ...}."""
    c = so_digitos(cnpj)
    if not cnpj_valido(c):
        return dict(ok=False, erro="CNPJ inválido. Confira os 14 dígitos.")

    erros = []
    if token:
        try:
            r = requests.get(
                f"https://api.cnpja.com/office/{c}",
                params={"simples": "true", "registrations": "BR", "suframa": "true", "maxAge": 30},
                headers={"Authorization": token}, timeout=TIMEOUT)
            if r.status_code == 200:
                dados = _de_cnpja(r.json(), "CNPJá (comercial)", com_ie=True)
                if dados["ok"]:
                    return dados
            erros.append(f"CNPJá comercial: {r.status_code}")
        except (requests.RequestException, ValueError) as exc:
            erros.append(f"CNPJá comercial: {exc}")

    try:
        r = requests.get(f"https://open.cnpja.com/office/{c}", timeout=TIMEOUT)
        if r.status_code == 200:
            dados = _de_cnpja(r.json(), "CNPJá (gratuita)", com_ie=False)
            if dados["ok"]:
                return dados
        erros.append(f"CNPJá pública: {r.status_code}")
    except (requests.RequestException, ValueError) as exc:
        erros.append(f"CNPJá pública: {exc}")

    try:
        r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{c}", timeout=TIMEOUT)
        if r.status_code == 200:
            dados = _de_brasilapi(r.json())
            if dados["ok"]:
                return dados
        erros.append(f"BrasilAPI: {r.status_code}")
    except (requests.RequestException, ValueError) as exc:
        erros.append(f"BrasilAPI: {exc}")

    return dict(ok=False, erro="Não foi possível consultar o CNPJ agora. Preencha os dados manualmente.",
                detalhe="; ".join(erros))
