use std::path::Path;
const RAW: &[u8] = include_bytes!("fixtures/bweb/reversible.csv");
const QUERIES: &[u8] = include_bytes!("fixtures/bweb/queries.csv");

#[test]
fn codecs_conferem_bytes_e_recusam_hash_errado_sem_promover() {
    let tmp = tempfile::tempdir().unwrap();
    let source = tmp.path().join("source");
    std::fs::write(&source, RAW).unwrap();
    for method in [
        "stored",
        "zstd-1",
        "zstd-3-blocks",
        "xz-6",
        "brotli-5",
        "brotli-11",
    ] {
        let compressed = tmp.path().join(format!("{method}.encoded"));
        let measured = tsepack::codec::compress(&source, &compressed, method, None).unwrap();
        assert!(measured.round_trip_ok);
        assert_eq!(measured.source_sha256, tsepack::hash::sha256_bytes(RAW));
        let output = tmp.path().join(format!("{method}.restored"));
        assert!(tsepack::codec::decompress(
            &compressed,
            &output,
            method,
            None,
            &tsepack::hash::sha256_bytes(b"outros bytes"),
            RAW.len() as u64
        )
        .is_err());
        assert!(!output.exists());
        tsepack::codec::decompress(
            &compressed,
            &output,
            method,
            None,
            &measured.source_sha256,
            RAW.len() as u64,
        )
        .unwrap();
        assert_eq!(std::fs::read(output).unwrap(), RAW);
    }
}

#[test]
fn arquivo_por_fonte_preserva_conteudos_iguais_e_reprova_selecao_duplicada() {
    let tmp = tempfile::tempdir().unwrap();
    let raw = tmp.path().join("raw");
    std::fs::create_dir(&raw).unwrap();
    for name in ["first.csv", "second.csv"] {
        std::fs::write(raw.join(name), RAW).unwrap();
    }
    let manifest = tmp.path().join("manifest.json");
    let m = tsepack::manifest::Manifest::build_from_dir(&raw, "fixture-sintetica").unwrap();
    m.save(&manifest).unwrap();
    let selection = tmp.path().join("selection.json");
    let mut doc = serde_json::json!({"format_version":1,"source_manifest_sha256":tsepack::hash::sha256_file(&manifest).unwrap(),"files":m.files.iter().map(|f|serde_json::json!({"source_path":f.path,"codec":"stored","encoded_path":raw.join(&f.path)})).collect::<Vec<_>>()});
    std::fs::write(&selection, serde_json::to_vec_pretty(&doc).unwrap()).unwrap();
    let archive = tmp.path().join("archive");
    tsepack::archive::seal_individual(&selection, &manifest, &archive).unwrap();
    tsepack::archive::verify(&archive).unwrap();
    let output = tmp.path().join("restored");
    tsepack::archive::restore(&archive, &output).unwrap();
    for name in ["first.csv", "second.csv"] {
        assert_eq!(std::fs::read(output.join(name)).unwrap(), RAW);
    }
    let entries = doc["files"].as_array_mut().unwrap();
    entries[1] = entries[0].clone();
    std::fs::write(&selection, serde_json::to_vec(&doc).unwrap()).unwrap();
    assert!(
        tsepack::archive::seal_individual(&selection, &manifest, &tmp.path().join("no")).is_err()
    );
}

