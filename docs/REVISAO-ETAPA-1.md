# Revisão técnica da Etapa 1 — implementação validada após correções

Data: 28/10/2026. Escopo: `docs/ETAPA-1.md`. A revisão cobre as alterações da
primeira entrega, suas regressões e execução no acervo local de MT. Não é
validação de transformação semântica nem de resultados eleitorais.

## Resultado

**Etapa 1 tecnicamente validada dentro do seu escopo após as correções abaixo.**
Os testes da primeira entrega passavam, mas não cobriam falhas de inventário,
proteção da origem, finalização dos relatórios e limites efetivamente aplicados.
Esses casos foram reproduzidos por regressões antes das correções.

A base preserva o manifesto de origem v1 válido. O mapeador preserva a interface
e os campos existentes do mapa v1, acrescentando frequências por coluna de
escopo, bytes efetivamente lidos e finais de linha. A etapa não introduz
transformação eleitoral, formato de compressão próprio ou parser ASN.1.

## Falhas encontradas e correções

1. **Travessia incompleta aprovada pelo mapeador:** `os.walk` não tinha tratamento
   de erro. Um diretório sem permissão era omitido e a execução concluía com
   sucesso. Agora erros de travessia/metadata propagam reprovação; nomes de
   diretórios vazios também são validados, inclusive representabilidade UTF-8.
2. **Escrita na origem por alias:** a comparação lexical da saída não detectava
   um symlink apontando para os brutos. Agora as raízes são resolvidas antes de
   qualquer escrita e precisam ser árvores separadas. Links nos destinos de
   artefatos são rejeitados; teste confirma que o arquivo da fonte não muda.
3. **Mapa completo remanescente ou misturado após falha:** a tentativa inválida
   podia deixar `map.json` de uma execução anterior; o mapa também era publicado
   antes dos membros e o erro de escrita do recibo era apenas impresso. Agora
   gerações anteriores são preservadas em `.previous-*`, o recibo deve ter sido
   escrito e `map.json` é publicado por último. Falhas deixam diagnóstico e
   recibo de reprovação, sem mapa completo atual. A falha de publicação foi
   injetada em teste e a geração anterior permaneceu byte a byte preservada.
4. **Limites ineficazes ou divergentes:** o CSV continuava após exceder limite,
   acumulando erros; o limite interno padrão de campo do Python divergia do
   configurado. Agora a leitura interrompe na falha, configura/restaura o limite
   do parser e controla bytes lexicais do registro antes de materializar a linha,
   incluindo aspas e finais de linha. Valores de escopo retidos têm orçamento
   de bytes centralizado. A razão de expansão é comparada sem arredondamento.
5. **Classificação e nomes ZIP:** um ZIP com outra extensão não era catalogado.
   A descoberta agora usa sua assinatura. Caminhos com drive Windows, segmentos
   ambíguos e nomes truncados por NUL reprovam; não há escolha silenciosa de nome.
6. **Evidências incompletas/imprecisas:** escopos tinham valores distintos sem
   frequências; amostras liam um byte extra não refletido no contador; relatórios
   genéricos afirmavam `logd.dat` mesmo sem examinar aquele conteúdo. Frequências
   agora vêm dos registros, bytes de amostra correspondem à leitura e limitações
   de `.jez` são condicionais à amostra realmente encontrada. Membros CSV só
   recebem hash integral após EOF sem erro e tamanho lido conferido.
7. **Coerência Rust e testes:** diretórios vazios com nomes não UTF-8 eram
   ignorados e o construtor podia produzir caminho com barra invertida que o
   verificador recusava. A validação foi unificada, com rejeição de prefixos
   Windows/NUL. O carregamento do manifesto reutiliza a guarda de versão.
   O teste de ordenação passou a construir um manifesto de arquivos reais de
   fixtures; a regressão CLI de hash agora altera bytes mantendo o tamanho.
   Testes que usam APIs Unix estão condicionados à plataforma.
8. **Documentação e recursos:** corrigidas afirmações sobre rejeição de campos
   adicionais que o JSON v1 ainda não implementa, descrição de dependência de
   schema e status dos recursos. Arquivos de testes/validador são fechados
   corretamente, eliminando os avisos de recursos não fechados observados.

## Verificações executadas

- `cargo fmt --check`: aprovado.
- `cargo check --locked --offline --all-targets`: aprovado.
- `cargo clippy --locked --offline --all-targets -- -D warnings`: aprovado.
- `cargo test --locked --offline`: **28 testes**, sem falhas: 3 de biblioteca
  (incluem os 2 de hash), 2 de determinismo/benchmark e 23 de integração.
- `python3 -m unittest discover -s scripts -p 'test_*.py'`: **35 testes**,
  sem falhas: 33 do mapeador e 2 do validador. Erros injetados e a criação de
  nome ZIP duplicado fazem parte dos cenários negativos, que reprovam como esperado.
