# Mapa dos dados brutos — MT como referência inicial

## Escopo e nível de evidência

Mapa estrutural inicial conferido em 28/10/2026 nos ZIPs já baixados de MT:
leitura do diretório central, cabeçalhos CSV completos e leia-mes internos.
Amostras de registros e de assinaturas de formato não validam o arquivo inteiro.
Este mapa não demonstra cobertura completa de MT ou do Brasil, unicidade de
chaves, interpretação ASN.1 nem validade das assinaturas eleitorais.

A Etapa 1 (`docs/ETAPA-1.md`) gerou o inventário reproduzível e os perfis
completos dos CSVs em 28/10/2026 (execução em MT, `relatorios-locais/etapa-1/mt/`,
com `map.json`, `members.jsonl`, `report.md` e `run.json`). Números de arquivos,
bytes e hashes da instalação ficam nos relatórios locais, calculados dos objetos;
não copiar inventários desatualizados para constantes, testes ou configurações
nacionais. As contagens de registros lógicos e os conjuntos de escopo abaixo são
evidência estrutural dessa execução (gerações examinadas, não o universo nacional);
hashes e tamanhos por arquivo estão somente nos relatórios locais.

## Organização e localização

O acesso local parte de `dados/brutos/<ano>/t<turno>/<abrangencia>/`, com `dados`
podendo ser um link de raiz legítimo. O manifesto de origem local disponível
está em `dados/manifest-2026-mt.json`. Caminhos físicos da máquina ficam fora
da documentação versionada e são passados por parâmetro.

Preservar o nome oficial dos downloads e todas as versões. Pastas e nomes são
pistas de aquisição; não determinam necessariamente o escopo de cada membro.
Distinguir `collection_round_hint`, derivado da localização, de `observed_rounds`,
extraídos do conteúdo ou de metadados documentais verificados. Não mover arquivos
brutos para ajustar uma classificação descoberta posteriormente.

**Caso observado:** o ZIP `Relatorio_Resultado_Totalizacao_2026_MT.zip`, guardado
junto do primeiro turno, contém PDFs com nomes de primeiro e segundo turnos.
A leitura da capa do membro `6258_MT_MATO-GROSSO_2026_T2_PRESIDENTE.pdf` confirma
segundo turno. Isso não fornece BU/RDV/logs por seção do segundo turno.

O catálogo nacional deve distinguir UF, abrangência nacional, exterior e outros
códigos oficiais conforme a fonte. Os leia-mes CSV examinados mencionam `BR`,
`ZZ` e `VT`; não tratá-los como UFs civis ou descartar registros por essa razão.

## Famílias observadas

### BU web — `bweb_<turno>_<UF>_<geracao>.zip`

Membros observados: CSV `bweb_...csv` e `_leiame-boletimurnaweb.pdf`.
Cabeçalho observado: 45 campos, listado adiante. Há contexto da seção/urna/cargo
repetido nas linhas por votável. Candidato, legenda, branco e nulo precisam de
categorias oficiais próprias, sem reduzir a tabela a candidatos nominais.

- Unidade da linha a validar: ocorrência de votação por seção/cargo/votável,
  com contexto e identificação eleitoral; não presumir chave única global.
- Contexto: aptos, comparecimento, abstenções, urna efetivada, carga, horários,
  seções agregadas, junta/turma e biometria.
- Chave candidata de contexto: snapshot + eleição/pleito + turno + abrangência
  + município TSE + zona + seção + cargo/pergunta. Confirmar significados e
  situações especiais antes de impor unicidade ou reduzir contexto.
- Quantidade de votos é medida por votável. Aptos/comparecimento não são
  aditivos por linha de votável. Igualdade do contexto precisa ser testada.
- `DS_SECOES_AGREGADAS` é lista textual; manter a forma original e, futuramente,
  vínculos explícitos com a seção principal sem contagem territorial duplicada.

### Correspondência esperada — `CESP_<turno>_<UF>_<geracao>.zip`

Contém **duas famílias CSV diferentes**, acompanhadas de seus leia-mes:

- `csec_...csv`: correspondência esperada de seção, 21 campos observados;
- `ccont_...csv`: contingência, 19 campos observados; não contém `NR_SECAO`
  nem `NR_LOCAL_VOTACAO` no cabeçalho examinado.

Não inventar seção para contingência ou usar o mesmo esquema/chave para ambas.
As gerações de CESP são snapshots preservados; não concatenar versões como se
fossem ocorrências novas nem apagar versões para montar uma visão atual.
Os exemplares t1/t2 examinados têm os mesmos cabeçalhos por família; isso não
prova que todos os anos/UFs/gerações os manterão.

### Correspondência efetivada — `CEFT_<turno>_<UF>_<geracao>.zip`

