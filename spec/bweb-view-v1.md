# View de armazenamento BU web v1

`artifact_kind: bweb_storage_view`, `format_version: 1`,
`guarantee: exact-csv-member-bytes`. Contrato local de materialização regenerável;
não substitui o ZIP original quando a garantia exige preservar o download.

`view.json` tem exatamente: `artifact_kind`, `format_version`, `guarantee`,
`kind`, `source`, `encoded`, `codec`, `dictionary`, `pack_manifest`, `decoded_stream`.
Objetos de arquivo têm `file` (basename), `bytes`, `sha256`.
`source` contém `bytes`, `sha256`, `records`, `zip_path`, `zip_sha256`,
`member_name`, `member_ordinal`. Identidade do membro usa ordinal, não somente nome.
As referências são calculadas do mapa integral e vinculadas ao manifesto de origem.

- `csv-codec`: codec padrão sobre os bytes exatos do CSV. Dicionário, se
  necessário, acompanha com hash e seus bytes entram no custo.
- `column-stream`: concatenação das 45 colunas do pacote BU web v2,
  comprimida; `pack_manifest` acompanha. `decoded_stream` compromete tamanho e
  SHA-256 da concatenação. Restauração separa pelo tamanho das colunas, valida
  o pacote em Rust e chama o inverso com prova do CSV original.
- `parquet`: Parquet ZSTD com 45 campos **string não nullable**, sem conversão
  numérica, deduplicação ou ordenação. Headers e ordem dos registros são
  preservados; valores vazios e sentinelas continuam strings. Metadados exatos:
  `urnapack_format=bweb-parquet-v1`, `source_member_sha256`, `encoding=latin-1`,
  `lineterminator=CRLF`, `quoting_rule=tse-text-columns-v1`.

Parquet v1 reconstrói cabeçalho/aspas/CRLF conforme o perfil canônico observado.
Só é aprovado se a reconstrução completa tiver tamanho, registros e SHA-256
da origem. Entradas com outra emissão lexical não são normalizadas silenciosamente.
O layout usa PyArrow como ferramenta de experimento, sem criar um novo parser
de produção em Python. O pipeline principal de codecs/arquivos é Rust.

`restore-view` verifica o descritor, hashes e limites, rejeita saída existente
e escreve por temporário. Campos desconhecidos e chaves JSON repetidas reprovam.
Todas as formas exigem verificação dos bytes restaurados. O verificador Parquet
não converte nulos em strings nem aceita campos adicionais.

```bash
python3 scripts/compression_stage.py restore-view \
  --input cache/view.json --output bweb-restaurado.csv
```

O bundle mínimo preserva somente a **receita** e os originais recuperáveis,
evitando uma segunda cópia permanente da mesma informação. O cache selecionado
permanece fora dele como opção de uso local e tem seu custo informado separadamente.
`materialize-view` recupera o ZIP do arquivo FORENSIC, verifica seu hash,
seleciona membro por ordinal/nome, verifica tamanho/SHA do CSV e reproduz o
cache CSV selecionado. Esse materializador suporta o perfil CSV do experimento;
outra representação selecionada exige receita de produção própria.

```bash
python3 scripts/compression_stage.py materialize-view \
  --input pacote/bundle.json --output cache-novo
```

A receita inclui o hash esperado do encoder atual. Mudança que produza outro
bitstream reprova explicitamente e exige reavaliação da materialização, ainda
que os bytes do CSV possam continuar equivalentes. A garantia principal de
recuperar os downloads não depende de manter esse cache.
