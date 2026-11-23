# servicos.py
# Integrações externas. Credenciais vêm de st.secrets (Streamlit Cloud: Settings › Secrets).
# Sem credenciais, a calculadora continua funcionando e oferece downloads de reserva.

import base64
import mimetypes
import csv
import io
import re
import json
import os
from urllib.parse import quote

import requests

TIMEOUT = 20
GRAPH = "https://graph.microsoft.com/v1.0"


def _secao(st, nome):
    try:
        return dict(st.secrets[nome])
    except Exception:
        return None


def senha_adm(st):
    try:
        return st.secrets["ADM_SENHA"]
    except Exception:
        return None


def token_cnpja(st):
    s = _secao(st, "cnpja")
    return (s or {}).get("token") or None


# ------------------------------------------------------------------
# Distância de rodovia (OpenRouteService) para a montagem
# [rotas] ors_key = "..."   (chave gratuita em openrouteservice.org)
# ------------------------------------------------------------------
ORIGEM_FABRICA = "Avenida Henrique Gonçalves Baptista, 2035, Jardim Belval, Barueri, SP, 06420-130, Brasil"
ORS = "https://api.openrouteservice.org"


UF_SIGLAS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins"}

# complementos que confundem o mapa (sala, apto, conjunto...) ficam de fora da busca
_COMPLEMENTO = re.compile(r"^\s*(sala|salas|sl|apto|apt|ap|apartamento|conj|conjunto|cj|bloco|bl|andar|loja|lj|"
                          r"galp[aã]o|box|casa|fundos|frente|lote|lt|quadra|qd|km|torre|unidade|un|edif[ií]cio|"
                          r"ed|pr[eé]dio|pavimento|pav|lado|anexo|n[ºo°]?\s*$)", re.I)


def _sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").lower().strip()


def _partes_endereco(destino):
    """Do texto 'Rua X, 123, Sala 4, Bairro · Cidade/UF · CEP 00000-000' tira
    (logradouro e número, cidade, UF, CEP). Complemento e bairro ficam de fora."""
    t = (destino or "").replace("\n", " ")
    cep = re.search(r"(\d{5})-?(\d{3})", t)
    cep = f"{cep.group(1)}-{cep.group(2)}" if cep else ""
    cid = re.search(r"([A-Za-zÀ-ÿ'´`.\- ]+?)\s*[/\-]\s*([A-Za-z]{2})\b(?![A-Za-z])", t.split("·", 1)[1] if "·" in t else t)
    cidade, uf = (cid.group(1).strip(" ,-"), cid.group(2).upper()) if cid else ("", "")
    if uf not in UF_SIGLAS:
        cidade, uf = "", ""
    rua = t.split("·")[0]
    pedacos = [p.strip() for p in rua.split(",") if p.strip()]
    logradouro = pedacos[0] if pedacos else ""
    numero = ""
    if len(pedacos) > 1 and re.match(r"^(n[ºo°.]?\s*)?\d+[a-zA-Z]?$", pedacos[1], re.I):
        numero = re.sub(r"^n[ºo°.]?\s*", "", pedacos[1], flags=re.I)
    return (f"{logradouro} {numero}".strip() if logradouro and not _COMPLEMENTO.match(logradouro) else ""), \
        cidade, uf, cep


def _confere_uf(props, uf):
    if not uf:
        return True
    if (props.get("region_a") or "").upper() == uf:
        return True
    return _sem_acento(props.get("region")) == _sem_acento(UF_SIGLAS[uf])


