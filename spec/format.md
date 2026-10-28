# Formato de distribuição — v1

Contratos para pacotes, manifestos, índice e tags. Implementação de referência
para validação: `scripts/validate.py`. Valores operacionais autoritativos em
`scripts/limits.env`.

## Pacotes

- Nome determinístico:
  `urnapack-<ano>-t<turno>-<UF>-<tipo>-<seq>.upk.zst`
  ex.: `urnapack-2026-t2-MT-bu-0001.upk.zst`
- Regex: `^urnapack-\d{4}-t[12]-[A-Z]{2}-[a-z]+-\d{4}\.upk\.zst$`
- Tipos (`dataset_type`): `bu`, `rdv`, `logs`, `resultados`, `metadata`.
- Pacotes são independentes: cada um baixa e verifica isoladamente.
- Divisão: sequência `seq` zero-padded; reconstrução = concatenação ordenada
  por `seq`, validada pelo SHA-256 de cada parte e do conjunto.
- `.upk` (formato binário próprio) ainda NÃO existe — pacotes atuais usam
  apenas compressão convencional; o sufixo reserva o contrato.

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
