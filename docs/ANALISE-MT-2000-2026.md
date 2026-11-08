# Análise MT 2000-2026 — descritiva e inconsistências observadas

Metodologia em `scripts/analyze_mt_historico.py` (stdlib, streaming Latin-1,
`;`), testes em `scripts/test_analyze_mt_historico.py`. Sem deduplicação, sem
conversão de identificadores, sem soma de eleitores entre cargos. Nenhuma
conclusão de fraude/autenticidade; flags exigem confronto com fonte e
documentação oficial.

## Corpus ingerido (MT, dadosabertos.tse.jus.br)

- Inventário: `scripts/inventory_mt_2000_2026.json` (157 recursos, 89 arquivos
  de dados + sidecars).
- Destino: `/data/urnapack/brutos/<ano>/MT/` (+ legado `2026/t1/MT/`), com
  retomada e SHA-256 local; sidecar oficial preservado quando publicado
  (`.sha512` 2016-2026, `.sha1` 2012-2014, ausente em votação/relatórios).
- Volume: ~5,6 GB. Recibo local: `relatorios-locais/fetch-mt-historico.json`.
- Relatório local (não versionado): `relatorios-locais/mt-historico/analysis.json`
  (125 membros) + `REPORT.md`.

## Layouts observados (não presumir MT-2026)

- BU web: `.txt` 31-32 cols sem cabeçalho (2012-2016, preservados sem
  agregação); 42 cols com cabeçalho (2018, ex.: `SG_ UF` com espaço,
  `CD_FLASCARD`, `DS_AGREGADAS`); 45 cols canônicas (2020-2026).
- Votação por seção: 23 cols (2000-2006, 2010-2014); 26 cols com
  `SQ_CANDIDATO`/`NM_LOCAL`/`DS_ENDERECO` (2008, 2016-2026).
- CESP/CEFT: cabeçalhos e ordem variam por ano (ex.: `NR_LOCAL_VOTACAO`
  deslocada em 2024, `DT_RECO_*` vs `DT_RECBTO_*`, `DS_DIVERGENCIA` vs
  `TP_DIVERGENCIA`); `cmrj` com 0 registros em 2020-2022.
- `map_raw_data.py` reprova variantes desconhecidas explicitamente, sem
  eliminar dados.

## Controles por arquivo (onde aplicável)

- Aritmética `aptos=comp+abst` (bweb): 0 falhas em todos os bweb 45/42 cols
  lidos (2018, 2022, 2024, 2026 t1/t2; 2020 t2).
- Chave de ocorrência e igualdade de contexto (bweb/votação): 0 duplicatas,
  0 divergências em bweb e votação (CESP/CEFT fora do escopo dessas chaves).
- `bweb_1t_MT_181120201545.zip#bweb_1t_MT_181120201549.csv` (2020 t1, 322 MB):
  erro de quoting `';' expected after '"'` após 59.082 registros — bytes
  preservados, membro excluído da agregação, votação 2020 t1 (593.064 regs)
  cobre o pleito.

## BU × votação (soma QT_VOTOS por eleição/turno/cargo)

Unidade comparável exige `CD_ELEICAO`: o mesmo arquivo pode misturar pleitos
(ex.: votação 2018 contém 297 regular + 438 suplementar com `DT_ELEICAO`
15/11/2020). Agregação por cargo/turno sem eleição mistura universos.

| ano-arquivo | eleição | turno | cargo | BU | votação | estado |
|---|---|---|---|---|---|---|
| 2018 | 297 regular | 1 | 3 | 1.757.368 | 1.757.368 | OK |
| 2018 | 297 regular | 1 | **5 (Senador)** | **3.514.736** | **3.514.736** | **OK (0 divergentes em 7.247 seções)** |
| 2018 | 297 regular | 1 | 6 | 1.757.368 | 1.757.368 | OK |
| 2018 | 297 regular | 1 | 7 | 1.757.368 | 1.757.368 | OK |
| 2018 | 438 suplementar | 1 | 5 | bloqueada (quoting 2020) | 1.725.489 (6.624 grupos) | observação, reconciliação pendente |
| 2022 | 1 | 3/5/6/7 | 1.889.012 cada | iguais | OK |
| 2024 | 1 | 11/13 | 1.958.974 cada | iguais | OK |
| 2024 | 2 | 11 | 330.537 | 330.537 | OK |
| 2020 | 2 | 11 | 284.352 | 284.352 | OK |
| 2026 | 1 | 3/6/7 | 2.049.718 cada | iguais | OK |
| 2026 | 1 | 5 | 4.099.436 | 4.099.436 | OK (2×) |

