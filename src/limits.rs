//! Limites compartilhados, definidos somente em scripts/limits.env.
use anyhow::{bail, Context, Result};

pub fn get(name: &str) -> Result<u64> {
    for line in include_str!("../scripts/limits.env").lines() {
        if let Some((key, value)) = line.split_once('=') {
            if key.trim() == name {
                let number: u64 = value
                    .trim()
                    .parse()
                    .with_context(|| format!("limite inválido: {name}"))?;
                if number == 0 {
                    bail!("limite deve ser positivo: {name}");
                }
                return Ok(number);
            }
        }
    }
    bail!("limite ausente: {name}")
}
