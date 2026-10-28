# Etapa 1 — verificações básicas e mapeamento de MT

## Missão e limite da entrega

Entregar uma base que reprove as falhas de integridade delimitadas abaixo e um
mapa estrutural reproduzível dos dados já baixados de MT. Esta etapa não produz
dados eleitorais tratados nem comprova a semântica completa. Sua conclusão será
revisada antes de iniciar ingestão gerenciada, transformação ou otimização.

Trabalhar sequencialmente em três incrementos: correções/testes, mapeador/testes,
execução real/documentação. Reutilizar `src/` e automações existentes; evitar
refatorações laterais. Rust continua a linguagem de produção, Python em
`scripts/` serve somente à automação de inventário ZIP/CSV.

## Entrada disponível

- Fontes, somente leitura: `dados/brutos/2026/`.
- Manifesto de origem existente: `dados/manifest-2026-mt.json`.
- Contexto da instalação: `dados/LEIAME-LOCAL.md`; não copiar caminhos físicos
  ou o inventário da máquina para arquivos versionados.
- Referência estrutural: `docs/DADOS-BRUTOS.md`, baseada em membros reais.
- Regras: `AGENTS.md`, `docs/PLANO.md`, `docs/ARQUITETURA.md` e
  `docs/VERIFICACAO.md`.

Não baixar nem alterar brutos/manifesto existente. Não assumir que a localização
em `t1` restringe todos os membros ao primeiro turno. Descobrir todos os ZIPs
presentes e sidecars por varredura, sem lista de arquivos codificada em código.

## E1.1 — Corrigir a base com regressões reais

1. `inspect` e construção do manifesto: raiz inexistente, raiz que não é
   diretório, erro de travessia/metadata/leitura ou nome não representável sem
   perda precisam reprovar explicitamente. Eliminar `filter_map(e.ok())`,
   tamanho substituído por zero e conversões de caminho com perda. Raiz vazia
   pode ter inventário vazio explícito, mas não é dataset pronto; `verify` de
   manifesto sem arquivos continua reprovando.
2. Compartilhar a política de travessia entre inventário e manifesto sem
   criar um framework. Permitir link legítimo na raiz, após sua resolução;
   rejeitar symlinks internos e arquivos especiais, sem ignorá-los.
3. `verify`: rejeitar `format_version` não suportado, caminhos vazios,
   absolutos, com `..` ou representações relativas não canônicas, duplicatas
   de caminho e symlinks internos/componentes que escapem da raiz. Duplicata
   de caminho de manifesto é diferente de duplicata eleitoral legítima.
4. Preservar leitura de manifestos de origem v1 válidos e determinismo dos
   manifestos gerados. Não confundir origem Rust com dataset de distribuição.
   Esta etapa não redesenha campos/discriminadores desses contratos; essa
   evolução e a política completa de campos adicionais ficam na Etapa 2.
   Não transportar novas garantias em campos extras silenciosamente ignorados.
5. Corrigir `scripts/validate.py`: acumular erros do repositório e do índice,
   sem substituir os anteriores. Na falta de `jsonschema`, validação que exige
   schema completo deve reprovar com instrução explícita sobre a dependência
   já usada na CI; não afirmar que o fallback parcial foi validação completa.
6. Testar corrupção com o mesmo tamanho, ausente, truncado, manifesto vazio,
   versão incompatível, caminho repetido, travessia, symlinks, raiz inexistente
   e propagação de erro de leitura. Executar testes de CLI para checar exit ≠ 0
   nos casos inválidos, além de testes de biblioteca pertinentes.
7. Corrigir, ao tocar os testes de manifesto, o uso atual de hashes fictícios
   como `"x"`: usar bytes de fixtures identificadas e hashes calculados. Não
   apenas testar uma ordenação manual como prova da construção do manifesto.

Não prometer segurança contra alteração concorrente de arquivos sem mecanismo
apropriado; registrar a exigência de fonte imutável durante a verificação.
Mudança incompatível de formato, se inevitável, requer versão/teste/spec antes
de continuar; não aproveitar esta etapa para desenhar um formato novo.

