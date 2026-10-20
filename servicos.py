# servicos.py
# Integrações externas da calculadora. Credenciais vêm de st.secrets
# (Streamlit Cloud: Settings › Secrets). Sem credenciais, tudo continua
# funcionando: o registro vira download em CSV e os parâmetros são salvos
# só no app até a próxima reinicialização.

import base64
import csv
import io
import json
from urllib.parse import quote

import requests

TIMEOUT = 20


def _secrets(st, secao):
    try:
        return dict(st.secrets[secao])
    except Exception:
        return None


# ------------------------------------------------------------------
# Senha do Adm
# ------------------------------------------------------------------
def senha_adm(st):
    try:
        return st.secrets["ADM_SENHA"]
    except Exception:
        return None


# ------------------------------------------------------------------
# Parâmetros: salvar o config.json direto no GitHub
# Secrets necessários na seção [github]: token, repo ("dono/repositorio"),
# branch (opcional, padrão "main"), path (opcional, padrão "config.json")
# ------------------------------------------------------------------
def salvar_config_github(st, cfg, autor="Tela de Parâmetros (Adm)"):
    gh = _secrets(st, "github")
    if not gh or not gh.get("token") or not gh.get("repo"):
        return False, "Integração com o GitHub não configurada (secrets [github])."
    repo = gh["repo"]
    branch = gh.get("branch", "main")
    path = gh.get("path", "config.json")
    url = f"https://api.github.com/repos/{repo}/contents/{quote(path)}"
    headers = {
        "Authorization": f"Bearer {gh['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        atual = requests.get(url, headers=headers, params={"ref": branch}, timeout=TIMEOUT)
        sha = atual.json().get("sha") if atual.status_code == 200 else None
        conteudo = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
        corpo = {
            "message": f"Atualiza parâmetros da calculadora ({autor})",
            "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            corpo["sha"] = sha
        resp = requests.put(url, headers=headers, json=corpo, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            return True, f"Parâmetros gravados no GitHub ({repo}, branch {branch})."
        return False, f"GitHub recusou a gravação ({resp.status_code}): {resp.text[:200]}"
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o GitHub: {exc}"


# ------------------------------------------------------------------
# Registro das simulações numa tabela do Excel no SharePoint/OneDrive
# Secrets necessários na seção [sharepoint]:
#   tenant_id, client_id, client_secret,
#   site_hostname  (ex.: "minimaldesign.sharepoint.com"),
#   site_path      (ex.: "/sites/Comercial"),
#   file_path      (ex.: "Simulacoes/Simulacoes.xlsx", relativo à biblioteca Documentos),
#   table_name     (opcional, padrão "Simulacoes")
# ------------------------------------------------------------------
COLUNAS = [
    "Data/hora", "Data da simulação", "Vendedor", "Cliente", "Orçamento", "Nº do pedido",
    "UF", "Localização", "Possui IE", "Finalidade", "Forma do acréscimo",
    "Valor dos produtos", "Frete (custo)", "Montagem (custo)",
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


def registrar_sharepoint(st, valores):
    sp = _secrets(st, "sharepoint")
    obrig = ["tenant_id", "client_id", "client_secret", "site_hostname", "site_path", "file_path"]
    if not sp or any(not sp.get(k) for k in obrig):
        return False, "Registro na planilha ainda não configurado (secrets [sharepoint])."
    try:
        tok = requests.post(
            f"https://login.microsoftonline.com/{sp['tenant_id']}/oauth2/v2.0/token",
            data={
                "client_id": sp["client_id"],
                "client_secret": sp["client_secret"],
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=TIMEOUT,
        )
        if tok.status_code != 200:
            return False, f"Microsoft recusou o login do aplicativo ({tok.status_code})."
        h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
        g = "https://graph.microsoft.com/v1.0"

        site = requests.get(f"{g}/sites/{sp['site_hostname']}:{sp['site_path']}", headers=h, timeout=TIMEOUT)
        if site.status_code != 200:
            return False, f"Site do SharePoint não encontrado ({site.status_code})."
        site_id = site.json()["id"]

        arq = requests.get(f"{g}/sites/{site_id}/drive/root:/{quote(sp['file_path'])}",
                           headers=h, timeout=TIMEOUT)
        if arq.status_code != 200:
            return False, f"Planilha não encontrada ({arq.status_code})."
        item_id = arq.json()["id"]

        tabela = sp.get("table_name", "Simulacoes")
        add = requests.post(
            f"{g}/sites/{site_id}/drive/items/{item_id}/workbook/tables/{tabela}/rows/add",
            headers=h, json={"values": [valores]}, timeout=TIMEOUT,
        )
        if add.status_code in (200, 201):
            return True, "Simulação registrada na planilha."
        return False, f"Não foi possível incluir a linha na planilha ({add.status_code})."
    except requests.RequestException as exc:
        return False, f"Falha de conexão com o SharePoint: {exc}"
