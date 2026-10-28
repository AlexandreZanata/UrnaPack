//! Consultas de controle da Etapa 4: votos e contexto presidencial sem duplicá-lo.
use anyhow::{bail, Context, Result};
use serde::Serialize;
use sha2::Digest;
use std::collections::BTreeMap;
use std::io::Write;
use std::path::Path;

#[derive(Debug, Serialize)]
pub struct Votes {
    pub key: Vec<String>,
    pub votes: String,
}
#[derive(Debug, Serialize)]
pub struct Zone {
    pub key: Vec<String>,
    pub sections: u64,
    pub aptos: String,
    pub comparecimento: String,
    pub abstencoes: String,
}
#[derive(Debug, Serialize)]
pub struct QueryReport {
    pub artifact_kind: String,
    pub format_version: u32,
    pub source_member_sha256: String,
    pub records: u64,
    pub q1: Vec<Votes>,
    pub q2_presidente: Vec<Zone>,
    pub localized_key: Vec<String>,
    pub localized_rows: u64,
    pub localized_sha256: String,
}
struct State {
    rows: u64,
    votes: BTreeMap<Vec<String>, u128>,
    contexts: BTreeMap<Vec<String>, [u64; 3]>,
    localized_key: Option<Vec<String>>,
    localized: crate::bweb::HashWriter,
    localized_rows: u64,
    max_rows: u64,
    max_keys: u64,
}
fn text(bytes: &[u8]) -> Result<String> {
    Ok(std::str::from_utf8(bytes)?.to_owned())
}
fn key(r: &csv::ByteRecord, cols: &[usize]) -> Result<Vec<String>> {
    cols.iter().map(|i| text(&r[*i])).collect()
}
impl State {
    fn new() -> Result<Self> {
        Ok(Self {
            rows: 0,
            votes: BTreeMap::new(),
            contexts: BTreeMap::new(),
            localized_key: None,
            localized: crate::bweb::HashWriter::new(),
            localized_rows: 0,
            max_rows: crate::limits::get("MAX_CSV_RECORDS")?,
            max_keys: crate::limits::get("MAX_BWEB_OCCURRENCE_KEYS")?,
        })
    }
    fn accept(&mut self, r: &csv::ByteRecord) -> Result<()> {
        if r.len() != crate::bweb::BWEB_HEADER.len() {
            bail!("campos divergentes");
        }
        self.rows += 1;
        if self.rows > self.max_rows {
            bail!("limite de registros excedido");
        }
        // CARGO=16, UF=10, município=11, votos=31 no layout versionado.
        let vote: u64 = std::str::from_utf8(&r[31])?
            .parse()
            .context("QT_VOTOS inválido")?;
        let total = self.votes.entry(key(r, &[16, 10, 11])?).or_default();
        *total = total
            .checked_add(u128::from(vote))
            .context("overflow de votos")?;
        if self.votes.len() as u64 > self.max_keys {
            bail!("limite de grupos excedido");
        }
        if &r[16] == b"1" {
            let k = key(r, &[5, 7, 10, 11, 13, 14])?;
            let mut context = [0u64; 3];
            for (out, i) in context.iter_mut().zip([22, 23, 24]) {
                *out = std::str::from_utf8(&r[i])?
                    .parse()
                    .context("contexto numérico inválido")?;
            }
            if context[1].checked_add(context[2]) != Some(context[0]) {
                bail!("aritmética de contexto divergente");
            }
            if let Some(old) = self.contexts.insert(k, context) {
                if old != context {
                    bail!("contexto diverge dentro da seção presidencial");
                }
            }
            if self.contexts.len() as u64 > self.max_keys {
                bail!("limite de contextos excedido");
            }
        }
        let k = key(r, &[5, 7, 10, 11, 13, 14, 16])?;
        let wanted = self.localized_key.get_or_insert_with(|| k.clone());
        if &k == wanted {
            for (i, value) in r.iter().enumerate() {
                if i != 0 {
                    self.localized.write_all(b";")?;
                }
                crate::bweb::emit_field(&mut self.localized, value, crate::bweb::BWEB_QUOTED[i])?;
            }
            self.localized.write_all(b"\r\n")?;
            self.localized_rows += 1;
        }
        Ok(())
    }
    fn finish(self, sha: String) -> Result<QueryReport> {
        let mut zones: BTreeMap<Vec<String>, (u64, [u128; 3])> = BTreeMap::new();
        for (k, context) in self.contexts {
            let entry = zones.entry(k[2..5].to_vec()).or_default();
            entry.0 += 1;
            for (target, v) in entry.1.iter_mut().zip(context) {
                *target = target
                    .checked_add(u128::from(v))
                    .context("overflow de contexto")?;
            }
        }
        Ok(QueryReport {
            artifact_kind: "bweb_control_queries".into(),
            format_version: 1,
            source_member_sha256: sha,
            records: self.rows,
            q1: self
                .votes
                .into_iter()
                .map(|(key, total)| Votes {
                    key,
                    votes: total.to_string(),
                })
                .collect(),
            q2_presidente: zones
                .into_iter()
                .map(|(key, (sections, c))| Zone {
                    key,
                    sections,
                    aptos: c[0].to_string(),
                    comparecimento: c[1].to_string(),
                    abstencoes: c[2].to_string(),
                })
                .collect(),
            localized_key: self.localized_key.unwrap_or_default(),
            localized_rows: self.localized_rows,
            localized_sha256: hex::encode(self.localized.hash.finalize()),
        })
    }
}
pub fn run(path: &Path) -> Result<QueryReport> {
    let mut state = State::new()?;
    let sha = if path.is_dir() {
        let m = crate::bweb::load_verified(path)?;
        crate::bweb::verify_restoration(path, &m)?;
        crate::bweb::visit_rows(path, &m, |r| state.accept(r))?;
        m.source_member_sha256.context("origem ausente")?
    } else {
        if std::fs::metadata(path)?.len() > crate::limits::get("MAX_SOURCE_FILE_BYTES")? {
            bail!("origem excessiva");
        }
        let raw = crate::bweb::BoundedCsv {
            inner: std::fs::File::open(path)?,
            quoted: false,
            bytes: 0,
            maximum: crate::limits::get("MAX_RECORD_BYTES")?,
        };
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(false)
            .flexible(false)
            .delimiter(b';')
            .from_reader(raw);
        let mut row = csv::ByteRecord::new();
        if !reader.read_byte_record(&mut row)?
            || row
                .iter()
                .ne(crate::bweb::BWEB_HEADER.iter().map(|s| s.as_bytes()))
        {
            bail!("layout BU web incompatível");
        }
        while reader.read_byte_record(&mut row)? {
            state.accept(&row)?;
        }
        crate::hash::sha256_file(path)?
    };
    state.finish(sha)
}
