"""Isolated, bounded reproduction of imported pricing worksheets.

External lookup results become explicit historical inputs. Internal formulas are
always evaluated from inputs; stored Excel outputs are comparison evidence only.
No formula is executed as Python, SQL, a macro, or a network request.
"""
from datetime import date,datetime,time,timedelta
from decimal import Decimal,DecimalException,InvalidOperation,ROUND_UP
from io import BytesIO
from pathlib import Path
import re
import unicodedata
from zipfile import ZipFile,BadZipFile

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries,get_column_letter
from openpyxl.utils.datetime import to_excel

MAX_CELLS=6000
MAX_RANGE=10000
MAX_VALUE=Decimal('1e24')
ADDRESS=re.compile(r'^\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})$')


def _number(value):
    if value is None or value=='':return Decimal(0)
    if isinstance(value,bool):return Decimal(int(value))
    try:
        text=str(value).strip()
        if len(text)>128:raise ValueError()
        if ',' in text:text=text.replace('.','').replace(',','.')
        result=Decimal(text)
        if not result.is_finite() or result.copy_abs()>MAX_VALUE or (result and result.adjusted() < -24):raise ValueError()
        return result
    except (DecimalException,ValueError,TypeError):raise ValueError('Número inválido ou fora do limite.') from None


def _serial(value):
    if isinstance(value,Decimal):return format(value.normalize(),'f') if value else '0'
    return value


def _norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '').lower()) if not unicodedata.combining(c)).strip()


def _value(value):
    if isinstance(value,datetime):return value.isoformat(),'date'
    if isinstance(value,date):return value.isoformat(),'date'
    if isinstance(value,time):return value.isoformat(),'time'
    if isinstance(value,timedelta):return _serial(Decimal(str(value.total_seconds()))/86400),'number'
    if isinstance(value,bool):return value,'boolean'
    if isinstance(value,(int,float,Decimal)):return _serial(_number(value)),'number'
    return value,'text'


