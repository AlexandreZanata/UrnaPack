# BU web — pacote colunar reversível v1 (Etapa 3)

> Contrato experimental legado, substituído por [v2](bweb-pack-v2.md).
> A implementação inicial não conferia a emissão contra os bytes da origem no
> produtor e permitia omitir seu hash. A leitura atual só aceita v1 com hash
> de origem válido, após verificar manifesto, colunas e restauração. A escrita
> gera exclusivamente v2. As garantias abaixo eram a intenção do protótipo;
> a revisão e as condições executáveis atuais estão na especificação v2.

Contêiner diretório, byte a byte restaurável para o membro CSV original.
Escopo: layout `bweb` 45 colunas (fingerprint em `spec/bweb.canonical-v1.md`).
Garantias separadas: restauração byte a byte (SHA-256) e equivalência semântica
(mesmas linhas/valores lógicos, verificada por leitura independente em Python).

## Regra de emissão TSE observada (MT 2026 t1, 891.997/891.997 linhas)

- Cabeçalho: todas as 45 colunas sempre com aspas (`QUOTE_ALL`).
- Linhas de dados, por conjunto de colunas (uniforme em 100% das linhas):
  - **Q (26, sempre com aspas)**: `DT_GERACAO, HH_GERACAO, NM_TIPO_ELEICAO,
    DT_PLEITO, DS_ELEICAO, SG_UF, NM_MUNICIPIO, DS_CARGO_PERGUNTA, SG_PARTIDO,
    NM_PARTIDO, DT_BU_RECEBIDO, DS_TIPO_URNA, DS_TIPO_VOTAVEL, NM_VOTAVEL,
    CD_CARGA_1_URNA_EFETIVADA, CD_CARGA_2_URNA_EFETIVADA,
    CD_FLASHCARD_URNA_EFETIVADA, DT_CARGA_URNA_EFETIVADA,
    DS_CARGO_PERGUNTA_SECAO, DS_SECOES_AGREGADAS, DT_ABERTURA, DT_ENCERRAMENTO,
    QT_ELEI_BIOM_SEM_HABILITACAO, DT_EMISSAO_BU, NR_JUNTA_APURADORA,
    NR_TURMA_APURADORA`.
  - **B (19, nunca com aspas)**: `ANO_ELEICAO, CD_TIPO_ELEICAO, CD_PLEITO,
    NR_TURNO, CD_ELEICAO, CD_MUNICIPIO, NR_ZONA, NR_SECAO, NR_LOCAL_VOTACAO,
    CD_CARGO_PERGUNTA, NR_PARTIDO, QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCOES,
    CD_TIPO_URNA, CD_TIPO_VOTAVEL, NR_VOTAVEL, QT_VOTOS, NR_URNA_EFETIVADA`.
- Separador `;`, terminador `\r\n`, codificação Latin-1 (1 byte/caractere).
- Escape: `"` interno vira `""`. Neste corpus nenhum valor contém `"` nem quebra
  de linha física (891.998 linhas físicas = 1 cabeçalho + 891.997 registros);
  o inversor falha explicitamente se valor de coluna B contiver
  `;`, `"`, CR ou LF (nunca emite bytes ambíguos).

## Layout do pacote (`<saída>/`)

- `pack.json`: `{artifact_kind: bweb_columnar_pack, format_version: 1,
  family: bweb, header: [...45], quoted: [bool ×45], rows, encoding: latin-1,
  lineterminator: \r\n, quoting_rule: tse-text-columns-v1,
  source_member_sha256?, columns: [{file, rows, bytes, sha256}×45]}`.
- `columns/00.bin` … `columns/44.bin`: por coluna, em ordem das linhas,
  registros `u32 LE comprimento + bytes Latin-1` (sem escapes, sem perdas).
  `columns[].sha256` é o SHA-256 dos bytes do arquivo `.bin` (inclui prefixos).

## CLI

```bash
tsepack pack --family bweb --input bweb.csv --output pacote/ \
  --source-sha <sha256-do-membro>
tsepack unpack --input pacote/ --output bweb-restaurado.csv
```

`--source-sha` grava o SHA do membro de origem no pacote; o `unpack`
reconfronta o restaurado e reprova em divergência (FORENSIC automático).

`pack` falha sem transformar parcialmente: cabeçalho divergente, contagem de
campos divergente (com ordinal/linha física) ou valor B com especial reprova com
exit ≠ 0. `unpack` valida `pack.json` (versão, 45 colunas/arquivos, SHAs) antes
de emitir. A aprovação final é SHA-256 do restaurado igual ao original
(FORENSIC) mais equivalência por leitura independente (`scripts/verify_pack.py`).
