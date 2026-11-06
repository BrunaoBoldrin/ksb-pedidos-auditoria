"""Cálculo puro de uma peça. Não lê custos de arquivos nem executa fórmulas Excel."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from typing import Mapping


class PricingError(ValueError):
    pass


def number(value, label='Valor', minimum=Decimal('0'), maximum=Decimal('1000000000000')):
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        text = str(value).strip()
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        result = Decimal(text)
        if not result.is_finite() or result < minimum or result > maximum:
            raise ValueError()
        return result
    except (ValueError, InvalidOperation):
        raise PricingError(f'{label}: informe um número válido entre {minimum} e {maximum}.') from None


def review_date(value):
    try:
        result = date.fromisoformat(str(value)[:10])
        if result > date.today():
            raise ValueError()
        return result.isoformat()
    except (ValueError, TypeError):
        raise PricingError('Informe a data da revisão, sem data futura.') from None


def convert_amount(amount, source, target, base):
    source, target = str(source).upper(), str(target).upper()
    if source == target:
        return amount
    scales = {'KG': ('mass', Decimal('1000')), 'G': ('mass', Decimal('1')),
              'M': ('length', Decimal('1000')), 'MM': ('length', Decimal('1'))}
    if source in scales and target in scales and scales[source][0] == scales[target][0]:
        return amount * scales[source][1] / scales[target][1]
    if target == 'BAR' and source in ('MM', 'M'):
        length = number(base.get('length_mm'), 'Comprimento da barra', minimum=Decimal('0.000001'))
        return amount * (1000 if source == 'M' else 1) / length
    raise PricingError(f'Conversão de {source} para {target} não cadastrada.')


@dataclass(frozen=True)
class PriceCalculation:
    cost: Decimal
    gross_price: Decimal
    net_price: Decimal
    reviewed_on: str
    breakdown: dict
    lines: list
    parameters: dict

    def snapshot(self):
        def serial(value):
            if isinstance(value, Decimal): return str(value)
            if isinstance(value, dict): return {str(k): serial(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)): return [serial(v) for v in value]
            return value
        return serial(dict(cost=self.cost, gross_price=self.gross_price, net_price=self.net_price,
                           reviewed_on=self.reviewed_on, breakdown=self.breakdown,
                           lines=self.lines, parameters=self.parameters, formula_version=1, pieces=1))


def calculate_sheet(sheet: Mapping, bases: Mapping, fiscal_divisor=None) -> PriceCalculation:
    if sheet.get('confirmed') is not True or sheet.get('basis') not in ('NET', 'GROSS'):
        raise PricingError('Confirme a base comercial do preço da folha antes de publicar.')
    efficiency = number(sheet.get('efficiency', '1'), 'Eficiência', Decimal('0.000001'), Decimal('1'))
    margin = number(sheet.get('margin', '0'), 'Margem', maximum=Decimal('0.999999'))
    taxes = number(sheet.get('taxes', '0'), 'Impostos de venda', maximum=Decimal('0.999999'))
    commission = number(sheet.get('commission', '0'), 'Comissão', maximum=Decimal('0.999999'))
    divisor = 1 - margin - taxes - commission
    if divisor <= 0:
        raise PricingError('Margem, impostos e comissão devem somar menos de 100%.')
    dates = [review_date(sheet.get('reviewed_on'))]
    subtotals = {kind: Decimal('0') for kind in ('material','component','process','service')}
    evidence = []
    if not sheet.get('lines'):
        raise PricingError('Inclua ao menos uma linha na composição de uma peça.')
    for line in sheet['lines']:
        kind = line.get('kind')
        try:
            item = bases[(kind, int(line['base_id']))]
        except (KeyError, ValueError, TypeError):
            raise PricingError('Insumo ou processo não cadastrado.') from None
        if kind not in subtotals or item.get('active') is not True:
            raise PricingError('Insumo ou processo inativo.')
        dates.append(review_date(item.get('reviewed_on')))
        price = number(item.get('price'), 'Custo base')
        factor = number(item.get('factor', '1'), 'Fator líquido de compra', maximum=Decimal('1'))
        if kind == 'process' and item['unit'] == 'H':
            duration = number(line.get('hours', '0'), 'Horas') + number(line.get('minutes', '0'), 'Minutos') / 60
            people = number(line.get('people', '1'), 'Pessoas', Decimal('1'), Decimal('1000'))
            if people != people.to_integral_value() or duration <= 0:
                raise PricingError('Informe pessoas inteiras e tempo positivo para a operação.')
            amount = duration * (people if item.get('per_person', True) else 1)
        else:
            quantity = number(line.get('quantity', '1'), 'Quantidade por peça', Decimal('0.000000001'))
            if kind == 'material' and line.get('mode') == 'BLANK':
                length = number(line.get('blank_length'), 'Comprimento blank', Decimal('0.000001'))
                width = number(line.get('blank_width'), 'Largura blank', Decimal('0.000001'))
                pl = number(line.get('piece_length'), 'Comprimento peça', Decimal('0.000001'))
                pw = number(line.get('piece_width'), 'Largura peça', Decimal('0.000001'))
                if not ((pl <= length and pw <= width) or (pw <= length and pl <= width)):
                    raise PricingError('As dimensões da peça excedem o blank informado.')
                if item['unit'] != 'KG':
                    raise PricingError('O cálculo de blank requer custo por kg.')
                kg_m2 = number(item.get('kg_m2'), 'Massa por área', Decimal('0.000001'))
                amount = quantity * length * width / 1000000 * kg_m2
            else:
                consumption = number(line.get('consumption', '1'), 'Consumo por peça', Decimal('0.000000001'))
                amount = quantity * convert_amount(consumption, line.get('unit', item['unit']), item['unit'], item)
        cost = amount * price * factor
        subtotals[kind] += cost
        evidence.append(dict(input=dict(line), base=dict(item), amount=amount, nominal_cost=cost))
    subtotals['process_nominal'] = subtotals['process']
    subtotals['process'] /= efficiency
    subtotals['tool'] = number(sheet.get('tool_cost', '0'), 'Amortização unitária')
    total = sum(subtotals[k] for k in ('material','component','process','service','tool'))
    if total <= 0 or total > Decimal('1000000000000'):
        raise PricingError('O custo total da peça deve ser positivo e estar dentro do limite.')
    if sheet.get('rounding') not in ('UP_REAL', 'CENT'):
        raise PricingError('Selecione a regra de arredondamento.')
    gross = (total / divisor).quantize(Decimal('1') if sheet['rounding']=='UP_REAL' else Decimal('0.01'),
                                      rounding=ROUND_CEILING if sheet['rounding']=='UP_REAL' else ROUND_HALF_UP)
    if gross > Decimal('1000000000000'):
        raise PricingError('Preço calculado acima do limite de armazenamento.')
    if sheet['basis'] == 'GROSS':
        tax_divisor = number(fiscal_divisor, 'Divisor fiscal', Decimal('0.000001'), Decimal('1'))
    else:
        tax_divisor = Decimal('1')
    net = (gross * tax_divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if net <= 0:
        raise PricingError('O preço líquido deve ser maior que zero.')
    return PriceCalculation(total, gross.quantize(Decimal('0.01')), net, min(dates), subtotals,
                            evidence, dict(efficiency=efficiency, margin=margin, taxes=taxes,
                                           commission=commission, rounding=sheet['rounding'],
                                           basis=sheet['basis'], fiscal_divisor=tax_divisor))
