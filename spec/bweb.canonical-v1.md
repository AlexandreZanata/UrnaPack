# BU web — esquema canônico v1 (documental, Etapa 2)

Escopo validado: **MT, eleição 2026, turno 1, geração `bweb_1t_MT_051020261403`**.
Outros anos, UFs, turnos ou gerações exigem extensão versionada deste esquema
(`bweb.canonical-v2`, ...). Nenhuma hipótese aqui autoriza deduplicação:
divergência reprova com evidência; unicidade nacional **não** está provada.

Cabeçalho canônico (45 colunas, ordem exata; fingerprint SHA-256 do JSON UTF-8
do array, `ensure_ascii=False`, separadores `(',', ':')`):
`c93ec8fe8f0ad3403b583e77ea166ac7c9db29246f79a0fdd27dfa30e48372c8`.
O validador executável (`scripts/validate_bweb.py`) compara o cabeçalho lido
com esta lista; variante reprova sem eliminar campos.

```text
DT_GERACAO, HH_GERACAO, ANO_ELEICAO, CD_TIPO_ELEICAO, NM_TIPO_ELEICAO,
CD_PLEITO, DT_PLEITO, NR_TURNO, CD_ELEICAO, DS_ELEICAO, SG_UF, CD_MUNICIPIO,
NM_MUNICIPIO, NR_ZONA, NR_SECAO, NR_LOCAL_VOTACAO, CD_CARGO_PERGUNTA,
DS_CARGO_PERGUNTA, NR_PARTIDO, SG_PARTIDO, NM_PARTIDO, DT_BU_RECEBIDO,
QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCOES, CD_TIPO_URNA, DS_TIPO_URNA,
CD_TIPO_VOTAVEL, DS_TIPO_VOTAVEL, NR_VOTAVEL, NM_VOTAVEL, QT_VOTOS,
NR_URNA_EFETIVADA, CD_CARGA_1_URNA_EFETIVADA, CD_CARGA_2_URNA_EFETIVADA,
CD_FLASHCARD_URNA_EFETIVADA, DT_CARGA_URNA_EFETIVADA,
DS_CARGO_PERGUNTA_SECAO, DS_SECOES_AGREGADAS, DT_ABERTURA, DT_ENCERRAMENTO,
QT_ELEI_BIOM_SEM_HABILITACAO, DT_EMISSAO_BU, NR_JUNTA_APURADORA,
NR_TURMA_APURADORA
```

## Tipos lexicais (nível 1 — estrutural, sem cast)

Toda coluna é texto Latin-1 preservado. Padrões verificados por linha:

| Colunas | Padrão |
|---|---|
| `ANO_ELEICAO` | `^\d{4}$` |
| `DT_GERACAO` | `^\d{2}/\d{2}/\d{4}$` (hipótese de formato a formalizar fuso) |
| `HH_GERACAO` | `^\d{2}:\d{2}:\d{2}$` |
| `DT_PLEITO`, `DT_BU_RECEBIDO`, `DT_CARGA_URNA_EFETIVADA`, `DT_ABERTURA`, `DT_ENCERRAMENTO`, `DT_EMISSAO_BU` | `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$` |
| `QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES`, `QT_VOTOS`, `QT_ELEI_BIOM_SEM_HABILITACAO` | `^\d+$` |
| `NR_ZONA`, `NR_SECAO`, `NR_LOCAL_VOTACAO`, `NR_VOTAVEL`, `NR_URNA_EFETIVADA`, `NR_JUNTA_APURADORA`, `NR_TURMA_APURADORA`, `CD_MUNICIPIO`, `NR_PARTIDO` | `^-?\d+$` (`-1` ocorre como sentinela, não como contagem) |
| `CD_CARGA_1_URNA_EFETIVADA`, `CD_CARGA_2_URNA_EFETIVADA` | `^[\d.]+$` (dígitos com pontos; semântica pendente) |
| `CD_FLASHCARD_URNA_EFETIVADA` | `^[0-9A-Fa-f]+$` |
| Demais (`NM_*`, `DS_*`, `SG_*`, códigos) | texto livre preservado |

## Domínios MT-2026 (nível 2 — valores observados, extensíveis por versão)

