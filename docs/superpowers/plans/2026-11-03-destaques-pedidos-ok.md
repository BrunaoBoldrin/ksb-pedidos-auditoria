# Destaques dos Pedidos Aprovados Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agrupar o diagnóstico por pedido, exibir pedidos totalmente aprovados primeiro e destacar, por item, Código Glória, preço unitário final com impostos e prazo até a entrega.

**Architecture:** O parser passará ao DataFrame de análise os campos de cadastro e entrega que já consulta. Funções puras em `ui_components.py` selecionarão e formatarão os destaques e classificarão os pedidos; `app.py` ficará responsável apenas por renderizar os grupos e preservar os diagnósticos existentes.

**Tech Stack:** Python, pandas, Streamlit, unittest/Streamlit AppTest.

**Spec:** `docs/superpowers/specs/2026-11-03-destaques-pedidos-ok-design.md`

## Global Constraints

- Implementar a partir da branch `teste` e enviar somente para `teste`.
- Não alterar regras fiscais, comerciais, de revisão de preço, auditoria ou implantação.
- Não alterar banco de dados nem criar campos persistentes.
- Pedido OK exige que todos os seus itens tenham status fiscal e comercial `OK`.
- Preço destacado é o valor total da linha dividido pela quantidade.

## Review Focus

- Unidade com acento ou texto adicional deve selecionar corretamente Jundiaí ou Várzea.
- Pedido misto deve permanecer no grupo pendente mesmo quando o filtro mostra apenas seu item aprovado.
- Quantidade zero, ausente ou inválida não pode causar divisão por zero.
- Data inválida, entrega hoje e entrega vencida devem produzir textos inequívocos.
- Código interno e descrição vindos do banco/PDF devem continuar escapados antes de entrar em HTML.

---

### Task 1: Enriquecer o resultado do parser

**Files:**
- Modify: `parser.py`
- Test: `tests/test_parser_items.py`

**Interfaces:**
- Consumes: dicionário retornado por `buscar_material_por_codigo(codigo_material)` e `data_entrega` já extraída do bloco do item.
- Produces: colunas `Código Interno Jundiaí`, `Código Interno Várzea` e `Data Entrega` no DataFrame `analises` de `processar_pdf`.

- [ ] **Step 1: Escrever testes falhos do enriquecimento**

Adicionar casos que façam o mock do material com os dois códigos internos e confirmem as três novas colunas; confirmar também valores vazios quando o material não estiver cadastrado.

- [ ] **Step 2: Executar o teste e verificar a falha**

Run: `python -m unittest tests.test_parser_items -v`
Expected: FAIL porque as colunas ainda não existem.

- [ ] **Step 3: Implementar o enriquecimento em `processar_pdf`**

Copiar os dois códigos internos do material cadastrado e a data de entrega extraída para cada dicionário de `analises`, usando texto vazio quando o cadastro não existir.

- [ ] **Step 4: Executar o teste e verificar sucesso**

Run: `python -m unittest tests.test_parser_items -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parser.py tests/test_parser_items.py
git commit -m "Adicionar dados operacionais ao diagnóstico"
```

### Task 2: Calcular e ordenar os destaques de apresentação

**Files:**
- Modify: `ui_components.py`
- Test: `tests/test_ui_components.py`

**Interfaces:**
- Consumes: linhas pandas com `Unidade Pedido`, códigos internos, `Valor Pedido`, `Quantidade` e `Data Entrega`; DataFrames completo e visível.
- Produces: `selecionar_codigo_gloria(linha) -> str`, `calcular_preco_unitario_final(linha) -> float | None`, `formatar_prazo_entrega(data_entrega, data_referencia=None) -> str` e `agrupar_pedidos(df_lote, df_visivel) -> list[tuple[str, str, pd.DataFrame]]`.

- [ ] **Step 1: Escrever testes falhos dos cálculos e agrupamento**

