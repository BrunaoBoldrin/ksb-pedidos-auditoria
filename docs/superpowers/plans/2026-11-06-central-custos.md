# Central de custos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduzir a manutenção dos preços a uma grade unificada com um salvamento, restaurando listas selecionáveis e edição de folhas/permissões.
**Architecture:** Manter o cálculo e os snapshots atuais; ampliar o serviço transacional para lotes de custos/perfis e propostas de preço de rascunhos. Separar a grade central, a folha e usuários em módulos de UI com navegação por listas.
**Tech Stack:** Python, Streamlit, pandas, PostgreSQL, psycopg2, unittest/AppTest.
**Spec:** docs/superpowers/specs/2026-11-06-central-custos-design.md

## Global Constraints
- Sem alteração de produção; primeiro destino continua sendo teste e seu banco isolado.
- Exemplos e testes publicados são sintéticos.
- Erro, versão vencida ou autorização removida desfaz todo o salvamento.
- Salvar rascunho não altera custo global nem preço vigente.

## Review Focus
- Mudança simultânea de custo e perfil da mesma folha deve recalcular a folha uma única vez.
- Editar duas linhas em reruns consecutivos conserva ambas e a versão inicial da grade.
- Trocar usuário, item ou revisão não reaproveita campos de outra entidade.
- Publicar uma proposta de preço vencida não sobrescreve um custo global mais recente.
- Exclusão/bloqueio não perde histórico nem permite precificação sem um custo obrigatório.

### Task 1: Catálogo transacional e consultas de lista
**Files:** pricing_catalog.py, pricing_repository.py, pricing_service.py, migrations/002_catalog_management.sql, tests/test_pricing_catalog.py.
**Interfaces:** CatalogService(PricingService) implementa preview_catalog(changes,profiles,deletions,actor,expected_version) e publish_catalog(changes,profiles,deletions,actor,expected_version,reason,key). PricingRepository.catalog() retorna versão, bases e perfis em leitura consistente; sheets() retorna revisões/preços para seleção.
- [ ] Escrever integrações: lote custo100→110 e perfil impostos30%→20% resulta183,33 na folha dependente; apenas uma memória nova; erro reverte o lote; reenvio idempotente.
- [ ] Executar e observar RED; implementar transação única, CRUD e restrições; executar GREEN no PostgreSQL de CI.
- [ ] Commit coerente de backend e testes.

### Task 2: Seleção técnica e permissões dentro do usuário
**Files:** pricing_ui.py, pricing_users.py, pricing_catalog.py, app.py, tests/test_pricing_ui.py, tests/test_pricing_catalog.py.
**Interfaces:** render_users(actor) lista usuários e abre formulário por ID; save_user(user_id,data,permissions,actor,expected_version) salva dados e permissões atomicamente.
- [ ] AppTest seleciona checkbox de item, abre edição e preserva identificação; consulta de usuários não exibe permissões soltas; edição exibe e salva as do usuário correto.
- [ ] Executar RED; implementar seleção e formulário; testar salvamento com versão/autorização e GREEN.
- [ ] Commit.

### Task 3: Central de custos editável e perfis
**Files:** pricing_catalog_ui.py, pricing_workspace.py, pricing_ui.py, tests/test_pricing_workspace.py, tests/test_pricing_ui.py.
**Interfaces:** render_catalog(actor,service,profiles_only=False); workspace conserva baseline/version/edits por usuário e área, gera alterações exclusivamente das linhas modificadas.
- [ ] Escrever testes de duas alterações+perfil em um salvamento, precisão decimal, seleção CRUD, rejeição de prévia vencida e preservação dos edits entre reruns.
- [ ] Executar RED; implementar grade unificada com categorias e perfis, ações de novo/editar/excluir/bloquear/ativar, prévia opcional e um Salvar alterações; GREEN.
- [ ] Commit.

### Task 4: Folhas por lista e layout de planilha
**Files:** pricing_sheets_ui.py, pricing_service.py, pricing_ui.py, tests/test_pricing_sheet_workflow.py, tests/test_pricing_catalog.py.
**Interfaces:** save_draft aceita proposed_prices; preview_draft simula; activate aplica propostas autorizadas e recalcula a união dos dependentes em uma publicação. UI mantém versão de abertura e identidade por item/revisão.
- [ ] Testar rascunho com proposta sem alterar preço, publicação atualizando outros itens, proposta vencida rejeitada, ausência de permissão e rollback.
- [ ] AppTest cobre lista/visualização/edição, tempos/margem e seleção imediata do novo rascunho.
- [ ] Executar RED; implementar blocos de planilha, propostas globais e publicação; GREEN.
- [ ] Commit.

### Task 5: Verificação e liberação em teste
- [ ] Suíte completa local e PostgreSQL de CI, revisão independente do branch e regressões dos achados importantes.
- [ ] PR para teste, merge autorizado pelo escopo e acompanhamento do deploy automático; main permanece preservada.
- [ ] Registrar evidências e decisões, informar alterações e limites relevantes ao usuário.
