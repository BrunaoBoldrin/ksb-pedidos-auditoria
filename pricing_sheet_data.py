"""Worksheet rows retain shared cost identity and separate per-piece inputs."""
from decimal import Decimal

from pricing_calculator import PricingError, number
from pricing_workspace import KINDS

COMMON=['Base','Quantidade','Consumo','Unidade','Preço (R$)']
COLUMNS={
 'material':COMMON+['Modo','Blank C (mm)','Blank L (mm)','Peça C (mm)','Peça L (mm)'],
 'component':COMMON+['Observação'],
 'process':['Base','Etapa','Horas','Minutos','Pessoas']+COMMON[1:],
 'service':COMMON+['Observação']}


def base_label(base):return base['code']+' — '+base['description']


def sheet_rows(data,catalog,include_proposals=True):
    lookups={kind:{int(b['id']):b for b in bases} for kind,bases in catalog.items()}
    proposals={(p['kind'],int(p['base_id'])):p for p in data.get('proposed_prices',[])} if include_proposals else {}
    rows={kind:[] for kind in KINDS}
    for line in data.get('lines',[]):
        kind=line['kind'];base=lookups.get(kind,{}).get(int(line['base_id']))
        if not base:raise PricingError('Um custo da composição não foi encontrado no catálogo.')
        proposal=proposals.get((kind,base['id']))
        row={'Base':base_label(base),'Quantidade':float(line.get('quantity',1)),
             'Consumo':float(line.get('consumption',1)),'Unidade':line.get('unit',base['unit']),
             'Preço (R$)':str(proposal['price'] if proposal else base['price']),
             'Modo':line.get('mode','CONSUMO'),'Etapa':line.get('stage','Execução'),
             'Horas':float(line.get('hours',0)),'Minutos':float(line.get('minutes',0)),
             'Pessoas':float(line.get('people',1)),'Observação':line.get('note','')}
        for label,field in [('Blank C (mm)','blank_length'),('Blank L (mm)','blank_width'),('Peça C (mm)','piece_length'),('Peça L (mm)','piece_width')]:
            row[label]=float(line.get(field,0))
        rows[kind].append(row)
    return rows


def empty_row():
    return {'Base':'','Quantidade':1.,'Consumo':1.,'Unidade':'UN','Preço (R$)':'','Modo':'CONSUMO',
            'Etapa':'Execução','Horas':0.,'Minutos':0.,'Pessoas':1,'Observação':'',
            'Blank C (mm)':0.,'Blank L (mm)':0.,'Peça C (mm)':0.,'Peça L (mm)':0.}


def composition_from_rows(rows,catalog,today):
    lines=[];proposals={}
    for kind,entries in rows.items():
        lookup={base_label(base):base for base in catalog[kind]}
        for row in entries:
            if not row.get('Base'):
                if row.get('Preço (R$)') or row.get('Observação') or row.get('Horas') or row.get('Minutos'):
                    raise PricingError('Escolha o custo base para cada linha preenchida.')
                continue
            base=lookup.get(row['Base'])
            if base is None:raise PricingError('Custo base inválido na composição.')
            line=dict(kind=kind,base_id=base['id'],quantity=str(row.get('Quantidade',1)),
                      consumption=str(row.get('Consumo',1)),unit=row.get('Unidade') or base['unit'],
                      mode=row.get('Modo') or 'CONSUMO',stage=row.get('Etapa') or 'Execução',
                      hours=str(row.get('Horas') or 0),minutes=str(row.get('Minutos') or 0),
                      people=str(row.get('Pessoas') or 1),note=str(row.get('Observação') or ''))
            for label,field in [('Blank C (mm)','blank_length'),('Blank L (mm)','blank_width'),('Peça C (mm)','piece_length'),('Peça L (mm)','piece_width')]:
                line[field]=str(row.get(label) or 0)
            lines.append(line)
            value=row.get('Preço (R$)')
            if value not in (None,''):
                price=number(value,'Preço da linha')
                if price!=Decimal(str(base['price'])):
                    identity=(kind,base['id'])
                    proposal=dict(kind=kind,base_id=base['id'],price=str(price),version=base['version'],reviewed_on=today.isoformat())
                    if identity in proposals and proposals[identity]['price']!=proposal['price']:
                        raise PricingError('O mesmo custo compartilhado deve ter um único preço em toda a folha.')
                    proposals[identity]=proposal
    return lines,list(proposals.values())
