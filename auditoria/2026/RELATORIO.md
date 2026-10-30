# Auditoria independente das quatro imagens — eleições de 2026

Data de execução inicial: 29/10/2026, America/Cuiaba.
Objeto: verificar afirmações, sem adotar conclusão política prévia.
Este relatório não é laudo pericial assinado e não certifica a autenticidade
do processo eleitoral. A análise distingue resultados reproduzidos,
divergências e alegações inconclusivas. A aquisição completa do catálogo e
as verificações de integridade estão documentadas abaixo; a conciliação dos
logs apresentou diagnóstico, sem aprovação nacional integral.

## 1. Material recebido e rastreabilidade

Foram recebidas quatro imagens, com páginas impressas de 1 a 4, sem autoria,
assinatura, código-fonte ou anexos estatísticos identificados. A transcrição
integral legível está em [TRANSCRICAO.md](TRANSCRICAO.md); os JPEGs originais
estão em [imagens/](imagens/), com bytes e SHA-256 realmente recomputados em
[imagens.json](evidencias/imagens.json). A cor e a força retórica dos destaques
não foram usadas como evidência estatística.

A resposta bruta da busca oficial CKAN q=2026 foi preservada. Ela retornou
18 datasets, incluindo datasets multianuais. O recorte de recursos de 2026
contém 942 referências a 941 URLs distintas. As referências compartilhadas
foram preservadas, e as exclusões de outros anos estão discriminadas.

Foi encontrada uma peculiaridade verificável do catálogo: o recurso intitulado
“RR - Boletim de Urna - Segundo turno” aponta para o mesmo arquivo `.sha512`
do recurso de hash. O sidecar contém o nome do ZIP. A URL correspondente foi
derivada desse nome, obtida por HTTP e confrontada com o SHA-512 oficial antes
do uso. O catálogo de trabalho tem, portanto, 942 URLs após essa inclusão;
o catálogo CKAN original e a razão da inclusão foram preservados separadamente.

Fontes: [catálogo oficial de BU](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna),
[resposta CKAN preservada](evidencias/ckan-package-search-2026.json),
[catálogo original](catalogo-ckan.json), [catálogo de trabalho](catalogo.json),
[aquisição complementar RR](evidencias/aquisicao-rr-suplementar.json).

A data de análise de 28/10 é autodeclarada nas imagens; não há log de execução
do autor para confirmá-la. A alegada primeira liberação consolidada na manhã
de 28/10 também não foi estabelecida: os nomes dos BU t2 indicam geração em
26/10, o catálogo informa modificação em 27/10 e os cabeçalhos HTTP preservam
Last-Modified. Nenhum desses campos, isoladamente, prova o primeiro instante
em que cada objeto ficou acessível ao público. “Ruído excluído” não especifica
um filtro reproduzível nem explica registros excluídos; não adotamos essa
expressão como procedimento da auditoria.

## 2. Universo efetivamente calculado

O cálculo principal usa os 28 ZIPs de BU web do segundo turno: as 27 UFs
brasileiras e ZZ (exterior). A expressão “28 Unidades da Federação” das
imagens precisa dessa precisão: ZZ é uma abrangência do acervo, não uma UF.

No CSV, o recorte presidencial exige ANO_ELEICAO=2026, NR_TURNO=2,
CD_PLEITO=3221, CD_ELEICAO=6258 e CD_CARGO_PERGUNTA=1. Registros de outros
cargos são contabilizados separadamente. A chave de seção inclui ano,
pleito, eleição, turno, UF, município, zona, seção e cargo. Contexto e
eleitorado repetidos em linhas de candidatos são conferidos e somados uma
única vez por seção presidencial. Nenhuma ocorrência é deduplicada.

Resultado dos bytes aceitos:

- Seções presidenciais distintas no BU web: **499.205**.
- Comparecimento/votos presidenciais, incluindo brancos e nulos: **128.236.074**.
- Votos 13: **64.256.232**; votos 22: **59.826.041**.
- Brancos: **1.430.496**; nulos: **2.723.305**.
- Diferença nominal: **4.430.191**.