CSV `ceft_...csv`, com 36 campos observados, e
`leiame-corresp-efetivada.pdf`. Inclui urnas/cargas esperadas e efetivadas,
sequenciais de correspondência, recebimento, origem do voto e divergência.
Esperada e efetivada não são valores intercambiáveis; não inferir substituição
ou anomalia apenas da diferença sem interpretar a categoria e o contexto.

### Votação por seção — `votacao_secao_<ano>_<abrangencia>.zip`

CSV homônimo e `leiame.pdf`; 26 campos observados. É uma fonte de totalização,
a reconciliar com o BU conforme as definições oficiais, sem assumir identidade
semântica por semelhança de nomes. O nome não contém turno: a Etapa 1 deve ler
`NR_TURNO`/`CD_ELEICAO` de todos os registros para documentar o escopo observado.

`CD_CARGO` nesta família e `CD_CARGO_PERGUNTA` no BU web exigem correspondência
validada. `SQ_CANDIDATO`, `SG_UE`, local e endereço são campos a preservar;
não removê-los por não serem usados na primeira análise.

### Arquivos da urna — `bu_imgbu_logjez_rdv_vscmr_<ano>_<turno>_<UF>.zip`

Na listagem examinada, os membros seguem famílias de nomes:

- `o<identificacao>-bu.dat`: BU binário;
- `o<identificacao>-rdv.dat`: RDV binário;
- `o<identificacao>-imgbu.dat`: representação/spool do BU;
- `o<identificacao>-log.jez`: contêiner de log;
- `o<identificacao>-vota.vsc`: assinatura;
- `leiame.pdf`: documentação, também preservada.

Evidência da execução de 28/10/2026 (`relatorios-locais/etapa-1/mt/`): o contêiner
tem 41.436 membros no diretório central = 1 `leiame.pdf` + 8.287 blocos de
(bu.dat, rdv.dat, imgbu.dat, log.jez, vota.vsc), ou seja, 8.287 de cada tipo
(24.861 `.dat` no total). Amostras de formato mágico (primeira ocorrência por
família, leitura limitada, sem decoder novo): `bu.dat`/`rdv.dat`/`imgbu.dat`/`vsc`
opacos com magia `30 82 …` (DER/ASN.1 presumido por magia — hipótese, sem parser);
`log.jez` com magia ZIP `50 4b 03 04` e membro interno `logd.dat` (aninhamento
pendente, não expandido). Demais membros opacos catalogados como `metadata_only`.

A segmentação de `<identificacao>` em pleito/UF/município/zona/seção é hipótese
até confronto com especificação da versão e conteúdo. Não inferir todo o
universo de seções apenas pela contagem de sufixos ou apenas pelo prefixo.
Não tratar `.dat` como texto ou imagem genérica pela extensão.

**Contêiner de log:** a amostra examinada de `.jez` começa com assinatura ZIP
(`50 4b 03 04`) e contém `logd.dat` textual. O leia-me descreve empacotamento 7z
e possível aninhamento. Registrar essa diferença entre descrição e observação;
identificar formato por assinatura e versão, sem escolher decoder só pela extensão.
O mapeamento externo não deve alegar validação completa dos logs aninhados.

BU/RDV/assinatura exigem especificação ASN.1 e material oficial correspondente
antes do parser de produção. Não converter posição no RDV em ordem de votação
ou identidade de eleitor. A Etapa 1 cataloga esses membros como opacos e registra
amostras de formato, sem decodificação eleitoral nem nova dependência para 7z.

### Relatório de totalização — `Relatorio_Resultado_Totalizacao_<ano>_<UF>.zip`

Membros PDF observados no exemplar de MT: relatórios federais T1 e T2,
relatório estadual T1 e `_leiame.pdf`. Preservar cada PDF como evidência.
Não converter PDF em tabela numérica por extração de texto sem validação de
layout e totais; essa extração fica fora da Etapa 1.

### Sidecars de integridade

Arquivos `.sha512` são objetos de proveniência, não registros de votação.
Conferir os bytes do objeto referenciado quando o sidecar existir. Conservar
SHA-256 local e evidência de autoria separadamente. A falta de sidecar não
significa ausência de dados nem autoriza declarar assinatura verificada.

## CSV: regras de leitura e documentação

Os leia-mes internos do BU web, votação por seção e correspondências examinados
declaram Latin-1 e separador `;`. Usar parser CSV real com aspas e preservação
de linhas/ordinais; não usar `split(';')`, inferência automática de tipos ou
substituição de caracteres inválidos. O contrato por fonte prevalece sobre
heurística. Latin-1 é a declaração documental, não conclusão obtida por tentar
decodificar uma pequena amostra como Windows-1252.

