# Plano de execução — compressão e dados verificáveis

## Objetivo e situação

**Minimizar os bytes totais necessários para preservar a evidência e reproduzir
as análises, sem comprometer integridade, cobertura ou rastreabilidade.**

Plano refinado em 28/10/2026. A versão v0.2.0 implementa `inspect`, `benchmark`
em streaming (stored/ZSTD/Brotli), `verify` de arquivos de origem e `pack`/`unpack`
experimental para BU web. Há aquisição gerenciada em `scripts/fetch_source.py`;
o subcomando Rust `download` ainda não a integra. Etapa 1 revisada; fases 2–4
revisadas com correções em `docs/REVISAO-ETAPAS-2-4.md`. G3 passou no membro CSV
de MT; **G4 concluído para o corpus local baixado**, com resultados em
`docs/RESULTADO-COMPRESSAO-MT.md`. Arquivo local v2 fecha o vínculo criptográfico
de execução e implementa `optimize`/`restore`. O manifesto de distribuição v2
antigo continua bloqueado para publicação. A Etapa 5A foi executada para o BU
web de MT 2026 t1 (votos e contexto aprovados; seções físicas bloqueadas e
reconciliações pendentes), com resultados em `docs/ETAPA-5A.md`; expansão nacional,
reconciliação, modelos e distribuição permanecem nas etapas seguintes.
Um plano ou status declarado não constitui evidência de execução.

Documentos de execução:

- `docs/ETAPA-1.md`: primeira entrega delimitada e critérios de revisão.
- `docs/PROMPT-ETAPA-1.md`: instrução para o agente implementador.
- `docs/DADOS-BRUTOS.md`: mapa inicial dos layouts observados em MT e regras
  para documentar novos anos, turnos, abrangências e variantes.
- `docs/ARQUITETURA.md` e `docs/VERIFICACAO.md`: contratos e garantias.
- `docs/PLANO-ANALISE.md`: liberação por uso e dependências analíticas.
- `docs/ETAPA-5A.md`: execução, resultados e limites da análise descritiva de
  MT 2026 t1; contrato em `spec/analyze-v1.md`.

## Contratos que orientam todas as etapas

1. **Evidência:** preservar os downloads originais, membros, assinaturas e
   documentos de leiaute. FORENSIC restaura os bytes do objeto original
   declarado. Reconstruir membros não prova identidade do ZIP baixado.
2. **Canônico analítico:** preservar campos e ocorrências com tipos exatos,
   sentinelas, precisão, categorias e contexto; esquema e transformação
   versionados. Campo desconhecido bloqueia interpretação automática.
3. **Produtos derivados:** agregações, filtros e modelos são regeneráveis;
   suas exclusões e limites são explícitos. ANALYTICAL não autoriza descartar
   a única cópia de informação potencialmente necessária a outra análise.
4. **Unidades:** separar contexto seção/cargo, votos por votável,
   correspondências e eventos. Aptos/comparecimento repetidos por votável
   não são somados por linha. Compartilhar contexto exige verificar igualdade.
5. **Proveniência:** ocorrência → hash da fonte, membro/ordinal, versão do
   esquema e transformação. Hash de arquivo sozinho não localiza um registro.
6. **Comparação justa:** medir a mesma informação e garantia; incluir
   dicionários, índices, resíduos, proveniência e originais ainda necessários.
7. **Falha explícita:** erro de leitura, hash, interpretação ou cardinalidade
   não pode resultar em conjunto aparentemente completo. Recortes válidos
   exigem escopo, lacunas e limitações documentados.
8. **Compatibilidade:** alteração incompatível exige versão, teste e `spec/`.
   Manifesto de origem e manifesto de distribuição são contratos distintos.
9. **Limites:** valores operacionais em `scripts/limits.env`; processamento
   em streaming/lotes, com RAM e disco temporário medidos na escala requerida.

## Etapa 1 — Base confiável e mapa reproduzível de MT

Escopo fechado em `docs/ETAPA-1.md`. Não executar etapas posteriores nesta entrega.

- Corrigir aprovação de versão incompatível, omissões de inventário, caminhos
  duplicados e escapes por symlinks; distinguir link da raiz de links internos.
- Preservar erros acumulados pelo validador do repositório e impedir que
  validação incompleta de schema seja apresentada como validação completa.
- Automatizar inventário dos downloads e membros ZIP; documentar cabeçalhos
  e perfis estruturais dos CSVs, sem transformá-los em tabelas analíticas.
- Usar os dados já baixados de MT; preservar snapshots e identificar escopo
  pelo conteúdo, sem assumir que pasta, nome ou extensão bastem.
- Produzir evidências locais, testes de regressão e documentação reutilizável.

**Saída G1:** testes negativos realmente reprovam; fonte válida continua
verificável; mapa identifica arquivos, membros, layouts, turnos observados,
limitações e objetos ainda não decodificados. Revisão humana antes da Etapa 2.

## Etapa 2 — Ingestão gerenciada e contratos de dados

- Implementar aquisição com URL por arquivo, ambiente, identificadores
  oficiais, metadados HTTP disponíveis, checkpoints e retomada validada.
  Escrever parciais separadamente e concluir por operação atômica.
- Preservar snapshots e correções; não presumir que arquivos coletados juntos
  pertençam à mesma atualização. Completar inventário esperado por fonte.
- Formalizar contratos de origem, dataset e execução, suas versões e vínculos
  por hash; resolver campos desconhecidos, extensões e migração dos manifestos.
- Definir objeto restaurável, unidade de decodificação, dependências entre
  pacotes, ordem e hash do conjunto reconstruído antes de publicar pacotes.
