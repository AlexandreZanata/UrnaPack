# Bateria exploratória de anomalias estatísticas

Leia [PROTOCOLO.md](PROTOCOLO.md) e o
[contrato v1](../../../spec/statistical-suite-v1.md). O protocolo foi fixado
no Git antes da execução nova, com consciência da análise descritiva anterior.
Critérios bilaterais, candidatos simétricos, testes nulos e todos os resultados
ficam preservados. Desvio de modelo não é probabilidade de fraude.

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
