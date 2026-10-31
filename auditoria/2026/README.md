# Auditoria das imagens sobre as eleições de 2026

O [relatório](RELATORIO.md) confronta individualmente o conteúdo das
[quatro imagens transcritas](TRANSCRICAO.md) com dados e documentos oficiais.
A aquisição dos 942 recursos foi concluída e relida sem erros. Os logs das
28 abrangências foram processados, com diagnóstico nacional explícito:
41 chaves presentes não conciliadas e uma chave esperada ausente em SP.
Isso não impede documentar os achados, mas impede aprovar a conciliação
integral ou anunciar uma contagem exata nacional de eventos após 17h.

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

Nos releases serão distribuídos somente os dados tratados e comprimidos,
com inventário, hashes e prova de restauração. O acervo original de centenas
de GB permanece no SSD e não será enviado como assets. Um pacote deve declarar
exatamente quais dados contém: compressão reversível conserva os bytes da
entrada selecionada; uma projeção analítica continua sendo transformação
semântica, mesmo quando depois é comprimida sem perdas.

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

`verify_zip_integrity_2026.py` acrescenta leitura de todos os membros declarados
dos ZIPs externos, com CRC/tamanho conferidos por ordinal, inclusive nomes
repetidos. O cache só é reutilizado após novo hash integral da fonte e com a
mesma chave de implementação/ambiente/limites. Recursos não ZIP são contados
explicitamente fora dessa etapa; sua integridade permanece coberta por
`acquire_2026.py verify`. ZIPs aninhados são opacos para o CRC externo; os
logs usados na análise são abertos e conferidos também pela importação.

O catálogo fixado, quando gerado após a verificação integral, acrescenta o
tamanho e SHA-256 realmente medidos de cada recurso. `fetch` e `verify`
conferem esses valores; uma mudança na URL oficial reprova em vez de produzir
silenciosamente outro snapshot. O catálogo de descoberta original continua
preservado. Gere a fixação com `scripts/pin_catalog_2026.py`, fornecendo o
catálogo e o recibo final de `verify`; cobertura parcial ou com erros reprova.

Para usar curl com HTTP/2 na aquisição, acrescente `--transport curl` a
`fetch`. É necessário curl compilado com HTTP/2 (`curl --version`). A
implementação valida status e cabeçalhos, corpo, fim do processo e retomada;
um erro de transporte mantém o parcial, sem promovê-lo como íntegro. O
transporte padrão continua sendo a biblioteca padrão do Python.
`--metadata-method range` permite uma sondagem GET de exatamente um byte
quando HEAD não fornece a mesma versão do GET. Exige Content-Range válido,
validadores coerentes e o mesmo primeiro byte no arquivo completo. Não ignora
divergências e não muda o significado dos cabeçalhos no recibo. O catálogo
fixado conserva o método medido por recurso.

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

## Logs e relógio nominal

Compile a revisão escolhida, sem atualizar as dependências travadas:

```bash
cargo build --locked --release --bin audit_2026 --bin audit_logs_2026
python3 scripts/build_time_policy_2026.py --help
```

A política preservada em `evidencias/politica-relogio-nominal-2026.json` usa o
índice municipal oficial preservado. Para acrescentar encerramentos com
deslocamento nominal, repita `audit_2026` com `--time-policy` apontando para
essa política e outro caminho de saída. Os recortes lexicais permanecem no
mesmo relatório para confronto com as imagens.

Após adquirir os ZIPs `arqurnatot` do segundo turno:

```bash
python3 scripts/run_logs_2026.py \
  --root /data/urnapack/auditoria-2026/fontes \
  --catalog auditoria/2026/catalogo.json \
  --sections /data/urnapack/auditoria-2026/secoes-presidente-2t-repeticao.csv \
  --export-receipt auditoria/2026/evidencias/exportacao-secoes-v1.json \
  --policy auditoria/2026/evidencias/politica-relogio-nominal-2026.json \
  --zero-sections auditoria/2026/evidencias/registros-exterior-sem-cargo.json \
  --out-root /data/urnapack/auditoria-2026/logs/repeticao
python3 scripts/collect_logs_2026.py \
  --directories /data/urnapack/auditoria-2026/logs/repeticao/?? \
  --official auditoria/2026/evidencias/totalizacao-presidente-2t.json \
  --output /tmp/urnapack-logs-input.json
target/release/audit_logs_2026 \
  --aggregate-manifest /tmp/urnapack-logs-input.json \
  --output /tmp/urnapack-logs-nacional.json
```

