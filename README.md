# UrnaPack — Compressão extrema e verificável dos dados do TSE

> **English brief:** UrnaPack is an open-source Rust toolkit to compress,
> structure and independently verify Brazil's public electronic voting data
> (TSE). It optimizes for maximum storage reduction under non-negotiable
> integrity and verifiability constraints. Independent project — not
> affiliated with or endorsed by the TSE.

Versão **v0.2.0** em Rust. Objetivo: minimizar os bytes totais necessários para
preservar a evidência e reproduzir análises dos dados das urnas brasileiras,
**sem perder integridade, cobertura, auditabilidade ou verificabilidade**.

> Etapa 4 concluída para o acervo local de MT: matriz de codecs, dicionários,
> Parquet, consultas e restauração integral executadas. Arquivo FORENSIC local
> v2 com recibo vinculado; cache BU web regenerável. A liberação analítica e
> publicação continuam nas etapas seguintes.
> [Resultados e garantias](docs/RESULTADO-COMPRESSAO-MT.md).

## Planejamento e próxima entrega

- [Plano refinado](docs/PLANO.md): etapas, contratos e critérios de saída.
- [Etapa 1](docs/ETAPA-1.md): correções delimitadas e mapa reproduzível de MT.
- [Prompt para implementar a Etapa 1](docs/PROMPT-ETAPA-1.md).
- [Mapa dos dados brutos](docs/DADOS-BRUTOS.md): layouts observados e contrato
  de catalogação para novos anos, turnos e abrangências.
- [Plano analítico](docs/PLANO-ANALISE.md): validação por uso desde o MVP.
- [Etapa 4](docs/ETAPA-4.md): experimento completo, custos e reprodução.

Os documentos distinguem a base implementada das garantias planejadas.
O mapeador está em `scripts/map_raw_data.py`; resultados e limites da revisão
estão em [Revisão da Etapa 1](docs/REVISAO-ETAPA-1.md).

## O que o UrnaPack faz

- `inspect` — varre um diretório, agrega contagem/bytes por extensão e gera
  **manifesto versionado** (`format_version`, SHA-256 por arquivo).
- `benchmark` — mede baselines em streaming sobre arquivos: `stored` + ZSTD + Brotli 5
  (quick: níveis 1,3 · exhaustive: 1,3,10,19), com tempo de compressão/
  descompressão e SHA-256 dos bytes decodificados conferido. Para pacotes BU web,
  compara ZSTD por coluna e sólido; `--output` salva artefatos e checkpoints,
  `--resume` reconfere os artefatos antes de reutilizar compressões.
- `pack --family bweb` / `unpack` — pacote colunar experimental v2 com
  inverso e compromisso SHA-256 obrigatório, calculado da origem. Rejeita
  variantes de CSV que não recuperem os bytes originais; preserva ordem,
  duplicatas e valores lexicais. [Contrato](spec/bweb-pack-v2.md).
- `scripts/fetch_source.py` — aquisição com retomada e hash esperado;
  `scripts/validate_bweb.py` — regras do perfil MT-2026-t1;
  `scripts/verify_pack.py` — confronto independente de todos os valores e bytes.
- `codec compress/check/decompress/train` — codecs padrão com prova de bytes;
  `optimize` — seleção por arquivo; `archive` — TAR/selagem/conferência;
  `restore` — restauração integral do arquivo FORENSIC.
- `queries` — controles Q1/Q2 e seção/cargo de referência. A automação
  `scripts/compression_stage.py` compara as representações e gera o bundle mínimo.
- `verify` — relê o manifesto de origem do disco, recalcula SHA-256 e
  aprova/reprova arquivos ausentes, truncados ou alterados. Emite JSON + texto;
  exit 1 em divergência detectada. As correções da Etapa 1 rejeitam versão
  incompatível, caminhos duplicados/não canônicos e symlinks internos; a
  inspeção propaga os erros de travessia.
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

Binário Linux x86_64 e SHA-256 estão nas
[releases de software](https://github.com/AlexandreZanata/UrnaPack/releases).
Mudanças e compatibilidade: [CHANGELOG.md](CHANGELOG.md).
XZ precisa estar instalado para os codecs XZ; os demais codecs fazem parte do binário.

Requer Rust 1.99 (ver `rust-toolchain.toml`; `rustup` instala automaticamente).

```bash
cargo build --release
./target/release/tsepack --help
```

Os experimentos e testes Python completos usam `scripts/requirements-compression.txt`,
mais `pyyaml` e `jsonschema`. Os dados e resultados locais não integram o Git nem
o binário de software; sua geração e restauração estão documentadas na Etapa 4.

## Como executar testes

```bash
cargo fmt --check
cargo check --all-targets
cargo clippy --all-targets -- -D warnings
cargo test
python3 scripts/validate.py repo        # limites, nomes, esquemas, índice, segredos
python3 scripts/validate.py self-test   # cenários: hash ruim, ausente, truncado, duplicado...
python3 -m unittest discover -s scripts -p 'test_*.py'
```

## Como validar datasets

```bash
# 1. Integridade dos arquivos contra o manifesto de origem gerado por inspect:
tsepack verify --manifest manifest-origem.json --source ./originais

# 2. Formato e convenções do repositório:
python3 scripts/validate.py manifest <manifest.json> --data-root <dir-dos-pacotes>
python3 scripts/validate.py index data/index.json
```

Detalhes em `spec/format.md` e `docs/VERIFICACAO.md`.
O manifesto de dataset de distribuição e o manifesto de origem Rust têm
contratos diferentes; o `verify` atual não valida transformações semânticas.

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
