"""Orquestração testável do processamento e reprocessamento de pedidos."""

from hashlib import sha256

from audit_rules import can_reaudit


class ReauditConfirmationRequired(ValueError):
    pass


def upload_fingerprints(files):
    return [
        (uploaded_file.name, sha256(uploaded_file.getvalue()).hexdigest())
        for uploaded_file in files
    ]


def approved_orders_in_batch(files, extract_order_number_func, is_approved_func):
    approved = []
    for uploaded_file in files:
        order_number = extract_order_number_func(uploaded_file.name)
        if order_number and is_approved_func(order_number) and order_number not in approved:
            approved.append(order_number)
    return approved


def process_uploaded_orders(
    files,
    user,
    reaudit_order_numbers,
    confirmations,
    process_pdf_func,
    register_audit_func,
):
    reaudit_order_numbers = {str(number) for number in (reaudit_order_numbers or [])}
    confirmed_audit, confirmed_implementation = confirmations
    if reaudit_order_numbers and not can_reaudit(confirmed_audit, confirmed_implementation):
        raise ReauditConfirmationRequired("As duas confirmações são obrigatórias para reavaliar o pedido.")

    results = []
    for uploaded_file in files:
        extracted_data, analysis = process_pdf_func(uploaded_file.name)
        if analysis.empty:
            raise ValueError(f"Nenhum item foi identificado no arquivo {uploaded_file.name}.")

        order_data = analysis.iloc[0].to_dict()
        items = analysis.to_dict("records")
        order_number = str(order_data.get("Pedido") or order_data.get("Numero Pedido") or "")
        if not order_number.strip():
            raise ValueError(f"Número do pedido não identificado no arquivo {uploaded_file.name}.")
        is_reaudit = order_number in reaudit_order_numbers
        register_audit_func(
            dados_pedido=order_data,
            itens=items,
            usuario=user,
            reavaliacao=bool(is_reaudit),
            confirmou_auditoria=bool(confirmed_audit) if is_reaudit else False,
            confirmou_implantacao=bool(confirmed_implementation) if is_reaudit else False,
            arquivo_pdf=uploaded_file.name,
        )
        results.append((extracted_data, analysis))
    return results