def _ors_coord(chave, texto, uf="", estruturado=None):
    """Coordenadas do primeiro resultado no Brasil (e na UF, quando informada)."""
    if estruturado:
        params = dict(estruturado, api_key=chave, country="BR", size=5)
        url = f"{ORS}/geocode/search/structured"
    else:
        params = {"api_key": chave, "text": texto, "boundary.country": "BR", "size": 5}
        url = f"{ORS}/geocode/search"
    r = requests.get(url, timeout=TIMEOUT, params=params)
    if r.status_code != 200:
        return None, f"localização indisponível ({r.status_code})"
    for f in r.json().get("features") or []:
        props = f.get("properties", {})
        if _confere_uf(props, uf):
            lon, lat = f["geometry"]["coordinates"][:2]
            return (lon, lat), props.get("label", "")
    return None, "endereço não encontrado no mapa" + (f" em {uf}" if uf else "")


def _coord_por_cep(cep, uf):
    """Coordenadas do CEP pela BrasilAPI (CEP v2). Só vale se o CEP for da UF do cliente."""
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cep/v2/{re.sub(r'[^0-9]', '', cep)}", timeout=TIMEOUT)
        if r.status_code != 200:
            return None, ""
        j = r.json()
        if uf and (j.get("state") or "").upper() != uf:
            return None, ""
        c = ((j.get("location") or {}).get("coordinates") or {})
        lon, lat = c.get("longitude"), c.get("latitude")
        if not lon or not lat:
            return None, ""
        rotulo = ", ".join(x for x in (j.get("street"), j.get("neighborhood"), j.get("city"), j.get("state")) if x)
        return (float(lon), float(lat)), f"{rotulo} (CEP {cep})"
    except (requests.RequestException, ValueError, TypeError):
        return None, ""


def _localizar_destino(chave, destino):
    """Tenta do mais preciso ao menos preciso, sempre conferindo a UF do resultado:
    rua + número na cidade → texto limpo → CEP → centro da cidade (aproximado)."""
    rua, cidade, uf, cep = _partes_endereco(destino)
    estado = UF_SIGLAS.get(uf, "")
    if cep:
        coord, rotulo = _coord_por_cep(cep, uf)       # 1º: pelo CEP (BrasilAPI)
        if coord:
            return coord, rotulo
    tentativas = []
    if rua and cidade:
        tentativas.append(("", dict(address=rua, locality=cidade, region=estado,
                                    **({"postalcode": cep} if cep else {})), ""))
        tentativas.append((f"{rua}, {cidade}, {uf}, Brasil", None, ""))
    if cep:
        tentativas.append(("", dict(postalcode=cep, **({"locality": cidade} if cidade else {})), " (pelo CEP)"))
    if cidade:
        tentativas.append((f"{cidade}, {estado}, Brasil", None, " (centro da cidade: aproximado)"))
    if not tentativas:
        tentativas.append((destino.replace("·", ","), None, ""))
    ultimo = "endereço não encontrado no mapa"
    for texto, estr, obs in tentativas:
        coord, rotulo = _ors_coord(chave, texto, uf, estr)
        if coord:
            return coord, rotulo + obs
        ultimo = rotulo
    return None, ultimo


def distancia_km(st, destino):
    """Distância de rodovia ida e volta (km) da fábrica em Barueri até o destino.
    Retorna (km_ida_e_volta ou None, mensagem)."""
    chave = (_secao(st, "rotas") or {}).get("ors_key")
    if not chave:
        return None, "Cálculo de km não configurado (Secrets [rotas] ors_key). Informe os km manualmente."
    if not (destino or "").strip():
        return None, "Sem endereço do cliente: consulte o CNPJ ou informe o endereço de entrega."
    try:
        origem, _ = _ors_coord(chave, ORIGEM_FABRICA, "SP")
        if not origem:
            return None, "Não foi possível localizar a fábrica no mapa. Informe os km manualmente."
        dest, rotulo = _localizar_destino(chave, destino)
        if not dest:
            return None, f"Destino: {rotulo}. Informe os km manualmente."
        r = requests.post(f"{ORS}/v2/directions/driving-car", timeout=TIMEOUT,
                          headers={"Authorization": chave, "Content-Type": "application/json"},
                          json={"coordinates": [list(origem), list(dest)]})
        if r.status_code != 200:
            return None, f"Rota indisponível ({r.status_code}). Informe os km manualmente."
        metros = r.json()["routes"][0]["summary"]["distance"]
        ida = metros / 1000
        trecho = f"{ida:,.0f}".replace(",", ".")
        return float(round(ida * 2)), f"Rota Barueri → {rotulo}: {trecho} km por trecho"
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        return None, f"Falha no cálculo de km ({exc.__class__.__name__}). Informe os km manualmente."


