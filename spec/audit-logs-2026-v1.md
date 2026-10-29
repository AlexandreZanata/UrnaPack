# Auditoria dos logs de 2026 — contrato v1

Núcleo Rust: `src/bin/audit_logs_2026.rs`. Aquisição, ZIP e entrega dos bytes:
`scripts/import_logs_2026.py`. Sem dependência nova e sem mudança dos formatos
de compressão do UrnaPack. Resultados são transformações semânticas; os ZIPs
originais e seus recibos permanecem preservados.

## Entrada e integridade

O importador verifica tamanho e SHA-256 do ZIP contra o recibo de aquisição,
e da projeção de seções contra o recibo de exportação. Indexa todos os membros
externos (inclusive os não interpretados) e rejeita nomes duplicados. Abre
contêineres `o03221<uf><município><zona><seção>-log.jez` e `-logsa.jez`;
membros internos desconhecidos reprovam. ZIPs aninhados são percorridos com
limites centralizados, CRC e tamanho conferidos. O suporte a um nome não
presume suporte a qualquer leiaute interno: linha desconhecida reprova.

O protocolo binário v1 entrega uma linha JSON `kind=log`, seguida do número
exato de bytes declarado. O cabeçalho registra versão, chave geográfica,
comparecimento esperado, deslocamento BRT nominal, URL e SHA-256 do ZIP,
nomes externo/interno, bytes e SHA-256 do corpo. Campos desconhecidos reprovam.
O Rust relê e calcula tamanho/hash dos bytes efetivamente analisados.

Frames de cada seção são contíguos e as seções ordenadas; contexto divergente
reprova. O último frame `kind=end` traz número de arquivos, número e hash das
chaves esperadas, hash da política e da projeção de seções. O hash das chaves
é SHA-256 de chaves UTF-8 ordenadas, cada uma terminada por LF. Não pode haver
bytes depois do fim. Python e Rust calculam independentemente o hash de todo
o fluxo; divergência reprova.

## Eventos e relógios

Texto é analisado como bytes, sem recodificar os originais. Linhas não vazias
exigem timestamp `dd/mm/aaaa hh:mm:ss` e ao menos seis campos separados por
TAB. Aplicativo `VOTA`, mensagens exatas:

- `Voto confirmado para [Presidente]`: confirmação para o cargo.
- `O voto do eleitor foi computado`: conclusão da votação pelo eleitor.

São contadores separados. Só 25/10/2026 entra nas contagens auditadas. Eventos
relevantes de outras datas ficam contados por data; não são apagados do índice.
O contexto interno é reconstruído, em cada corpo, pelas mensagens `GAP`
de município, zona e seção. Um novo município invalida zona/seção anteriores,
e uma nova zona invalida a seção. Eventos de outra chave são contados em
`other_context_relevant_events`, sem atribuição ao nome externo. Evento com
contexto incompleto fica contado e impede a conciliação. A consolidação exige
explicitamente esse método; não aceita relatórios das primeiras tentativas
que usavam somente o nome externo.
Os cortes são estritamente `>17:00:00` e `>19:00:00` após deslocamento nominal
local para Brasília; ZZ é separado dos cortes BRT. A política é construída
com códigos do índice oficial e exceções municipais documentadas (11 no
Amazonas e Fernando de Noronha). Não é evidência de sincronização física do
relógio. O log não informa o candidato escolhido.

## Duplicatas, cobertura e conciliação

Nenhum arquivo ou evento é deduplicado. Corpos idênticos são contados e todos
são analisados. Isso pode incluir cópias de eventos de outras datas. Linhas
relevantes idênticas da data auditada são contadas integralmente, registradas
como repetição e impedem a conciliação da seção. Não se transforma uma soma
duplicada em contagem validada mediante descarte.

Cada seção precisa ter conclusão de eleitores igual ao comparecimento no BU,
sem repetição relevante e com política de relógio conhecida (exceto ZZ).
Cobertura exige número E hash do conjunto de seções esperado. As duas
sentinelas ZZ sem cargo e sem votantes são incluídas explicitamente pelo
arquivo de reconciliação; não se inventa voto para completar uma seção.

Falha de conciliação publica diagnóstico e CSV completo das seções e retorna
exit diferente de zero. Falha de hash, estrutura ou fluxo não publica sucesso;
o importador preserva índice parcial e recibo de erro. Saídas finais existentes
não são sobrescritas. Limites de linhas, membros, eventos, evidências e
concorrência são lidos de `scripts/limits.env`.
Linhas com campos ou timestamp inválidos ficam contadas, com localização,
tamanho e SHA-256 sem EOL em amostra limitada; todos os bytes permanecem no
ZIP e no hash do corpo. Impedem conciliação da seção, mas a leitura continua
para fornecer diagnóstico e cobertura completos. Não são corrigidas nem
tratadas como eventos interpretados. Limite de linha excedido continua fatal.

## Consolidação

`collect_logs_2026.py` exige a escolha explícita de um diretório por UF,
verifica os resultados contra os hashes do recibo e gera um manifesto v1.
O modo Rust `--aggregate-manifest` relê hashes/tamanhos de todos os relatórios
e da totalização oficial. Rejeita UF repetida ou política/exportação diferente.
Só declara sucesso nacional com as 27 UFs mais ZZ, cobertura das seções
instaladas, todas as conciliações e comparecimento igual à totalização.
Incompletude publica diagnóstico e retorna exit diferente de zero. Somas de
diagnóstico não são apresentadas como contagem nacional validada.
O relatório também publica intervalo conservador de conclusões após 17h:
o limite inferior vem das seções conciliadas; o superior acrescenta todo o
comparecimento oficial ainda não conciliado. Não atribui horários ausentes,
e a política nominal e a exclusão de ZZ continuam explícitas.

O recibo registra hash do executável e dos arquivos de implementação presentes
antes da importação. O hash do fonte no checkout não é atestado criptográfico
de que um executável foi compilado dele. A reprodução deve compilar a revisão
Git escolhida, com `Cargo.lock`, e registrar os binários e a versão do ambiente.

## Limitações

SHA-256/CRC e sidecar publicado não são verificação de assinatura digital,
autenticador de linha, cadeia de certificados ou autenticidade eleitoral.
Essas verificações não são realizadas por este binário. Cobertura completa e
conciliação não eliminam essas limitações, nem demonstram causa política.
