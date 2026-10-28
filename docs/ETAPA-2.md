# Etapa 2 — ingestão gerenciada e contratos de dados

## Missão e limite da entrega

Transformar downloads ad hoc em **aquisição gerenciada** (URL por arquivo,
metadados HTTP, retomada validada, conclusão atômica, confronto de hash) e
**formalizar os contratos versionados** (origem, dataset, execução) com
vínculos por hash, política de campos desconhecidos e migração testada —
além das **regras executáveis da primeira família a transformar (BU web)**:
esquema canônico documental, validação de chaves nos dados e consultas
representativas planejadas.

Esta etapa não implementa transformador, inverso, formato próprio, Parquet/Arrow,
parser ASN.1, `restore`, análise estatística ou publicação. Não baixa nem altera
o acervo local existente salvo prova mínima explícita (um sidecar de 158 bytes).
Nenhum número novo é prometido; semântica continua hipótese até a Etapa 3.

Trabalhar sequencialmente em três incrementos. Reutilizar `src/`, `scripts/` e
`spec/`; sem dependência Rust nova; Python de automação somente em `scripts/`.
Limites operacionais em `scripts/limits.env`, sem duplicação em código.

## Entrada disponível

- Origem v1: `Manifest { format_version: 1, ... }` em `src/manifest.rs`
  (leitura de v1 válidos preservada desde a Etapa 1).
- Dataset v1: `spec/manifest.schema.json` + `spec/index.schema.json` +
  `scripts/validate.py` + fixtures em `tests/fixtures/`.
- Mapa estrutural v1: `scripts/map_raw_data.py` + `relatorios-locais/etapa-1/mt/`.
- Evidência de aquisição atual: URLs oficiais em `dados/baixa-mt.sh` (local,
  fora do Git) sob `https://cdn.tse.jus.br/estatistica/sead`.
- Regras: `AGENTS.md`, `docs/PLANO.md` (Etapa 2), `docs/ARQUITETURA.md`,
  `docs/VERIFICACAO.md`, `docs/DADOS-BRUTOS.md`, `docs/REVISAO-ETAPA-1.md`.

## E2.1 — Aquisição gerenciada com prova mínima real

Criar `scripts/fetch_source.py` (stdlib, `urllib`): dado um manifesto de origem
com `url` por arquivo e SHA-256/tamanho esperados, para cada arquivo:

- Capturar metadados HTTP disponíveis (status, Content-Length, ETag,
  Last-Modified, Accept-Ranges) sem fingir suporte inexistente.
- Retomar via `Range` a partir de parcial `.partial` + deslocamento em disco;
  se o servidor ignorar o intervalo (200 em vez de 206), recomeçar do zero e
  registrar `range_ignored: true` (nunca promover parcial como completo).
- Escrever parciais separadamente e concluir por operação atômica (rename) **só
  após** SHA-256 recomputado dos bytes finais conferir com o esperado e o
  tamanho conferir; divergência reprova explicitamente (exit ≠ 0) e preserva o
  diagnóstico, sem deixar arquivo final marcado como íntegro.
- Emitir recibo de execução por arquivo (URL, bytes, hashes, metadados, tempos,
  `resumed`, ferramenta/versão) em JSON determinístico.

Regressões em `scripts/test_fetch_source.py` com servidor HTTP local nos testes
(suporte a `Range` sob controle do teste): retomada real após interrupção
simulada, rejeição de hash divergente, metadados registrados, saída dentro da
fonte recusada. Prova real mínima: baixar **um** sidecar `.sha512` (158 bytes)
da CDN oficial com a ferramenta e confrontar com o acervo local — sem baixar
gigabytes, sem alterar o acervo (destino em temporário ignorado).

## E2.2 — Contratos versionados, vínculos e migração

1. **Origem v1→v2 (Rust, sem dependência nova):** congelar a leitura de v1
   válidos; `FORMAT_VERSION = 2`; escrita gera v2; leitura aceita `{1, 2}` e
   rejeita outras versões explicitamente. V2 = mesmos campos de v1 com
   `deny_unknown_fields` (campo desconhecido bloqueia interpretação automática,
   em vez de silêncio). Teste de migração: v1 válido → carrega → regrava em v2
   com `files[]` idênticos (caminhos, tamanhos, hashes preservados byte a byte
   no conteúdo). `spec/format.md` documenta a política e o vínculo entre versões.