Os leia-mes descrevem branco no banco como `#NULO`/`-1` e informação não
registrada como `#NE`/`-3`. A amostra também contém grafia `#NULO#`. Contar e
preservar as grafias realmente encontradas, por coluna; não normalizá-las ou
confundi-las com vazio, zero e ausência. Valores desconhecidos exigem avaliação.

Registrar por layout: cabeçalho completo em ordem, número de campos, regra de
quoting/escape, codificação declarada e evidência, finais de linha observados,
quantidade de registros lidos e campos divergentes. Um registro CSV pode ocupar
mais de uma linha física; ordinal do registro e linha física são localizadores
diferentes. Hash de cabeçalho é fingerprint de layout, não hash do membro inteiro.

Os cabeçalhos abaixo foram lidos dos membros reais. Descrevem observações desta
versão; o agente deve comparar cada membro, conservar variantes e nunca usar o
número de campos sozinho para reconhecer um layout.

### Cabeçalho observado: ceft

```text
DT_GERACAO
HH_GERACAO
AA_ELEICAO
DT_PLEITO
CD_PLEITO
SG_UF
CD_MUNICIPIO
NM_MUNICIPIO
NR_ZONA
NR_SECAO
NR_LOCAL_VOTACAO
SQ_CORRESPONDENCIA_ESPERADA
NR_URNA_ESPERADA
CD_CARGA_URNA_ESPERADA
CD_CARGA_1_URNA_ESPERADA
CD_CARGA_2_URNA_ESPERADA
CD_FLASHCARD_URNA_ESPERADA
DT_CARGA_URNA_ESPERADA
DT_RECBTO_URNA_ESPERADA
SQ_CORRESPONDENCIA_EFETIVADA
NR_URNA_EFETIVADA
CD_CARGA_URNA_EFETIVADA
CD_CARGA_1_URNA_EFETIVADA
CD_CARGA_2_URNA_EFETIVADA
CD_FLASHCARD_URNA_EFETIVADA
DT_CARGA_URNA_EFETIVADA
DT_RECBTO_URNA_EFETIVADA
CD_ORIGEM_VOTO
DS_ORIGEM_VOTO
TP_DIVERGENCIA
NM_MAQUINA_GERACAO_MIDIA
NR_SRI_TPM_GERACAO_MIDIA
NR_SRI_INSTAL_GERACAO_MIDIA
NM_MAQUINA_TRANSM_CORRESP
NR_SRI_TPM_TRANSM_CORRESP
NR_SRI_INSTAL_TRANSM_CORRESP
```

### Cabeçalho observado: csec

```text
DT_GERACAO
HH_GERACAO
AA_ELEICAO
CD_PLEITO
SG_UF
CD_MUNICIPIO
NM_MUNICIPIO
NR_ZONA
NR_SECAO
NR_LOCAL_VOTACAO
NR_URNA_ESPERADA
CD_CARGA_URNA_ESPERADA
CD_FLASHCARD_URNA_ESPERADA
DT_CARGA_URNA_ESPERADA
ST_CORRESP_ALTERADA
NM_MAQUINA_GERACAO_MIDIA
NR_SRI_TPM_GERACAO_MIDIA
NR_SRI_INSTAL_GERACAO_MIDIA
NM_MAQUINA_TRANSM_CORRESP
NR_SRI_TPM_TRANSM_CORRESP
NR_SRI_INSTAL_TRANSM_CORRESP
```

### Cabeçalho observado: ccont

```text
DT_GERACAO
HH_GERACAO
AA_ELEICAO
CD_PLEITO
SG_UF
CD_MUNICIPIO
NM_MUNICIPIO
NR_ZONA
NR_URNA_ESPERADA
CD_CARGA_URNA_ESPERADA
CD_FLASHCARD_URNA_ESPERADA
DT_CARGA_URNA_ESPERADA
ST_CORRESP_ALTERADA
NM_MAQUINA_GERACAO_MIDIA
NR_SRI_TPM_GERACAO_MIDIA
NR_SRI_INSTAL_GERACAO_MIDIA
NM_MAQUINA_TRANSM_CORRESP
NR_SRI_TPM_TRANSM_CORRESP
NR_SRI_INSTAL_TRANSM_CORRESP
```

### Cabeçalho observado: bweb

