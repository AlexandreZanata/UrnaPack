# Prompt de implementação — Etapa 1

Copie o bloco abaixo para um agente que tenha acesso a este repositório e aos
dados locais. O escopo foi limitado para execução sequencial e revisão posterior.
Este é o roteiro usado para a primeira entrega, agora implementada e revista.
O estado atual e as evidências estão em `docs/REVISAO-ETAPA-1.md`; não confundir
este roteiro com o escopo da Etapa 2.

```text
Implemente somente a Etapa 1 do UrnaPack: corrigir as verificações básicas e
produzir o mapa estrutural reproduzível dos dados reais já baixados de MT.

Leia nesta ordem:
1. AGENTS.md.
2. docs/ETAPA-1.md — contrato autoritativo desta entrega.
3. docs/DADOS-BRUTOS.md — famílias/cabeçalhos reais e cuidados de interpretação.
4. docs/ARQUITETURA.md e docs/VERIFICACAO.md.
5. docs/PLANO.md, somente para entender os limites entre etapas.

Use os dados de dados/brutos/2026/ e o manifesto dados/manifest-2026-mt.json.
O caminho dados pode ser um symlink de raiz legítimo. Leia dados/LEIAME-LOCAL.md
para o contexto da instalação, sem copiar caminhos físicos para arquivos Git.
Preserve fontes e manifesto existentes: leitura somente, sem novo download.

Trabalhe em três incrementos, sem subagentes ou refatoração lateral:

A. Corrija inspect/build_from_dir/verify e seus testes reais de biblioteca/CLI:
- erros de raiz/travessia/metadata/leitura não podem ser omitidos;
- caminhos não podem sofrer conversão com perda;
- versão incompatível, duplicatas de caminho, travessia e symlinks internos
  devem reprovar explicitamente, com exit não zero na CLI;
- permita resolver um link legítimo da raiz e mantenha a política de rejeitar
  links internos e arquivos especiais; não altere o acervo para passar testes;
- mantenha leitura do manifesto de origem v1 válido e seu determinismo;
- não redesenhe os dois contratos de manifesto nesta etapa; documente limites;
- corrija a perda de erros acumulados em scripts/validate.py e a falsa validação
  completa quando jsonschema não estiver disponível;
- substitua hashes fictícios de testes tocados por hashes calculados dos bytes.

B. Implemente scripts/map_raw_data.py conforme E1.2, com biblioteca padrão:
- argumentos --source, --year, --scope e --output;
- descoberta de arquivos/ZIPs por varredura, sem lista fixa de MT ou arquivos;
- SHA-256 real dos arquivos, catálogo de membros por fonte+ordinal+nome;
- metadados ZIP identificados como declarados, sem fingir leitura integral;
- CSVs lidos integralmente em streaming, com parser CSV real, Latin-1 e ';',
  cabeçalhos em ordem, fingerprints definidos, contagem de registros, escopos
  observados e sentinelas lexicais por coluna;
- SHA-256 dos membros CSV calculado sobre todos os bytes, separado do hash do
  cabeçalho; não calcular hash completo a partir de amostra;
- binários/PDFs opacos com estado explícito; amostras de formato são limitadas;
- não extrair caminhos do ZIP, não expandir contêineres recursivamente e não
  inferir tipo somente pela extensão;
- limites operacionais centralizados em scripts/limits.env, sem números
  duplicados em scripts/workflows; limite ou esquema desconhecido reprova;
- produzir map.json, members.jsonl, report.md e run.json na saída ignorada
  relatorios-locais/etapa-1/mt, com finalização segura;
- conteúdo do mapa/membros determinístico; data e tempos de execução separados.

Cuidados específicos já observados:
- BU web mistura contexto seção/cargo repetido com votos por votável. Não somar
  aptos/comparecimento por linha e não deduplicar contexto sem verificar igualdade.
- CESP contém csec e ccont com cabeçalhos diferentes; contingência não tem seção
  no layout examinado. CEFT é outra fonte, com esperada e efetivada separadas.
- votacao_secao não tem turno no nome; mapear os turnos/eleições lidos dos CSVs.
- ZIP de relatórios localizado em t1 contém também PDF de t2; pasta não prova
  o turno de todos os membros. Não mover os brutos por causa disso.
- uma amostra de log.jez é ZIP com logd.dat, apesar da descrição genérica 7z
  no leia-me. Registrar formato observado e aninhamento pendente; sem decoder novo.
- nomes, ordem, campos, sentinelas, versões e ocorrências não podem desaparecer.
- presença de relatórios de t2 não equivale a BU/RDV/logs de t2 por seção.

C. Escreva regressões pequenas e execute em MT:
- testes Rust e scripts/test_*.py conforme E1.3; fixtures sintéticas identificadas
  em tests/fixtures/, hashes calculados e verificações realmente executadas;
- inclua o comando unittest na CI existente, preservando pins e permissões;
- execute todos os checks de docs/ETAPA-1.md, depois o verify do manifesto local
  e o mapeador em MT; confira a repetibilidade dos artefatos determinísticos;
- complete docs/DADOS-BRUTOS.md com o dicionário estrutural por campo e novas
  variantes efetivamente observadas, distinguindo evidência e hipótese;
- escreva docs/REVISAO-ETAPA-1.md com mudanças, testes/comandos/resultados reais,
  referências relativas a relatórios locais, limitações e checklist G1.

O objetivo desta etapa é integridade de inventário e conhecimento da estrutura,
sem transformar os dados eleitorais. Não implementar downloader, compressor
próprio, Parquet/Arrow, parser ASN.1, restore, análise estatística ou publicação.
Não apagar/alterar fontes, não versionar inventários da instalação, não criar
commit/push. Sem dependência Rust nova; Python de automação somente em scripts/.
Não prometer desempenho, economia, autenticidade ou completude sem medição.

Se faltar informação semântica, registre pendência e preserve os bytes. Se um
check não puder executar, relate a causa exata e não apresente G1 como aprovado.
Não gaste contexto investigando etapas futuras. Ao terminar a Etapa 1, pare e
resuma: arquivos alterados, checks executados, evidências locais e pendências
que precisam da revisão técnica antes da Etapa 2.
```
