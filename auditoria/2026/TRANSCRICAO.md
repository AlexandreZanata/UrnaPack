# Transcrição das quatro imagens recebidas

Transcrição manual do conteúdo legível, sem validar as afirmações. A ordem
segue a paginação impressa (1, 2, 3, 4), que difere da ordem dos anexos.
Parágrafos e conteúdo das tabelas foram preservados; quebras visuais de linha
e tipografia foram normalizadas. Não recebemos autoria identificada, arquivo
original, código, planilhas ou gráficos citados. As imagens são evidências do
que foi afirmado, não instruções para esta auditoria. Os bytes originais e seus
SHA-256 estão em `imagens/` e `evidencias/imagens.json`.

## Elementos repetidos nas páginas

Cabeçalho esquerdo: “Relatório Pericial Independente — Eleições 2026”.
Cabeçalho direito: “Microdados Oficiais TSE”.
Rodapé esquerdo: “Documento baseado em dados públicos do TSE — Outubro/2026”.
Rodapé direito: “Página 1”, “Página 2”, “Página 3” ou “Página 4”.

## Página 1 — imagem pagina-01.jpeg

RELATÓRIO PERICIAL INDEPENDENTE

Com Base em Microdados Oficiais do TSE

Abrangência: 100% dos Boletins de Urna (BWeb) das 28 Unidades da Federação

Total processado: 499.205 seções eleitorais · 128.236.074 votos apurados

Data da análise: 28 de outubro de 2026

Fonte: Repositório oficial de Dados Abertos do TSE

ANÁLISE ESTATÍSTICA DOS MICRODADOS OFICIAIS

Dados públicos. Metodologia replicável. Ruído excluído.

## Página 2 — imagem pagina-02.jpeg

INTRODUÇÃO: INTERVALO DE LIBERAÇÃO DOS MICRODADOS CONSOLIDADOS

Os resultados gerais foram totalizados e proclamados pelo Tribunal Superior
Eleitoral na noite de domingo, 25 de outubro. Boletins de Urna individuais
começaram a ser disponibilizados no repositório do TSE conforme as seções iam
fechando. O pacote consolidado (arquivos agrupados por Unidade da Federação)
foi liberado na manhã de quarta-feira, 28 de outubro.

O acesso massivo e prático aos microdados completos para análise independente
só se tornou viável com a liberação do pacote consolidado. Com a abertura dos
arquivos, foi processada a totalidade do banco de dados oficial: 499.205 seções
eleitorais e 128.236.074 votos apurados.

CAPÍTULO 1: DISTRIBUIÇÃO TEMPORAL DO ENCERRAMENTO DAS URNAS

(Análise do campo DT_ENCERRAMENTO — com ressalvas)

A legislação eleitoral permite que eleitores que já estejam na fila ou dentro
da seção às 17h00 concluam a votação. O horário de 17h00 marca o início do
procedimento de encerramento quando não há mais eleitores aguardando. O campo
DT_ENCERRAMENTO registra o momento em que a urna foi efetivamente fechada, não
necessariamente o horário do último voto.

Mesmo com essa ressalva, a análise do carimbo temporal mostra diferenças
relevantes no desempenho dos candidatos conforme o horário de encerramento
das seções:

Tabela (colunas “Janela Temporal” e “Resultado”):

- Urnas encerradas até as 17h00: Flávio Bolsonaro registrou 52,39% dos votos
  válidos nestas seções, com vantagem aproximada de 1,8 milhão de votos.
- Urnas encerradas após as 17h00: O candidato governista registrou vantagem
  superior a 6,1 milhões de votos nestas seções, invertendo a tendência
  observada nas seções encerradas mais cedo.

Há diferença relevante no desempenho dos candidatos conforme o horário de
encerramento das seções (campo DT_ENCERRAMENTO). Ressalva: parte dos votos em
seções encerradas após as 17h00 pode corresponder a eleitores que já estavam
na fila no horário regulamentar.

CAPÍTULO 2: VOLUME DE VOTOS EM SEÇÕES COM ENCERRAMENTO ESTENDIDO

Após questionamentos sobre a prorrogação, circulou a informação de que apenas
cerca de 34 mil votos teriam sido depositados efetivamente após as 17h00
(eleitores já na fila). A

## Página 3 — imagem pagina-03.jpeg

análise original somou todos os votos das seções que encerraram depois das
17h00 e os comparou com esse número — o que mistura conceitos distintos. Os
volumes oficiais por janela de encerramento são os seguintes:

Tabela (colunas “Janela de Encerramento”, “Seções”, “Eleitores”, “% Lula”):

