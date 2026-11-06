"""Cadastro técnico: contratos sem campos de preço ou revisão comercial."""
from io import BytesIO
import unicodedata

import pandas as pd
import database

COLUMNS=['Código Material','Descrição','Material','Norma','NCM','Unidade',
         'Código Interno Jundiaí','Código Interno Várzea']
FIELDS=['codigo_material','descricao','material','norma','ncm','unidade_medida',
        'codigo_interno_jundiai','codigo_interno_varzea']


def list_items():
    with database._cursor() as c:
        c.execute('SELECT '+','.join(FIELDS)+' FROM materiais ORDER BY codigo_material')
        return c.fetchall()


def get_item(code):
    with database._cursor() as c:
        c.execute('SELECT '+','.join(FIELDS)+' FROM materiais WHERE BTRIM(codigo_material)=%s',(str(code).strip(),))
        row=c.fetchone()
        return dict(zip(FIELDS,row)) if row else None


def require_item_editor(c,actor):
    c.execute('SELECT perfil,ativo FROM usuarios WHERE usuario=%s',(actor,))
    row=c.fetchone()
    if not row or row[1]!=1 or row[0] not in ('ADMIN','PROCESSISTA'):
        raise PermissionError('Usuário sem autorização para editar o cadastro técnico.')


def save_item(values,actor):
    data=[database._limpar_texto(values.get(field,'')) for field in FIELDS]
    if not data[0] or not data[1]:raise ValueError('Informe código KSB e descrição.')
    with database._cursor(commit=True) as c:
        require_item_editor(c,actor)
        assignments=','.join(f'{field}=EXCLUDED.{field}' for field in FIELDS[1:])
        c.execute('INSERT INTO materiais ('+','.join(FIELDS)+') VALUES('+','.join(['%s']*8)+
                  ') ON CONFLICT(codigo_material) DO UPDATE SET '+assignments,tuple(data))


def delete_item(code,actor):
    with database._cursor(commit=True) as c:
        require_item_editor(c,actor)
        c.execute('SELECT 1 FROM pricing_sheets WHERE material_code=%s',(code,))
        if c.fetchone():raise ValueError('Item possui folha/histórico vinculado e deve ser preservado.')
        c.execute('DELETE FROM materiais WHERE codigo_material=%s',(code,))


def import_items(file):
    def normalize(s):
        return unicodedata.normalize('NFKD',str(s).lower()).encode('ascii','ignore').decode().replace('_',' ').strip()
    aliases={normalize(c):c for c in COLUMNS}
    aliases.update({'codigo material':'Código Material','cod material':'Código Material','unidade medida':'Unidade'})
    frames=[];notes=[]
    for name,df in pd.read_excel(file,sheet_name=None,dtype=str).items():
        renamed={c:aliases[normalize(c)] for c in df.columns if normalize(c) in aliases}
        if not {'Código Material','Descrição'}<=set(renamed.values()):
            notes.append(f'{name}: sem Código Material e Descrição; aba ignorada.');continue
        if any('preco' in normalize(c) or 'revisao' in normalize(c) for c in df.columns):
            notes.append(f'{name}: colunas de preço e revisão ignoradas; somente dados técnicos serão importados.')
        frame=df[list(renamed)].rename(columns=renamed).fillna('')
        for column in COLUMNS:
            if column not in frame:frame[column]=''
        frame=frame[COLUMNS].map(lambda v:str(v).strip())
        frames.append(frame[frame['Código Material']!=''])
    return (pd.concat(frames,ignore_index=True).drop_duplicates('Código Material',keep='last') if frames else pd.DataFrame(columns=COLUMNS)),notes