def _annotate_inputs(cells, cost_row):
    """Describe business inputs; retain other source literals as auxiliary evidence."""
    for address,cell in cells.items():
        value=cell.get('value')
        cell['role']='calculated' if not cell['editable'] else 'auxiliary' if value not in (None,'') and str(value).strip() else 'layout'
        cell['label']='Campo auxiliar '+address if cell['editable'] else 'Cálculo '+address
    def field(address,label,kind=None,section=None):
        c=cells.get(address)
        if c is None:return
        c['label']=label
        if section:c['section']=section
        if c['editable']:
            c['role']='input'
            if kind:c['input_type']=kind
            if c['value'] is not None and not str(c['value']).strip():c['value']=None
    headers={'E3':('Cliente','text'),'V3':('Data da fonte','date'),'Y4':('Vendedor','text'),
             'E5':('Produto','text'),'T5':('Quantidade da fonte','number'),'V5':('Unidade do produto','text'),
             'Y6':('Tipo de orçamento','text')}
    for a,(label,kind) in headers.items():field(a,label,kind,'Identificação')
    headings={}
    for a,c in cells.items():
        if c['column']==2:
            name=_norm(c.get('value'))
            if name in ('materia prima','componentes','mdo interna','mdo/servicos externos','ferramental'):headings[name]=c['row']
    names={'materia prima':'Matérias-primas','componentes':'Componentes','mdo interna':'Processos internos',
           'mdo/servicos externos':'Serviços externos','ferramental':'Ferramental'}
    for name,start in headings.items():
        end=min([r for r in headings.values() if r>start]+[cost_row-5])
        section=names[name]
        for row in range(start+2,end):
            get=lambda col:cells.get(f'{col}{row}',{}).get('value')
            if name=='materia prima':
                if not f'D{row}' in cells or cells.get(f'AA{row}',{}).get('formula','') and 'SUM(' in (cells[f'AA{row}']['formula'] or ''):continue
                fields={'A':('Item','text'),'B':('Quantidade','number'),'D':('Material / espessura','text'),
                        'K':('Comprimento da peça (mm)','number'),'N':('Largura da peça (mm)','number'),
                        'P':('Comprimento do blank (mm)','number'),'S':('Largura do blank (mm)','number'),
                        'U':('Massa por área (kg/m²)','number'),'X':('Preço do material','number')}
                context=str(get('D') or 'Nova matéria-prima').strip()
            elif name=='componentes':
                if not f'D{row}' in cells or _norm(get('D'))=='descricao':continue
                fields={'A':('Item','text'),'B':('Quantidade','number'),'D':('Descrição','text'),'U':('Fornecedor','text'),'AA':('Preço de compra','number')}
                context=str(get('D') or 'Novo componente').strip()
            elif name=='mdo interna':
                if not get('J') or _norm(get('J'))=='descricao':continue
                fields={'A':('Item','text'),'B':('Horas','number'),'D':('Minutos','number'),'J':('Operação','text'),
                        'V':('Pessoas','number'),'X':('Tarifa por hora / operador','number')}
                context=str(get('J')).strip()
            elif name=='mdo/servicos externos':
                if not f'E{row}' in cells or _norm(get('E'))=='descricao':continue
                code='codigo' in _norm(cells.get(f'B{start+1}',{}).get('value'))
                fields={'A':('Item','text'),'B':('Código da operação' if code else 'Quantidade','text' if code else 'number'),
                        'E':('Serviço','text'),'U':('Fornecedor','text'),'AA':('Custo unitário','number'),'AD':('Custo total informado','number')}
                context=str(get('E') or 'Novo serviço').strip()
            else:
                fields={'B':('Descrição da ferramenta','text'),'U':('Quantidade anual','number'),'X':('Custo da ferramenta','number'),'AA':('Amortização informada','number')}
                context='Ferramental'
            for col,(label,kind) in fields.items():field(f'{col}{row}',context+' · '+label,kind,section)
    for a,c in list(cells.items()):
        if c['row']>=cost_row-5:
            row=c['row'];text=_norm(c.get('value'))
            if text=='eficiencia':field(f'O{row}','Eficiência','number','Formação do preço')
            if text=='margem':field(f'K{row+1}','Margem bruta','number','Formação do preço')
            if text=='impostos':field(f'N{row+1}','Impostos de venda','number','Formação do preço')
            if text.startswith('comissao'):field(f'H{row}','Comissão / taxa administrativa','number','Formação do preço')
            if text in ('inte','m.o'):field(f'AA{row}','Impostos · '+str(c['value']),'number','Formação do preço')
        if c['role']=='auxiliary':
            left=cells.get(f'{get_column_letter(max(1,c["column"]-1))}{c["row"]}',{}).get('value')
            if isinstance(left,str) and left.strip() and not re.match(r'^[-+0-9., ]+$',left):c['label']='Referência · '+left.strip()+' · '+a
    return cells


