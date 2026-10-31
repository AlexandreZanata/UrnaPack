# Rotinas históricas MT — revisão v2

A consolidação preserva a implementação anterior no histórico Git e seus
artefatos locais. Esta revisão corrige promoção sem comparar sidecar,
perda de referências por deduplicação, agregações incompletas apresentadas
sem reprovação e repetição de contexto sem conferência. Não reescreve
arquivos originais nem atribui fraude aos diagnósticos.

## Descoberta e aquisição

O inventário anterior `scripts/inventory_mt_2000_2026.json` permanece
preservado. Uma nova descoberta exige destino novo:

```bash
python3 scripts/inventory_mt_historico.py --output /tmp/mt-inventario-novo.json
python3 scripts/fetch_mt_historico.py \
  --inventory scripts/inventory_mt_2000_2026.json \
  --root /data/urnapack/mt-historico-verificado/fontes \
  --catalog-output /tmp/mt-catalogo-novo.json \
  --receipt /tmp/mt-aquisicao-nova.json
```

A descoberta v2 preserva respostas JSON recebidas e seus hashes; HTTP 404
fica separado de falhas de transporte/API, que reprovam. Referências a uma
mesma URL são mantidas. O baixador deriva um catálogo v1 de aquisição,
preservando aliases em `references`, e usa `acquire_2026.py` também para
anos históricos: locks, retomada com validadores, limites centrais,
releitura SHA-256 e comparação com sidecar antes de promover o arquivo.
O destino conserva host/caminho oficial. O corpus legado `brutos/` continua
preservado; sua existência não é usada como aprovação criptográfica.

## Descritiva histórica

```bash
python3 scripts/analyze_mt_historico.py \
  --brutos /data/urnapack/brutos \
  --output /data/urnapack/mt-historico-revisao-nova
```

Para analisar diretamente o novo destino por host/caminho, use `--catalog`
com o catálogo fixado e `--root` com o diretório de fontes, no lugar de
`--brutos`. Cada ZIP é relido e confrontado com tamanho/SHA-256 antes da
agregação. O recibo registra o hash do catálogo e distingue os recursos
não ZIP que ficam fora desta análise. Gere a fixação com `pin_catalog_2026.py`
após uma verificação integral sem erros, como na auditoria nacional.

`analysis.json` tem `format_version=2`, `success`, `errors`, `files` e
`archive_members`. O índice registra todos os membros por ordinal, inclusive
os não interpretados. Arquivos de conteúdo igual continuam relacionados
individualmente. Não há soma geral de votos entre esses arquivos.

Cabeçalho duplicado, largura errada, inteiro inválido/negativo ou excesso de
limite bloqueiam a agregação do membro. Aritmética, duplicatas e contexto
divergente reprovam seus controles. O diagnóstico é preservado e a execução
retorna exit 1; uma execução vazia também reprova. TXT antigo fica catalogado
sem agregação automática. Votos de eleições diferentes não são misturados.
O BU MT 2020 t1 com quoting inválido permanece diagnóstico, sem correção
dos bytes para produzir totais.

## Inspeção e reconciliação

```bash
python3 scripts/inspect_2020_bweb_quoting.py \
  --output /tmp/mt-2020-quoting-novo.json
python3 scripts/reconcile_senado_2018.py --output /tmp/mt-senado-2018-v2-novo.json
```

A inspeção confere CRC ao ler o membro e calcula hashes, offset, linha física,
registros aceitos e ordinal do primeiro erro pelo parser estrito. Não há
contagem de erro fixada no código. Linha física e registro CSV permanecem
distintos. A reconciliação v2 separa eleições, exige campos e inteiros
válidos e rejeita ocorrência duplicada antes de somar.

## Baseline observado

```bash
python3 scripts/model_baseline_mt.py \
  --zip /data/urnapack/brutos/2026/t1/MT/bweb_1t_MT_051020261403.zip \
  --expected-sha256 610eda446fb6bab25f29ceea31adf8f91acf68db14a179228516d11c0fac226f \
  --output /tmp/mt-baseline-v2-novo.json
```

O hash acima é do snapshot real fixado no perfil MT; a ferramenta o relê
dos bytes. A saída v2 conserva apenas os dados observados e a proveniência,
com contadores de seleção e repetição de contexto. Cada ocorrência precisa
ser única; os campos de contexto repetidos devem coincidir. Arquivo alterado,
contexto conflitante, população vazia e aritmética inválida reprovam.

O método continua sendo binomial homogêneo com aproximação normal bilateral
e BH q=0,05. É um baseline descritivo sem modelo suficiente da heterogeneidade
entre seções; flags não são um detector validado de fraude. Casos sintéticos
ficam nos testes e não são publicados como contagens eleitorais observadas.
Nenhum contrato de compressão ou garantia byte a byte foi substituído por
essa transformação semântica.
