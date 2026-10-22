# servicos.py
# Integrações externas. Credenciais vêm de st.secrets (Streamlit Cloud: Settings › Secrets).
# Sem credenciais, a calculadora continua funcionando e oferece downloads de reserva.

import base64
import csv
import io
import json
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
def salvar_config_github(st, cfg, autor="Tela de Parâmetros (Adm)"):
    gh = _secao(st, "github")
    if not gh or not gh.get("token") or not gh.get("repo"):
        return False, "Integração com o GitHub não configurada (secrets [github])."
    repo = gh["repo"]
    branch = gh.get("branch", "main")
    path = gh.get("path", "calculadora-2026/config.json")
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
# [sharepoint] site_hostname, site_path, file_path, table_name
# [email] remetente, destinatarios (lista)
# ------------------------------------------------------------------
def _token_microsoft(st):
    ms = _secao(st, "microsoft")
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
            return None, f"Microsoft recusou o login do aplicativo ({r.status_code})."
        return r.json()["access_token"], None
    except requests.RequestException as exc:
        return None, f"Falha de conexão com a Microsoft: {exc}"


COLUNAS = [
    "Data/hora do envio", "Data da simulação", "Vendedor", "Cliente", "CNPJ",
    "Razão social (consulta)", "Orçamento", "Nº do pedido",
    "Origem UF/cidade", "Origem contribuinte", "Data/hora da consulta", "Fonte da consulta",
    "Simples Nacional", "SUFRAMA",
    "UF", "Localização", "Contribuinte", "Finalidade",
    "Frete aplicado", "Montagem aplicada",
    "Valor dos produtos", "A pagar à transportadora", "A pagar à montadora",
    "Frete cobrado", "Montagem cobrada", "DIFAL/FCP embutido",
    "Guia DIFAL", "Guia FCP", "IPI", "Valor dos itens na NF", "Total da NF",
    "Resultado frete/montagem", "% comissão", "Comissão correta",
    "Comissão pelo sistema", "Diferença de comissão",
]


def linha_csv(valores):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(COLUNAS)
    w.writerow(valores)
    return buf.getvalue().encode("utf-8-sig")


def registrar_planilha(st, valores, token=None):
    sp = _secao(st, "sharepoint")
    if not sp or any(not sp.get(k) for k in ("site_hostname", "site_path", "file_path")):
        return False, "Planilha ainda não configurada (secrets [sharepoint])."
    if token is None:
        token, erro = _token_microsoft(st)
        if not token:
            return False, erro
    h = {"Authorization": f"Bearer {token}"}
    try:
        site = requests.get(f"{GRAPH}/sites/{sp['site_hostname']}:{sp['site_path']}",
                            headers=h, timeout=TIMEOUT)
        if site.status_code != 200:
            return False, f"Site do SharePoint não encontrado ({site.status_code})."
        site_id = site.json()["id"]
        arq = requests.get(f"{GRAPH}/sites/{site_id}/drive/root:/{quote(sp['file_path'])}",
                           headers=h, timeout=TIMEOUT)
        if arq.status_code != 200:
            return False, f"Planilha não encontrada ({arq.status_code})."
        tabela = sp.get("table_name", "Simulacoes")
        add = requests.post(
            f"{GRAPH}/sites/{site_id}/drive/items/{arq.json()['id']}/workbook/tables/{tabela}/rows/add",
            headers=h, json={"values": [valores]}, timeout=TIMEOUT)
        if add.status_code in (200, 201):
            return True, "Simulação salva na planilha."
        return False, f"Não foi possível incluir a linha na planilha ({add.status_code})."
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o SharePoint: {exc}"


def enviar_email(st, assunto, corpo_html, anexos, token=None):
    """anexos: lista de (nome_arquivo, bytes)."""
    em = _secao(st, "email")
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


def enviar_e_salvar(st, valores, assunto, corpo_html, anexos):
    """Faz as duas etapas; retorna (ok_planilha, msg_planilha, ok_email, msg_email)."""
    token, erro = _token_microsoft(st)
    if not token:
        return False, erro, False, erro
    ok_p, msg_p = registrar_planilha(st, valores, token)
    ok_e, msg_e = enviar_email(st, assunto, corpo_html, anexos, token)
    return ok_p, msg_p, ok_e, msg_e