- `python3 scripts/validate.py repo`: aprovado.
- `python3 scripts/validate.py self-test`: **9/9 cenários** aprovados.
- `git diff --check`: aprovado.
- `cargo build --release --locked --offline`: aprovado.
- `tsepack verify` contra o manifesto de origem local: **13/13 arquivos**
  aprovados, SHA-256 recomputado dos bytes.
- Os **5 sidecars SHA-512** locais foram confrontados com seus arquivos por
  `sha512sum --check`, todos aprovados. Isso verifica correspondência com o
  sidecar disponível, sem equivaler a validação de assinatura ou cadeia oficial.

O número de testes Rust não soma os testes de hash novamente aos de biblioteca.
Nenhum cenário não executado é apresentado como aprovado.

## Execução real e reprodução

O mapeador corrigido foi executado com as mesmas fontes de MT em duas saídas:

```bash
python3 scripts/map_raw_data.py \
  --source dados/brutos/2026 --year 2026 --scope MT \
  --output relatorios-locais/etapa-1/mt
python3 scripts/map_raw_data.py \
  --source dados/brutos/2026 --year 2026 --scope MT \
  --output relatorios-locais/etapa-1/mt-recheck
cmp relatorios-locais/etapa-1/mt/map.json \
    relatorios-locais/etapa-1/mt-recheck/map.json
cmp relatorios-locais/etapa-1/mt/members.jsonl \
    relatorios-locais/etapa-1/mt-recheck/members.jsonl
```

As duas comparações passaram byte a byte. Em cada execução foram inventariados
**13 arquivos físicos**, **41.458 membros** e **9 CSVs** com leitura integral.
Tempos medidos ficam em `run.json`; não representam benchmark de compressão.

Conferências adicionais dos artefatos:

- hash de `members.jsonl` recomputado com `sha256sum` e confrontado com o mapa;
- os 41.458 membros comparados novamente com os diretórios centrais dos ZIPs:
  fonte/ordinal, nome, tamanho declarado, tamanho comprimido e CRC;
- SHA-256 dos 9 CSVs recomputado por `unzip -p` + `sha256sum`, sem usar o leitor
  e o acumulador de hash do mapeador; todos coincidem com os perfis;
- soma das frequências de cada coluna de escopo igual à quantidade de registros
  do respectivo perfil; bytes CSV lidos iguais ao tamanho do membro;
- recibo confere o SHA-256 do script executado e registra a versão do ambiente.

As frequências agora tornam reproduzível a separação de registros por eleição.
Igualdade de contagens entre fontes não comprova igualdade de seus registros ou
votos: reconciliação permanece pendente.

## Artefatos e arquivos para revisão

Relatórios locais ignorados pelo Git:

- `relatorios-locais/etapa-1/mt/map.json` e `members.jsonl`: conteúdo determinístico.
- `relatorios-locais/etapa-1/mt/report.md`: resumo legível.
- `relatorios-locais/etapa-1/mt/run.json`: comando, produtor, ambiente e tempos.
- `relatorios-locais/etapa-1/mt-recheck/`: repetição usada na comparação.
- `.previous-*` dentro de cada saída: gerações anteriores preservadas.

Implementação: `src/traverse.rs`, `src/manifest.rs`, `src/inspect.rs`,
`src/verify.rs`, `scripts/map_raw_data.py`, `scripts/validate.py` e limites em
`scripts/limits.env`. Regressões: `tests/integracao.rs`, testes de biblioteca e
`scripts/test_*.py`. O dicionário inicial continua em `docs/DADOS-BRUTOS.md`.

## Limites e critérios G1

- [x] Erros delimitados de inventário, versão, caminhos e integridade reprovam.
- [x] Manifesto de origem válido de MT continua verificável.
- [x] Mapeador executado em MT e artefatos determinísticos comparados.
- [x] Hashes CSV e catálogo confrontados por caminhos independentes.
- [x] Regressões exercitam operações e falhas, incluindo falha na finalização.
- [x] Revisão técnica da implementação e correções concluídas.

Continuam fora da garantia desta etapa: unicidade de chaves de negócio,
cardinalidades de joins, equivalência semântica, reconciliação entre fontes,
decodificação ASN.1/logs, assinatura digital e completude eleitoral/nacional.
Campos adicionais do manifesto JSON de origem v1 ainda são ignorados; não
transportar novas garantias neles. Sua política e o vínculo entre manifestos
exigem a evolução versionada prevista para a Etapa 2.

Fonte deve permanecer imutável durante a leitura e deve haver um único escritor
por saída; não há garantia contra substituições concorrentes ou escritores
simultâneos. Opacos `metadata_only`/`sampled` não passam a ser decodificados ou
verificados integralmente por estarem em um mapa `complete`. Não foi medida
viabilidade nacional em 32 GB nem taxa de compressão especializada.

A revisão valida tecnicamente o escopo G1. A Etapa 2 permanece uma entrega
separada, com seus próprios contratos e critérios de aceitação.
