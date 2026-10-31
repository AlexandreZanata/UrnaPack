# Fixtures sintéticas da análise descritiva (Etapa 5A)

Todas são SINTÉTICAS, sem vínculo com o TSE. Usam o cabeçalho canônico
de 45 campos e valores de escopo MT/2026/t1 apenas para exercitar o perfil.
Hashes abaixo são SHA-256 dos bytes reais (Latin-1, CRLF, separador `;`).

| arquivo | SHA-256 | registros | finalidade |
|---|---|---:|---|
| `header-bad.csv` | `a8bf847071c8be6b98a49cd6549c4fa35f8c48b81683dcfda0a91a31234f8cbc` | 1 | cabeçalho divergente |
| `mt-agregadas.csv` | `52e95667f2368323a3c385b38861c137b0e34c2db4625ab1f473661e9b2b4b59` | 8 | DS_SECOES_AGREGADAS não sentinela |
| `mt-context-divergent.csv` | `1aef3c046aaf7f061d11573a0257b856d39fc1c176583111a4e8a816269f5835` | 2 | mesmo contexto divergente entre linhas da seção/cargo |
| `mt-duplicate-conflict.csv` | `73ed99bf2e4e2cc76a3468fccddfd81b7c9018c1ddf90c1abda6bb8e81728987` | 2 | mesma chave com conteúdo divergente |
| `mt-duplicate-exact.csv` | `29d6258bd78afdc429c7fb20f456260416af4a7fe4c6ae5a5af9ebcbe42568b2` | 2 | ocorrência repetida idêntica |
| `mt-out-of-scope.csv` | `d09660bb615e90d56cf404aed7f96f87febe4911084e59412dc429148ae4a18e` | 1 | turno fora do perfil |
| `mt-overflow.csv` | `0064b7e25243bf54ce11ba6a51145401ec2d2c907d8fbc2426f467957f322e2d` | 2 | overflow na soma de QT_VOTOS |
| `mt-truncated.csv` | `a4ee8805d72ca6c5ff2272495f20d136c1a7492ec63825e2b70a922e05c7b73f` | 1 | registro truncado (44 campos) |
| `mt-unknown-category.csv` | `b505e5526f4d8bd77abb013db061ab004c6dd3b1adc97a80fd955bf26b76552d` | 1 | categoria de votável desconhecida |
| `mt-valid.csv` | `7fab350089ebbe67dbd881dec3f6b942e214e26950e081604463b3b7fb745381` | 8 | contexto repetido, zeros à esquerda, sentinelas, categorias, denominador zero |
