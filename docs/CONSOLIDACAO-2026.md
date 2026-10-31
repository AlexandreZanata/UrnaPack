# Consolidação e reprodução da auditoria

A auditoria inicial das quatro imagens está em
[CONCLUSOES.md](../auditoria/2026/CONCLUSOES.md) e
[RELATORIO.md](../auditoria/2026/RELATORIO.md). O release
[audit-2026-buweb-v1](https://github.com/AlexandreZanata/UrnaPack/releases/tag/audit-2026-buweb-v1)
preserva seus produtores, dados selecionados comprimidos e resultados.
Somente depois dessa publicação começou a consolidação das mudanças locais
e dos PRs #1, #2, #4, #9 e #10. Os commits originais foram preservados por
merges; não houve substituição do trabalho local por uma árvore remota.

## Evidência da execução

Os recibos pequenos estão em
[auditoria/consolidacao/evidencias](../auditoria/consolidacao/evidencias/).
Os resultados maiores são distribuídos comprimidos no release
`consolidacao-2026-v1`. Nenhum desses pacotes contém o acervo nacional bruto
de 252.866.700.631 bytes. Esse snapshot continua no SSD, acessível pelo link
local `dados -> /data/urnapack`, e suas URLs e hashes estão versionados.

- A repetição nacional integral em clone limpo conferiu 942 recursos e
  606 ZIPs externos. Os campos presidenciais e os relatórios por UF dos
  logs coincidiram com os publicados. Os diagnósticos dos logs continuam
  reprovando a conciliação: exit 1, sem transformação em aprovação. A
  [prova final](../auditoria/2026/evidencias/reproducao-integral-final.json)
  registra revisão, hashes, 257 artefatos e códigos de saída.
- O candidato isolado passou em 99 testes Rust, 147 testes Python,
  formatação, clippy com warnings reprovados, validação do repositório e
  nove cenários de falha. `validacao-codigo.json` vincula os logs aos hashes
  das 133 fontes, configurações e fixtures efetivamente comparadas.
- O comando MT `analyze` leu 891.997 registros e aprovou os controles de
  qualidade; o conferidor independente passou nos 17 controles. Sua soma
  de 12.300.723 votos abrange cargos diferentes e não é comparecimento.
- O arquivo nativo MT restaurou 13 arquivos, com 1.635.287.528 bytes de
  origem. Cada caminho e SHA-256 foi relido depois da restauração pelo
  binário consolidado. O invólucro `urnapack-mt-2026-comprimido.zip` tem
  1.622.423.708 bytes; seu recibo registra todos os membros e o hash real.
  É um recorte MT do trabalho anterior, sem pretensão de cobertura nacional.

## Correções da revisão

O download histórico passa a comparar o sidecar antes de promover o arquivo.
O inventário preserva respostas e referências repetidas; falhas de rede não
se tornam silenciosamente ausência de dataset. A análise histórica conserva
todos os caminhos e membros e reprova contexto divergente, ocorrências
duplicadas, inteiros inválidos, limites e CSV malformado. O baseline observado
não mistura simulações sintéticas aos indicadores eleitorais. Saídas de
análise/conferência exigem destinos novos para preservar tentativas anteriores.

O leitor Rust de análise limita a expansão e interrompe efetivamente a
leitura quando excede o limite de registros. A mudança Brotli 8 → 9 tem teste
de leitura de bytes produzidos pela versão anterior; a fixture sintética
identificada inclui hashes e proveniência reais. As versões revisadas das
automações históricas estão descritas em [historico-v2.md](../spec/historico-v2.md).

## Snapshots históricos distintos

Foram adquiridos e relidos 157 recursos oficiais, incluindo 89 ZIPs de dados
e 68 sidecars. As 90 referências ZIP legadas também foram relidas, sem apagar
aliases. Em 86, o hash coincide com o snapshot recém-adquirido. Nos quatro
restantes, a [comparação de todos os membros](../auditoria/consolidacao/evidencias/zip-legado-vs-atual.json)
mostra que três conservam nomes e bytes internos, embora o ZIP difira.
O CSV de votação MT 2024 difere na ordem dos registros. A conferência dos
622.036 registros completos, incluindo todos os campos e a multiplicidade
de duplicatas, encontrou o mesmo multiconjunto: nenhuma diferença de conteúdo
dos registros. Isso é equivalência semântica sob reordenação, não identidade
dos bytes do CSV. As duas análises e os hashes permanecem preservados.

O arquivo MT 2020 t1 contém quoting incompatível com CSV estrito. A inspeção
aceita 59.082 registros antes do primeiro erro, no registro lógico 59.083;
a linha física do padrão inspecionado é 59.084. Esses números foram medidos,
não fixados no código. O membro permanece reprovado e não foi corrigido para
produzir totais. A reconciliação de senador MT 2018 separa a eleição regular
297 da suplementar 438: na regular, BU e votação por seção somam 3.514.736,
sem diferença nas 7.247 seções comparadas. Somar pleitos distintos gerava a
aparência anterior de incompatibilidade.

A repetição histórica com os 89 ZIPs do catálogo fixado produziu 125 resultados
de membros e um erro, exclusivamente o quoting de 2020 descrito acima.
Seu exit 1 está preservado em `analise-historica-fixada.json`.

## Repetir a partir de um clone

Use uma revisão Git fixa, Rust/Cargo e Python 3.12. Os logs publicados
registram o ambiente efetivo; não são promessa de tempo ou recursos em outra
máquina. Instale as dependências declaradas em um ambiente isolado:

```bash
python3 -m venv /tmp/urnapack-venv
/tmp/urnapack-venv/bin/pip install pyyaml==6.0.2 jsonschema==4.23.0 -r scripts/requirements-compression.txt
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
/tmp/urnapack-venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
/tmp/urnapack-venv/bin/python scripts/validate.py repo --root .
/tmp/urnapack-venv/bin/python scripts/validate.py self-test
```

Destine temporários de testes a um volume com o espaço exigido em
`scripts/limits.env`, definindo `TMPDIR` antes dos comandos. A aquisição
precisa de rede e espaço para o snapshot original; falhar por espaço,
hash divergente ou arquivo ausente é comportamento esperado de proteção.

Para repetir a auditoria nacional completa, siga
[auditoria/2026/README.md](../auditoria/2026/README.md), inclusive o caminho
offline que usa os CSVs comprimidos do release. Para repetir o histórico
fixado, use um diretório de fontes e recibos novos:

```bash
python3 scripts/acquire_2026.py fetch \
  --catalog auditoria/consolidacao/evidencias/catalogo-historico-fixado.json \
  --root /data/urnapack/historico-repeticao/fontes \
  --receipt /data/urnapack/historico-repeticao-fetch.json
python3 scripts/acquire_2026.py verify \
  --catalog auditoria/consolidacao/evidencias/catalogo-historico-fixado.json \
  --root /data/urnapack/historico-repeticao/fontes \
  --receipt /data/urnapack/historico-repeticao-verify.json
python3 scripts/analyze_mt_historico.py \
  --catalog auditoria/consolidacao/evidencias/catalogo-historico-fixado.json \
  --root /data/urnapack/historico-repeticao/fontes \
  --output /data/urnapack/historico-repeticao-analise
```

A análise histórica retorna exit 1 enquanto o membro 2020 permanecer
malformado. Preserve `analysis.json`, `REPORT.md` e o código de saída;
não retire o membro para apresentar uma execução como integralmente aprovada.
As rotinas de inspeção, reconciliação e baseline têm comandos e contratos
em [historico-v2.md](../spec/historico-v2.md).

Para conferir o pacote MT sem baixar o corpus nacional, baixe os assets do
release `consolidacao-2026-v1` em diretório novo e execute:

```bash
sha256sum --check SHA256SUMS-consolidacao-2026
unzip urnapack-mt-2026-comprimido.zip -d mt-pacote
cargo build --release --locked --bin tsepack
target/release/tsepack archive verify --input mt-pacote/forensic-mt
target/release/tsepack restore --dataset mt-pacote/forensic-mt --output mt-restaurado
```

O manifesto interno declara os caminhos e hashes esperados. A igualdade
byte a byte dos arquivos restaurados não autentica a origem eleitoral.
Os resultados descritivos são transformações semânticas com escopo declarado;
compactar suas saídas conserva as saídas, não recupera dados descartados
pela projeção. Os originais e diagnósticos continuam preservados no SSD.