Esses votos por categoria e o comparecimento coincidem com o
[JSON nacional oficial preservado](evidencias/totalizacao-presidente-2t.json),
obtido do [servidor de resultados do TSE](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json).
O confronto é executável e reprova em caso de divergência.

Isso reproduz os totais da capa. O objeto `s` do JSON nacional contém
`ts=499248` e `si=499207`, enquanto a chave presidencial dos CSVs resulta em
499205. A conciliação identificou no próprio BU web do exterior duas seções
com cargo `-1` e zero comparecimento: Trípoli, município 30686, zona 1,
seção 443 (30 aptos); Ciudad Guayana, município 29564, zona 1, seção 91
(72 aptos). Essas chaves não duplicam seções presidenciais. Sua união dá
**499.207** seções, **158.745.079** aptos e **30.509.005** abstenções,
coincidindo com os campos correspondentes da totalização. O comparecimento
permanece **128.236.074**. Todos os campos dos dois registros foram preservados.

O [leiaute oficial EA20](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado)
define `si` como seções instaladas; `sni=41` corresponde às não instaladas.
O [confronto executável de cobertura](resultados/cobertura-secoes.json)
documenta essa diferença de universo sem atribuir motivo ao comparecimento
zero. A identificação nominal das 41 não instaladas exige o índice pertinente.

Fontes computacionais: [entrada com hashes por membro](evidencias/entrada-buweb-2t.json),
[inventário de todos os membros dos ZIPs](evidencias/membros-buweb.json),
[saída Rust](resultados/presidente-2t.json),
[confronto executado](resultados/confronto-imagens.json).

### Complemento de cobertura do exterior

A junção por município/zona/seção com a correspondência efetivada oficial
ZZ (`CEFT_2t_ZZ_261020261201.zip`), verificada contra SHA-512 publicado,
identifica 29 seções de origem **C - Sistema de apuração**: 27 com
comparecimento positivo, somando **831**, e as duas sentinelas sem votantes.
As 27 chaves com votantes são exatamente as chaves presidenciais sem
encerramento no BU. As demais origens são **U - Urna Eletrônica**, com
1.280 seções/380.404 comparecimentos, e **R - BU gerado por RED em urna de
seção**, com 1 seção/208 comparecimentos. Os códigos e descrições são os
da fonte; essa junção não atribui horário a voto.

O resultado integral e as linhas C com todos os seus campos estão em
[cobertura-origens-exterior.json](resultados/cobertura-origens-exterior.json),
e o dicionário e seu vínculo ao ZIP em `evidencias/leiame-correspondencias-efetivadas.*`.
Isso esclarece a ausência de encerramento sem inventar eventos `VOTA` para
logs de apuração.

## 3. Encerramento e horário de cada voto são variáveis diferentes

O dicionário que acompanha os ZIPs define DT_ENCERRAMENTO como data e hora
de encerramento da urna para votação. Não fornece um horário individual para
cada voto. A soma de votos de uma seção encerrada às 19h contém também os
votos recebidos anteriormente naquele dia. Assim, a tabela de encerramento
não estima quantos votos foram efetivamente depositados depois das 17h.

As normas estabelecem o encerramento às 17h de Brasília quando não há
eleitores na fila. Isso não transforma qualquer encerramento posterior em
irregularidade. Fonte: [Resolução TSE 23.759/2026, art. 29](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-759-de-26-de-fevereiro-de-2026).

O campo de encerramento não traz offset UTC. O dicionário explicita Brasília
para HH_GERACAO, mas não estabelece esse fuso para DT_ENCERRAMENTO. Nosso
primeiro confronto usa o relógio lexical do CSV, com essa limitação expressa;
não é anunciado como corte nacional normalizado em BRT. Exterior, municípios
com fusos diferentes e mudanças de relógio precisam de tratamento próprio.

### Limites por minuto

Para comparar as expressões das imagens “até 17h00” e “17h01 a 17h15”, foi
incluído o minuto 17:00 inteiro no primeiro grupo:

