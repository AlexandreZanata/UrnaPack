# Asset de CSVs da auditoria — invólucro v1

Usa o arquivo UrnaPack v2 já implementado em `src/archive.rs`; não cria
formato binário UPK. O invólucro é ZIP padrão, com membros armazenados sem
nova compressão porque o payload interno já usa ZSTD. A instância nacional
de 2026 contém os 28 CSVs BU web t2 selecionados pelo manifesto de análise.

## Conteúdo

- `audit-input.json`: cópia dos bytes do manifesto analítico de entrada,
  incluindo URL/hash do ZIP de origem e hash/tamanho do membro CSV.
- `archive/dataset.json`, `archive/source-manifest.json`,
  `archive/execution.json`, `archive/payload.tar.encoded`: arquivo v2 selado.

O inventário ZIP e o SHA-256 de cada membro são confrontados com os arquivos
selados antes da publicação do asset. Nenhum ZIP original do acervo volumoso
está incluído. O manifesto de origem lista os caminhos relativos dos CSVs.
Não se substitui o manifesto de distribuição UPK reservado em `spec/format.md`.

## Produção e prova

`package_buweb_audit_2026.py` exige destino novo, fora da origem. Confere o
inventário completo, tamanhos e hashes contra o manifesto analítico; arquivo
extra ou caminho duplicado reprova. Invoca `inspect`, `archive tar`,
`codec compress`, `archive seal`, `archive verify`, `restore` e `verify` do
núcleo Rust. A restauração é materializada e cada arquivo também é relido
pela automação para confronto de bytes/SHA-256. Diretório com erro permanece
como evidência, sem recibo de sucesso. O consumidor exige `package-run.json`
com sucesso e hash do asset correspondente.

O limite do asset é lido de `scripts/limits.env`. Falha de inventário, hash,
restauração ou limite retorna exit diferente de zero. O relatório registra
comandos efetivamente executados e hashes de seus logs. Não se afirma mínimo
global de compressão nem espaço físico liberado: fontes e intermediários
continuam preservados. Metadados de ambiente, caminho e tempo podem variar;
a garantia refere-se aos arquivos restaurados, não ao hash do invólucro em
todo ambiente.

## Uso offline e limites

Depois de extrair o ZIP em diretório novo, `archive verify` verifica o arquivo
v2 e `restore` recupera os CSVs. `relocate_audit_manifest_2026.py` recalcula
seus hashes/tamanhos e cria outro manifesto, alterando somente `path`; um
recibo separado registra o vínculo entre os dois manifestos. O manifesto
anterior permanece intacto. UF/membro inválido, symlink interno, duplicata ou
divergência de bytes reprova.

A identidade byte a byte refere-se aos CSVs selecionados, não aos contêineres
ZIP, assinaturas ou autenticidade eleitoral. Uma projeção por seção continua
sendo transformação semântica, mesmo se comprimida sem perdas depois.
Resumos/índices de logs não substituem seus arquivos originais para reprocessar
os eventos. A disponibilização futura de objetos mutáveis na mesma URL do
TSE não é garantida pelo pacote; o catálogo fixado detecta mudanças.
# ZIP de resultados derivados

`scripts/package_audit_results_2026.py` é um invólucro ZIP padrão, separado
do arquivo UrnaPack v2 e do pacote de CSVs descrito neste documento. A seleção
de arquivos/diretórios é explícita, recursiva e sem deduplicação. Symlinks,
caminhos inválidos, sobreposição da seleção e saída dentro da origem reprovam.
Não preserva diretórios vazios ou metadados do sistema de arquivos.

O membro reservado `_inventory.json`, `format_version=1`, contém escopo,
seleção, ambiente/implementação e mapa de caminhos para bytes/SHA-256. O
recibo externo `package-results.json` registra sucesso ou falha e, em caso
de sucesso, os hashes medidos do asset. Todos os membros são relidos do ZIP
e comparados com os bytes selecionados; divergência ou excesso do limite
central de asset reprova, preservando o parcial. A compactação conserva
os arquivos derivados selecionados; não recupera informação que sua
transformação analítica já não continha.
