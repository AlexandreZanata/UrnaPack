//! Política compartilhada de travessia para inventário e manifesto.
//!
//! Regras da Etapa 1 (sem framework): raiz inexistente ou que não é diretório
//! reprova; um link legítimo na raiz é resolvido; symlinks internos, arquivos
//! especiais e nomes não representáveis sem perda reprovam; erros de
//! travessia/metadata/leitura propagam (nunca omitidos).

use anyhow::{bail, Context, Result};
use std::path::{Component, Path, PathBuf};
use walkdir::WalkDir;

/// Resolve a raiz informada, permitindo um link legítimo na raiz.
///
/// Falha se a raiz não existir ou se, após resolução, não for diretório.
/// Exige fonte imutável durante a verificação (documentado); não promete
/// proteção contra substituição concorrente de arquivos.
pub fn resolve_root(root: &Path) -> Result<PathBuf> {
    if std::fs::symlink_metadata(root).is_err() {
        bail!("raiz inexistente: {}", root.display());
    }
    let canon =
        std::fs::canonicalize(root).with_context(|| format!("resolver raiz {}", root.display()))?;
    if !canon.is_dir() {
        bail!("raiz não é diretório: {}", root.display());
    }
    Ok(canon)
}

/// Converte caminho absoluto em relativo canônico com `/` como separador.
///
/// Reprova nomes não representáveis sem perda (não UTF-8) e componentes
/// não canônicos. Não usa conversão com perda.
pub fn rel_to_canonical(root: &Path, abs: &Path) -> Result<String> {
    let rel = abs.strip_prefix(root).with_context(|| {
        format!(
            "caminho fora da raiz: {} (raiz {})",
            abs.display(),
            root.display()
        )
    })?;
    if rel.as_os_str().is_empty() {
        bail!("caminho vazio após raiz: {}", abs.display());
    }
    let mut parts: Vec<String> = Vec::new();
    for comp in rel.components() {
        match comp {
            Component::Normal(os) => {
                let s = os.to_str().ok_or_else(|| {
                    anyhow::anyhow!(
                        "nome não representável sem perda (não UTF-8): {}",
                        abs.display()
                    )
                })?;
                if s.is_empty() {
                    bail!("componente vazio em: {}", abs.display());
                }
                parts.push(s.to_owned());
            }
            Component::ParentDir => {
                bail!("travessia com `..` rejeitada: {}", abs.display())
            }
            Component::CurDir => {
                bail!("representação não canônica com `.`: {}", abs.display())
            }
            Component::RootDir | Component::Prefix(_) => {
                bail!("caminho absoluto rejeitado: {}", abs.display())
            }
        }
    }
    if parts.is_empty() {
        bail!("caminho vazio: {}", abs.display());
    }
    let relative = parts.join("/");
    validate_manifest_rel(&relative)?;
    Ok(relative)
}

/// Varre a raiz canônica e retorna arquivos regulares ordenados.
///
/// Rejeita symlinks internos e arquivos especiais sem ignorá-los.
/// Propaga erros de travessia/metadata. Diretórios são percorridos;
/// a raiz vazia retorna lista vazia explícita.
pub fn collect_files(canonical_root: &Path) -> Result<Vec<PathBuf>> {
    let mut out: Vec<PathBuf> = Vec::new();
    let walker = WalkDir::new(canonical_root)
        .min_depth(1)
        .follow_links(false);
    for entry in walker.into_iter() {
        let entry =
            entry.with_context(|| format!("erro de travessia em {}", canonical_root.display()))?;
        let path = entry.path().to_path_buf();
        // Diretórios vazios também não podem esconder nomes não representáveis.
        rel_to_canonical(canonical_root, &path)?;
        let ftype = entry.file_type();
        if ftype.is_symlink() {
            bail!("symlink interno rejeitado: {}", path.display());
        }
        if ftype.is_dir() {
            continue;
        }
        if !ftype.is_file() {
            bail!("arquivo especial rejeitado: {}", path.display());
        }
        // Confirma leitura de metadata (propaga erro, sem substituir por zero).
        let _ = std::fs::metadata(&path).with_context(|| format!("metadata {}", path.display()))?;
        out.push(path);
    }
    out.sort();
    Ok(out)
}

/// Valida um caminho declarado em manifesto (forma canônica relativa).
///
/// Rejeita vazio, absoluto, `..`, `.` ou segmentos vazios (`//`, barras
/// inicial/final). Retorna o relativo validado.
pub fn validate_manifest_rel(rel: &str) -> Result<()> {
    if rel.is_empty() {
        bail!("caminho vazio em manifesto");
    }
    if rel.starts_with('/') {
        bail!("caminho absoluto rejeitado em manifesto: {rel}");
    }
    if rel.contains('\\') {
        bail!("separador inválido em manifesto: {rel}");
    }
    let bytes = rel.as_bytes();
    if rel.contains('\0')
        || (bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':')
    {
        bail!("caminho não portátil ou com NUL em manifesto: {rel:?}");
    }
    for seg in rel.split('/') {
        if seg.is_empty() {
            bail!("representação não canônica (segmento vazio) em manifesto: {rel}");
        }
        if seg == "." || seg == ".." {
            bail!("travessia rejeitada em manifesto: {rel}");
        }
    }
    Ok(())
}
