# Auditoria das imagens de 2026 — contrato v1

Novo binário `audit_2026`, sem mudança dos formatos de compressão existentes.
Entrada e saída usam `format_version: 1`. O binário não é uma implementação
genérica do subcomando `tsepack audit` e não verifica assinatura digital.

## Universo e entrada

- `--manifest`: JSON com `format_version` e `inputs`; campos desconhecidos
  reprovados por serde. Cada membro tem `path`, `sha256`, `bytes`, `uf`,
  `zip_sha256`, `zip_url`, `member`.
- `scripts/prepare_audit_2026.py` exige as 27 UFs e ZZ; verifica SHA-256 do ZIP
  contra seu recibo e SHA-512 contra o sidecar oficial; exige um CSV por ZIP,
  preserva o inventário de todos os outros membros e o dicionário oficial.
- O binário verifica o SHA-256 e o tamanho dos bytes efetivamente lidos pelo
  parser, na mesma passagem. Duplicata de UF no manifesto é erro. Um manifesto
  parcial pode ser usado para diagnóstico; o confronto nacional exige 28
  abrangências explícitas, nunca presume completude a partir do nome do arquivo.
- CSV de bytes Latin-1, separador `;`, cabeçalho de 45 campos reutilizado de
  `src/bweb.rs`. Textos de nomes não são recodificados para agregação.
- Ano=2026, turno=2, UF igual à entrada. Presidente: cargo=1, pleito=3221,
  eleição=6258. Registros de outros cargos são contados em
  `excluded_records_by_cargo` e não somados ao eleitorado presidencial.

## Controles

Chave: ano/pleito/eleição/turno/UF/município/zona/seção/cargo. Votáveis
13/22 nominais, 95 brancos, 96 nulos; outras categorias reprovadas. Ocorrência
repetida seção/votável reprova; contexto repetido divergente reprova. Nenhum
registro é deduplicado. Aptos=comparecimento+abstenções; biometria não
habilitada <= comparecimento; soma de todos os votos do cargo=comparecimento.
Limites são lidos exclusivamente de `scripts/limits.env`.
Contagens individuais de seção são inteiros u32; acumuladores nacionais são
u64. Identificadores numéricos são validados sem retirar zeros à esquerda.
Essa validação de identificadores ocorre dentro do recorte presidencial;
sentinelas de outros cargos, como `CD_CARGO_PERGUNTA=-1`, são contadas no
universo excluído antes dessa validação, sem perder o registro original.

## Agregações

Eleitorado e biometria são somados uma vez por seção/cargo, apesar de repetidos
nas linhas de candidatos. Percentual nominal: votos/(votos13+votos22).
Seções sem válidos são contadas separadamente e não classificadas como unânimes.
Mais de 90% usa `10*votos > 9*válidos`; 90% ou mais usa `>=` separadamente.

Horários são lexicais, sem inferir fuso a partir da UF. O relatório publica
cenários de fronteira ao segundo e ao minuto: até 17:00:00, até 17:00:59,
17:01:00–17:15:59, 17:16:00–18:59:59, >=19:00:00 e >19:00:00. Vazio,
`#NULO#` e `#NE#` são contados como encerramento ausente; não entram nas janelas,
mas permanecem nos totais. Outras datas/horas inesperadas reprovam.

`--time-policy` acrescenta `normalized_closing` sem alterar os recortes
lexicais. O hash da política é calculado dos bytes, a regra usa códigos
municipais com exceções antes do padrão da UF, e ZZ fica separado. Cortes
ao segundo e ao minuto são publicados em paralelo. Hora ausente permanece
contada. Trata-se de relógio nominal, não de prova de sincronização nem do
instante de cada voto. Sem essa opção, a saída anterior permanece igual.

Pearson e Spearman: x=biometria não habilitada/comparecimento e
y=votos13/válidos, entre seções com denominadores positivos; sem pesos.
Spearman usa postos médios nos empates. Pearson adicional usa desvios das
médias de x/y por UF/município, sem alegação de controle causal. Variância zero
gera `null`, não r=0. Ordem estável das chaves garante reprodutibilidade.
Sem p-valores, pois desenho amostral/modelo causal não foram estabelecidos.

Benford: histogramas do primeiro dígito dos votos nominais positivos por
candidato e probabilidades teóricas `log10(1+1/d)`. Zeros não têm primeiro
dígito significativo. Não há teste de fraude nem p-valor inferencial.

## Saída e falhas

JSON contém fontes, controles implícitos na aceitação, totais, UFs, janelas,
extremos, correlações, histogramas e limitações. Saída preexistente não é
sobrescrita. Qualquer falha de integridade, layout, universo ou controle gera
exit diferente de zero, sem publicar relatório de sucesso.
As saídas são escritas em parcial, sincronizadas e publicadas sem sobrescrever
destino existente. Falha de escrita preserva o parcial sem criar um final.

`--sections-output` exporta uma projeção semântica CSV v1 de uma linha por
seção presidencial, ordenada pela chave: identificadores da chave original,
local, número da urna, encerramento original, tipo de urna, aptos,
comparecimento, abstenções, contagem biométrica e votos 13/22/brancos/nulos.
Categoria ausente tem zero nesta projeção, após verificar que a soma de todos
os votos do cargo iguala comparecimento. Não é restauração do CSV original.
O recibo externo registra bytes/SHA-256 e o manifesto de fontes utilizado.
`scripts/reconcile_coverage_2026.py` confere esse hash e relê o CSV ZZ original
com seu hash para localizar sentinelas; exige chaves distintas e concilia
seções instaladas, aptos e abstenções com o JSON nacional. Zeros à esquerda
são normalizados apenas para a junção semântica, com colisões reprovadas.

`scripts/check_audit_2026.py` confronta categorias e comparecimento com o JSON
oficial de totalização. Divergência com totalização é erro; divergência com
uma afirmação das imagens é registrada como resultado, sem ajustar o cálculo
para produzir concordância.

## Aquisição, preservação e escopo

`scripts/acquire_2026.py` cria catálogo v1 da resposta completa CKAN q=2026,
conserva aliases de URL e exclusões de outros anos. A descoberta não abrange
automaticamente todos os objetos de DivulgaCand, PJe ou outros sistemas.
Recibos v1 registram HTTP, bytes, SHA-256/SHA-512/SHA-1 e confronto com sidecar
quando listado. Hash local não equivale a assinatura/autoria. `Last-Modified`
não prova instante de primeira publicação. HEAD sem Content-Length gera
limitação explícita. Retomada exige tamanho, ETag/Last-Modified e Content-Range
coerentes. Lock por destino impede escrita simultânea. Parciais nunca são
promovidos como completos antes da releitura e verificações; falhas não apagam
os bytes. Respostas e recibos anteriores permanecem como histórico de tentativas.
O catálogo fixado acrescenta `expected_bytes` e `expected_sha256`, derivados
de uma verificação concluída sem erros e com exatamente as URLs do catálogo.
Ambos são obrigatórios quando qualquer um aparece. Arquivo local divergente
reprova; download divergente permanece parcial e não é promovido. A fixação
não verifica autoria/assinatura, mas impede aceitar outro snapshot na mesma URL.
