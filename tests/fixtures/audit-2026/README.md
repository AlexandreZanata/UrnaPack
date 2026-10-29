# Fixture sintética — auditoria 2026

Não representa dados do TSE. Duas seções artificiais para verificar agregação, limites de horário, denominadores e falhas explícitas.

SHA-256 real dos bytes de `synthetic.csv`: `e586b1cee52d7c54ff35e9098909e833ef69a139f67e7973a213a8382ce0181a`.

`coverage-synthetic.json` contém um caso artificial de conciliação com seção sem votantes. Não representa dados oficiais. Bytes e SHA-256 real em `hashes.json`.

Os arquivos `log*-synthetic.*` são inteiramente artificiais e identificados para testar o parser de logs. Incluem eventos de outro turno e fronteiras exatas de horário. O token final das linhas é o SHA-256 truncado do prefixo de teste; **não** é um autenticador TSE. O ZIP e todos os corpos têm hashes reais em `hashes.json`. Nenhuma URL de fixture afirma publicação real no TSE.
