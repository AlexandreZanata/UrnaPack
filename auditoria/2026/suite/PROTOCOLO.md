# Protocolo exploratório da bateria estatística v1

Este protocolo é fixado antes da nova execução, depois de uma auditoria
descritiva já conhecida. Não é pré-registro prospectivo nem análise cega.
Não existe teste isolado capaz de converter uma probabilidade estatística
em probabilidade de fraude. Ambos os candidatos recebem as mesmas regras.
Serão publicados resultados nulos, desvios, falhas de calibração e cobertura.

## Universo e controles

Projeção presidencial nacional 2026/t2, incluindo ZZ, vinculada aos BU web
pelos manifestos da auditoria anterior. Entrada de 47.457.542 bytes, SHA-256
`259922561b38cb87c7847566ae667892272a6e103375ea3d817bfd1030339999`.
Os 21 campos, chaves, inteiros, aptos=comparecimento+abstenção, soma dos votos,
biometria≤comparecimento e denominadores são conferidos. Chaves duplicadas,
campo desconhecido, hash divergente e estouro de limite reprovam. Contadores
de denominadores nulos e horário ausente são explícitos. A projeção não contém
os eleitores individualizados nem comprova votação física/assinaturas.

## Famílias definidas antes da execução

1. Integridade e consistência; reuso de identificadores de urna e perfis
   repetidos de votos, com contagem de multiplicidades, sem concluir sua causa.
2. Distribuições conjuntas de comparecimento e voto, tamanho das seções,
   extremos, unanimidade, dígitos e percentuais exatamente múltiplos de 5%.
3. Referências binomiais nacional, por UF e município, deliberadamente
   simples: medem sensibilidade à composição geográfica, não fraude.
4. Modelo beta-binomial municipal em cinco folds definidos por SHA-256 da
   chave. A seção avaliada não participa do ajuste do seu fold. Municípios
   com menos de 30 seções de treino usam a UF de treino; fallback é contado.
   Momentos das proporções, com correção do ruído binomial, estimam a
   sobredispersão. A média recebe regularização simétrica e rho fica em
   [0;0,95]. Dependência entre seções e incerteza dos parâmetros continuam
   limitações. PIT aleatorizado e taxas de cauda fora do fold verificam ajuste.
5. Scores preditivos bilaterais por seção nos quatro modelos. Holm é aplicado
   ao conjunto completo modelo×seção; complementos dos dois candidatos são
   a mesma hipótese bilateral. Scores são nominais sob modelos estimados:
   uma rejeição pode revelar inadequação do modelo. Log-probabilidades evitam
   apresentar underflow numérico como probabilidade exatamente zero.
6. Associações bilaterais entre proporção de votos válidos e comparecimento,
   taxa de biometria não habilitada, taxa de brancos/nulos e encerramento BRT
   nominal. Correlação residual por estrato: município, município/zona e local
   de votação; cada um também condicionado a faixas de 50 votos válidos.
   Permutações de proporções apenas dentro desses estratos, 9.999 por nível.
   Isso pressupõe intercambialidade dentro dos estratos, sem causalidade.
   Estratos unitários e variância zero têm cobertura explícita, sem p fictício.
7. Holm único para todas as associações nacionais e por UF, em todos os três
   níveis e quatro variáveis. Alfa familiar 0,05. P de Monte Carlo=(b+1)/(B+1),
   nunca zero. A resolução e seu limite para múltiplos testes são declarados.
8. Referências preditivas de dígitos finais, unanimidade, >90% e grade de 5%,
   condicionadas ao tamanho real e ao modelo beta-binomial ajustado fora do
   fold. 999 réplicas independentes sob parâmetros congelados. Oito checagens
   globais bilaterais com Holm; são diagnósticos de modelo, não p-valores
   calibrados de integridade eleitoral. Primeiro dígito/Benford é descritivo.
9. Os diagnósticos anteriores dos logs são incorporados com SHA-256 e escopo
   preservados; não são apagados nem convertidos em aprovação estatística.

Todas as análises usam igual peso por seção, salvo probabilidades condicionais
ao número de votos e totais explicitamente ponderados. Encerramento não mede
horário individual dos votos. ZZ não recebe fuso nacional e é excluído apenas
da variável de horário. Não se presume normalidade das proporções ou
uniformidade dos dígitos finais. Não há classificação rural, hardware inferido
de número serial, causalidade, prova de coação ou identificação de votantes.

## Implementação e verificação

Rust no núcleo; automações Python em `scripts/`. Reutilizar leitores, hashes,
publicação atômica e limites. Uma dependência matemática sem recursos opcionais
(`statrs` 0.18) fornece log-beta testado, evitando implementar funções especiais
ad hoc. Esse é o ganho demonstrado da dependência; RNG próprio é apenas o
SplitMix64 determinístico para simulação, sem função criptográfica.

Testes executáveis: enumeração binomial pequena, beta-binomial uniforme,
normalização, simetria de candidatos, correção Holm, permutação exata pequena,
repetição com mesma semente, corrupção/duplicata/saída existente e controles
sintéticos identificados de calibração e injeção. Um conferidor independente
relê a projeção e as saídas. Fixtures e simulações não são resultados eleitorais.

Serão conservados CSVs completos de scores, todos os testes, distribuição das
réplicas, parâmetros, protocolo, ambiente, hashes e relatório. Um alerta que
não resista à mudança de modelo será descrito como sensível ao modelo; nem
alertas nem ausência deles certificam todo o processo eleitoral. Não se ajustam
cortes ou sementes depois de observar os resultados para produzir conclusão.

## Fundamentação consultada

- [Phipson e Smyth, 2010](https://pubmed.ncbi.nlm.nih.gov/21044043/): cálculo
  de p em permutações amostradas e resolução finita.
- [Documentação R, p.adjust](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html):
  Holm e controle familiar sob dependência arbitrária, desde que os p sejam válidos.
- [Stan, distribuições discretas limitadas](https://mc-stan.org/docs/functions-reference/bounded_discrete_distributions.html):
  modelos binomial e beta-binomial.
- [Deckert, Myagkov e Ordeshook, 2011](https://doi.org/10.1093/pan/mpr014):
  limitações de Benford em eleições.
- [Klimek et al., 2012](https://doi.org/10.1073/pnas.1210722109): importância
  de mecanismos, heterogeneidade e escala de agregação na perícia estatística.
