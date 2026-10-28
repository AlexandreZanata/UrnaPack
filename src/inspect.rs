//! Inspeção de um diretório de dados: contagem e tamanhos por tipo.
//!
//! Não interpreta o conteúdo (Fase 1 fará isso por formato).
//! Apenas responde: quantos arquivos, de que tipos, de que tamanhos.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;
use walkdir::WalkDir;

/// Estatística agregada por extensão.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeStat {
    pub extension: String,
    pub count: u64,
    pub bytes: u64,
}

/// Relatório de inspeção.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InspectReport {
    pub root: String,
    pub file_count: u64,
    pub total_bytes: u64,
    pub by_type: Vec<TypeStat>,
}

pub fn scan(root: &Path) -> Result<InspectReport> {
    let mut agg: BTreeMap<String, (u64, u64)> = BTreeMap::new();
    let mut file_count = 0u64;
    let mut total_bytes = 0u64;

    for entry in WalkDir::new(root)
        .min_depth(1)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if !entry.file_type().is_file() {
            continue;
        }
        let size = entry.metadata().map(|m| m.len()).unwrap_or(0);
        let ext = entry
            .path()
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_lowercase()))
            .unwrap_or_else(|| "(sem-extensao)".to_string());
        let slot = agg.entry(ext).or_insert((0, 0));
        slot.0 += 1;
        slot.1 += size;
        file_count += 1;
        total_bytes += size;
    }

    let by_type = agg
        .into_iter()
        .map(|(extension, (count, bytes))| TypeStat {
            extension,
            count,
            bytes,
        })
        .collect();

    Ok(InspectReport {
        root: root.to_string_lossy().into_owned(),
        file_count,
        total_bytes,
        by_type,
    })
}
