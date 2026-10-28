//! Verificador de integridade dos arquivos de origem (Nível 1).
//!
//! Reexecuta o hashing dos arquivos de origem e compara com o
//! manifesto registrado: detecta ausentes, truncados/alterados e
//! divergências de versão. NÃO compartilha estado com o compressor:
//! lê o manifesto do disco e recalcula tudo a partir dos arquivos.
//!
//! Limite documentado: exige fonte imutável durante a verificação;
//! não promete proteção contra substituição concorrente de arquivos.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::manifest::Manifest;
use crate::traverse::{resolve_root, validate_manifest_rel};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum VerifyStatus {
    Ok,
    Missing,
    SizeMismatch,
    HashMismatch,
    /// Caminho declarado inválido (vazio, absoluto, `..`, não canônico,
    /// duplicado) ou componente que escapa da raiz / symlink interno.
    InvalidPath,
    /// Versão do manifesto não suportada. Também reportado como erro
    /// antes da comparação quando o carregamento falha por versão.
    UnsupportedVersion,
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

/// Junta o relativo validado à raiz canônica, rejeitando escapes por
/// componentes symlink internos. Retorna o absoluto correspondente.
fn join_checked(root: &Path, rel: &str) -> Result<PathBuf> {
    validate_manifest_rel(rel)?;
    let mut abs = root.to_path_buf();
    let parts: Vec<_> = rel.split('/').collect();
    for (index, part) in parts.iter().enumerate() {
        abs.push(part);
        let meta = match std::fs::symlink_metadata(&abs) {
            Ok(meta) => meta,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(root.join(rel)),
            Err(e) => return Err(e).with_context(|| format!("metadata {}", abs.display())),
        };
        if meta.file_type().is_symlink() {
            bail!("symlink interno em componente: {rel}");
        }
        if index + 1 < parts.len() && !meta.is_dir() {
            bail!("componente não diretório em: {rel}");
        }
    }
    Ok(abs)
}

pub fn verify(manifest_path: &Path, source_dir: &Path) -> Result<VerifyReport> {
    // Carrega o manifesto com guarda de versão explícita. Divergência de
    // versão reprova com erro (exit não zero na CLI), não com aprovação.
    let manifest = Manifest::load(manifest_path)?;

    let root = resolve_root(source_dir)?;

    // Duplicata de caminho de manifesto: reprova explicitamente.
    // (Duplicata eleitoral legítima é outro conceito e não entra aqui.)
    let mut seen: HashSet<&str> = HashSet::new();
    let mut duplicate_paths: HashSet<&str> = HashSet::new();
    for e in &manifest.files {
        if !seen.insert(e.path.as_str()) {
            duplicate_paths.insert(e.path.as_str());
        }
    }

    let mut verdicts = Vec::with_capacity(manifest.files.len());
    let mut passed = 0usize;

    for entry in &manifest.files {
        if duplicate_paths.contains(entry.path.as_str()) {
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::InvalidPath,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: None,
            });
            continue;
        }
        // Validação de forma do caminho declarado.
        if validate_manifest_rel(&entry.path).is_err() {
            verdicts.push(FileVerdict {
                path: entry.path.clone(),
                status: VerifyStatus::InvalidPath,
                expected_sha256: entry.sha256.clone(),
                actual_sha256: None,
            });
            continue;
        }
        let abs = match join_checked(&root, &entry.path) {
            Ok(p) => p,
            Err(_) => {
                verdicts.push(FileVerdict {
                    path: entry.path.clone(),
                    status: VerifyStatus::InvalidPath,
                    expected_sha256: entry.sha256.clone(),
                    actual_sha256: None,
                });
                continue;
            }
        };
        // Symlink no próprio arquivo: rejeita sem ignorar.
        match std::fs::symlink_metadata(&abs) {
            Ok(meta) if meta.file_type().is_symlink() => {
                verdicts.push(FileVerdict {
                    path: entry.path.clone(),
                    status: VerifyStatus::InvalidPath,
                    expected_sha256: entry.sha256.clone(),
                    actual_sha256: None,
                });
                continue;
            }
            Ok(meta) if !meta.file_type().is_file() => {
                verdicts.push(FileVerdict {
                    path: entry.path.clone(),
                    status: VerifyStatus::InvalidPath,
                    expected_sha256: entry.sha256.clone(),
                    actual_sha256: None,
                });
                continue;
            }
            Err(_) => {
                verdicts.push(FileVerdict {
                    path: entry.path.clone(),
                    status: VerifyStatus::Missing,
                    expected_sha256: entry.sha256.clone(),
                    actual_sha256: None,
                });
                continue;
            }
            _ => {}
        }
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
