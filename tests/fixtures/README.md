# Fixtures deste diretório (todas SINTÉTICAS, sem vínculo com dados reais do TSE):
#
# - data/bu-amostra.csv: amostra mínima para validar o mecanismo (hashes reais dos bytes).
# - manifest-good.json: manifesto válido referenciando bu-amostra.csv (SHA-256 e tamanho reais).
# - manifest-bad-hash.json: idêntico ao válido, com o último dígito do hash alterado.
# - manifest-missing.json: referencia arquivo inexistente (testa detecção de ausência).
# - manifest-bad-version.json: format_version incompatível (testa guarda de versão).
# - index-dup.json: índice com a mesma entrada duas vezes (testa anti-duplicata).