```text
DT_GERACAO
HH_GERACAO
ANO_ELEICAO
CD_TIPO_ELEICAO
NM_TIPO_ELEICAO
CD_PLEITO
DT_PLEITO
NR_TURNO
CD_ELEICAO
DS_ELEICAO
SG_UF
CD_MUNICIPIO
NM_MUNICIPIO
NR_ZONA
NR_SECAO
NR_LOCAL_VOTACAO
CD_CARGO_PERGUNTA
DS_CARGO_PERGUNTA
NR_PARTIDO
SG_PARTIDO
NM_PARTIDO
DT_BU_RECEBIDO
QT_APTOS
QT_COMPARECIMENTO
QT_ABSTENCOES
CD_TIPO_URNA
DS_TIPO_URNA
CD_TIPO_VOTAVEL
DS_TIPO_VOTAVEL
NR_VOTAVEL
NM_VOTAVEL
QT_VOTOS
NR_URNA_EFETIVADA
CD_CARGA_1_URNA_EFETIVADA
CD_CARGA_2_URNA_EFETIVADA
CD_FLASHCARD_URNA_EFETIVADA
DT_CARGA_URNA_EFETIVADA
DS_CARGO_PERGUNTA_SECAO
DS_SECOES_AGREGADAS
DT_ABERTURA
DT_ENCERRAMENTO
QT_ELEI_BIOM_SEM_HABILITACAO
DT_EMISSAO_BU
NR_JUNTA_APURADORA
NR_TURMA_APURADORA
```

### Cabeçalho observado: votacao

```text
DT_GERACAO
HH_GERACAO
ANO_ELEICAO
CD_TIPO_ELEICAO
NM_TIPO_ELEICAO
NR_TURNO
CD_ELEICAO
DS_ELEICAO
DT_ELEICAO
TP_ABRANGENCIA
SG_UF
SG_UE
NM_UE
CD_MUNICIPIO
NM_MUNICIPIO
NR_ZONA
NR_SECAO
CD_CARGO
DS_CARGO
NR_VOTAVEL
NM_VOTAVEL
QT_VOTOS
NR_LOCAL_VOTACAO
SQ_CANDIDATO
NM_LOCAL_VOTACAO
DS_LOCAL_VOTACAO_ENDERECO
```

## Contrato do catálogo reutilizável na escala nacional

Para cada execução, documentar e gerar em formato legível por máquina:

- raiz lógica relativa, ambiente, ano/abrangência solicitados, commit/ferramenta,
  versão do mapa, parâmetros e limites efetivamente usados;
- download: caminho relativo, tamanho medido, SHA-256 dos bytes, URL quando
  houver evidência, hash/assinatura oficial disponível e seus estados separados;
- membro: hash do download + ordinal do diretório central + nome completo,
  flags e método ZIP, tamanhos/CRC declarados, tipo observado e nível de leitura;
- integridade de membro: hash somente se calculado dos bytes completos;
  `metadata_only`, `sampled` e `fully_read` são estados distintos. CRC não
  substitui SHA-256 nem prova autoria;
- CSV: família/variante, cabeçalho ordenado, fingerprint definido, contagem de
  registros realmente lidos, escopos observados e sentinelas lexicais por coluna;
- dicionário semântico: significado, fonte documental/versão, tipo candidato,
  domínio/sentinelas, unidade, chave candidata e regras de soma/join. Distinguir
  `documented`, `observed`, `hypothesis` e `verified`;
- cobertura: solicitado, encontrado, lido, interpretado e apto a cada uso;
  lacunas e escopos mistos sem preencher ausentes com dados de outro turno;
- contêineres aninhados, esquemas desconhecidos, duplicatas de nomes/cabeçalhos,
  caminhos perigosos, arquivos vazios e erros identificados explicitamente.

O membro é identificado por ordinal mesmo se nomes repetirem; uma ferramenta
que não suporte a ambiguidade deve reprovar, nunca escolher o primeiro ou o último.
A Etapa 1 não extrai arquivos controlados pelo ZIP para caminhos no disco.

Para novo ano/UF/abrangência: reexecutar descoberta → comparar fingerprints e
nomes → catalogar variantes → consultar leiaute → validar chaves/escopo → só
então habilitar adaptador de transformação. MT é a referência inicial; diferenças
exigem evidência e testes, não exceções codificadas apenas pelo nome da UF.

## Fontes de documentação examinadas

Leia-mes preservados dentro dos ZIPs originais: `_leiame-boletimurnaweb.pdf`,
`leiame-corresp-esperada-secao.pdf`, `leiame-corresp-esperada-contingencia.pdf`,
`leiame-corresp-efetivada.pdf`, `leiame.pdf` de votação/arquivos da urna e
`_leiame.pdf` de relatórios. O catálogo gerado deve vinculá-los ao hash do
contêiner e ao ordinal/nome do membro, evitando confundir PDFs homônimos.

Documentação externa para a etapa de interpretação deve ser arquivada ou
referenciada por versão e hash, incluindo ASN.1, formato de log e instruções
oficiais de aquisição. Não aplicar leiaute antigo a 2026 sem confronto.

## Evidência da execução reproduzível (MT, 28/10/2026)

