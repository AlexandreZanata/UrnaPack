# BU web — pacote reversível v2

Formato experimental de diretório. `PACK_FORMAT_VERSION = 2`; não é um asset
de distribuição `.upk.zst`. Escopo: membro CSV BU web com as 45 colunas de
`bweb.canonical-v1.md`. O empacotador preserva valores lexicais e aceita somente
entradas cuja emissão recupere integralmente os bytes de origem. Validação dos
domínios do perfil MT é uma operação separada, em `validate_bweb.py`.

## Contrato e compatibilidade

`pack.json` contém exatamente `artifact_kind: bweb_columnar_pack`,
`format_version: 2`, `family: bweb`, `header` (45 nomes em ordem), `quoted`
(45 booleanos), `rows`, `encoding: latin-1`, `lineterminator: \r\n`,
`quoting_rule: tse-text-columns-v1`, `source_member_sha256` (hex64 minúsculo,
obrigatório) e `columns` (45 objetos com `file`, `rows`, `bytes`, `sha256`).
Campos adicionais reprovam no manifesto e nas colunas.

Os únicos arquivos de dados são `columns/00.bin` … `columns/44.bin`, na ordem
do cabeçalho. Cada valor é `u32 little-endian comprimento + bytes Latin-1`,
sem cast, normalização ou deduplicação. Vazio tem comprimento zero. Ordem,
zeros significativos, sentinelas, aspas e quebras internas são preservados.
O ordinal da ocorrência é o mesmo ordinal lógico do CSV, a partir de 1;
o cabeçalho fica fora dessa contagem. Hash do membro + ordinal localiza o
registro dentro desse membro. O mapa estrutural vincula-o ao ZIP e ao ordinal
do membro; esses vínculos ainda não são incorporados ao pacote.

V1 tem o mesmo enquadramento de colunas, porém aceitava hash opcional e não
exigia prova da emissão no produtor. Leitura de v1 com compromisso válido
continua suportada; v1 sem ele reprova. Escrita sempre v2. Versões novas
incompatíveis exigem mudança explícita de versão e testes.

## Emissão e verificação

Separador `;`; cabeçalho com todos os nomes entre aspas; CRLF após cada
registro, incluindo o último. Nas linhas, o conjunto Q de `bweb-pack-v1.md`
tem sempre aspas e duplica aspas internas; B nunca tem aspas e rejeita `;`,
aspas, CR ou LF. Entradas com outras regras de aspas, LF, ausência de CRLF
final ou linhas vazias descartadas pelo parser reprovam pela comparação de
tamanho e SHA-256 da emissão com a origem. Nenhum resíduo é descartado.

O produtor calcula o hash da origem a partir dos bytes; `--source-sha` é um
compromisso esperado adicional, nunca um hash confiado sem cálculo. Antes de
publicar, calcula tamanhos/hashes das colunas e comprova a emissão original.
O inverso valida versão, layout, inventário exato, metadados, hashes das colunas,
comprimentos, número de valores e EOF. Recalcula o SHA-256 do CSV escrito e
confere com o compromisso antes de tornar a saída final visível. Falha é exit
diferente de zero, também quando a biblioteca é chamada sem a CLI.

`scripts/verify_pack.py` usa `csv` do Python para conferir cada valor/ordinal
e uma emissão própria, além dos hashes. Funciona também com `python3 -O`;
nenhuma validação depende de `assert`. Esse confronto aprova equivalência
lexical e restauração de bytes separadamente de qualquer análise de negócio.

## Saídas e recursos

Saída existente, arquivo desconhecido, caminho divergente, symlink interno,
coluna truncada, resíduo e campo desconhecido reprovam. A raiz pode ser link
legítimo. `unpack` recusa saída dentro do pacote, inclusive por aliases.
Gravação usa temporário irmão, removido em falhas normais, e promoção após
validação. SIGKILL pode deixar temporários identificados; não promove um
pacote incompleto. Exige fonte imutável e um escritor por diretório; não
promete proteção contra troca concorrente nem durabilidade por `fsync`.

Limites de fonte, registros, campo, registro lexical, manifesto, pacote e
buffer estão em `scripts/limits.env`. Rust incorpora-os na compilação;
alterações exigem recompilar. Leitura e escrita são streaming, com um buffer
por coluna. Medições de MT não equivalem a comprovação de escala nacional.

```bash
tsepack pack --family bweb --input bweb.csv --output pacote
tsepack unpack --input pacote --output restaurado.csv
cmp bweb.csv restaurado.csv
python3 -O scripts/verify_pack.py --pack pacote --original bweb.csv
```

A identidade garantida refere-se ao membro CSV, não ao contêiner ZIP baixado,
às assinaturas ou à autenticidade eleitoral. Os originais continuam retidos.
