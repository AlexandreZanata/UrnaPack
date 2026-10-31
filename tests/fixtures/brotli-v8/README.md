# Fixture de compatibilidade Brotli 8 → 9

Dados sintéticos, não eleitorais. `manifest.json` registra hashes e tamanhos
recomputados dos bytes, revisão do produtor e hash do executável realmente
usado. A entrada é `../analyze/mt-valid.csv`, preservada em Latin-1/CRLF.

Produção: o `tsepack` da revisão indicada no manifesto executou
`codec compress --input <CSV da fixture> --output payload.br --method brotli-5`.
O teste atual deve restaurar exatamente os bytes com a biblioteca atualizada,
sem depender de comprimir e descomprimir com a mesma versão.
