# Arquitetura — base atual e direção de implementação

## Estrutura e estado real

Um executável Rust (`tsepack`) e sua biblioteca interna. Sem workspace,
microsserviços ou novas dependências sem ganho demonstrado. O plano executável
está em `docs/PLANO.md`; a primeira entrega está em `docs/ETAPA-1.md`.

Módulos existentes:

- `main.rs`: CLI; `inspect`, `benchmark` e `verify` implementados; outros
  subcomandos falham explicitamente.
- `hash.rs`: SHA-256 de bytes/arquivos, com leitura de arquivos em streaming.
- `manifest.rs`: manifesto de origem v1, construção ordenada com Rayon.
- `inspect.rs`: inventário físico por extensão; não interpreta dados eleitorais.
- `benchmark.rs`: stored/ZSTD por arquivo, round-trip comparando bytes.
  A leitura atual do arquivo inteiro em memória é limitação da base.
- `verify.rs`: confronto dos arquivos declarados com tamanho e SHA-256,
  validação de versão, unicidade de caminhos e rejeição de symlinks internos.
- `traverse.rs`: política compartilhada de raiz, nomes portáveis, arquivos
  regulares e propagação de erros de travessia.

Automações Python ficam em `scripts/`. A Etapa 1 implementa um mapeador de ZIP/CSV
com biblioteca padrão; parsing/transformação eleitoral de produção permanece
em Rust. Não criar um segundo compressor ou parser canônico em Python.

## Camadas propostas

1. **Evidência original:** downloads imutáveis, sidecars, documentos de leiaute,
   assinaturas, índices e membros. Bytes recuperáveis conforme objeto declarado.
2. **Mapa estrutural:** inventário, cabeçalhos, formatos identificados e
   limitações. Uma catalogação não implica interpretação semântica completa.
3. **Canônico:** todos os campos e ocorrências suportados, tipos exatos,
   sentinelas e contexto, com proveniência. Parser e esquema versionados.
4. **Produtos analíticos:** consultas, agregações e modelos regeneráveis,
   com escopo, parâmetros e dependências registrados.

Representações intermediárias e caches só são materializados quando úteis;
se forem mantidos, seus bytes entram no custo total. O formato próprio não é
pré-requisito para as camadas canônica e analítica.

## Contratos de artefato

Hoje coexistem dois contratos distintos, ambos com `format_version: 1`:

- origem Rust: `source`, `files[]`, caminho, tamanho, SHA-256 e URL opcional;
- dataset de distribuição: `spec/manifest.schema.json`, com `source_files[]`,
  `packages[]`, perfil e identificação eleitoral.

O `verify` Rust atual aceita o primeiro, não o segundo. Não usar um como se
fosse o outro. A Etapa 1 preserva o formato de origem válido existente e corrige
as verificações delimitadas. A Etapa 2 formaliza os tipos/discriminadores,
versões, política de campos desconhecidos e referências entre os contratos,
com migração e testes antes de qualquer mudança incompatível.

O mapa estrutural tem seu próprio `artifact_kind` e `format_version`;
não reutilizar `FORMAT_VERSION` da origem para evoluí-lo. Campos adicionais
no JSON de origem ainda não têm uma política segura implementada: não usar
extensões silenciosas para transportar novas garantias durante a Etapa 1.

Conteúdo determinístico inclui caminhos relativos ordenados, cabeçalhos em
ordem original e hashes calculados. Datas/tempos da execução ficam em recibo
separado para não invalidar a comparação do conteúdo entre duas execuções.

## Unidades e vínculos

- Contexto seção/cargo contém medidas compartilhadas, depois de igualdade
  verificada; tabela de votos preserva ocorrências por votável.
- Correspondência esperada de seção, contingência e efetivada são fontes
  distintas. Chaves e cardinalidades são hipóteses até verificação.
- Logs e RDV mantêm granularidade própria. Não os reduzir a totais de seção
  como única representação preservada.
- Proveniência usa referência compacta a fontes + membro/ordinal, sem repetir
  URLs e hashes textuais em cada registro. O vínculo deve recuperar a fonte.
- Ordem de membros ZIP e nomes repetidos precisam ser identificáveis por
  ordinal; nomes iguais não autorizam sobrescrita ou descarte de ocorrências.

## Segurança e recursos

Permitir que a raiz indicada pelo usuário seja um link legítimo, como `dados`.
A política conservadora da Etapa 1 rejeita symlinks internos, arquivos especiais
e caminhos não representáveis sem perda; erros de leitura propagam reprovação.
Não prometer proteção contra substituições concorrentes de arquivos sem uma
implementação apropriada: verificar conjuntos imutáveis e documentar o limite.

Na geração de relatórios, manter um único escritor por diretório de saída.
Resolver aliases de fonte/saída antes de escrever e usar árvores separadas.
Gerações anteriores ficam em `.previous-*`; `map.json` é o último arquivo
publicado e seu hash de `members.jsonl` precisa ser conferido pelo consumidor.
Falha interrompe o processamento e deixa diagnóstico, sem mapa completo atual.

O mapeador da Etapa 1 não extrai caminhos controlados por ZIP no disco. Identifica
travessias, nomes duplicados, formatos opacos e limites excedidos explicitamente.
Aninhamento, extração gerenciada e parsers binários chegam com contratos e
limites próprios, sem confiar apenas em extensão, CRC ou tamanhos declarados.

Valores operacionais ficam em `scripts/limits.env`. Streaming, lotes, checkpoints
e custo de consultas precisam ser medidos antes de afirmar execução em 32 GB
na escala nacional. Rayon permanece adequado ao hashing; aquisição assíncrona,
Parquet/Arrow e outros componentes só entram quando a necessidade for demonstrada.
