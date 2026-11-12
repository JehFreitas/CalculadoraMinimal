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
| `config_comercial.json`, `descontos.py` | Condições de pagamento, limites da política e cálculo do desconto |
| `consulta.py` | Consulta do cliente pelo CNPJ (CNPJá) |
| `servicos.py`, `comum.py` | Planilha, e-mail, GitHub, PDF |
| `modelos/Controle de Simulações - Calculadora Comercial.xlsx` | Planilha de controle (abas NF-e e Venda Assistida) |
| `.streamlit/secrets.toml.exemplo` | Modelo dos Secrets |

## Regras de preenchimento

- NF-e: o vendedor informa o Total Itens de tabela (sem descontos), a condição de pagamento, a equipe e a política (em % ou pelo valor final desejado). A calculadora aplica a condição e depois a política sobre os itens, como o Focco, e devolve o que lançar no orçamento.
- % da condição: prazo médio = Σ (prazo da parcela + 30 dias de fabricação) × % da parcela (sinal = −23 dias); % = (1 + custo diário)^(prazo médio − 60) − 1, custo diário = 1,03^(1/30) − 1; arredondado ao múltiplo de 0,5%. Só aparecem as condições cadastradas no Focco com o mesmo %; as demais o vendedor pede ao ADM Comercial.
- Divisão produto/serviço (opção no NF-e 2026): pedido de serviço = 40% do Valor Total (sem ICMS, IPI, acréscimos ou descontos); no pedido de produtos saem montagem, DIFAL e FCP, ficam frete, condição e política, e entra um desconto em valor aos itens para fechar em 60%: (itens líquidos − desconto + frete) × (1 + IPI) = 60% do total. Como a política do Focco incide sobre o que é lançado aos itens, o desconto lançado = redução necessária ÷ (1 − política).
- Itens com desconto diferente: o vendedor informa só as exceções (valor de tabela × quantidade e % do item); os demais itens levam o desconto padrão. No Focco a política vai na linha Política (700/1/3) de cada item e a da capa fica em 0%. O limite da equipe vale por item.
- Modo valor final: só a política se ajusta (4 casas); frete, montagem e DIFAL/FCP nunca são reduzidos; o limite da equipe nunca é ultrapassado.

- NF-e: frete sempre ao pedido (campo de frete da NF); montagem sempre ao pedido (despesas acessórias); DIFAL/FCP sempre embutido nos itens. SP Capital: frete e montagem não são cobrados, e o custo é registrado com 4% da Salis.
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