def _source_warnings(cells, outputs):
    warnings=[]
    def refs(formula):
        result=set()
        try:tokens=Tokenizer(formula).items
        except Exception:return result
        for token in tokens:
            if token.type!='OPERAND' or token.subtype!='RANGE':continue
            ref=token.value.replace('$','').upper()
            if ADDRESS.fullmatch(ref):result.add(ref)
            elif re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}:[A-Z]{1,3}[1-9][0-9]{0,6}',ref):
                c1,r1,c2,r2=range_boundaries(ref)
                if 0<(c2-c1+1)*(r2-r1+1)<=MAX_RANGE:
                    result.update(f'{get_column_letter(c)}{r}' for r in range(r1,r2+1) for c in range(c1,c2+1))
        return result
    def dependencies(address):
        visited=set();pending=[address]
        while pending and len(visited)<MAX_CELLS:
            a=pending.pop()
            if a in visited:continue
            visited.add(a);c=cells.get(a,{})
            if c.get('formula') and not c.get('editable'):pending.extend(refs(c['formula'])-visited)
        return visited
    component_dependencies=dependencies(outputs.get('breakdown',{}).get('component'))
    for a,c in cells.items():
        if c['section']=='Matérias-primas' and c['column']==16 and c['role']=='input':
            r=c['row']
            try:
                length,width,pl,pw=(_number(cells.get(f'{col}{r}',{}).get('value')) for col in ('P','S','K','N'))
                if min(length,width,pl,pw)>0 and not ((pl<=length and pw<=width) or (pw<=length and pl<=width)):
                    warnings.append(f'Linha {r}: dimensões da peça excedem o blank informado. A conferência reproduz o consumo da fonte; a geometria precisa de revisão antes do uso produtivo.')
            except ValueError:pass
        if c['section']=='Componentes' and c['column']==2 and c['role']=='input':
            try:quantity=_number(c.get('value'))
            except ValueError:continue
            if quantity>0:
                if a not in component_dependencies:warnings.append(f'Quantidade {a} não participa do total de componentes na fórmula original. A conferência preserva essa regra para comparação; revise antes do uso produtivo.')
                conversion=cells.get(f'AE{c["row"]}',{}).get('formula') or ''
                if '/6000' in conversion.replace(' ',''):
                    warnings.append(f'Conversão em AE{c["row"]}: a fonte divide o preço por 6000. Comprimento e unidade de consumo precisam ser conferidos; a fórmula foi preservada.')
        formula=c.get('formula')
        if formula and not c.get('editable'):
            for reference in refs(formula):
                if int(re.sub('[A-Z]','',reference))>500:
                    warnings.append(f'{a} referencia {reference}, fora da área da folha. O Excel trata essa célula vazia como zero; confira a referência original.')
    return warnings


def import_workbook(source):
    """Read one source worksheet and return a JSON-serializable calculation model."""
    raw=source if isinstance(source,bytes) else Path(source).read_bytes()
    if len(raw)>8_000_000:raise ValueError('Planilha excede o limite de 8 MB.')
    try:
        with ZipFile(BytesIO(raw)) as archive:
            info=archive.infolist()
            if len(info)>1000 or sum(i.file_size for i in info)>40_000_000:raise ValueError('Conteúdo da planilha excede o limite.')
        formulas=load_workbook(BytesIO(raw),data_only=False,keep_links=False)
        cached=load_workbook(BytesIO(raw),data_only=True,keep_links=False)
    except (BadZipFile,KeyError,TypeError) as exc:raise ValueError('Arquivo Excel inválido.') from exc
    sheet=formulas.active;values=cached[sheet.title]
    if sheet.max_row>500 or sheet.max_column>100 or sheet.max_row*sheet.max_column>MAX_CELLS:
        raise ValueError('Dimensões da planilha excedem o limite de conferência.')
    cells={};warnings=[];sections=[];section='Identificação';cost_row=None
    # Preserve styled blank input slots, including suppliers and annual tooling quantity.
    for row in sheet:
        for cell in row:
            if isinstance(cell,MergedCell):continue
            if cell.value is None and not cell.has_style:continue
            formula=cell.value if cell.data_type=='f' else None
            external=bool(formula and ('[' in formula and '!' in formula))
            today=bool(formula and formula.upper()=='=TODAY()')
            original=values[cell.coordinate].value
            value,input_type=_value(original if external or today else cell.value if not formula else None)
            if external:input_type='number'
            if today:input_type='date'
            # Formula cells are never inputs except unavailable external lookup/date sources.
            label=str(cell.value or '') if not formula else cell.coordinate
            normalized=_norm(cell.value)
            if cell.column==2 and normalized in ('materia prima','componentes','mdo interna','mdo/servicos externos','ferramental'):
                section={'materia prima':'Matérias-primas','componentes':'Componentes','mdo interna':'Processos internos',
                         'mdo/servicos externos':'Serviços externos','ferramental':'Ferramental'}[normalized]
                sections.append({'name':section,'row':cell.row})
            if normalized=='custo total':cost_row=cell.row
            cells[cell.coordinate]=dict(value=value,formula=formula,cached=_value(original)[0],editable=not formula or external or today,
                    external=external,input_type=input_type,label=label,section=section,row=cell.row,column=cell.column)
    if not cost_row:raise ValueError('Não foi encontrada a linha de custo total da folha de processo.')
    cost=f'H{cost_row}'
    gross=next((a for a,c in cells.items() if c['row']==cost_row and c['formula'] and 'ROUNDUP(' in c['formula'].upper()),None)
    if gross is None:raise ValueError('Não foi encontrada a fórmula do preço final da folha.')
    unit=next((a for a,c in cells.items() if c['formula'] and re.search(r'\b'+gross+r'/\$?T\$?5\b',c['formula'].replace('$',''),re.I)),None)
    # Structured output mapping remains stable when labels are edited.
    breakdown={}
    for a,c in cells.items():
        text=_norm(c['value']);key=None
        if text=='custo materia prima':key='material'
        elif text=='custo componentes':key='component'
        elif text=='custo mdo interna':key='process'
        elif text=='custo mdo externa':key='service'
        elif text=='amortiz ferramental':key='tool'
        if key:breakdown[key]=f'H{c["row"]}'
    if any(c['external'] for c in cells.values()):warnings.append('Consultas a arquivos externos usam os valores históricos armazenados, apresentados como entradas editáveis.')
    if any(c['formula'] and c['formula'].upper()=='=TODAY()' for c in cells.values()):warnings.append('A data da fonte foi preservada como entrada, sem atualizar automaticamente para hoje.')
    _annotate_inputs(cells,cost_row)
    warnings.extend(_source_warnings(cells,dict(breakdown=breakdown)))
    return dict(format_version=1,sheet_name=sheet.title,cells=cells,outputs=dict(cost=cost,gross=gross,unit_price=unit,pieces='T5',breakdown=breakdown),
                sections=sections,warnings=warnings,max_row=sheet.max_row,max_column=sheet.max_column)


