//! Manifesto versionado de proveniência (Nível 1 da verificação).
//!
//! Cada arquivo oficial gera uma entrada com: caminho relativo,
//! tamanho, SHA-256, tipo inferido e URL de origem (quando conhecida).
//! A serialização JSON é determinística: entradas ordenadas por caminho.

use anyhow::{Context, Result};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

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
    pub fn build_from_dir(root: &Path, source: &str) -> Result<Self> {
        let paths: Vec<PathBuf> = WalkDir::new(root)
            .min_depth(1)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
            .map(|e| e.path().to_path_buf())
            .collect();

        let mut files: Vec<FileEntry> = paths
            .par_iter()
            .map(|abs| {
                let rel = abs
                    .strip_prefix(root)
                    .map(|p| {
                        p.components()
                            .map(|c| c.as_os_str().to_string_lossy().into_owned())
                            .collect::<Vec<_>>()
                            .join("/")
                    })
                    .unwrap_or_else(|_| abs.to_string_lossy().into_owned());
                let meta = std::fs::metadata(abs)?;
                let sha256 = crate::hash::sha256_file(abs)?;
                let file_type = abs
                    .extension()
                    .map(|e| e.to_string_lossy().to_lowercase())
                    .unwrap_or_default();
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

    pub fn load(path: &Path) -> Result<Self> {
        let data =
            std::fs::read_to_string(path).with_context(|| format!("ler {}", path.display()))?;
        let m: Self = serde_json::from_str(&data)?;
        Ok(m)
    }

    pub fn total_bytes(&self) -> u64 {
        self.files.iter().map(|f| f.size).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifesto_ordena_caminhos() {
        let mut m = Manifest {
            format_version: 1,
            tool_version: "test".into(),
            source: "s".into(),
            files: vec![
                FileEntry {
                    path: "b.csv".into(),
                    size: 1,
                    sha256: "x".into(),
                    file_type: "csv".into(),
                    url: None,
                },
                FileEntry {
                    path: "a.csv".into(),
                    size: 1,
                    sha256: "x".into(),
                    file_type: "csv".into(),
                    url: None,
                },
            ],
        };
        m.files.sort_by(|a, b| a.path.cmp(&b.path));
        assert_eq!(m.files[0].path, "a.csv");
    }
}
