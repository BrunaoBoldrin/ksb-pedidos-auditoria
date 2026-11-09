# Central de custos — miniplanilhas juntas

## Escopo aprovado

Quatro tabelas editáveis de largura total, empilhadas: matérias-primas, componentes, custos de produção e serviços externos. Inclusão de várias linhas diretamente na tabela, colagem de células, preenchimento por teclado e um único **Salvar tudo**. Custos ligados a folhas ou histórico podem ser editados, mas não removidos. Campos técnicos opcionais são mostrados em conjunto, sem ficha por registro. Valores financeiros mantêm precisão decimal e entrada brasileira.

Implementar na interface existente. A avaliação de substituição do Streamlit foi consultiva; a aprovação deste turno escolheu o layout. Não alterar fórmulas, cadastro fiscal, esquema do banco ou produção.

## Etapas

1. Proteger o contrato de edição em testes: quatro grupos, múltiplas linhas novas, última célula preservada ao adicionar/navegar, envio único, erro/conflito mantendo rascunho, remoção protegida e consulta sem permissão de escrita.
2. Substituir cartões/ficha de inclusão por grades com identidades estáveis. Manter a edição de células no navegador, sem recarregar a cada digitação; capturar deltas antes de ações e navegação. Regenerar grades só quando estrutura ou configuração muda; inclusão começa vazia e validação ocorre no salvamento. Preservar custos ocultos, versão original, códigos editáveis e defaults. Bloquear remoção de referências conhecidas ou desconhecidas antes de enviá-la ao serviço; servidor continua sendo autoridade.
3. Executar suíte completa, verificar visualmente com dados sintéticos e revisar a alteração de forma independente. Cobrir recálculo/atomicidade com os testes PostgreSQL existentes e casos adicionais se necessários.
4. Commit e PR destinados a `teste`; aguardar CI, integrar e verificar deploy do ambiente isolado de teste. Manter `main` e banco de produção intactos.

## Validação

`python -m unittest discover -s tests -q`. Testes de interface via AppTest com simulação apenas da fronteira do banco; testes de serviço usam PostgreSQL com schemas efêmeros. Inspeção local em navegador com dados fictícios. Conferir conflitos de edição, preço inválido, zero sem justificativa, códigos duplicados, linha vazia, exclusão proibida, rascunho entre telas e eventos simultâneos antes de publicar.
