# Bateria exploratória de anomalias estatísticas

Leia [PROTOCOLO.md](PROTOCOLO.md) e o
[contrato v1](../../../spec/statistical-suite-v1.md). O protocolo foi fixado
no Git antes da execução nova, com consciência da análise descritiva anterior.
Critérios bilaterais, candidatos simétricos, testes nulos e todos os resultados
ficam preservados. Desvio de modelo não é probabilidade de fraude.

Resultados medidos: [RELATORIO.md](RELATORIO.md); interpretação e seguimento
de todos os alertas: [CONCLUSOES.md](CONCLUSOES.md). Os recibos pequenos estão
em `evidencias/`; CSVs completos e snapshots HTML estaduais ficam no pacote
comprimido, com inventário e hashes. O núcleo foi executado na revisão
`45a3955327085f0912e9d339421ea5d793edb660`.

## Reproduzir

Use clone Git em revisão fixa, Rust/Cargo, Python 3.12 e SSD com espaço livre.
O pacote de resultados contém a projeção original `sources/sections.csv`,
a política nominal e o relatório anterior de logs com os hashes fixados.
Os originais nacionais de centenas de GB não são necessários para repetir
esta bateria; sua relação com a projeção está na auditoria inicial.

```bash
bash scripts/reproduce_statistical_suite_2026.sh \
  /data/urnapack/suite-estatistica-2026/sources \
  /data/urnapack/suite-estatistica-2026/repeticao-nova
```

Saída nova obrigatória. O comando compila o Rust otimizado com Cargo.lock,
executa o protocolo fixado, confere resultados em implementação independente
e gera relatório e inventário SHA-256. `CARGO_TARGET_DIR` pode apontar para
cache externo no SSD. O cache não é artefato científico. Caminhos e metadados
de ambiente variam; compare dados, definições e resultados científicos.

## Seguimentos adicionais, posteriores aos testes

Para repetir o contexto de todos os alertas, o subcatálogo seleciona **51
recursos e 302.735.050 bytes**: metadados de locais, CEFT ZZ e BU das UFs
envolvidas, com sidecars. Não exige baixar o corpus nacional inteiro.

```bash
python3 scripts/acquire_2026.py fetch \
  --catalog auditoria/2026/suite/evidencias/catalogo-contexto.json \
  --root /data/urnapack/contexto-repeticao/fontes \
  --receipt /data/urnapack/contexto-repeticao-aquisicao.json
python3 scripts/contextualize_statistical_alerts_2026.py \
  --result /data/urnapack/suite-estatistica-2026/execucao-1/results \
  --catalog auditoria/2026/suite/evidencias/catalogo-contexto.json \
  --root /data/urnapack/contexto-repeticao/fontes \
  --bu-zip-root /data/urnapack/contexto-repeticao/fontes \
  --bu-manifest auditoria/2026/evidencias/entrada-buweb-2t.json \
  --output /data/urnapack/contexto-repeticao.json
```

`--result` pode apontar aos resultados descomprimidos do pacote. O seguimento
relê todos os alertas, seus BU originais e as seções do mesmo local. Os campos
cadastrais desconhecidos continuam nos registros exportados. Não reclassifica
scores nem estima sua causa. O escopo de correspondências é CEFT ZZ; uma
lista vazia em outra UF significa fora desse recorte, não dado inexistente.

Para o controle temporal MT, basta adquirir o ZIP 2022 e seu sidecar:

```bash
python3 scripts/acquire_2026.py fetch \
  --catalog auditoria/consolidacao/evidencias/catalogo-historico-fixado.json \
  --match bweb_2t_MT_311020221535.zip \
  --root /data/urnapack/temporal-repeticao/fontes \
  --receipt /data/urnapack/temporal-repeticao-aquisicao.json
python3 scripts/compare_mt_presidential_profiles_2026.py \
  --historical-catalog auditoria/consolidacao/evidencias/catalogo-historico-fixado.json \
  --root /data/urnapack/temporal-repeticao/fontes \
  --result /data/urnapack/suite-estatistica-2026/execucao-1/results \
  --output /data/urnapack/temporal-repeticao.json
```

Esse controle compara perfis em chaves numéricas comuns; não garante a mesma
população entre anos e não procura cópias entre chaves diferentes. Os snapshots
HTML dos documentos estaduais ficam no pacote comprimido; seus URLs, status,
tamanhos e hashes estão em `evidencias/web/sources.json`. São contexto
documental, sem participação nos testes estatísticos.

## Testes do código

```bash
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
python3 -m unittest discover -s scripts -p 'test_statistical_suite.py' -v
```

Para todos os testes Python, instale as dependências declaradas como na
consolidação e rode `test_*.py`. `TMPDIR` deve ter o espaço mínimo exigido
em `scripts/limits.env`. Se definir `CARGO_TARGET_DIR`, mantenha a mesma
variável nos testes Python para que encontrem o executável recém-compilado.
Nenhum teste ausente é convertido em skip/sucesso.

Fixtures artificiais identificadas em `tests/fixtures/statistical-suite/`.
Elas verificam denominadores zero, duplicatas, simetria, adulteração,
matemática conhecida e preservação de saídas. Simulações não são contagens
eleitorais observadas. Os testes estatísticos não validam assinaturas,
relógios físicos, coação ou transmissão.
