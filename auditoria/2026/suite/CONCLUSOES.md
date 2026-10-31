# O que a nova bateria encontrou

A bateria terminou e seu conferidor independente aprovou. Foram comparados
todos os 21 campos das 499.205 seções; 501 scores selecionados por hash
foram recalculados com outra implementação matemática. Todos os ajustes,
correlações residuais, correções e réplicas foram conferidos. O protocolo
foi fixado antes desta execução, depois da análise descritiva anterior:
é exploração transparente, não estudo cego ou pré-registro prospectivo.

## Existem anomalias estatísticas?

**Existem desvios em relação aos modelos e associações condicionais.**
Não são impossibilidades matemáticas nem uma contagem de fraudes. A própria
calibração mostra que o modelo mais flexível ainda descreve mal as caudas.
É necessário manter juntos o alerta, seu pressuposto e o contexto cadastral.

O número de alertas nominais após a mesma correção múltipla varia de
163.026 na referência binomial nacional para 68.209 por UF, 15.239 por
município e **192** na beta-binomial municipal ajustada fora do fold.
São contagens de modelos diferentes, sem pressupor conjuntos aninhados.
Isso mostra por que não se deve chamar um evento de “milagre” usando uma
probabilidade nacional única para seções de populações distintas.

Nos 192 alertas do quarto modelo, **178** têm proporção para 13 acima
da referência e **14** abaixo, na direção de 22. Todos foram preservados.
Não são 178/14 votos irregulares nem seções fraudulentas demonstradas.

## A calibração impede interpretar esses números como chances de fraude

Na cauda nominal de 0,0001, apareceram **1.069** seções; N×0,0001 é
aproximadamente 49,9. Na cauda de 0,001, apareceram **2.343**, para
referência de aproximadamente 499,2. Dados discretos não precisam atingir
exatamente a taxa nominal, mas esse excesso de cauda requer investigar
inadequação do modelo, dependência e subpopulações não representadas.
Holm não corrige um modelo nulo inadequado.

Unanimidade observada: **106** para 13 e **4** para 22. A referência
beta-binomial estima aproximadamente **10,47** e **4,33**. Seções >90%:
**6.816/378** observadas e aproximadamente **4.315/500** esperadas.
Há excesso e déficit em relação à referência; nenhum estabelece sua causa.

## O confronto com as fontes originais e os locais

O seguimento foi feito **depois** dos testes e não alterou scores ou cortes.
Todas as 192 seções foram relidas nos CSVs originais do TSE, também
diretamente nos ZIPs fixados. Comparecimento, aptos, biometria, urna, local,
encerramento e quatro contagens de votos coincidiram. Os scores das 192
foram recalculados independentemente. Não se detectou erro da projeção
nesses casos; isso não autentica o voto físico.

Todas as 192 têm correspondência no cadastro de locais: **181 Convencional,
10 Preso provisório e 1 Temporário**. Elas se distribuem por **155 locais**.
Essas categorias são as publicadas, sem inferir identidade ou comportamento
dos eleitores. Presídios e locais especiais não foram excluídos para melhorar
o resultado estatístico.

