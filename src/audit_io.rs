//! I/O compartilhado entre os binários de auditoria: hash da leitura e saída atômica.
use anyhow::{ensure, Context, Result};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::Path;

pub(crate) struct HashingRead<R> {
    pub(crate) inner: R,
    pub(crate) hash: Sha256,
    pub(crate) bytes: u64,
}

impl<R: Read> Read for HashingRead<R> {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let count = self.inner.read(buffer)?;
        self.hash.update(&buffer[..count]);
        self.bytes += count as u64;
        Ok(count)
    }
}

pub(crate) fn publish_file(
    path: &Path,
    write: impl FnOnce(&mut std::fs::File) -> Result<()>,
) -> Result<()> {
    ensure!(!path.exists(), "saída existente; bytes preservados");
    let mut name = path
        .file_name()
        .context("saída sem nome de arquivo")?
        .to_os_string();
    name.push(format!(".partial-{}", std::process::id()));
    let partial = path.with_file_name(name);
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&partial)?;
    write(&mut file).with_context(|| format!("parcial preservado: {}", partial.display()))?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    std::fs::hard_link(&partial, path)?;
    std::fs::remove_file(partial)?;
    Ok(())
}
