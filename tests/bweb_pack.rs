use std::path::Path;
use tsepack::bweb;
const RAW: &[u8] = include_bytes!("fixtures/bweb/reversible.csv");
fn make(root: &Path) -> std::path::PathBuf {
    let input = root.join("original.csv");
    std::fs::write(&input, RAW).unwrap();
    let pack = root.join("pack");
    bweb::pack(&input, &pack, None).unwrap();
    pack
}
fn edit(root: &Path, f: impl FnOnce(&mut serde_json::Value)) {
    let path = root.join("pack.json");
    let mut m = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    f(&mut m);
    std::fs::write(path, serde_json::to_vec_pretty(&m).unwrap()).unwrap();
}
#[test]
fn reversivel_com_duplicatas_zeros_aspas_e_multilinhas() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    let output = tmp.path().join("back.csv");
    let manifest = bweb::unpack(&pack, &output).unwrap();
    assert_eq!(manifest.format_version, 2);
    assert_eq!(manifest.rows, 3);
    assert_eq!(
        manifest.source_member_sha256,
        Some(tsepack::hash::sha256_bytes(RAW))
    );
    assert_eq!(std::fs::read(output).unwrap(), RAW);
}
#[test]
fn quoting_ou_newline_diferente_reprova_sem_saida() {
    for raw in [
        RAW.replace_bytes(b"\r\n", b"\n"),
        RAW.strip_suffix(b"\r\n").unwrap().to_vec(),
        RAW[1..].to_vec(),
    ] {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("input");
        std::fs::write(&source, raw).unwrap();
        let output = tmp.path().join("pack");
        assert!(bweb::pack(&source, &output, None).is_err());
        assert!(!output.exists());
    }
}
trait ReplaceBytes {
    fn replace_bytes(&self, from: &[u8], to: &[u8]) -> Vec<u8>;
}
impl ReplaceBytes for [u8] {
    fn replace_bytes(&self, from: &[u8], to: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        let mut rest = self;
        while let Some(i) = rest.windows(from.len()).position(|s| s == from) {
            out.extend_from_slice(&rest[..i]);
            out.extend_from_slice(to);
            rest = &rest[i + from.len()..];
        }
        out.extend_from_slice(rest);
        out
    }
}
#[test]
fn hash_de_origem_errado_reprova_no_pack_e_no_unpack() {
    let tmp = tempfile::tempdir().unwrap();
    let source = tmp.path().join("in");
    std::fs::write(&source, RAW).unwrap();
    assert!(bweb::pack(
        &source,
        &tmp.path().join("no"),
        Some(tsepack::hash::sha256_bytes(b"fixture diferente"))
    )
    .is_err());
    let pack = make(tmp.path());
    edit(&pack, |m| {
        m["source_member_sha256"] = serde_json::json!(tsepack::hash::sha256_bytes(b"outros bytes"))
    });
    let output = tmp.path().join("no.csv");
    assert!(bweb::unpack(&pack, &output).is_err());
    assert!(!output.exists());
}
#[test]
fn caminhos_metadados_e_campos_desconhecidos_reprovam() {
    for (pointer, value) in [
        ("/columns/0/file", serde_json::json!("../original.csv")),
        ("/columns/0/bytes", serde_json::json!(1)),
        ("/encoding", serde_json::json!("utf-8")),
        ("/lineterminator", serde_json::json!("\n")),
        ("/quoting_rule", serde_json::json!("outra")),
        ("/extra", serde_json::json!("desconhecido")),
        ("/columns/1/file", serde_json::json!("columns/00.bin")),
    ] {
        let tmp = tempfile::tempdir().unwrap();
        let pack = make(tmp.path());
        edit(&pack, |m| {
            if pointer == "/extra" {
                m["extra"] = value;
            } else {
                *m.pointer_mut(pointer).unwrap() = value;
            }
        });
        let output = tmp.path().join("no.csv");
        assert!(bweb::unpack(&pack, &output).is_err(), "{pointer}");
        assert!(!output.exists());
    }
}
#[test]
fn truncado_ou_residuo_mesmo_com_hash_atualizado_reprova_sem_parcial() {
    for truncate in [true, false] {
        let tmp = tempfile::tempdir().unwrap();
        let pack = make(tmp.path());
        let path = pack.join("columns/00.bin");
        let mut bytes = std::fs::read(&path).unwrap();
        if truncate {
            bytes.truncate(1);
        } else {
            bytes.push(42);
        }
        std::fs::write(&path, &bytes).unwrap();
        edit(&pack, |m| {
            m["columns"][0]["bytes"] = serde_json::json!(bytes.len());
            m["columns"][0]["sha256"] = serde_json::json!(tsepack::hash::sha256_bytes(&bytes));
        });
        let output = tmp.path().join("no.csv");
        assert!(bweb::unpack(&pack, &output).is_err());
        assert!(!output.exists());
    }
}
#[test]
fn legado_com_hash_e_legado_sem_hash_sao_distintos() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    edit(&pack, |m| m["format_version"] = serde_json::json!(1));
    bweb::unpack(&pack, &tmp.path().join("back")).unwrap();
    edit(&pack, |m| {
        m["source_member_sha256"] = serde_json::Value::Null
    });
    assert!(bweb::unpack(&pack, &tmp.path().join("no")).is_err());
}
#[test]
fn saida_dentro_do_pacote_e_arquivo_extra_reprovam() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    assert!(bweb::unpack(&pack, &pack.join("new/restore.csv")).is_err());
    assert!(!pack.join("new").exists());
    std::fs::write(pack.join("extra"), RAW).unwrap();
    assert!(bweb::load_verified(&pack).is_err());
}
#[test]
fn checkpoint_retomavel_reconfere_binario_e_origem() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    let out = tmp.path().join("bench.json");
    let first = tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), false).unwrap();
    assert!(first.complete);
    assert_eq!(first.input_bytes, RAW.len() as u64);
    for c in first.cases.iter().skip(1) {
        assert!(c.compress_ns.is_some());
        assert!(c.decompress_ns.is_some());
    }
    let mut checkpoint = first.clone();
    checkpoint.complete = false;
    checkpoint.cases.pop();
    std::fs::write(&out, serde_json::to_vec_pretty(&checkpoint).unwrap()).unwrap();
    let orphan = tmp.path().join("bench.json.assets").join(
        first
            .cases
            .last()
            .unwrap()
            .compressed_file
            .as_ref()
            .unwrap(),
    );
    std::fs::remove_file(orphan).unwrap();
    let resumed =
        tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), true).unwrap();
    assert!(resumed.complete);
    assert!(resumed.cases.iter().any(|c| c.compression_reused));
    let file = tmp
        .path()
        .join("bench.json.assets")
        .join(resumed.cases[1].compressed_file.as_ref().unwrap());
    std::fs::write(file, b"corrompido").unwrap();
    assert!(tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), true).is_err());
    let failed: serde_json::Value = serde_json::from_slice(&std::fs::read(&out).unwrap()).unwrap();
    assert_eq!(failed["complete"], false);
}
#[test]
fn verificador_python_funciona_tambem_com_otimizacao() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    let source = tmp.path().join("original.csv");
    for optimized in [false, true] {
        let mut cmd = std::process::Command::new("python3");
        if optimized {
            cmd.arg("-O");
        }
        let result = cmd
            .arg("scripts/verify_pack.py")
            .arg("--pack")
            .arg(&pack)
            .arg("--original")
            .arg(&source)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
    for (pointer, value) in [
        ("/format_version", serde_json::json!(true)),
        ("/quoted/0", serde_json::json!(1)),
    ] {
        let saved = std::fs::read(pack.join("pack.json")).unwrap();
        edit(&pack, |m| *m.pointer_mut(pointer).unwrap() = value);
        let result = std::process::Command::new("python3")
            .args(["-O", "scripts/verify_pack.py", "--pack"])
            .arg(&pack)
            .arg("--original")
            .arg(&source)
            .output()
            .unwrap();
        assert!(!result.status.success(), "{pointer}");
        std::fs::write(pack.join("pack.json"), saved).unwrap();
    }
    edit(&pack, |m| {
        m["source_member_sha256"] = serde_json::json!(tsepack::hash::sha256_bytes(b"outros bytes"))
    });
    let result = std::process::Command::new("python3")
        .args(["-O", "scripts/verify_pack.py", "--pack"])
        .arg(&pack)
        .arg("--original")
        .arg(&source)
        .output()
        .unwrap();
    assert!(!result.status.success());
}
#[test]
fn limites_de_comprimento_sao_aplicados_antes_de_alocar() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    let bytes = u32::MAX.to_le_bytes();
    std::fs::write(pack.join("columns/00.bin"), bytes).unwrap();
    edit(&pack, |m| {
        m["columns"][0]["bytes"] = serde_json::json!(bytes.len());
        m["columns"][0]["sha256"] = serde_json::json!(tsepack::hash::sha256_bytes(&bytes));
    });
    assert!(bweb::unpack(&pack, &tmp.path().join("no")).is_err());
}