class _Parser:
    precedence={'=':1,'<>':1,'<':1,'>':1,'<=':1,'>=':1,'&':2,'+':3,'-':3,'*':4,'/':4,'^':5}
    def __init__(self,formula):
        if len(formula)>4000:raise ValueError('Fórmula longa demais.')
        try:self.tokens=[t for t in Tokenizer(formula).items if t.type!='WHITE-SPACE']
        except Exception:raise ValueError('Fórmula inválida.') from None
        if len(self.tokens)>400:raise ValueError('Fórmula complexa demais.')
        self.pos=0;self.depth=0
    def take(self):
        if self.pos>=len(self.tokens):raise ValueError('Fórmula incompleta.')
        result=self.tokens[self.pos];self.pos+=1;return result
    def peek(self):return self.tokens[self.pos] if self.pos<len(self.tokens) else None
    def expression(self,minimum=0):
        self.depth+=1
        if self.depth>60:raise ValueError('Fórmula aninhada demais.')
        token=self.take()
        if token.type=='OPERATOR-PREFIX':node=('unary',token.value,self.expression(6))
        elif token.type=='PAREN' and token.subtype=='OPEN':
            node=self.expression();end=self.take()
            if end.type!='PAREN' or end.subtype!='CLOSE':raise ValueError('Parêntese inválido.')
        elif token.type=='FUNC' and token.subtype=='OPEN':
            name=token.value[:-1].upper();args=[]
            if name not in ('SUM','IF','ROUNDUP'):raise ValueError(f'Função não suportada: {name}.')
            while self.peek() and not (self.peek().type=='FUNC' and self.peek().subtype=='CLOSE'):
                args.append(self.expression())
                if self.peek() and self.peek().type=='SEP':self.take()
                else:break
            end=self.take()
            if end.type!='FUNC' or end.subtype!='CLOSE':raise ValueError('Argumentos inválidos.')
            node=('function',name,args)
        elif token.type=='OPERAND':
            if token.subtype=='NUMBER':node=('literal',_number(token.value))
            elif token.subtype=='TEXT':node=('literal',token.value[1:-1].replace('""','"'))
            elif token.subtype=='LOGICAL':node=('literal',token.value.upper()=='TRUE')
            elif token.subtype=='RANGE':node=('reference',token.value)
            elif token.subtype=='ERROR':node=('error',token.value)
            else:raise ValueError('Operando não suportado.')
        else:raise ValueError('Expressão não suportada.')
        while self.peek():
            token=self.peek()
            if token.type=='OPERATOR-POSTFIX' and token.value=='%':self.take();node=('unary','%',node);continue
            priority=self.precedence.get(token.value,-1) if token.type=='OPERATOR-INFIX' else -1
            if priority<minimum:break
            self.take();right=self.expression(priority if token.value=='^' else priority+1);node=('binary',token.value,node,right)
        self.depth-=1;return node
    def parse(self):
        node=self.expression()
        if self.pos!=len(self.tokens):raise ValueError('Conteúdo adicional na fórmula.')
        return node


