//! Integração real com fixture artificial identificada, sem representar dados TSE.
use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;

fn fixture() -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/statistical-suite/synthetic.csv"),
    )
    .unwrap()
}
fn protocol(input: &Path, raw: &[u8]) -> Value {
    let policy = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("auditoria/2026/evidencias/politica-relogio-nominal-2026.json");
    json!({"format_version":1,"source_kind":"synthetic_fixture","scope":"Fixture sintética, não são dados eleitorais observados",
        "sections":{"path":input,"bytes":raw.len(),"sha256":tsepack::hash::sha256_bytes(raw)},
        "time_policy":{"bytes":std::fs::metadata(&policy).unwrap().len(),"sha256":tsepack::hash::sha256_file(&policy).unwrap(),"path":policy},"log_report":null,
        "permutations":39,"predictive_replicates":19,"seed":77,"folds":5,"minimum_training_sections":8,"size_bin_width":50,"maximum_rho":0.95,"alpha":0.05})
}
fn invoke(p: &Path, out: &Path) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_statistical_suite_2026"))
        .args([
            "--protocol",
            p.to_str().unwrap(),
            "--output",
            out.to_str().unwrap(),
        ])
        .output()
        .unwrap()
}
fn prepare(temp: &Path, raw: &[u8]) -> std::path::PathBuf {
    let input = temp.join("synthetic.csv");
    std::fs::write(&input, raw).unwrap();
    let p = temp.join("protocol.json");
    std::fs::write(&p, serde_json::to_vec(&protocol(&input, raw)).unwrap()).unwrap();
    p
}
fn error_text(o: &std::process::Output) -> String {
    String::from_utf8_lossy(&o.stderr).into_owned()
}

#[test]
fn fixture_hash_is_measured_and_fixture_is_identified() {
    let p = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/statistical-suite/manifest.json");
    let m: Value = serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap();
    assert_eq!(m["kind"], "synthetic_fixture_not_TSE");
    assert_eq!(m["files"]["synthetic.csv"]["bytes"], fixture().len());
    assert_eq!(
        m["files"]["synthetic.csv"]["sha256"],
        tsepack::hash::sha256_bytes(&fixture())
    );
}

