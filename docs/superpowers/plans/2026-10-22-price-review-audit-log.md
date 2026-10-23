# Price Review and Audit Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar vigência de preços por três meses, painel administrativo, bloqueio de reavaliação de pedidos aprovados e logs persistentes, sem alterar as demais regras existentes.

**Architecture:** Regras determinísticas de preço e reavaliação ficarão em módulos Python puros e testáveis. `parser.py` aplicará somente o novo diagnóstico; `database.py` fará migrações idempotentes e persistência transacional; `app.py` integrará o bloqueio e as duas telas administrativas mantendo intactos os demais fluxos.

**Tech Stack:** Python, Streamlit, pandas, pdfplumber, psycopg2/PostgreSQL (Neon), unittest.

**Spec:** `docs/superpowers/specs/2026-10-22-price-review-audit-log-design.md`

## Global Constraints

- Implementar exclusivamente na branch `teste`.
- Não alterar regras fiscais, fórmulas, limites de divergência, perfis ou menus existentes fora das adições especificadas.
- Usar três meses-calendário; a data-limite ainda é válida e o dia seguinte é vencido.
- Data vazia ou inválida torna o preço vencido.
- A mensagem deve ser exatamente `PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.`
- Somente mudança real do preço, arredondada aos centavos, gera histórico.
- Os menus `Revisão de Preços` e `Log` são exclusivos do perfil `ADMIN`.
- Migrações devem ser idempotentes e preservar todos os dados existentes.

## Review Focus

- Datas em fim de mês, inclusive 31 de janeiro, devem calcular o limite sem erro e sem antecipar o vencimento; coberto em Task 1.
- Um lote com pedidos novos e previamente aprovados não pode processar nenhum aprovado sem as duas confirmações; coberto em Task 4.
- Uma falha após iniciar a persistência não pode deixar pedido sem itens/auditorias nem mostrar sucesso; coberto em Task 2 e Task 4.
- Valores equivalentes após arredondamento para centavos não podem gerar falso log; coberto em Task 2.
- Uma aprovação antiga continua exigindo confirmação mesmo após uma reavaliação pendente; coberto em Task 2.

---

### Task 1: Regras puras de vigência e confirmação

**Files:**
- Create: `price_rules.py`
- Create: `audit_rules.py`
- Create: `tests/test_price_rules.py`
- Create: `tests/test_audit_rules.py`

**Interfaces:**
- Produces: `parse_review_date(value) -> date | None`, `add_calendar_months(value: date, months: int) -> date`, `is_price_outdated(value, today: date | None = None) -> bool`.
- Produces: `can_reaudit(confirmed_audit: bool, confirmed_implementation: bool) -> bool`, `summarize_item_statuses(items: list[dict]) -> tuple[str, str]`.

- [ ] **Step 1: Write failing tests for calendar validity**

Test exact three-month boundary, the following day, empty/invalid values, ISO and KSB date formats, and 31 January → 30 April behavior.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_price_rules -v`
Expected: FAIL because `price_rules` does not exist.

- [ ] **Step 3: Implement the minimal date rules**

Accept `%Y-%m-%d`, `%d/%m/%Y` and `%d.%m.%Y`; clamp calendar-month addition to the last valid day of the destination month.

- [ ] **Step 4: Write and verify failing tests for confirmation and status consolidation**

Assert that only two `True` confirmations release reauditing, and that one non-`OK` item makes the corresponding consolidated stage pending.

- [ ] **Step 5: Implement `audit_rules.py` and run both test modules**

Run: `python -m unittest tests.test_price_rules tests.test_audit_rules -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add price_rules.py audit_rules.py tests/test_price_rules.py tests/test_audit_rules.py
git commit -m "feat: adicionar regras de vigência e reavaliação"
```

### Task 2: Persistência de auditorias e histórico de preços

**Files:**
- Modify: `database.py`
- Create: `tests/test_database_history.py`

**Interfaces:**
- Consumes: `summarize_item_statuses(items)` from Task 1.
- Produces: `pedido_ja_aprovado(numero_pedido: str) -> bool`.
- Produces: `registrar_auditoria_pedido(dados_pedido: dict, itens: list[dict], usuario: str, reavaliacao: bool, confirmou_auditoria: bool, confirmou_implantacao: bool, arquivo_pdf: str) -> int`.
- Produces: `listar_logs_auditorias() -> list[tuple]`, `listar_logs_revisoes_preco() -> list[tuple]`.
- Extends: `atualizar_material(..., origem_alteracao: str = "ALTERAÇÃO PELO SISTEMA")` without changing existing positional arguments.

- [ ] **Step 1: Write failing migration tests**

Using a controlled fake cursor at the PostgreSQL boundary, assert idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements for audit metadata and creation of `revisoes_preco` without a destructive foreign key.

- [ ] **Step 2: Run migration test and verify RED**

Run: `python -m unittest tests.test_database_history.DatabaseMigrationTests -v`
Expected: FAIL because the new schema is absent.

- [ ] **Step 3: Implement idempotent schema changes**

Extend `pedidos` with user, execution type, both confirmation flags and timestamp-compatible upload data; create immutable `revisoes_preco` with material snapshot, old/new values, user, timestamp and origin.

- [ ] **Step 4: Write failing repository tests**

Cover: detecting any historic fully approved run; retaining that detection after a later pending run; atomic insertion of pedido/items/auditorias; manual and Excel origins; no log for insert; no log for equal cent values such as `100.00` and `100.004`; rollback propagation.

- [ ] **Step 5: Implement repository functions and transactional price logging**

Read the previous material inside the same update transaction. Compare values with `Decimal` rounded to two places using `ROUND_HALF_UP`; insert a revision only when an existing material changes by at least one cent. Reuse the existing `_cursor(commit=True)` rollback behavior.

- [ ] **Step 6: Run database tests**

Run: `python -m unittest tests.test_database_history -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add database.py tests/test_database_history.py
git commit -m "feat: persistir auditorias e revisões de preço"
```

### Task 3: Diagnóstico comercial e leitura preliminar do pedido

**Files:**
- Modify: `parser.py`
- Modify: `tests/test_parser_items.py`
- Create: `tests/test_parser_price_review.py`

**Interfaces:**
- Consumes: `is_price_outdated(value, today)` from Task 1.
- Produces: `extract_pdf_text(pdf_path) -> str`, `extract_order_number(pdf_path) -> str`.
- Extends: `processar_pdf(pdf_path, price_reference_date: date | None = None)` with a backward-compatible optional date used only by the new price-validity rule.

- [ ] **Step 1: Write the failing stale-price diagnostic test**

Build a fake PDF whose order price equals the registered price but whose review date is over three months old. Assert status `PENDENTE - REVISÃO DE PREÇO`, the exact mandatory message and no overall commercial approval.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_parser_price_review -v`
Expected: FAIL because equal prices currently produce `OK`.