| Coluna | Domínio observado | Nota |
|---|---|---|
| `DT_GERACAO` / `HH_GERACAO` / `DT_PLEITO` | `05/10/2026` / `14:03:43` / `2026-10-04 00:00:00` | arquivo de geração única |
| `ANO_ELEICAO` | `2026` | |
| `CD_TIPO_ELEICAO` / `NM_TIPO_ELEICAO` | `0` / `Eleição Ordinária` | difere da votação (`2`); por fonte |
| `CD_PLEITO` | `3220` | |
| `NR_TURNO` | `1` | perfil restrito a t1; t2 exige outra versão |
| `CD_ELEICAO` / `DS_ELEICAO` | `6257`↔`Eleição Geral Federal 2026`, `6259`↔`Eleições Gerais Estaduais 2026` | consistência cruzada verificada |
| `SG_UF` | `MT` | |
| `CD_CARGO_PERGUNTA` / `DS_CARGO_PERGUNTA` | `1`↔Presidente, `3`↔Governador, `5`↔Senador, `6`↔Deputado Federal, `7`↔Deputado Estadual | consistência cruzada verificada |
| `CD_TIPO_URNA` / `DS_TIPO_URNA` | `1`↔`Apurada` | |
| `CD_TIPO_VOTAVEL` / `DS_TIPO_VOTAVEL` | `1`↔Nominal, `2`↔Branco, `3`↔Nulo, `4`↔Legenda | categorias oficiais; consistência cruzada verificada |

Eleição `6257` exige cargo `1`; eleição `6259` rejeita cargo `1`.
As datas têm validação lexical, sem promessa de calendário ou fuso.
Valor fora dos dois níveis reprova com ordinal e coluna (sem normalizar nem
descartar). Sentinelas lexicais `{#NULO, #NULO#, #NE, #NE#, -1, -3, ""}` são contadas
por coluna como evidência; `DS_SECOES_AGREGADAS` é lista textual opaca nesta etapa.
O relatório registra `complete` e só inclui `source_sha256` após leitura até
EOF. Evidências têm teto, contagens totais de erros permanecem explícitas.

## Chaves candidatas (não verificadas globalmente)

- **Ocorrência** (unidade da linha): `CD_PLEITO, NR_TURNO, SG_UF, CD_MUNICIPIO,
  NR_ZONA, NR_SECAO, CD_CARGO_PERGUNTA, NR_VOTAVEL`. Em MT 2026 t1: 891.997
  registros, 891.997 chaves distintas, 0 duplicatas (verificado por leitura
  integral — evidência local, não prova nacional).
- **Contexto** (medidas compartilhadas): `QT_APTOS, QT_COMPARECIMENTO,
  QT_ABSTENCOES` + urna/carga/horários por seção/cargo. Igualdade do contexto
  entre linhas do mesmo grupo é verificação da Etapa 5, não assumida aqui.
- Regra aritmética verificada em MT (891.997/891.997):
  `QT_ABSTENCOES = QT_APTOS − QT_COMPARECIMENTO` e `QT_COMPARECIMENTO ≤ QT_APTOS`.
  Divergência reprova com ordinal.

## Regras de agregação (para a Etapa 5, sem executar aqui)

- `QT_VOTOS` soma por votável/grupo declarado; nunca somar `QT_APTOS` ou
  `QT_COMPARECIMENTO` por linha de votável (medidas de contexto repetidas).
- `DS_SECOES_AGREGADAS` não autoriza contagem territorial duplicada.
- Reduções são produtos derivados regeneráveis; não substituem a evidência.

## Consultas representativas planejadas (guia da representação física futura)

- Q1: votos por cargo/UE (`CD_CARGO_PERGUNTA`, `SG_UE` equivalente, `QT_VOTOS`).
- Q2: comparecimento por zona/seção (contexto, sem somar por votável).
- Q3: eleitores por local de votação (`NR_LOCAL_VOTACAO`, contexto).
- Q4: confronto BU×votação por seção/cargo (depende da Etapa 3+; hoje só totais).
- Q5: trilha ocorrência→fonte (hash do ZIP + ordinal do membro + ordinal do registro).

Nenhuma escolha física (colunar, índices, dicionários) nesta etapa; medir antes
de afirmar viabilidade em 32 GB na escala nacional.
