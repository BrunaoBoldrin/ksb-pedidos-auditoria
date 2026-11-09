# Conciliação das folhas Excel

Pedido aprovado: todos os campos de entrada relevantes das dez fontes acessíveis no sistema, equivalência numérica reproduzível dos exemplos, correção de lacunas e validação em teste.

- Mapear fontes e divergências usando fórmulas, não apenas valores cacheados. Nunca publicar fontes comerciais privadas no repositório público.
- Completar os campos de negócio da folha comercial e ferramental por base explícita de amortização; preservar entradas não visíveis ao editar.
- Disponibilizar conferência das planilhas originais recalculável e editável. Os arquivos usam custos históricos diferentes para o mesmo insumo e algumas fórmulas anômalas. Guardar originais imutáveis, edições versionadas e comparação com saídas da fonte. Manter o preço comercial atual dependente do catálogo e NCM, identificando a diferença entre as bases.
- Validar dez fontes por subtotal, custo, PV lote e PV por peça. Cobrir edição de entradas, salvamento, concorrência, permissões, limites do interpretador e preservação do preço comercial.
- Dados somente no banco teste. CI, revisão independente e navegador antes de integrar à branch teste e conferir deploy.