#[test]
fn dicionario_treinado_e_multiplos_blocos_reconstroem_todos_os_bytes() {
    let tmp = tempfile::tempdir().unwrap();
    let raw = RAW.repeat(1024);
    let source = tmp.path().join("source");
    std::fs::write(&source, &raw).unwrap();
    let dictionary = tmp.path().join("dictionary");
    tsepack::codec::train(&source, &dictionary, 512).unwrap();
    for method in ["zstd-3", "zstd-3-blocks"] {
        let output = tmp.path().join(method);
        let m = tsepack::codec::compress(&source, &output, method, Some(&dictionary)).unwrap();
        assert_eq!(m.source_sha256, tsepack::hash::sha256_bytes(&raw));
        tsepack::codec::check(
            &output,
            method,
            Some(&dictionary),
            &m.source_sha256,
            raw.len() as u64,
        )
        .unwrap();
        assert!(
            tsepack::codec::check(&output, method, None, &m.source_sha256, raw.len() as u64)
                .is_err()
        );
    }
}
#[test]
fn decoder_falha_em_truncamento_e_tamanho_excedido() {
    let tmp = tempfile::tempdir().unwrap();
    let source = tmp.path().join("source");
    std::fs::write(&source, RAW).unwrap();
    for method in ["zstd-3", "xz-6", "brotli-5"] {
        let compressed = tmp.path().join(format!("{method}.encoded"));
        let m = tsepack::codec::compress(&source, &compressed, method, None).unwrap();
        let output = tmp.path().join("no");
        assert!(tsepack::codec::decompress(
            &compressed,
            &output,
            method,
            None,
            &m.source_sha256,
            1
        )
        .is_err());
        assert!(!output.exists());
        let mut bytes = std::fs::read(&compressed).unwrap();
        bytes.truncate(bytes.len() / 2);
        std::fs::write(&compressed, bytes).unwrap();
        assert!(tsepack::codec::decompress(
            &compressed,
            &output,
            method,
            None,
            &m.source_sha256,
            RAW.len() as u64
        )
        .is_err());
        assert!(!output.exists());
    }
}
fn prepare(root: &Path) -> (std::path::PathBuf, std::path::PathBuf, std::path::PathBuf) {
    let source = root.join("raw");
    std::fs::create_dir(&source).unwrap();
    std::fs::write(source.join("one.csv"), RAW).unwrap();
    let manifest = root.join("manifest.json");
    tsepack::manifest::Manifest::build_from_dir(&source, "fixture-sintetica")
        .unwrap()
        .save(&manifest)
        .unwrap();
    let tar = root.join("source.tar");
    tsepack::archive::create_tar(&source, &manifest, &tar).unwrap();
    (source, manifest, tar)
}
#[test]
fn arquivo_padrao_deterministico_restaura_e_vincula_recibo() {
    let tmp = tempfile::tempdir().unwrap();
    let (source, manifest, tar) = prepare(tmp.path());
    let second = tmp.path().join("second.tar");
    tsepack::archive::create_tar(&source, &manifest, &second).unwrap();
    assert_eq!(std::fs::read(&tar).unwrap(), std::fs::read(second).unwrap());
    let payload = tmp.path().join("payload.zst");
    tsepack::codec::compress(&tar, &payload, "zstd-3", None).unwrap();
    let archive = tmp.path().join("archive");
    tsepack::archive::seal(&payload, "zstd-3", &manifest, &archive).unwrap();
    tsepack::archive::verify(&archive).unwrap();
    let descriptor = archive.join("dataset.json");
    let saved = std::fs::read(&descriptor).unwrap();
    let mut legacy: serde_json::Value = serde_json::from_slice(&saved).unwrap();
    legacy["format_version"] = serde_json::json!(1);
    legacy.as_object_mut().unwrap().remove("layout");
    legacy.as_object_mut().unwrap().remove("entries");
    std::fs::write(&descriptor, serde_json::to_vec(&legacy).unwrap()).unwrap();
    tsepack::archive::verify(&archive).unwrap();
    legacy["format_version"] = serde_json::json!(2);
    std::fs::write(&descriptor, serde_json::to_vec(&legacy).unwrap()).unwrap();
    assert!(tsepack::archive::verify(&archive).is_err());
    let mut extra: serde_json::Value = serde_json::from_slice(&saved).unwrap();
    extra["unknown"] = serde_json::json!("não ignorar");
    std::fs::write(&descriptor, serde_json::to_vec(&extra).unwrap()).unwrap();
    assert!(tsepack::archive::verify(&archive).is_err());
    std::fs::write(descriptor, saved).unwrap();
    let restored = tmp.path().join("restored");
    tsepack::archive::restore(&archive, &restored).unwrap();
    assert_eq!(std::fs::read(restored.join("one.csv")).unwrap(), RAW);
    assert!(tsepack::archive::restore(&archive, &archive.join("nested/restored")).is_err());
    let mut receipt: serde_json::Value =
        serde_json::from_slice(&std::fs::read(archive.join("execution.json")).unwrap()).unwrap();
    receipt["success"] = serde_json::json!(false);
    std::fs::write(
        archive.join("execution.json"),
        serde_json::to_vec_pretty(&receipt).unwrap(),
    )
    .unwrap();
    let mut d: serde_json::Value =
        serde_json::from_slice(&std::fs::read(archive.join("dataset.json")).unwrap()).unwrap();
    let receipt = archive.join("execution.json");
    d["execution"]["sha256"] = serde_json::json!(tsepack::hash::sha256_file(&receipt).unwrap());
    d["execution"]["bytes"] = serde_json::json!(std::fs::metadata(receipt).unwrap().len());
    std::fs::write(
        archive.join("dataset.json"),
        serde_json::to_vec_pretty(&d).unwrap(),
    )
    .unwrap();
    assert!(tsepack::archive::verify(&archive).is_err());
}

