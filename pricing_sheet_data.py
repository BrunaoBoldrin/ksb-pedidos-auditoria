"""Worksheet rows retain shared cost identity and separate per-piece inputs."""
from decimal import Decimal
from copy import deepcopy
import json

from pricing_calculator import PricingError, number
from pricing_workspace import KINDS

META=['_base_original','_price_original','_proposal_version','_line_original']
COMMON=['Base','Quantidade','Consumo','Unidade','Unidade do custo','Custo atual (R$)','Preço (R$)']
COLUMNS={
 'material':['Posição']+COMMON+['Modo','Blank C (mm)','Blank L (mm)','Peça C (mm)','Peça L (mm)']+META,
 'component':['Posição']+COMMON+['Fornecedor','Observação']+META,
 'process':['Posição','Base','Etapa','Horas','Minutos','Pessoas']+COMMON[1:]+META,
 'service':['Posição','Código operação']+COMMON+['Fornecedor','Observação']+META}
TOOL_COLUMNS={'Descrição':'description','Quantidade anual':'annual_quantity','Custo total (R$)':'cost',
              'Quantidade para amortização':'amortization_quantity'}


def tooling_rows(data):
    return [{label:'' if tool.get(field) is None else str(tool[field]) for label,field in TOOL_COLUMNS.items()}
            for tool in data.get('tooling',[])]


def tooling_from_rows(rows):
    result=[]
    for row in rows:
        if not any(str(row.get(label) or '').strip() for label in TOOL_COLUMNS):continue
        description=str(row.get('Descrição') or '').strip()
        if not description:raise PricingError('Informe a descrição do ferramental.')
        annual=row.get('Quantidade anual')
        result.append(dict(description=description,
                           annual_quantity=str(number(annual,'Quantidade anual')) if annual not in (None,'') else '',
                           cost=str(number(row.get('Custo total (R$)'),'Custo do ferramental')),
                           amortization_quantity=str(number(row.get('Quantidade para amortização'),'Quantidade para amortização',Decimal('0.000001')))))
    return result


def base_label(base):return base['code']+' — '+base['description']


def sheet_rows(data,catalog,include_proposals=True):
    lookups={kind:{int(b['id']):b for b in bases} for kind,bases in catalog.items()}
    proposals={(p['kind'],int(p['base_id'])):p for p in data.get('proposed_prices',[])} if include_proposals else {}
    rows={kind:[] for kind in KINDS}
    for line in data.get('lines',[]):
        kind=line['kind'];base=lookups.get(kind,{}).get(int(line['base_id']))
        if not base:raise PricingError('Um custo da composição não foi encontrado no catálogo.')
        proposal=proposals.get((kind,base['id']))
        row={'Posição':str(line.get('position','')),'Fornecedor':line.get('supplier',''),
             'Código operação':line.get('operation_code',''),'_line_original':json.dumps(line,ensure_ascii=False),
             'Base':base_label(base),'Quantidade':float(line.get('quantity',1)),
             'Consumo':float(line.get('consumption',1)),'Unidade':line.get('unit',base['unit']),
             'Unidade do custo':base['unit'],'Custo atual (R$)':str(base['price']),
             'Preço (R$)':str(proposal['price'] if proposal else base['price']),
             '_base_original':str(base['id']),'_price_original':str(proposal['price'] if proposal else base['price']),
             '_proposal_version':proposal['version'] if proposal else base['version'],
             'Modo':line.get('mode','CONSUMO'),'Etapa':line.get('stage','Execução'),
             'Horas':float(line.get('hours',0)),'Minutos':float(line.get('minutes',0)),
             'Pessoas':float(line.get('people',1)),'Observação':line.get('note','')}
        for label,field in [('Blank C (mm)','blank_length'),('Blank L (mm)','blank_width'),('Peça C (mm)','piece_length'),('Peça L (mm)','piece_width')]:
            row[label]=float(line.get(field,0))
        rows[kind].append(row)
    return rows


def empty_row():
    return {'Posição':'','Fornecedor':'','Código operação':'','_line_original':'{}',
            'Base':'','Quantidade':1.,'Consumo':1.,'Unidade':'UN','Preço (R$)':'','Modo':'CONSUMO',
            'Etapa':'Execução','Horas':0.,'Minutos':0.,'Pessoas':1,'Observação':'',
            'Unidade do custo':'','Custo atual (R$)':'','_base_original':'','_price_original':'','_proposal_version':'',
            'Blank C (mm)':0.,'Blank L (mm)':0.,'Peça C (mm)':0.,'Peça L (mm)':0.}


def normalize_rows(rows,bases,refresh_prices=False):
    """A base substitution loads that base's price; existing proposals keep their version."""
    lookup={base_label(base):base for base in bases}
    result=deepcopy(rows)
    for row in result:
        base=lookup.get(row.get('Base'))
        if base is None:continue
        changed=str(row.get('_base_original',''))!=str(base['id'])
        if refresh_prices or changed:
            previous=row.get('_price_original','')
            current=row.get('Preço (R$)','')
            if refresh_prices or current in (None,'') or str(current)==str(previous):
                row['Preço (R$)']=str(base['price'])
            if not row.get('_base_original'):row['Unidade']=base['unit']
            row['_base_original']=str(base['id'])
            row['_proposal_version']=base['version']
        row['Unidade do custo']=base['unit'];row['Custo atual (R$)']=str(base['price'])
        row['_price_original']=str(row.get('Preço (R$)') or '')
    return result


def composition_from_rows(rows,catalog,today):
    lines=[];proposals={}
    for kind,entries in rows.items():
        lookup={base_label(base):base for base in catalog[kind]}
        for row in normalize_rows(entries,catalog[kind]):
            if not row.get('Base'):
                if row.get('Preço (R$)') or row.get('Observação') or row.get('Horas') or row.get('Minutos'):
                    raise PricingError('Escolha o custo base para cada linha preenchida.')
                continue
            base=lookup.get(row['Base'])
            if base is None:raise PricingError('Custo base inválido na composição.')
            line=json.loads(row.get('_line_original') or '{}')
            line.update(kind=kind,base_id=base['id'],quantity=str(row.get('Quantidade',1)),
                      consumption=str(row.get('Consumo',1)),unit=row.get('Unidade') or base['unit'],
                      mode=row.get('Modo') or 'CONSUMO',stage=row.get('Etapa') or 'Execução',
                      hours=str(row.get('Horas') or 0),minutes=str(row.get('Minutos') or 0),
                      people=str(row.get('Pessoas') or 1),note=str(row.get('Observação') or ''),
                      position=str(row.get('Posição') or ''),supplier=str(row.get('Fornecedor') or ''),
                      operation_code=str(row.get('Código operação') or ''))
            for label,field in [('Blank C (mm)','blank_length'),('Blank L (mm)','blank_width'),('Peça C (mm)','piece_length'),('Peça L (mm)','piece_width')]:
                line[field]=str(row.get(label) or 0)
            lines.append(line)
            value=row.get('Preço (R$)')
            if value not in (None,''):
                price=number(value,'Preço da linha')
                if price!=Decimal(str(base['price'])):
                    identity=(kind,base['id'])
                    proposal=dict(kind=kind,base_id=base['id'],price=str(price),version=int(row.get('_proposal_version') or base['version']),reviewed_on=today.isoformat())
                    if identity in proposals and proposals[identity]['price']!=proposal['price']:
                        raise PricingError('O mesmo custo compartilhado deve ter um único preço em toda a folha.')
                    proposals[identity]=proposal
    return lines,list(proposals.values())
