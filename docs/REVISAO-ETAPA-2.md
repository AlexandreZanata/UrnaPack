# Revisão da Etapa 2 — ingestão gerenciada e contratos de dados

> Registro histórico da entrega do agente. A revisão posterior encontrou
> falhas adicionais em aquisição, vínculos e validação; o estado corrigido
> está em [Revisão das fases 2–4](REVISAO-ETAPAS-2-4.md). Os checks G2 abaixo
> não constituem aprovação atual: falta o vínculo por hash do recibo de execução.

Data: 28/10/2026. Escopo: `docs/ETAPA-2.md`. Parada para revisão antes da Etapa 3.
Sem commit/push sem autorização (este documento integra a entrega a commitar).

## Resumo

- E2.1 (aquisição): `scripts/fetch_source.py` (stdlib) com URL por arquivo,
  metadados HTTP, retomada `Range` com checkpoint, conclusão atômica após
  SHA-256/tamanho, recibo `fetch-run.json` conforme `spec/execution.schema.json`.
  10 regressões com servidor HTTP local; prova real mínima: 1 sidecar oficial
  baixado da CDN, byte-identical ao acervo, com metadados registrados.
- E2.2 (contratos): origem `FORMAT_VERSION=2` (leitura {1,2}, escrita v2,
  `deny_unknown_fields`, migração testada); dataset v2
  (`source_manifest_sha256` + `execution`, raiz/itens estritos) com
  `validate.py` selecionando schema e reconfrontando o vínculo;
  `spec/execution.schema.json` v1 + subcomando `execution`. v1 congelados.
- E2.3 (BU web): `spec/bweb.canonical-v1.md` (tipos lexicais, domínios MT-2026,
  consistências cruzadas, chave de ocorrência, regra aritmética, Q1–Q5) +
  `scripts/validate_bweb.py` executado na BU web real: 891.997 registros,
  0 divergências, chave única (evidência local, não prova nacional).
- Fontes e escopos em `docs/FONTES.md`; 5/5 sidecars oficiais confrontados OK.

## Arquivos

Novos: `docs/ETAPA-2.md`, `docs/FONTES.md`, `docs/REVISAO-ETAPA-2.md`,
`scripts/fetch_source.py`, `scripts/test_fetch_source.py`,
`scripts/validate_bweb.py`, `scripts/test_validate_bweb.py`,
`spec/execution.schema.json`, `spec/manifest-v2.schema.json`,
`spec/bweb.canonical-v1.md`, `tests/fixtures/origin-v2-good.json`,
`tests/fixtures/dataset-v2-good.json`, `tests/fixtures/execution-good.json`,
`tests/fixtures/execution-bad.json`, `tests/fixtures/data/origem-v2.bin`.

Editados: `src/lib.rs` (FORMAT_VERSION 2 + suportadas), `src/manifest.rs`
(estrito, guarda {1,2}), `tests/integracao.rs` (+5 migração/versão),
`scripts/validate.py` (schemas v1/v2, vínculo, execution),
`scripts/test_validate.py` (+5), `scripts/limits.env` (fetch + bweb),
`spec/format.md` (políticas v2), `tests/fixtures/README.md`.

## Comandos e resultados reais

- `cargo fmt --check`, `git diff --check`, `check`, `clippy -D warnings`: OK.
- `cargo test --locked --offline`: OK (3+2+28; inclui 5 novos de origem v2).
- `python3 -m unittest discover -s scripts -p 'test_*.py'`: OK (58 testes).
- `validate.py repo` / `self-test`: OK (9/9; sem `jsonschema` reprova explícito).
- `validate.py manifest dataset-v2-good --source-manifest origin-v2-good`: OK;
  v1 sob `--schema-version 2` e vínculo divergente reprovam explícitos.
- `validate.py execution` (bom/ruim): aprova/reprova como esperado.
- `cargo build --release --locked --offline`: OK.
- `tsepack verify` do manifesto v1 local: 13/13 aprovados (v1 segue verificável).
- `fetch_source.py` (sidecar real da CDN → temporário): exit 0, byte-identical,
  metadados `content-length`/`etag`/`last-modified` registrados, sem
  `accept-ranges` (recomeço documentado quando aplicável).
- `validate_bweb.py` (BU web real no ZIP): exit 0 — 891.997 registros,
  0 divergências de campos/padrão/domínio/aritmética, 891.997 chaves distintas.

Relatórios locais (ignorados): recibos `fetch-run.json` nos destinos; relatório
da BU web em temporário. Nenhum artefato final promovido parcialmente em falha.

## Limites e G2

- [x] Aquisição gerenciada com prova real mínima, sem mover gigabytes.
- [x] Contratos versionados, vínculos e migração testados; v1 legíveis.
- [x] Regras da BU web executadas em MT; chave única e aritmética verificadas.
- [x] Fontes/escopos documentados; Q1–Q5 planejadas sem escolha física.
- [ ] Revisão técnica humana — **pendente**.

Pendentes p/ revisão: aprovar domínios MT-2026 como v1 do canônico (extensão por
versão); aprovar `deny_unknown_fields` como política definitiva; autorizar Etapa 3.
Fora da garantia: unicidade nacional de chaves, equivalência semântica, `restore`,
compressão especializada, publicação; t2 segue parcial no acervo.
