# Etapa 5A — validação analítica e análise descritiva do BU web de MT

**Execução:** 28/10/2026, branch `codex/etapa-5a-analise-mt`.
**Escopo:** MT, eleição 2026, turno 1, BU web, snapshot
`bweb_1t_MT_051020261403`. Não é uma declaração de cobertura nacional nem de
conclusão da Etapa 5.

## O que foi implementado

- `tsepack analyze` com contrato analítico `v1`, perfil
  `mt-2026-t1-bweb-v1` e entrada CSV ou view da Etapa 4
  ([spec/analyze-v1.md](../spec/analyze-v1.md)).
- Leitura em streaming dos 45 campos, sem cast de identificadores e sem
  deduplicação. Verificação de cabeçalho, fingerprint, snapshot, hash,
  tamanho, contagem, inteiros/overflow, aritmética de contexto, sentinelas,
  chaves, igualdade de contexto, eleição/cargo, categorias e padrões
  lexicais.
- Agregações: votos por cargo, cargo/categoria e cargo/município/categoria;
  contexto (aptos, comparecimento, abstenções) por cargo, cargo/município e
  cargo/município/zona, contado uma vez por grupo seção/cargo. Nenhum total de
  eleitores entre cargos é produzido.
- Saídas determinísticas: `results.json`, `quality.json`, cinco CSVs,
  `REPORT.md` e `run.json` com proveniência (incluindo SHA-256 da view),
  versões, parâmetros, recursos e hashes das saídas.
- Verificador independente `scripts/analyze_check.py`, que recalcula os
  agregados e Q1/Q2 com a stdlib e não chama funções Rust, com testes próprios
  em `scripts/test_analyze_check.py`.

## Fonte e integridade conferidas

| item | valor |
|---|---|
| View | `relatorios-locais/etapa-4-completa/rematerialized-bweb` |
| SHA-256 do `view.json` | `fdaf0b976eeba3d1af39146f180d24daf709dd132173c05f08896603c3a098c4` |
| SHA-256 do payload | `8b9ea36b2ce732f63295422b6e4362c2984f713953ed9192626ba3b28c503904` |
| CSV restaurado | 411.757.026 bytes |
| SHA-256 do CSV | `5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3` |
| ZIP de origem | `t1/MT/bweb_1t_MT_051020261403.zip` |
| SHA-256 do ZIP | `610eda446fb6bab25f29ceea31adf8f91acf68db14a179228516d11c0fac226f` |
| Membro / ordinal | `bweb_1t_MT_051020261403.csv` / `0` |
| Snapshot | `05/10/2026 14:03:43`, pleito `3220`, turno `1`, UF `MT` |

O CSV foi restaurado da view com a rotina documentada
`scripts/compression_stage.py restore-view` e conferido por SHA-256 contra o
descritor. O pacote final da Etapa 4, os dados brutos e os formatos de
compressão não foram alterados.

## Comandos executados

```bash
# restauração do CSV a partir do cache da Etapa 4
python3 scripts/compression_stage.py restore-view \
  --binary target/release/tsepack \
  --input relatorios-locais/etapa-4-completa/rematerialized-bweb/view.json \
  --output relatorios-locais/etapa-5a/mt/inputs/bweb_1t_MT_051020261403.csv

# análise real (duas execuções independentes)
./target/release/tsepack analyze \
  --input relatorios-locais/etapa-4-completa/rematerialized-bweb \
  --output relatorios-locais/etapa-5a/mt/run-1
./target/release/tsepack analyze \
  --input relatorios-locais/etapa-4-completa/rematerialized-bweb \
  --output relatorios-locais/etapa-5a/mt/run-2

# reconferência independente
python3 scripts/analyze_check.py \
  --csv relatorios-locais/etapa-5a/mt/inputs/bweb_1t_MT_051020261403.csv \
  --results relatorios-locais/etapa-5a/mt/run-1/results.json \
  --quality relatorios-locais/etapa-5a/mt/run-1/quality.json \
  --reference relatorios-locais/etapa-4-completa/queries/reference.json \
  --expected-sha256 5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3 \
  --output relatorios-locais/etapa-5a/mt/run-1/independent-check.json

# validador canônico existente
python3 scripts/validate_bweb.py \
  --csv relatorios-locais/etapa-5a/mt/inputs/bweb_1t_MT_051020261403.csv \
  --output relatorios-locais/etapa-5a/mt/run-1/canonical-validation.json

# reexecução das consultas existentes
./target/release/tsepack queries \
  --input relatorios-locais/etapa-5a/mt/inputs/bweb_1t_MT_051020261403.csv \
  --output relatorios-locais/etapa-5a/mt/run-1/queries-reexecuted.json
```

