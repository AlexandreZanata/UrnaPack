# UrnaPack — Compressão extrema e verificável dos dados do TSE

> **English brief:** UrnaPack is an open-source Rust toolkit to compress,
> structure and independently verify Brazil's public electronic voting data
> (TSE). It optimizes for maximum storage reduction under non-negotiable
> integrity and verifiability constraints. Independent project — not
> affiliated with or endorsed by the TSE.

Base **v0.1** em Rust. Objetivo: descobrir o limite prático de compressão dos
dados das urnas brasileiras **sem perder auditabilidade nem verificabilidade**.

> Status honesto: esta entrega contém a base + infraestrutura open source.
> Nenhum formato próprio existe ainda. Nenhum número de compressão sobre dados
> reais do TSE é afirmado aqui — os primeiros números reais saem na Fase 2
> (ver `docs/PLANO.md`).

## O que o UrnaPack faz

- `inspect` — varre um diretório, agrega contagem/bytes por extensão e gera
  **manifesto versionado** (`format_version`, SHA-256 por arquivo).
- `benchmark` — mede baselines reais sobre arquivos: `stored` + ZSTD
  (quick: níveis 1,3 · exhaustive: 1,3,10,19), com tempo de compressão/
  descompressão e **round-trip byte a byte conferido**.
- `verify` — verificador independente: relê o manifesto do disco, recalcula
  SHA-256 da origem e aprova/reprova (detecta ausente, truncado, alterado,
  path traversal). Emite JSON + texto; exit 1 em divergência.
- Distribuição futura: pacotes `.upk.zst` por UF/turno via GitHub Releases,
  com manifestos criptográficos e índice público (`data/index.json`).

## O que o UrnaPack NÃO comprova

- Um pacote com hash correto **não prova**, por si só, correspondência com os
  arquivos do TSE — só prova integridade contra o manifesto publicado.
- A correspondência com o TSE exige baixar os oficiais, validar a origem e
  **reexecutar a transformação** (ver `docs/VERIFICACAO.md`).
- Assinaturas geradas pelo projeto nunca são apresentadas como assinaturas
  do TSE. O projeto **não produz conclusões de fraude** a partir de anomalias.

## Princípios de integridade

1. Nunca afirmar prova mais forte que a implementada.
2. Nunca descartar registro silenciosamente; falhar explicitamente.
3. Sem arquivos oficiais íntegros = sem reverificação integral.
4. Sem número inventado: todo ganho precisa de benchmark reproduzível.
5. Nenhum dado fictício em manifestos, releases ou relatórios.

## Instalação e compilação

Requer Rust 1.99 (ver `rust-toolchain.toml`; `rustup` instala automaticamente).

```bash
cargo build --release
./target/release/tsepack --help
```

## Como executar testes

```bash
cargo fmt --check
cargo check --all-targets
cargo clippy --all-targets -- -D warnings
cargo test
python3 scripts/validate.py repo        # limites, nomes, esquemas, índice, segredos
python3 scripts/validate.py self-test   # cenários: hash ruim, ausente, truncado, duplicado...
```

## Como validar datasets

```bash
# 1. Integridade do pacote contra o manifesto publicado:
tsepack verify --manifest manifest.json --source ./originais

# 2. Formato e convenções do repositório:
python3 scripts/validate.py manifest <manifest.json> --data-root <dir-dos-pacotes>
python3 scripts/validate.py index data/index.json
```

Detalhes em `spec/format.md` e `docs/VERIFICACAO.md`.

## Como encontrar os dados publicados

- Catálogo: `data/index.json` (vazio até a primeira publicação real).
- Releases com tag `data-<ano>-t<turno>-<UF>-<versão>` (ex.: `data-2026-t2-MT-v1`).
- Nenhum pacote `.upk.zst` é versionado no Git — só em Releases.

## Aviso legal

Projeto **independente**, sem vínculo ou endosso do Tribunal Superior
Eleitoral. Os dados originais do TSE preservam sua origem e condições de uso;
esta licença MIT cobre apenas o software do UrnaPack, não o conteúdo oficial.

## Licença e contribuição

- Licença: MIT (`LICENSE`). Decisão: licença permissiva e simples, padrão do
  ecossistema de tooling; sem copyleft para maximizar reuso por auditores
  independentes. Sem CLA; contribuições seguem a mesma licença.
- Como contribuir: `CONTRIBUTING.md`. Segurança: `SECURITY.md`.
- Regras para agentes de IA: `AGENTS.md`.
