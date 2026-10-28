# Etapa 4 — experimento completo de compressão do acervo local de MT

Implementação: `scripts/compression_stage.py`, orquestrando codecs, arquivos
e consultas do executável Rust. Ferramentas de comparação: XZ, PyArrow, DuckDB
e psutil. Dependências Python fixadas em `scripts/requirements-compression.txt`.
`tar` é a única dependência Rust adicional desta etapa: permite contêiner padrão,
reprodução determinística e validação de headers sem implementar outro TAR.

## Escopo e matriz

O corpus são todos os arquivos declarados no manifesto local de MT, incluindo
os ZIPs já comprimidos e sidecars. O mapa continua declarando a cobertura parcial
de t2. Isso não equivale à expansão nacional nem à conclusão da Etapa 5.

- Downloads completos: stored, TAR sólido + ZSTD 3/19, XZ 6/9e, Brotli 5;
  arquivos individuais com stored/ZSTD3/XZ6. Comparação final inclui o tamanho
  de descritores, manifesto, recibo e enquadramento do contêiner.
- Membro BU web completo: stored, ZSTD 1/3/10/19, XZ 6/9e, Brotli 5/11,
  ZSTD3/19 em blocos independentes de 1 MiB. Brotli 11 usa janela 24;
  qualidade 5 usa 22. O grid de ZIPs opacos limita Brotli a 5.
- Mesmo modelo colunar: ZSTD por coluna e sólido 1/3/10/19; fluxo sólido
  com XZ6/9e, Brotli5 e ZSTD19 em blocos. Manifesto e prefixos entram na conta.
- Dicionários ZSTD: partição por seção sem compartilhar grupos entre treino,
  ajuste e teste; tamanhos derivados de `MAX_DICTIONARY_BYTES` (1/8, 1/2 e inteiro).
  Seleção na validação por bytes comprimidos + dicionário, nível fixo 10;
  comparação independente no teste; candidato escolhido também medido no corpus todo.
- Parquet ZSTD3/19, row groups 8.192/65.536, dicionário interno e estatísticas;
  todos os campos como strings, com restauração integral conferida.

É um grid finito declarado. O vencedor é a menor alternativa **medida**, sem
alegação de ótimo absoluto entre todos os algoritmos e parâmetros possíveis.
Formatos especializados e novas transformações continuam na Etapa 7.

## Dicionários sem vazamento

Chave de grupo: pleito, turno, UF, município, zona, seção. SHA-256 do JSON
compacto UTF-8 da chave; primeiros 8 bytes big-endian módulo 10: 0–5 treino,
6–7 validação, 8–9 teste. Todos os cargos/votáveis do grupo ficam na mesma
partição. Quantidades reais e hashes das partições são registrados.
Treino usa no máximo os primeiros 32 MiB da partição de treino, em amostras
de 32 KiB. Esses limites ficam no arquivo central; não se declara amostragem
geográfica representativa a partir desse prefixo. Validação/teste abrangem suas
partições completas. Nenhuma decisão usa o teste; custo do dicionário é incluído.

## Consultas e recursos

Q1 soma votos por cargo/UF/município. Q2 usa Presidente: confere igualdade de
aptos/comparecimento/abstenções dentro de cada seção e conta o contexto uma
única vez por seção, antes de agregar por zona. Recuperação localizada confere
todas as ocorrências em ordem da primeira chave real de seção/cargo.

Rust/CSV é referência; pacote colunar e quatro variantes Parquet devem produzir
o mesmo JSON de resultados. Cada consulta é repetida conforme `BENCH_REPETITIONS`.
Isso verifica os controles do experimento, sem liberar joins/modelos da Etapa 5.

Tempo de codec vem de `Instant`; inclui I/O de compressão/finalização e
descompressão+SHA-256. Processo tem tempo de parede adicional e RSS da árvore
amostrado com psutil a cada `BENCH_POLL_MILLIS`: pico **amostrado**, podendo
subestimar pulsos curtos e contar páginas compartilhadas em mais de um processo.
Disco por caso é soma lógica dos arquivos sob sua pasta, amostrada; entradas
compartilhadas são contabilizadas separadamente. Não representa alocação física
de blocos nem pico global de todos os aplicativos. Os primeiros métodos podem
rodar concorrentemente; o cache do SO não é esvaziado. Não extrapolar para o Brasil.

A compressão da view selecionada é repetida; cada bitstream deve reproduzir
o SHA-256 escolhido, com round-trip novamente conferido. O arquivo completo é
restaurado em disco; adicionalmente, sua decodificação para hash, sem gravar
novas cópias, é repetida. Essa latência de conferência não é a de escrita de
todos os arquivos restaurados. O custo de compressão integral dos downloads
tem uma execução por candidato; variação de compressão da view e de recuperação
do arquivo/consultas é registrada, sem inventar repetição dos métodos caros.

## Armazenamento escolhido

Comparar arquivo sólido e seleção por fonte após selar ambos com os mesmos
compromissos. O menor diretório completo é promovido como arquivo FORENSIC.
Fonte com resultado maior permanece stored. ZIPs originais continuam recuperáveis
byte a byte; todos os campos desconhecidos internos continuam nos ZIPs.

O bundle mínimo inclui arquivo, proveniência comprimida e receita da view.
O cache de consulta é opcional e regenerável a partir do ZIP preservado; guardá-lo
permanentemente soma seu custo. Originais locais e intermediários do experimento
também permanecem e são reportados, sem alegar espaço liberado no disco.

Contratos: `spec/archive-v2.md`, `spec/bweb-view-v1.md`, `spec/benchmark-v2.md`.
O manifesto de distribuição v2 antigo não é promovido: seu portão de publicação
continua bloqueado. O arquivo local tem contrato próprio com recibo vinculado.

## Reprodução e conclusão

Pré-requisitos: dados brutos, manifesto, mapa integral da Etapa 1 e pacote BU web
v2 já conferido na Etapa 3. Usar uma saída nova ou retomar a mesma saída com
entradas imutáveis; um único escritor por pasta. Exemplo no acervo desta revisão:

```bash
cargo build --release --locked --offline
python3 -m pip install -r scripts/requirements-compression.txt
python3 scripts/compression_stage.py all \
  --csv relatorios-locais/revisao-fases/restored.csv \
  --raw-root dados/brutos/2026 \
  --manifest dados/manifest-2026-mt.json \
  --map relatorios-locais/etapa-1/mt/map.json \
  --pack relatorios-locais/revisao-fases/bweb-v2 \
  --output relatorios-locais/experimento-novo
```

Os checkpoints guardam hashes reais de origem, artefato e dicionário. Retomada
de codecs reconfere também a decodificação; um órfão não vira resultado completo.
Parquet tem reconstrução conferida no produtor; seu hash é rechecado ao retomar.
Nova decisão de view exige grid completo e não reutiliza prova de outro candidato.
Falha interrompe a fase, sem `stage-report.json` completo novo.

`stage-report.json` só recebe `complete: true` após matriz, consultas, repetições,
seleção, restauração de todos os arquivos e verificação contra a origem.
`final/bundle.json` descreve o conjunto portátil mínimo; `final/forensic-mt/`
é restaurável com `tsepack restore`. Os resultados desta execução, quando
concluída, ficam documentados em `docs/RESULTADO-COMPRESSAO-MT.md`.
