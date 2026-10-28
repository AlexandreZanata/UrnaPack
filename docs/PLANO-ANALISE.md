# Plano de análise — requisitos durante o tratamento e execução por escopo

## Posição no projeto

Os requisitos analíticos orientam o tratamento desde a Etapa 1 de
`docs/PLANO.md`. Os controles descritivos começam no MVP validado; modelos e
comparações dependem das fontes que cada uso requer. Não esperar a publicação
ou a cobertura nacional para verificar um recorte local completo.

Este documento define ordem e portões. A metodologia estatística completa
precisa ser versionada no repositório ou referenciada por versão e hash antes
da implementação dos respectivos modelos. A especificação externa mencionada
na versão anterior não foi localizada; não tratá-la como requisito implementado.

## A1 — Contrato de entrada para cada uso

Registrar ano, ambiente, abrangência, eleição/pleito, cargo, fontes, snapshots,
recorte e cobertura. Só liberar o uso quando existirem evidências de:

- hashes recomputados dos objetos exigidos e dependências disponíveis;
- preservação/restauração conforme o perfil e equivalência do canônico;
- granularidade e medidas declaradas: contexto seção/cargo, votos por votável,
  correspondências e eventos separados logicamente;
- localização de cada ocorrência na fonte por hash + membro/ordinal;
- sentinelas, nulos, categorias, tipos e referência temporal documentados;
- contagens e multiplicidades confrontadas com leitura dos dados;
- chaves, cardinalidades e regras de agregação verificadas;
- lacunas, exclusões explícitas e limitações de origem/autoria registradas.

`tsepack verify` atual confere arquivos de origem. O validador do índice confere
estrutura. Esses comandos não implementam sozinhos A1 nem conferem equivalência
semântica. O índice pode estar vazio e estruturalmente correto.

## A2 — Controles por fonte antes de unir tabelas

- Comparar somas e categorias com suas definições oficiais para ano/cargo.
  Não impor a todos os cargos a mesma relação entre votos e comparecimento.
- Aptos/comparecimento repetidos por votável exigem igualdade verificada antes
  de extrair contexto. Divergência bloqueia o uso afetado e gera evidência.
- Preservar todas as ocorrências, inclusive duplicatas legítimas e versões;
  escolher snapshot para uma análise por regra registrada.
- Medir cobertura e qualidade antes de procurar anomalias estatísticas.

## A3 — Correspondência entre fontes e turnos

- Identificar unidade comparável por códigos oficiais, sem ligar apenas por
  nome ou por número de seção isolado. Códigos de eleição podem variar por turno.
- Validar cardinalidades antes de cada join; multiplicação de linhas é erro
  se a relação esperada era muitos-para-um.
- Documentar seções principais, agregadas, desmembradas e correspondências
  esperadas/efetivadas/contingência. Não contar principal e agregadas novamente.
- Sem par confiável: bloquear a comparação nessa granularidade ou publicar
  outro recorte explicitamente validado; não fabricar correspondência.
- BU × RDV × totalização exige fontes disponíveis, compatibilidade e tratamento
  das situações oficiais. Relatório de reconciliação separado da estatística.

## A4 — Comparação descritiva

Construir registros comparativos apenas para pares válidos, com numeradores,
denominadores, unidades e regras explícitos. Distinguir pontos percentuais de
variação percentual; tratar denominador zero sem produzir taxa artificial.

Começar por comparecimento, brancos/nulos e distribuições por cargo e grupo,
com categorias oficiais preservadas. A primeira análise serve também para
verificar se o tratamento conservou o contexto necessário.

## A5 — Modelos e controles que os acompanham

- Baseline simples primeiro, por exemplo binomial/beta-binomial quando suas
  hipóteses forem adequadas. Complexidade exige calibração melhor demonstrada.
- Registrar famílias de hipóteses e controle de testes múltiplos desde o
  primeiro modelo. FDR, permutação e bootstrap dependem das hipóteses e da
  estrutura de dependência; não são selos automáticos de validade.
- Usar sintéticos identificados, controles, falsificação e validação separada
  do ajuste antes de interpretar achados reais. Medir as taxas sob as
  hipóteses simuladas e verificar sua adequação aos dados observados.
- Análise ecológica exige limites de compatibilidade e não-identificação
  explícita. Não transformar agregado em trajetória de eleitor individual.
- Territorial depende de geometria confiável; logs dependem de formatos e
  referência temporal conhecidos; dígitos exigem hipóteses justificadas.
- ML é exploratório e opcional. Sua ausência não bloqueia outros relatórios.
- RDV não oferece identidade/ordem individual de comparecimento; não fabricar
  vínculos entre votos por cargo ou turno a partir de posições ou agregados.

Esses métodos não formam uma fila obrigatória. Cada um depende de A1–A4 e de
seus próprios controles. Explicabilidade e falsificação são transversais.

## A6 — Execução e relatório reproduzíveis

Planejar extensão do binário existente com `tsepack analyze`; ainda não
implementada. Cada execução registrará hashes de datasets/tabelas auxiliares,
versões de esquema/parser/código, parâmetros, seleção/exclusões, denominadores,
sementes quando aplicáveis, limitações e verificações executadas.

Relatórios JSON/CSV/HTML versionados devem separar qualidade dos dados,
reconciliação determinística e achados estatísticos. Estado parcial precisa
estar explícito. Comando não implementado ou dependência ausente falha; não
finge sucesso.

## MVP e critérios de revisão

MT: contrato → controles por fonte → correspondência → descrição → um modelo
calibrado, se necessário → relatório. Comparação t1×t2 somente com o par
exigido; verificações de um turno não dependem de aguardar o outro.

Aprovação exige evidências para A1–A6 aplicáveis, consultas conferidas contra
uma referência independente, controles executados e relatório interpretável.
A expansão nacional reaplica os mesmos portões e a detecção de variantes do
mapa de dados brutos. RAM nacional deve ser medida; projeção continua projeção.
Nenhum indicador isolado produz conclusão de fraude ou autenticidade eleitoral.
