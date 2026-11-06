"""One-transaction catalog maintenance and user access editing."""
from pricing_calculator import PricingError
from pricing_repository import TABLES, json_value, plain
from pricing_service import PricingService, StalePreview


class CatalogService(PricingService):
    def _write_profile(self,c,data):
        code,params,reviewed=self._normalize_profile(data.get('code'),data.get('data',{}),data.get('reviewed_on'))
        old=None
        if data.get('id'):
            c.execute('SELECT * FROM pricing_profiles WHERE id=%s',(data['id'],))
            old=c.fetchone()
            if not old:raise PricingError('Perfil não encontrado.')
            if data.get('version') is not None and int(data['version'])!=old['version']:
                raise StalePreview('O perfil mudou. Atualize os dados antes de salvar.')
        c.execute('SELECT id FROM pricing_profiles WHERE code=%s',(code,))
        duplicate=c.fetchone()
        if duplicate and duplicate['id']!=data.get('id'):
            raise PricingError('Já existe um perfil com esse nome.')
        active=data.get('active',True) is True
        if old and not active:
            c.execute("SELECT 1 FROM pricing_revisions WHERE profile_id=%s AND status='ACTIVE' LIMIT 1",(old['id'],))
            if c.fetchone():raise PricingError('Perfil usado em folha ativa. Substitua o perfil nas folhas antes de bloquear.')
        if old:
            c.execute('''UPDATE pricing_profiles SET code=%s,data=%s,reviewed_on=%s,active=%s,
              version=version+1 WHERE id=%s RETURNING *''',(code,json_value(params),reviewed,active,old['id']))
        else:
            c.execute('INSERT INTO pricing_profiles(code,data,reviewed_on,active) VALUES(%s,%s,%s,%s) RETURNING *',
                      (code,json_value(params),reviewed,active))
        return plain(c.fetchone()),plain(old)

    def _catalog_changes(self,c,changes,profiles,deletions,actor,reason):
        touched=set();revisions={}
        for revision in self._dependents(c,changes):revisions[revision['id']]=revision
        for profile in profiles:
            identity=('profile',profile.get('id') or profile.get('code'))
            if identity in touched:raise PricingError('Perfil repetido no mesmo salvamento.')
            touched.add(identity)
            result,old=self._write_profile(c,profile)
            c.execute("SELECT r.*,s.material_code FROM pricing_revisions r JOIN pricing_sheets s ON s.id=r.sheet_id WHERE r.profile_id=%s AND r.status='ACTIVE'",(result['id'],))
            for revision in c.fetchall():revisions[revision['id']]=dict(revision)
            self._event(c,actor,'ALTERAR PERFIL',result['id'],dict(before=old,after=result,reason=reason))
        for kind,data in changes:
            identity=(kind,data.get('id') or data.get('code'))
            if identity in touched:raise PricingError('Custo repetido no mesmo salvamento.')
            touched.add(identity)
            result,old=self._write_base(c,kind,data)
            self._event(c,actor,'ALTERAR CUSTO',f'{kind}:{result["id"]}',dict(before=old,after=result,reason=reason))
        for kind,record_id in deletions:
            identity=(kind,record_id)
            if identity in touched:raise PricingError('Registro marcado para editar e excluir ao mesmo tempo.')
            touched.add(identity)
            table='pricing_profiles' if kind=='profile' else TABLES.get(kind)
            if table is None:raise PricingError('Categoria de custo inválida.')
            if kind=='profile':
                c.execute('SELECT 1 FROM pricing_revisions WHERE profile_id=%s LIMIT 1',(record_id,))
            else:
                c.execute(f'SELECT 1 FROM pricing_dependencies WHERE {kind}_id=%s LIMIT 1',(record_id,))
            if c.fetchone():raise PricingError('Registro vinculado a folhas ou histórico. Preserve-o; substitua a referência antes de bloquear.')
            c.execute(f'DELETE FROM {table} WHERE id=%s RETURNING *',(record_id,))
            old=c.fetchone()
            if not old:raise PricingError('Registro não encontrado para exclusão.')
            self._event(c,actor,'EXCLUIR CUSTO' if kind!='profile' else 'EXCLUIR PERFIL',f'{kind}:{record_id}',dict(before=plain(old),reason=reason))
        return [revisions[rid] for rid in sorted(revisions)]

    def preview_catalog(self,changes,profiles,deletions,actor,expected_version):
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'costs')
            revisions=self._catalog_changes(c,changes,profiles,deletions,actor,'Simulação')
            items=[]
            for revision in revisions:
                result,_=self._calculate(c,revision)
                c.execute('SELECT net_price FROM pricing_prices WHERE revision_id=%s ORDER BY id DESC LIMIT 1',(revision['id'],))
                old=c.fetchone()
                items.append(dict(code=revision['material_code'],before=str(old['net_price']) if old else None,after=str(result.net_price),gross=str(result.gross_price)))
            c.execute('ROLLBACK')
            return dict(version=expected_version,items=items)

    def publish_catalog(self,changes,profiles,deletions,actor,expected_version,reason,key):
        if not changes and not profiles and not deletions:raise PricingError('Nenhuma alteração para salvar.')
        if not reason.strip():raise PricingError('Informe o motivo das alterações.')
        fp=self._fingerprint(actor,'catalog',[changes,profiles,deletions,reason])
        with self.repo.transaction() as c:
            c.execute('SELECT version FROM pricing_control WHERE id=1 FOR UPDATE')
            self._require(c,actor,'costs')
            prior=self._prior(c,key,fp)
            if prior:return prior
            self._lock(c,expected_version)
            revisions=self._catalog_changes(c,changes,profiles,deletions,actor,reason)
            return self._publish_prices(c,revisions,actor,'SALVAR CENTRAL DE CUSTOS',key,fp,
                                        details=dict(costs=len(changes),profiles=len(profiles),deleted=len(deletions),reason=reason))

    def users(self,actor):
        with self.repo.transaction() as c:
            self._require(c,actor,'permissions')
            c.execute('''SELECT u.id,u.nome,u.usuario,u.perfil,u.ativo,coalesce(p.permissions,'[]'::jsonb) AS permissions
              FROM usuarios u LEFT JOIN pricing_permissions p ON p.username=u.usuario ORDER BY u.nome''')
            return plain(c.fetchall())

    def save_user(self,user_id,data,permissions,actor,expected_version):
        name=str(data.get('name') or '').strip();username=str(data.get('username') or '').strip()
        profile=data.get('profile');active=1 if data.get('active') else 0
        chosen=set(permissions)
        if not name or not username:raise PricingError('Informe nome e usuário.')
        if profile not in ('ADMIN','PROCESSISTA','VENDEDORA'):raise PricingError('Perfil inválido.')
        if not chosen<={'view','edit','publish','costs'}:raise PricingError('Permissões inválidas.')
        if chosen:chosen.add('view')
        if not user_id and not data.get('password'):raise PricingError('Informe a senha do novo usuário.')
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'permissions')
            old=None
            if user_id:
                c.execute('SELECT id,nome,usuario,perfil,ativo FROM usuarios WHERE id=%s',(user_id,))
                old=c.fetchone()
                if not old:raise PricingError('Usuário não encontrado.')
                if old['usuario']==actor and (not active or profile!='ADMIN' or username!=actor):
                    raise PricingError('Preserve seu usuário, perfil de administrador e acesso ativo enquanto estiver conectado.')
            c.execute('SELECT id FROM usuarios WHERE usuario=%s',(username,))
            duplicate=c.fetchone()
            if duplicate and duplicate['id']!=user_id:raise PricingError('Este usuário já está cadastrado.')
            if user_id:
                c.execute('UPDATE usuarios SET nome=%s,usuario=%s,perfil=%s,ativo=%s WHERE id=%s',(name,username,profile,active,user_id))
            else:
                c.execute('INSERT INTO usuarios(nome,usuario,senha,perfil,ativo) VALUES(%s,%s,%s,%s,%s) RETURNING id',
                          (name,username,data['password'],profile,active));user_id=c.fetchone()['id']
            c.execute('''INSERT INTO pricing_permissions(username,permissions) VALUES(%s,%s)
              ON CONFLICT(username) DO UPDATE SET permissions=EXCLUDED.permissions,updated_at=now()''',
                      (username,json_value(sorted(chosen) if profile!='ADMIN' else [])))
            self._advance(c)
            self._event(c,actor,'EDITAR USUÁRIO',user_id,dict(before=plain(old),after=dict(name=name,username=username,profile=profile,active=active,permissions=sorted(chosen))))
            return user_id

    def user_action(self,user_id,action,actor,expected_version,password=None):
        if action not in ('password','delete'):raise PricingError('Ação de usuário inválida.')
        if action=='password' and not password:raise PricingError('Informe a nova senha.')
        with self.repo.transaction() as c:
            self._lock(c,expected_version);self._require(c,actor,'permissions')
            c.execute('SELECT id,nome,usuario,perfil,ativo FROM usuarios WHERE id=%s',(user_id,))
            user=c.fetchone()
            if not user:raise PricingError('Usuário não encontrado.')
            if action=='delete':
                if user['usuario']==actor:raise PricingError('Você não pode excluir o próprio usuário conectado.')
                c.execute('DELETE FROM usuarios WHERE id=%s',(user_id,))
            else:c.execute('UPDATE usuarios SET senha=%s WHERE id=%s',(password,user_id))
            self._advance(c)
            self._event(c,actor,'EXCLUIR USUÁRIO' if action=='delete' else 'REDEFINIR SENHA',user_id,dict(user=plain(user)))