# ------------------------------------------------------------------
# Parâmetros: gravar o config.json no GitHub
# [github] token, repo, branch, path
# ------------------------------------------------------------------
ARQUIVOS_CONFIG = ("config.json", "config_2027.json", "config_comercial.json", "config_cavaletti.json")
PASTA_APP = os.path.dirname(os.path.abspath(__file__))


CONFIG_REPO_PADRAO = "JehFreitas/calculadora-minimal-config"


def _destino_config(gh):
    """Onde ficam os parâmetros. Com [github] config_repo: num repositório PRIVADO só de parâmetros
    (raiz do repositório). Sem ele: no próprio repositório do app (modo antigo)."""
    if gh.get("config_repo") or gh.get("token"):
        return gh.get("config_repo") or CONFIG_REPO_PADRAO, gh.get("config_branch", "main"), ""
    pasta = gh.get("pasta") or os.path.dirname(gh.get("path", "calculadora-2026/config.json"))
    return gh["repo"], gh.get("branch", "main"), pasta


def carregar_configs_privados(st):
    """Baixa os parâmetros do repositório privado (secrets [github] token + config_repo) para a
    pasta do app, uma vez por processo. Os arquivos não ficam no repositório público.
    Retorna (ok, mensagem)."""
    gh = _secao(st, "github") or {}
    faltam = [a for a in ARQUIVOS_CONFIG if not os.path.exists(os.path.join(PASTA_APP, a))]
    if not (gh.get("config_repo") or gh.get("token")):
        if faltam:
            return False, ("Parâmetros não encontrados: configure [github] token e config_repo "
                           "nos Secrets do Streamlit.")
        return True, "Parâmetros locais."
    if getattr(carregar_configs_privados, "_feito", False) and not faltam:
        return True, "Parâmetros já carregados."
    repo, branch, _ = _destino_config(gh)
    headers = {"Authorization": f"Bearer {gh.get('token', '')}",
               "Accept": "application/vnd.github.raw+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    erros = []
    for arq in ARQUIVOS_CONFIG:
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}/contents/{quote(arq)}",
                             headers=headers, params={"ref": branch}, timeout=TIMEOUT)
            if r.status_code != 200:
                erros.append(f"{arq} ({r.status_code})")
                continue
            json.loads(r.text)                                   # confere que é JSON válido
            with open(os.path.join(PASTA_APP, arq), "w", encoding="utf-8") as f:
                f.write(r.text)
        except (requests.RequestException, ValueError, OSError) as exc:
            erros.append(f"{arq} ({exc.__class__.__name__})")
    ainda_faltam = [a for a in ARQUIVOS_CONFIG if not os.path.exists(os.path.join(PASTA_APP, a))]
    carregar_configs_privados._feito = not ainda_faltam
    if ainda_faltam:
        return False, "Não foi possível carregar os parâmetros: " + ", ".join(erros or ainda_faltam) + "."
    return True, ("Parâmetros carregados." if not erros else
                  "Parâmetros carregados (alguns da cópia anterior): " + ", ".join(erros) + ".")