## E1.2 — Mapeador de automação, sem transformação eleitoral

Criar `scripts/map_raw_data.py`, com biblioteca padrão e reaproveitamento das
rotinas de hashing/limites já existentes em `scripts/` quando apropriado.
Interface implementada em `scripts/map_raw_data.py`:

```bash
python3 scripts/map_raw_data.py \
  --source dados/brutos/2026 \
  --year 2026 --scope MT \
  --output relatorios-locais/etapa-1/mt
```

A raiz pode ser um link legítimo; não seguir links internos. O `--source` é a
raiz do corpus a inventariar, não uma lista fixa de UFs. `--year` e `--scope`
identificam o recorte solicitado; conteúdo divergente/misto é documentado e
não é descartado para forçar concordância. Recusar saída dentro da fonte.

Saídas locais requeridas:

- `map.json`: `artifact_kind: raw_structure_map`, `format_version: 1`,
  parâmetros lógicos, fontes relativas e SHA-256, perfis CSV, cobertura por
  nível e limitações; inclui hash do arquivo de membros gerado.
- `members.jsonl`: uma entrada por membro do diretório central, em ordem
  determinística por fonte e ordinal; sem manter todo o corpus em memória.
- `report.md`: resumo legível de layouts, escopos, problemas e pendências;
  distinguir observações, documentação, hipóteses e verificações.
- `run.json`: comando, ambiente, versões e tempos medidos; campos variáveis
  de execução ficam aqui, separados do conteúdo determinístico do mapa.

Adicionar `/relatorios-locais/` ao `.gitignore`; os resultados da instalação
não são versionados. Documentação de layouts e código são versionáveis.
Não escrever em `dados` nem extrair caminhos do ZIP no disco. Usar temporários
na área de saída e só finalizar os artefatos após sucesso; falha não deixa
um mapa final marcado como completo. Diagnóstico parcial deve ser identificado.
Na implementação revista, a geração anterior é preservada em `.previous-*`;
`map.json` é publicado por último. Manter um escritor por saída e verificar
o hash do catálogo referenciado antes de consumir o mapa.

### Inventário de arquivos e membros

- Recomputar SHA-256 de todos os arquivos físicos do corpus; registrar tamanho
  medido e tipo. Confrontar com o manifesto local de origem em execução separada.
- Catalogar cada membro ZIP por hash da fonte + ordinal + nome. Registrar
  método, flags, diretórios, tamanho/CRC declarados e extensão, sem tratar
  metadado do ZIP como bytes lidos ou integridade de conteúdo verificada.
- Nomes duplicados, caminhos inseguros, cabeçalhos ambíguos, erros e limites
  excedidos reprovam explicitamente; o diagnóstico preserva a identificação das
  ocorrências. Nunca usar seleção do primeiro/último membro por nome.
- Binários e PDFs ficam opacos nesta entrega. Identificar uma amostra
  determinística e limitada por família quando necessário para formato mágico;
  registrar `sampled`, nome/ordinal e bytes efetivamente lidos.
- `.jez` não implica decoder 7z: a amostra de MT examinada era ZIP com `logd.dat`.
  Registrar aninhamento como pendência; não expandir recursivamente nesta etapa.
- Hash de membro só existe se calculado dos bytes completos. Para leitura
  parcial/metadados, usar ausência/null documentada com estado correspondente,
  nunca digest, tamanho medido ou contagem de registros inventados.

### Perfis dos CSVs

- Comparar o cabeçalho completo/ordenado com as famílias documentadas; variantes
  desconhecidas geram diagnóstico e reprovação, sem eliminar campos ou membros.
- Usar `csv` com `;`, regras de aspas e Latin-1 conforme a fonte; preservar
  strings e valores lexicais. Nenhum casting para float ou normalização.
- Ler **todos** os registros CSV em streaming. Contar registros lógicos,
  conferir número de campos e informar ordinal e linhas físicas em divergência.
