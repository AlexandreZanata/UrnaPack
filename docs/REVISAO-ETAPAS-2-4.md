# Revisão das fases 2 a 4 — MT

> Registro histórico da revisão inicial. A Etapa 4 foi posteriormente executada
> integralmente no corpus local: ver [resultado final](RESULTADO-COMPRESSAO-MT.md).
> O estado G4 parcial e os números rápidos abaixo descrevem aquele momento.

Revisão em 28/10/2026 das alterações de ingestão, contratos, pacote BU web e
benchmark deixadas pelo agente anterior. O plano continua coerente com o
objetivo de compressão máxima sob integridade e transparência. A implementação
precisava de correções antes de sustentar as garantias declaradas.

Estado: aquisição e perfil canônico corrigidos, G2 com pendência de contrato de
execução; G3 aprovado para o membro CSV identificado abaixo; G4 parcial.
A liberação analítica depende da Etapa 5. Nenhum formato de distribuição foi
escolhido ou publicado, e os originais permanecem preservados.

## Falhas corrigidas

- O produtor assumia aspas e CRLF sem confrontar a emissão com a origem;
  seu hash podia ser omitido ou apenas copiado de um argumento. A restauração
  era conferida pela CLI, sem a mesma garantia na biblioteca. O pacote v2
  calcula o hash, exige emissão idêntica e só promove saídas após aprovação.
  CSV incompatível falha; não há normalização ou perda silenciosa.
- O inverso precisava validar metadados, caminhos, inventário, hashes,
  comprimentos, truncamento e bytes residuais. Essas verificações agora
  antecedem a promoção da saída, inclusive em chamadas diretas da biblioteca.
  Variantes, duplicatas, zeros significativos, aspas, Latin-1 e campos com
  quebra interna têm regressões reproduzíveis.
- O verificador Python usava `assert`, que desaparece com `python3 -O`, e
  delimitava registros por linha física. Agora usa parser CSV independente,
  limites antes de alocar valores, confronto de cada ocorrência/valor e
  emissão/hashes; permanece ativo sob otimização.
- O benchmark comprimía novamente as colunas para obter detalhes e total,
  atribuía tempos zero a trabalho não medido e usava o tamanho inflado das
  colunas como denominador. Agora cada método comprime uma vez, mede tempos,
  registra `null` quando não houve codec e compara com os bytes do CSV original.
  O caminho escalar também passou a streaming; erros de travessia propagam.
- Benchmark de pacote salva artefatos verificados e checkpoints por método.
  Retomada exige entrada/perfil/ambiente compatíveis, revalida bytes, hashes,
  descompressão e fronteiras das colunas e recalcula taxas. Cache corrompido
  não mantém aprovação completa. Não há nova recompressão dos casos aprovados.
- Aquisição aceitava seleções inexistentes, colisões de nomes com parciais/
  recibo e destinos que eram links. A revisão adicionou preflight, preservação
  de finais divergentes, recusa de links/arquivos especiais, validação completa
  de `Content-Range`, limites corretos na retomada e promoção de parcial já
  completa somente após hash. O hash de entrada do recibo é o dos bytes do
  manifesto realmente lidos, sem releitura tardia.
- O dataset podia referenciar o hash correto de um manifesto de origem e
  declarar outros arquivos em `source_files`. Agora listas, URLs conhecidas e
  duplicatas são confrontadas. Sucesso de recibo com erros ou hashes de entrada
  incompletos reprova. A fixture v2 foi corrigida para vincular sua origem real.
- O perfil documental MT-t1 aceitava turno 2 e combinações incompatíveis de
  eleição/cargo. A validação foi alinhada ao escopo, passou a limitar evidências,
  identificar leitura completa e registrar SHA somente após EOF. Nome de membro
  repetido em ZIP reprova em vez de selecionar uma ocorrência silenciosamente.

As dependências `csv` e `brotli` introduzidas pelo agente foram mantidas: parser
de bytes com CSV real e baseline Brotli da Etapa 4. Não foi adicionada outra
dependência Rust. Limites novos estão somente em `scripts/limits.env`.

## Evidência real

Membro `bweb_1t_MT_051020261403.csv`, 411.757.026 bytes, 891.997 registros,
45 colunas. SHA-256 recomputado:
`5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3`.
É o mesmo compromisso do perfil integral no mapa estrutural de MT.

- `tsepack verify` aprovou os 13/13 arquivos contra o manifesto de origem local.
- `validate_bweb.py` revisado terminou com 891.997 chaves distintas, zero
  divergências e hash completo igual ao membro mapeado. Essa unicidade é local;
  o empacotador continua preservando ocorrências repetidas.
- Novo pacote v2 produzido; `unpack`, SHA-256 e `cmp` aprovaram a restauração.
  `verify_pack.py -O` aprovou separadamente o legado com compromisso e o v2,
  conferindo todos os valores, ordinais e bytes emitidos.
- A geração do pacote levou 10,40 s e pico RSS de 50.028 KiB; a restauração
  levou 14,28 s e 51.032 KiB, medidos por `/usr/bin/time -v` nesta máquina.
  São observações de uma execução local, sem extrapolação nacional.