#[test]
fn optimize_e_restore_cli_executam_verificacao_real() {
    let tmp = tempfile::tempdir().unwrap();
    let (source, manifest, _) = prepare(tmp.path());
    let output = tmp.path().join("optimized");
    let result = std::process::Command::new(env!("CARGO_BIN_EXE_tsepack"))
        .args(["optimize", "--input"])
        .arg(&source)
        .arg("--manifest")
        .arg(&manifest)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let descriptor = tsepack::archive::verify(&output).unwrap();
    assert_eq!(descriptor.format_version, tsepack::archive::ARCHIVE_VERSION);
    assert_eq!(descriptor.entries.len(), 1);
    assert!(descriptor.entries[0].data.bytes <= RAW.len() as u64);
    let restored = tmp.path().join("restored-cli");
    let result = std::process::Command::new(env!("CARGO_BIN_EXE_tsepack"))
        .arg("restore")
        .arg("--dataset")
        .arg(&output)
        .arg("--output")
        .arg(&restored)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(std::fs::read(restored.join("one.csv")).unwrap(), RAW);
}
#[test]
fn origem_duplicada_tar_desconhecido_e_campos_extras_reprovam() {
    let tmp = tempfile::tempdir().unwrap();
    let (_source, manifest, _tar) = prepare(tmp.path());
    let bytes = std::fs::read(&manifest).unwrap();
    for name in ["source/unknown.csv", "source/../escape.csv"] {
        let bad = tmp.path().join("bad.tar");
        let mut builder = tar::Builder::new(std::fs::File::create(&bad).unwrap());
        let mut h = tar::Header::new_gnu();
        h.set_mode(0o644);
        h.set_size(bytes.len() as u64);
        h.set_cksum();
        builder
            .append_data(&mut h, "source-manifest.json", bytes.as_slice())
            .unwrap();
        let mut h = tar::Header::new_gnu();
        h.set_size(RAW.len() as u64);
        h.set_mode(0o644);
        h.as_mut_bytes()[..name.len()].copy_from_slice(name.as_bytes());
        h.set_cksum();
        builder.append(&h, RAW).unwrap();
        builder.finish().unwrap();
        drop(builder);
        let output = tmp.path().join("no");
        assert!(tsepack::archive::seal(&bad, "stored", &manifest, &output).is_err());
        assert!(!output.exists());
        std::fs::remove_file(bad).unwrap();
    }
    let mut m = tsepack::manifest::Manifest::load(&manifest).unwrap();
    m.files.push(m.files[0].clone());
    m.save(&manifest).unwrap();
    assert!(tsepack::archive::create_tar(
        &tmp.path().join("raw"),
        &manifest,
        &tmp.path().join("no.tar")
    )
    .is_err());
}
#[test]
fn q2_nao_soma_contexto_por_votavel_e_detecta_divergencia() {
    let tmp = tempfile::tempdir().unwrap();
    let source = tmp.path().join("queries.csv");
    std::fs::write(&source, QUERIES).unwrap();
    let report = tsepack::queries::run(&source).unwrap();
    assert_eq!(report.records, 3);
    assert_eq!(report.q1[0].votes, "6");
    assert_eq!(report.q2_presidente[0].sections, 1);
    assert_eq!(report.q2_presidente[0].comparecimento, "7");
    let pack = tmp.path().join("pack");
    tsepack::bweb::pack(&source, &pack, None).unwrap();
    assert_eq!(
        serde_json::to_value(tsepack::queries::run(&pack).unwrap()).unwrap(),
        serde_json::to_value(report).unwrap()
    );
    let mut rows = csv::ReaderBuilder::new()
        .delimiter(b';')
        .has_headers(false)
        .from_reader(QUERIES)
        .byte_records()
        .map(|r| r.unwrap())
        .collect::<Vec<_>>();
    let mut fields = rows[2].iter().map(|s| s.to_vec()).collect::<Vec<_>>();
    fields[23] = b"8".to_vec();
    fields[24] = b"2".to_vec();
    rows[2] = csv::ByteRecord::from(fields);
    let mut writer = csv::WriterBuilder::new()
        .delimiter(b';')
        .from_writer(Vec::new());
    for r in rows {
        writer.write_byte_record(&r).unwrap();
    }
    std::fs::write(&source, writer.into_inner().unwrap()).unwrap();
    assert!(tsepack::queries::run(&source).is_err());
}
