# Arquitetura — base atual e direção de implementação

## Estrutura e estado real

Um executável Rust (`tsepack`) e sua biblioteca interna. Sem workspace,
microsserviços ou novas dependências sem ganho demonstrado. O plano executável
está em `docs/PLANO.md`; a primeira entrega está em `docs/ETAPA-1.md`.

Módulos existentes:

- `main.rs`: CLI; `inspect`, `benchmark`, `verify`, `pack`/`unpack`, `codec`,
  `archive`, `optimize`, `restore`, `queries` implementados; outros
  subcomandos falham explicitamente.
- `hash.rs`: SHA-256 de bytes/arquivos, com leitura de arquivos em streaming.
- `manifest.rs`: manifesto de origem v2 (leitura v1/v2), construção ordenada com Rayon.
- `inspect.rs`: inventário físico por extensão; não interpreta dados eleitorais.
- `benchmark.rs`: stored/ZSTD/Brotli por arquivo em streaming; BU web colunar/sólido,
  hashes dos bytes decodificados, artefatos e retomada por método. Relatório v2
  em `spec/benchmark-v2.md`.
- `bweb.rs`: pacote experimental v2 e inverso; todos os valores lexicais em
  colunas, ordinal preservado, emissão conferida contra SHA-256 do CSV original.
- `codec.rs`: codecs padrão, treinamento de dicionário, streaming e promoção
  somente após prova de bytes; XZ é subprocesso, demais encoders são bibliotecas Rust.
- `archive.rs`: arquivo FORENSIC v2, sólido ou por fonte, com recibo vinculado;
  TAR padrão e arquivos originais opacos preservados, incluindo ZIPs completos.
- `queries.rs`: Q1/Q2 e recuperação de controle, sem somar contexto por votável.
- `output.rs` / `limits.rs`: saídas temporárias e limites compartilhados com
  `scripts/limits.env` (Rust incorpora os valores na compilação).
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

Hoje coexistem contratos distintos, com versões independentes:

- origem Rust v2 (leitura v1/v2): `source`, `files[]`, caminho, tamanho,
  SHA-256 e URL opcional; campos desconhecidos reprovam;
- dataset de distribuição v1/v2: `spec/manifest*.schema.json`, com `source_files[]`,
  `packages[]`, perfil e identificação eleitoral;
- execução v1: `spec/execution.schema.json`;
- pacote BU web v2: `spec/bweb-pack-v2.md` (leitura de v1 com compromisso SHA válido).
- arquivo FORENSIC local v2: `spec/archive-v2.md`; view regenerável v1:
  `spec/bweb-view-v1.md`. Esses contratos têm escopo e versões próprios.

O `verify` Rust atual aceita o primeiro, não o segundo. Não usar um como se
fosse o outro. A migração de origem v1→v2 tem testes. O dataset v2 vincula o
manifesto de origem, porém seu campo `execution` ainda é apenas um descritor.
Não há compromisso por hash do recibo; `--require-status validated|published`
bloqueia v2 até um contrato completo e versionado. Validação estrutural
isolada não comprova reexecução nem libera publicação.
O arquivo local v2 tem recibo com hash, entradas/saídas reconfrontadas e prova
do conteúdo restaurado. Isso resolve sua execução local, sem promover o
manifesto antigo de distribuição nem publicar dados automaticamente.

O mapa estrutural tem seu próprio `artifact_kind` e `format_version`;
não reutilizar `FORMAT_VERSION` da origem para evoluí-lo. Campos adicionais
no JSON de origem reprovam; novas garantias exigem contrato explícito.

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
