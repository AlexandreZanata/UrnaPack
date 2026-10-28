# Verificação — garantias e evidências exigidas

Os níveis abaixo descrevem garantias diferentes. A base atual não implementa
um atestado único que reúna todas. As correções da Etapa 1 estão registradas em
`docs/REVISAO-ETAPA-1.md`; não apresentar garantias futuras como implementadas.

## Nível 1 — Integridade dos objetos declarados

Implementação parcial: manifesto de origem Rust v1 + `tsepack verify` recomputam
SHA-256 e tamanho dos arquivos declarados. URL por arquivo é opcional na base.
Versões incompatíveis, duplicatas, caminhos não canônicos e symlinks internos
reprovam, e erros de travessia não são omitidos. Hashes de membros internos não
são produzidos pelo `inspect`: o mapeador calcula SHA-256 dos CSVs lidos até EOF;
membros opacos catalogados/amostrados mantêm hash ausente e nível explícito.

A aprovação prova correspondência com o manifesto examinado, não completude
da eleição, interpretação correta ou autoria do TSE. Sidecar de hash e assinatura
digital são evidências diferentes; tamanho/Content-Length sozinho não comprova
integridade criptográfica. Ausência de assinatura/chave/cadeia verificável precisa
aparecer como limitação, sem ser substituída por assinatura do projeto.

## Nível 2 — Equivalência semântica

Contrato exigido antes do primeiro transformador: nome e ordem dos campos,
tipo original/canônico, domínio/sentinelas, precisão/fuso, normalização, regra
de equivalência e reconstruibilidade. Preservar nulo, vazio, zero, não existente,
zeros significativos, categorias oficiais, multiplicidades e ordem com significado.

Verificar todas as ocorrências e valores, e não apenas somas ou determinismo.
Campo desconhecido bloqueia interpretação até atualização de esquema. Uma
redução analítica é produto derivado de escopo declarado, regenerável a partir
da evidência preservada; não substitui a única cópia de informação eliminada.
Nenhum transformador semântico existe na base atual.

## Nível 3 — Rastreabilidade por ocorrência

Contrato: ocorrência → hash do download, membro e ordinal/posição, escopo,
versão do esquema e transformação. Hash do arquivo sozinho não identifica a
linha; caminho do membro sozinho não resolve nomes repetidos em um ZIP.

Preservar identidade de negócio e identidade da ocorrência separadamente.
Deduplicação física não pode fundir ocorrências eleitorais nem apagar snapshots.
Merkle fica sob demanda, com codificação canônica e domain separation
especificados; não é pré-requisito para o primeiro índice rastreável.

## Nível 4 — Reexecução e verificador independente

O verificador atual relê o manifesto de origem e os bytes; não valida dataset
transformado, parser eleitoral, multiplicidades ou consultas. A independência
atual é de execução/estado; não constitui um segundo parser eleitoral.

Cada família transformada precisará de reexecução determinística, comparação
integral do contrato e confronto de contagens com os arquivos. Usar leitura ou
referência independente onde seja necessário detectar o mesmo erro de parsing
compartilhado pelo produtor e pelo verificador.

Validar também cardinalidades de joins, igualdade do contexto repetido,
cobertura e regras de agregação. Diagnóstico explícito bloqueia o uso afetado;
um recorte válido precisa de declaração própria, sem virar conjunto completo.

## Nível 5 — Reconstrução byte a byte

FORENSIC exige SHA-256 dos bytes restaurados igual ao SHA-256 do objeto original
declarado. Cada técnica deve ser entregue com seu inverso e seus testes.

Distinguir download ZIP, membro descomprimido, representação canônica e pacote
derivado. Recriar um ZIP com os mesmos membros não prova identidade do ZIP
baixado. Se esse download é o objeto prometido, preservar o original ou todos
os resíduos necessários à sua reconstrução e contabilizar esse custo.

Se o especializado não superar a alternativa convencional equivalente,
usar a alternativa convencional ou stored. Não enfraquecer a garantia para
produzir uma taxa de compressão melhor.

## Portões de uso e publicação

Hash válido, JSON conforme schema e `verification_status: validated` são
condições distintas. Nenhum deles sozinho comprova o pipeline completo.

Aprovar um uso somente com cobertura das dependências, origem, semântica,
rastreabilidade e agregações exigidas por ele. Comparação entre turnos requer
ambos os lados; uma inspeção de um turno não. Publicação exige ainda arquivos
completos, vínculos coerentes e reverificação dos assets disponibilizados.

Registrar relatório, hashes de entrada/saída, versões, parâmetros, limitações
e comandos. Sem originais íntegros, rebaixados com confronto de hash ou
reconstruíveis, não há reverificação integral. Atestação anterior documenta,
mas não substitui a evidência. Semântica e bytes são relatados separadamente.
