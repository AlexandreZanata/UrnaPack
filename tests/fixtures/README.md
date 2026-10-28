# Fixtures deste diretório (todas SINTÉTICAS, sem vínculo com dados reais do TSE):
#
# - data/bu-amostra.csv: amostra mínima para validar o mecanismo (hashes reais dos bytes).
# - manifest-good.json: manifesto válido referenciando bu-amostra.csv (SHA-256 e tamanho reais).
# - manifest-bad-hash.json: idêntico ao válido, com o último dígito do hash alterado.
# - manifest-missing.json: referencia arquivo inexistente (testa detecção de ausência).
# - manifest-bad-version.json: format_version incompatível (testa guarda de versão).
# - index-dup.json: índice com a mesma entrada duas vezes (testa anti-duplicata).
# - map/csec-amostra.csv: CSV sintético Latin-1 com layout csec real (3 registros,
#   acentos, aspas, quebra de linha em campo, sentinelas e vazio). Hashes sempre
#   calculados dos bytes nos testes; nenhum digest fictício.
# - data/origem-v2.bin + origin-v2-good.json: origem sintética v2 (bytes e hash
#   reais) para o vínculo dataset→origem.
# - dataset-v2-good.json: dataset v2 migrado de manifest-good (mesmos pacotes),
#   com source_manifest_sha256 real do documento de origem e recibo de execução.
# - execution-good.json / execution-bad.json: recibo de execução válido e inválido
#   (sem tool) para o subcomando execution.
