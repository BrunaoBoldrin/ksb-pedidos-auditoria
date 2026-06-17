import re
import pdfplumber
import pandas as pd

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

    pedido_match = re.search(
        r"Pedido\s+(\d+)",
        texto_completo
    )

    numero_pedido = (
        pedido_match.group(1)
        if pedido_match else ""
    )

    # ====================================
    # DATA EMISSAO
    # ====================================

    datas = re.findall(
        r"\d{2}\.\d{2}\.\d{4}",
        texto_completo
    )

    data_emissao = (
        datas[0]
        if len(datas) > 0 else ""
    )

    # ====================================
    # UNIDADE
    # ====================================

    unidade = ""

    if re.search(
        r"Jundiai",
        texto_completo,
        re.IGNORECASE
    ):

        unidade = "Jundiai"

    elif re.search(
        r"Varzea",
        texto_completo,
        re.IGNORECASE
    ):

        unidade = "Varzea Paulista"

    # ====================================
    # COMPRADOR
    # ====================================

    comprador = ""

    linhas_documento = texto_completo.splitlines()

    for i, linha in enumerate(linhas_documento):

        if "Contato Grupo de Compras" in linha:

            if i + 1 < len(linhas_documento):

                proxima_linha = linhas_documento[i + 1].strip()

                comprador_match = re.search(
                    r"([A-Za-zÀ-Úà-ú\s]+)\s+\d+",
                    proxima_linha
                )

                if comprador_match:

                    comprador = comprador_match.group(1).strip()

                break

    # ====================================
    # ITENS
    # ====================================

    matches = list(re.finditer(
        r"^\s*(000\d{2})\s+(\d{8})",
        texto_completo,
        re.MULTILINE
    ))

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

        item_match = re.search(
            r"(000\d{2})",
            bloco
        )

        item = (
            item_match.group(1)
            if item_match else ""
        )

        # ====================================
        # CODIGO MATERIAL
        # ====================================

        codigo_match = re.search(
            r"000\d{2}\s+(\d{8})",
            bloco
        )

        codigo_material = (
            codigo_match.group(1)
            if codigo_match else ""
        )

        # ====================================
        # DATA ENTREGA
        # ====================================

        data_entrega_match = re.search(
            r"(\d{2}\.\d{2}\.\d{4})",
            bloco
        )

        data_entrega = (
            data_entrega_match.group(1)
            if data_entrega_match else ""
        )

        # ====================================
        # QUANTIDADE
        # ====================================

        quantidade_match = re.search(
            r"\d{2}\.\d{2}\.\d{4}\s+(\d+(?:,\d+)?)",
            bloco
        )

        quantidade = (
            quantidade_match.group(1)
            if quantidade_match else ""
        )

        # ====================================
        # UNIDADE ITEM
        # ====================================

        unidade_item_match = re.search(
            r"\d+(?:,\d+)?\s+(PEÇ|M2|KG|UN|CJ|PC|LT|TON|BAR|ROL)",
            bloco
        )

        unidade_item = (
            unidade_item_match.group(1)
            if unidade_item_match else ""
        )

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

        medida_match = re.search(
            r"tamanho/dimensão:\s*(.*)",
            bloco
        )

        medida = (
            medida_match.group(1).strip()
            if medida_match else ""
        )

        # ====================================
        # MATERIAL
        # ====================================

        material_match = re.search(
            r"Mat\.básic:\s*(.*)",
            bloco
        )

        material = (
            material_match.group(1).strip()
            if material_match else ""
        )

        # ====================================
        # NORMA
        # ====================================

        norma = ""

        for linha in linhas:

            if "Desenho/Norma:" in linha:

                norma = linha.split(
                    "Desenho/Norma:"
                )[1].strip()

                norma = re.sub(
                    r"\s+\d{2}$",
                    "",
                    norma
                )

                break

        # ====================================
        # NCM
        # ====================================

        ncm_match = re.search(
            r"NCM:\s*(.*)",
            bloco
        )

        ncm = (
            ncm_match.group(1).strip()
            if ncm_match else ""
        )

        # ====================================
        # VALOR UNITARIO
        # ====================================

    

        # ====================================
        # VALOR UNITARIO
        # ====================================

        valor_unitario_match = re.search(
            r"(\d{1,3}(?:\.\d{3})*,\d{2}\/1)",
            bloco
        )

        valor_unitario = (
            valor_unitario_match.group(1)
            if valor_unitario_match else ""
        )

        # ====================================
        # VALOR TOTAL
        # ====================================

        valor_total = ""

        linha_item = ""

        for linha in linhas:

            if re.search(r"000\d{2}", linha):

                linha_item = linha

                break

        
valores_linha = re.findall(
    r"(\d{1,3}(?:\.\d{3})*,\d{2})",
    linha_item
)



        if len(valores_linha) > 0:

            valor_total = valores_linha[-1]

        # ====================================
        # VALIDACOES
        # ====================================

        divergencias = []

        # ====================================
        # NCM
        # ====================================

        if "LATÃO" in material.upper():

            ncm_correto = "7419.80.90"

        else:

            ncm_correto = "7325.99.10"

        if ncm != ncm_correto:

            divergencias.append(

                f"NCM divergente "
                f"(Esperado: {ncm_correto} | "
                f"Encontrado: {ncm})"
            )

        # ====================================
        # VALIDACAO VALOR
        # ====================================

        quantidade_float = moeda_para_float(
            quantidade
        )

        valor_unitario_float = moeda_para_float(
            valor_unitario
        )

        valor_total_float = moeda_para_float(
            valor_total
        )

        # ====================================
        # LATÃO
        # ====================================

        if ncm == "7419.80.90":

            valor_base = (
                valor_unitario_float / 0.7986
            ) * quantidade_float

            valor_calculado = (
                valor_base * 1.0325
            )

        # ====================================
        # OUTROS
        # ====================================

        else:

            valor_base = (
                valor_unitario_float / 0.7442
            ) * quantidade_float

            valor_calculado = (
                valor_base * 1.065
            )

        valor_calculado = round(
            valor_calculado,
            2
        )

        diferenca = abs(
            valor_calculado - valor_total_float
        )

        if diferenca > 1:

            divergencias.append(

                f"Valor divergente "
                f"(Calculado: {valor_calculado} | "
                f"Pedido: {valor_total_float} | "
                f"Diferença: {round(diferenca, 2)})"
            )

        # ====================================
        # LEADTIME
        # ====================================

        try:

            data_upload = datetime.today()

            data_entrega_dt = datetime.strptime(
                data_entrega,
                "%d.%m.%Y"
            )

            leadtime = (
                data_entrega_dt - data_upload
            ).days

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

        analises.append({

            "Pedido": numero_pedido,
            "Item": item,
            "Status": status_final,
            "Leadtime": leadtime,

            "Divergencias": (
                " | ".join(divergencias)
                if divergencias else "-"
            )
        })

        # ====================================
        # CSV
        # ====================================

        dados_csv.append({

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
            "NCM": ncm,

            "Valor Unitario": valor_unitario,
            "Valor Total": valor_total
        })

    # ====================================
    # RETORNO FINAL
    # ====================================

    return (
        pd.DataFrame(dados_csv),
        pd.DataFrame(analises)
    )