Mapeador `scripts/map_raw_data.py` executado sobre as gerações locais de MT
(`--year 2026 --scope MT`), com limites de `scripts/limits.env`. Artefatos
locais (não versionados): `relatorios-locais/etapa-1/mt/map.json`,
`members.jsonl`, `report.md`, `run.json`. Repetição byte a byte confirmada
para `map.json` e `members.jsonl`. Inventário físico: 13 arquivos (8 ZIPs +
5 sidecars `.sha512`); membros catalogados: 41.458 (9 CSVs + 41.449 opacos,
0 diretórios). Diagnóstico vazio (estado `complete`).

Registros lógicos lidos integralmente em streaming (parser csv real, Latin-1,
`;`), com SHA-256 do membro calculado dos bytes completos e fingerprint de
layout = SHA-256 do JSON UTF-8 do array ordenado de nomes
(`ensure_ascii=False`, separadores `(',', ':')`, sem newline):

| CSV (geração) | Família | Registros | Fingerprint do cabeçalho |
|---|---|---:|---|
| `ceft_1t_MT_051020261049.csv` | ceft | 8.287 | `5697514c3c693c23…` |
| `csec_1t_MT_031020261534.csv` | csec | 8.287 | `124f979553c16348…` |
| `ccont_1t_MT_031020261534.csv` | ccont | 1.240 | `280c7c40805a06c1…` |
| `csec_1t_MT_041020261259.csv` | csec | 8.286 | `124f979553c16348…` |
| `ccont_1t_MT_041020261259.csv` | ccont | 1.270 | `280c7c40805a06c1…` |
| `bweb_1t_MT_051020261403.csv` | bweb | 891.997 | `c93ec8fe8f0ad340…` |
| `votacao_secao_2026_MT.csv` | votacao | 831.247 | `329ec2ffb444554c…` |
| `csec_2t_MT_241020261231.csv` | csec | 8.286 | `124f979553c16348…` |
| `ccont_2t_MT_241020261231.csv` | ccont | 1.246 | `280c7c40805a06c1…` |

Diferenças observadas (evidência, não conclusão nacional):

- BU web contém **dois pleitos/eleições no mesmo CSV de turno 1**: `CD_ELEICAO`
  6257 (`Eleição Geral Federal 2026`, `CD_CARGO_PERGUNTA` 1 = Presidente,
  60.750 linhas) + 6259 (`Eleições Gerais Estaduais 2026`, 831.247 linhas).
  `NR_TURNO` = 1 em todas as linhas; `CD_PLEITO` = 3220.
- Votação por seção contém **só a eleição 6259** (831.247 linhas = mesmo total
  do recorte 6259 do BU web; igualdade de totais ≠ equivalência de registros —
  reconciliação pendente). `CD_TIPO_ELEICAO` = 2 na votação vs 0 no BU web
  (códigos por fonte, sem identidade presumida); `TP_ABRANGENCIA` = E;
  `CD_CARGO` 3/5/6/7 (sem Presidente).
- CESP tem **duas gerações t1 preservadas como snapshots** (pleito 3220):
  03/10 com csec 8.287 + ccont 1.240 e `ST_CORRESP_ALTERADA` = `*` em tudo;
  04/10 com csec 8.286 + ccont 1.270 e `ST_CORRESP_ALTERADA` = `N` (8.280) +
  `S` (6). Geração t2 (pleito 3221): csec 8.286 + ccont 1.246, tudo `*`.
  Não concatenar gerações como série; não apagar versões.
- CEFT (pleito 3220): 8.287 linhas; `TP_DIVERGENCIA` = vazio em 8.252 e `C`
  em 35 (leitura lexical; semântica de `C`/vazio pendente).
- Sentinelas lexicais contadas por coluna (conjunto
  `{#NULO, #NULO#, #NE, -1, -3, ""}`, sem normalização): BU web
  `DS_SECOES_AGREGADAS` = `#NULO#` em 830.764, `NM/SG_PARTIDO` = `#NULO#` e
  `NR_PARTIDO` = `-1` em 80.721, `NR_JUNTA_APURADORA`/`NR_TURMA_APURADORA` =
  `-1` em todas as 891.997; votação `SQ_CANDIDATO` = `-1` em 65.506 e `-3` em
  87.415 (hipótese: branco/não-registrado — a confirmar no leia-me, sem
  confundir com vazio/zero); CEFT `TP_DIVERGENCIA` vazio acima; csec/ccont sem
  ocorrências desse conjunto nesta execução (`ST_CORRESP_ALTERADA` usa
  `*`/`N`/`S`, fora do conjunto — valores preservados, semântica pendente).
- Escopos observados agregados: ano 2026; turnos só `1`; pleitos 3220/3221;
  `SG_UF`/`SG_UE` só MT; `CD_TIPO_ELEICAO` 0 (bweb) e 2 (votação);
  cargos estaduais 3/5/6/7 + 1 (Presidente, só bweb). Divergências de recorte
  (ex.: t2 presente só em CESP/relatórios) documentadas sem descarte.
