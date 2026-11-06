"""Diagnóstico comercial usando exclusivamente uma referência publicada da folha."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import unicodedata

from price_rules import is_price_outdated
from pricing_calculator import number


def unit(value):
    value=unicodedata.normalize('NFKD',str(value or '').upper()).encode('ascii','ignore').decode().strip()
    return 'UN' if value in ('UN','UNID','UNIDADE','PC','PCS','PEC','PECA','PECAS','EA') else value


def currency(value):
    return 'R$ '+f'{value:,.2f}'.replace(',','_').replace('.',',').replace('_','.')


def evaluate_price(order_price,quantity,order_unit,reference,today=None,settings=None):
    from system_settings import normalize_system_settings
    settings=normalize_system_settings(settings)
    today=today or date.today()
    result=dict(status='PENDENTE - SEM FOLHA DE PROCESSO ATIVA',diagnosis='',price=None,
                difference=None,total_difference=None,percentage=None)
    state=(reference or {}).get('state','MISSING')
    if state!='ACTIVE' or not reference.get('price'):
        reasons={'MISSING':'Cadastre e ative uma folha de processo válida para este item.',
                 'INVALID':'A folha ativa não possui cálculo publicado válido.',
                 'UNIT_CHANGED':'A unidade do cadastro mudou. Confira a composição de uma peça e republique a folha.',
                 'FISCAL_CHANGED':'A regra fiscal mudou após a publicação. Confira a base comercial e republique a folha.'}
        result['diagnosis']='FOLHA DE PROCESSO PENDENTE\n'+reasons.get(state,reasons['INVALID'])
        return result
    price=number(reference['price'],'Preço da folha',Decimal('0.01'))
    order=number(order_price,'Preço do pedido')
    qty=number(quantity,'Quantidade',Decimal('0.000001'))
    difference=(order-price).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    total=(difference*qty).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    percentage=(difference/price*100).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    reasons=[]
    if unit(order_unit)!=unit(reference.get('unit')):
        reasons.append('UNIDADE DIVERGENTE: unidade do pedido não corresponde à unidade da folha.')
    if is_price_outdated(reference.get('reviewed_on'),today,max_age_days=settings.price_review_days):
        reasons.append('REVISÃO VENCIDA: PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.')
    if abs(difference)>Decimal(str(settings.price_difference_tolerance)):
        reasons.append('PREÇO DIVERGENTE: negociar ou revisar o pedido KSB.')
    status='OK' if not reasons else ('PENDENTE - PREÇO DIVERGENTE' if len(reasons)==1 and reasons[0].startswith('PREÇO DIVERGENTE') else 'PENDENTE - REVISÃO DA FOLHA')
    details=[f'Origem: folha de processo, revisão {reference.get("revision")}. Revisão de custos: {reference.get("reviewed_on") or "-"}.',
             f'Pedido KSB: {currency(order)} | Folha: {currency(price)} | Diferença unitária: {currency(difference)}.',
             f'Diferença total: {currency(total)} | Variação: {percentage}%.']
    result.update(status=status,diagnosis='\n'.join(reasons+details) if reasons else 'PREÇO OK\n'+'\n'.join(details),
                  price=price,difference=difference,total_difference=total,percentage=percentage)
    return result