`--ufs AC MT` permite um lote explicitamente parcial. A consolidação não
declara sucesso nacional com UFs ausentes. Cada tentativa usa diretório novo;
não misture duas tentativas da mesma UF no manifesto. O contrato completo,
as definições dos eventos e as limitações estão em
[spec/audit-logs-2026-v1.md](../../spec/audit-logs-2026-v1.md).

## Testes

A análise e a aquisição usam biblioteca padrão do Python e as dependências
Rust travadas em `Cargo.lock`. O ambiente de cada execução deve registrar
`rustc --version --verbose`, `python3 --version` e `curl --version`.
Para executar também todos os testes e experimentos preexistentes do
repositório, instale num ambiente virtual `pyyaml==6.0.2`,
`jsonschema==4.23.0` e `scripts/requirements-compression.txt`, conforme a CI.
Os dados volumosos exigem espaço no volume de destino; a aquisição consulta
o espaço livre e respeita o limite centralizado.

```bash
python3 -m unittest discover -s scripts -p 'test_acquire_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_check_audit_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_prepare_audit_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_reconcile_coverage_2026.py' -v
cargo test --bin audit_2026 --test audit_2026
cargo test --bin audit_logs_2026 --test audit_logs_2026
python3 -m unittest discover -s scripts -p 'test_import_logs_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_curl_transport.py' -v
python3 -m unittest discover -s scripts -p 'test_package_buweb_audit_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_relocate_audit_manifest_2026.py' -v
python3 -m unittest discover -s scripts -p 'test_verify_zip_integrity_2026.py' -v
```

Os testes executam o binário sobre fixture sintética identificada em
`tests/fixtures/audit-2026/`, com hash real. O confronto também usa os pequenos
relatórios reais versionados; mutações locais são apenas testes negativos.
As alterações que já existiam no checkout antes da auditoria foram
preservadas para a etapa posterior de consolidação solicitada pelo usuário.

## Execução integral em um comando

Após publicar o catálogo fixado completo, o comando abaixo repete a aquisição,
releitura de integridade, BU, política nominal, conciliação de cobertura e
logs. O segundo diretório deve ser novo. Execute de uma revisão Git conhecida.

```bash
bash scripts/reproduce_audit_2026.sh \
  /data/urnapack/auditoria-2026/fontes \
  /data/urnapack/auditoria-2026/reproducao-nova
```

O catálogo fixado já está versionado. O roteiro verifica seu vínculo com o
catálogo de descoberta e exige tamanho/SHA-256 para cada recurso antes de
criar o diretório da execução. Ele também repete a conciliação das origens
do exterior com o ZIP CEFT. Uma URL oficial que passe a servir bytes diferentes
reprova; nesse caso, use os originais preservados com os mesmos hashes.

`exit 1` por diagnóstico de logs não significa que o programa declarou
sucesso nem que a aquisição falhou. Confira `verification.json`,
`zip-integrity.json`, `log-national.json` e `artifacts.json` separadamente.
O inventário final registra os códigos de logs, consolidação e empacotamento.

O script registra ambiente, revisão Git, executáveis, comandos/recibos de
importação e hashes dos artefatos. Uma divergência científica nos logs produz
diagnóstico e exit diferente de zero; não é convertida em sucesso pela
orquestração. Falhas anteriores preservam os recibos e parciais já produzidos.
Metadados de caminho/ambiente podem variar entre máquinas; compare as
definições, contagens e hashes dos dados, sem confundir equivalência semântica
com igualdade byte a byte de todos os arquivos de proveniência.

A repetição integral em clone limpo foi concluída e seus 257 artefatos foram
relidos: [recibo final](evidencias/reproducao-integral-final.json). Os campos
presidenciais e os relatórios por UF coincidiram com os resultados publicados.
Os códigos de logs e consolidação continuam 1 pelos diagnósticos descritos;
o empacotamento terminou com código 0. Aquisição e integridade não foram
confundidas com aprovação científica da conciliação.

