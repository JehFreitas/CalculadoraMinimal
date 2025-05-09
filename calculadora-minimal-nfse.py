# Divisão dos produtos
valor_produtos_nfe = Decimal(valor_produtos) * Decimal("0.6")
valor_produtos_nfse = Decimal(valor_produtos) * Decimal("0.4")

# Tabelas de imposto aplicadas sobre os 60%
IPI = Decimal("0.0325")
ICMS = Decimal(TABELA_ICMS.get(estado, 0))
DIFAL = Decimal(TABELA_DIFAL.get(estado, 0))
FCP = Decimal(TABELA_FCP.get(estado, 0))

# ====================
# FRETE (aplicado sobre 60%)
# ====================
frete_base = Decimal(0)
if frete_opcao == "Calcular Salis":
    if estado == "São Paulo":
        if cidade == "Capital" and horario == "Comercial":
            frete_base = valor_produtos_nfe * Decimal("0.03")
        else:
            frete_base = valor_produtos_nfe * Decimal("0.04")
    else:
        percentual = TABELA_SALIS.get((estado, cidade), Decimal("0.0"))
        base_frete = valor_produtos_nfe if valor_produtos_nfe > 18000 else Decimal("18000.00")
        frete_base = base_frete * Decimal(percentual or 0)
elif frete_opcao == "Informar valor negociado":
    frete_base = Decimal(frete_negociado)
elif frete_opcao == "Não contratar":
    frete_base = Decimal(0)

# ====================
# MONTAGEM (baseada em 60% dos produtos, mas entra na NFSe)
# ====================
montagem_base = Decimal(0)
if montagem_opcao == "Calcular automaticamente":
    if estado == "São Paulo" and cidade == "Capital":
        montagem_base = valor_produtos_nfe * Decimal("0.035")
    else:
        valor_base_montagem = valor_produtos_nfe * Decimal("0.035")
        custo_km = Decimal(km_ida_volta) * Decimal("3.50")
        montagem_base = valor_base_montagem + custo_km
elif montagem_opcao == "Valor negociado":
    montagem_base = Decimal(montagem_negociada)
elif montagem_opcao == "Não contratar":
    montagem_base = Decimal(0)

# ====================
# MULTIPLICADOR (idêntico ao da CALC1)
# ====================
BASE = Decimal("500000")
ipi_frete = BASE * IPI / (1 + IPI)
icms_frete = BASE * ICMS
base_liquida = BASE - ipi_frete
pis_cofins = base_liquida * Decimal("0.0365")
irpj = base_liquida * Decimal("0.08") * Decimal("0.25")
csll = base_liquida * Decimal("0.12") * Decimal("0.09")

if tem_ie == "Não":
    difal_frete = BASE * DIFAL
    fcp_frete = BASE * FCP
    t_imp_frete = ipi_frete + icms_frete + pis_cofins + irpj + csll + difal_frete + fcp_frete
else:
    t_imp_frete = ipi_frete + icms_frete + pis_cofins + irpj + csll

frete_liquido = BASE - t_imp_frete
multiplicador = BASE / frete_liquido if frete_liquido > 0 else Decimal("1.0")

# ===========================
# CÁLCULOS FISCAIS SOBRE A NFe (60%)
# ===========================
if tem_ie == "Não":
    base_difal1 = (valor_produtos_nfe + frete_final) / (1 - DIFAL - FCP)
    base_difal2 = 1 - ((IPI * (1 - DIFAL - FCP)) / (1 + IPI))
    base_difal = base_difal1 / base_difal2

    guia_difal = base_difal * DIFAL
    guia_fcp = base_difal * FCP
    valor_ipi = base_difal * IPI / (1 + IPI)

    difal_embutido = ((base_difal - valor_produtos_nfe - frete_final - valor_ipi) * DIFAL) / (DIFAL + FCP) if (DIFAL + FCP) != 0 else Decimal(0)
    fcp_embutido = base_difal - valor_produtos_nfe - frete_final - difal_embutido - valor_ipi
else:
    base_difal = valor_produtos_nfe + frete_final
    guia_difal = Decimal(0)
    guia_fcp = Decimal(0)
    valor_ipi = base_difal * IPI / (1 + IPI)
    difal_embutido = Decimal(0)
    fcp_embutido = Decimal(0)

# Despesas acessórias e valor final da NFe
despesas_acessorias = base_difal - valor_produtos_nfe - frete_final - valor_ipi if guia_difal > 0 else Decimal(0)
valor_nfe = valor_produtos_nfe + frete_final + valor_ipi + despesas_acessorias


# ====================
# Valores finais aplicando multiplicador
# ====================
frete_final = frete_base * multiplicador
montagem_final = montagem_base * multiplicador
# ===========================
# CÁLCULO NFSe
# ===========================
valor_nfse = valor_produtos_nfse + montagem_final
st.subheader("Resumo da Nota Fiscal de Produtos (NFe)")
st.write(f"Valor dos produtos (60%): {formatar(valor_produtos_nfe)}")
st.write(f"Valor do Frete: {formatar(frete_final)}")
st.write(f"Valor do IPI: {formatar(valor_ipi)}")
st.write(f"Difal embutido: {formatar(difal_embutido)}")
st.write(f"FCP embutido: {formatar(fcp_embutido)}")
st.write(f"Despesas acessórias: {formatar(despesas_acessorias)}")
st.write(f"Valor total da NFe: {formatar(valor_nfe)}")

st.subheader("Resumo da Nota Fiscal de Serviço (NFSe)")
st.write(f"Valor dos produtos (40%): {formatar(valor_produtos_nfse)}")
st.write(f"Valor da Montagem: {formatar(montagem_final)}")
st.write(f"Valor total da NFSe: {formatar(valor_nfse)}")