- Relatórios: ZIP com membros `stored` (sem compressão declarada),
  incluindo `6258_…_T2_PRESIDENTE.pdf` sob a pasta t1 — pasta não prova turno
  dos membros; capa confirma T2 só para aquele PDF. Não equivale a BU/RDV/logs
  de t2 por seção (ausentes no acervo examinado).

## Dicionário estrutural por campo (observado em MT, 28/10/2026)

Legenda: `observed` = lido do conteúdo/central nesta execução; `documented` =
leia-me/contrato citado neste mapa; `hypothesis` = inferência por nome, sem
confronto — não usar como esquema canônico. Tipo candidato padrão: texto
lexical Latin-1 preservado, sem cast/normalização. Unidade `—` = sem unidade
aplicável. Chaves: candidatas, não verificadas (unicidade exige Etapa 2).
Sentinelas referem-se ao conjunto contado acima; ausência = nenhuma ocorrência
desse conjunto nesta execução (outros valores atípicos seguem preservados).
Evidência completa por membro em `relatorios-locais/etapa-1/mt/`.

### bweb (45 campos, fingerprint `c93ec8fe8f0ad340…`, 891.997 registros)

| Pos | Campo | Significado (status) | Tipo/unidade | Sentinelas observadas | Chave/join candidata | Evidência | Pendência |
|---:|---|---|---|---|---|---|---|
| 1 | DT_GERACAO | data de geração do extrato (documented) | texto, data `DD/MM/AAAA` | — | parte do snapshot | observed+documented | formato/fuso a formalizar |
| 2 | HH_GERACAO | hora de geração (documented) | texto, hora | — | parte do snapshot | observed+documented | fuso a formalizar |
| 3 | ANO_ELEICAO | ano eleitoral (documented) | texto; obs: só `2026` | — | escopo | observed | — |
| 4 | CD_TIPO_ELEICAO | código do tipo de eleição (hypothesis) | texto; obs: só `0` | — | escopo (por fonte) | observed | tabela oficial pendente; difere da votação (=2) |
| 5 | NM_TIPO_ELEICAO | nome do tipo (documented) | texto; obs: `Eleição Ordinária` | — | — | observed | — |
| 6 | CD_PLEITO | código do pleito (documented) | texto; obs: `3220` | — | escopo | observed | tabela de pleitos pendente |
| 7 | DT_PLEITO | data do pleito (documented) | texto; obs: `2026-10-04 00:00:00` | — | — | observed | fuso/formato a formalizar |
| 8 | NR_TURNO | turno (documented) | texto; obs: só `1` | — | escopo | observed | t2 ausente neste CSV |
| 9 | CD_ELEICAO | código da eleição (documented) | texto; obs: `6257`/`6259` | — | escopo+join p/ votação | observed | semântica 6257×6259 = hipótese razoável, validar |
| 10 | DS_ELEICAO | descrição da eleição (documented) | texto; 2 valores | — | — | observed | — |
| 11 | SG_UF | UF (documented) | texto; obs: só `MT` | — | escopo | observed | `BR`/`ZZ`/`VT` não aparecem aqui |
| 12 | CD_MUNICIPIO | código TSE do município (documented) | texto | — | parte da chave de contexto | observed | tabela oficial pendente |
| 13 | NM_MUNICIPIO | nome do município (documented) | texto | — | — | observed | acentos preservados em Latin-1 |
| 14 | NR_ZONA | zona (documented) | texto | — | parte da chave de contexto | observed | zeros significativos preservados |
| 15 | NR_SECAO | seção (documented) | texto | — | parte da chave de contexto | observed | — |
| 16 | NR_LOCAL_VOTACAO | local de votação (documented) | texto | — | parte da chave | observed | — |
| 17 | CD_CARGO_PERGUNTA | código cargo/pergunta (documented) | texto; obs: 1/3/5/6/7 | — | escopo+candidato a chave | observed | tabela cargos×eleição pendente |
| 18 | DS_CARGO_PERGUNTA | descrição cargo/pergunta (documented) | texto; 5 valores | — | — | observed | — |
| 19 | NR_PARTIDO | número do partido (documented) | texto | `-1` em 80.721 (hipótese: sem partido) | — | observed | semântica de `-1` a confirmar |
| 20 | SG_PARTIDO | sigla (documented) | texto | `#NULO#` em 80.721 | — | observed | grafia preservada, sem normalizar |
| 21 | NM_PARTIDO | nome (documented) | texto | `#NULO#` em 80.721 | — | observed | — |
| 22 | DT_BU_RECEBIDO | recebimento do BU (documented) | texto, data/hora | — | — | observed | formato/fuso a formalizar |
| 23 | QT_APTOS | eleitores aptos (documented) | texto numérico; medida de contexto | — | NÃO somar por votável | observed+documented | igualdade do contexto por seção/cargo a testar |
| 24 | QT_COMPARECIMENTO | comparecimento (documented) | texto numérico; contexto | — | NÃO somar por votável | observed+documented | idem |
| 25 | QT_ABSTENCOES | abstenções (documented) | texto numérico; contexto | — | NÃO somar por votável | observed+documented | idem |
| 26 | CD_TIPO_URNA | código tipo de urna (hypothesis) | texto | — | — | observed | tabela pendente |
| 27 | DS_TIPO_URNA | descrição tipo de urna (hypothesis) | texto | — | — | observed | — |
| 28 | CD_TIPO_VOTAVEL | código tipo do votável (documented) | texto | — | categoria oficial | observed | categorias (nominal/legenda/branco/nulo) a formalizar |
| 29 | DS_TIPO_VOTAVEL | descrição tipo do votável (documented) | texto | — | — | observed | — |
| 30 | NR_VOTAVEL | número do votável (documented) | texto | — | parte da ocorrência | observed | sentinelas de branco/nulo por categoria a mapear |
| 31 | NM_VOTAVEL | nome do votável (documented) | texto | — | — | observed | grafias `#NULO`/`#NE` citadas em leia-me; contagem por coluna pendente p/ Etapa 2 |
| 32 | QT_VOTOS | votos do votável (documented) | texto numérico; medida | — | somável por votável, não por contexto | observed+documented | — |
| 33 | NR_URNA_EFETIVADA | urna efetivada (documented) | texto | — | join c/ correspondências (hipótese) | observed | validação de join pendente |
| 34 | CD_CARGA_1_URNA_EFETIVADA | carga 1 (hypothesis) | texto | — | — | observed | semântica pendente |
| 35 | CD_CARGA_2_URNA_EFETIVADA | carga 2 (hypothesis) | texto | — | — | observed | — |
| 36 | CD_FLASHCARD_URNA_EFETIVADA | flashcard (hypothesis) | texto | — | — | observed | — |
| 37 | DT_CARGA_URNA_EFETIVADA | data da carga (hypothesis) | texto | — | — | observed | formato a formalizar |
| 38 | DS_CARGO_PERGUNTA_SECAO | cargo por seção (hypothesis) | texto | — | — | observed | relação c/ campo 17 pendente |
| 39 | DS_SECOES_AGREGADAS | lista textual de agregadas (documented) | texto, lista | `#NULO#` em 830.764 | NÃO contar como território duplicado | observed+documented | parser da lista é Etapa 2+ |
| 40 | DT_ABERTURA | abertura (hypothesis) | texto | — | — | observed | — |
| 41 | DT_ENCERRAMENTO | encerramento (hypothesis) | texto | — | — | observed | — |
| 42 | QT_ELEI_BIOM_SEM_HABILITACAO | biometria sem habilitação (hypothesis) | texto numérico | — | — | observed | semântica pendente |
| 43 | DT_EMISSAO_BU | emissão do BU (documented) | texto | — | — | observed | — |
| 44 | NR_JUNTA_APURADORA | junta (hypothesis) | texto | `-1` em todas | — | observed | semântica de `-1` pendente |
| 45 | NR_TURMA_APURADORA | turma (hypothesis) | texto | `-1` em todas | — | observed | — |

