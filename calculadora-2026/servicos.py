# servicos.py
# Integrações externas. Credenciais vêm de st.secrets (Streamlit Cloud: Settings › Secrets).
# Sem credenciais, a calculadora continua funcionando e oferece downloads de reserva.

import base64
import csv
import io
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
# Parâmetros: gravar o config.json no GitHub
# [github] token, repo, branch, path
# ------------------------------------------------------------------
def salvar_config_github(st, cfg, arquivo="config.json", autor="Tela de Parâmetros (Adm)"):
    gh = _secao(st, "github")
    if not gh or not gh.get("token") or not gh.get("repo"):
        return False, "Integração com o GitHub não configurada (secrets [github])."
    repo = gh["repo"]
    branch = gh.get("branch", "main")
    pasta = gh.get("pasta") or os.path.dirname(gh.get("path", "calculadora-2026/config.json"))
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
                res.append((True, "Planilha encontrada."))
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
                 "contentType": "application/pdf",
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
        return False, f"Não foi possível enviar o e-mail ({r.status_code})."
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o e-mail: {exc}"


def enviar_e_salvar(st, valores, assunto, corpo_html, anexos, tipo="nfe"):
    """Faz as duas etapas; retorna (ok_planilha, msg_planilha, ok_email, msg_email)."""
    token, erro = _token_microsoft(st)
    if not token:
        return False, erro, False, erro
    ok_p, msg_p = registrar_planilha(st, valores, token, tipo)
    ok_e, msg_e = enviar_email(st, assunto, corpo_html, anexos, token)
    return ok_p, msg_p, ok_e, msg_e
