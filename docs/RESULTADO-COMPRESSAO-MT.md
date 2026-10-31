# Resultado final da compressão — MT

**G4 concluído em 28/10/2026 para o acervo local baixado.**
Foram processados 13 arquivos de origem; o mapa continua
declarando t2 parcial. Não é uma afirmação de cobertura nacional.
Matriz e reprodução: [Etapa 4](ETAPA-4.md).

## Representação escolhida

- **Evidência completa:** TAR sólido + **zstd-19**. O arquivo FORENSIC
  tem 1.621.324.849 bytes,
  incluindo manifesto, recibo vinculado e descritor. A alternativa por fonte
  teve 1.629.456.419 bytes.
- **Bundle mínimo portátil:** 1.622.018.772 bytes,
  contra 1.635.287.528 bytes dos downloads originais:
  **0,8114%** de redução líquida,
  incluindo 689.263
  bytes de proveniência comprimida e a receita da view.
- **BU web para materialização:** **bweb-xz-9e**. CSV de
  411.757.026 bytes → 11.644.396
  bytes de payload; 11.645.135 com o descritor:
  **97,1718%** de redução, sem mudar nenhum byte do CSV restaurado.

O ganho adicional sobre o acervo bruto é pequeno porque os downloads já estavam
majoritariamente em ZIP. A redução do membro CSV é outra comparação e não é
apresentada como economia total dos ZIPs. O CSV não substitui o ZIP original;
o arquivo FORENSIC preserva todos os downloads e sidecars byte a byte.

O cache BU web é regenerável e fica **fora do bundle mínimo**. Mantê-lo soma
11.645.135 bytes. Os originais não
foram apagados: originais + bundle ocupam logicamente
3.257.306.300 bytes, sem contar
intermediários do experimento nem caches de outras etapas. Não houve alegação
de espaço físico liberado no disco.

## Comparações e controles executados

59 casos completos de codec/Parquet passaram no round-trip, mais
8 perfis ZSTD colunar/sólido
do benchmark exhaustive. Nenhum candidato desta execução foi interrompido ou
tratado como completo sem conferência; Brotli máximo terminou naturalmente.

O menor Parquet testado foi `parquet-g65536-z19`, com
26.300.809 bytes no mesmo contrato de restauração lexical;
ZSTD19 sólido do modelo colunar teve 25.544.850 bytes.
Brotli11 teve 13.725.810 bytes com descritor. A forma
convencional escolhida superou essas alternativas em bytes; o formato colunar
experimental não foi escolhido para armazenamento mínimo.

Treino, validação e teste de dicionário tiveram, respectivamente,
540.624,
170.005 e
181.368 registros, com grupos
de seção disjuntos. Dicionário selecionado: 32.768
bytes, contabilizados nas comparações; teste não participou da seleção.

Q1, Q2 e recuperação localizada produziram resultados idênticos em **18
baterias de consultas**, com três repetições por representação. Q2 verifica
contexto igual e conta comparecimento uma vez por seção presidencial, sem
somar por votável. O teste localizado cobre a primeira chave real; não é um
benchmark nacional de acesso aleatório.

Mediana da bateria CSV: 1,308 s.
Menor mediana observada: `parquet-g65536-z3`,
0,707 s. Inicialização e checagens de
integridade estão incluídas, cache do SO não foi esvaziado e outros trabalhos
da máquina não foram controlados. Pico RSS amostrado máximo entre os casos:
679,51 MiB; soma de processos, não pico global do sistema.

## Provas de restauração

Os 13 arquivos foram restaurados e aprovados contra o
manifesto original. Decodificação e hashes do arquivo final foram repetidos
três vezes, além da restauração real em disco.

A view escolhida foi comprimida três vezes com o mesmo SHA-256 de saída.
Depois, o cache foi **regenerado a partir do bundle**: downloads restaurados,
ZIP e membro conferidos por hash/ordinal, CSV extraído e recomprimido. O CSV
restaurado dessa regeneração passou em SHA-256 e `cmp` contra o original.
São 891.997 registros e 45 campos preservados.

SHA-256 do membro CSV:
`5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3`.

Verificações de software: **55 testes Rust e 79 testes Python**,
Clippy com `-D warnings`, formatação, validação do repositório, 9/9 cenários
do self-test e schema do recibo. Fixtures são sintéticas identificadas, com
hashes reais; nenhuma métrica de dados foi inventada.

## Artefatos e uso

Artefatos locais, ignorados pelo Git: `relatorios-locais/etapa-4-completa/`.
O pacote portátil é `final/`; o seu descritor é `final/bundle.json`.
Evidências: `stage-report.json`, `final-validation.json`, comparações de views,
queries, dicionários, casos individuais e logs.

Usar saídas novas:

```bash
./target/release/tsepack archive verify \
  --input relatorios-locais/etapa-4-completa/final/forensic-mt
./target/release/tsepack restore \
  --dataset relatorios-locais/etapa-4-completa/final/forensic-mt \
  --output relatorios-locais/mt-restaurado-novo
python3 scripts/compression_stage.py materialize-view \
  --input relatorios-locais/etapa-4-completa/final/bundle.json \
  --output relatorios-locais/cache-bweb-novo
python3 scripts/compression_stage.py restore-view \
  --input relatorios-locais/cache-bweb-novo/view.json \
  --output relatorios-locais/bweb-novo.csv
```

O arquivo local v2 fecha o vínculo criptográfico do seu recibo. Publicação no
manifesto de distribuição antigo continua bloqueada e não foi executada.
A Etapa 5A executou a análise descritiva do BU web de MT 2026 t1 a partir deste
cache; votos e contexto foram aprovados, enquanto contagem de seções físicas
(`DS_SECOES_AGREGADAS`), joins/reconciliação, comparação entre turnos e modelos
permanecem bloqueados ou não executados. Ver `docs/ETAPA-5A.md`. Expansão
nacional na Etapa 6. As garantias aqui são de preservação, reprodução e
controles descritos, sem conclusão sobre autenticidade eleitoral.
