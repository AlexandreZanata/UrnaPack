# AGENTS.md — Regras para agentes de IA neste repositório

Arquivo único de orientação (não duplicar em outros diretórios).

1. **Rust é a linguagem principal.** Python só em `scripts/` (automação).
2. **Preserve a integridade dos dados** acima de qualquer otimização.
3. **Proibidos dados fictícios**: nenhum hash, tamanho, contagem ou taxa de
   compressão inventada — em código, manifestos, releases ou relatórios.
   Fixtures sintéticas vivem em `tests/fixtures/`, identificadas, com hashes
   reais dos bytes.
4. **Testes reproduzíveis** para todo comportamento novo; teste que não executa
   a verificação é proibido.
5. **Verificação criptográfica**: SHA-256 recomputado a partir dos bytes;
   divergência reprova explicitamente (exit ≠ 0).
6. **Distinga sempre** compressão reversível (byte a byte) de transformação
   semântica (equivalência documentada, perdas declaradas). Semântica ≠ bytes.
7. **Nunca elimine dados silenciosamente** (registros, duplicatas, campos
   desconhecidos). Falhe explicitamente.
8. **Simplicidade**: YAGNI/KISS/DRY; reutilize `src/`; sem workspace, sem
   microsserviços, sem dependência nova sem ganho demonstrado.
9. **Compatibilidade**: mudança incompatível ⇒ versionamento explícito
   (`FORMAT_VERSION`, `format_version`) + teste + atualização de `spec/`.
10. **Limites centralizados** em `scripts/limits.env`; não duplique valores em
    workflows/scripts.
11. **Workflows**: permissão mínima, sem `pull_request_target` com código de
    PR, actions fixadas por SHA, sem segredos em logs.
12. **Nenhuma alegação de fraude ou autenticidade eleitoral** sem evidência
    técnica adequada. Auditoria gera evidência reproduzível, não conclusão
    política.
