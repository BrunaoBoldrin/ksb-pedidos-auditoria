# Precificação dinâmica por folha de processo

## Objetivo
Cada item possui uma folha de processo para uma peça acabada. O preço é calculado a partir de custos compartilhados. O cadastro técnico não fornece preço alternativo. A análise comercial usa exclusivamente a última publicação válida da folha.

## Escopo aprovado
- Tabelas separadas para matéria-prima, componentes, processos internos e serviços externos.
- Consumos, dimensões do blank e da peça, conversões de unidade, preparação/execução, pessoas, eficiência e amortização unitária.
- Margem, encargos de venda, comissão e política de arredondamento explícitos.
- Base comercial validada: PV já líquido ou PV com ICMS/PIS/COFINS sem IPI, convertido pela regra fiscal existente.
- Rascunhos não alteram o preço. Ativação/arquivamento são auditados.
- Prévia de impacto e atualização atômica de todas as folhas ativas dependentes.
- Referências imutáveis nas auditorias anteriores.
- Permissões por usuário e verificação no serviço em cada ação.
- Primeiro deploy no ambiente teste com endpoint isolado. Produção não recebe esta implantação.
- Exemplos internos e credenciais não fazem parte deste repositório público.

## Cálculo
Custo unitário = matéria-prima + componentes + mão de obra corrigida + terceiros + ferramenta.
Mão de obra nominal = horas por peça × tarifa × multiplicador de pessoas aplicável.
Mão de obra corrigida = nominal / eficiência.
PV = custo / (1 − margem − impostos de venda − comissão), com arredondamento configurado.
Custos de compra já líquidos não têm nova dedução. Conversão barra/comprimento exige medida explícita.
A quantidade do pedido multiplica apenas os totais da avaliação, sem ratear a folha por lote.

## Integridade
- Uma revisão ativa por item, snapshots imutáveis, custo compartilhado com identificação estável.
- Escritas serializadas pela versão global; prévias vencidas são recusadas.
- Publicações idempotentes. Qualquer erro desfaz custos e preços do conjunto.
- Revisão efetiva é a mais antiga da composição e seus custos; recalcular não mascara revisão vencida.
- Mudança fiscal que invalide a conversão bloqueia a referência até nova publicação.
- Item sem folha válida fica pendente, independentemente do preço histórico.
- Linhas ativas exigem números finitos, unidades compatíveis, consumo positivo e soma de encargos menor que um.
- Cadastro/importação/exportação técnica sem preços.
- Importação antiga informa que colunas de preço são ignoradas.

## Implantação e transição
Ativação por configuração no serviço de teste, verificada contra endpoint esperado configurado por variável privada.
Migração aditiva guarda os preços legados como arquivo histórico. Durante homologação, suas colunas físicas permanecem por compatibilidade com a inicialização e rollback, mas não são lidas como preço vigente nem editáveis no modo novo.
Regra fiscal existente permanece responsável pela auditoria tributária.

## Entregas
1. Motor de cálculo e testes de comportamento.
2. Persistência PostgreSQL, autorizações e publicações atômicas.
3. Cadastro técnico sem preço e telas de precificação/folhas/permissões.
4. Resolvedor integrado ao parser e contexto de preço persistido em auditorias.
5. Testes PostgreSQL isolados, testes de tela, revisão e deploy somente em teste.

## Verificação
Suíte atual mais testes do cálculo, concorrência, rollback, autorização, idempotência, referências históricas, importação técnica e divergência de preços. Integração PostgreSQL usa esquema descartável exclusivo em banco de CI. Nenhum teste altera dados de produção.