def recalculate(model,edits=None):
    """Validate editable inputs and compute internal formulas with finite Decimal math."""
    cells=model.get('cells',{})
    if model.get('format_version')!=1 or not isinstance(cells,dict) or len(cells)>MAX_CELLS:raise ValueError('Modelo de planilha inválido.')
    edits=edits or {}
    if not isinstance(edits,dict) or len(edits)>MAX_CELLS:raise ValueError('Alterações inválidas.')
    inputs={a:c.get('value') for a,c in cells.items() if c.get('editable')}
    for address,value in edits.items():
        cell=cells.get(address)
        if not cell or not cell.get('editable'):raise ValueError(f'{address}: célula inexistente ou calculada.')
        kind=cell.get('input_type')
        if kind=='number':value=_serial(_number(value)) if value not in (None,'') else None
        elif kind=='date':
            try:value=datetime.fromisoformat(str(value)).isoformat()
            except (TypeError,ValueError):raise ValueError(f'{address}: data inválida.') from None
        elif kind=='time':
            try:value=time.fromisoformat(str(value)).isoformat()
            except (TypeError,ValueError):raise ValueError(f'{address}: horário inválido.') from None
        elif kind=='boolean':
            if not isinstance(value,bool):raise ValueError(f'{address}: informe verdadeiro ou falso.')
        elif value is not None:
            if not isinstance(value,(str,int,float,Decimal)):raise ValueError(f'{address}: conteúdo inválido.')
            value=str(value)
            if len(value)>2000:raise ValueError(f'{address}: texto longo demais.')
        inputs[address]=value
    cache={};errors={};active=set();warnings=list(model.get('warnings',[]));operations=0
    def evaluate(address):
        nonlocal operations
        address=address.replace('$','').upper()
        if not ADDRESS.fullmatch(address):raise ValueError('Referência de célula não suportada.')
        if address in cache:return cache[address]
        if address in errors:raise ValueError(errors[address])
        if address in active:raise ValueError('Referência circular.')
        if len(active)>80:raise ValueError('Cadeia de fórmulas longa demais.')
        cell=cells.get(address)
        if cell is None:
            if len(warnings)<100 and int(re.sub('[A-Z]','',address))>model.get('max_row',500):
                warnings.append(f'Referência {address} fora da área da fonte: célula vazia tratada como zero pelo Excel.')
            return None
        operations+=1
        if operations>MAX_CELLS*4:raise ValueError('Limite de cálculo excedido.')
        active.add(address)
        try:
            if cell.get('editable'):
                value=inputs[address];kind=cell.get('input_type')
                if kind=='number':
                    if cell.get('external') and (value is None or not str(value).strip()):raise ValueError('Consulta externa sem valor armazenado. Informe o valor de origem.')
                    if isinstance(value,str) and value.startswith('#'):raise ValueError('Entrada externa sem valor disponível: '+value)
                    value=_number(value)
                elif kind=='date' and value:value=Decimal(str(to_excel(datetime.fromisoformat(str(value)))))
                elif kind=='time' and value:value=Decimal(str(to_excel(time.fromisoformat(str(value)))))
                elif isinstance(value,str) and value.startswith(('#N/A','#REF!','#VALUE!','#DIV/0!')):raise ValueError(value)
            elif cell.get('formula'):value=walk(_Parser(cell['formula']).parse())
            else:value=cell.get('value')
            if isinstance(value,Decimal):_number(value)
            cache[address]=value;return value
        except (ValueError,DecimalException,ZeroDivisionError,OverflowError,RecursionError) as exc:
            message='Divisão por zero.' if isinstance(exc,ZeroDivisionError) else str(exc)
            errors[address]=message;raise ValueError(message) from None
        finally:active.remove(address)
    def walk(node):
        kind=node[0]
        if kind=='literal':return node[1]
        if kind=='error':raise ValueError(node[1])
        if kind=='reference':
            ref=node[1].replace('$','').upper()
            if ':' not in ref:return evaluate(ref)
            if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}:[A-Z]{1,3}[1-9][0-9]{0,6}',ref):raise ValueError('Intervalo não suportado.')
            c1,r1,c2,r2=range_boundaries(ref)
            if c2<c1 or r2<r1 or (c2-c1+1)*(r2-r1+1)>MAX_RANGE:raise ValueError('Intervalo excede o limite.')
            return [evaluate(f'{get_column_letter(c)}{r}') for r in range(r1,r2+1) for c in range(c1,c2+1)]
        if kind=='unary':
            value=_number(walk(node[2]));return -value if node[1]=='-' else value/100 if node[1]=='%' else value
        if kind=='function':
            name,args=node[1:]
            if name=='IF':
                if len(args) not in (2,3):raise ValueError('IF requer dois ou três argumentos.')
                condition=walk(args[0]);return walk(args[1]) if condition else walk(args[2]) if len(args)==3 else False
            if name=='SUM':
                total=Decimal(0)
                for arg in args:
                    result=walk(arg)
                    for v in result if isinstance(result,list) else [result]:
                        if isinstance(v,(Decimal,int,float,bool)):total+=_number(v)
                return total
            if len(args)!=2:raise ValueError('ROUNDUP requer dois argumentos.')
            value=_number(walk(args[0]));places=_number(walk(args[1]))
            if places!=places.to_integral_value() or abs(places)>12:raise ValueError('Precisão de arredondamento inválida.')
            return value.quantize(Decimal(10)**-int(places),rounding=ROUND_UP)
        if kind=='binary':
            op=node[1];a=walk(node[2]);b=walk(node[3])
            if op=='&':return str(_serial(a) or '')+str(_serial(b) or '')
            if op in ('=','<>','<','>','<=','>='):
                try:a,b=_number(a),_number(b)
                except ValueError:a,b=str(a or ''),str(b or '')
                return {'=':lambda:a==b,'<>':lambda:a!=b,'<':lambda:a<b,'>':lambda:a>b,'<=':lambda:a<=b,'>=':lambda:a>=b}[op]()
            a,b=_number(a),_number(b)
            if op=='^' and (b!=b.to_integral_value() or abs(b)>100):raise ValueError('Expoente fora do limite.')
            result={'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b,'^':lambda:a**int(b)}[op]()
            return _number(result)
        raise ValueError('Expressão inválida.')
    for address in cells:
        try:evaluate(address)
        except ValueError:pass
    outputs=model['outputs']
    def numeric(address):
        if not address:return None
        try:return _number(evaluate(address))
        except ValueError:return None
    cost=numeric(outputs['cost']);gross=numeric(outputs['gross']);pieces=numeric(outputs['pieces'])
    if pieces is not None and pieces<=0:errors[outputs['pieces']]='Quantidade da fonte deve ser positiva.';pieces=None
    def per_piece(value,label):
        if value is None or pieces is None:return None
        try:return _number(value/pieces)
        except (ValueError,DecimalException,ZeroDivisionError):
            errors[outputs['pieces']]=label+' por peça fora do limite de cálculo.'
            return None
    unit=numeric(outputs.get('unit_price')) if outputs.get('unit_price') else per_piece(gross,'Preço')
    cost_per_piece=per_piece(cost,'Custo')
    return dict(values={a:_serial(v) for a,v in cache.items()},errors=errors,warnings=list(dict.fromkeys(warnings)),inputs=inputs,
                cost_total=_serial(cost),cost_per_piece=_serial(cost_per_piece),
                gross_total=_serial(gross),gross_per_piece=_serial(unit),pieces=_serial(pieces),
                breakdown={k:_serial(numeric(a)) for k,a in outputs.get('breakdown',{}).items()})