### votacao (26 campos, fingerprint `329ec2ffb444554c…`, 831.247 registros, só eleição 6259)

| Pos | Campo | Significado (status) | Tipo/unidade | Sentinelas observadas | Chave/join candidata | Evidência | Pendência |
|---:|---|---|---|---|---|---|---|
| 1 | DT_GERACAO | geração (documented) | texto | — | snapshot | observed | — |
| 2 | HH_GERACAO | hora (documented) | texto | — | snapshot | observed | — |
| 3 | ANO_ELEICAO | ano (documented) | texto; `2026` | — | escopo | observed | — |
| 4 | CD_TIPO_ELEICAO | tipo (hypothesis) | texto; obs: `2` (≠ bweb) | — | por fonte, sem identidade presumida | observed | tabela pendente |
| 5 | NM_TIPO_ELEICAO | nome do tipo (documented) | texto | — | — | observed | — |
| 6 | NR_TURNO | turno (documented) | texto; só `1` | — | escopo | observed | — |
| 7 | CD_ELEICAO | eleição (documented) | texto; só `6259` | — | join c/ bweb (hipótese) | observed | validar join antes de reconciliar |
| 8 | DS_ELEICAO | descrição (documented) | texto | — | — | observed | — |
| 9 | DT_ELEICAO | data (`DD/MM/AAAA`, hypothesis de formato) | texto; obs: `04/10/2026` | — | — | observed | formato difere do BU web; formalizar |
| 10 | TP_ABRANGENCIA | abrangência (documented) | texto; só `E` | — | escopo | observed | tabela `E`/outros pendente |
| 11 | SG_UF | UF (documented) | texto; `MT` | — | escopo | observed | — |
| 12 | SG_UE | sigla da UE (documented) | texto; `MT` | — | escopo | observed | distinção UF×UE a documentar |
| 13 | NM_UE | nome da UE (documented) | texto; `MATO GROSSO` | — | — | observed | — |
| 14 | CD_MUNICIPIO | município TSE (documented) | texto | — | chave | observed | — |
| 15 | NM_MUNICIPIO | nome (documented) | texto | — | — | observed | — |
| 16 | NR_ZONA | zona (documented) | texto | — | chave | observed | — |
| 17 | NR_SECAO | seção (documented) | texto | — | chave | observed | — |
| 18 | CD_CARGO | cargo (documented) | texto; 3/5/6/7 | — | escopo+chave | observed | corresponder c/ `CD_CARGO_PERGUNTA` do BU (Etapa 2) |
| 19 | DS_CARGO | descrição (documented) | texto; 4 valores | — | — | observed | — |
| 20 | NR_VOTAVEL | número (documented) | texto | — | ocorrência | observed | — |
| 21 | NM_VOTAVEL | nome (documented) | texto | — | — | observed | preservar; sem reduzir a nominais |
| 22 | QT_VOTOS | votos (documented) | texto numérico; medida | — | somável por ocorrência | observed | regra de agregação é Etapa 2+ |
| 23 | NR_LOCAL_VOTACAO | local (documented) | texto | — | chave | observed | — |
| 24 | SQ_CANDIDATO | sequencial do candidato (hypothesis) | texto | `-1` em 65.506, `-3` em 87.415 | — | observed | hipótese branco/não-registrado; confirmar |
| 25 | NM_LOCAL_VOTACAO | nome do local (hypothesis) | texto | — | — | observed | — |
| 26 | DS_LOCAL_VOTACAO_ENDERECO | endereço (hypothesis) | texto | — | — | observed | LGPD/uso analítico é Etapa 5+ |