#[test]
fn checkpoint_recalcula_taxas_e_rejeita_fronteiras_de_coluna_falsas() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    let out = tmp.path().join("bench.json");
    let report =
        tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), false).unwrap();
    let mut edited = report.clone();
    edited.cases[1].ratio = None;
    edited.cases[1].saved_pct = None;
    std::fs::write(&out, serde_json::to_vec_pretty(&edited).unwrap()).unwrap();
    let verified =
        tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), true).unwrap();
    assert_eq!(verified.cases[1].ratio, report.cases[1].ratio);
    assert_eq!(verified.cases[1].saved_pct, report.cases[1].saved_pct);
    edited = verified;
    *edited.columns[0].zstd_bytes.get_mut("zstd-1").unwrap() += 1;
    *edited.columns[1].zstd_bytes.get_mut("zstd-1").unwrap() -= 1;
    std::fs::write(&out, serde_json::to_vec_pretty(&edited).unwrap()).unwrap();
    assert!(tsepack::benchmark::run_pack_checkpoint(&pack, "quick", Some(&out), true).is_err());
}

#[cfg(unix)]
#[test]
fn saida_resolve_symlink_antes_de_pai() {
    let tmp = tempfile::tempdir().unwrap();
    let pack = make(tmp.path());
    std::os::unix::fs::symlink(pack.join("columns"), tmp.path().join("alias")).unwrap();
    let output = tmp.path().join("alias/../new.csv");
    assert!(bweb::unpack(&pack, &output).is_err());
    assert!(!pack.join("new.csv").exists());
    assert!(tsepack::output_path_conflicts(&pack, &output).unwrap());
}

#[test]
fn relatorio_escalar_nao_sobrescreve_e_permite_denominador_vazio() {
    let tmp = tempfile::tempdir().unwrap();
    let input = tmp.path().join("empty");
    std::fs::write(&input, []).unwrap();
    let report = tsepack::benchmark::run_on_file(&input, "quick").unwrap();
    assert!(report
        .cases
        .iter()
        .all(|c| c.ratio.is_none() && c.saved_pct.is_none()));
    assert_eq!(report.cases[0].compress_ns, None);
    let output = tmp.path().join("report.json");
    tsepack::benchmark::save_reports(&[report], &output).unwrap();
    let saved = std::fs::read(&output).unwrap();
    assert!(tsepack::benchmark::save_reports(&[], &output).is_err());
    assert_eq!(std::fs::read(output).unwrap(), saved);
}
