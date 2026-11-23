// Office Script: grava a linha enviada pela Calculadora Comercial na tabela certa.
// Uso: Power Automate › Excel Online (Business) › "Executar script", parâmetro "conteudo".
function main(workbook: ExcelScript.Workbook, conteudo: string) {
  const dados = JSON.parse(conteudo) as { tabela: string; colunas: string[]; linha: (string | number)[] };
  const tabela = workbook.getTable(dados.tabela);
  if (!tabela) {
    throw new Error("Tabela não encontrada: " + dados.tabela);
  }
  // Monta a linha pela ordem das colunas da planilha (colunas que faltarem ficam em branco).
  const cabecalho = tabela.getHeaderRowRange().getValues()[0] as string[];
  const linha = cabecalho.map(nome => {
    const i = dados.colunas.indexOf(String(nome));
    return i >= 0 ? dados.linha[i] : "";
  });
  // Planilha nova: a tabela começa com uma linha em branco. A primeira simulação ocupa essa linha.
  const corpo = tabela.getRangeBetweenHeaderAndTotal();
  const valores = corpo.getValues();
  const vazia = valores.length === 1 && valores[0].every(v => v === "" || v === null);
  if (vazia) {
    corpo.getRow(0).setValues([linha]);
  } else {
    tabela.addRow(-1, linha);
  }
}