### ceft (36 campos, fingerprint `5697514c3c693c23…`, 8.287 registros, pleito 3220)

Campos 1–11 (geração/pleito/UF/município/zona/seção/local) como nas demais
correspondências (documented para geração e localização; tipos: texto). Campos
12–19: correspondência **esperada** (`SQ_CORRESPONDENCIA_ESPERADA`,
`NR_URNA_ESPERADA`, cargas 0/1/2, flashcard, datas de carga/recebimento —
hypothesis para semântica de cada carga; texto). Campos 20–27: correspondência
**efetivada** (mesma estrutura com `SQ_CORRESPONDENCIA_EFETIVADA` — documented
que esperada ≠ efetivada; sem inferir substituição/anomalia). Campos 28–29
(`CD/DS_ORIGEM_VOTO`, hypothesis), 30 (`TP_DIVERGENCIA`: vazio 8.252 + `C` 35 —
observed; semântica pendente), 31–36 (máquinas/SRI de geração e transmissão —
hypothesis; texto). Chave candidata (não verificada): pleito + município +
zona + seção + sequência de correspondência. Sentinelas do conjunto: só o vazio
em `TP_DIVERGENCIA` nesta execução.

### csec (21 campos, fingerprint `124f979553c16348…`; t1: 8.287 e 8.286; t2: 8.286)

Campos 1–10 (geração/pleito/UF/município/zona/seção/local — documented p/
geração e localização; texto). Campos 11–14 (urna/cargas/flashcard/data —
hypothesis). Campo 15 (`ST_CORRESP_ALTERADA`: `*` em 03/10-t1 e t2; `N` 8.280 +
`S` 6 em 04/10-t1 — observed; semântica de `*`/`N`/`S` pendente, sem normalizar).
Campos 16–21 (máquinas/SRI — hypothesis). Chave candidata (não verificada):
pleito + município + zona + seção. Cabeçalho idêntico nas 3 gerações (mesmo
fingerprint); contagens e `ST_CORRESP_ALTERADA` divergem — snapshots, não série.

### ccont (19 campos, fingerprint `280c7c40805a06c1…`; t1: 1.240 e 1.270; t2: 1.246)

Sem `NR_SECAO`/`NR_LOCAL_VOTACAO` no cabeçalho examinado (observed —
**não inventar seção** para contingência; não usar o esquema do csec).
Campos 1–8 (geração/pleito/UF/município/zona — texto), 9–12
(urna/cargas/flashcard/data — hypothesis), 13 (`ST_CORRESP_ALTERADA` —
hypothesis; distribuição por geração a extrair do mapa local), 14–19
(máquinas/SRI — hypothesis). Cabeçalho idêntico nas 3 gerações; contagens
divergem — snapshots. Chave/granularidade da contingência: hipótese aberta
(Etapa 2), sem join presumido com seção.
