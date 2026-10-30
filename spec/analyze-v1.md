# `tsepack analyze` — contrato analítico v1 (Etapa 5A)

Perfil desta versão: **`mt-2026-t1-bweb-v1`**, restrito a **MT, ano 2026,
turno 1**, BU web da geração/snapshot aceito. Outros anos, UF, turnos,
gerações ou famílias exigem novo perfil e versão de contrato. O registro de
perfis (`profile_for_id`) rejeita perfil desconhecido sem inferir a partir
dos dados; novo snapshot exige novo perfil versionado.

## Snapshot aceito

O perfil fixa o CSV pelo SHA-256
`5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3`
(411.757.026 bytes, 891.997 registros) e, quando a entrada é uma view da
Etapa 4, também:

- ZIP `t1/MT/bweb_1t_MT_051020261403.zip`, SHA-256
  `610eda446fb6bab25f29ceea31adf8f91acf68db14a179228516d11c0fac226f`;
- membro `bweb_1t_MT_051020261403.csv`, ordinal `0`;
- geração `05/10/2026 14:03:43`, pleito `3220`, turno `1`, UF `MT`;
- `DT_PLEITO` `2026-10-04 00:00:00`, `CD_TIPO_ELEICAO` `0`,
  `NM_TIPO_ELEICAO` `Eleição Ordinária`, `CD_TIPO_URNA` `1`,
  `DS_TIPO_URNA` `Apurada`.

O snapshot não é uma declaração de completude do universo eleitoral.

## Entradas

1. **CSV canônico** (`--input arquivo.csv`): verifica tamanho, SHA-256 e
   contagem de registros contra o perfil. Não há como verificar o ZIP/membro
   de origem nesse modo; a view é preferida para proveniência completa.
2. **Diretório de view da Etapa 4** (`--input diretorio/` com `view.json`):
   valida o descritor estrito (`bweb_storage_view`, versão 1,
   `exact-csv-member-bytes`, `kind=csv-codec`), o hash/tamanho do payload e a
   proveniência (ZIP, membro e ordinal), decodifica em streaming e confere
   bytes, SHA-256 e registros do CSV restaurado. O SHA-256 do próprio
   `view.json` também é registrado. A view real usada na execução está em
   `relatorios-locais/etapa-4-completa/rematerialized-bweb/` (descritor
   `fdaf0b976eeba3d1af39146f180d24daf709dd132173c05f08896603c3a098c4`).

O CSV é lido como Latin-1, separador `;`, aspas duplas, CRLF, 45 campos na
ordem canônica de `spec/bweb.canonical-v1.md`. Identificadores são mantidos
como texto; zeros à esquerda não são removidos e códigos não são convertidos
em números. Nenhum registro é reescrito ou deduplicado.

## Chaves

**Ocorrência** (10 campos):
`ANO_ELEICAO`, `CD_PLEITO`, `CD_ELEICAO`, `NR_TURNO`, `SG_UF`,
`CD_MUNICIPIO`, `NR_ZONA`, `NR_SECAO`, `CD_CARGO_PERGUNTA`, `NR_VOTAVEL`.

**Contexto** (9 campos, sem `NR_VOTAVEL`): os mesmos campos acima.

**Igualdade de contexto** (20 campos, verificada entre linhas do mesmo
contexto): `DT_BU_RECEBIDO`, `QT_APTOS`, `QT_COMPARECIMENTO`,
`QT_ABSTENCOES`, `CD_TIPO_URNA`, `DS_TIPO_URNA`, `NR_LOCAL_VOTACAO`,
`NR_URNA_EFETIVADA`, `CD_CARGA_1_URNA_EFETIVADA`,
`CD_CARGA_2_URNA_EFETIVADA`, `CD_FLASHCARD_URNA_EFETIVADA`,
`DT_CARGA_URNA_EFETIVADA`, `DS_CARGO_PERGUNTA_SECAO`,
`DS_SECOES_AGREGADAS`, `DT_ABERTURA`, `DT_ENCERRAMENTO`,
`QT_ELEI_BIOM_SEM_HABILITACAO`, `DT_EMISSAO_BU`, `NR_JUNTA_APURADORA`,
`NR_TURMA_APURADORA`.

A chave de ocorrência é a candidata do contrato canônico v1. O ordinal de
registro usado em evidências é 1-based e exclui o cabeçalho; um registro CSV
pode ocupar mais de uma linha física, então ordinal de registro e linha física
são localizadores distintos.

Duplicatas nunca são removidas. Chave repetida é classificada como
`repeated_occurrence` (todos os 45 campos idênticos) ou `conflict` (mesma
chave, conteúdo divergente), com ordinal e primeira ocorrência. Qualquer
duplicata reprova o controle obrigatório e bloqueia votos/contexto.

## Controles e falhas

Controles obrigatórios:

- cabeçalho canônico e fingerprint SHA-256 do array de 45 nomes;
- tamanho, SHA-256 e contagem de registros da fonte;
- escopo/snapshot e igualdade dos campos de contexto entre registros;
- inteiros (`QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES`, `QT_VOTOS`,
  `QT_ELEI_BIOM_SEM_HABILITACAO`) com detecção de overflow;
- `QT_APTOS = QT_COMPARECIMENTO + QT_ABSTENCOES` em cada linha;
- chave de ocorrência (sem duplicatas);
- igualdade dos 20 campos de contexto por seção/cargo;
- coerência eleição/cargo (`6257`↔`1`; `6259`↔cargos `3/5/6/7`) e
  código/descrição de eleição, cargo, urna e categoria confirmada;
- padrões lexicais de datas, inteiros, cargas e flashcard usados no contrato.

