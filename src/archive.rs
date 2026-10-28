//! Arquivo v2 (sólido/por fonte); vincula payload, origem e recibo. Lê TAR legado v1.
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::Digest;
use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const ARCHIVE_VERSION: u32 = 2;
fn solid_layout() -> String {
    "solid-tar".into()
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Object {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Descriptor {
    pub artifact_kind: String,
    pub format_version: u32,
    pub guarantee: String,
    pub codec: String,
    #[serde(default = "solid_layout")]
    pub layout: String,
    pub payload: Option<Object>,
    #[serde(default)]
    pub entries: Vec<EncodedEntry>,
    pub source_manifest: Object,
    pub execution: Object,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EncodedEntry {
    pub source_path: String,
    pub codec: String,
    pub data: Object,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Selection {
    format_version: u32,
    source_manifest_sha256: String,
    files: Vec<SelectedFile>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SelectedFile {
    source_path: String,
    codec: String,
    encoded_path: std::path::PathBuf,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Reference {
    path: String,
    sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    artifact_kind: String,
    format_version: u32,
    tool: String,
    command: Vec<String>,
    inputs: Vec<Reference>,
    outputs: Vec<Reference>,
    started_at: String,
    finished_at: String,
    elapsed_ms: u128,
    success: bool,
    errors: Vec<String>,
}
fn object(root: &Path, name: &str) -> Result<Object> {
    let path = root.join(name);
    Ok(Object {
        file: name.into(),
        bytes: std::fs::metadata(&path)?.len(),
        sha256: crate::hash::sha256_file(&path)?,
    })
}
fn read_metadata(path: &Path) -> Result<Vec<u8>> {
    let m = std::fs::symlink_metadata(path)?;
    if !m.is_file() || m.len() > crate::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")? {
        bail!("metadados excessivos/não regulares");
    }
    Ok(std::fs::read(path)?)
}
fn origin(bytes: &[u8]) -> Result<crate::manifest::Manifest> {
    let m: crate::manifest::Manifest = serde_json::from_slice(bytes)?;
    if !crate::SUPPORTED_FORMAT_VERSIONS.contains(&m.format_version) || m.files.is_empty() {
        bail!("manifesto de origem incompatível/vazio");
    }
    let mut paths = std::collections::HashSet::new();
    let mut total = 0u64;
    for f in &m.files {
        crate::traverse::validate_manifest_rel(&f.path)?;
        if !paths.insert(&f.path)
            || f.sha256.len() != 64
            || !f
                .sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            bail!("origem duplicada ou hash inválido");
        }
        total = total.checked_add(f.size).context("overflow de origem")?;
        if f.size > crate::limits::get("MAX_SOURCE_FILE_BYTES")?
            || total > crate::limits::get("MAX_PACK_BYTES")?
        {
            bail!("limite de origem excedido");
        }
    }
    Ok(m)
}
fn append<W: Write, R: Read>(
    tar: &mut tar::Builder<W>,
    name: &str,
    size: u64,
    reader: R,
) -> Result<()> {
    let mut h = tar::Header::new_gnu();
    h.set_size(size);
    h.set_mode(0o644);
    h.set_uid(0);
    h.set_gid(0);
    h.set_mtime(0);
    h.set_cksum();
    tar.append_data(&mut h, name, reader)?;
    Ok(())
}
pub fn create_tar(root: &Path, manifest: &Path, output: &Path) -> Result<()> {
    let bytes = read_metadata(manifest)?;
    let m = origin(&bytes)?;
    let checked = crate::verify::verify(manifest, root)?;
    if !checked.approved {
        bail!("origem reprovada antes do TAR");
    }
    if crate::output_path_conflicts(root, output)? {
        bail!("TAR dentro da origem recusado");
    }
    let stage = crate::output::Stage::new(output, false)?;
    let mut builder = tar::Builder::new(std::fs::File::create(&stage.path)?);
    append(
        &mut builder,
        "source-manifest.json",
        bytes.len() as u64,
        bytes.as_slice(),
    )?;
    let mut files = m.files.iter().collect::<Vec<_>>();
    files.sort_by(|a, b| a.path.cmp(&b.path));
    for f in files {
        append(
            &mut builder,
            &format!("source/{}", f.path),
            f.size,
            std::fs::File::open(root.join(&f.path))?,
        )?;
    }
    builder.finish()?;
    drop(builder);
    verify_payload(&stage.path, "stored", &bytes, None)?;
    stage.publish(output)
}

fn verify_payload(
    payload: &Path,
    codec: &str,
    expected: &[u8],
    destination: Option<&Path>,
) -> Result<()> {
    let m = origin(expected)?;
    let mut wanted: BTreeMap<_, _> = m
        .files
        .iter()
        .map(|f| (format!("source/{}", f.path), f))
        .collect();
    let mut decoded =
        crate::codec::reader(payload, codec, None, crate::limits::get("MAX_PACK_BYTES")?)?;
    {
        let mut archive = tar::Archive::new(&mut decoded);
        let mut entries = archive.entries()?;
        let mut first = entries.next().context("TAR vazio")??;
        if first.path_bytes().as_ref() != b"source-manifest.json"
            || !first.header().entry_type().is_file()
            || first.size() != expected.len() as u64
        {
            bail!("origem ausente/incompatível no TAR");
        }
        let mut actual = Vec::new();
        first.read_to_end(&mut actual)?;
        if actual != expected {
            bail!("manifesto embutido diverge");
        }
        drop(first);
        for entry in entries {
            let mut entry = entry?;
            if !entry.header().entry_type().is_file() {
                bail!("entrada TAR não regular");
            }
            let name = std::str::from_utf8(&entry.path_bytes())?.to_string();
            let f = wanted
                .remove(&name)
                .with_context(|| format!("entrada TAR desconhecida/duplicada: {name}"))?;
            if entry.size() != f.size {
                bail!("tamanho de entrada TAR diverge");
            }
            let mut hash = crate::bweb::HashWriter::new();
            if let Some(destination) = destination {
                let target = destination.join(&f.path);
                std::fs::create_dir_all(target.parent().context("pai ausente")?)?;
                let mut output = std::fs::OpenOptions::new()
                    .create_new(true)
                    .write(true)
                    .open(&target)?;
                let n = std::io::copy(&mut entry, &mut output)?;
                output.flush()?;
                if n != f.size || crate::hash::sha256_file(&target)? != f.sha256 {
                    bail!("restauração diverge: {}", f.path);
                }
            } else {
                std::io::copy(&mut entry, &mut hash)?;
                if hash.bytes != f.size || hex::encode(hash.hash.finalize()) != f.sha256 {
                    bail!("conteúdo TAR diverge: {}", f.path);
                }
            }
        }
        if !wanted.is_empty() {
            bail!("TAR incompleto");
        }
    }
    let mut remaining = vec![0; crate::limits::get("IO_BUFFER_BYTES")? as usize];
    loop {
        let n = decoded.read(&mut remaining)?;
        if n == 0 {
            break;
        }
        if remaining[..n].iter().any(|b| *b != 0) {
            bail!("resíduo não nulo após TAR");
        }
    }
    decoded.finish()
}
fn stamp() -> Result<String> {
    Ok(format!(
        "unix-ns:{}",
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    ))
}
pub fn seal(payload: &Path, codec: &str, manifest: &Path, output: &Path) -> Result<Descriptor> {
    let started_at = stamp()?;
    let start = Instant::now();
    let source = read_metadata(manifest)?;
    origin(&source)?;
    let stage = crate::output::Stage::new(output, true)?;
    let name = "payload.tar.encoded";
    std::fs::copy(payload, stage.path.join(name))?;
    std::fs::write(stage.path.join("source-manifest.json"), &source)?;
    verify_payload(&stage.path.join(name), codec, &source, None)?;
    let data = object(&stage.path, name)?;
    let source_object = object(&stage.path, "source-manifest.json")?;
    let receipt = Receipt {
        artifact_kind: "urnapack_execution".into(),
        format_version: 1,
        tool: format!("tsepack {}", crate::TOOL_VERSION),
        command: std::env::args().collect(),
        inputs: vec![
            Reference {
                path: manifest.display().to_string(),
                sha256: source_object.sha256.clone(),
            },
            Reference {
                path: payload.display().to_string(),
                sha256: data.sha256.clone(),
            },
        ],
        outputs: vec![
            Reference {
                path: name.into(),
                sha256: data.sha256.clone(),
            },
            Reference {
                path: source_object.file.clone(),
                sha256: source_object.sha256.clone(),
            },
        ],
        started_at,
        finished_at: stamp()?,
        elapsed_ms: start.elapsed().as_millis(),
        success: true,
        errors: vec![],
    };
    std::fs::write(
        stage.path.join("execution.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )?;
    let result = Descriptor {
        artifact_kind: "urnapack_forensic_archive".into(),
        format_version: ARCHIVE_VERSION,
        guarantee: "relative-paths-and-file-bytes".into(),
        codec: codec.into(),
        layout: solid_layout(),
        payload: Some(data),
        entries: Vec::new(),
        source_manifest: source_object,
        execution: object(&stage.path, "execution.json")?,
    };
    std::fs::write(
        stage.path.join("dataset.json"),
        serde_json::to_vec_pretty(&result)?,
    )?;
    stage.publish(output)?;
    Ok(result)
}
pub fn seal_individual(selection: &Path, manifest: &Path, output: &Path) -> Result<Descriptor> {
    let started_at = stamp()?;
    let start = Instant::now();
    let source = read_metadata(manifest)?;
    let m = origin(&source)?;
    let selected: Selection = serde_json::from_slice(&read_metadata(selection)?)?;
    if selected.format_version != 1
        || selected.source_manifest_sha256 != crate::hash::sha256_bytes(&source)
        || selected.files.len() != m.files.len()
    {
        bail!("seleção incompatível com origem");
    }
    let mut choices = BTreeMap::new();
    for file in selected.files {
        if choices.insert(file.source_path.clone(), file).is_some() {
            bail!("seleção duplicada");
        }
    }
    let stage = crate::output::Stage::new(output, true)?;
    std::fs::create_dir(stage.path.join("data"))?;
    std::fs::write(stage.path.join("source-manifest.json"), &source)?;
    let source_object = object(&stage.path, "source-manifest.json")?;
    let mut inputs = vec![Reference {
        path: manifest.display().to_string(),
        sha256: source_object.sha256.clone(),
    }];
    let mut outputs = vec![Reference {
        path: source_object.file.clone(),
        sha256: source_object.sha256.clone(),
    }];
    let mut entries = Vec::new();
    for (index, f) in m.files.iter().enumerate() {
        let choice = choices
            .remove(&f.path)
            .context("fonte ausente na seleção")?;
        let name = format!("data/{index:05}.encoded");
        std::fs::copy(&choice.encoded_path, stage.path.join(&name))?;
        crate::codec::check(
            &stage.path.join(&name),
            &choice.codec,
            None,
            &f.sha256,
            f.size,
        )?;
        let data = object(&stage.path, &name)?;
        inputs.push(Reference {
            path: choice.encoded_path.display().to_string(),
            sha256: data.sha256.clone(),
        });
        outputs.push(Reference {
            path: name,
            sha256: data.sha256.clone(),
        });
        entries.push(EncodedEntry {
            source_path: f.path.clone(),
            codec: choice.codec,
            data,
        });
    }
    if !choices.is_empty() {
        bail!("seleção contém fontes desconhecidas");
    }
    let receipt = Receipt {
        artifact_kind: "urnapack_execution".into(),
        format_version: 1,
        tool: format!("tsepack {}", crate::TOOL_VERSION),
        command: std::env::args().collect(),
        inputs,
        outputs,
        started_at,
        finished_at: stamp()?,
        elapsed_ms: start.elapsed().as_millis(),
        success: true,
        errors: vec![],
    };
    std::fs::write(
        stage.path.join("execution.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )?;
    let d = Descriptor {
        artifact_kind: "urnapack_forensic_archive".into(),
        format_version: ARCHIVE_VERSION,
        guarantee: "relative-paths-and-file-bytes".into(),
        codec: "per-file".into(),
        layout: "per-file".into(),
        payload: None,
        entries,
        source_manifest: source_object,
        execution: object(&stage.path, "execution.json")?,
    };
    std::fs::write(
        stage.path.join("dataset.json"),
        serde_json::to_vec_pretty(&d)?,
    )?;
    stage.publish(output)?;
    Ok(d)
}
fn verified(root: &Path) -> Result<(Descriptor, Vec<u8>)> {
    let root = crate::traverse::resolve_root(root)?;
    if std::fs::metadata(root.join("dataset.json"))?.len()
        > crate::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?
    {
        bail!("descritor excessivo");
    }
    let raw = read_metadata(&root.join("dataset.json"))?;
    let value: serde_json::Value = serde_json::from_slice(&raw)?;
    if value.get("format_version") == Some(&serde_json::json!(ARCHIVE_VERSION))
        && (!value
            .as_object()
            .context("objeto esperado")?
            .contains_key("layout")
            || !value
                .as_object()
                .context("objeto esperado")?
                .contains_key("entries"))
    {
        bail!("layout v2 incompleto");
    }
    let d: Descriptor = serde_json::from_slice(&raw)?;
    if d.artifact_kind != "urnapack_forensic_archive"
        || ![1, ARCHIVE_VERSION].contains(&d.format_version)
        || d.guarantee != "relative-paths-and-file-bytes"
        || d.source_manifest.file != "source-manifest.json"
        || d.execution.file != "execution.json"
    {
        bail!("arquivo incompatível");
    }
    let bytes = read_metadata(&root.join(&d.source_manifest.file))?;
    let m = origin(&bytes)?;
    let mut objects = vec![&d.source_manifest];
    if d.layout == "solid-tar" {
        let p = d.payload.as_ref().context("payload ausente")?;
        if p.file != "payload.tar.encoded" || !d.entries.is_empty() {
            bail!("layout sólido divergente");
        }
        objects.push(p);
    } else if d.layout == "per-file" && d.format_version == ARCHIVE_VERSION {
        if d.payload.is_some() || d.codec != "per-file" || d.entries.len() != m.files.len() {
            bail!("layout por arquivo divergente");
        }
        for (i, (e, f)) in d.entries.iter().zip(&m.files).enumerate() {
            if e.source_path != f.path || e.data.file != format!("data/{i:05}.encoded") {
                bail!("ordem/caminho de arquivo divergente");
            }
            objects.push(&e.data);
        }
    } else {
        bail!("layout desconhecido");
    }
    let found = crate::traverse::collect_files(&root)?;
    let mut expected = std::collections::HashSet::from(["dataset.json", d.execution.file.as_str()]);
    for o in &objects {
        expected.insert(o.file.as_str());
    }
    if found.len() != expected.len() {
        bail!("inventário de arquivo divergente");
    }
    for p in found {
        if !expected.contains(crate::traverse::rel_to_canonical(&root, &p)?.as_str()) {
            bail!("arquivo desconhecido");
        }
    }
    for o in objects.iter().copied().chain(std::iter::once(&d.execution)) {
        let actual = object(&root, &o.file)?;
        if actual.bytes != o.bytes || actual.sha256 != o.sha256 {
            bail!("hash/tamanho diverge: {}", o.file);
        }
    }
    if d.source_manifest.bytes > crate::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?
        || d.execution.bytes > crate::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?
    {
        bail!("metadados excessivos");
    }
    let r: Receipt = serde_json::from_slice(&std::fs::read(root.join(&d.execution.file))?)?;
    if !r.success
        || !r.errors.is_empty()
        || r.artifact_kind != "urnapack_execution"
        || r.format_version != 1
        || r.outputs.len() != objects.len()
        || r.inputs.len() != objects.len()
        || r.command.is_empty()
    {
        bail!("recibo reprovado");
    }
    let mut expected_hashes = objects
        .iter()
        .map(|o| o.sha256.as_str())
        .collect::<Vec<_>>();
    expected_hashes.sort();
    let mut input_hashes = r
        .inputs
        .iter()
        .map(|i| i.sha256.as_str())
        .collect::<Vec<_>>();
    input_hashes.sort();
    if input_hashes != expected_hashes {
        bail!("entradas do recibo divergem");
    }
    for o in objects {
        let (f, h) = (&o.file, &o.sha256);
        if r.outputs
            .iter()
            .filter(|o| &o.path == f && &o.sha256 == h)
            .count()
            != 1
        {
            bail!("vínculo do recibo diverge");
        }
    }
    Ok((d, bytes))
}
pub fn verify(root: &Path) -> Result<Descriptor> {
    let (d, m) = verified(root)?;
    verify_content(root, &d, &m, None)?;
    Ok(d)
}
pub fn restore(root: &Path, output: &Path) -> Result<Descriptor> {
    if crate::output_path_conflicts(root, output)? {
        bail!("restauração dentro do arquivo recusada");
    }
    let (d, m) = verified(root)?;
    let stage = crate::output::Stage::new(output, true)?;
    verify_content(root, &d, &m, Some(&stage.path))?;
    stage.publish(output)?;
    Ok(d)
}
/// Seleção local por arquivo; exploração completa e retomável em compression_stage.py.
pub fn optimize(
    input: &Path,
    manifest: Option<&Path>,
    output: &Path,
    profile: &str,
) -> Result<Descriptor> {
    if crate::output_path_conflicts(input, output)? {
        bail!("saída dentro da origem recusada");
    }
    crate::output::absent(output)?;
    let methods = match profile {
        "quick" => vec!["zstd-3", "xz-6"],
        "exhaustive" => vec!["zstd-3", "zstd-19", "xz-6", "xz-9e", "brotli-5"],
        _ => bail!("perfil inválido"),
    };
    let scratch = crate::output::Stage::temporary(output, true)?;
    let source = scratch.path.join("source.json");
    if let Some(manifest) = manifest {
        if !crate::verify::verify(manifest, input)?.approved {
            bail!("origem reprovada");
        }
        std::fs::write(&source, read_metadata(manifest)?)?;
    } else {
        crate::manifest::Manifest::build_from_dir(input, "urnapack:local-byte-corpus")?
            .save(&source)?;
    }
    let m = origin(&std::fs::read(&source)?)?;
    let mut choices = Vec::new();
    for (index, f) in m.files.iter().enumerate() {
        let original = input.join(&f.path);
        let mut best = original.clone();
        let mut best_size = f.size;
        let mut codec = "stored";
        for method in &methods {
            eprintln!("optimize: {}: {method}", f.path);
            let encoded = scratch.path.join(format!("{index:05}-{method}"));
            let measured = crate::codec::compress(&original, &encoded, method, None)?;
            if measured.output_bytes < best_size {
                if best != original {
                    std::fs::remove_file(&best)?;
                }
                best = encoded;
                best_size = measured.output_bytes;
                codec = method;
            } else {
                std::fs::remove_file(encoded)?;
            }
        }
        choices.push(serde_json::json!({"source_path":f.path,"codec":codec,"encoded_path":best}));
    }
    let selection = scratch.path.join("selection.json");
    std::fs::write(
        &selection,
        serde_json::to_vec_pretty(
            &serde_json::json!({"format_version":1,"source_manifest_sha256":crate::hash::sha256_file(&source)?,"files":choices}),
        )?,
    )?;
    seal_individual(&selection, &source, output)
}
fn verify_content(root: &Path, d: &Descriptor, m: &[u8], destination: Option<&Path>) -> Result<()> {
    if let Some(payload) = &d.payload {
        return verify_payload(&root.join(&payload.file), &d.codec, m, destination);
    }
    let m = origin(m)?;
    for (entry, f) in d.entries.iter().zip(&m.files) {
        let input = root.join(&entry.data.file);
        if let Some(destination) = destination {
            let output = destination.join(&f.path);
            std::fs::create_dir_all(output.parent().context("pai ausente")?)?;
            crate::codec::decompress(&input, &output, &entry.codec, None, &f.sha256, f.size)?;
        } else {
            crate::codec::check(&input, &entry.codec, None, &f.sha256, f.size)?;
        }
    }
    Ok(())
}
