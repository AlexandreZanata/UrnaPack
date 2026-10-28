# Arquitetura — base v0.1

## Princípios

Um executável Rust (`tsepack`) + biblioteca interna. Sem workspace, sem
microsserviços, sem GPU. YAGNI: cada módulo existe porque a Fase 1–2 precisa
dele agora.

## Módulos (`src/`)

| Módulo | Responsabilidade | Fase |
|---|---|---|
| `main.rs` | CLI (clap). Comandos prontos: `inspect`, `benchmark`, `verify`. Demais: erro explícito | todas |
| `hash.rs` | SHA-256 em streaming (blocos 1 MiB, sem carregar arquivo na RAM) | 2 |
| `manifest.rs` | Manifesto JSON versionado; construção paralela (Rayon), ordenada e determinística | 2, 4 |
| `inspect.rs` | Agregação por extensão (contagem/bytes); não interpreta conteúdo | 1 |
| `benchmark.rs` | Baselines `stored` + ZSTD com round-trip conferido e tempos | 2 |
| `verify.rs` | Reverificação independente contra manifesto; defesa anti path-traversal | 4 |

## Artefatos e versionamento

- `Manifest { format_version: 1, tool_version, source, files[] }`.
- `FileEntry { path (relativo, `/`), size, sha256, file_type, url? }`.
- JSON pretty-printed, chaves estáveis, `files` ordenado → **bytes determinísticos**.
- Regra: mudança incompatível ⇒ `FORMAT_VERSION += 1` + teste de compatibilidade
  (a escrever na Fase 4; hoje há teste de determinismo em `tests/determinismo.rs`).

## Decisões (com motivo)

- **ZSTD primeiro**: melhor fronteira tamanho×velocidade para logs/CSVs; LZMA2/XZ,
  Brotli, Parquet e dicionários entram como comparativos na Fase 2, não na base.
- **Rayon, não Tokio (ainda)**: a base é CPU-bound (hash); download assíncrono
  chega com o `download` na Fase 2.
- **Sem Arrow/Parquet/DuckDB na base**: só entram se o benchmark mostrar vantagem
  mensurável (critério do projeto, §8).
- **mmap ausente**: I/O sequencial em streaming é suficiente e mais seguro para
  esta etapa.

## Limites configuráveis (base)

- `--threads N` (0 = automático). Limites de RAM/disco/lote, checkpoints e
  retomada chegam com o pipeline da Fase 2/6 (`optimize`/`download`).

## Segurança de extração

`verify` rejeita entradas com `..` ou caminho absoluto. ZIP-bomb/path-traversal
na ingestão de ZIPs será tratado no `download` (Fase 2) com limites de tamanho,
contagem e escrita atômica (nunca marcar parcial como concluído).
