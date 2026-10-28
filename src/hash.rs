//! Hash SHA-256 em streaming (sem carregar o arquivo inteiro na RAM).

use anyhow::{Context, Result};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;

/// Calcula o SHA-256 de um arquivo, lendo em blocos de 1 MiB.
/// Retorna o digest em hexadecimal minúsculo.
pub fn sha256_file(path: &Path) -> Result<String> {
    let file = File::open(path).with_context(|| format!("abrir {}", path.display()))?;
    let mut reader = BufReader::with_capacity(1024 * 1024, file);
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1024 * 1024];
    loop {
        let n = reader
            .read(&mut buf)
            .with_context(|| format!("ler {}", path.display()))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

/// Calcula o SHA-256 de bytes em memória (conveniência para testes).
pub fn sha256_bytes(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vetor_conhecido_sha256() {
        // Vetor padrão: SHA-256 de "abc".
        assert_eq!(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn arquivo_vazio_tem_hash_conhecido() {
        let dir = std::env::temp_dir().join("tsepack_hash_test");
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("vazio.bin");
        std::fs::write(&p, b"").unwrap();
        assert_eq!(
            sha256_file(&p).unwrap(),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        std::fs::remove_file(&p).ok();
    }
}