- [ ] **Step 3: Implement stale-price precedence**

Keep the existing material-missing, price-missing, price-divergence and fiscal rules unchanged. Add the new stale branch only between missing price and divergence, retaining price difference details when present.

- [ ] **Step 4: Write failing extraction tests**

Assert that preliminary extraction returns the order number and that `processar_pdf` reuses the same text reader without changing current item extraction.

- [ ] **Step 5: Implement shared text/order extraction and run parser tests**

Run: `python -m unittest tests.test_parser_price_review tests.test_parser_items -v`
Expected: PASS, including all existing parser regressions.

- [ ] **Step 6: Commit**

```bash
git add parser.py tests/test_parser_items.py tests/test_parser_price_review.py
git commit -m "feat: bloquear aprovação com preço desatualizado"
```

### Task 4: Fluxo Streamlit, painel administrativo e aba Log

**Files:**
- Modify: `app.py`
- Create: `ui_rules.py`
- Create: `tests/test_admin_views.py`
- Create: `tests/test_reaudit_workflow.py`

**Interfaces:**
- Consumes: rules from Tasks 1 and 3 and repository functions from Task 2.
- Produces in `ui_rules.py`: `menu_options_for_profile(profile) -> list[str]`, `build_outdated_prices_table(material_rows, today) -> pandas.DataFrame`, `filter_audit_log(df, query, user, start, end) -> pandas.DataFrame`, and `filter_price_log(...) -> pandas.DataFrame` for deterministic UI tests.
- Produces: `process_uploaded_orders(files, user, is_reaudit, confirmations)`, which persists each PDF only after successful processing.

- [ ] **Step 1: Write failing table/menu tests**

Assert that only positive-price stale materials appear, invalid dates show `Sem data de revisão` and sort before dated records, oldest valid dates follow, and `Revisão de Preços`/`Log` appear only in the `ADMIN` menu.

- [ ] **Step 2: Run view tests and verify RED**

Run: `python -m unittest tests.test_admin_views -v`
Expected: FAIL because builders and menus do not exist.

- [ ] **Step 3: Implement admin menu additions and views**

Add the total card, stale-material table, audit log tab and price-revision tab with query/user/date filters. Keep the existing `Histórico de Auditorias` entry and all existing profile access unchanged.

- [ ] **Step 4: Write failing reauditing workflow tests**

Cover: new order processes immediately; approved order stops at preflight; one checkbox cannot release; both checkboxes release; mixed batch lists every approved order and does not bypass them; persistence failure prevents the success message; each PDF is saved independently.

- [ ] **Step 5: Implement the confirmation gate and persistence integration**

Use `extract_order_number` before full processing. Store only the pending gate state in `st.session_state`; do not display or persist analysis results before both confirmations. Pass `IMPORTAÇÃO EXCEL` only from the import loop and the default system origin from manual editing.

- [ ] **Step 6: Run UI/workflow tests**

Run: `python -m unittest tests.test_admin_views tests.test_reaudit_workflow -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app.py ui_rules.py tests/test_admin_views.py tests/test_reaudit_workflow.py
git commit -m "feat: adicionar painéis e confirmação de reauditoria"
```

### Task 5: Regressão completa e publicação na branch de teste

**Files:**
- Verify only: all changed source and test files

**Interfaces:**
- Consumes all previous tasks; produces no new behavior.

- [ ] **Step 1: Run the complete suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS with no warnings or errors.

- [ ] **Step 2: Run static syntax and diff checks**

Run: `python -m py_compile app.py parser.py database.py price_rules.py audit_rules.py ui_rules.py`
Expected: exit 0.

Run: `git diff --check origin/teste...HEAD`
Expected: no output.

- [ ] **Step 3: Inspect scope**

Confirm the diff touches only the documented new rules, persistence, views and their tests; explicitly reject unrelated refactors.

- [ ] **Step 4: Push to `teste` and verify the remote SHA**

Run: `git push origin HEAD:teste`
Expected: fast-forward update. Fetch `teste` and verify its head equals local `HEAD`.
