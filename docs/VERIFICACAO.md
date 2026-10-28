# Verificação — os 5 níveis (o que cada um prova e o que NÃO prova)

## Nível 1 — Integridade do arquivo original ✅ base v0.1

Para cada arquivo: URL oficial (quando conhecida), SHA-256, tamanho, tipo,
hashes de internos extraídos. Implementado em `manifest` + `verify`.
**Não prova**: autoria do TSE (só a assinatura digital oficial provaria;
assinatura nossa nunca será apresentada como do TSE).

## Nível 2 — Equivalência semântica ⏳ Fase 4

Esquema formal por campo: tipo original → tipo transformado, regra exata,
normalização, reconstruibilidade, condições de equivalência. Exige preservar
zeros à esquerda, nulo≠vazio≠zero, duplicatas legítimas, ordenação com
significado, precisão/fuso de timestamps. Perda irreversível só no perfil que
a declarar. **Base v0.1**: nenhum transformador semântico existe; nada a declarar.

## Nível 3 — Rastreabilidade por registro ⏳ Fase 4

Índice registro→(fonte, hash, turno/UF, ids, versão do esquema). Merkle com
domain separation e codificação canônica, provas geradas sob demanda.
**Não prova**, isoladamente, que o parser interpretou certo o arquivo oficial.

## Nível 4 — Verificador independente ✅ parcial na base

`tsepack verify` relê manifesto do disco e recalcula tudo (detecta ausente,
truncado, alterado, versão). Na Fase 4 ganha: reexecução determinística da
transformação, comparação de multiplicidades/ids, compromissos e agregações,
relatório aprova/diverge em JSON+texto. Caminho com parser independente para
não compartilhar o mesmo defeito de parsing.

## Nível 5 — Reconstrução byte a byte ⏳ Fase 4 (perfil FORENSIC)

Formato reversível + resíduos → SHA-256 pós-restauração igual ao original.
Se o especializado não superar compressão convencional, usa-se a convencional.

## Limitação obrigatória (sempre)

Sem originais íntegros (recuperados, rebaixados por hash, ou reconstruídos via
FORENSIC), não há reverificação integral — atestações anteriores documentam,
não substituem a evidência. **Semântica ≠ bytes**: os dois níveis de garantia
são implementados e relatados separadamente.
