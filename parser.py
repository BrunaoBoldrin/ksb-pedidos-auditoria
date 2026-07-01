import re
import pdfplumber
import pandas as pd
from database import buscar_material_por_codigo, localizar_regra_fiscal_por_ncm

from datetime import datetime

# ====================================
# FUNCOES AUXILIARES
# ====================================


PIS_COFINS_PERCENTUAL = 0.0925
TOLERANCIA_IMPOSTO = 1.00


def moeda_para_float(valor):
    valor = str(valor)
    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")
    valor = valor.replace("/1", "")
    valor = valor.strip()

    try:
        return float(valor)
    except Exception:
        return 0.0


def normalizar_ncm(valor):
    return re.sub(r"\D", "", str(valor or ""))


def percentual_para_decimal(valor):
    try:
        return float(valor or 0) / 100
    except Exception:
        return 0.0


def numero_para_float(valor):
    if valor in [None, ""]:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto or texto.lower() in ["nan", "none"]:
        return 0.0

    if "," in texto:
        return moeda_para_float(texto)

    try:
        return float(texto)
    except Exception:
        return moeda_para_float(texto)


def formatar_moeda_texto(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def calcular_divisor_base(icms):
    try:
        icms_float = float(icms or 0)
    except Exception:
        return 0.7442

    if abs(icms_float - 12.0) < 0.01:
        return 0.7986

    if abs(icms_float - 18.0) < 0.01:
        return 0.7442

    divisor = 1 - (icms_float / 100) - PIS_COFINS_PERCENTUAL
    if divisor <= 0:
        return 0.7442

    return divisor


def texto_regra(regra):
    if not regra:
        return "Regra fiscal não cadastrada"
    return str(regra.get("observacao") or "Sem observação cadastrada").strip()


def diagnosticar_imposto_na_diferenca(diferenca, impostos):
    for nome, valor in impostos:
        if valor and abs(abs(diferenca) - abs(valor)) <= TOLERANCIA_IMPOSTO:
            return (
                f"A diferença encontrada corresponde aproximadamente ao valor do {nome}, "
                "indicando que este imposto pode não estar discriminado no pedido KSB."
            )

    return "Valor do pedido diverge do valor calculado com base líquida, divisor fiscal e IPI da regra fiscal."


# ====================================
# PROCESSAR PDF
# ====================================


def processar_pdf(PDF_PATH):
    dados_csv = []
    analises = []

    texto_completo = ""

    # ====================================
    # LEITURA PDF
    # ====================================

    with pdfplumber.open(PDF_PATH) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()

            if texto:
                texto_completo += texto + "\n"

    # ====================================
    # PEDIDO
    # ====================================

    pedido_match = re.search(r"Pedido\s+(\d+)", texto_completo)

    numero_pedido = pedido_match.group(1) if pedido_match else ""

    # ====================================
    # DATA EMISSAO
    # ====================================

    datas = re.findall(r"\d{2}\.\d{2}\.\d{4}", texto_completo)

    data_emissao = datas[0] if len(datas) > 0 else ""

    # ====================================
    # UNIDADE
    # ====================================

    unidade = ""

    unidade_match = re.search(
        r"Endereço de entrega:.*?KSB Brasil Ltda\.\s*([A-Za-zÀ-Úà-ú\s]+)-",
        texto_completo,
        re.DOTALL,
    )

    if unidade_match:
        unidade = unidade_match.group(1).strip()

    # ====================================
    # COMPRADOR
    # ====================================

    comprador = ""

    linhas_documento = texto_completo.splitlines()

    for i, linha in enumerate(linhas_documento):
        if "Contato Grupo de Compras" in linha:
            if i + 1 < len(linhas_documento):
                proxima_linha = linhas_documento[i + 1].strip()

                comprador_match = re.search(r"([A-Za-zÀ-Úà-ú\s]+)\s+\d+", proxima_linha)

                if comprador_match:
                    comprador = comprador_match.group(1).strip()

                break

    # ====================================
    # ITENS
    # ====================================

    matches = list(
        re.finditer(r"^\s*(000\d{2})\s+(\d{8})", texto_completo, re.MULTILINE)
    )

    # ====================================
    # LOOP ITENS
    # ====================================

    for i in range(len(matches)):
        inicio = matches[i].start()

        if i < len(matches) - 1:
            fim = matches[i + 1].start()

        else:
            fim = len(texto_completo)

        bloco = texto_completo[inicio:fim]

        linhas = bloco.splitlines()

        # ====================================
        # ITEM
        # ====================================

        item_match = re.search(r"(000\d{2})", bloco)

        item = item_match.group(1) if item_match else ""

        # ====================================
        # CODIGO MATERIAL
        # ====================================

        codigo_match = re.search(r"000\d{2}\s+(\d{8})", bloco)

        codigo_material = codigo_match.group(1) if codigo_match else ""

        # ====================================
        # DATA ENTREGA
        # ====================================

        data_entrega_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", bloco)

        data_entrega = data_entrega_match.group(1) if data_entrega_match else ""

        # ====================================
        # QUANTIDADE
        # ====================================

        quantidade_match = re.search(r"\d{2}\.\d{2}\.\d{4}\s+(\d+(?:,\d+)?)", bloco)

        quantidade = quantidade_match.group(1) if quantidade_match else ""

        # ====================================
        # UNIDADE ITEM
        # ====================================

        unidade_item_match = re.search(
            r"\d+(?:,\d+)?\s+(PEÇ|M2|KG|UN|CJ|PC|LT|TON|BAR|ROL)", bloco
        )

        unidade_item = unidade_item_match.group(1) if unidade_item_match else ""

        # ====================================
        # DESCRICAO
        # ====================================

        descricao = ""

        for idx, linha in enumerate(linhas):
            if re.search(r"000\d{2}", linha):
                if idx + 1 < len(linhas):
                    descricao = linhas[idx + 1].strip()

                    break

        # ====================================
        # MEDIDA
        # ====================================

        medida_match = re.search(r"tamanho/dimensão:\s*(.*)", bloco)

        medida = medida_match.group(1).strip() if medida_match else ""

        # ====================================
        # MATERIAL
        # ====================================

        material_match = re.search(r"Mat\.básic:\s*(.*)", bloco)

        material = material_match.group(1).strip() if material_match else ""

        # ====================================
        # NORMA
        # ====================================

        norma = ""

        for linha in linhas:
            if "Desenho/Norma:" in linha:
                norma = linha.split("Desenho/Norma:")[1].strip()

                norma = re.sub(r"\s+\d{2}$", "", norma)

                break

        # ====================================
        # NCM DO PEDIDO
        # ====================================

        ncm_match = re.search(r"NCM:\s*(.*)", bloco)

        ncm = ncm_match.group(1).strip() if ncm_match else ""

        # ====================================
        # VALOR UNITARIO
        # ====================================

        valor_unitario_match = re.search(
            r"(\d{1,3}(?:\.\d{3})*,\d{2})\/1",
            bloco
        )

        valor_unitario = ""

        if valor_unitario_match:
            valor_unitario = valor_unitario_match.group(1)

        # ====================================
        # VALOR TOTAL
        # ====================================

        valor_total = ""

        linha_item = ""

        for linha in linhas:
            if re.search(r"000\d{2}", linha):
                linha_item = linha

                break

        valores_linha = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", linha_item)

        if len(valores_linha) > 0:
            valor_total = valores_linha[-1]

        # ====================================
        # VALIDACOES
        # ====================================

        divergencias = []
        diagnosticos = []

        # ====================================
        # MATERIAL CADASTRADO -> NCM CADASTRADO -> REGRA FISCAL
        # ====================================

        material_cadastrado = buscar_material_por_codigo(codigo_material)

        ncm_cadastrado = ""
        regra_fiscal = None
        regra_fiscal_pedido = None
        icms_regra = None
        ipi_regra = None
        observacao_ncm_pedido = ""
        observacao_ncm_cadastro = ""
        descricao_ncm_pedido = ""
        descricao_ncm_cadastro = ""
        ncm_divergente = False

        if ncm:
            regra_fiscal_pedido = localizar_regra_fiscal_por_ncm(ncm)
            observacao_ncm_pedido = texto_regra(regra_fiscal_pedido)

        if not material_cadastrado:
            divergencias.append(
                f"Material KSB não cadastrado na lista de materiais: {codigo_material}"
            )
            diagnosticos.append(
                "Material não encontrado no cadastro. Cadastre o material para validar NCM, impostos e valores."
            )

        else:
            ncm_cadastrado = str(material_cadastrado.get("ncm") or "").strip()

            if not ncm_cadastrado:
                divergencias.append(
                    f"Material KSB {codigo_material} cadastrado sem NCM"
                )
                diagnosticos.append(
                    "Material cadastrado sem NCM. Informe o NCM no cadastro do material para concluir a auditoria."
                )

            else:
                regra_fiscal = localizar_regra_fiscal_por_ncm(ncm_cadastrado)
                observacao_ncm_cadastro = texto_regra(regra_fiscal)

                if normalizar_ncm(ncm) != normalizar_ncm(ncm_cadastrado):
                    ncm_divergente = True
                    descricao_ncm_pedido = observacao_ncm_pedido
                    descricao_ncm_cadastro = observacao_ncm_cadastro
                    divergencias.append(
                        f"NCM divergente (Cadastro: {ncm_cadastrado} | Pedido KSB: {ncm})"
                    )
                    diagnosticos.append(
                        f"NCM do pedido: {ncm} - {observacao_ncm_pedido}"
                    )
                    diagnosticos.append(
                        f"NCM correto: {ncm_cadastrado} - {observacao_ncm_cadastro}"
                    )

                if not regra_fiscal:
                    divergencias.append(
                        f"Nenhuma regra fiscal encontrada para o NCM cadastrado: {ncm_cadastrado}"
                    )
                    diagnosticos.append(
                        "Regra fiscal não localizada para o NCM correto do cadastro. Cadastre a regra fiscal para validar os impostos."
                    )

                else:
                    icms_regra = regra_fiscal["icms"]
                    ipi_regra = regra_fiscal["ipi"]

        # ====================================
        # VALIDACAO VALOR
        # ====================================

        quantidade_float = moeda_para_float(quantidade)
        valor_unitario_float = moeda_para_float(valor_unitario)
        valor_total_float = moeda_para_float(valor_total)
        aliquota_icms = percentual_para_decimal(icms_regra)
        aliquota_ipi = percentual_para_decimal(ipi_regra)

        divisor_base = calcular_divisor_base(icms_regra)
        valor_base = round((valor_unitario_float / divisor_base) * quantidade_float, 2) if regra_fiscal else 0.0
        valor_icms = round(valor_base * aliquota_icms, 2)
        valor_pis_cofins = round(valor_base * PIS_COFINS_PERCENTUAL, 2)
        valor_ipi = round(valor_base * aliquota_ipi, 2)
        valor_calculado = round(valor_base + valor_ipi, 2) if regra_fiscal else 0.0
        diferenca_assinada = round(valor_calculado - valor_total_float, 2) if regra_fiscal else 0.0
        diferenca = abs(diferenca_assinada)

        if regra_fiscal and diferenca > 1:
            divergencias.append(
                f"Valor divergente (Calculado: {valor_calculado} | Pedido: {valor_total_float} | Diferença: {round(diferenca, 2)})"
            )
            diagnosticos.append(
                diagnosticar_imposto_na_diferenca(
                    diferenca,
                    [
                        ("ICMS", valor_icms),
                        ("PIS/COFINS", valor_pis_cofins),
                        ("IPI", valor_ipi),
                    ],
                )
            )

        if not diagnosticos:
            diagnosticos.append("Item sem divergências identificadas.")

        # ====================================
        # ANALISE COMERCIAL
        # ====================================

        preco_pedido_ksb = valor_unitario_float
        preco_cadastrado = 0.0
        diferenca_preco = 0.0
        percentual_diferenca_preco = 0.0
        data_ultima_revisao_preco = ""
        usuario_ultima_revisao_preco = ""

        if not material_cadastrado:
            status_comercial = "PENDENTE - MATERIAL SEM CADASTRO"
            diagnostico_comercial = "Material não cadastrado. Cadastre o material para validar preço e revisão comercial."
        else:
            preco_cadastrado = numero_para_float(material_cadastrado.get("preco_unitario_liquido"))
            data_ultima_revisao_preco = str(material_cadastrado.get("data_ultima_revisao") or "")
            usuario_ultima_revisao_preco = str(material_cadastrado.get("usuario_ultima_revisao_preco") or "")
            diferenca_preco = round(preco_pedido_ksb - preco_cadastrado, 2)
            percentual_diferenca_preco = round((diferenca_preco / preco_cadastrado) * 100, 2) if preco_cadastrado else 0.0

            if preco_cadastrado <= 0:
                status_comercial = "PENDENTE - PREÇO NÃO CADASTRADO"
                diagnostico_comercial = "Material cadastrado sem preço unitário líquido. Informe o preço cadastrado para concluir a análise comercial."
            elif abs(diferenca_preco) > 0.01:
                status_comercial = "PENDENTE - REVISÃO DE PREÇO"
                diagnostico_comercial = (
                    f"Preço do pedido KSB: {formatar_moeda_texto(preco_pedido_ksb)} | "
                    f"Preço cadastrado: {formatar_moeda_texto(preco_cadastrado)} | "
                    f"Diferença: {formatar_moeda_texto(diferenca_preco)} | "
                    f"Última revisão: {data_ultima_revisao_preco or '-'} | "
                    f"Revisado por: {usuario_ultima_revisao_preco or '-'}. "
                    "Necessário revisar preço cadastrado ou negociar pedido."
                )
            else:
                status_comercial = "OK"
                diagnostico_comercial = "Preço líquido unitário do pedido KSB igual ao preço cadastrado."

        # ====================================
        # LEADTIME
        # ====================================

        try:
            data_analise = datetime.today().date()

            data_entrega_dt = datetime.strptime(data_entrega, "%d.%m.%Y").date()

            leadtime = (data_entrega_dt - data_analise).days

        except:
            leadtime = "Erro"

        # ====================================
        # STATUS FINAL
        # ====================================

        if len(divergencias) == 0:
            status_final = "OK"

        else:
            status_final = "DIVERGENTE"

        # ====================================
        # ANALISE
        # ====================================

        analises.append(
            {
                "Pedido": numero_pedido,
                "Data Emissão": data_emissao,
                "Unidade Pedido": unidade,
                "Comprador": comprador,
                "Item": item,
                "Código Material": codigo_material,
                "Descrição": descricao,
                "Quantidade": quantidade_float,
                "Unidade": unidade_item,
                "Status": status_final,
                "NCM Pedido KSB": ncm,
                "Descrição NCM Pedido": descricao_ncm_pedido if ncm_divergente else "",
                "NCM Cadastro": ncm_cadastrado,
                "Descrição NCM Cadastro": descricao_ncm_cadastro if ncm_divergente else "",
                "ICMS Regra": icms_regra if icms_regra is not None else "",
                "PIS/COFINS Regra": "9,25%",
                "IPI Regra": ipi_regra if ipi_regra is not None else "",
                "Valor Unitário Líquido": valor_unitario_float,
                "Valor Base": valor_base,
                "Valor ICMS": valor_icms,
                "Valor PIS/COFINS": valor_pis_cofins,
                "Valor IPI": valor_ipi,
                "Valor Pedido": valor_total_float,
                "Valor Calculado": valor_calculado if regra_fiscal else "",
                "Diferença": diferenca_assinada if regra_fiscal else "",
                "Diagnóstico": " | ".join(diagnosticos),
                "Divergencias": (" | ".join(divergencias) if divergencias else "-"),
                "Status Comercial": status_comercial,
                "Preço Pedido KSB": preco_pedido_ksb,
                "Preço Cadastrado": preco_cadastrado if material_cadastrado else "",
                "Diferença Preço": diferenca_preco if material_cadastrado else "",
                "Percentual Diferença Preço": percentual_diferenca_preco if material_cadastrado else "",
                "Data Última Revisão Preço": data_ultima_revisao_preco,
                "Usuário Última Revisão Preço": usuario_ultima_revisao_preco,
                "Leadtime Dias": leadtime,
                "Diagnóstico Comercial": diagnostico_comercial,
                "Leadtime": leadtime,
            }
        )

        # ====================================
        # CSV
        # ====================================

        dados_csv.append(
            {
                "Numero Pedido": numero_pedido,
                "Data Emissao": data_emissao,
                "Unidade Pedido": unidade,
                "Comprador": comprador,
                "Item": item,
                "Codigo Material": codigo_material,
                "Descricao": descricao,
                "Quantidade": quantidade,
                "Unidade Item": unidade_item,
                "Data Entrega": data_entrega,
                "Medida": medida,
                "Material": material,
                "Norma": norma,
                "NCM Pedido KSB": ncm,
                "NCM Cadastro": ncm_cadastrado,
                "ICMS Regra": icms_regra if icms_regra is not None else "",
                "IPI Regra": ipi_regra if ipi_regra is not None else "",
                "Valor Unitario": valor_unitario,
                "Valor Total": valor_total,
                "Valor Calculado": valor_calculado if regra_fiscal else "",
            }
        )

    return (pd.DataFrame(dados_csv), pd.DataFrame(analises))
