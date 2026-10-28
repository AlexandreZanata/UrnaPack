# Formato de distribuição — v1

Contratos para pacotes, manifestos, índice e tags. Implementação de referência
para validação: `scripts/validate.py`. Valores operacionais autoritativos em
`scripts/limits.env`.

## Estado e tipos de manifesto

Este documento descreve o contrato de distribuição v1 já usado pelas fixtures
e validadores, e reservas para distribuição futura. Não há formato `.upk`
implementado nem dataset publicado pela base. O refinamento do plano não altera
campos nem versões dos schemas JSON existentes.

O manifesto de origem produzido por `inspect` é outro contrato: Rust
`Manifest { format_version, tool_version, source, files[] }`, com
`FileEntry { path, size, sha256, file_type, url? }`. O `verify` atual lê esse
contrato. Não passar um manifesto de dataset a ele como prova de equivalência.
Discriminadores, versões próprias, campos desconhecidos e vínculos por hash
serão formalizados na Etapa 2, com versionamento de alterações incompatíveis.

Na origem v1, caminhos são relativos portáveis em UTF-8 com `/`, sem segmentos
vazios, `.`/`..`, NUL, separador invertido ou prefixo de unidade Windows.
O construtor e o verificador aplicam a mesma política. A raiz pode ser um link
resolvido explicitamente; links internos não são aceitos.

## Mapa estrutural local — v1

`scripts/map_raw_data.py` gera `artifact_kind: raw_structure_map` com sua
própria `format_version: 1`, independente dos manifestos de origem/dataset.
Os campos adicionais da revisão são compatíveis: frequências por coluna em
`csv_profiles[].scopes.<coluna>.counts`,
bytes efetivamente lidos de CSV em `member_bytes_read` e finais de linha em
`line_endings`. `params.source` preserva o argumento de origem, como na versão
inicial; caminhos de fontes/membros são relativos e o recibo registra a execução.
Os campos anteriores dos perfis são preservados.

O estado `complete` indica conclusão do mapeamento, sem afirmar completude da
eleição, equivalência semântica ou decodificação dos opacos. `metadata_only`,
`sampled` e `fully_read` distinguem o nível realmente executado; SHA-256 de
membro só é publicado após leitura integral sem erro e tamanho conferido.

`map.json` é o marcador publicado por último; consumidores conferem o hash de
`members.jsonl` nele registrado. Gerações anteriores são preservadas em
`.previous-*`; uma tentativa com erro não deixa mapa completo atual. O recibo
de execução precisa ter sido escrito antes da conclusão. Usar uma única
execução por diretório de saída; concorrência entre escritores não é suportada.

## Pacotes

- Nome determinístico:
  `urnapack-<ano>-t<turno>-<UF>-<tipo>-<seq>.upk.zst`
  ex.: `urnapack-2026-t2-MT-bu-0001.upk.zst`
- Regex: `^urnapack-\d{4}-t[12]-[A-Z]{2}-[a-z]+-\d{4}\.upk\.zst$`
- Tipos (`dataset_type`): `bu`, `rdv`, `logs`, `resultados`, `metadata`.
- Cada pacote deve permitir download e confronto de seu hash isoladamente.
  Isso não define ainda independência de decodificação de dicionários/outros pacotes.
- A sequência `seq` é zero-padded e ordena o catálogo. Não usar concatenação
  como algoritmo de restauração sem contrato do codec e do objeto reconstruído.
- Antes da primeira distribuição, especificar unidade de decodificação,
  completude/ordem e dependências, além do hash do objeto restaurado/conjunto.
  O schema atual não contém esse contrato completo: evoluí-lo com versão e
  testes antes de publicar um formato que dependa dele.
- `.upk` (formato binário próprio) ainda NÃO existe; o sufixo reserva o contrato.

## Manifesto de dataset

JSON versionado (`spec/manifest.schema.json`), um por
(ano, turno, UF, tipo, versão). Campos:

| Campo | Significado |
|---|---|
| `format_version` | Versão do esquema (atual: 1) |
| `election_year`, `round`, `state`, `dataset_type` | Identificação |
| `transform_version`, `tool_version` | O que gerou os pacotes |
| `source_files[]` | `{path, sha256, size_bytes, url}` dos oficiais |
| `source_urls[]` | URLs oficiais (mesma ordem ou espelho de `source_files`) |
| `packages[]` | `{name, sha256, size_bytes, records}` dos derivados |
| `package_hashes[]` | Espelho dos SHA-256 de `packages` (mesma ordem) |
| `record_counts` | Total de registros eleitorais (nunca fundir duplicatas legítimas) |
| `verification_profile` | `forensic` \| `analytical` |
| `verification_status` | `prepared` \| `validated` \| `published` \| `failed` |

Regras: hashes sempre SHA-256 dos bytes reais; publicação exige
`verification_status: validated`; hash próprio ≠ assinatura do TSE.
Invariante: `record_counts` = soma de `packages[].records`.
Essa igualdade entre declarações não verifica contagem de conteúdo. A liberação
exige leitura dos dados, multiplicidades reconciliadas e evidências do perfil.

`forensic` restaura os bytes do objeto original declarado; ZIP e membros são
objetos diferentes. `analytical` exige equivalência documentada do canônico;
reduções são produtos derivados regeneráveis a partir da evidência preservada.
Todos os bytes necessários à garantia entram na medição de armazenamento.

## Índice público (`data/index.json`, schema em `spec/index.schema.json`)

Entradas por (ano, turno, UF, tipo, versão): release, URLs dos assets,
manifesto + hashes, tamanhos, estado e data. Só aponta para publicados
e verificados.

## Tags

- Software: `vX.Y.Z` (ex.: `v0.1.0`).
- Datasets: `data-<ano>-t<turno>-<UF>-<versão>` (ex.: `data-2026-t2-MT-v1`).
  `BR` = índice/conjunto nacional real, nunca arquivo parcial como completo.
- Nunca sobrescrever tag publicada; nova versão = nova tag.

## Contrato futuro da CLI

Quando existirem pacotes, a CLI oferecerá (sem redesenhar o índice):

```bash
tsepack datasets list
tsepack datasets info 2026 2 MT
tsepack datasets download 2026 2 MT
tsepack datasets verify 2026 2 MT
```

Semântica de `verify`: (1) integridade do pacote contra o manifesto;
(2) correspondência com o TSE via reexecução da transformação — ver
`docs/VERIFICACAO.md`. Pacote com hash correto ≠ prova de correspondência.
