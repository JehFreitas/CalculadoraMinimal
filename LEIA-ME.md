# Calculadora Comercial Minimal — NF-e (regras de 2026)

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `calculadora-minimal-nfe.py` | Tela da calculadora (é o arquivo que o Streamlit Cloud executa) |
| `calculo.py` | Regras de cálculo. Não tem nenhum percentual fixo |
| `config.json` | Todos os percentuais e tabelas. Editável pela tela **⚙️ Parâmetros (Adm)** |
| `servicos.py` | Grava os parâmetros no GitHub e registra as simulações na planilha do SharePoint |
| `modelos/Simulacoes.xlsx` | Planilha modelo para o registro das simulações |
| `.streamlit/secrets.toml.exemplo` | Modelo dos Secrets (senhas e chaves) |

Senhas e chaves **nunca** ficam no código: ficam nos Secrets do Streamlit Cloud.

## 1. Testar no Codespace antes de publicar

1. Abra o Codespace do repositório e, no terminal, troque para a branch de teste:
   ```
   git fetch origin
   git checkout correcoes-2026
   pip install -r requirements.txt
   ```
2. Crie o arquivo de Secrets local (ele não vai para o GitHub):
   ```
   cp .streamlit/secrets.toml.exemplo .streamlit/secrets.toml
   ```
   Para o teste, basta trocar o `ADM_SENHA`. Os blocos `[github]` e `[sharepoint]` podem ficar como estão.
3. Rode a calculadora:
   ```
   streamlit run calculadora-minimal-nfe.py --server.enableCORS false --server.enableXsrfProtection false
   ```
4. Ao terminar, volte para a versão em produção com `git checkout main`.

## 2. Antes de aprovar o pull request: cadastrar os Secrets no Streamlit Cloud

Sem isso, a área do Adm e o PDF do Adm ficam desativados.

1. Em share.streamlit.io, no app **calculadora-minimal-nfe.py**, clique nos três pontos › **Settings** › **Secrets**.
2. Cole o conteúdo de `.streamlit/secrets.toml.exemplo` com os valores reais e salve.
3. **Use uma senha nova** no `ADM_SENHA`: a antiga ficou visível no código enquanto o repositório era público.

### Token do GitHub (para salvar os parâmetros pela tela do Adm)

O Streamlit Cloud apaga arquivos alterados quando o app reinicia. Por isso a tela do Adm grava o `config.json` direto no GitHub (cada alteração vira um commit, com histórico).

1. GitHub › foto › **Settings** › **Developer settings** › **Personal access tokens** › **Fine-grained tokens** › **Generate new token**.
2. Nome: `Calculadora - parâmetros`. Validade: 1 ano (anote para renovar).
3. **Repository access**: *Only select repositories* › `CalculadoraMinimal`.
4. **Permissions** › **Repository permissions** › **Contents**: *Read and write*. Nada mais.
5. Copie o token e cole em `token` no bloco `[github]` dos Secrets.

Ao salvar parâmetros, o app é atualizado automaticamente em cerca de um minuto.

## 3. Planilha de simulações no SharePoint (com o TI)

Enquanto isso não estiver pronto, cada cálculo oferece o botão **Baixar registro da simulação (CSV)**.

1. Envie `modelos/Simulacoes.xlsx` para a biblioteca **Documentos** do site do Comercial (ex.: pasta `Simulacoes`). A tabela do Excel já se chama `Simulacoes`. Depois que a primeira simulação for registrada, a linha vazia do modelo pode ser excluída.
2. O TI registra um aplicativo no **Microsoft Entra ID** (ex.: "Calculadora Minimal"):
   - anota o **ID do locatário** (tenant ID) e o **ID do aplicativo** (client ID);
   - cria um **segredo do cliente** (client secret);
   - concede a permissão de aplicativo **Sites.Selected** com consentimento do administrador e libera escrita só no site do Comercial (ou, se preferir, **Sites.ReadWrite.All**).
3. Preencha o bloco `[sharepoint]` dos Secrets com esses dados, o endereço do site e o caminho da planilha.
4. A coluna **Nº do pedido** é preenchida depois, direto no Excel, por quem cuida das comissões.

## 4. Segurança

- Deixe o repositório **privado** (GitHub › Settings › General › Danger Zone › Change visibility). O Streamlit Cloud continua funcionando.
- Troque a senha do PDF do Adm (passo 2).

## Opções que dependem de confirmação da contabilidade

Ficam na tela do Adm e podem ser ligadas ou desligadas sem mexer no código:

- **Cliente com IE para uso e consumo: ICMS sobre o IPI** — desligada até confirmar (ponto D).
- **Cliente sem IE: ICMS sobre o IPI e o DIFAL/FCP embutido** — ligada (confirmado).
- **PIS/COFINS sobre o valor embutido** — ligada (confirmado).
- **Créditos de PIS/COFINS sobre frete e montagem** — ligados (confirmado).
- **Empresa com lucro / adicional de IR** — desligados.
