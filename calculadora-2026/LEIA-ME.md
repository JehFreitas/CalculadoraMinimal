# Calculadora Comercial Minimal 2026 (NF-e, lucro real)

Calculadora nova, em pasta própria. A calculadora antiga (`calculadora-minimal-nfe.py`, na raiz do repositório) **não foi alterada** e continua no link de sempre.

## Arquivos desta pasta

| Arquivo | Para que serve |
|---|---|
| `app.py` | Tela da calculadora (o arquivo que o Streamlit executa) |
| `calculo.py` | Regras de cálculo, sem percentuais fixos |
| `config.json` | Percentuais e tabelas, editáveis pela tela **⚙️ Parâmetros (Adm)** |
| `consulta.py` | Consulta do cliente pelo CNPJ |
| `servicos.py` | Planilha no SharePoint, e-mail ao ADM Comercial e gravação dos parâmetros no GitHub |
| `requirements.txt` | Bibliotecas desta calculadora (o Streamlit usa este, e não o da raiz) |
| `modelos/Simulacoes.xlsx` | Modelo da planilha de simulações |
| `.streamlit/secrets.toml.exemplo` | Modelo dos Secrets (senhas e chaves) |

## 1. Criar o link novo no Streamlit Cloud

1. Em share.streamlit.io, clique em **Create app** › **Deploy a public app from GitHub** (ou "from GitHub").
2. Preencha:
   - **Repository:** `JehFreitas/CalculadoraMinimal`
   - **Branch:** `nova-calculadora-2026`
   - **Main file path:** `calculadora-2026/app.py`
   - **App URL:** um nome novo, por exemplo `calculadora-minimal-2026`
3. Em **Advanced settings** › **Secrets**, cole o conteúdo de `.streamlit/secrets.toml.exemplo` com uma **senha nova** em `ADM_SENHA`. Os demais blocos podem ficar vazios por enquanto.
4. Clique em **Deploy**. O app antigo continua no ar, no link dele.

## 2. Testar no Codespace (opcional)

```
git fetch origin
git checkout nova-calculadora-2026
cd calculadora-2026
pip install -r requirements.txt
cp .streamlit/secrets.toml.exemplo .streamlit/secrets.toml
streamlit run app.py --server.enableCORS false --server.enableXsrfProtection false
```

Para voltar: `Ctrl + C`, `cd ..` e `git checkout main`.

## 3. Integrações (podem ser ligadas depois, sem mexer no código)

Enquanto cada uma não estiver configurada, a calculadora funciona e oferece um download de reserva.

### Consulta pelo CNPJ
- Sem configuração: usa a API gratuita (UF, cidade, Simples Nacional e SUFRAMA). O vendedor confere a IE no CCC ou no Sintegra pelos links da tela.
- Com a API comercial da CNPJá (planos a partir de R$ 24,99/mês, cerca de 4 créditos por consulta): crie a conta, gere o token e cole em `[cnpja] token`. A consulta passa a marcar contribuinte/não contribuinte pela inscrição estadual.

### Parâmetros salvos pela tela do Adm (GitHub)
GitHub › Settings › Developer settings › Fine-grained tokens › Generate new token:
- Repository access: *Only select repositories* › `CalculadoraMinimal`
- Permissions › Contents: *Read and write*
- Cole em `[github] token`. A branch e o caminho já estão no modelo.

### Planilha e e-mail ao ADM Comercial (TI / Microsoft 365)
1. Envie `modelos/Simulacoes.xlsx` para a biblioteca **Documentos** do site do Comercial (ex.: pasta `Simulacoes`). A tabela se chama `Simulacoes`. A linha vazia do modelo pode ser excluída depois do primeiro registro.
2. O TI registra um aplicativo no **Microsoft Entra ID** (ex.: "Calculadora Minimal"), cria um **segredo do cliente** e concede, com consentimento do administrador:
   - **Sites.Selected**, com escrita liberada só no site do Comercial;
   - **Mail.Send**, restrito por política de acesso (*application access policy*) à caixa remetente, ex.: `calculadora@minimaldesign.com.br`.
3. Preencha `[microsoft]`, `[sharepoint]` e `[email]` nos Secrets.
4. A coluna **Nº do pedido** é preenchida depois, direto no Excel.

## Opções que dependem da contabilidade (tela do Adm)

- **Contribuinte consumidor final: ICMS sobre o IPI** — desligada até confirmar.
- **Não contribuinte: ICMS sobre o IPI e o DIFAL/FCP embutido** — ligada.
- **PIS/COFINS sobre o valor embutido** — ligada.
- **Créditos de PIS/COFINS sobre frete e montagem** — ligados.
- **Empresa com lucro / adicional de IR** — desligados.

## Regras de preenchimento

- Campos com `*` são obrigatórios; a calculadora lista o que falta.
- Frete e montagem: o vendedor escolhe se vão **ao pedido** (vFrete / despesas acessórias) ou **aos itens**.
- DIFAL/FCP (não contribuinte) e o ICMS sobre o IPI (consumidor final) vão **sempre aos itens**.
- A base da Salis e da montadora é o valor dos itens na NF (vProd); a calculadora resolve o cálculo circular.
- A comissão correta é sempre sobre os produtos; a diferença para o valor do sistema aparece na tela, no PDF do Adm e na planilha.
