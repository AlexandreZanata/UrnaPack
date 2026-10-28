# Plano de execução — Fases 1–7

## Onde estamos

**Base v0.1 entregue**: CLI com `inspect`/`benchmark`/`verify` funcionais,
manifesto v1, testes (unit + integração + round-trip + determinismo +
corrupção/ausência). Todo o resto abaixo é trabalho futuro — os subcomandos
correspondentes falham explicitamente até sua fase.

## Fase 1 — Investigação (próxima)

1. Localizar datasets 2026 (BU, RDV, logs, votação/totalização, CSVs,
   assinaturas, correspondências) nas fontes oficiais; ler ASN.1 antes de decodificar.
2. Amostrar MT + outras UFs, turnos e formatos variados (nunca só pequenos/compressíveis).
3. Rodar `tsepack inspect` + `benchmark --profile exhaustive` na amostra.
4. Entrega: relatório quantitativo (tipos, tamanhos, entropia aproximada,
   redundância intra/inter-arquivos, campos de baixa cardinalidade).
5. Critério de saída: saber **onde está a redundância** com números.

## Fase 2 — Baselines

1. Implementar `download` (hash no ato, manifesto, metadados HTTP, checkpoints/retomada).
2. Estender `benchmark`: ZSTD níveis altos + dicionários treinados (amostras
   treino/teste separadas), LZMA2/XZ, Brotli, Parquet+ZSTD, compressão sólida.
3. Registrar por método: tamanhos, razão, economia, tempos, pico RAM, temp,
   velocidade de leitura, tempo de consultas, integridade — separados por
   BU/RDV/logs/CSVs/binários/já-comprimidos.
4. Critério de saída: tabela de baselines reproduzível; **nenhum formato próprio
   antes de demonstrar oportunidade sobre o melhor baseline**.

## Fase 3 — Formato especializado

1. Dicionários globais/locais (medir com custo do dicionário incluído).
2. Diferencial: delta/delta-of-delta, VarInt, bit packing, RLE,
   frame-of-reference, colunar, timestamps.
3. Separação template×parâmetros em logs; deduplicação exata (hash) sem fundir
   ocorrências eleitorais distintas; layouts por eleição→seção; colunar×registros.
4. Regra de corte: técnica que não pagar sua complexidade em bytes é removida.
5. Perfis: `optimize --mode forensic` (reversível total) e
   `optimize --mode analytical` (mínimo auditável, perdas declaradas).

## Fase 4 — Verificação

`restore` + Níveis 2–5: manifestos de equivalência, Merkle sob demanda,
verificador com reexecução determinística, round-trip SHA-256, `report`
(JSON+texto). Testes: property-based, fuzz de parsers, truncados, campos
desconhecidos, compatibilidade, duplicatas, corrompidos, interrupção, regressão.

## Fase 5 — MVP (MT real) → Fase 6 — Escala nacional → Fase 7 — Otimização extrema

- F5: ponta a ponta em MT (todos os tipos + exceções), verificações aprovadas.
- F6: todas UFs/turnos em 32 GB com streaming, lotes, limites e retomada.
- F7: busca sistemática na fronteira Pareto (tamanho×tempo×RAM); só entra
  melhoria reproduzível (dicionários globais, sólida, layouts, dedup entre arquivos).

## Critérios de aceitação (resumo do §14)

Arquivos reais processados; economia comprovada vs baselines; consultas
eficientes; assinaturas conferidas quando aplicável; FORENSIC reconstrói
byte a byte (SHA-256 igual); ANALYTICAL reproduzível deterministicamente;
perdas identificadas; verificador usável por terceiros; roda em 32 GB;
resultados reproduzíveis + docs para revisão independente.

## Riscos conhecidos

- Dados 2026 podem estar indisponíveis/incompletos → registrar limitação,
  trabalhar com amostras válidas, nunca inventar resultados.
- RDV×BU e QRs impressos dependem de fontes independentes → escopo condicional.
- Assinaturas exigem cadeia/material oficial → sem isso, Nível 1 sem prova de autoria.
