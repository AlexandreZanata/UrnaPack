//! Pacote BU web com restauração exata, limites e publicação após validação.
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::{Path, PathBuf};

/// Cabeçalho canônico bweb em ordem (45 colunas).
pub const BWEB_HEADER: [&str; 45] = [
    "DT_GERACAO",
    "HH_GERACAO",
    "ANO_ELEICAO",
    "CD_TIPO_ELEICAO",
    "NM_TIPO_ELEICAO",
    "CD_PLEITO",
    "DT_PLEITO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "NR_LOCAL_VOTACAO",
    "CD_CARGO_PERGUNTA",
    "DS_CARGO_PERGUNTA",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "DT_BU_RECEBIDO",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCOES",
    "CD_TIPO_URNA",
    "DS_TIPO_URNA",
    "CD_TIPO_VOTAVEL",
    "DS_TIPO_VOTAVEL",
    "NR_VOTAVEL",
    "NM_VOTAVEL",
    "QT_VOTOS",
    "NR_URNA_EFETIVADA",
    "CD_CARGA_1_URNA_EFETIVADA",
    "CD_CARGA_2_URNA_EFETIVADA",
    "CD_FLASHCARD_URNA_EFETIVADA",
    "DT_CARGA_URNA_EFETIVADA",
    "DS_CARGO_PERGUNTA_SECAO",
    "DS_SECOES_AGREGADAS",
    "DT_ABERTURA",
    "DT_ENCERRAMENTO",
    "QT_ELEI_BIOM_SEM_HABILITACAO",
    "DT_EMISSAO_BU",
    "NR_JUNTA_APURADORA",
    "NR_TURMA_APURADORA",
];

/// Colunas sempre com aspas na emissão (26); demais (19) nunca (`spec/bweb-pack-v1.md`).
pub const BWEB_QUOTED: [bool; 45] = [
    true, true, false, false, true, false, true, false, false, true, true, false, true, false,
    false, false, false, true, false, true, true, true, false, false, false, false, true, false,
    true, false, true, false, false, true, true, true, true, true, true, true, true, true, true,
    true, true,
];