2. **Dataset v2 (schema):** `spec/manifest-v2.schema.json` = v1 + `format_version:
   const 2` + `source_manifest_sha256` (obrigatório, hex64 — vínculo por hash com
   o manifesto de origem) + `execution` (objeto opcional conforme
   `spec/execution.schema.json`). `additionalProperties: false` no nível raiz e
   nos itens (desconhecido bloqueia). `validate.py` seleciona o schema pela
   `format_version` declarada; v1 congelado (fixtures existentes continuam
   válidas). Teste de compatibilidade: v1 não passa em v2 (erro explícito de
   versão/campo), migrado passa, extras reprovam.
3. **Execução v1 (novo contrato):** `spec/execution.schema.json` —
   `artifact_kind: urnapack_execution`, `format_version: 1`, ferramenta/versão,
   comando/parâmetros, hashes das entradas, hashes das saídas, ambiente e tempos.
   Generaliza os `run.json` locais. `validate.py` ganha o subcomando `execution`;
   `fetch_source.py` emite recibos conformes. Fixtures sintéticas com hashes reais.

## E2.3 — Regras executáveis da primeira família (BU web)

1. **Esquema canônico documental:** `spec/bweb.canonical-v1.md` (versionado no
   nome): tipos lexicais por coluna (sem cast), domínios/sentinelas, precisão e
   formato de datas (hipóteses marcadas), chave candidata de ocorrência e de
   contexto, cardinalidades esperadas e regras de agregação (o que soma, o que
   nunca soma). Nenhuma hipótese vira deduplicação: duplicata de chave candidata
   **reprova com evidência**, nunca descarta.
2. **Validador executável:** `scripts/validate_bweb.py` (stdlib, streaming):
   cabeçalho exato em ordem, contagem de campos por registro (com ordinal/linha),
   domínios lexicais por coluna, sentinelas, e unicidade da chave candidata de
   ocorrência (conjunto de hashes; duplicatas listadas com ordinal, sem remover).
   Limites de `scripts/limits.env`. Saída: relatório JSON + exit ≠ 0 em divergência.
3. **Execução real em MT:** rodar o validador no CSV BU web local; documentar o
   resultado (chave única ou não, domínios divergentes) em `docs/REVISAO-ETAPA-2.md`
   como evidência para a Etapa 3 — sem transformar, sem concluir unicidade global.
4. **Consultas representativas planejadas** (só plano, sem código): Q1 votos por
   cargo/UE, Q2 comparecimento por zona/seção, Q3 eleitores por local, Q4 confronto
   BU×votação por seção/cargo, Q5 trilha de auditoria ocorrência→fonte. Guiarão a
   representação física futura; nenhuma escolha física nesta etapa.
5. **Fontes e escopos:** `docs/FONTES.md` — por arquivo oficial: URL oficial
   (evidência), sidecar/hash disponível e estado, turno/abrangência da fonte,
   cobertura do acervo local (t1 completo, t2 parcial), lacunas. Sem caminhos
   físicos, sem inventário de bytes/hashes do disco.

## Verificações e encerramento

```bash
cargo fmt --check
cargo check --locked --offline --all-targets
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/validate.py repo
python3 scripts/validate.py self-test
cargo build --release --locked --offline
./target/release/tsepack verify \
  --manifest dados/manifest-2026-mt.json --source dados/brutos/2026
python3 scripts/fetch_source.py --help
python3 scripts/validate_bweb.py --help
```

Se dependência/ambiente impedir algum comando, registrar a falha exata e
continuar os trabalhos independentes; não declarar o portão concluído. Teste
que não exercitou a verificação não pode ser apresentado como aprovado.

G2 exige E2.1–E2.3 executados, prova real mínima, contratos versionados com
migração testada, regras da BU web executadas em MT e pendências explicitadas.
Parar ao concluir; preparar relatório para revisão. Sem commit/push sem
autorização explícita.
