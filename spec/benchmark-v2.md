# Benchmark — relatório v2

O relatório evolui independentemente dos formatos de origem e BU web.
V2 substitui a serialização inicial sem versão e os tempos fictícios do
benchmark colunar. Leitura de checkpoint só aceita v2.

## Medições e denominadores

Por arquivo: JSON de saída é um array de `BenchReport`, cada um com
`format_version: 2`, `input`, `source_sha256`, `profile`, `cases`.
`quick` mede stored, ZSTD 1/3 e Brotli 5 (lgwin 22); `exhaustive` acrescenta
ZSTD 10/19. Encoders trabalham em streaming, sem parâmetros de dicionário
treinado nem tamanho prometido ao encoder ZSTD. Brotli usa a API de streaming
que propaga erros de finalização. Artefatos individuais são temporários.

Pacote: `PackBenchReport` tem `format_version: 2`, `complete`, `pack_dir`,
`profile`, `input_bytes`, `pack_uncompressed_bytes`, `pack_json_bytes`,
`manifest_sha256`, `environment`, `storage_scope`, `cases`, `columns`.
O benchmark valida o pacote e o SHA-256 da restauração antes de medir.
Denominador `input_bytes` é o tamanho do **CSV original restaurado**.
`pack_uncompressed_bytes` é colunas com prefixos + manifesto; pode exceder o
CSV original. Cada saída comprimida inclui os bytes de `pack.json` sem compressão.

Métodos de pacote: stored + ZSTD por coluna e sólido nos níveis do perfil.
Por coluna são 45 frames independentes concatenados em um arquivo; sólido é
um frame da concatenação das colunas. A mesma compressão produz tamanho total
e detalhes `columns[].zstd_bytes`: não se comprime novamente para somá-los.
O relatório não mede acesso aleatório nem fornece índice de consulta.

Cada caso contém método, bytes de entrada/saída, `ratio = entrada/saída`,
`saved_pct = 100*(1-saída/entrada)`, `compress_ms`, `decompress_ms`,
`compress_ns`, `decompress_ns`, `round_trip_ok`, `compression_reused`,
`compressed_file` e `compressed_sha256`. Tempos ms são truncamentos dos ns
medidos; ms zero pode ser uma medição inferior a 1 ms. Stored tem tempos
`null`, pois não executa codec; denominador vazio tem taxa `null`.
Compressão inclui I/O e finalização; descompressão inclui leitura e SHA-256
de todos os bytes decodificados. Hash e tamanho devem conferir, ou não há caso
aprovado. Não são tempos de consulta nem de reconstrução do CSV.

## Checkpoint e retomada do pacote

`--output caminho.json` mantém artefatos em `caminho.json.assets/` e salva o
relatório após cada método aprovado. Arquivo comprimido tem nome fixo por
método e hash calculado dos bytes. Relatório inicial é `complete: false`;
`complete: true` indica todos os métodos daquele perfil, não conclusão da
Etapa 4. Um único escritor; relatórios ficam fora da entrada.

`--resume --output caminho.json` exige entrada, perfil, versão e ambiente
compatíveis. Reconfronta metadados, SHA-256/tamanho de cada artefato,
descompressão e tamanhos dos frames com as respectivas colunas. Recalcula
taxas a partir dos bytes; não confia em taxas editadas no JSON.
Tempos de compressão anteriores são preservados e marcados
`compression_reused: true`; os de descompressão são medidos novamente.
O relatório fica incompleto durante a reconferência e em falha de cache.
Tempos preservados são evidência da execução anterior, sem atestado externo.

Interrupção durante um método exige refazer apenas esse método. Artefato já
promovido sem checkpoint correspondente reprova explicitamente: preservar
para diagnóstico ou removê-lo conscientemente antes de retomar. Temporários
de SIGKILL não são tratados como artefatos completos. Não há promessa de
recuperação de falha de energia, assinatura de medições ou concorrência segura.

## Limites da comparação

Inclui CSV equivalente, prefixos, frames e manifesto do pacote. Exclui ZIP
original, sidecars, recibos de aquisição, mapa e caches. Não é redução total
do projeto, e não autoriza eliminar os originais. Versões/parâmetros de
encoders diferentes podem produzir outros bytes; relatório antigo em memória
não deve ser misturado com os resultados do streaming v2.

Esse relatório isolado não fecha G4. Os demais baselines, treino/avaliação,
custo total, repetições, recursos e consultas foram executados na automação
`scripts/compression_stage.py`; ver `docs/ETAPA-4.md` e o resultado de MT.