- Registrar conjuntos/contagens dos campos de escopo realmente presentes
  (ano, turno, eleição/pleito, abrangência e cargo) e frequências das sentinelas
  lexicais por coluna. Campo não presente não recebe valor inferido como observado.
- Definir fingerprint de layout como SHA-256 do JSON UTF-8 do array ordenado
  de nomes, `ensure_ascii=False`, separadores `(',', ':')`, sem newline final.
  Distinguir esse fingerprint de SHA-256 do membro CSV inteiro.
- Contabilizar SHA-256 dos bytes completos dos CSVs durante a leitura, sem
  carregar o membro inteiro ou fazer leituras repetidas desnecessárias.
  Completar leitura até EOF para que erros de conteúdo/CRC sejam observáveis.
- Valores de conjuntos, tamanho de registro/campo e expansão têm limites
  centralizados em `scripts/limits.env`. Limite atingido não vira contagem
  exata truncada nem sucesso parcial silencioso.

O mapeador não calcula unicidade de chaves de negócio, equivalência BU×RDV,
assinatura digital, agregações eleitorais ou taxa de compressão. Seus contadores
são de objetos e registros realmente lidos, com definição explícita.

## E1.3 — Testes, execução em MT e documentação de retorno

Criar testes automatizados das automações em `scripts/test_*.py`, executáveis
por `python3 -m unittest discover -s scripts -p 'test_*.py'`. Incluir esse comando
na CI existente sem alterar permissões ou pins das actions.

Fixtures sintéticas identificadas em `tests/fixtures/`, pequenas e com hashes
reais dos bytes. Criar contêineres temporários a partir delas para testar:

- ZIP com CSV válido, texto Latin-1 com acentos, quoting, newline em campo,
  sentinelas e campo vazio; cabeçalho e contagens corretos;
- schema/cabeçalho desconhecido ou duplicado, linha com campos divergentes,
  ZIP inválido/truncado, nomes repetidos e path traversal;
- limite realmente aplicado, raiz/link legítimo e link interno reprovado;
- metadado declarado diferente de bytes lidos; leitura parcial sem hash completo;
- repetição da execução gerando `map.json` e `members.jsonl` byte a byte iguais;
- validador preservando erro anterior mesmo com índice válido, e falhando
  explicitamente quando a validação completa de schema não está disponível.

Executar as verificações no acervo real após os testes pequenos. Conferir se os
novos perfis revelam CSV com vários turnos/eleições; não inventar essa conclusão
pela pasta. Atualizar `docs/DADOS-BRUTOS.md` com diferenças observadas e um
**dicionário estrutural por campo**: posição/nome, significado documental,
tipo candidato, unidade/medida, sentinelas, chave/join candidato, evidência e
pendências. Não transformar hipótese em esquema canônico aprovado.

Criar `docs/REVISAO-ETAPA-1.md` ao concluir: resumo das mudanças, comandos e
resultados efetivos, referência relativa aos relatórios locais, diferenças de
layout descobertas, limitações e checklist G1. Não copiar caminhos físicos,
linhas reais ou o inventário de downloads para esse resumo versionado.

## Verificações e encerramento

```bash
cargo fmt --check
cargo check --locked --offline --all-targets
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/validate.py repo
python3 scripts/validate.py self-test
cargo build --release --locked --offline
./target/release/tsepack verify \
  --manifest dados/manifest-2026-mt.json --source dados/brutos/2026
python3 scripts/map_raw_data.py \
  --source dados/brutos/2026 --year 2026 --scope MT \
  --output relatorios-locais/etapa-1/mt
```

Se dependência/ambiente impedir algum comando, registrar a falha exata e
continuar os trabalhos independentes; não declarar o portão concluído. Teste
que não exercitou a verificação não pode ser apresentado como aprovado.

G1 exige E1.1–E1.3 executados, artefatos reais reproduzíveis e pendências
explicitadas. Parar ao concluir esta etapa; preparar relatório para revisão.
Não implementar downloader, formato próprio, Parquet/Arrow, parser ASN.1,
`restore`, modelos estatísticos, publicação, commit ou push nesta entrega.