## Pacote comprimido dos CSVs usados na auditoria

O primeiro pacote verificado contém os **28 CSVs originais de BU web t2**,
com todas as colunas e linhas, incluindo registros de outros cargos que não
entram na análise presidencial. São **924.395.728 bytes de CSVs** em um asset
de **67.026.472 bytes**, incluindo payload e metadados. Esse denominador é o
conjunto de CSVs selecionados, não o acervo de ZIPs de centenas de GB.

O formato interno é o arquivo UrnaPack v2 já implementado, com TAR e ZSTD19;
o invólucro externo é ZIP padrão com armazenamento do payload já comprimido.
Não é um formato binário UPK novo. O pacote não contém os ZIPs originais do
TSE nem todos os logs de urna. As fontes volumosas ficam no SSD, vinculadas
por URLs, hashes e recibos. A compressão conserva os bytes dos CSVs selecionados.

A geração e a restauração dos 28 arquivos foram executadas e conferidas em
[pacote-buweb-2t-csv.json](evidencias/pacote-buweb-2t-csv.json). Em outro
diretório, o asset foi extraído e restaurado, seu manifesto realocado após
nova releitura dos hashes, e o cálculo nacional repetido. Todos os campos
do relatório, exceto os caminhos dos membros, ficaram iguais, conforme
[reproducao-offline-pacote-2026.json](evidencias/reproducao-offline-pacote-2026.json).

Para gerar novamente, use destino novo:

```bash
python3 scripts/package_buweb_audit_2026.py \
  --input /data/urnapack/auditoria-2026/extraidos/buweb-2t \
  --expected-manifest auditoria/2026/evidencias/entrada-buweb-2t.json \
  --output /data/urnapack/auditoria-2026/tratados/buweb-2t-novo \
  --source tse-dados-abertos:buweb-2026-2t-csv
```

Depois de obter e conferir o hash do asset publicado, extraia-o em diretório
novo e execute os comandos a seguir. `pacote/` é a raiz extraída do ZIP.

```bash
target/release/tsepack archive verify --input pacote/archive
target/release/tsepack restore --dataset pacote/archive --output csvs-restaurados
python3 scripts/relocate_audit_manifest_2026.py \
  --manifest pacote/audit-input.json --restored csvs-restaurados \
  --output /tmp/urnapack-entrada-local.json
target/release/audit_2026 --manifest /tmp/urnapack-entrada-local.json \
  --time-policy auditoria/2026/evidencias/politica-relogio-nominal-2026.json \
  --output /tmp/urnapack-resultado-local.json
```

Esse caminho reproduz o cálculo dos BU sem baixar os ZIPs originais. O
reprocessamento dos eventos dos logs requer os respectivos ZIPs oficiais;
resumos e índices não substituem seus bytes originais.

## Empacotar resultados derivados dos logs

O pacote de resultados é um ZIP padrão de uma seleção explícita. `_inventory.json`
registra caminhos, tamanhos e SHA-256 dos membros; o empacotador relê todos os
membros e confere CRC, tamanho e SHA-256 antes de publicar o asset. Os arquivos
derivados são preservados byte a byte; isso não torna a análise uma restauração
dos logs originais. Os limites continuam em `scripts/limits.env`.

```bash
python3 scripts/package_audit_results_2026.py \
  --input /data/urnapack/auditoria-2026/reproducao-integral-1 \
  --output /data/urnapack/auditoria-2026/tratados/resultados-logs-novo \
  --include logs sections.csv sections-export.json log-national.json \
    time-policy.json comparison.json coverage.json environment.json \
    bu-input.json verification.json zip-integrity.json \
  --scope 'Resultados derivados e índices de proveniência dos logs; sem os ZIPs originais do TSE'
```

O pacote inclui todos os arquivos sob `logs`, inclusive diagnósticos e índices;
não contém os corpos originais dos logs. Para repetir os eventos a partir dos
originais, use os ZIPs oficiais e o roteiro integral. Para repetir a verificação
dos assets baixados do GitHub, execute `sha256sum -c SHA256SUMS-audit-2026` no
diretório do download. A primeira conferência publicada está em
`evidencias/download-release-conferido.json`.
