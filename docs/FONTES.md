# Fontes oficiais — MT 2026 (Etapa 2)

Origem: portal de dados abertos do TSE, base
`https://cdn.tse.jus.br/estatistica/sead` (evidência: script de aquisição local;
padrões de caminho abaixo conferidos contra a CDN em 28/10/2026 com um sidecar).
Nenhum caminho físico da máquina, nenhum inventário de bytes/hashes do disco.

## Arquivos por família (nome oficial → caminho na CDN)

| Arquivo oficial | Caminho sob a base | Sidecar oficial | Estado do sidecar |
|---|---|---|---|
| `bweb_1t_MT_051020261403.zip` | `eleicoes/eleicoes2026/buweb/` | `.sha512` | publicado; confrontado OK |
| `bu_imgbu_logjez_rdv_vscmr_2026_1t_MT.zip` | `eleicoes/eleicoes2026/arqurnatot/` | — | não publicado (limitação) |
| `CESP_1t_MT_031020261534.zip` | `eleicoes/eleicoes2026/correspesp/` | `.sha512` | publicado; confrontado OK |
| `CESP_1t_MT_041020261259.zip` | `eleicoes/eleicoes2026/correspesp/` | `.sha512` | publicado; confrontado OK |
| `CEFT_1t_MT_051020261049.zip` | `eleicoes/eleicoes2026/correspefet/` | `.sha512` | publicado; confrontado OK |
| `votacao_secao_2026_MT.zip` | `odsele/votacao_secao/` | — | não publicado (limitação) |
| `Relatorio_Resultado_Totalizacao_2026_MT.zip` | `odsele/relatorio_resultado_totalizacao/` | — | não publicado (limitação) |
| `CESP_2t_MT_241020261231.zip` | `eleicoes/eleicoes2026/correspesp/` | `.sha512` | publicado; confrontado OK |

Confronto `sha512sum --check` executado por diretório de turno contra os 5
sidecars publicados: 5/5 OK. Isso verifica correspondência com o sidecar
disponível; não equivale a validação de assinatura, cadeia ou autoria.
Ausência de sidecar não significa ausência de dados nem autoriza declarar
assinatura verificada.

## Cobertura do acervo local (gerações obtidas)

- **Turno 1**: completo no recorte obtido — BU web, arquivos da urna
  (bu/rdv/imgbu/log/vsc), 2 gerações CESP, CEFT, votação por seção e relatórios.
- **Turno 2**: parcial — só CESP e relatórios com PDFs de t2. BU web de t2 e
  arquivos da urna de t2 não publicados até esta data (repetir aquisição quando
  o TSE publicar; nunca preencher t2 com dados de t1).
- Gerações CESP/CEFT são snapshots preservados (pleitos 3220/3221); pastas e
  nomes são pistas de aquisição, não prova de turno dos membros (ver
  `docs/DADOS-BRUTOS.md`).

## Escopo para a aquisição gerenciada

Cada arquivo do manifesto de origem carrega sua `url` oficial (Etapa 2:
`scripts/fetch_source.py` exige URL por arquivo). Metadados HTTP observados na
CDN: `Content-Length`, `ETag`, `Last-Modified`; sem `Accept-Ranges` no objeto
verificado — a ferramenta recomeça do zero e registra `range_ignored` quando o
servidor ignora o intervalo. Parciais vivem como `.partial` e só são promovidos
por rename após SHA-256 e tamanho conferidos.