## Controles

Todos os 14 controles obrigatórios passaram; `category_domain` (não
obrigatório) também passou. Não houve erro de leitura, hash, escopo,
aritmética, chave, contexto, eleição/cargo ou categoria.

| controle | resultado |
|---|---|
| cabeçalho + fingerprint | 45 campos, `c93ec8fe…` |
| fonte | 411.757.026 bytes, SHA-256 e 891.997 registros conferidos |
| escopo/snapshot | 2026, pleito 3220, turno 1, MT; geração aceita |
| inteiros/overflow | 891.997 linhas válidas |
| `aptos = comparecimento + abstenções` | 891.997/891.997 |
| chave de ocorrência | 891.997 distintas, 0 duplicatas |
| igualdade de contexto | 41.435 grupos, 0 divergências |
| eleição/cargo | 6257↔1 e 6259↔3/5/6/7 |
| categorias | 1/2/3/4 confirmadas com descrições oficiais |
| sentinelas | contadas e preservadas por coluna |

## Resultados reais

Votos totais (soma de votos de todos os cargos, **não** de eleitores):
**12.300.723**.

| cargo | votos |
|---|---:|
| 1 — Presidente | 2.052.133 |
| 3 — Governador | 2.049.718 |
| 5 — Senador | 4.099.436 |
| 6 — Deputado Federal | 2.049.718 |
| 7 — Deputado Estadual | 2.049.718 |

| categoria | votos | participação no total de votos |
|---|---:|---:|
| Nominal | 11.094.765 | 90,1960% |
| Branco | 509.045 | 4,1383% |
| Nulo | 534.673 | 4,3467% |
| Legenda | 162.240 | 1,3189% |

Contexto por cargo, contado uma vez por grupo seção/cargo:

| cargo | grupos | aptos | comparecimento | abstenções | comp/aptos | abst/aptos |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 8.287 | 2.637.801 | 2.052.133 | 585.668 | 0,777971 | 0,222029 |
| 3 | 8.287 | 2.634.992 | 2.049.718 | 585.274 | 0,777884 | 0,222116 |
| 5 | 8.287 | 2.634.992 | 2.049.718 | 585.274 | 0,777884 | 0,222116 |
| 6 | 8.287 | 2.634.992 | 2.049.718 | 585.274 | 0,777884 | 0,222116 |
| 7 | 8.287 | 2.634.992 | 2.049.718 | 585.274 | 0,777884 | 0,222116 |

Os contextos de cargos diferentes **não** foram somados: os aptos do cargo 1
diferem dos cargos estaduais em 2.809 eleitores. Não há total geral de
eleitores nesta etapa.

Cobertura observada no arquivo: 142 códigos municipais TSE distintos, 147
pares município/zona, 41.435 grupos de contexto, 5 cargos, 2 eleições e 30
partidos. Isso não é uma declaração de completude do universo eleitoral e não
converte `CD_MUNICIPIO` para IBGE.

`DS_SECOES_AGREGADAS`: 401 valores distintos; 2.975 grupos de contexto com
valor não sentinela (830.764 linhas com `#NULO#` no nível de registro). O valor
foi preservado e **não interpretado**. A contagem de seções físicas e a
cobertura territorial dependente da lista ficaram bloqueadas.

## Usos liberados e bloqueados

Liberados: votos por cargo, votos por categoria, participação de categoria,
contexto/comparecimento/abstenções por cargo, município e zona, taxas
correspondentes e cobertura observada.

Bloqueados: contagem de seções físicas (`DS_SECOES_AGREGADAS`) e total de
eleitores entre cargos (falta população de referência validada).

Não executados: completude do universo, comparação entre turnos,
reconciliação BU×votação×RDV, modelos/detecção de anomalias e interface web.