pub const PACK_FORMAT_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ColumnMeta {
    pub file: String,
    pub rows: u64,
    pub bytes: u64,
    pub sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PackManifest {
    pub artifact_kind: String,
    pub format_version: u32,
    pub family: String,
    pub header: Vec<String>,
    pub quoted: Vec<bool>,
    pub rows: u64,
    pub encoding: String,
    pub lineterminator: String,
    pub quoting_rule: String,
    pub source_member_sha256: Option<String>,
    pub columns: Vec<ColumnMeta>,
}

fn digest_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn column_path(out: &Path, i: usize) -> PathBuf {
    out.join(format!("columns/{i:02}.bin"))
}
fn has_bare_special(v: &[u8]) -> bool {
    v.iter().any(|b| matches!(b, b';' | b'"' | b'\r' | b'\n'))
}

pub(crate) struct HashWriter {
    pub hash: Sha256,
    pub bytes: u64,
}
impl HashWriter {
    pub fn new() -> Self {
        Self {
            hash: Sha256::new(),
            bytes: 0,
        }
    }
}
impl Write for HashWriter {
    fn write(&mut self, data: &[u8]) -> std::io::Result<usize> {
        self.hash.update(data);
        self.bytes += data.len() as u64;
        Ok(data.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

pub(crate) fn emit_field<W: Write>(out: &mut W, value: &[u8], quoted: bool) -> Result<()> {
    if !quoted {
        if has_bare_special(value) {
            bail!("especial em coluna B");
        }
        out.write_all(value)?;
    } else {
        out.write_all(b"\"")?;
        for (i, part) in value.split(|b| *b == b'"').enumerate() {
            if i != 0 {
                out.write_all(b"\"\"")?;
            }
            out.write_all(part)?;
        }
        out.write_all(b"\"")?;
    }
    Ok(())
}
fn emit_header<W: Write>(out: &mut W) -> Result<()> {
    for (i, name) in BWEB_HEADER.iter().enumerate() {
        if i != 0 {
            out.write_all(b";")?;
        }
        emit_field(out, name.as_bytes(), true)?;
    }
    out.write_all(b"\r\n")?;
    Ok(())
}

/// Impede que o parser aloque um registro sem limite. O emissor exige CRLF;
/// aspas duplicadas alternam o estado duas vezes e conservam quebras internas.
pub(crate) struct BoundedCsv<R> {
    pub(crate) inner: R,
    pub(crate) quoted: bool,
    pub(crate) bytes: u64,
    pub(crate) maximum: u64,
}
impl<R: Read> Read for BoundedCsv<R> {
    fn read(&mut self, data: &mut [u8]) -> std::io::Result<usize> {
        let n = self.inner.read(data)?;
        for byte in &data[..n] {
            self.bytes += 1;
            if self.bytes > self.maximum {
                return Err(std::io::Error::other("MAX_RECORD_BYTES excedido"));
            }
            if *byte == b'"' {
                self.quoted = !self.quoted;
            }
            if *byte == b'\n' && !self.quoted {
                self.bytes = 0;
            }
        }
        Ok(n)
    }
}

pub fn pack(csv_path: &Path, out_dir: &Path, expected: Option<String>) -> Result<PackManifest> {
    crate::output::absent(out_dir)?;
    let size = std::fs::metadata(csv_path)?.len();
    if !std::fs::metadata(csv_path)?.is_file()
        || size > crate::limits::get("MAX_SOURCE_FILE_BYTES")?
    {
        bail!("origem inválida ou MAX_SOURCE_FILE_BYTES excedido");
    }
    let source_sha = crate::hash::sha256_file(csv_path)?;
    if let Some(value) = expected {
        if value.to_ascii_lowercase() != source_sha {
            bail!("SHA-256 esperado da origem diverge");
        }
    }
    let stage = crate::output::Stage::new(out_dir, true)?;
    std::fs::create_dir(stage.path.join("columns"))?;
    let capacity = crate::limits::get("IO_BUFFER_BYTES")? as usize;
    let raw = BoundedCsv {
        inner: std::fs::File::open(csv_path)?,
        quoted: false,
        bytes: 0,
        maximum: crate::limits::get("MAX_RECORD_BYTES")?,
    };
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(false)
        .delimiter(b';')
        .from_reader(raw);
    let mut record = csv::ByteRecord::new();
    if !reader.read_byte_record(&mut record)?
        || record.iter().ne(BWEB_HEADER.iter().map(|s| s.as_bytes()))
    {
        bail!("cabeçalho diverge do layout bweb");
    }
    let mut writers = Vec::new();
    for i in 0..BWEB_HEADER.len() {
        writers.push(BufWriter::with_capacity(
            capacity,
            std::fs::File::create(column_path(&stage.path, i))?,
        ));
    }
    let mut canonical = HashWriter::new();
    emit_header(&mut canonical)?;
    let max_field = crate::limits::get("MAX_FIELD_BYTES")?;
    let max_rows = crate::limits::get("MAX_CSV_RECORDS")?;
    let mut rows = 0;
    while reader
        .read_byte_record(&mut record)
        .with_context(|| format!("ler registro {}", rows + 1))?
    {
        rows += 1;
        if rows > max_rows {
            bail!("MAX_CSV_RECORDS excedido");
        }
        if record.len() != BWEB_HEADER.len() {
            bail!("contagem de campos diverge no registro {rows}");
        }
        for (i, value) in record.iter().enumerate() {
            if value.len() as u64 > max_field {
                bail!("MAX_FIELD_BYTES excedido no registro {rows}");
            }
            let length = u32::try_from(value.len())?;
            writers[i].write_all(&length.to_le_bytes())?;
            writers[i].write_all(value)?;
            if i != 0 {
                canonical.write_all(b";")?;
            }
            emit_field(&mut canonical, value, BWEB_QUOTED[i])?;
        }
        canonical.write_all(b"\r\n")?;
    }
    if canonical.bytes != size || hex::encode(canonical.hash.finalize()) != source_sha {
        bail!("emissão não recupera os bytes originais: quoting/CRLF/cabeçalho não canônicos");
    }
    for writer in &mut writers {
        writer.flush()?;
    }
    drop(writers);
    let mut columns = Vec::new();
    for i in 0..BWEB_HEADER.len() {
        let path = column_path(&stage.path, i);
        columns.push(ColumnMeta {
            file: format!("columns/{i:02}.bin"),
            rows,
            bytes: std::fs::metadata(&path)?.len(),
            sha256: crate::hash::sha256_file(&path)?,
        });
    }
    let manifest = PackManifest {
        artifact_kind: "bweb_columnar_pack".into(),
        format_version: PACK_FORMAT_VERSION,
        family: "bweb".into(),
        header: BWEB_HEADER.iter().map(|s| s.to_string()).collect(),
        quoted: BWEB_QUOTED.to_vec(),
        rows,
        encoding: "latin-1".into(),
        lineterminator: "\r\n".into(),
        quoting_rule: "tse-text-columns-v1".into(),
        source_member_sha256: Some(source_sha),
        columns,
    };
    std::fs::write(
        stage.path.join("pack.json"),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    stage.publish(out_dir)?;
    Ok(manifest)
}

/// Valida contrato, inventário e hashes antes de restaurar ou medir.
pub fn load_verified(pack_dir: &Path) -> Result<PackManifest> {
    let root = crate::traverse::resolve_root(pack_dir)?;
    let manifest_path = root.join("pack.json");
    if std::fs::metadata(&manifest_path)?.len() > crate::limits::get("MAX_PACK_MANIFEST_BYTES")? {
        bail!("MAX_PACK_MANIFEST_BYTES excedido");
    }
    let manifest: PackManifest = serde_json::from_slice(&std::fs::read(&manifest_path)?)?;
    if manifest.artifact_kind != "bweb_columnar_pack"
        || ![1, PACK_FORMAT_VERSION].contains(&manifest.format_version)
        || manifest.family != "bweb"
        || manifest.encoding != "latin-1"
        || manifest.lineterminator != "\r\n"
        || manifest.quoting_rule != "tse-text-columns-v1"
        || manifest.header != BWEB_HEADER
        || manifest.quoted != BWEB_QUOTED
        || manifest.columns.len() != BWEB_HEADER.len()
    {
        bail!("pacote incompatível ou layout divergente");
    }
    if !manifest
        .source_member_sha256
        .as_deref()
        .is_some_and(digest_valid)
    {
        bail!("SHA-256 da origem obrigatório; pacote legado sem compromisso não é FORENSIC");
    }
    if manifest.rows > crate::limits::get("MAX_CSV_RECORDS")? {
        bail!("MAX_CSV_RECORDS excedido");
    }
    let mut expected = std::collections::HashSet::from(["pack.json".to_string()]);
    for (i, column) in manifest.columns.iter().enumerate() {
        let name = format!("columns/{i:02}.bin");
        if column.file != name || column.rows != manifest.rows || !digest_valid(&column.sha256) {
            bail!("metadados da coluna {i} inválidos");
        }
        expected.insert(name);
    }
    for file in crate::traverse::collect_files(&root)? {
        let name = crate::traverse::rel_to_canonical(&root, &file)?;
        if !expected.remove(&name) {
            bail!("arquivo desconhecido no pacote: {name}");
        }
    }
    if !expected.is_empty() {
        bail!("pacote incompleto: {expected:?}");
    }
    let mut total_bytes = 0u64;
    for column in &manifest.columns {
        total_bytes = total_bytes
            .checked_add(column.bytes)
            .context("overflow de tamanho do pacote")?;
        if total_bytes > crate::limits::get("MAX_PACK_BYTES")? {
            bail!("MAX_PACK_BYTES excedido");
        }
        let path = root.join(&column.file);
        if column.bytes != std::fs::metadata(&path)?.len()
            || column.bytes > crate::limits::get("MAX_SOURCE_FILE_BYTES")?
            || crate::hash::sha256_file(&path)? != column.sha256
        {
            bail!("tamanho ou SHA-256 diverge na coluna {}", column.file);
        }
    }
    Ok(manifest)
}

pub(crate) fn render<W: Write>(root: &Path, manifest: &PackManifest, out: &mut W) -> Result<()> {
    emit_header(out)?;
    visit_rows(root, manifest, |record| {
        for (i, value) in record.iter().enumerate() {
            if i != 0 {
                out.write_all(b";")?;
            }
            emit_field(out, value, BWEB_QUOTED[i])?;
        }
        out.write_all(b"\r\n")?;
        Ok(())
    })
}

pub(crate) fn visit_rows(
    root: &Path,
    manifest: &PackManifest,
    mut visitor: impl FnMut(&csv::ByteRecord) -> Result<()>,
) -> Result<()> {
    let capacity = crate::limits::get("IO_BUFFER_BYTES")? as usize;
    let mut readers = Vec::new();
    for column in &manifest.columns {
        readers.push(BufReader::with_capacity(
            capacity,
            std::fs::File::open(root.join(&column.file))?,
        ));
    }
    let max_field = crate::limits::get("MAX_FIELD_BYTES")?;
    let max_record = crate::limits::get("MAX_RECORD_BYTES")?;
    let mut record = csv::ByteRecord::new();
    for row in 0..manifest.rows {
        record.clear();
        let mut row_bytes = 0u64;
        for (i, reader) in readers.iter_mut().enumerate() {
            let mut prefix = [0u8; 4];
            reader
                .read_exact(&mut prefix)
                .with_context(|| format!("coluna {i} truncada na linha {row}"))?;
            let length = u32::from_le_bytes(prefix) as u64;
            row_bytes += length;
            if length > max_field || row_bytes > max_record {
                bail!("comprimento de campo/registro excede limite na coluna {i}");
            }
            let mut value = vec![0; length as usize];
            reader
                .read_exact(&mut value)
                .with_context(|| format!("valor truncado na coluna {i}"))?;
            record.push_field(&value);
        }
        visitor(&record)?;
    }
    for (i, reader) in readers.iter_mut().enumerate() {
        if reader.read(&mut [0])? != 0 {
            bail!("bytes residuais na coluna {i}");
        }
    }
    Ok(())
}

pub fn verify_restoration(pack_dir: &Path, manifest: &PackManifest) -> Result<u64> {
    let mut hash = HashWriter::new();
    render(pack_dir, manifest, &mut hash)?;
    if Some(hex::encode(hash.hash.finalize())) != manifest.source_member_sha256 {
        bail!("SHA-256 restaurado diverge da origem");
    }
    Ok(hash.bytes)
}

pub fn unpack(pack_dir: &Path, csv_path: &Path) -> Result<PackManifest> {
    crate::output::absent(csv_path)?;
    let manifest = load_verified(pack_dir)?;
    let root = std::fs::canonicalize(pack_dir)?;
    if crate::output::resolved_target(csv_path)?.starts_with(&root) {
        bail!("saída dentro do pacote recusada");
    }
    let stage = crate::output::Stage::new(csv_path, false)?;
    let mut out = BufWriter::with_capacity(
        crate::limits::get("IO_BUFFER_BYTES")? as usize,
        std::fs::File::create(&stage.path)?,
    );
    render(pack_dir, &manifest, &mut out)?;
    out.flush()?;
    drop(out);
    if Some(crate::hash::sha256_file(&stage.path)?) != manifest.source_member_sha256 {
        bail!("SHA-256 do restaurado diverge da origem");
    }
    stage.publish(csv_path)?;
    Ok(manifest)
}
pub fn sha256_of(path: &Path) -> Result<String> {
    crate::hash::sha256_file(path)
}
