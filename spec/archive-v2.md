# Arquivo FORENSIC local v2

`artifact_kind: urnapack_forensic_archive`, `format_version: 2`.
Garantia: **mesmos caminhos relativos e bytes de todos os arquivos de origem**.
Não preserva metadados do sistema de arquivos (mtime, permissões, proprietário).
Um ZIP de origem é um objeto opaco: seus bytes, incluindo diretório central,
membros, ordem, duplicatas internas e assinaturas contidas, são preservados.
É um contêiner local, não o manifesto de distribuição `.upk.zst`.

## Contrato

Diretório com `dataset.json`, `source-manifest.json`, `execution.json` e dados.
Descritor estrito, sem campos adicionais:

- `artifact_kind`, `format_version`, `guarantee: relative-paths-and-file-bytes`;
- `layout`: `solid-tar` ou `per-file`; `codec`;
- `payload`: objeto `{file, bytes, sha256}` no sólido, `null` por arquivo;
- `entries`: array vazio no sólido; por arquivo, objetos estritos
  `{source_path, codec, data: {file, bytes, sha256}}`;
- `source_manifest`, `execution`: objetos estritos `{file, bytes, sha256}`.

SHA-256 é calculado dos bytes. `source-manifest.json` é a cópia exata do
manifesto de origem v1/v2 fornecido, preservando seus hashes, caminhos e URLs
quando existentes. Caminhos inválidos/duplicados, arquivos desconhecidos,
symlinks internos, versões incompatíveis e tipos não regulares reprovam.
A raiz pode ser um link legítimo. O inventário do pacote deve ser exato.

**Sólido:** `payload.tar.encoded`; `codec` é stored, ZSTD, XZ ou Brotli.
O TAR padrão começa pelo manifesto exato em `source-manifest.json`, seguido
dos arquivos sob `source/<caminho>`, ordenados pelo caminho. Headers de emissão
têm mode 0644, uid/gid/mtime zero; conteúdo de origem não é modificado.
Restauração lê os headers com `tar`, exige somente entradas regulares
declaradas, confere tamanho/SHA-256 de cada conteúdo, rejeita ausências,
duplicatas e resíduo não nulo após o TAR. O decoder deve terminar sem erro.

**Por arquivo:** `codec: per-file`, dados `data/00000.encoded` etc., na ordem
do manifesto de origem. Cada entrada vincula um caminho da origem a seu codec
e objeto codificado. Conteúdos iguais em caminhos diferentes continuam sendo
ocorrências diferentes, com restauração de ambos os caminhos. Cada decoder
reconfere tamanho e SHA-256 originais antes da promoção.

V1 experimental só tinha TAR sólido. A leitura atual aceita v1 sólido e v2;
escrita sempre v2. V2 exige os campos explícitos `layout` e `entries`; omiti-los
não permite reinterpretar v2 como legado. Há regressões de migração/rejeição.

## Recibo vinculado

`execution.json` usa `urnapack_execution`, v1: ferramenta, comando real,
entradas e saídas com hashes, início/fim reais, duração, sucesso e erros.
O descritor armazena SHA-256 e tamanho desse recibo. Entradas identificam o
manifesto e os objetos realmente lidos; saídas identificam o manifesto copiado
e os objetos codificados. O verificador compara caminhos de saída e multiconjunto
de hashes de entrada com os objetos do pacote. Conteúdos iguais não são eliminados.

Não há ciclo: recibo não referencia o próprio recibo nem `dataset.json`.
`started_at`/`finished_at` são strings `unix-ns:<nanosegundos desde Unix epoch>`;
`elapsed_ms` é medido, podendo ser zero em operações inferiores a 1 ms.
Um sucesso contraditório, recibo alterado ou vínculos divergentes reprova.
Os hashes não são assinatura do produtor nem autenticação da fonte oficial.

Esse vínculo completa a execução do **arquivo local**. O manifesto de
distribuição v2 antigo continua bloqueado para aprovação de publicação;
não se confunde com esse contrato e não herda garantias automaticamente.

## Codecs e limites

`codec compress` escreve arquivo novo e só o promove após decodificação
integral com tamanho e SHA-256 iguais à origem. `codec check` refaz a prova sem
materializar saída; `codec decompress` exige hash e tamanho esperados e usa
saída temporária. XZ é executado pelo utilitário instalado, single-thread,
CRC64, presets 6 ou 9 extremo. ZSTD usa a biblioteca do Cargo.lock, sem
dicionário salvo quando indicado. Brotli 5 usa lgwin 22; Brotli 11, lgwin 24.

Métodos `zstd-3-blocks` e `zstd-19-blocks` emitem frames independentes por bloco
de `COMPRESSION_BLOCK_BYTES`; tamanho de cada bloco é prometido ao encoder.
O decoder deve ler todos os frames. Não há índice de acesso aleatório nesse método.

Operações em streaming; limites em `scripts/limits.env`. Rust incorpora os
valores na compilação. Fontes devem permanecer imutáveis; um escritor por
saída. Temporário irmão é promovido somente após prova. SIGKILL pode deixar
temporários identificados; não se promete concorrência segura ou durabilidade
por `fsync`. A restrição de assets de Releases será tratada na distribuição;
esse arquivo local pode conter objetos maiores que aquele limite.

## CLI

```bash
# Seleção por arquivo: stored/ZSTD3/XZ6; exhaustive acrescenta ZSTD19/XZ9e/Brotli5.
tsepack optimize --input originais --manifest origem.json \
  --profile quick --output arquivo
tsepack archive verify --input arquivo
tsepack restore --dataset arquivo --output restaurados
tsepack verify --manifest origem.json --source restaurados
```

`optimize` só suporta modo FORENSIC e escolhe pelo tamanho codificado de cada
arquivo. O experimento completo compara também agrupamento sólido e overhead
dos contêineres; sua seleção final usa bytes totais, não apenas o payload.