Proveniência (SHA-256 dos ZIPs): `BWEB_1t_MT_101020181938.zip`
`9d45919df869dc69…` (950.130 regs), `votacao_secao_2018_MT.zip`
`16342cf83dec151b…` (954.912 regs). Reconciliação por seção/eleição em
`scripts/reconcile_senado_2018.py` → `reconcile-senado-2018.json`:
regular 297 com 0 divergentes; suplementar 438 com BU bloqueada.
RDV 2018 não publicado no portal (só arqurnatot 2022+); sem RDV não há
BU×votação×RDV fechada. Não autoriza alegação de fraude.

Inspeção 2020 t1 (`scripts/inspect_2020_bweb_quoting.py`): ZIP
`7c3cec2892a17e934be011e94b29d077…` (13.671.904 bytes), membro
`bweb_1t_MT_181120201549.csv` (322.652.918 bytes,
`c29b677fd3df1e67…`), offset 28.205.815, linha física 59.084 / registro
59.083, `NM_VOTAVEL="ELIEL ROCHA " O GORDINHO""` (aspa não escapada).
Parser estrito reprova após 59.082 íntegros; bytes preservados.

Baseline comparecimento (`scripts/model_baseline_mt.py`, 2026 t1 cargo 1
Presidente, 8.287 grupos, `p_hat=0,777971` igual à Etapa 5A): binomial H0 +
BH q=0,05 flagra 1.667 grupos (20%) — sobre-dispersão esperada entre seções,
não anomalia; calibração nula 0 flags e falsificação 10/10 OK
(`model-comparecimento-2026t1.json`). Modelo mais rico (beta-binomial por
município/zona) só com ganho demonstrado.

## Série votação por seção (QT_VOTOS por ano/turno/cargo)

| ano | t | cargos (votos) |
|---|---|---|
| 2000 | 1 | 11:1.086.169, 13:1.085.865 |
| 2002 | 1 | 3:1.346.646, 5:2.693.292 (2×), 6:1.346.620, 7:1.346.620 |
| 2004 | 1 | 11:763.689, 13:763.696 |
| 2006 | 1 | 3/5/6/7:1.549.616 cada |
| 2008 | 1 | 11:1.717.922, 13:1.671.591; 2: 11:298.478 |
| 2010 | 1 | 3:1.655.212, 5:3.310.424 (2×), 6:1.655.212, 7:1.655.212 |
| 2012 | 1 | 11:1.776.507, 13:1.776.507; 2: 11:322.918 |
| 2014 | 1 | 3/5/6/7:1.686.876 cada |
| 2016 | 1 | 11:1.858.123, 13:1.801.054; 2: 11:310.863 |
| 2018 | 1 | 3:1.757.368, 5:5.240.225, 6:1.757.368, 7:1.757.368 |
| 2020 | 1 | 11:1.743.729, 13:1.727.620; 2: 11:284.352 |
| 2022 | 1 | 3/5/6/7:1.889.012 cada |
| 2024 | 1 | 11:1.958.974, 13:1.958.974; 2: 11:330.537 |
| 2026 | 1 | 3:2.049.718, 5:4.099.436 (2×), 6:2.049.718, 7:2.049.718 |

Senador 2× (2002, 2010, 2018-BU, 2026) reflete 2 vagas; 2018-votação destoa
(≈2,98×) — ver divergência acima. Municipais t2 restritos a 1 município
(2020 t2, 2024 t2: só capital) — cobertura observada, não completude.

## Limites e próximos passos

- `votos=2×comp` por grupo em Senado 2 vagas é regra, não erro.
- 2020 t1 BU com erro de quoting exige inspeção byte a byte do trecho
  (≈registro 59.083) antes de qualquer reparse; não corrigir bytes originais.
- CESP `ccont`/`cmrj` têm duplicatas aparentes pela granularidade (sem
  `NR_SECAO`); análise atual só aplica chaves a bweb/votação.
- Seguir PLANO-ANALISE A1-A4 antes de modelos; calibrar baseline e
  falsificação antes de interpretar qualquer achado.