Sentinelas `{#NULO, #NULO#, #NE, #NE#, -1, -3, ""}` são contadas por coluna e
preservadas. Categoria `CD_TIPO_VOTAVEL` fora de `1..4` é não confirmada:
entra nos totais, na cobertura e nos resultados com status `unconfirmed`, mas
bloqueia a interpretação das categorias. Código conhecido com descrição
incompatível é falha obrigatória.

Aprovação vs usos: `approved=true` significa que os 14 controles obrigatórios
passaram; `category_domain` é não obrigatório por desenho. Usos
`votes_by_category`/`category_shares` ficam `blocked` quando há categoria não
confirmada, mesmo com `approved=true`. Consumidor deve ler `quality.uses`,
não apenas `approved`. Conflito de `NM_MUNICIPIO` para o mesmo
`CD_MUNICIPIO` conta `municipality_name_conflicts`, preserva o primeiro nome
e bloqueia `territorial_coverage_observed`.

Limites centrais (`scripts/limits.env`) aplicados também na análise:
`MAX_CSV_RECORDS`, `MAX_FIELD_BYTES`, `MAX_RECORD_BYTES`,
`MAX_BWEB_OCCURRENCE_KEYS`, `MAX_ANALYZE_EVIDENCE`,
`MAX_ANALYZE_DISTINCT_VALUES`. Excesso falha explicitamente com exit ≠ 0,
sem truncamento silencioso.

Padrões lexicais verificam formato e faixas básicas (dia 01-31, mês 01-12,
hora 00-23, minuto/segundo 00-59, ano 1900-2100; cargas sem `..` nem ponto
nas bordas). Validação semântica completa de calendário não é executada.

Erro obrigatório grava `quality.json`/`REPORT.md` com `approved=false` e o
comando retorna exit diferente de zero. Um relatório parcial nunca é
publicado como execução aprovada. A saída precisa ser um diretório novo,
escrito via diretório temporário e publicado por rename atômico; falha de
infraestrutura grava apenas `run.json` com o mesmo schema (com `error`,
`parameters`, `outputs={}` e `peak_rss_kib`).

## `DS_SECOES_AGREGADAS`

O valor original é preservado por grupo de contexto e o histograma é
registrado até `MAX_ANALYZE_DISTINCT_VALUES` (excesso conta
`values_overflow`, com totais preservados). Esta versão **não interpreta a
lista** (formato observado com valores como `38` ou `49 / 173`). Quando há
valor não sentinela, a contagem de seções físicas e a cobertura territorial
que dependam dessa lista ficam bloqueadas; a contagem de grupos de contexto
continua disponível como observação do arquivo.

## Agregações

- **Votos:** somas de `QT_VOTOS` por cargo, por cargo/categoria e por
  cargo/município/categoria. O total de votos de todos os cargos é uma soma de
  votos, não de eleitores. Participação de categoria usa como denominador os
  votos totais do mesmo cargo/município.
- **Contexto:** um contexto é extraído uma vez por grupo seção/cargo, depois de
  verificada a igualdade dos 20 campos. Aptos, comparecimento e abstenções são
  somados por cargo e por cargo/município e por cargo/município/zona. Contextos
  de cargos diferentes **não** são somados. Total geral de eleitores exige
  população de referência validada e não é produzido.
- **Taxas:** `numerador/denominador` com 6 casas decimais e arredondamento meio
  para cima. Denominador zero produz `null` e motivo `denominator_zero`; nenhuma
  taxa artificial é criada. Comparecimento/aptos e abstenção/aptos são
  calculados por cargo/município e por cargo/zona; os numeradores e
  denominadores permanecem nas linhas.
- **Cobertura:** conta o que foi observado no arquivo (municípios por código
  TSE, zonas, grupos de contexto, categorias, partidos). Não é declaração de
  completude do universo eleitoral e não converte `CD_MUNICIPIO` para IBGE.

## Saídas

`results.json`: definições, votos e contexto com status por uso.
`quality.json`: controles, erros, sentinelas, valores inesperados (com
contador de overflow da retenção de evidências), chaves, contexto,
`DS_SECOES_AGREGADAS`, cobertura e usos.
CSVs: `votes_by_office.csv`, `votes_by_office_municipality.csv`,
`context_by_office.csv`, `context_by_office_municipality.csv`,
`context_by_office_zone.csv`.
`REPORT.md`: resumo legível.
`run.json`: recibo com fonte, hashes, membro/ordinal, snapshot, perfil, versão
do contrato, versão do código, parâmetros, tempos, RSS e hashes das saídas.
Tempos, caminhos e RSS são metadados variáveis; `results.json` e
`quality.json` são determinísticos.

Status por uso: `approved`, `blocked` ou `not_executed`. Usos fora desta etapa
(comparação entre turnos, reconciliação BU×votação×RDV, completude do universo,
modelos/anomalias e interface) permanecem `not_executed` ou bloqueados.

## Validador canônico e escala

`scripts/validate_bweb.py` permanece verificação externa separada; a
concordância com `tsepack analyze` é verificada por `scripts/analyze_check.py`
(Q1/Q2) e por reexecução de `tsepack queries`. Escala nacional não é alegada:
`MAX_BWEB_OCCURRENCE_KEYS=2000000` comporta MT t1 (891.997 chaves) e reprova
explicitamente acima do teto; `analyze_check.py` é verificação não otimizada
para produção.

## Fora do escopo

Esta versão não compara turnos, não reconcilia fontes, não interpreta
`DS_SECOES_AGREGADAS`, não declara fraude/autenticidade, não usa ML e não
publica dados. O segundo turno do acervo local é parcial e não é analisado.
