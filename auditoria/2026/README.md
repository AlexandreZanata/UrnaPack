# Auditoria das imagens sobre as eleições de 2026

O [relatório](RELATORIO.md) confronta individualmente o conteúdo das
[quatro imagens transcritas](TRANSCRICAO.md) com dados e documentos oficiais.
O download amplo e a análise dos logs têm estado próprio; não estão
implicitamente concluídos porque a soma dos BU web foi executada.

## Artefatos

- `imagens/`: anexos originais do usuário, preservados byte a byte.
- `evidencias/imagens.json`: tamanhos e SHA-256 dos anexos.
- `evidencias/ckan-package-search-2026.json`: resposta CKAN original.
- `catalogo-ckan.json`: URLs e referências extraídas, sem apagar aliases.
- `catalogo.json`: catálogo de trabalho, incluindo a descoberta documentada
  do ZIP RR t2 a partir do sidecar que o catálogo referencia duas vezes.
- `evidencias/planejamento-http.json`: HEAD por URL; tamanho ausente é `null`.
- `evidencias/aquisicao-*.json`: histórico de tentativas, erros, HTTP e hashes.
  Um recibo interrompido não é um selo de completude do acervo.
- `evidencias/entrada-buweb-2t.json`: vínculo ZIP/CSV/UF/bytes/SHA-256.
- `evidencias/membros-buweb.json`: todos os membros de cada ZIP presidencial.
- `resultados/presidente-2t.json`: cálculo Rust e definições dos indicadores.
- `resultados/confronto-imagens.json`: afirmações numéricas e confronto com
  a totalização nacional oficial.
- `evidencias/web/`: obtenção e limitações das fontes documentais.

## Armazenamento local

O link já existente `dados -> /data/urnapack` leva ao SSD de dados.
O acervo novo fica em `/data/urnapack/auditoria-2026/`:

- `fontes/<host>/<caminho-oficial>`: originais, recibos individuais,
  validadores HTTP, locks e eventuais parciais.
- `extraidos/buweb-2t/<UF>/`: CSVs copiados dos ZIPs sem recodificação.
- `quarentena/`: parciais preservados que não podem ser usados como íntegros.

Dados brutos volumosos não entram no Git tradicional. O GitHub recebe código,
documentação, imagens recebidas, fontes documentais pequenas, manifestos e
resultados reais. O catálogo delimita o snapshot da busca CKAN, não promete
um espelho integral de PJe/DivulgaCand ou outros sistemas.

## Repetir aquisição

Execute a partir da raiz do repositório. Há retomada validada e bloqueio por
destino. Use um nome novo para cada recibo de tentativa a preservar.

```bash
curl --fail --location --silent --show-error \
  'https://dadosabertos.tse.jus.br/api/3/action/package_search?q=2026&rows=100' \
  -o /tmp/urnapack-ckan-2026-atual.json
python3 scripts/acquire_2026.py catalog \
  --snapshot /tmp/urnapack-ckan-2026-atual.json \
  --catalog /tmp/urnapack-catalogo-atual.json
```

Isso descobre um novo snapshot e não repete automaticamente a inclusão RR.
Para repetir exatamente o catálogo preservado, use os comandos seguintes.

```bash
python3 scripts/acquire_2026.py fetch \
  --catalog auditoria/2026/catalogo.json \
  --root /data/urnapack/auditoria-2026/fontes \
  --receipt /tmp/urnapack-fetch-repeticao.json
python3 scripts/acquire_2026.py verify \
  --catalog auditoria/2026/catalogo.json \
  --root /data/urnapack/auditoria-2026/fontes \
  --receipt /tmp/urnapack-verify-repeticao.json
```

`verify` relê os bytes, confere SHA-256 e os sidecars publicados, não baixa
arquivos ausentes e retorna exit diferente de zero se algo faltar ou divergir.
O planejamento pode ser repetido com `plan --catalog ... --receipt ...`.
Limites e concorrência estão em `scripts/limits.env`.

## Repetir cálculo

```bash
python3 scripts/prepare_audit_2026.py \
  --catalog auditoria/2026/catalogo.json \
  --root /data/urnapack/auditoria-2026/fontes \
  --destination /data/urnapack/auditoria-2026/extraidos/buweb-2t \
  --evidence /tmp/urnapack-audit-evidence \
  --manifest /tmp/urnapack-audit-input.json
cargo build --release --bin audit_2026
target/release/audit_2026 \
  --manifest /tmp/urnapack-audit-input.json \
  --output /tmp/urnapack-audit-result.json \
  --sections-output /data/urnapack/auditoria-2026/secoes-presidente-2t-repeticao.csv
python3 scripts/check_audit_2026.py \
  --report /tmp/urnapack-audit-result.json \
  --official auditoria/2026/evidencias/totalizacao-presidente-2t.json \
  --output /tmp/urnapack-audit-comparison.json
python3 scripts/reconcile_coverage_2026.py \
  --sections /data/urnapack/auditoria-2026/secoes-presidente-2t-repeticao.csv \
  --export-receipt auditoria/2026/evidencias/exportacao-secoes-v1.json \
  --source-manifest /tmp/urnapack-audit-input.json \
  --report /tmp/urnapack-audit-result.json \
  --official auditoria/2026/evidencias/totalizacao-presidente-2t.json \
  --output /tmp/urnapack-cobertura-repeticao.json
```

O binário preserva saídas existentes; escolha um caminho ainda inexistente.
A transformação analítica está documentada em `spec/audit-2026-v1.md`.

## Testes

```bash
python3 -m unittest discover -s scripts -p 'test_acquire_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_check_audit_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_prepare_audit_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_reconcile_coverage_2026.py' -v
cargo test --bin audit_2026 --test audit_2026
```

Os testes executam o binário sobre fixture sintética identificada em
`tests/fixtures/audit-2026/`, com hash real. O confronto também usa os pequenos
relatórios reais versionados; mutações locais são apenas testes negativos.
As alterações que já existiam no checkout antes da auditoria não pertencem
a esta entrega.
