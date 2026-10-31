# Bateria estatística exploratória v1

Executável `statistical_suite_2026`; protocolo e relatórios com
`format_version=1`. O escopo é a projeção presidencial 2026/t2 de 21 campos
produzida por `audit_2026`, não uma auditoria de todos os sistemas eleitorais.
O protocolo exploratório versionado antecede a execução nacional nova.

## Entrada e falhas

`--protocol JSON --output DIRETORIO_NOVO`; overrides `--sections`,
`--time-policy` e `--log-report` substituem somente caminhos. Tamanhos e
SHA-256 fixados continuam obrigatórios. Todos os campos do protocolo são
conhecidos; campos desconhecidos reprovam. `source_kind` distingue
`official_derived` de `synthetic_fixture`. A origem observada exige todas
as abrangências da política; a fixture pode ser parcial, identificada.

A leitura confere o cabeçalho canônico compartilhado, inteiros não negativos,
aritmética, biometria≤comparecimento, pleito/turno/cargo e chaves únicas
normalizadas numericamente. O SHA-256 é calculado dos bytes consumidos.
Nenhuma deduplicação é permitida. Data de encerramento preenchida deve estar
em 25/10/2026; ZZ não recebe conversão BRT. Dados inválidos, hash divergente,
limite excedido ou treino vazio reprovam com exit diferente de zero.
Saída existente nunca é sobrescrita. Parciais de falhas são preservados.

Os limites operacionais estão em `scripts/limits.env`. Parâmetros científicos
(réplicas, folds, mínimo de treino, faixa de tamanho, rho máximo e alfa)
ficam no protocolo; não são ajustados após observar os resultados.

## Matemática e reprodutibilidade

Três binomiais usam médias ponderadas por votos com regularização simétrica
Jeffreys `(K+0,5)/(N+1)`. São referências descritivas ajustadas no próprio
universo. O quarto modelo exclui todo o fold da seção do treino municipal,
com fallback UF registrado. Fold = primeiros oito bytes SHA-256 da chave,
interpretados little-endian, módulo número de folds. A chave é
`UF/município:05/zona:04/seção:04`. IDs ficam preservados nos campos de entrada.

No treino beta-binomial, `p_i=k_i/n_i`, `m=mean(p_i)`,
`v=mean(p_i²)-m²`, `a=mean(1/n_i)`;
`rho=clip((v/[m(1-m)]-a)/(1-a),0,rho_max)`. Média preditiva
`(sum(p_i)+0,5)/(S+1)`. Quando m é 0/1 ou a=1, rho=0; rho<1e-6
usa o limite binomial para estabilidade. A relação pressupõe que tamanho
e preferência latente não se correlacionem dentro do treino. Isso pode falhar.
O modelo não incorpora todas as subpopulações nem a incerteza dos parâmetros.

PMFs são construídas no log por recorrência, com log-beta de `statrs` 0.18
sem recursos opcionais. Erro de normalização maior que 1e-7 reprova; depois
da conferência, normaliza-se o erro de arredondamento, sem alterar contagens.
Score bilateral nominal = `min(1,2*min(P[X≤k],P[X≥k]))`. Holm usa todos
os pares seção×modelo com válidos positivos, no log, sem converter
underflow em p=0. Ambos os candidatos compartilham a hipótese bilateral.

PIT discreto usa `F(k-1)+U*P(k)`. Réplicas congelam o ajuste por seção e
preservam seus válidos; independência entre seções é pressuposta. As caudas
de referência não incorporam refit/variabilidade dos parâmetros. Dígitos
finais são confrontados com esse modelo, nunca automaticamente com uniforme.
No qui-quadrado de dígitos, classes excedentes, frequências inválidas ou
expectativa numérica zero com massa observada positiva reprovam explicitamente;
nenhuma classe é ignorada. Zero simultâneo de observado/esperado contribui zero.
Grade exata de 5% inclui 0% e 100%, usa aritmética inteira, sem arredondar.

Associações usam resíduos de x e y após retirar a média do estrato, com igual
peso por seção. Faixa = `válidos // size_bin_width`. Estratos também fixam
o padrão de presença das variáveis para não imputar horários. Valores
exatamente constantes recebem resíduo zero, evitando falsa variância numérica.
Proporções residuais y são permutadas por Fisher–Yates dentro do estrato,
com amostragem de índices sem viés modular. Sementes SplitMix64 por nível e
réplica são determinísticas; o RNG não é criptográfico. Candidatos têm r
opostos e o mesmo p bilateral. Singleton não adiciona covariância; cobertura
e variância zero permanecem explícitas, sem inventar p.

P MC=(b+1)/(B+1), com empates conservadores e tolerância numérica 1e-12
na correlação. Holm inclui toda a família planejada, inclusive hipóteses
não testáveis no tamanho da família. Não se usa p=0 nem se declara precisão
abaixo da resolução da simulação. Validade inferencial depende da
intercambialidade dentro dos estratos; correlação não é efeito causal.

## Saídas

- `section_scores.csv`: todos os 21 campos de todas as linhas e scores/fold/
  treino/PIT. Válidos zero têm motivo e campos de score vazios.
- `models.json`: observado/esperado, flags nominais, PIT, caudas e fallback
  nacionais e por UF, incluindo resultados sem rejeição.
- `associations.json`: todos os testes, coberturas, coeficientes e correções.
- `permutations-*.csv`: todas as réplicas; colunas não testáveis ficam vazias.
- `predictive_replicates.csv`: todas as réplicas de referência, 26 contadores.
- `repeated_urn_identifiers.csv` e `repeated_vote_profiles.csv`: todas as
  repetições no escopo indicado; perfis únicos permanecem contados no relatório.
- `report.json`: execução, protocolo efetivo, fontes, diagnósticos anteriores
  dos logs preservados integralmente, resumos e hashes dos artefatos acima.

`execution_success=true` significa que os cálculos terminaram. Não significa
que os modelos passaram na calibração ou que os logs foram conciliados.
`log_reconciliation_passed` permanece separado. Diagnósticos estatísticos
não mudam o código de execução para simular falha de transporte, nem são
convertidos em aprovação eleitoral.

O roteiro registra revisão Git limpa, ferramentas, binário e fontes. O
conferidor Python usa `math.lgamma` para scores selecionados por hash,
refaz os parâmetros de treino de todas as seções, compara todos os campos,
recalcula correlações residuais por Welford, correções e referências de todas
as réplicas. Os métodos são implementações independentes, não observações
independentes da votação. A compactação conserva os bytes das saídas;
a projeção e os indicadores continuam transformações semânticas declaradas.
