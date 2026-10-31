# Bateria estatística exploratória — Presidente 2026/t2

Natureza da entrada: **official_derived**. Protocolo SHA-256: `06a1cfc0870fb45dc2947cd49e06b53d7667a12f4af09a96b52567f464ccee52`.

Os mesmos critérios foram aplicados aos dois candidatos. Testes de troca de rótulos verificam a invariância dos scores bilaterais e das associações. Réplicas preditivas têm variação Monte Carlo e pressupostos de modelo declarados.

Foram preservadas **499.205 seções**; **0** não têm válidos e permanecem fora dos scores com motivo explícito. Total de comparecimento: **128.236.074**.

Integridade estrutural aprovada: `True`. Conciliação anterior dos logs: `False`. O segundo resultado não é convertido em aprovação pelos testes estatísticos.

## Referências de extremos e sensibilidade ao modelo

Contagens observadas: unanimidade 13/22 = **106/4**; estritamente >90% = **6.816/378**.

| Modelo | Unanimidade esperada 13 / 22 | >90% esperado 13 / 22 | Alertas Holm nominais: excesso 13 / 22 |
|---|---:|---:|---:|
| national_binomial | 0.03015 / 0.01608 | 0.09821 / 0.04689 | 89.248 / 73.778 |
| uf_binomial | 0.1332 / 0.04117 | 1.47 / 0.3622 | 39.155 / 29.054 |
| municipality_binomial | 0.9136 / 0.3771 | 808.5 / 24.22 | 9.686 / 5.553 |
| crossfit_municipality_beta_binomial | 10.47 / 4.333 | 4315 / 500.2 | 178 / 14 |

A diferença entre esses modelos mede sensibilidade à referência adotada. Binomial homogênea não é um modelo suficiente da composição social das seções. Alertas preditivos continuam nominais, mesmo após Holm; parâmetros estimados e dependência podem invalidar a interpretação como p calibrado.

## Calibração fora do fold

Seções válidas: 499.205; fallback municipal→UF: 63.281; rho médio ajustado: 0.0269.

| Limiar nominal bilateral | Caudas observadas | Referência N × limiar |
|---|---:|---:|
| 0.05 | 25.485 | 2.496e+04 |
| 0.01 | 7.869 | 4992 |
| 0.001 | 2.343 | 499.2 |
| 0.0001 | 1.069 | 49.92 |

Para dados discretos, a taxa nominal não é uma igualdade obrigatória. Excesso de cauda ou PIT não uniforme indica inadequação potencial do modelo; não identifica sua causa. O histograma PIT completo está em models.json para todas as UFs.

## Associações com controle geográfico e de tamanho

Família planejada: **348**; testáveis: **342**; rejeições após Holm global: **180**. Menor p de Monte Carlo representável: **0.0001**. Não se afirma precisão abaixo dessa resolução.

Os coeficientes abaixo são do candidato 13; para 22, o sinal se inverte e o teste bilateral é o mesmo. Cada linha pressupõe intercambialidade entre seções dentro do estrato. Não demonstra causalidade, voto individual ou irregularidade.

| Estrato + faixa de válidos | Variável | Seções permutáveis | Correlação residual 13 | p MC | p Holm global |
|---|---|---:|---:|---:|---:|
| municipality_size | turnout_rate | 494.890 | -0.0602371 | 0.0001 | 0.0348 |
| municipality_size | biometric_rate | 494.890 | 0.00104 | 0.4794 | 1 |
| municipality_size | invalid_rate | 494.890 | 0.0525255 | 0.0001 | 0.0348 |
| municipality_size | closing_brt_seconds | 493.758 | -0.0155391 | 0.0001 | 0.0348 |
| municipality_zone_size | turnout_rate | 494.494 | -0.0642647 | 0.0001 | 0.0348 |
| municipality_zone_size | biometric_rate | 494.494 | 0.0128101 | 0.0001 | 0.0348 |
| municipality_zone_size | invalid_rate | 494.494 | 0.052201 | 0.0001 | 0.0348 |
| municipality_zone_size | closing_brt_seconds | 493.362 | 0.00351107 | 0.0057 | 0.8151 |
| voting_place_size | turnout_rate | 442.393 | -0.0261849 | 0.0001 | 0.0348 |
| voting_place_size | biometric_rate | 442.393 | 0.0510238 | 0.0001 | 0.0348 |
| voting_place_size | invalid_rate | 442.393 | 0.0235425 | 0.0001 | 0.0348 |
| voting_place_size | closing_brt_seconds | 441.298 | -0.00187732 | 0.2484 | 1 |

Todos os resultados por UF, inclusive os nulos e não testáveis, estão em associations.json. Todas as réplicas estão nos três CSVs de permutação. Efeito pequeno pode produzir p pequeno com muitas seções; tamanho do efeito deve acompanhar o p.

## Dígitos, percentuais exatos e extremos sob referência preditiva

Não se pressupõe uniformidade dos dígitos nem Benford como certificador. As réplicas usam o tamanho real de cada seção e o ajuste beta-binomial fora do fold, com parâmetros congelados e seções simuladas independentemente. As frações abaixo são diagnósticos desse modelo, sem refazer a estimação dos parâmetros.

| Checagem global bilateral | Fração Monte Carlo | Fração corrigida por Holm, nominal |
|---|---:|---:|
| unanimity13 | 0.001 | 0.008 |
| unanimity22 | 1 | 1 |
| gt90_13 | 0.001 | 0.008 |
| gt90_22 | 0.001 | 0.008 |
| exact5percent13 | 0.337 | 1 |
| exact5percent22 | 0.337 | 1 |
| last_digit_chisq13 | 0.812 | 1 |
| last_digit_chisq22 | 0.277 | 1 |

## Controles de repetição e cobertura

Identificadores de urna repetidos: **2 grupos**, abrangendo **27 seções**; todas as chaves constam de repeated_urn_identifiers.csv. Reuso de identificador não determina hardware nem causa.

Perfis idênticos de quatro contagens de votos: **54.424 grupos**, **117.752 seções**, **73.596 pares**. Contagens inteiras repetem em universos grandes; isso não é sinônimo de clonagem. A lista completa está em repeated_vote_profiles.csv.

Sem encerramento BRT nominal utilizável: **1.308**. ZZ não recebe fuso nacional; ausência não é imputada. Seções com comparecimento igual a aptos positivos: **12**.

## Leitura dos achados

Um desvio pode representar heterogeneidade legítima, falta de intercambialidade, inadequação do modelo, problema do arquivo ou irregularidade. A bateria não distingue automaticamente essas causas. Não estima votos fraudulentos nem probabilidade de fraude e não certifica todo o processo eleitoral.

Os diagnósticos dos logs anteriores permanecem integralmente no report.json, com fonte fixada por hash. Assinaturas, relógios físicos, coação, demografia rural e transmissão não foram certificados por esta bateria.

## Reprodução e rastreabilidade

Protocolo e referências: auditoria/2026/suite/PROTOCOLO.md. Executável: statistical_suite_2026. Roteiro: scripts/reproduce_statistical_suite_2026.sh. Conferência independente: scripts/check_statistical_suite_2026.py. Todos os campos de todas as seções são confrontados; scores amostrados por hash usam uma implementação independente com math.lgamma.

section_scores.csv conserva os 21 campos de entrada e acrescenta scores no log, correções, fold, treino e PIT. É uma transformação semântica; o pacote inclui também a projeção de entrada original para repetir os bytes e cálculos. As versões completas dos dados TSE continuam vinculadas pelos manifestos da auditoria inicial.