## Verificação independente e reprodutibilidade

- `scripts/analyze_check.py`: **17/17** verificações, incluindo Q1 e Q2
  recalculadas de forma independente; as duas consultas coincidem com
  `relatorios-locais/etapa-4-completa/queries/reference.json`.
- `tsepack queries` reexecutado: JSON **byte a byte idêntico** à referência
  (`340045930a2e1ef1…`).
- `scripts/validate_bweb.py`: 891.997 registros, 891.997 chaves distintas, 0
  duplicatas, `success=true`.
- Duas execuções da análise: `results.json`, `quality.json`, CSVs e
  `REPORT.md` idênticos. `run.json` é idêntico excluindo os metadados
  variáveis `started_at_unix_seconds`, `finished_at_unix_seconds`,
  `duration_ms`, `peak_rss_kib`, `input` e `output`. Evidência em
  `relatorios-locais/etapa-5a/mt/reproducibility.json`.

Recursos medidos (uma execução, sem projeção nacional):

| processo | tempo | pico RSS | observação |
|---|---:|---:|---|
| `tsepack analyze` (release) | 5,37 s | 266.244 KiB | streaming; 891.997 registros |
| `scripts/analyze_check.py` | 29,06 s | 654.176 KiB | verificação independente, não otimizada para produção |
| `scripts/validate_bweb.py` | 19,29 s | 417.708 KiB | validador canônico existente |

## Testes executados

```text
cargo fmt --check                              PASS
cargo clippy --all-targets -- -D warnings      PASS
cargo test                                     69 testes, 0 falhas
python3 -m unittest discover -s scripts ...    82 testes, OK
python3 scripts/validate.py repo               114 arquivos verificados
python3 scripts/validate.py self-test          9/9 cenários OK
scripts/validate_bweb.py                       OK (891.997 registros)
scripts/analyze_check.py                       OK (17 verificações)
```

Os novos testes Rust cobrem contexto repetido sem multiplicar eleitores,
contexto divergente, duplicata repetida, conflito, zeros à esquerda,
sentinelas, categoria desconhecida, denominador zero, overflow, hash
divergente, entrada truncada, fora do escopo, view com payload adulterado,
determinismo e exit code. As fixtures são sintéticas e identificadas em
`tests/fixtures/analyze/README.md`, com hashes calculados dos bytes reais.

## Artefatos

Resultados reais (fora do Git):

- `relatorios-locais/etapa-5a/mt/run-1/` — execução principal;
- `relatorios-locais/etapa-5a/mt/run-2/` — segunda execução;
- `relatorios-locais/etapa-5a/mt/reproducibility.json` — comparação;
- `relatorios-locais/etapa-5a/mt/inputs/bweb_1t_MT_051020261403.csv` — cópia
  restaurada e conferida por SHA-256.

Dentro de `run-1/`: `results.json`, `quality.json`, `REPORT.md`, `run.json`,
`votes_by_office.csv`, `votes_by_office_municipality.csv`,
`context_by_office.csv`, `context_by_office_municipality.csv`,
`context_by_office_zone.csv`, `independent-check.json`,
`canonical-validation.json`, `queries-reexecuted.json`, `stdout.log`,
`resource-usage.txt` e os tempos das verificações.

## Limitações e pendências de revisão

- A contagem de 142 códigos municipais TSE é observação do arquivo; a
  equivalência com municípios IBGE não foi estabelecida.
- `DS_SECOES_AGREGADAS` precisa de regra documentada e testada antes de
  liberar contagem de seções físicas ou cobertura territorial dependente.
- O validador canônico foi executado como verificação externa; decidir se
  `tsepack analyze` deve integrá-lo ou manter a separação.
- O snapshot aceito está fixado no perfil; outra geração exige novo perfil
  versionado.
- Categoria desconhecida é não obrigatória por desenho: entra nos totais e
  bloqueia a interpretação das categorias. Revisar se esse é o comportamento
  desejado para outros snapshots.
- `analysis_code_version` é `0.2.0-etapa5a`; a versão do crate não foi
  alterada e não houve release, merge ou push.
- Comparação entre turnos, reconciliação BU×votação×RDV, completude do
  universo, modelos e interface permanecem fora desta entrega.
