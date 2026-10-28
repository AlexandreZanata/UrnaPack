//! Inspeção de um diretório de dados: contagem e tamanhos por tipo.
//!
//! Não interpreta o conteúdo; o mapeador estrutural ZIP/CSV é uma automação separada.
//! Apenas responde: quantos arquivos, de que tipos, de que tamanhos.
//! Erros de raiz/travessia/metadata/leitura reprovam explicitamente.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;

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
    let canonical = crate::traverse::resolve_root(root)?;
    let files = crate::traverse::collect_files(&canonical)?;

    let mut agg: BTreeMap<String, (u64, u64)> = BTreeMap::new();
    let mut file_count = 0u64;
    let mut total_bytes = 0u64;

    for abs in &files {
        // Tamanho medido; erro de leitura propaga (sem substituir por zero).
        let size = std::fs::metadata(abs)
            .with_context(|| format!("metadata {}", abs.display()))?
            .len();
        // Extensão sem conversão com perda: caminho já validado como UTF-8.
        let rel = crate::traverse::rel_to_canonical(&canonical, abs)?;
        let file_name = rel.rsplit('/').next().unwrap_or(&rel);
        let ext = match file_name.rfind('.') {
            Some(i) if i + 1 < file_name.len() => {
                format!(".{}", file_name[i + 1..].to_lowercase())
            }
            _ => "(sem-extensao)".to_string(),
        };
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