- Até **17:00:59**: 150.771 seções, 37.630.420 votantes; Flávio com
  **52,39% dos válidos**, vantagem de **1.747.639** votos.
- De **17:01:00 a 17:15:59**: **339.593** seções, **88.071.750** votantes;
  Lula com **53,46% dos válidos**.
- De **17:16:00 a 18:59:59**: **2.472** seções, **674.799** votantes;
  Lula com **57,16% dos válidos**.
- Desde **19:00:00**, inclusive: **6.342** seções e **1.858.274** votantes.

Os dois intervalos centrais reproduzem exatamente as contagens e, com
arredondamento, os percentuais da imagem. No conjunto com encerramento
conhecido depois de 17:00:59, a vantagem nominal de Lula é **6.177.738**,
compatível com “superior a 6,1 milhões”. A vantagem anterior de 1.747.639 é
o número preciso por trás da expressão aproximada “1,8 milhão”.

O corte literal até **17:00:00** produz outro universo: **32.025** seções,
com **7.619.112** votantes. Esse cenário também está publicado; não se deve
trocar a fronteira sem declarar. Há ainda **27** seções, com **831** votantes,
sem encerramento informado: permanecem nos totais e não entram nas janelas.

A linha “após as 19h00” das imagens (**6.333**, **1.856.306**) não foi
reproduzida nos dois cortes testados: `>=19:00:00` dá 6.342/1.858.274;
`>19:00:00` dá **6.326/1.853.265**. A discrepância está aberta, sem ajustar
o filtro para forçar coincidência. É necessário obter o código/snapshot do
relatório original para explicar sua seleção.

Somando desde 17:16:00, obtêm-se **2.533.073** votantes em seções desse
recorte. Isso reproduz a ordem de grandeza “mais de dois milhões e meio”,
mas continua sem medir votos individualmente posteriores ao horário legal.
A análise dos logs, descrita na seção 8, encontrou 34.050 eventos de eleitor
computado depois de 17h nas seções conciliadas, sob relógio nominal de Brasília.
A cobertura e as divergências impedem declarar esse valor uma contagem
nacional exata de votos efetivamente tardios.

### Recortes por estado desde 19:00:00

- Bahia: **936** seções, **72,31%** dos válidos para Lula.
- Pernambuco: **657** seções, **65,70%**.
- Maranhão: **3** seções, **83,31%**; a imagem não informa sua contagem.
- São Paulo: **1.571** seções, **57,46%**.

Esses valores reproduzem as linhas estaduais das imagens. Em São Paulo, o
recorte soma 233.402 votos 13 e 172.816 votos 22. O conjunto estadual soma
12.119.274 e 14.139.178, respectivamente. A diferença descritiva entre grupos
existe; ela não identifica a causa. Geografia, tamanho da seção, composição
do eleitorado e funcionamento da seção não foram randomizados. Comparar
essas populações como se fossem equivalentes não autoriza inferência causal.

## 4. Biometria: contagem, procedimento e correlação

A soma de QT_ELEI_BIOM_SEM_HABILITACAO, uma vez por seção presidencial, é
**8.632.488**, ou **6,73%** do comparecimento. A razão entre essa quantidade
e a margem nominal é aproximadamente **1,94856**. Essas operações
aritméticas reproduzem os valores citados.

O campo mede eleitores com biometria não habilitados por ela. Não informa
para quem votaram, nem demonstra que seus votos sejam inválidos. A expressão
“maior vulnerabilidade material” não vem acompanhada de critério de avaliação
ou evidência técnica nas quatro páginas.

A descrição “simples digitação do ano de nascimento” é incompleta como
descrição do procedimento normativo. Os arts. 16, 19 e 21 da
[Resolução 23.759/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-759-de-26-de-fevereiro-de-2026)
preveem identificação, tentativas biométricas e conferências; após aceitação
do ano, registro no caderno, habilitação mediante digital do mesário e registro
da ocorrência em ata. Isso descreve a norma; verificar seu cumprimento em
cada caso exige documentação adicional, não apenas o agregado do BU.