Os dois menores scores são de **MT/90280/0028/0200** e
**MT/90280/0028/0158**, em Confresa: **309/0** e **128/1** votos 13/22,
respectivamente. O TSE cadastra ambas no local 1120, Escola Estadual
Tapi'Itawa, bairro Zona Rural. São as duas seções desse local na projeção.
O [ATO 498/2022 do CEE/MT](https://iomat.mt.gov.br/legislacao/diario_oficial/detalhes/53767)
identifica escola de mesmo nome e município na aldeia Tapi'Itâwa, TI Urubu
Branco. Um [aviso estadual de 2025](https://iomat.mt.gov.br/legislacao/diario_oficial/detalhes/945981)
também a descreve como escola indígena nessa localidade.

A associação documental por nome/município é contexto; não identifica cada
votante. Uma subpopulação pode ter preferência muito diferente da média
municipal, que foi a referência desse score. Isso é uma hipótese concreta
de inadequação do modelo, não prova automática de lisura ou de coação.

Também foram preservados os extremos na direção oposta. O menor score
nessa direção é **AM/02674/0029/0068**, em Novo Aripuanã, com **19/81**
votos 13/22; o TSE cadastra o local E. M. São João em bairro Zona Rural.
Os registros completos de todos os casos, sem seleção partidária, estão em
[contexto-alertas.json](evidencias/contexto-alertas.json).

## Horários, biometria e comparecimento

Foram planejadas **348** associações; **342** são testáveis e **180**
passam Holm global sob a hipótese de intercambialidade dentro dos estratos.
Seis não testáveis continuam explícitas. O menor p de Monte Carlo é
0,0001; não se declara precisão inferior a isso.

Com controle por local de votação e faixa de tamanho, no agregado nacional:

- Encerramento: **r = −0,001877**, p MC **0,2484**, p Holm **1**.
  A associação não permanece significativa nesse recorte. Isso não prova
  ausência de todo efeito de horário; encerramento não é instante dos votos.
- Biometria: **r = 0,051024**, p Holm **0,0348**. É uma associação pequena
  e positiva. Com controle municipal/faixa, r fica em **0,001040**, p Holm
  **1**. O resultado depende do nível de controle, sem efeito causal provado.
- Comparecimento: **r = −0,026185**, p Holm **0,0348**.
- Brancos/nulos: **r = 0,023543**, p Holm **0,0348**.

Os coeficientes acima usam proporção de 13 nos válidos; para 22 os sinais
se invertem e os testes bilaterais são os mesmos. Significância com muitas
seções pode coexistir com efeito pequeno e heterogeneidade legítima.
Todos os resultados nacionais e por UF estão em
[associations.json](evidencias/associations.json), inclusive os nulos.

## Dígitos, percentuais arredondados e repetições

Não houve alerta global nas checagens preditivas de dígitos finais ou da
grade exata de 5%: frações corrigidas iguais a **1**. As frações não corrigidas
foram **0,812/0,277** para dígitos de 13/22 e **0,337** para a grade.
São checagens sob o modelo congelado, sem refit dos parâmetros. O resultado
não certifica os dígitos nem transforma Benford em teste de autenticidade.

Foram encontrados **54.424** perfis repetidos das quatro contagens de votos,
abrangendo **117.752** seções e **73.596** pares. Igualdade de contagens
discretas em universo grande não demonstra clonagem; todos os grupos estão
no CSV, sem atribuir uma probabilidade de colisão não modelada.

O reuso de identificadores de urna ocorre em **2 grupos e 27 seções**.
Todos esses casos são do exterior e têm **origem C, Sistema de apuração**, no
CEFT oficial. Não foram encontrados identificadores repetidos em seções
domésticas nessa projeção. Não se deduz hardware a partir de número serial.

## Controle temporal adicional, com resultado nulo

Um controle posterior comparou todos os perfis presidenciais MT 2022/t2 e
2026/t2, após conferência dos bytes originais: **7.652** seções em 2022,
**8.287** em 2026 e **7.403** chaves numéricas comuns. Nessas chaves, houve
**zero** igualdade das quatro contagens de votos. Nenhuma repetição exata
foi encontrada para as chaves comuns testadas; isso não autentica o corpus,
não investiga cópias entre chaves diferentes e não se extrapola ao país.
Chave numérica igual entre anos não garante mesma população ou local.
Todas as comparações e chaves sem par estão no
[recibo temporal](evidencias/controle-temporal-mt.json).

## O que se pode concluir

Há seções distantes da referência municipal e associações residuais que
merecem exame. Os números não autorizam chamar esses casos de milagres,
fraudes ou votos fabricados. A falta de ajuste das caudas e o contexto de
locais específicos impedem interpretar os scores nominais como chances
reais desses eventos em uma eleição íntegra.

Também não se conclui ausência de irregularidades. Os diagnósticos anteriores
dos logs continuam reprovados. A entrega é uma bateria reproduzível com
fontes, hipóteses, efeitos, resultados nulos e limitações preservados.
