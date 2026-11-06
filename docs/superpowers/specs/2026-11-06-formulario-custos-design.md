# Formulário único de custos

Substituir a grade da central por um formulário de campos em cartões, conforme a referência visual fornecida. Agrupar custos de produção e padrões comerciais lado a lado; matérias-primas, componentes e serviços em cartões na mesma página. Campos principais exibem nome, valor e unidade, em duas colunas por cartão. Opções adicionais ficam recolhidas para não ocupar a leitura dos preços.

Os campos representam os registros universais já usados pelas folhas. Adicionar campo informa nome, categoria, unidade e preço; o registro aparece no formulário e é persistido ao salvar o conjunto. Permitir adicionar perfis na mesma página. Não importar valores ou regras do exemplo visual de outro sistema.

Um único Salvar alterações envia os valores de todos os cartões ao serviço transacional existente e recalcula as folhas dependentes. Adicionar ou remover um campo também submete e conserva os demais valores já digitados, sem gravar parcialmente no banco. Nenhum seletor ou botão Editar é necessário para alterar cada preço.

Consultar os vínculos dos custos e perfis no mesmo snapshot do catálogo. Campos vinculados a qualquer revisão de folha, inclusive rascunho e histórico, permanecem visíveis e têm remoção desabilitada. Sem informação confiável de vínculo, a remoção fica indisponível. O servidor revalida os vínculos ao salvar, preservando as restrições e o controle de versão existentes.

Manter precisão Decimal, permissões, histórico, bases fiscais e o escopo exclusivo do branch teste. Esta alteração não muda as folhas, os usuários ou o cadastro técnico.
