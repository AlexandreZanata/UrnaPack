# Segurança — UrnaPack

## Reportar vulnerabilidades

- **Não abra issue pública** para vulnerabilidades. Prefira
  *Security Advisories* do GitHub (aba Security → Report a vulnerability)
  ou contato direto com o mantenedor.
- Inclua: versão/commit, impacto, PoC mínima, se envolve parser,
  hash/verificação ou supply chain.
- Alvo de resposta inicial: 7 dias. Divulgação responsável: correção ou
  mitigação antes da exposição pública; crédito ao repórter, se desejado.

## O que é sensível aqui

- **Parsers de arquivos do TSE** (ASN.1, ZIPs, CSVs): entrada hostil pode
  conter path traversal, ZIP bombs, estouros e campos malformados.
  Regras: limites de tamanho/contagem, escrita atômica, falha explícita,
  fuzzing de parsers novos.
- **Corrupção de dados / falhas de hash**: qualquer divergência SHA-256
  reprova a verificação (`verify` sai com exit 1). Hash próprio nunca é
  apresentado como assinatura do TSE.
- **Transformações**: perda silenciosa é tratada como bug de segurança de
  integridade — todo descarte deve ser explícito e declarado no perfil.
- **Supply chain**: dependências via crates.io fixadas em `Cargo.lock`;
  Dependabot semanal; `cargo audit` no CI; actions externas fixadas por
  commit SHA; workflows de PR sem permissão de escrita; sem
  `pull_request_target` com código de PR.

## Segredos

- Nenhum token/senha/chave no Git. `scripts/validate.py repo` faz varredura
  básica (chaves privadas, tokens `ghp_`/`gho_`, chaves AWS).
- Tokens de automação: só via GitHub Secrets, nunca em logs
  (workflows usam `GITHUB_TOKEN` com permissão mínima por job).

## Arquivos maliciosos em datasets

Pacotes publicados passam por: limite de tamanho, hash recomputado,
manifesto validado contra schema e re-verificação pós-upload antes de
entrar no índice público. Publicação exige `verification_status: validated`.
