"""Fiscal inputs from the item's registered rule, using the analyzer's contract."""
import re
from decimal import Decimal

from pricing_calculator import number, PricingError


def parameters_for_item(item):
    if not item:
        raise PricingError('Item KSB não encontrado.')
    ncm=re.sub(r'\D','',str(item.get('ncm') or ''))
    if len(ncm)!=8:
        raise PricingError('NCM ausente ou inválido. Preencha os 8 dígitos no cadastro do item para calcular o preço.')
    if item.get('aliquota_icms') is None or item.get('aliquota_ipi') is None:
        raise PricingError(f'Cadastre uma regra fiscal ativa para o NCM {ncm} para calcular o preço.')
    icms=number(item['aliquota_icms'],'ICMS cadastrado',maximum=Decimal('99.999999'))
    ipi=number(item['aliquota_ipi'],'IPI cadastrado',maximum=Decimal('99.999999'))
    # Keep the same conversion/rounding already used to evaluate KSB orders.
    from parser import calcular_divisor_base, PIS_PERCENTUAL, COFINS_PERCENTUAL
    if 1-icms/100-Decimal(str(PIS_PERCENTUAL))-Decimal(str(COFINS_PERCENTUAL))<=0:
        raise PricingError('Alíquotas cadastradas não permitem formar um preço líquido positivo.')
    divisor=Decimal(str(calcular_divisor_base(icms)))
    return dict(source='NCM',basis='GROSS',ncm=ncm,unit=item.get('unidade_medida'),
                rule_id=item.get('rule_id'),icms=str(icms),ipi=str(ipi),
                pis=str(Decimal(str(PIS_PERCENTUAL))*100),cofins=str(Decimal(str(COFINS_PERCENTUAL))*100),
                taxes=str(1-divisor),fiscal_divisor=str(divisor))