Cobrir Jundiaí, Várzea com e sem acento, unidade desconhecida, código ausente, total 240/quantidade 2, quantidade zero, prazo futuro/hoje/vencido/inválido, pedido totalmente OK e pedido misto. Confirmar que o pedido OK vem primeiro e que os itens são ordenados numericamente.

- [ ] **Step 2: Executar os testes e verificar a falha**

Run: `python -m unittest tests.test_ui_components -v`
Expected: FAIL porque as quatro funções ainda não existem.

- [ ] **Step 3: Implementar as funções puras em `ui_components.py`**

Normalizar a unidade removendo acentos e comparando por palavra; validar números sem lançar exceção; interpretar entrega em `%d.%m.%Y`; classificar cada pedido usando o lote completo e agrupar apenas as linhas visíveis.

- [ ] **Step 4: Executar os testes e verificar sucesso**

Run: `python -m unittest tests.test_ui_components -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui_components.py tests/test_ui_components.py
git commit -m "Preparar destaques e ordenação dos pedidos"
```

### Task 3: Renderizar pedidos agrupados na tela

**Files:**
- Modify: `app.py`
- Modify: `assets/design-system.css`
- Test: `tests/test_app_design.py`

**Interfaces:**
- Consumes: as quatro funções de `ui_components.py` produzidas na Task 2.
- Produces: área `Resultado por pedido` com blocos `Pedidos OK` e `Pedidos com pendências`, cabeçalho único por pedido e três destaques operacionais em cada item.

- [ ] **Step 1: Escrever o teste falho da tela agrupada**

Montar um lote com um pedido OK e um pedido misto inseridos fora da ordem; confirmar no HTML/texto do AppTest que o pedido OK aparece primeiro, cada cabeçalho aparece uma vez, os três destaques são exibidos e os diagnósticos atuais continuam presentes.

- [ ] **Step 2: Executar o teste e verificar a falha**

Run: `python -m unittest tests.test_app_design.AppDesignTests -v`
Expected: FAIL porque a tela ainda usa a lista plana.

- [ ] **Step 3: Implementar o agrupamento em `exibir_cards_auditoria`**

Manter resumo, filtros e contagem; renderizar os grupos na ordem calculada, um título por pedido e, dentro de cada item, as métricas `Código Glória`, `Preço unitário com impostos` e `Prazo de entrega`, seguidas dos diagnósticos e expansores atuais.

- [ ] **Step 4: Adicionar estilos mínimos para os cabeçalhos de pedido**

Usar tokens existentes no design system; não introduzir cores ou tipografia fora do padrão atual.

- [ ] **Step 5: Executar os testes de tela e verificar sucesso**

Run: `python -m unittest tests.test_app_design.AppDesignTests -v`
Expected: PASS.

- [ ] **Step 6: Executar a suíte completa**

Run: `python -m unittest discover -s tests -v`
Expected: todos os testes PASS.

- [ ] **Step 7: Commit**

```bash
git add app.py assets/design-system.css tests/test_app_design.py
git commit -m "Agrupar pedidos e destacar dados operacionais"
```

### Task 4: Revisão e entrega na branch de teste

**Files:**
- Verify: todos os arquivos alterados nas Tasks 1–3.

**Interfaces:**
- Consumes: branch implementada e suíte verde.
- Produces: pull request com base `teste`, revisão final concluída e merge somente em `teste`.

- [ ] **Step 1: Revisar o diff contra `origin/teste`**

Confirmar que não há mudanças de regras de diagnóstico, banco de dados ou implantação.

- [ ] **Step 2: Executar verificação final**

Run: `python -m unittest discover -s tests -v`
Expected: todos os testes PASS e árvore de trabalho limpa após o commit final.

- [ ] **Step 3: Abrir PR para `teste` e revisar o resultado**

Base: `teste`; head: `codex/destaques-pedidos-ok`.

- [ ] **Step 4: Fazer merge do PR em `teste`**

Não atualizar `main`.
