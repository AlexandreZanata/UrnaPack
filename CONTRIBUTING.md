# Contribuindo com o UrnaPack

## Ambiente

- Rust 1.99 via `rustup` (`rust-toolchain.toml` fixa o canal).
- Python 3.10+ (stdlib) para `scripts/validate.py`; `pyyaml`/`jsonschema`
  são opcionais (validação total) e instalados automaticamente no CI.

## Issues e pull requests

- Issues: use os templates (bug / funcionalidade). Descreva evidência,
  nunca conclusão política.
- Todo PR para `main` passa pelo CI (`fmt`, `check`, `clippy -D warnings`,
  `test`, validação do repositório). PR de externo roda sem escrita.
- PRs pequenos e focados; um tópico por PR.

## Testes (obrigatório)

- Novo comportamento exige teste reproduzível (`cargo test` ou
  `scripts/validate.py self-test`).
- Proibido teste que retorna sucesso sem executar a verificação.
- Proibidos dados fictícios: fixtures ficam em `tests/fixtures/`,
  identificadas como sintéticas, com hashes reais dos bytes.
- Parsers devem ter testes de: truncamento, campo desconhecido,
  duplicata legítima, arquivo corrompido.

## Código

- Rust como linguagem principal; `cargo fmt` + `clippy -D warnings` limpos.
- Simples e eficiente: reutilize `src/` existente; sem workspace multi-crate
  sem justificativa; sem dependência nova sem ganho demonstrado.
- Falhe explicitamente em dado não interpretável; nunca descarte
  silenciosamente; nunca marque parcial como concluído.

## Formato e compatibilidade

- Mudança incompatível no formato ⇒ `FORMAT_VERSION += 1` + teste de
  compatibilidade + atualização de `spec/`.
- Distinção obrigatória: compressão reversível (byte a byte) vs transformação
  semântica (equivalência documentada, perdas declaradas).
- Novos compressores/parsers: só entram com benchmark contra baselines nas
  mesmas condições e vantagem reproduzível.

## Reprodutibilidade

- Transformações determinísticas (saída ordenada, sem timestamps embutidos).
- Registre versão da ferramenta e das fontes em todo artefato.
