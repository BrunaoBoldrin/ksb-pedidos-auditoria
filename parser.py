import re
import pdfplumber
import pandas as pd
from database import buscar_material_por_codigo, localizar_regra_fiscal_por_ncm

from datetime import datetime

# ====================================
# FUNCOES AUXILIARES
# ====================================


def moeda_para_float(valor):
    valor = str(valor)

    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")
    valor = valor.replace("/1", "")
    valor = valor.strip()

    try:
        return float(valor)

    except:
        return 0.0


def normalizar_ncm(valor):
    return re.sub(r"\D", "", str(valor or ""))


def calcular_divisor_base(icms):
    """Mantém compatibilidade com os fatores que já eram usados no sistema.

    Para as alíquotas conhecidas, usa os divisores originais:
    ICMS 12% -> 0.7986
    ICMS 18% -> 0.7442

    Para outros ICMS, usa fallback genérico baseado em ICMS + 9,25%.
    """
    try:
        icms_float = float(icms)
    except:
        return 0.7442

    if abs(icms_float - 12.0) < 0.01:
        return 0.7986

    if abs(icms_float - 18.0) < 0.01:
        return 0.7442

    divisor = 1 - (icms_float / 100) - 0.0925

    if divisor <= 0:
        return 0.7442

    return divisor


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

        # ====================================
        # MATERIAL CADASTRADO -> NCM CADASTRADO -> REGRA FISCAL
        # ====================================

        material_cadastrado = buscar_material_por_codigo(codigo_material)

        ncm_cadastrado = ""
        regra_fiscal = None
        icms_regra = None
        ipi_regra = None

        if not material_cadastrado:
            divergencias.append(
                f"Material KSB não cadastrado na lista de materiais: {codigo_material}"
            )

        else:
            ncm_cadastrado = str(material_cadastrado.get("ncm") or "").strip()

            if not ncm_cadastrado:
                divergencias.append(
                    f"Material KSB {codigo_material} cadastrado sem NCM"
                )

            else:
                regra_fiscal = localizar_regra_fiscal_por_ncm(ncm_cadastrado)

                if normalizar_ncm(ncm) != normalizar_ncm(ncm_cadastrado):
                    divergencias.append(
                        f"NCM divergente (Cadastro: {ncm_cadastrado} | Pedido KSB: {ncm})"
                    )

                if not regra_fiscal:
                    divergencias.append(
                        f"Nenhuma regra fiscal encontrada para o NCM cadastrado: {ncm_cadastrado}"
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

        valor_calculado = 0.0

        if regra_fiscal:
            divisor_base = calcular_divisor_base(icms_regra)
            valor_base = (valor_unitario_float / divisor_base) * quantidade_float
            valor_calculado = valor_base * (1 + (float(ipi_regra or 0) / 100))
            valor_calculado = round(valor_calculado, 2)

            diferenca = abs(valor_calculado - valor_total_float)

            if diferenca > 1:
                divergencias.append(
                    f"Valor divergente (Calculado: {valor_calculado} | Pedido: {valor_total_float} | Diferença: {round(diferenca, 2)})"
                )

        # ====================================
        # LEADTIME
        # ====================================

        try:
            data_upload = datetime.today()

            data_entrega_dt = datetime.strptime(data_entrega, "%d.%m.%Y")

            leadtime = (data_entrega_dt - data_upload).days

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
                "Item": item,
                "Código Material": codigo_material,
                "Status": status_final,
                "NCM Pedido KSB": ncm,
                "NCM Cadastro": ncm_cadastrado,
                "ICMS Regra": icms_regra if icms_regra is not None else "",
                "IPI Regra": ipi_regra if ipi_regra is not None else "",
                "Valor Calculado": valor_calculado if regra_fiscal else "",
                "Leadtime": leadtime,
                "Divergencias": (" | ".join(divergencias) if divergencias else "-"),
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
