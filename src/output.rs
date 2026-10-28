//! Saídas temporárias removidas em falha, publicadas somente após validação.
use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
static NEXT: AtomicU64 = AtomicU64::new(0);

pub fn absent(path: &Path) -> Result<()> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => bail!("saída existente recusada: {}", path.display()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e).with_context(|| format!("verificar saída {}", path.display())),
    }
}

pub struct Stage {
    pub path: PathBuf,
    directory: bool,
}
impl Stage {
    pub fn new(target: &Path, directory: bool) -> Result<Self> {
        absent(target)?;
        Self::temporary(target, directory)
    }
    pub fn temporary(target: &Path, directory: bool) -> Result<Self> {
        let parent = target
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        std::fs::create_dir_all(parent)?;
        loop {
            let path = parent.join(format!(
                ".urnapack-stage-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let result = if directory {
                std::fs::create_dir(&path)
            } else {
                std::fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(&path)
                    .map(|_| ())
            };
            match result {
                Ok(()) => return Ok(Self { path, directory }),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e.into()),
            }
        }
    }
    pub fn publish(&self, target: &Path) -> Result<()> {
        absent(target)?;
        if self.directory {
            std::fs::rename(&self.path, target)?;
        } else {
            std::fs::hard_link(&self.path, target)?;
            std::fs::remove_file(&self.path)?;
        }
        Ok(())
    }
}
impl Drop for Stage {
    fn drop(&mut self) {
        if self.directory {
            let _ = std::fs::remove_dir_all(&self.path);
        } else {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

/// Resolve o destino mesmo antes de existir, sem criar diretórios.
pub fn resolved_target(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut resolved = PathBuf::new();
    for part in absolute.components() {
        match part {
            std::path::Component::ParentDir => {
                resolved.pop();
            }
            std::path::Component::CurDir => {}
            other => {
                resolved.push(other.as_os_str());
                match std::fs::symlink_metadata(&resolved) {
                    Ok(_) => resolved = std::fs::canonicalize(&resolved)?,
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                    Err(e) => return Err(e.into()),
                }
            }
        }
    }
    Ok(resolved)
}