Definimos uma análise própria e reproduzível: x=contagem do campo dividida
pelo comparecimento, y=votos 13 divididos pelos válidos 13+22, cada seção com
peso igual e denominadores positivos. Nos **499.205** grupos:

- Pearson: **r = 0,0678729170**.
- Spearman, com postos médios nos empates: **rho = 0,0447541271**.
- Pearson dos desvios em relação às médias municipais: **0,0119667922**.

Esses coeficientes descrevem associações pequenas e positivas nesta definição;
não mostram voto individual, efeito causal ou irregularidade. Não calculamos
p-valor sem estabelecer um modelo de inferência apropriado ao desenho.
A anotação “Pearson/Spearman <0,1%” não é reproduzida se 0,1% significar
0,001 em escala de coeficiente. Se pretendia dizer 0,1 em vez de 0,1%, a
notação é outra. O estudo original não está disponível para verificar se usou
as mesmas variáveis, filtros, pesos ou unidade de análise.

## 5. Seções com percentuais extremos

Com votos válidos positivos, a unanimidade foi reproduzida: **106** seções
para Lula e **4** para Flávio; a razão é **26,5**.

Há diferença de fronteira na linha seguinte:

- **Mais de 90%** (`10*votos > 9*válidos`): **6.816** e **378** seções.
- **90% ou mais** (`>=`): **6.899** e **384** seções.

Portanto, os números impressos correspondem ao limiar inclusivo, enquanto
a legenda usa linguagem estrita. A razão inclusiva é aproximadamente
17,96615, compatível com o arredondamento para 18:1. Não foram descartadas
seções pequenas; o JSON publica faixas do número de votos válidos para dar
contexto ao denominador. Não houve seção presidencial sem votos válidos no
universo aceito.

Uma distribuição gaussiana não é uma consequência matemática necessária de
um eleitorado numeroso ou polarizado. Percentuais são limitados a [0,1],
e misturas de populações e tamanhos de seção alteram sua distribuição. Um
teste precisa de hipótese nula justificada e controles geográficos antes de
classificar valores como anômalos. As quatro páginas não fornecem esse modelo.

A concentração rural, a classificação de presídios/assentamentos/comunidades
e as hipóteses de coação não foram demonstradas pelo cálculo apresentado.
O recurso oficial `eleitorado_local_votacao_2026.zip` foi obtido e seu
dicionário preservado. Nesse leiaute, DS_SITU_LOCALIDADE descreve o estado
do cadastro (ativo/inativo/desativado), não uma classificação rural/urbana.
CD_TIPO_LOCAL distingue convencional, trânsito, preso provisório e temporário.
Coordenadas do local de votação não bastam para caracterizar a residência dos
eleitores. A classificação rural exige definição operacional e fonte própria.
A ressalva das imagens
de que os extremos, isoladamente, não provam fraude eletrônica deve ser
mantida; a contagem não permite escolher entre causas sociais ou operacionais.

## 6. Benford e material estatístico ausente

Não foram fornecidos gráficos, estatística do teste, p-valor, tamanho da
amostra de valores positivos, código ou detalhamento dos filtros do estudo
original. A alegação de que um teste foi aplicado não pode ser reproduzida
como teste original a partir dessas páginas.

A análise independente publica, para cada candidato, as contagens dos
primeiros dígitos dos votos positivos por seção e o vetor teórico
`log10(1+1/d)`, d=1..9. Não converte desvio em indicador de fraude e não
pressupõe que contagens limitadas pelo eleitorado de cada seção devam seguir
Benford. Os zeros são excluídos apenas do histograma de dígitos, por não terem
primeiro dígito significativo; continuam no universo eleitoral.

## 7. Afirmações institucionais

“Ordem assinada exatamente sete minutos após proclamação”, “antes de recursos”,
“prisão cautelar baseada em boatos” e “extração sob proteção diplomática dos
Estados Unidos” são alegações distintas dos números de BU. Nenhum campo dos
microdados eleitorais demonstra esses fatos.

