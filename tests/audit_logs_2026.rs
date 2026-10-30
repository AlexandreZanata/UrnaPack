//! O teste executa o binário real com fluxo de fixture e verifica os artefatos.
use std::io::Write;
use std::process::{Command, Stdio};

#[test]
fn cli_checks_hashes_and_produces_verified_stream_receipt() {
    let fixture: serde_json::Value = serde_json::from_slice(include_bytes!(
        "fixtures/audit-2026/log-frame-synthetic.json"
    ))
    .unwrap();
    let mut wire = serde_json::to_vec(&fixture["header"]).unwrap();
    wire.push(b'\n');
    wire.extend(include_bytes!("fixtures/audit-2026/logd-synthetic.dat"));
    wire.extend(serde_json::to_vec(&fixture["end"]).unwrap());
    wire.push(b'\n');
    let temp = tempfile::tempdir().unwrap();
    let output = temp.path().join("analysis.json");
    let sections = temp.path().join("sections.csv");
    let mut child = Command::new(env!("CARGO_BIN_EXE_audit_logs_2026"))
        .args([
            "--output",
            output.to_str().unwrap(),
            "--sections-output",
            sections.to_str().unwrap(),
        ])
        .stdin(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(&wire).unwrap();
    assert!(child.wait().unwrap().success());
    let report: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&output).unwrap()).unwrap();
    assert_eq!(report["success"], true);
    assert_eq!(report["wire_sha256"], tsepack::hash::sha256_bytes(&wire));
    let rows = csv::Reader::from_path(sections).unwrap().records().count();
    assert_eq!(rows, 1);
    let source = |path: &std::path::Path| {
        let bytes = std::fs::read(path).unwrap();
        serde_json::json!({"path": path, "bytes": bytes.len(), "sha256": tsepack::hash::sha256_bytes(&bytes)})
    };
    let manifest = temp.path().join("aggregate-input.json");
    let official = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("auditoria/2026/evidencias/totalizacao-presidente-2t.json");
    let mut input = serde_json::json!({"format_version": 1, "official": source(&official), "inputs": [source(&output)]});
    std::fs::write(&manifest, serde_json::to_vec(&input).unwrap()).unwrap();
    let aggregate = temp.path().join("aggregate.json");
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_audit_logs_2026"))
            .args([
                "--aggregate-manifest",
                manifest.to_str().unwrap(),
                "--output",
                aggregate.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    assert!(!run().status.success());
    let diagnostic: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&aggregate).unwrap()).unwrap();
    assert_eq!(diagnostic["national_coverage_complete"], false);
    assert_eq!(diagnostic["missing_ufs"].as_array().unwrap().len(), 27);
    assert_eq!(diagnostic["all_parsed_events"]["completed_electors"], 2);
    std::fs::remove_file(&aggregate).unwrap();
    input["inputs"][0]["bytes"] = serde_json::json!(0);
    std::fs::write(&manifest, serde_json::to_vec(&input).unwrap()).unwrap();
    assert!(!run().status.success());
    assert!(!aggregate.exists());
    input["inputs"] = serde_json::json!([source(&output), source(&output)]);
    std::fs::write(&manifest, serde_json::to_vec(&input).unwrap()).unwrap();
    assert!(!run().status.success());
    assert!(!aggregate.exists());
}
