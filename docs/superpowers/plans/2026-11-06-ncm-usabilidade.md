# Implementação: NCM e usabilidade

Spec: `docs/superpowers/specs/2026-11-06-ncm-usabilidade-design.md`.

## Task 1: cálculo fiscal automático
- Escrever e executar regressões para cálculo sem confirmação, origem NCM, falta de regra e consulta agrupada.
- Usar regras fiscais cadastradas em todos os cálculos atuais; conservar snapshots e impedir referência antiga após mudança fiscal.
- Remover dependência de perfil em novos rascunhos; guardar eficiência e arredondamento próprios.
- Verificar testes unitários e de integração financeira.

## Task 2: folhas e navegação
- Regressões AppTest para botões, ausência de perfis e preços visíveis em visualização/edição.
- Retirar perfis da central e folhas, mostrar impostos automáticos e preços no início.
- Preservar alterações de edição, ações de publicação e os campos de custos já vinculados.

## Task 3: desempenho e entrega
- Medir e reduzir consultas por cálculo, permissões duplicadas, criação de conexões e exportações repetidas.
- Testar reutilização/rollback de conexões e invalidação dos dados de tela.
- Executar suíte completa, PostgreSQL em CI e revisão final independente.
- Publicar somente em teste e verificar commit, deploy e saúde.

## Review Focus
Alíquotas e arredondamento coerentes com a análise de pedidos; NCM inválido não resulta em preço zero; rascunho não substitui preço publicado; revogação de acesso continua imediata; pool nunca compartilha uma transação entre usuários; navegação preserva alterações; referências e snapshots não ficam silenciosamente desatualizados.