- Definir esquema canônico por família: tipos, chaves candidatas, cardinalidades,
  sentinelas, precisão/fuso e regras de agregação. Validar chaves nos dados;
  nunca converter hipótese de unicidade em deduplicação automática.
- Planejar consultas representativas antes de escolher a representação física.

**Saída G2:** fontes e escopos documentados, contratos versionados, testes de
compatibilidade e regras executáveis para a primeira família a transformar.

## Etapa 3 — MVP reversível por família em MT

- Uma família por vez, começando pelo CSV BU web disponível e seu contexto.
- Desenvolver transformador, inverso e verificação no mesmo incremento.
- Preservar bytes originais ou resíduos suficientes à garantia declarada;
  validar valores, campos, multiplicidades e ordens com significado.
- Documentar diferenças entre tabelas canônicas e bytes restaurados. Não
  confundir igualdade de somas com equivalência de todos os registros.
- Incluir rastreabilidade por ocorrência, testes de corrupção, interrupção,
  campos novos, sentinelas, zeros significativos, duplicatas e overflow.
- Parsers binários exigem especificação oficial da versão e testes próprios;
  inventariar arquivos opacos não significa decodificá-los corretamente.

**Saída G3:** restauração SHA-256 e equivalência semântica aprovadas separadamente;
verificador reproduzível, com leitura independente onde houver risco de erro comum.

## Etapa 4 — Baselines completos e decisão de armazenamento

**Executada em MT.** Matriz e critérios em `docs/ETAPA-4.md`; decisão e evidências
reais em `docs/RESULTADO-COMPRESSAO-MT.md`. O resultado vale para os arquivos
locais declarados, preservando a limitação já mapeada de t2.

- Comparar stored, ZSTD, dicionários com treino/ajuste/avaliação separados,
  XZ/LZMA2, Brotli, agrupamentos sólidos/blocos e Parquet+ZSTD quando aplicável.
- Separar preservação dos bytes de compressão do mesmo modelo canônico.
- Incluir custo de esquema, índices, dicionários, vínculos, multiplicidades,
  resíduos, originais retidos e materializações. Separar custo permanente,
  replicação e pico temporário.
- Registrar hashes do corpus, versões/parâmetros, ambiente, threads, tempos,
  variação entre execuções, pico RAM/disco e consultas representativas.
- Comparar arquivos individuais e agrupamentos, incluindo os já comprimidos.
  Usar o conjunto disponível e amostras estratificadas identificadas.
- Medir recuperação por seção/cargo e agregações territoriais, além de bytes.
  O benchmark atual usa streaming; medições locais não comprovam viabilidade
  nem custo de consultas na escala nacional.

**Saída G4:** experimento reproduzível identifica a melhor alternativa por
requisito; formato próprio só avança com oportunidade demonstrada. Nenhuma taxa
é prometida antecipadamente; manter stored pode ser o melhor resultado válido.

## Etapa 5 — Validação analítica do MVP de MT

**Parcialmente executada (5A, 28/10/2026).** O BU web de MT 2026 t1 teve
contrato, controles e análise descritiva aprovados; comparação entre turnos,
reconciliação e modelos continuam pendentes. Ver `docs/ETAPA-5A.md`.

- Aplicar `docs/PLANO-ANALISE.md` ao escopo com dependências completas.
- Verificar contexto repetido, cardinalidades de joins, correspondências,
  seções agregadas, categorias e denominadores antes de qualquer inferência.
- Um turno permite seus próprios controles; comparação entre turnos exige
  ambos os lados completos para a unidade e o método declarados.
- Produzir relatório de qualidade e uma análise simples reproduzível;
  calibração, falsificação e controle de falsos positivos acompanham os modelos.

**Saída G5:** consultas exigidas corretas, fontes rastreáveis, limitações
explícitas e execução analítica versionada. Publicação não é pré-requisito
para validar um uso local; tem seu próprio portão.

## Etapa 6 — Expansão nacional

- Reexecutar o mapeador por ano/ambiente/abrangência; detectar variantes de
  cabeçalho/leiaute e cadastrar adaptadores, sem presumir que MT cobre o Brasil.
- Preservar UFs, exterior e outros códigos oficiais como categorias distintas,
  conforme a fonte; `BR` não pode rotular conjunto parcial como completo.
- Reconciliar universo esperado, encontrado, verificado, interpretado e apto
  a cada uso por tipo/turno. Não inferir ausência global por falta no disco local.
- Processar em streaming/lotes, com retomada, RAM e disco medidos; alvo já
  estabelecido: executar no ambiente de 32 GB, sem converter projeção em medição.
- Validar leitura localizada, dependências de dicionários e recuperação após falha.

**Saída G6:** mesmas garantias do MVP em escopo nacional explicitamente coberto;
variações e exceções documentadas, sem novos descartes silenciosos.

## Etapa 7 — Otimização extrema e distribuição

- Explorar dicionários, delta, VarInt, bit packing, RLE, layouts, template de
  logs e deduplicação física exata com multiplicidades e vínculos preservados.
- Melhorias entram apenas com ganho reproduzível sobre baseline equivalente,
  restauração aprovada e custo aceitável de consulta, recursos e manutenção.
- Publicação exige artefatos completos, validação estrutural e de conteúdo,
  restauração/equivalência conforme perfil e reverificação dos assets publicados.
  `validated` escrito em JSON não substitui relatórios nem execução.
- Adiar Merkle/provas sob demanda até existir necessidade e codificação canônica
  especificada; não bloquear o MVP por essa estrutura.

**Saída G7:** pacote verificável por terceiros, índice coerente, documentação e
benchmark reproduzíveis. Hash do projeto não é assinatura do TSE; anomalias
não autorizam conclusão política ou alegação de fraude.
