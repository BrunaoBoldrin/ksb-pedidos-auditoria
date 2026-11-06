"""Autorizações, rascunhos e publicação atômica dos preços e seus custos base."""
import hashlib
import json
import uuid
from decimal import Decimal

from pricing_calculator import calculate_sheet, number, review_date, PricingError
from pricing_repository import PricingRepository, TABLES, json_value, plain
from pricing_fiscal import parameters_for_item


class StalePreview(PricingError):
    pass


class PricingService:
    def __init__(self,repo=None):self.repo=repo or PricingRepository()

    @staticmethod
    def _permissions(c,actor):
        c.execute('''SELECT u.perfil,u.ativo,p.permissions FROM usuarios u
                     LEFT JOIN pricing_permissions p ON p.username=u.usuario WHERE u.usuario=%s''',(actor,))
        row=c.fetchone()
        if not row or row['ativo']!=1:raise PermissionError('Usuário inativo ou não autorizado.')
        return {'view','edit','publish','costs','permissions'} if row['perfil']=='ADMIN' else set(row['permissions'] or [])

    def permissions(self,actor):
        with self.repo.transaction() as c:return self._permissions(c,actor)

    def _require(self,c,actor,permission):
        perms=self._permissions(c,actor)
        if permission not in perms or (permission!='permissions' and 'view' not in perms):
            raise PermissionError('Você não tem autorização para esta ação de precificação.')

    @staticmethod
    def _lock(c,expected,read_only=False):
        c.execute('SELECT version FROM pricing_control WHERE id=1 FOR '+('SHARE' if read_only else 'UPDATE'))
        version=c.fetchone()['version']
        if expected!=version:raise StalePreview('Os dados mudaram. Atualize a tela e refaça a prévia.')
        return version

    @staticmethod
    def _advance(c):
        c.execute('UPDATE pricing_control SET version=version+1 WHERE id=1 RETURNING version')
        return c.fetchone()['version']

    @staticmethod
    def _event(c,actor,action,target,data):
        c.execute('INSERT INTO pricing_events(actor,action,target,data) VALUES(%s,%s,%s,%s)',(actor,action,str(target),json_value(data)))

    @staticmethod
    def _fingerprint(actor,action,payload):
        return hashlib.sha256(json.dumps(plain([actor,action,payload]),sort_keys=True).encode()).hexdigest()

    def _prior(self,c,key,fingerprint):
        c.execute('SELECT fingerprint,result FROM pricing_publications WHERE operation_key=%s',(key,))
        row=c.fetchone()
        if row and row['fingerprint']!=fingerprint:raise PricingError('Identificador de operação já usado com outros dados.')
        return row['result'] if row else None

    @staticmethod
    def _normalize_base(data):
        data=dict(data)
        for field in ('code','description','unit'):data[field]=str(data.get(field) or '').strip()
        if not data['code'] or not data['description']:raise PricingError('Informe código e descrição do custo base.')
        if data['unit'] not in ('KG','G','M','MM','M2','UN','BAR','H'):raise PricingError('Unidade de custo inválida.')
        data['price']=str(number(data.get('price'),'Custo'))
        data['factor']=str(number(data.get('factor','1'),'Fator líquido',maximum=Decimal('1')))
        for field in ('kg_m2','length_mm'):
            data[field]=str(number(data[field],field)) if data.get(field) not in (None,'') else None
        data['note']=str(data.get('note') or '').strip()
        if Decimal(data['price'])==0 and not data['note']:raise PricingError('Justifique o custo zero nas observações.')
        data['reviewed_on']=review_date(data.get('reviewed_on'))
        data['active']=data.get('active',True) is True
        data['per_person']=data.get('per_person',True) is True
        return data

    def _write_base(self,c,kind,data):
        if kind not in TABLES:raise PricingError('Tipo de custo inválido.')
        data=self._normalize_base(data)
        c.execute(f'SELECT id FROM {TABLES[kind]} WHERE code=%s',(data['code'],))
        duplicate=c.fetchone()
        if duplicate and duplicate['id']!=data.get('id'):
            raise PricingError('Já existe um custo com esse código nesta tabela.')
        fields=('code','description','unit','price','factor','kg_m2','length_mm','per_person','reviewed_on','active','note')
        if data.get('id'):
            c.execute(f'SELECT * FROM {TABLES[kind]} WHERE id=%s',(data['id'],));old=c.fetchone()
            if not old:raise PricingError('Custo base não encontrado.')
            if data.get('version') is not None and int(data['version'])!=old['version']:raise StalePreview('Custo base alterado por outro usuário.')
            c.execute(f"UPDATE {TABLES[kind]} SET "+','.join(f'{f}=%s' for f in fields)+',version=version+1 WHERE id=%s RETURNING *',tuple(data[f] for f in fields)+(data['id'],))
        else:
            old=None
            c.execute(f"INSERT INTO {TABLES[kind]} ("+','.join(fields)+') VALUES('+','.join(['%s']*len(fields))+') RETURNING *',tuple(data[f] for f in fields))
        return plain(c.fetchone()),plain(old)

    def _proposed_changes(self,c,data):
        proposed=data.get('proposed_prices',[])
        if not isinstance(proposed,list) or len(proposed)>500:raise PricingError('Propostas de preços inválidas.')
        references={(line.get('kind'),int(line['base_id'])) for line in data.get('lines',[])}
        changes={}
        for proposal in proposed:
            kind=proposal.get('kind');base_id=int(proposal['base_id'])
            identity=(kind,base_id)
            if kind not in TABLES or identity not in references:
                raise PricingError('A proposta de preço deve pertencer a um custo usado na composição.')
            c.execute(f'SELECT * FROM {TABLES[kind]} WHERE id=%s',(base_id,))
            base=c.fetchone()
            if not base:raise PricingError('Custo proposto não encontrado.')
            if proposal.get('version') is None or int(proposal['version'])!=base['version']:
                raise StalePreview('Um custo proposto mudou após a edição. Reabra a folha e confira o preço atual antes de salvar nova revisão.')
            price=str(number(proposal.get('price'),'Preço proposto'))
            if identity in changes and changes[identity]['price']!=price:
                raise PricingError('O mesmo custo não pode ter dois preços propostos diferentes.')
            changed=dict(base,price=price,reviewed_on=review_date(proposal.get('reviewed_on')))
            changes[identity]=changed
        return [(kind,data) for (kind,_),data in changes.items()]

    def _calculate(self,c,revision,with_proposed=False):
        data=dict(revision['data'])
        bases={};ids={kind:set() for kind in TABLES}
        for line in data.get('lines',[]):
            kind=line.get('kind')
            if kind not in TABLES:raise PricingError('Categoria de linha inválida.')
            ids[kind].add(int(line['base_id']))
        queries=[];args=[]
        for kind,values in ids.items():
            if values:
                queries.append(f"SELECT '{kind}' AS kind,to_jsonb(b)::text AS base FROM {TABLES[kind]} b WHERE id=ANY(%s)")
                args.append(sorted(values))
        if queries:
            c.execute(' UNION ALL '.join(queries),tuple(args))
            for row in c.fetchall():
                base=json.loads(row['base'],parse_float=Decimal)
                bases[(row['kind'],base['id'])]=base
        if with_proposed:
            for kind,base in self._proposed_changes(c,data):bases[(kind,base['id'])]=base
        context=self._fiscal(c,revision['material_code'])
        data.update(basis='GROSS',confirmed=True,taxes=context['taxes'])
        result=calculate_sheet(data,bases,context['fiscal_divisor'])
        result.parameters.update(tax_source='NCM',ipi=Decimal(context['ipi'])/100)
        return result,context

    @staticmethod
    def _fiscal(c,code):
        c.execute('''SELECT m.ncm,m.unidade_medida,f.id AS rule_id,f.aliquota_icms,f.aliquota_ipi
          FROM materiais m LEFT JOIN LATERAL(SELECT id,aliquota_icms,aliquota_ipi FROM regras_fiscais
          WHERE regexp_replace(ncm,'[^0-9]','','g')=regexp_replace(m.ncm,'[^0-9]','','g')
          AND ativo=1 ORDER BY id DESC LIMIT 1)f ON true WHERE m.codigo_material=%s''',(code,))
        return parameters_for_item(c.fetchone())

    def fiscal_for_item(self,code,actor):
        with self.repo.transaction() as c:
            self._require(c,actor,'view')
            return self._fiscal(c,code)

    def _revision(self,c,revision_id):
        c.execute('SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id WHERE r.id=%s',(revision_id,))
        row=c.fetchone()
        if not row:raise PricingError('Revisão não encontrada.')
        return dict(row)

    def _publish_prices(self,c,revisions,actor,action,key,fingerprint,details=None):
        publication_id=uuid.uuid4().hex
        items=[]
        for revision in revisions:
            result,context=self._calculate(c,revision)
            c.execute('''SELECT p.net_price FROM pricing_prices p JOIN pricing_revisions r ON r.id=p.revision_id
              WHERE r.sheet_id=%s ORDER BY p.id DESC LIMIT 1''',(revision['sheet_id'],))
            old=c.fetchone()
            snapshot=result.snapshot()
            snapshot.update(sheet_revision_id=revision['id'],sheet_revision=revision['number'],material_code=revision['material_code'],fiscal_context=context)
            c.execute('''INSERT INTO pricing_prices(revision_id,publication_id,net_price,gross_price,reviewed_on,snapshot,fiscal_context)
              VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''',(revision['id'],publication_id,result.net_price,result.gross_price,result.reviewed_on,json_value(snapshot),json_value(context)))
            snapshot_id=c.fetchone()['id']
            if old and old['net_price']!=result.net_price:
                c.execute('''INSERT INTO revisoes_preco(codigo_material,descricao_material,preco_anterior,preco_novo,usuario,origem)
                 SELECT codigo_material,descricao,%s,%s,%s,'ATUALIZAÇÃO POR FOLHA' FROM materiais WHERE codigo_material=%s''',
                 (old['net_price'],result.net_price,actor,revision['material_code']))
            items.append(dict(code=revision['material_code'],before=str(old['net_price']) if old else None,
                              after=str(result.net_price),gross=str(result.gross_price),snapshot_id=snapshot_id))
        version=self._advance(c)
        publication=dict(publication_id=publication_id,version=version,count=len(items),items=items)
        if details is not None:publication['details']=details
        c.execute('INSERT INTO pricing_publications(id,operation_key,fingerprint,version,actor,action,result) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                  (publication_id,key,fingerprint,version,actor,action,json_value(publication)))
        self._event(c,actor,action,publication_id,publication)
        return publication

    def save_base(self,kind,data,actor,expected_version,key):
        fp=self._fingerprint(actor,'base',[kind,data])
        with self.repo.transaction() as c:
            self._require(c,actor,'costs')
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE')
            self._require(c,actor,'costs')
            prior=self._prior(c,key,fp)
            if prior:return prior['base']
            self._lock(c,expected_version)
            result,old=self._write_base(c,kind,data)
            revisions=self._dependents(c,[(kind,result)])
            pub=self._publish_prices(c,revisions,actor,'CUSTO BASE',key,fp)
            self._event(c,actor,'ALTERAR CUSTO',f'{kind}:{result["id"]}',dict(before=old,after=result))
            pub['base']=result
            c.execute('UPDATE pricing_publications SET result=%s WHERE id=%s',(json_value(pub),pub['publication_id']))
            return result

    @staticmethod
    def _dependents(c,changes):
        ids=set()
        for kind,data in changes:
            if kind not in TABLES:raise PricingError('Tipo de custo inválido.')
            if not data.get('id'):continue
            c.execute(f'''SELECT DISTINCT r.id FROM pricing_dependencies d JOIN pricing_revisions r ON r.id=d.revision_id
                       WHERE r.status='ACTIVE' AND d.{kind}_id=%s''',(data['id'],))
            ids.update(x['id'] for x in c.fetchall())
        revisions=[]
        for rid in sorted(ids):
            c.execute('SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id WHERE r.id=%s',(rid,))
            revisions.append(dict(c.fetchone()))
        return revisions

    def preview_costs(self,changes,actor):
        with self.repo.transaction() as c:
            self._require(c,actor,'costs')
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE');version=c.fetchone()['version']
            self._require(c,actor,'costs')
            revisions=self._dependents(c,changes)
            for kind,data in changes:self._write_base(c,kind,data)
            items=[]
            for revision in revisions:
                result,_=self._calculate(c,revision)
                c.execute('SELECT net_price FROM pricing_prices WHERE revision_id=%s ORDER BY id DESC LIMIT 1',(revision['id'],));old=c.fetchone()
                items.append(dict(code=revision['material_code'],before=str(old['net_price']) if old else None,after=str(result.net_price),gross=str(result.gross_price)))
            c.execute('ROLLBACK')
            return dict(version=version,items=items,key=uuid.uuid4().hex)

    def publish_costs(self,changes,actor,expected_version,reason,key):
        if not reason.strip():raise PricingError('Informe o motivo da atualização.')
        fp=self._fingerprint(actor,'costs',[changes,reason])
        with self.repo.transaction() as c:
            self._require(c,actor,'costs')
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE')
            self._require(c,actor,'costs')
            prior=self._prior(c,key,fp)
            if prior:return prior
            self._lock(c,expected_version)
            revisions=self._dependents(c,changes)
            for kind,data in changes:
                result,old=self._write_base(c,kind,data)
                self._event(c,actor,'ALTERAR CUSTO',f'{kind}:{result["id"]}',dict(before=old,after=result,reason=reason))
            return self._publish_prices(c,revisions,actor,'ATUALIZAR CUSTOS',key,fp)

    def save_draft(self,code,data,actor,expected_version):
        if not isinstance(data.get('lines',[]),list) or len(data.get('lines',[]))>500:raise PricingError('Composição inválida ou acima de 500 linhas.')
        data=dict(data,profile_id=None,basis='GROSS',confirmed=True,tax_source='NCM')
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'edit')
            if data.get('proposed_prices'):
                self._require(c,actor,'costs');self._proposed_changes(c,data)
            c.execute('INSERT INTO pricing_sheets(material_code,created_by) VALUES(%s,%s) ON CONFLICT(material_code) DO UPDATE SET material_code=EXCLUDED.material_code RETURNING id',(code,actor))
            sid=c.fetchone()['id']
            c.execute('SELECT coalesce(max(number),0)+1 AS n FROM pricing_revisions WHERE sheet_id=%s',(sid,));n=c.fetchone()['n']
            profile_id=int(data['profile_id']) if data.get('profile_id') else None
            c.execute("INSERT INTO pricing_revisions(sheet_id,number,data,profile_id,status,author) VALUES(%s,%s,%s,%s,'DRAFT',%s) RETURNING id",(sid,n,json_value(data),profile_id,actor))
            rid=c.fetchone()['id']
            for line in data.get('lines',[]):
                kind=line.get('kind')
                if kind not in TABLES:raise PricingError('Categoria de linha inválida.')
                c.execute(f'INSERT INTO pricing_dependencies(revision_id,{kind}_id) VALUES(%s,%s)',(rid,int(line['base_id'])))
            self._advance(c);self._event(c,actor,'SALVAR RASCUNHO',rid,dict(code=code,revision=n))
            return dict(id=rid,number=n)

    def preview_sheet(self,revision_id,actor):
        with self.repo.transaction() as c:
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR SHARE')
            self._require(c,actor,'view');revision=self._revision(c,revision_id)
            result,context=self._calculate(c,revision,with_proposed=revision['status']=='DRAFT')
            return dict(calculation=dict(result.snapshot(),fiscal_context=context),fiscal_context=context)

    def preview_draft(self,code,data,actor,expected_version):
        with self.repo.transaction() as c:
            self._lock(c,expected_version,read_only=True);self._require(c,actor,'view')
            revision=dict(data=data,profile_id=data.get('profile_id'),material_code=code)
            result,context=self._calculate(c,revision,with_proposed=True)
            return dict(calculation=dict(result.snapshot(),fiscal_context=context),fiscal_context=context)

    def preview_profile(self,code,data,reviewed_on,actor,expected_version):
        code,data,reviewed_on=self._normalize_profile(code,data,reviewed_on)
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'costs')
            c.execute('''INSERT INTO pricing_profiles(code,data,reviewed_on) VALUES(%s,%s,%s)
              ON CONFLICT(code) DO UPDATE SET data=EXCLUDED.data,reviewed_on=EXCLUDED.reviewed_on RETURNING id''',
              (code,json_value(data),reviewed_on))
            pid=c.fetchone()['id']
            c.execute("SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id WHERE r.profile_id=%s AND r.status='ACTIVE'",(pid,))
            items=[]
            for revision in c.fetchall():
                result,_=self._calculate(c,dict(revision))
                items.append(dict(code=revision['material_code'],after=str(result.net_price),gross=str(result.gross_price)))
            c.execute('ROLLBACK')
            return dict(version=expected_version,items=items,key=uuid.uuid4().hex)

    def activate(self,revision_id,actor,expected_version,key):
        fp=self._fingerprint(actor,'activate',revision_id)
        with self.repo.transaction() as c:
            self._require(c,actor,'publish')
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE')
            self._require(c,actor,'publish')
            prior=self._prior(c,key,fp)
            if prior:return prior
            self._lock(c,expected_version);rev=self._revision(c,revision_id)
            if rev['status']=='ARCHIVED':
                raise PricingError('Copie a composição arquivada para um novo rascunho antes de publicar.')
            changes=[]
            if rev['status']=='DRAFT' and rev['data'].get('proposed_prices'):
                self._require(c,actor,'costs')
                changes=self._proposed_changes(c,rev['data'])
                for kind,data in changes:
                    result,old=self._write_base(c,kind,data)
                    self._event(c,actor,'ALTERAR CUSTO PELA FOLHA',f'{kind}:{result["id"]}',dict(before=old,after=result,sheet_revision_id=rev['id']))
            c.execute("UPDATE pricing_revisions SET status='ARCHIVED' WHERE sheet_id=%s AND status='ACTIVE'",(rev['sheet_id'],))
            c.execute("UPDATE pricing_revisions SET status='ACTIVE' WHERE id=%s",(revision_id,))
            affected={r['id']:r for r in self._dependents(c,changes)}
            affected[rev['id']]=rev
            return self._publish_prices(c,list(affected.values()),actor,'ATIVAR FOLHA',key,fp)

    def archive(self,code,actor,expected_version,reason,key):
        if not reason.strip():raise PricingError('Informe o motivo do arquivamento.')
        fp=self._fingerprint(actor,'archive',[code,reason])
        with self.repo.transaction() as c:
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE');self._require(c,actor,'publish')
            prior=self._prior(c,key,fp)
            if prior:return prior
            self._lock(c,expected_version)
            c.execute("UPDATE pricing_revisions SET status='ARCHIVED' WHERE sheet_id=(SELECT id FROM pricing_sheets WHERE material_code=%s) AND status='ACTIVE' RETURNING id,number",(code,))
            revisions=[dict(id=r['id'],number=r['number'],previous_status='ACTIVE') for r in c.fetchall()]
            details=dict(code=code,reason=reason.strip(),revisions=revisions)
            return self._publish_prices(c,[],actor,'ARQUIVAR FOLHA',key,fp,details=details)

    def set_permissions(self,username,permissions,actor,expected_version):
        chosen=set(permissions)
        if not chosen<= {'view','edit','publish','costs'}:raise PricingError('Permissões inválidas.')
        if chosen:chosen.add('view')
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'permissions')
            c.execute('''INSERT INTO pricing_permissions(username,permissions) VALUES(%s,%s)
                         ON CONFLICT(username) DO UPDATE SET permissions=EXCLUDED.permissions,updated_at=now()''',(username,json_value(sorted(chosen))))
            self._advance(c);self._event(c,actor,'PERMISSÕES',username,dict(permissions=sorted(chosen)))

    @staticmethod
    def _normalize_profile(code,data,reviewed_on):
        code=str(code or '').strip()
        if not code:raise PricingError('Informe o nome do perfil.')
        allowed={'efficiency','taxes','rounding'}
        if not set(data)<=allowed:raise PricingError('Campo de perfil inválido.')
        efficiency=number(data.get('efficiency'),'Eficiência',Decimal('0.000001'),Decimal('1'))
        taxes=number(data.get('taxes'),'Impostos',maximum=Decimal('0.999999'))
        if data.get('rounding') not in ('UP_REAL','CENT'):raise PricingError('Arredondamento inválido.')
        return code,dict(efficiency=str(efficiency),taxes=str(taxes),rounding=data['rounding']),review_date(reviewed_on)

    def save_profile(self,code,data,actor,expected_version,reviewed_on,key):
        code,data,reviewed_on=self._normalize_profile(code,data,reviewed_on)
        fp=self._fingerprint(actor,'profile',[code,data,reviewed_on])
        with self.repo.transaction() as c:
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE');self._require(c,actor,'costs')
            prior=self._prior(c,key,fp)
            if prior:return prior
            self._lock(c,expected_version)
            c.execute('''INSERT INTO pricing_profiles(code,data,reviewed_on) VALUES(%s,%s,%s)
              ON CONFLICT(code) DO UPDATE SET data=EXCLUDED.data,reviewed_on=EXCLUDED.reviewed_on,version=pricing_profiles.version+1 RETURNING id''',
              (code,json_value(data),reviewed_on))
            pid=c.fetchone()['id']
            c.execute("SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id WHERE r.profile_id=%s AND r.status='ACTIVE'",(pid,))
            revisions=[dict(r) for r in c.fetchall()]
            self._event(c,actor,'PERFIL',pid,dict(code=code,data=data))
            return self._publish_prices(c,revisions,actor,'ATUALIZAR PERFIL',key,fp)
