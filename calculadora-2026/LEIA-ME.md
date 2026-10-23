# Calculadora Comercial Minimal

App do Streamlit em pasta própria. A calculadora antiga (`calculadora-minimal-nfe.py`, na raiz) não é alterada.

## Cálculos (menu lateral)

| Menu | Situação | Regras |
|---|---|---|
| NF-e Minimal › Cálculo 2026 | Em uso | Lucro real: PIS/COFINS 9,25% com créditos, IPI, ICMS, DIFAL/FCP |
| NF-e Minimal › Cálculo 2027 | 🔒 Bloqueado | CBS/IBS por fora no lugar de PIS/COFINS, IPI zero |
| Venda Assistida › Cavaletti 2026 | Em uso | NF de produto da Cavaletti + NF de serviço da Minimal (ISS + PIS/COFINS) |
| Venda Assistida › Cavaletti 2027 | 🔒 Bloqueado | NF de serviço com ISS e CBS/IBS por fora, IPI zero |

Os cálculos de 2027 ficam visíveis, mas só o Adm consegue simular. Para liberar: área do Adm › Parâmetros do cálculo › marcar "Alíquota da CBS definida", informar a alíquota fixada pelo Senado, marcar "Liberar este cálculo para o Comercial" e salvar.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `app.py` | Menu lateral e área do Adm (arquivo que o Streamlit executa) |
| `tela_nfe.py`, `tela_cavaletti.py` | Telas |
| `calculo.py`, `calculo_2027.py`, `cavaletti.py` | Regras de cálculo |
| `config.json`, `config_2027.json`, `config_cavaletti.json` | Parâmetros, editáveis pela área do Adm |
| `consulta.py` | Consulta do cliente pelo CNPJ (CNPJá) |
| `servicos.py`, `comum.py` | Planilha, e-mail, GitHub, PDF |
| `modelos/Controle de Simulações - Calculadora Comercial.xlsx` | Planilha de controle (abas NF-e e Venda Assistida) |
| `.streamlit/secrets.toml.exemplo` | Modelo dos Secrets |

## Regras de preenchimento

- NF-e: frete ao pedido ou aos itens; montagem e DIFAL/FCP sempre ao pedido (despesas acessórias). SP Capital: frete e montagem não são cobrados, e o custo é registrado com 4% da Salis.
- Cavaletti: uma linha por produto (custo sem IPI, IPI, entrega/montagem por unidade, quantidade); % da NF de produto; desconto à vista; RT limitado pela tabela de RT.

## Secrets (Streamlit Cloud › app › Settings › Secrets)

Copie `.streamlit/secrets.toml.exemplo` e preencha:

- `ADM_SENHA`: senha da área do Adm e do PDF do Adm.
- `[cnpja] token`: token da API comercial da CNPJá (CNPJá › Conta › Chaves de API).
- `[github] token`: token fine-grained só deste repositório, com Contents: Read and write (para salvar parâmetros).
- `[microsoft]`, `[sharepoint]`, `[email]`: preenchidos depois que o TI registrar o aplicativo.

## Planilha de controle

1. Envie `modelos/Controle de Simulações - Calculadora Comercial.xlsx` para a biblioteca **Comercial** do site **Área Comercial** no SharePoint, na raiz da biblioteca (ou ajuste `file_path` nos Secrets).
2. Não renomeie as tabelas (`Simulacoes` e `VendaAssistida`) nem as colunas.
3. O botão **Enviar simulação ao ADM Comercial e salvar** inclui uma linha na tabela e envia o e-mail com os PDFs. Até o TI configurar o Microsoft 365, o botão oferece o CSV e o PDF do Adm para envio manual.

### TI (Microsoft 365)

Registrar um aplicativo no Microsoft Entra ID, criar um segredo do cliente e conceder, com consentimento do administrador:
- **Sites.Selected** com escrita no site Área Comercial (ou Files.ReadWrite.All);
- **Mail.Send**, restrito por *application access policy* à caixa remetente.

## Testar no Codespace

```
git fetch origin
git checkout nova-calculadora-2026
cd calculadora-2026
pip install -r requirements.txt
cp .streamlit/secrets.toml.exemplo .streamlit/secrets.toml
streamlit run app.py --server.enableCORS false --server.enableXsrfProtection false
```
