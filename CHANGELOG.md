# Changelog

## Não lançado — Etapa 5A (MT 2026 t1)

- `tsepack analyze` com contrato analítico v1 e perfil `mt-2026-t1-bweb-v1`:
  validação de fonte/view, snapshot, hash, escopo, inteiros/overflow,
  aritmética de contexto, chaves, duplicatas, contexto e categorias.
- Análise descritiva de votos e contexto em JSON/CSV/Markdown, sem somar
  contextos de cargos diferentes e sem deduplicar ocorrências.
- Verificador independente `scripts/analyze_check.py`, fixtures sintéticas e
  documentação em `docs/ETAPA-5A.md` e `spec/analyze-v1.md`.
- Revisão: `MAX_CSV_RECORDS`/`MAX_FIELD_BYTES` aplicados no Rust, saída
  atômica via `Stage`, `run.json` de falha com mesmo schema, verificação
  `mismatch` para view fora do perfil, faixas de data/hora, teto em
  `DS_SECOES_AGREGADAS` (`values_overflow`), conflito de `NM_MUNICIPIO`
  bloqueia cobertura territorial, registro de perfis e determinismo de
  CSVs/`REPORT.md` testado.

## v0.2.0 — 28/10/2026

- Compressão em streaming com ZSTD, XZ e Brotli, round-trip obrigatório,
  dicionários treinados e saídas publicadas somente após validação.
- Arquivo FORENSIC local v2, sólido ou por fonte, com manifesto e recibo de
  execução vinculados por SHA-256; `optimize`, `archive` e `restore` funcionais.
- Pacote BU web reversível v2, verificador independente e consultas Q1/Q2 de
  controle, preservando valores lexicais, ordem, duplicatas e zeros significativos.
- Experimento completo no acervo local de MT com comparação de Parquet,
  dicionários, blocos e agrupamentos, incluindo custo de metadados/proveniência.
  Bundle mínimo e cache de consulta regenerável; resultados em
  [RESULTADO-COMPRESSAO-MT.md](docs/RESULTADO-COMPRESSAO-MT.md).
- Aquisição retomável, validação de caminhos/versões/inventário e rejeição
  explícita de corrupção, truncamento, campos desconhecidos e vínculos divergentes.

Compatibilidade de dados: origem lê v1/v2 e escreve v2; BU web lê v1 com
compromisso SHA-256 e v2, escreve v2; arquivo FORENSIC lê v1 sólido/v2 e
escreve v2. Relatórios de benchmark usam v2, views usam v1. Esses números
evoluem independentemente da versão do software.

O binário de software não inclui os dados de MT. Publicação de datasets,
expansão nacional e liberação de modelos analíticos permanecem em suas etapas
específicas. Resultados experimentais preservam a versão com que foram produzidos.
