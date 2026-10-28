//! Manifesto versionado de proveniência (Nível 1 da verificação).
//!
//! Cada arquivo oficial gera uma entrada com: caminho relativo,
//! tamanho, SHA-256, tipo inferido e URL de origem (quando conhecida).
//! A serialização JSON é determinística: entradas ordenadas por caminho.

use anyhow::{Context, Result};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::{FORMAT_VERSION, TOOL_VERSION};

/// Um arquivo rastreado pelo manifesto.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FileEntry {
    /// Caminho relativo ao diretório raiz, com `/` como separador.
    pub path: String,
    pub size: u64,
    pub sha256: String,
    /// Extensão em minúsculas sem ponto (ex.: "csv", "zip"), ou "" se ausente.
    pub file_type: String,
    /// URL oficial de origem, quando conhecida. `None` = amostra local.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
}

/// Manifesto de um conjunto de arquivos oficiais.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Manifest {
    pub format_version: u32,
    pub tool_version: String,
    /// Identificação da fonte (ex.: "tse-dados-abertos:resultados-2026-bu").
    pub source: String,
    pub files: Vec<FileEntry>,
}

impl Manifest {
    /// Varre `root` recursivamente, calcula SHA-256 em paralelo e
    /// retorna o manifesto ordenado por caminho (determinístico).
    ///
    /// A raiz pode ser um link legítimo (resolvido). Symlinks internos,
    /// arquivos especiais, raiz inexistente/não diretório, erros de
    /// travessia/metadata/leitura e nomes não representáveis sem perda
    /// reprovam explicitamente. Campos adicionais no JSON ainda são ignorados
    /// pela desserialização v1; não transportam garantias verificadas. A Etapa 2
    /// formalizará a política com versionamento e testes de compatibilidade.
    pub fn build_from_dir(root: &Path, source: &str) -> Result<Self> {
        let canonical = crate::traverse::resolve_root(root)?;
        let paths: Vec<PathBuf> = crate::traverse::collect_files(&canonical)?;

        let mut files: Vec<FileEntry> = paths
            .par_iter()
            .map(|abs| {
                let rel = crate::traverse::rel_to_canonical(&canonical, abs)?;
                let meta = std::fs::metadata(abs)
                    .with_context(|| format!("metadata {}", abs.display()))?;
                let sha256 = crate::hash::sha256_file(abs)?;
                // Tipo por extensão sem conversão com perda (rel já é UTF-8).
                let file_name = rel.rsplit('/').next().unwrap_or(&rel);
                let file_type = match file_name.rfind('.') {
                    Some(i) if i + 1 < file_name.len() => file_name[i + 1..].to_lowercase(),
                    _ => String::new(),
                };
                Ok(FileEntry {
                    path: rel,
                    size: meta.len(),
                    sha256,
                    file_type,
                    url: None,
                })
            })
            .collect::<Result<Vec<_>>>()
            .context("calcular hashes do diretório")?;

        files.sort_by(|a, b| a.path.cmp(&b.path));

        Ok(Self {
            format_version: FORMAT_VERSION,
            tool_version: TOOL_VERSION.to_string(),
            source: source.to_string(),
            files,
        })
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(path, json).with_context(|| format!("escrever {}", path.display()))?;
        Ok(())
    }

    /// Lê um manifesto de origem v1 válido, preservando compatibilidade.
    ///
    /// Rejeita versão incompatível explicitamente; não redesenha o contrato
    /// nesta etapa.
    pub fn load(path: &Path) -> Result<Self> {
        let data =
            std::fs::read_to_string(path).with_context(|| format!("ler {}", path.display()))?;
        let m: Self = serde_json::from_str(&data)?;
        if m.format_version != FORMAT_VERSION {
            anyhow::bail!(
                "format_version incompatível em {}: {} (suportado: {})",
                path.display(),
                m.format_version,
                FORMAT_VERSION
            );
        }
        Ok(m)
    }

    pub fn total_bytes(&self) -> u64 {
        self.files.iter().map(|f| f.size).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hash::sha256_bytes;

    #[test]
    fn manifesto_ordena_caminhos_com_hash_real() {
        let dir = tempfile::tempdir().unwrap();
        let first = include_bytes!("../tests/fixtures/data/bu-amostra.csv");
        let second = include_bytes!("../tests/fixtures/map/csec-amostra.csv");
        std::fs::write(dir.path().join("b.csv"), second).unwrap();
        std::fs::write(dir.path().join("a.csv"), first).unwrap();
        let manifest = Manifest::build_from_dir(dir.path(), "fixture-sintetica").unwrap();
        assert_eq!(manifest.files.len(), 2);
        assert_eq!(manifest.files[0].path, "a.csv");
        assert_eq!(manifest.files[0].size, first.len() as u64);
        assert_eq!(manifest.files[0].sha256, sha256_bytes(first));
        assert_eq!(manifest.files[1].path, "b.csv");
        assert_eq!(manifest.files[1].size, second.len() as u64);
        assert_eq!(manifest.files[1].sha256, sha256_bytes(second));
    }
}
