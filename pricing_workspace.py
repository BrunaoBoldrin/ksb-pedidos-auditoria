"""Serializable editing buffers and Decimal-preserving catalog changes."""
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from pricing_calculator import PricingError, number, review_date

KINDS={'material':'Matérias-primas','component':'Componentes','process':'Processos internos','service':'Serviços externos'}
LABEL_TO_KIND={label:kind for kind,label in KINDS.items()}
COST_COLUMNS=['Selecionar','_key','Categoria','Código','Descrição','Unidade','Preço (R$)','Fator líquido',
              'kg/m²','Comprimento barra (mm)','Por operador','Ativo','Revisão','Observações']
PROFILE_COLUMNS=['Selecionar','_key','Perfil','Eficiência (%)','Impostos (%)','Arredondamento','Ativo','Revisão']
ROUNDINGS={'CENT':'Centavos','UP_REAL':'Para cima ao real inteiro'}


def cost_row(kind,base):
    return dict(zip(COST_COLUMNS,[False,f'{kind}:{base["id"]}',KINDS[kind],base['code'],base['description'],base['unit'],
                  str(base['price']),str(base.get('factor',1)),str(base.get('kg_m2') or ''),str(base.get('length_mm') or ''),
                  base.get('per_person',True),base.get('active',True),str(base['reviewed_on']),base.get('note','')]))


def profile_row(profile):
    data=profile['data']
    return dict(zip(PROFILE_COLUMNS,[False,f'profile:{profile["id"]}',profile['code'],str(Decimal(str(data['efficiency']))*100),
                  str(Decimal(str(data['taxes']))*100),ROUNDINGS[data['rounding']],profile.get('active',True),str(profile['reviewed_on'])]))


def new_workspace(snapshot):
    originals={f'{kind}:{base["id"]}':deepcopy(base) for kind,bases in snapshot['bases'].items() for base in bases}
    profiles={f'profile:{p["id"]}':deepcopy(p) for p in snapshot['profiles']}
    return dict(version=snapshot['version'],originals=originals,profile_originals=profiles,
                costs=[cost_row(kind,base) for kind,bases in snapshot['bases'].items() for base in bases],
                profiles=[profile_row(p) for p in snapshot['profiles']],deleted=[],epoch=0,key=uuid4().hex)


def _same_number(left,right):
    if left in (None,'') or right in (None,''):return left in (None,'') and right in (None,'')
    return number(left)==number(right)


def workspace_changes(workspace,costs,profiles,today):
    changes=[];profile_changes=[]
    for row in costs:
        old=workspace['originals'].get(row.get('_key'))
        if not old and not any(str(row.get(col) or '').strip() for col in ('Código','Descrição','Preço (R$)')):continue
        kind=LABEL_TO_KIND.get(row.get('Categoria'))
        if kind is None:raise PricingError('Escolha a categoria de cada custo novo.')
        if old and not row['_key'].startswith(kind+':'):raise PricingError('A categoria de um custo existente não pode ser alterada.')
        data=dict(code=str(row.get('Código') or '').strip(),description=str(row.get('Descrição') or '').strip(),
                  unit=row.get('Unidade'),price=str(number(row.get('Preço (R$)'),'Preço')),
                  factor=str(number(row.get('Fator líquido',1),'Fator líquido',maximum=Decimal('1'))),
                  kg_m2=str(number(row['kg/m²'])) if row.get('kg/m²') not in (None,'') else None,
                  length_mm=str(number(row['Comprimento barra (mm)'])) if row.get('Comprimento barra (mm)') not in (None,'') else None,
                  per_person=bool(row.get('Por operador',True)),active=bool(row.get('Ativo',True)),
                  reviewed_on=review_date(row.get('Revisão')),note=str(row.get('Observações') or ''))
        numeric={'price','factor','kg_m2','length_mm'}
        changed=not old or any(not _same_number(data[f],old.get(f)) if f in numeric else data[f]!=old.get(f) for f in data)
        if changed:
            if old:
                data.update(id=old['id'],version=old['version'])
                if data['reviewed_on']==str(old['reviewed_on']) and any(not _same_number(data[f],old.get(f)) for f in numeric):
                    data['reviewed_on']=today.isoformat()
            changes.append((kind,data))
    for row in profiles:
        old=workspace['profile_originals'].get(row.get('_key'))
        if not old and not str(row.get('Perfil') or '').strip():continue
        rounding=next((key for key,label in ROUNDINGS.items() if label==row.get('Arredondamento')),None)
        if rounding is None:raise PricingError('Escolha o arredondamento do perfil.')
        data=dict(code=str(row.get('Perfil') or '').strip(),data=dict(efficiency=str(number(row.get('Eficiência (%)'))/100),
                  taxes=str(number(row.get('Impostos (%)'))/100),rounding=rounding),
                  reviewed_on=review_date(row.get('Revisão')),active=bool(row.get('Ativo',True)))
        changed=not old or data['code']!=old['code'] or data['active']!=old.get('active',True) or data['reviewed_on']!=str(old['reviewed_on'])
        if old:
            changed=changed or any(not _same_number(data['data'][f],old['data'][f]) for f in ('efficiency','taxes')) or data['data']['rounding']!=old['data']['rounding']
        if changed:
            if old:
                data.update(id=old['id'],version=old['version'])
                if data['reviewed_on']==str(old['reviewed_on']) and data['data']!=old['data']:data['reviewed_on']=today.isoformat()
            profile_changes.append(data)
    return changes,profile_changes,list(workspace['deleted'])
