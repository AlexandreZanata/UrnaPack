//! Verificador independente (Níveis 1–2 da verificação).
//!
//! Reexecuta o hashing dos arquivos de origem e compara com o
//! manifesto registrado: detecta ausentes, truncados/alterados e
//! divergências de versão. NÃO compartilha estado com o compressor:
//! lê o manifesto do disco e recalcula tudo a partir dos arquivos.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::manifest::Manifest;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum VerifyStatus {
    Ok,
    Missing,
    SizeMismatch,
    HashMismatch,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileVerdict {
    pub path: String,
    pub status: VerifyStatus,
    pub expected_sha256: String,
    pub actual_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifyReport {
    pub manifest: String,
    pub source_dir: String,
    pub format_version: u32,
    pub files_checked: usize,
    pub passed: usize,
    pub failed: usize,
    pub verdicts: Vec<FileVerdict>,
    pub approved: bool,
}

pub fn verify(manifest_path: &Path, source_dir: &Path) -> Result<VerifyReport> {
    let manifest = Manifest::load(manifest_path)?;
    let mut verdicts = Vec::with_capacity(manifest.files.len());
    let mut passed = 0usize;

    for entry in &manifest.files {
        // Defesa contra path traversal no manifesto: rejeita `..` e raiz.
        let rel = Path::new(&entry.path);
        let unsafe_path = rel.is_absolute()
            || rel
                .components()
                .any(|c| matches!(c, std::path::Component::ParentDir));
        if unsafe_path {
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::Missing,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: None,
            });
            continue;
        }
        let abs = source_dir.join(rel);
        if !abs.is_file() {
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::Missing,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: None,
            });
            continue;
        }
        let size = std::fs::metadata(&abs)
            .with_context(|| format!("stat {}", abs.display()))?
            .len();
        if size != entry.size {
            let actual = crate::hash::sha256_file(&abs).ok();
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::SizeMismatch,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: actual,
            });
            continue;
        }
        let actual = crate::hash::sha256_file(&abs)?;
        if actual == entry.sha256 {
            passed += 1;
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::Ok,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: Some(actual),
            });
        } else {
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::HashMismatch,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: Some(actual),
            });
        }
    }

    let failed = verdicts.len() - passed;
    Ok(VerifyReport {
        manifest: manifest_path.to_string_lossy().into_owned(),
        source_dir: source_dir.to_string_lossy().into_owned(),
        format_version: manifest.format_version,
        files_checked: verdicts.len(),
        passed,
        failed,
        approved: failed == 0 && !verdicts.is_empty(),
        verdicts,
    })
}