#[test]
fn complete_run_preserves_zero_denominator_and_is_reproducible() {
    let t = tempfile::tempdir().unwrap();
    let p = prepare(t.path(), &fixture());
    let a = t.path().join("a");
    let b = t.path().join("b");
    for out in [&a, &b] {
        let o = invoke(&p, out);
        assert!(o.status.success(), "{}", error_text(&o));
    }
    assert_eq!(
        std::fs::read(a.join("report.json")).unwrap(),
        std::fs::read(b.join("report.json")).unwrap()
    );
    let r: Value = serde_json::from_slice(&std::fs::read(a.join("report.json")).unwrap()).unwrap();
    assert_eq!(r["source_kind"], "synthetic_fixture");
    assert_eq!(r["descriptive"]["sections"], 64);
    assert_eq!(r["descriptive"]["zero_valid_sections"], 1);
    assert_eq!(r["descriptive"]["repeated_urn_identifiers"]["groups"], 1);
    let mut reader = csv::Reader::from_path(a.join("section_scores.csv")).unwrap();
    let rows: Vec<_> = reader.records().collect::<Result<_, _>>().unwrap();
    assert_eq!(rows.len(), 64);
    assert_eq!(
        rows[63].iter().next_back().unwrap(),
        "not_tested_zero_valid_votes"
    );
    let tests: Vec<Value> =
        serde_json::from_slice(&std::fs::read(a.join("associations.json")).unwrap()).unwrap();
    assert!(tests
        .iter()
        .filter_map(|r| r["p_mc"].as_f64())
        .all(|p| p >= 1. / 40.));
}
#[test]
fn tampered_bytes_cannot_pass_a_semantically_identical_csv() {
    let t = tempfile::tempdir().unwrap();
    let raw = fixture();
    let p = prepare(t.path(), &raw);
    let mut changed = raw;
    changed.push(b'\n');
    std::fs::write(t.path().join("synthetic.csv"), &changed).unwrap();
    let mut meta: Value = serde_json::from_slice(&std::fs::read(&p).unwrap()).unwrap();
    meta["sections"]["bytes"] = json!(changed.len());
    std::fs::write(&p, serde_json::to_vec(&meta).unwrap()).unwrap();
    let o = invoke(&p, &t.path().join("out"));
    assert!(!o.status.success());
    assert!(error_text(&o).contains("SHA-256 divergente"));
}
#[test]
fn duplicate_key_fails_instead_of_deduplicating() {
    let t = tempfile::tempdir().unwrap();
    let raw = String::from_utf8(fixture()).unwrap();
    let duplicate = format!("{}{}\n", raw, raw.lines().nth(1).unwrap());
    let p = prepare(t.path(), duplicate.as_bytes());
    let o = invoke(&p, &t.path().join("out"));
    assert!(!o.status.success());
    assert!(error_text(&o).contains("chave duplicada"));
}
#[test]
fn bad_arithmetic_unknown_fields_and_existing_output_fail() {
    let raw = String::from_utf8(fixture()).unwrap();
    let mut lines: Vec<_> = raw.lines().map(str::to_string).collect();
    let mut row: Vec<_> = lines[1].split(',').map(str::to_string).collect();
    row[13] = "1".into();
    lines[1] = row.join(",");
    let t = tempfile::tempdir().unwrap();
    let p = prepare(t.path(), lines.join("\n").as_bytes());
    let o = invoke(&p, &t.path().join("out"));
    assert!(!o.status.success());
    assert!(error_text(&o).contains("aritmética divergente"));
    let t = tempfile::tempdir().unwrap();
    let p = prepare(
        t.path(),
        raw.replacen("ANO_ELEICAO", "UNKNOWN_FIELD", 1).as_bytes(),
    );
    let o = invoke(&p, &t.path().join("out"));
    assert!(!o.status.success());
    assert!(error_text(&o).contains("cabeçalho"));
    let t = tempfile::tempdir().unwrap();
    let p = prepare(t.path(), &fixture());
    let out = t.path().join("out");
    std::fs::create_dir(&out).unwrap();
    std::fs::write(out.join("preserve"), b"synthetic existing output").unwrap();
    assert!(!invoke(&p, &out).status.success());
    assert_eq!(
        std::fs::read(out.join("preserve")).unwrap(),
        b"synthetic existing output"
    );
}
#[test]
fn swapping_candidates_preserves_bilateral_evidence() {
    let raw = String::from_utf8(fixture()).unwrap();
    let mut changed = String::new();
    changed.push_str(raw.lines().next().unwrap());
    changed.push('\n');
    for line in raw.lines().skip(1) {
        let mut r: Vec<_> = line.split(',').collect();
        r.swap(17, 18);
        changed.push_str(&r.join(","));
        changed.push('\n');
    }
    let a = tempfile::tempdir().unwrap();
    let b = tempfile::tempdir().unwrap();
    let pa = prepare(a.path(), &fixture());
    let pb = prepare(b.path(), changed.as_bytes());
    for (p, t) in [(&pa, &a), (&pb, &b)] {
        let o = invoke(p, &t.path().join("out"));
        assert!(o.status.success(), "{}", error_text(&o));
    }
    let ra: Vec<Value> =
        serde_json::from_slice(&std::fs::read(a.path().join("out/associations.json")).unwrap())
            .unwrap();
    let rb: Vec<Value> =
        serde_json::from_slice(&std::fs::read(b.path().join("out/associations.json")).unwrap())
            .unwrap();
    for (x, y) in ra.iter().zip(&rb) {
        assert_eq!(x["p_mc"], y["p_mc"]);
        if let (Some(u), Some(v)) = (
            x["partial_pearson_13"].as_f64(),
            y["partial_pearson_13"].as_f64(),
        ) {
            assert!((u + v).abs() < 1e-10);
        }
    }
    let mut x = csv::Reader::from_path(a.path().join("out/section_scores.csv")).unwrap();
    let mut y = csv::Reader::from_path(b.path().join("out/section_scores.csv")).unwrap();
    for (x, y) in x.records().zip(y.records()) {
        let x = x.unwrap();
        let y = y.unwrap();
        for j in 28..36 {
            if !x[j].is_empty() {
                assert!((x[j].parse::<f64>().unwrap() - y[j].parse::<f64>().unwrap()).abs() < 1e-8);
            }
        }
    }
}