def salvar_config_github(st, cfg, arquivo="config.json", autor="Tela de Parâmetros (Adm)"):
    gh = _secao(st, "github")
    if not gh or not gh.get("token") or not (gh.get("repo") or gh.get("config_repo")):
        return False, "Integração com o GitHub não configurada (secrets [github])."
    repo, branch, pasta = _destino_config(gh)
    path = f"{pasta}/{arquivo}" if pasta else arquivo
    url = f"https://api.github.com/repos/{repo}/contents/{quote(path)}"
    headers = {"Authorization": f"Bearer {gh['token']}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        atual = requests.get(url, headers=headers, params={"ref": branch}, timeout=TIMEOUT)
        sha = atual.json().get("sha") if atual.status_code == 200 else None
        conteudo = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
        corpo = {"message": f"Atualiza parâmetros da calculadora ({autor})",
                 "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
                 "branch": branch}
        if sha:
            corpo["sha"] = sha
        resp = requests.put(url, headers=headers, json=corpo, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            return True, f"Parâmetros gravados no GitHub ({repo}, branch {branch})."
        return False, f"GitHub recusou a gravação ({resp.status_code})."
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o GitHub: {exc}"


# ------------------------------------------------------------------
# Microsoft 365 (planilha no SharePoint e e-mail)
# [microsoft] tenant_id, client_id, client_secret
# [sharepoint] drive_id (ou site_hostname + site_path), file_path
# [email] remetente, destinatarios (lista)
# ------------------------------------------------------------------
def _token_microsoft(st):
    ms = _secao(st, "microsoft")
    if ms:
        ms = {k: (str(v).strip() if isinstance(v, str) else v) for k, v in ms.items()}
        # tenant_id e client_id são GUIDs: aproveita só o GUID, mesmo se vier com
        # caracteres invisíveis, aspas tipográficas ou texto a mais copiado do e-mail.
        for chave in ("tenant_id", "client_id"):
            achado = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                               str(ms.get(chave) or ""))
            if achado:
                ms[chave] = achado.group(0)
    if not ms or any(not ms.get(k) for k in ("tenant_id", "client_id", "client_secret")):
        return None, "Aplicativo Microsoft 365 ainda não configurado (secrets [microsoft])."
    try:
        r = requests.post(
            f"https://login.microsoftonline.com/{ms['tenant_id']}/oauth2/v2.0/token",
            data={"client_id": ms["client_id"], "client_secret": ms["client_secret"],
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"},
            timeout=TIMEOUT)
        if r.status_code != 200:
            try:
                j = r.json()
            except ValueError:
                j = {}
            codigos = j.get("error_codes") or []
            dicas = {
                7000215: "o client_secret não confere: cole o VALOR do segredo (não o ID do segredo).",
                7000222: "o client_secret expirou: peça um novo ao TI.",
                700016: "o client_id não foi encontrado neste tenant: confira o client_id.",
                90002: "o tenant_id não foi encontrado: confira o tenant_id.",
                900023: "o tenant_id está em formato inválido: confira o tenant_id.",
                7000216: "faltou o client_secret.",
            }
            dica = next((dicas[c] for c in codigos if c in dicas), None)
            detalhe = dica or (j.get("error_description", "") or "").split("\r\n")[0][:200]
            return None, (f"Microsoft recusou o login do aplicativo ({r.status_code}"
                          + (f", AADSTS{codigos[0]}" if codigos else "") + f"): {detalhe}")
        return r.json()["access_token"], None
    except requests.RequestException as exc:
        return None, f"Falha de conexão com a Microsoft: {exc}"


COLUNAS_NFE = [
    "Data/hora do envio", "Cálculo", "Data da simulação", "Vendedor", "Cliente", "CNPJ",
    "Razão social (consulta)", "Orçamento", "Nº do pedido",
    "Origem UF/cidade", "Origem contribuinte", "Data/hora da consulta", "Fonte da consulta",
    "Simples Nacional", "SUFRAMA",
    "UF", "Localização", "Contribuinte", "Finalidade", "Frete aplicado",
    "Valor dos produtos", "A pagar à transportadora", "A pagar à montadora",
    "Frete cobrado", "Montagem cobrada", "DIFAL/FCP embutido", "Despesas acessórias",
    "Guia DIFAL", "Guia FCP", "IPI", "CBS", "IBS", "Valor dos itens na NF", "Total da NF",
    "Resultado frete/montagem",
    "Total Itens (tabela)", "Condição de pagamento", "% condição", "Equipe", "Modo da política",
    "% política", "Valor final desejado",
    "Divisão produto/serviço", "Pedido de serviço", "Desconto aos itens (produtos)", "Total pedido de produtos",
    "Itens com desconto diferente", "Divisão de venda", "Faixa de comissão (%)",
    "% RT", "Base comissão/RT (valor líquido)", "RT do arquiteto", "Comissão estimada",
]

COLUNAS_VA = [
    "Data/hora do envio", "Cálculo", "Data da simulação", "Vendedor", "Cliente", "CNPJ",
    "Orçamento", "Nº do pedido", "Arquiteto (RT)", "Itens", "Quantidade total",
    "Desconto à vista (%)", "% NF de produto", "% NF de serviço",
    "NF de produto (Cavaletti)", "IPI na NF de produto", "NF de serviço (Minimal)",
    "CBS", "IBS", "Total do pedido", "% RT", "RT do arquiteto",
    "ISS", "PIS/COFINS", "Valor líquido dos serviços", "Comissão do vendedor",
    "Comissionamento empresa",
]

TABELAS = {"nfe": ("Simulacoes", COLUNAS_NFE), "va": ("VendaAssistida", COLUNAS_VA)}


def linha_csv(valores, tipo="nfe"):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(TABELAS[tipo][1])
    w.writerow(valores)
    return buf.getvalue().encode("utf-8-sig")


def _localizar_planilha(sp, h):
    """
    Retorna (url_do_drive, id_do_arquivo, erro).
    [sharepoint] drive_id + file_path, ou
                 site_hostname + site_path + file_path. Neste caso, se o primeiro
                 trecho de file_path for o nome de uma biblioteca do site
                 (ex.: "Comercial/Calculadora/arquivo.xlsx"), usa essa biblioteca.
    """
    caminho = sp["file_path"].strip("/")
    if sp.get("drive_id"):
        drives = [(f"{GRAPH}/drives/{sp['drive_id']}", caminho)]
    else:
        host = sp["site_hostname"]
        path = "/" + sp["site_path"].strip("/")
        site = requests.get(f"{GRAPH}/sites/{host}:{path}", headers=h, timeout=TIMEOUT)
        if site.status_code != 200:
            return None, None, f"Site do SharePoint não encontrado ({site.status_code})."
        sid = site.json()["id"]
        drives = []
        primeiro, _, resto = caminho.partition("/")
        lista = requests.get(f"{GRAPH}/sites/{sid}/drives", headers=h, timeout=TIMEOUT)
        if lista.status_code == 200 and resto:
            for dr in lista.json().get("value", []):
                if dr.get("name", "").lower() == primeiro.lower():
                    drives.append((f"{GRAPH}/drives/{dr['id']}", resto))
        drives.append((f"{GRAPH}/sites/{sid}/drive", caminho))
    ultimo = None
    for drive, rel in drives:
        arq = requests.get(f"{drive}/root:/{quote(rel)}", headers=h, timeout=TIMEOUT)
        if arq.status_code == 200:
            return drive, arq.json()["id"], None
        ultimo = arq.status_code
    # Não achou no caminho: procura o arquivo pelo nome nas bibliotecas do site.
    nome = caminho.rsplit("/", 1)[-1]
    if not sp.get("drive_id"):
        bibliotecas, achados = [], []
        if lista.status_code == 200:
            for dr in lista.json().get("value", []):
                bibliotecas.append(dr.get("name", ""))
                busca = requests.get(f"{GRAPH}/drives/{dr['id']}/root/search(q='{quote(nome.rsplit('.', 1)[0])}')",
                                     headers=h, timeout=TIMEOUT)
                if busca.status_code != 200:
                    continue
                for it in busca.json().get("value", []):
                    if it.get("name", "").lower() == nome.lower() and "file" in it:
                        pasta = (it.get("parentReference", {}).get("path", "").split("root:", 1)[-1]).strip("/")
                        achados.append((f"{GRAPH}/drives/{dr['id']}", it["id"],
                                        "/".join(x for x in (dr.get("name", ""), pasta, nome) if x)))
        if len(achados) == 1:
            return achados[0][0], achados[0][1], None
        if len(achados) > 1:
            return None, None, ("Há mais de uma planilha com esse nome no site: "
                                + "; ".join(a[2] for a in achados) + ". Ajuste file_path nos Secrets.")
        return None, None, (f"Planilha não encontrada ({ultimo}): o arquivo \"{nome}\" não está no site. "
                            f"Bibliotecas do site: {', '.join(bibliotecas) or '—'}. "
                            "Suba o modelo na pasta Calculadora ou ajuste file_path nos Secrets.")
    return None, None, f"Planilha não encontrada ({ultimo}). Confira file_path nos Secrets."


def _config_sharepoint(st):
    sp = _secao(st, "sharepoint") or {}
    if sp.get("site") and not sp.get("site_hostname"):          # formato "host:/sites/Nome"
        host, _, path = sp["site"].partition(":")
        sp["site_hostname"], sp["site_path"] = host, path
    if not sp.get("file_path") or not (sp.get("drive_id") or (sp.get("site_hostname") and sp.get("site_path"))):
        return None
    return sp


def registrar_planilha(st, valores, token=None, tipo="nfe"):
    sp = _config_sharepoint(st)
    if not sp:
        return False, "Planilha ainda não configurada (secrets [sharepoint])."
    if token is None:
        token, erro = _token_microsoft(st)
        if not token:
            return False, erro
    h = {"Authorization": f"Bearer {token}"}
    try:
        drive, item, erro = _localizar_planilha(sp, h)
        if erro:
            return False, erro
        tabela = sp.get(f"tabela_{tipo}") or TABELAS[tipo][0]
        base = f"{drive}/items/{item}/workbook/tables/{tabela}"
        # Monta a linha pela ordem das colunas da tabela na planilha: colunas novas da
        # calculadora que ainda não existem na planilha são ignoradas, e colunas extras
        # da planilha ficam em branco.
        por_nome = dict(zip(TABELAS[tipo][1], valores))
        col = requests.get(f"{base}/columns?$select=name", headers=h, timeout=TIMEOUT)
        if col.status_code == 200:
            nomes = [c.get("name") for c in col.json().get("value", [])]
            valores = [por_nome.get(nm, "") for nm in nomes]
        add = requests.post(f"{base}/rows/add", headers=h, json={"values": [valores]}, timeout=TIMEOUT)
        if add.status_code in (200, 201):
            return True, "Simulação salva na planilha."
        return False, f"Não foi possível incluir a linha na planilha ({add.status_code}): {add.text[:150]}"
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o SharePoint: {exc}"


def criar_planilha(st):
    """Sobe o modelo da planilha para o caminho de file_path no SharePoint (cria as pastas que
    faltarem). Não substitui: se a planilha já existir, não faz nada. Retorna (ok, mensagem)."""
    sp = _config_sharepoint(st)
    if not sp:
        return False, "Planilha não configurada (secrets [sharepoint])."
    token, erro = _token_microsoft(st)
    if not token:
        return False, erro
    h = {"Authorization": f"Bearer {token}"}
    try:
        drive, item, erro = _localizar_planilha(sp, h)
        if item:
            return False, "A planilha já existe no SharePoint. Nada foi alterado."
        caminho = sp["file_path"].strip("/")
        if sp.get("drive_id"):
            alvo, rel = f"{GRAPH}/drives/{sp['drive_id']}", caminho
        else:
            site = requests.get(f"{GRAPH}/sites/{sp['site_hostname']}:/{sp['site_path'].strip('/')}",
                                headers=h, timeout=TIMEOUT)
            if site.status_code != 200:
                return False, f"Site do SharePoint não encontrado ({site.status_code})."
            sid = site.json()["id"]
            alvo, rel = f"{GRAPH}/sites/{sid}/drive", caminho
            primeiro, _, resto = caminho.partition("/")
            lista = requests.get(f"{GRAPH}/sites/{sid}/drives", headers=h, timeout=TIMEOUT)
            if lista.status_code == 200 and resto:
                for dr in lista.json().get("value", []):
                    if dr.get("name", "").lower() == primeiro.lower():
                        alvo, rel = f"{GRAPH}/drives/{dr['id']}", resto
        modelo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos",
                              "Controle de Simulações - Calculadora Comercial.xlsx")
        with open(modelo, "rb") as f:
            conteudo = f.read()
        up = requests.put(f"{alvo}/root:/{quote(rel)}:/content?@microsoft.graph.conflictBehavior=fail",
                          headers=dict(h, **{"Content-Type": "application/octet-stream"}),
                          data=conteudo, timeout=60)
        if up.status_code in (200, 201):
            return True, f"Planilha criada no SharePoint em {caminho}."
        return False, f"Não foi possível criar a planilha ({up.status_code}): {up.text[:150]}"
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o SharePoint: {exc}"


def testar_integracao(st):
    """Verificação sem gravar nada: login do aplicativo, planilha e tabelas. Lista de (ok, mensagem)."""
    res = []
    token, erro = _token_microsoft(st)
    if not token:
        return [(False, erro)]
    res.append((True, "Login do aplicativo no Microsoft 365: ok."))
    sp = _config_sharepoint(st)
    if not sp:
        res.append((False, "Planilha não configurada (secrets [sharepoint])."))
    else:
        h = {"Authorization": f"Bearer {token}"}
        try:
            drive, item, erro = _localizar_planilha(sp, h)
            if erro:
                res.append((False, erro))
            else:
                info = requests.get(f"{drive}/items/{item}?$select=webUrl,parentReference,name",
                                    headers=h, timeout=TIMEOUT)
                url = info.json().get("webUrl", "") if info.status_code == 200 else ""
                pasta = (info.json().get("parentReference", {}).get("path", "").split("root:", 1)[-1].strip("/")
                         if info.status_code == 200 else "")
                res.append((True, "Planilha encontrada" + (f" na pasta \"{pasta}\"" if pasta else "")
                            + (f": [abrir no SharePoint]({url})" if url else ".")))
                t = requests.get(f"{drive}/items/{item}/workbook/tables", headers=h, timeout=TIMEOUT)
                nomes = [x.get("name") for x in t.json().get("value", [])] if t.status_code == 200 else []
                for tipo, (padrao, _) in TABELAS.items():
                    nome = sp.get(f"tabela_{tipo}") or padrao
                    if nome not in nomes:
                        res.append((False, f"Tabela {nome}: não encontrada."))
                        continue
                    col = requests.get(f"{drive}/items/{item}/workbook/tables/{nome}/columns?$select=name",
                                       headers=h, timeout=TIMEOUT)
                    tem = [c.get("name") for c in col.json().get("value", [])] if col.status_code == 200 else []
                    faltam = [c for c in TABELAS[tipo][1] if c not in tem]
                    res.append((not faltam, f"Tabela {nome}: " + ("ok." if not faltam else
                                "faltam as colunas " + ", ".join(faltam) + " (atualize pelo modelo).")))
        except requests.RequestException as exc:
            res.append((False, f"Falha de conexão com o SharePoint: {exc}"))
    em = _secao(st, "email")
    res.append((bool(em and em.get("remetente") and em.get("destinatarios")),
                "E-mail: " + (f"remetente {em['remetente']}." if em and em.get("remetente") else "não configurado (secrets [email]).")))
    return res


def enviar_email(st, assunto, corpo_html, anexos, token=None, destinatarios=None):
    """anexos: lista de (nome_arquivo, bytes)."""
    em = _secao(st, "email")
    if em and destinatarios:
        em["destinatarios"] = destinatarios
    if not em or not em.get("remetente") or not em.get("destinatarios"):
        return False, "Envio de e-mail ainda não configurado (secrets [email])."
    if token is None:
        token, erro = _token_microsoft(st)
        if not token:
            return False, erro
    dest = em["destinatarios"]
    if isinstance(dest, str):
        dest = [x.strip() for x in dest.split(",") if x.strip()]
    msg = {
        "message": {
            "subject": assunto,
            "body": {"contentType": "HTML", "content": corpo_html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in dest],
            "attachments": [
                {"@odata.type": "#microsoft.graph.fileAttachment", "name": nome,
                 "contentType": mimetypes.guess_type(nome)[0] or "application/octet-stream",
                 "contentBytes": base64.b64encode(conteudo).decode("ascii")}
                for nome, conteudo in anexos
            ],
        },
        "saveToSentItems": True,
    }
    try:
        r = requests.post(f"{GRAPH}/users/{quote(em['remetente'])}/sendMail",
                          headers={"Authorization": f"Bearer {token}"}, json=msg, timeout=TIMEOUT)
        if r.status_code == 202:
            return True, "E-mail enviado ao ADM Comercial."
        try:
            erro = r.json().get("error", {})
        except ValueError:
            erro = {}
        cod, txt = erro.get("code", ""), (erro.get("message", "") or "")[:200]
        if r.status_code in (502, 503, 504):
            dica = "Serviço da Microsoft indisponível no momento. Tente de novo em alguns minutos."
        elif r.status_code == 403:
            dica = "Sem permissão para enviar por esta caixa: confira com o TI a permissão Mail.Send e a caixa autorizada."
        elif r.status_code == 404:
            dica = "Caixa remetente não encontrada: confira [email] remetente nos Secrets."
        else:
            dica = txt
        return False, f"Não foi possível enviar o e-mail ({r.status_code}{', ' + cod if cod else ''}). {dica}"
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o e-mail: {exc}"


def registro_json(valores, tipo="nfe"):
    """Anexo com a linha da planilha (nome das colunas + valores), para um fluxo do Power
    Automate gravar numa planilha do Excel sem acesso da calculadora ao SharePoint."""
    tabela, colunas = TABELAS[tipo]
    return json.dumps({"tabela": tabela, "colunas": list(colunas),
                       "linha": [v if isinstance(v, (int, float)) else ("" if v is None else str(v))
                                 for v in valores]}, ensure_ascii=False).encode("utf-8")


def _planilha_por_email(st):
    return bool((_secao(st, "sharepoint") or {}).get("registro_por_email"))


def enviar_e_salvar(st, valores, assunto, corpo_html, anexos, tipo="nfe"):
    """Faz as duas etapas; retorna (ok_planilha, msg_planilha, ok_email, msg_email).
    O e-mail leva sempre o anexo registro_simulacao.json. Com [sharepoint] registro_por_email = true,
    a calculadora não grava no SharePoint: quem grava a linha é o fluxo do Power Automate."""
    token, erro = _token_microsoft(st)
    if not token:
        return False, erro, False, erro
    anexos = list(anexos) + [("registro_simulacao.json", registro_json(valores, tipo))]
    if _planilha_por_email(st):
        ok_e, msg_e = enviar_email(st, assunto, corpo_html, anexos, token)
        return ok_e, ("Registro enviado junto com o e-mail para a planilha do ADM." if ok_e
                      else "Registro não enviado: o e-mail falhou."), ok_e, msg_e
    ok_p, msg_p = registrar_planilha(st, valores, token, tipo)
    ok_e, msg_e = enviar_email(st, assunto, corpo_html, anexos, token)
    return ok_p, msg_p, ok_e, msg_e