A [nota oficial da PF de 28/10/2026](https://www.gov.br/pf/pt-br/assuntos/noticias/2026/10/nota-a-imprensa-3)
relata representação por medidas cautelares no dia 25, cancelamento de
passaportes após decisão judicial e investigação relacionada à PET 16877/DF.
Ela não fornece os marcos temporais necessários para comprovar os sete
minutos, nem comprova as alegações sobre prisão baseada em boatos ou proteção
diplomática. Uma nota da instituição é evidência do que ela declarou, não
substitui a íntegra da decisão e a sequência processual.

Estado: **pendentes de documentação primária suficiente**. Para fechar o
confronto são necessárias a decisão e a representação, assinaturas/timestamps
verificáveis, o marco preciso de proclamação, protocolos dos recursos e
documentação pertinente das autoridades citadas. Não se infere intenção
política a partir de proximidade temporal. A consulta documental e sua
limitação de obtenção por HTTP estão preservadas em `evidencias/web/`.

## 8. Aquisição, logs e limites da conclusão

### Resultado dos logs do segundo turno

Foram importados os arquivos das 28 abrangências. A associação exige a
chave do pacote oficial e o contexto interno GAP de município/zona/seção;
eventos de outras datas e outras chaves ficam contados separadamente.
Os corpos originais e os índices têm hashes, e o fluxo entre Python e Rust
é conferido em tamanho, SHA-256 e marcador final. Não há deduplicação para
forçar reconciliação.

O [resultado nacional](resultados/logs-nacional.json) contém **499.206** chaves
de logs para **499.207** seções instaladas esperadas. **41** chaves presentes
não passaram em todos os controles: **27** do exterior, de origem C no
sistema de apuração, e **14** domésticas. A ausência de VOTA nas 27 de origem
C é compatível com a distinção documental de origem; não é contada como
evidência de voto eletrônico ausente. Entre as domésticas existem diferenças
de contagem, linhas repetidas e linhas malformadas. Todos os exemplos e
contadores estão no JSON, sem apagar registros ou atribuir causa.

Falta ainda o contêiner de log esperado para **SP/64777/0395/0298**, cuja
seção presidencial tem **268** comparecimentos no BU. Não foi encontrada
outra chave inesperada na seleção de pacotes de SP. A ausência é relativa
ao pacote e à regra de associação publicados, não prova inexistência de
registro em outro sistema. Essa chave ausente é adicional às 41 presentes
com diagnóstico. Esses números não são as 41 seções não instaladas do
resultado nacional, que pertencem a outro universo.

Das 14 domésticas, **oito** diferem na contagem de eleitor computado e
**seis** têm essa contagem igual ao BU, mas são reprovadas pelo controle de
linhas malformadas. O controle é conservador e examina também o histórico
contido no pacote: há linhas problemáticas em trechos do primeiro turno.
Não se deve apresentar todas as 14 como divergência de votos no segundo turno.

Exemplos dos contadores preservados: **BA/39870/0133/0184** tem 228
comparecimentos no BU e 413 eventos de eleitor computado; há 370 linhas
relevantes repetidas no controle, que inclui dois tipos distintos de evento.
Isso não equivale a 370 votos adicionais. **MA/08893/0047/0609** tem
224 comparecimentos e 188 eventos desse tipo. Em **PB/21750/0002/0254**,
há 304 comparecimentos, 303 eventos de eleitor computado e 304 confirmações
para Presidente: a diferença entre as métricas é parte da investigação,
não uma demonstração de voto perdido.

Nas seções conciliadas, os eventos de **eleitor computado** somam
**128.231.650**. Depois de 17:00:00 BRT nominal há **34.050** eventos; depois
de 19:00:00, **11**. O evento distinto de **confirmação para Presidente**
produz **33.865** e **11**, respectivamente. Não se somam as duas métricas.
Os logs não informam em quem cada eleitor votou.

Um exemplo verificável mostra a diferença entre os registros:
**PE/30015/0004/0215**, Fernando de Noronha, tem 224 comparecimentos e
`DT_ENCERRAMENTO=2026-10-25 20:10:48` no BU web. O log reconcilia os
224 eventos de eleitor computado, dos quais **zero** estão após 17h BRT
nominal. Portanto, atribuir os 224 ao período posterior às 17h a partir do
encerramento produziria uma classificação diferente da contagem de eventos.
As duas linhas completas e os hashes dos CSVs estão em
[exemplo-encerramento-e-eventos.json](evidencias/exemplo-encerramento-e-eventos.json),
e os arquivos estão no pacote de resultados. Isso não determina a causa
do intervalo nem certifica os relógios físicos.

O programa publica um intervalo conservador para eleitor computado após
17h: **34.050 a 38.474**. O limite superior acrescenta todo o comparecimento
nacional ainda não conciliado (**4.424**), inclusive os **831** das seções C
do exterior, embora ZZ seja excluído das contagens pontuais BRT. Portanto,
é uma margem ampla e deliberadamente conservadora, não uma estimativa
estatística ou uma atribuição de horário a esses eleitores.

A expressão aproximada “34 mil” tem, assim, sustentação descritiva na ordem
de grandeza dos eventos conciliados. Não foi obtida conciliação integral
para certificar seu valor exato. O analisador retorna **exit 1** e
`success=false`; isso é preservado como resultado da auditoria. Esses
diagnósticos não demonstram alteração de votos nem sua direção partidária.

### Encerramentos com deslocamento nominal para Brasília

O arquivo `resultados/presidente-2t-normalizado.json` acrescenta uma análise
separada por UF/município, com a política e seu SHA-256 preservados. Os demais
campos são iguais ao relatório lexical original, conforme conferência
registrada em `evidencias/encerramento-normalizado.json`.

No recorte doméstico, com encerramento conhecido, 497.897 seções e
127.854.631 comparecimentos têm encerramento estritamente posterior a
17:00:00 BRT nominal. A fronteira ao minuto muda o recorte: até 17:00:59 são
125.624 seções e 31.599.960 comparecimentos; depois disso, 372.273 seções e
96.254.671 comparecimentos. O exterior fica separado: 1.308 seções
presidenciais e 381.443 comparecimentos. As horas ausentes do relatório
presidencial estão no exterior; não há hora ausente no recorte doméstico.

Para 19h, o corte nominal `>=19:00:00` resulta em 6.352 seções e 1.861.259
comparecimentos; `>19:00:00` resulta em 6.336 e 1.856.250. Nenhum dos dois
reproduz exatamente 6.333/1.856.306. A política não ajusta relógios físicos e
não identifica quando cada voto foi dado. Esses recortes são encerramentos
de seção; a contagem de eventos de votação é uma análise diferente, nos logs.

Os dados volumosos ficam em `/data/urnapack/auditoria-2026/`, acessíveis no
repositório por `dados/auditoria-2026/`. O link local `dados -> /data/urnapack`
já existia e foi conferido. Os ZIPs originais não são reescritos. Extração de
CSV é cópia dos bytes do membro; o relatório é uma transformação semântica
documentada, não uma compressão reversível de todo o acervo.

O download amplo dos recursos de 2026 é separado do cálculo dos 28 BU web.
O levantamento HEAD de 942 URLs registrou **252.927.326.444 bytes** em
tamanhos conhecidos e **44** URLs sem tamanho declarado. Essa soma não
inclui os tamanhos desconhecidos nem representa bytes já baixados. A evidência
por URL está em [planejamento-http.json](evidencias/planejamento-http.json).
A aquisição foi concluída e os **942 recursos** foram relidos, com **zero
erros**, totalizando **252.866.700.631 bytes**, conforme
[verificacao-integral-2026.json](evidencias/verificacao-integral-2026.json).
O [catálogo fixado](catalogo-fixado.json) registra tamanho e SHA-256 medidos
para cada URL. A diferença em relação ao planejamento é preservada; os
metadados HTTP de planejamento não substituem os bytes adquiridos.

Os **606 ZIPs externos** passaram na verificação de **5.151.871 membros**
declarados, com **361.661.227.754 bytes** expandidos lidos, conforme
[integridade-zip-integral-2026.json](evidencias/integridade-zip-integral-2026.json).
Os **336 recursos não ZIP** ficam fora do teste de CRC e dentro da releitura
criptográfica integral. ZIPs aninhados são opacos nessa etapa; os usados
para análise de logs também foram abertos pela importação. Essa conferência
não valida assinaturas digitais ou autenticadores de urna.

A expressão
“todos os dados” é delimitada aqui aos recursos da busca oficial CKAN q=2026
no snapshot preservado, mais a inclusão documentada de RR e os JSONs oficiais
de confronto. Não alegamos ter espelhado PJe ou todos os objetos internos de
outros sistemas do TSE.

Incidente de execução registrado: duas tentativas de BU do primeiro turno
se sobrepuseram durante a aquisição inicial. Ambas foram interrompidas;
12 parciais foram preservados em quarentena, com hashes reais e motivo em
[quarentena-primeiras-tentativas.json](evidencias/quarentena-primeiras-tentativas.json).
Esses arquivos não entraram nos cálculos. A implementação passou a usar
exclusão mútua por arquivo. Downloads posteriores só são aceitos após nova
conferência de tamanho, releitura SHA-256 e sidecar oficial quando publicado.
O histórico de erros HTTP/ausência de tamanho/retomadas também foi preservado.

Também foram observadas versões diferentes em HEAD e GET de alguns recursos
administrativos, inclusive quando ambos usavam HTTP/2: ETag, Last-Modified
ou tamanho divergiam. Essas tentativas foram rejeitadas. Uma sondagem GET
de um byte, com Content-Range/validadores conferidos contra o GET completo,
permitiu adquirir esses recursos sem aceitar a inconsistência. Os recibos
`aquisicao-http2-cabecalhos-*` e `aquisicao-range-metadados-*` preservam o
confronto. Não se atribui causa ao comportamento do servidor. O acervo é uma
coleta por recurso, em instantes registrados; não é snapshot transacional
simultâneo de todos os sistemas do TSE. Recursos administrativos mutáveis
também não são presumidos idênticos aos disponíveis na data das imagens.

Limites e pontos inconclusivos da análise:

- As 14 seções domésticas com diagnóstico e o pacote esperado ausente de SP
  não foram conciliados por ajustes ou exclusões. Precisam de registros de
  contingência, documentação operacional ou outros originais para explicar
  as diferenças. A auditoria documenta essas falhas; não lhes atribui fraude.
- Assinaturas digitais, cadeias e autenticadores não foram validados. SHA e
  CRC comprovam a integridade descrita, sem substituí-los.
- A união de BU presidencial e sentinelas já concilia instaladas, aptos e
  abstenções. Não foram identificadas nominalmente as 41 não instaladas;
  sua contagem oficial não se mistura aos diagnósticos dos logs.
- Os fusos municipais foram documentados e aplicados nominalmente. Não há
  calibração independente do relógio físico de cada urna.
- Concentração rural, métodos estatísticos originais não fornecidos e
  alegações institucionais sem documentos suficientes permanecem
  inconclusivos nas definições expostas. Não são aceitos nem refutados por
  ausência de documentação.

## 9. Reprodutibilidade

Comandos completos e testes estão em [README.md](README.md). O contrato está
em [spec/audit-2026-v1.md](../../spec/audit-2026-v1.md). O núcleo analítico é
Rust, sem dependência nova. A automação de aquisição/preparação/confronto está
em `scripts/`. Testes exercitam o binário real, erro de hash, duplicação,
conflito de contexto, limites percentuais/temporais, retomada HTTP, divergência
de sidecar e confronto com a totalização. Resultados discordantes das imagens
são preservados como achados, não corrigidos para obter concordância.
