# Plano de execução — Análise entre turnos (pós-tratamento)

Sequência executável da fase de detecção de anomalias e comparação entre
turnos. A metodologia completa é a especificação recebida para esta fase;
este documento define **quando começar, em que ordem e como saber que cada
etapa está pronta**. Sem duplicar a metodologia: os detalhes de cada método
vivem na especificação; aqui vive a ordem, as dependências e os portões.

Posição no projeto: infraestrutura pronta → **tratamento (docs/PLANO.md,
Fases 2–6)** → este plano. Nada abaixo começa antes do portão de entrada.

## 0. Portão de entrada (objetivo, verificável por comando)

O tratamento está concluído para (ano, turnos, UF) quando:

1. `data/index.json` contém entradas `validated`/`published` para 2026 t1 e t2.
2. `tsepack verify` aprova os manifestos contra as fontes.
3. Cada registro tratado referencia arquivo oficial + hash (rastreabilidade).
4. Granularidade mínima: seção (zona/município/UF deriváveis por agregação).
5. Cargo presidencial separável por identificador oficial (sem misturar cargos).

```bash
python3 scripts/validate.py index data/index.json
tsepack verify --manifest <manifest-t1> --source <origem-t1>
tsepack verify --manifest <manifest-t2> --source <origem-t2>
```

Sem isso: registrar a lacuna e executar só o subconjunto válido. Nunca
completar resultado com dado ausente.

## 1. Ordem de execução (cada etapa só começa com a anterior verde)

1. **Correspondência de seções** — tabela canônica de unidades comparáveis
   (ano/UF/município/zona/seção + agregadas/desmembradas); sem par confiável,
   sem comparação inventada (sobe para zona/município e registra).
2. **Registro comparativo por seção** — t1×t2 lado a lado + métricas derivadas,
   denominadores explícitos, sem divisão por zero, pp ≠ % relativa.
3. **Invariantes aritméticas** — somas, válidos/brancos/nulos, comparecimento,
   abstenção, aptos, agregações; divergência relata valor calculado × oficial.
4. **BU × RDV × totalização** — relatório separado da estatística.
5. **Comparecimento** — robusto + intervalos empíricos calibrados por grupo.
6. **Brancos/nulos** — condicional a turno/cargo/grupo; categorias documentadas.
7. **Hierárquicos** — baseline simples primeiro (binomial/beta-binomial);
   complexidade só com calibração melhor demonstrada.
8. **Ecológica** — limites de compatibilidade antes de qualquer matriz;
   não-identificação explícita quando houver.
9. **Territorial** — só com geometria confiável; controle de testes múltiplos.
10. **ML** — somente exploratório, após 5–9, com calibração e remoção se inútil.
11. **Operacional/logs e dígitos** — condicionais à disponibilidade e às
    hipóteses do método; sem valor probatório isolado.
12. **Falsos positivos** — FDR/permuta/bootstrap desde o primeiro modelo.
13. **Controle/falsificação** — sintéticos identificados, ground truth, taxas
    de detecção e falso positivo antes de qualquer conclusão sobre reais.
14. **Explicabilidade + CLI + relatórios** — achado sem justificativa não
    existe; relatório JSON/CSV/HTML versionado.

## 2. Regras de implementação

- Módulos = responsabilidades (`section_matching`, `deterministic_checks`,
  `turn_comparison`, `statistical_models`, ...), sem dez crates.
- CLI no binário existente: `tsepack analyze <compare|integrity|turnout|
  statistical|spatial|transitions|report> --year 2026 --rounds 1,2 --state MT`.
- Comando não implementado falha explicitamente; relatório nunca finge sucesso.
- Streaming/lotes, 32 GB; determinístico (sementes registradas).
- Sintéticos em `tests/fixtures/`, identificados; jamais misturados a reais.

## 3. MVP (MT) e expansão

MT primeiro: correspondência → invariantes → turnout → 1 modelo calibrado →
falsificação → relatório. Nacional só com pipeline validado e estável.

## 4. Aceitação (como verificar cada item)

Itens 1–5, 9–10: comandos + relatórios reproduzíveis. Itens 6–8, 12:
testes sintéticos com taxas medidas e limiares pré-registrados. Item 11:
pico de RAM medido em MT e projeção nacional. Item 13: revisão dos relatórios
— nenhum converte indicador em alegação sem evidência direta.
