"""Regras puras para consolidação e reavaliação de pedidos."""


PENDING_STATUS = "PENDENTE/DIVERGENTE"


def can_reaudit(confirmed_audit, confirmed_implementation):
    return bool(confirmed_audit and confirmed_implementation)


def summarize_item_statuses(items):
    if not items:
        return PENDING_STATUS, PENDING_STATUS

    fiscal_status = "OK" if all(item.get("Status") == "OK" for item in items) else PENDING_STATUS
    commercial_status = (
        "OK"
        if all(item.get("Status Comercial") == "OK" for item in items)
        else PENDING_STATUS
    )
    return fiscal_status, commercial_status
