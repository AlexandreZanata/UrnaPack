# As alegações das imagens fazem sentido?

Parte das contagens é reproduzível e algumas perguntas são legítimas.
As quatro páginas, porém, não fornecem evidência suficiente para transformar
as diferenças descritivas em uma conclusão de manipulação eleitoral.
A auditoria encontrou também divergências e limites que devem permanecer
visíveis. O [relatório completo](RELATORIO.md) contém as definições, fontes,
comandos e referências de cada afirmação.

## O que foi reproduzido

- 499.205 seções presidenciais, 128.236.074 comparecimentos e diferença
  nominal de 4.430.191 votos. A soma dos BU web coincide com o JSON nacional
  publicado. São duas representações do acervo oficial, não testemunhos
  independentes da votação física.
- 8.632.488 eleitores no campo de biometria citado, equivalentes a 6,73%
  do comparecimento. O campo não revela candidato escolhido ou invalidade
  do voto. Compará-lo à margem final não demonstra direção partidária.
- Os intervalos de encerramento 17h01–17h15 e 17h16–18h59 e os percentuais
  estaduais apresentados. A diferença de desempenho entre grupos existe;
  horário de encerramento não é horário individual de cada voto e os grupos
  não têm composição geográfica e social controlada.
- 106 seções com 100% dos válidos para Lula e quatro para Flávio. Não há
  modelo nulo ou controle geográfico que estabeleça, nessas páginas, se
  essa assimetria é estatisticamente inesperada.

## Diferenças no relatório das imagens

- A linha nacional após 19h informa 6.333 seções/1.856.306 eleitores.
  O corte lexical inclusivo produz 6.342/1.858.274; o estrito,
  6.326/1.853.265. O ajuste nominal de fuso também não reproduz exatamente
  a linha. A seleção original permanece sem explicação verificável.
- “Mais de 90%” produz 6.816/378 seções. Os 6.899/384 impressos são
  reproduzidos por “90% ou mais”: há diferença de fronteira entre texto
  e contagem.
- Os coeficientes que calculamos são Pearson 0,0678729170 e Spearman
  0,0447541271, com definição explícita por seção. São associações pequenas
  e positivas; não reproduzem “<0,1%” se essa expressão significar 0,001.
  A ausência do método original impede afirmar que ele calculou as mesmas
  variáveis. Correlação não estabelece voto individual ou causalidade.
- Não se justifica exigir uma distribuição gaussiana apenas porque há
  muitos eleitores. Benford precisa de condições de aplicação; os gráficos
  e resultados originais não foram fornecidos. Nenhum dos dois argumentos
  identifica manipulação por si só.

## Divergências efetivamente encontradas nos dados

Nos logs há 41 chaves presentes com diagnóstico: 27 do exterior são
identificadas no CEFT como sistema de apuração, e 14 domésticas têm
diferenças de contagem, linhas repetidas ou malformadas. Existe também um
pacote de log esperado ausente em SP, cuja seção tem 268 comparecimentos.
Todos esses casos e seus hashes estão documentados. Não foram descartados
para fazer o resultado fechar e não lhes foi atribuída causa sem evidência.

Os 34.050 eventos de eleitor computado após 17h, nas seções conciliadas,
dão sustentação à ordem de grandeza “34 mil”. A outra métrica, confirmação
para Presidente, produz 33.865. Como a conciliação nacional não é completa,
não certificamos uma contagem nacional exata. O intervalo conservador do
programa é 34.050–38.474, sob a política nominal de relógios documentada.
Ele não revela em quem esses eleitores votaram.

Também apareceram questões de catálogo e aquisição: uma URL de ZIP de RR
apontava para o sidecar e alguns recursos administrativos serviram versões
divergentes em HEAD/GET. Foram documentadas e resolvidas com validação,
sem inferir alteração de votos a partir de comportamento HTTP.

## O que permanece inconclusivo

Não foi estabelecida a alegada concentração rural. Não foram comprovadas
as afirmações dos sete minutos, dos fundamentos da prisão ou da proteção
diplomática com documentação primária suficiente. Hashes e CRCs foram
verificados; assinaturas eleitorais e a calibração física dos relógios
não foram certificadas.

Há evidência para reproduzir várias contagens e para investigar os
diagnósticos dos arquivos. Não há, nesta análise, evidência técnica
suficiente para concluir fraude ou certificar a autenticidade de todo o
processo eleitoral. O que a auditoria entrega é o confronto reproduzível,
com resultados concordantes, discordantes e inconclusivos preservados.