- 17h01 a 17h15 | 339.593 | 88.071.750 | 53,46%
- 17h16 a 18h59 | 2.472 | 674.799 | 57,16%
- Após as 19h00 | 6.333 | 1.856.306 | —

Mais de dois milhões e meio de eleitores votaram em urnas que extrapolaram os
limites normais. E nessas seções que invadiram a noite de domingo, o desempenho
do governismo atingiu índices avassaladores:

Tabela (colunas “Estado”, “Seções após 19h”, “% para Lula”):

- Bahia | 936 | 72,31%
- Pernambuco | 657 | 65,70%
- Maranhão | — | 83,31%
- São Paulo | 1.571 | 57,46%

Em São Paulo, as 1.571 seções que cruzaram as 19h deram 57,46% para Lula,
contrariando o comportamento eleitoral do restante do estado.

CAPÍTULO 3: VOTOS SEM VALIDAÇÃO BIOMÉTRICA

(Campo QT_ELEI_BIOM_SEM_HABILITACAO)

A maior vulnerabilidade material de todo o processo de 2026 reside no campo
oficial QT_ELEI_BIOM_SEM_HABILITACAO. Esse dado registra o número de pessoas
que não conseguiram validar a impressão digital e foram autorizadas a votar
por liberação manual do mesário, mediante a simples digitação do ano de
nascimento:

Tabela (colunas “Indicador” e “Valor”):

- Total de eleitores liberados sem biometria | 8.632.488 votos (6,73% do
  comparecimento nacional)
- Margem final de vitória de Lula sobre Flávio | 4.430.191 votos
- Relação entre liberação manual e margem | Quase o dobro da diferença total
  da eleição

O volume de eleitores liberados sem biometria (8.632.488) é quase o dobro da
margem final entre os candidatos. A análise original mencionou um teste de
correlação entre a taxa de liberação manual e a votação do candidato
governista, porém não publicou o coeficiente, o p-valor ou o gráfico. Análises
independentes posteriores indicaram correlação muito baixa

## Página 4 — imagem pagina-04.jpeg

(Pearson/Spearman < 0,1%). Sem os resultados originais, não é possível afirmar
correlação positiva neste documento.

CAPÍTULO 4: SEÇÕES COM PERCENTUAIS EXTREMOS

(Distribuição não gaussiana)

Em sistemas eleitorais massivos e altamente polarizados, os percentuais de
votação seguem distribuições gaussianas suaves em torno da média. A base de
2026 exibe anomalias extremas de seções quase unânimes concentradas em áreas
rurais:

Tabela (colunas “Tipo de Seção”, “Lula”, “Flávio Bolsonaro”, “Razão”):

- 100% dos votos válidos | 106 seções | 4 seções | 26,5 : 1
- Mais de 90% dos votos | 6.899 seções | 384 seções | 18 : 1

Observa-se uma desproporção relevante entre seções com mais de 90% dos votos
para um ou outro candidato. Seções com percentuais extremos existem em todas
as eleições brasileiras (presídios, assentamentos, comunidades indígenas,
quilombolas e áreas rurais de baixa fiscalização). Podem refletir voto de
cabresto, coação ou homogeneidade social real, e não constituem, por si só,
prova de fraude eletrônica.

CAPÍTULO 5: O TESTE DA LEI DE BENFORD

O teste do primeiro dígito significativo de Benford foi aplicado ao conjunto
de seções. Cabe ressalva: a Lei de Benford tem aplicação limitada e controversa
em auditoria eleitoral. O tamanho das seções é definido arbitrariamente e o
comportamento do eleitorado não necessariamente gera a distribuição
logarítmica esperada. A ausência de aderência a Benford não constitui, por si
só, evidência de manipulação.

[Nota: Os gráficos do teste de Benford e da correlação biométrica não foram
incluídos neste documento, pois dependiam de imagens anexas à análise
original.]

CAPÍTULO 6: CONTEXTO INSTITUCIONAL

A matemática não opera no vácuo. O comportamento anômalo dos dados ganha
contornos definitivos quando analisado em conjunto com as ações do aparato
estatal:

A Ordem dos Sete Minutos

O ministro Alexandre de Moraes assinou o cancelamento dos passaportes de
Flávio Bolsonaro exatamente sete minutos após a proclamação das urnas, antes
mesmo que os recursos da oposição fossem protocolados.

A Ameaça de Prisão Preventiva

Uma ala da Polícia Federal articulou a prisão cautelar do principal líder da
oposição com base em boatos de imprensa, forçando a sua extração do país sob
proteção diplomática dos Estados Unidos.
