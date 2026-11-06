# Central de custos e navegação por listas

## Solicitação
Restaurar a seleção por checkbox em Itens Cadastrados. Editar permissões dentro do formulário do usuário selecionado. Listar folhas e apresentar a composição por peça em blocos próximos da planilha Excel. Listar custos e perfis com ações de novo, editar, excluir e bloquear/ativar. Unificar os valores compartilhados em uma tela editável e salvar várias alterações de uma vez, recalculando automaticamente as folhas dependentes.

## Abordagem
Manter Python/Streamlit/PostgreSQL e o cálculo atual. A central apresenta todos os catálogos em uma grade editável, com categoria, identificação, unidade, custo, fatores, medidas, situação e revisão. Perfis universais ficam também nessa mesma tela. Um único botão Salvar alterações valida e publica o conjunto atomicamente. A prévia de impacto é opcional; não exige abrir e salvar um formulário para cada valor.

Listas técnicas e de folhas usam checkbox e botões. Folhas abrem em visualização ou edição, com identificação, matérias-primas, componentes, operações, terceiros e resumo de formação do preço. Tempos, consumos e margem pertencem à revisão. Preços de insumos continuam compartilhados: alterações feitas na folha são propostas no rascunho e aplicadas à tabela central na publicação, recalculando todos os dependentes. Não criar exceções locais silenciosas que impeçam propagação.

Usuários continuam sendo selecionados na tabela. Perfil, situação e permissões são salvos na mesma transação do formulário. Administradores mantêm acesso integral. Sessões revalidam autorização no servidor.

## Integridade
- Cada grade mantém a versão e os dados de origem enquanto há edições; reruns não renovam silenciosamente uma edição antiga.
- Custos e perfis alterados na mesma operação publicam a união dos dependentes uma única vez.
- Erro, versão vencida ou autorização removida desfaz todo o salvamento.
- Exclusão somente de registros sem vínculo; histórico e revisões anteriores são preservados.
- Bloqueio de um custo ou perfil usado por folha ativa é recusado com orientação para substituir a referência antes; evita retirar custos obrigatórios silenciosamente.
- Preços propostos na folha exigem permissão de custos; salvar rascunho não altera custo global nem preço vigente.
- Publicar proposta de preço já vencida é recusado; nova simulação/edição deve usar o custo atual.
- Trocar somente o insumo carrega o preço e a unidade de custo do novo insumo, sem propor alteração global indevida.
- Reabrir uma proposta preserva sua versão original; reconciliar usa a ação explícita Atualizar preços da folha.
- Alterar o perfil preserva os campos locais e a composição; somente eficiência, impostos e arredondamento recebem os valores do perfil.
- Sem alteração de produção; primeiro destino continua sendo teste e seu banco isolado.
- Exemplos e testes publicados são sintéticos.

## Verificação
Interações de checkbox/edição, permissões embutidas, edição de várias linhas e perfis com um salvar, persistência entre reruns, exclusão/bloqueio com vínculos, proposta na folha sem efeitos antes de publicar, atualização conjunta dos dependentes, concorrência, rollback e idempotência. Revisão independente ao final e CI PostgreSQL antes do deploy em teste.