No benchmark `quick` em streaming, o pacote sem codec tem 484.909.666 bytes,
incluindo manifesto: maior que o CSV por causa dos prefixos de comprimento.
Com ZSTD nível 3 por coluna tem 41.674.039 bytes (89,879% de redução frente ao
CSV); sólido tem 41.801.985 bytes. CSV direto com ZSTD nível 3 tem 45.980.515
bytes. O ganho colunar nesse nível é demonstrado no tamanho, sem demonstrar
ótimo global. Todos esses casos passaram na conferência dos bytes decodificados.

O denominador é o CSV original e as saídas colunares incluem `pack.json`.
ZIP, sidecars, mapa, recibos, originais ainda retidos e caches ficam fora dessa
comparação. Portanto, esses percentuais não representam economia total do
projeto. Os primeiros benchmarks rápidos ocorreram com outras verificações
concorrentes; seus tempos não sustentam uma comparação de desempenho isolada.
Os números antigos do encoder em memória ficam como histórico e não são
misturados aos resultados do streaming v2.

Evidências locais ignoradas pelo Git ficam em `relatorios-locais/revisao-fases/`:
`bweb-v2/pack.json`, `restored.csv`, relatórios JSON de benchmark, artefatos
`.assets`, logs de conferência e medições `.time`. Especificações executáveis:
`spec/bweb-pack-v2.md` e `spec/benchmark-v2.md`.

A rodada final aprovou **47 testes Rust** (3 biblioteca, 13 pacote/regressões,
2 determinismo, 29 integração) e **72 testes Python**, além de Clippy com
`-D warnings`, formatação, validação do repositório e 9/9 cenários do self-test.
Os testes HTTP rodaram com sockets de localhost permitidos. A retomada real
revalidou os quatro artefatos comprimidos do perfil rápido e reutilizou suas
compressões. O baseline final está em `bench-csv-v2-final.json`; o pacote,
reconferido, em `bench-pack-v2.json`. `evidence.json` consolida os vínculos e
hashes calculados dos arquivos da revisão.

## Situação dos portões e próximos passos

**G2 tem pendência real.** Dataset v2 inclui apenas um descritor de execução,
sem hash obrigatório do recibo nem verificação das suas entradas/saídas em
relação ao dataset. O validador agora bloqueia `--require-status validated`
e `published` para v2. Uma validação estrutural simples ainda pode passar;
isso não atesta execução nem libera publicação. Fechar essa pendência exige
um contrato versionado completo de recibo vinculado, antes de distribuir dados.

**G3 passou neste membro CSV.** Isso comprova restauração e equivalência lexical
no corpus testado, além das regressões sintéticas identificadas. Não comprova
identidade do ZIP baixado, outros layouts, assinaturas ou autenticidade eleitoral.
O pacote conserva hash do membro + ordinal; sua ligação ao ZIP depende do mapa
retido, e ainda precisa integrar o contrato de distribuição.

**G4 segue parcial.** O mecanismo de benchmark e retomada foi corrigido e o
perfil rápido foi executado. Falta concluir XZ/LZMA2, dicionários com conjuntos
separados de treino/avaliação, Parquet quando aplicável, demais agrupamentos,
custos permanentes/temporários, repetições e consultas Q1/Q2 medidas. O perfil
`exhaustive` com níveis 10/19 no corpus integral não foi concluído nesta revisão;
nenhum resultado para ele foi inventado ou inferido do perfil rápido.

**Etapa 5 permanece necessária antes das análises profissionais.** Conferir
igualdade do contexto por seção/cargo, cardinalidades de joins, seções agregadas,
cobertura e denominadores. Aptos e comparecimento não podem ser somados por
linha de votável. Preservação integral não substitui essas validações analíticas.

O print mostra tentativas longas e interrupção do benchmark, sem diagnóstico
do sistema que comprove a causa da morte do processo. Recompressão redundante,
ausência de checkpoint e pouca indicação de progresso agravavam o custo; foram
corrigidas. RAM reduzida e retomada testada diminuem retrabalho, sem prometer
que qualquer configuração extrema terminará em um prazo fixo.

## Reprodução

Usar entradas imutáveis, saídas novas e um único escritor por diretório:

```bash
cargo fmt --check
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/validate.py repo
python3 scripts/validate.py self-test
cargo build --release --locked --offline

# CSV extraído sem modificação do membro identificado pelo mapa:
tsepack pack --family bweb --input bweb.csv --output pacote-v2
tsepack unpack --input pacote-v2 --output restaurado.csv
cmp bweb.csv restaurado.csv
python3 -O scripts/verify_pack.py --pack pacote-v2 --original bweb.csv
python3 scripts/validate_bweb.py --csv bweb.csv --output validacao.json
tsepack benchmark --input bweb.csv --profile quick --output csv-quick.json
tsepack benchmark --input pacote-v2 --profile quick --output pack-quick.json
tsepack benchmark --input pacote-v2 --profile quick --output pack-quick.json --resume
```

Os testes HTTP usam servidor local; o ambiente deve permitir sockets de
localhost. Reprovar por bloqueio do ambiente não constitui teste aprovado.
