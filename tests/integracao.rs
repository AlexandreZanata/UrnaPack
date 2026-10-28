//! Round-trip e regressões da Etapa 1: manifesto/verify/inspect.
//!
//! Todos os hashes usam bytes reais calculados; nenhum digest fictício.
//! Cada teste realmente exercita a verificação (não apenas ordenação).

use std::path::{Path, PathBuf};
use tsepack::manifest::{FileEntry, Manifest};
use tsepack::verify::{verify, VerifyStatus};

fn sha_of(data: &[u8]) -> String {
    tsepack::hash::sha256_bytes(data)
}

fn save_manifest(dir: &Path, files: Vec<FileEntry>) -> PathBuf {
    let m = Manifest {
        format_version: tsepack::FORMAT_VERSION,
        tool_version: "teste-etapa1".into(),
        source: "teste".into(),
        files,
    };
    let mpath = dir.join("manifest.json");
    m.save(&mpath).unwrap();
    mpath
}

#[test]
fn manifest_round_trip_e_verify_ok() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("bu_001.csv"), "a,b,c\n1,2,3\n").unwrap();
    std::fs::write(dir.path().join("log.txt"), "evento repetido\n".repeat(100)).unwrap();

    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    assert_eq!(m.files.len(), 2);

    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();
    let m2 = Manifest::load(&mpath).unwrap();
    assert_eq!(m, m2);

    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(rep.approved, "esperava aprovação: {rep:?}");
    assert_eq!(rep.failed, 0);
}

#[test]
fn corrupcao_e_detectada() {
    let dir = tempfile::tempdir().unwrap();
    let f = dir.path().join("dado.csv");
    std::fs::write(&f, "original").unwrap();

    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();

    // Corrompe (trunca/altera) o arquivo após o manifesto.
    std::fs::write(&f, "adulterado!").unwrap();

    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert_eq!(rep.failed, 1);
}

#[test]
fn arquivo_ausente_e_detectado() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("x.bin"), b"0123456789").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = Path::new(dir.path()).join("manifest.json");
    m.save(&mpath).unwrap();

    std::fs::remove_file(dir.path().join("x.bin")).unwrap();
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
}

#[test]
fn corrupcao_mesmo_tamanho_reprova_com_hash_mismatch() {
    let dir = tempfile::tempdir().unwrap();
    let f = dir.path().join("dado.bin");
    std::fs::write(&f, b"ABCDEFGH").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();

    // Mesmo tamanho, conteúdo diferente: deve dar HashMismatch, não Ok.
    std::fs::write(&f, b"ABCDEFGX").unwrap();
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert_eq!(rep.failed, 1);
    assert_eq!(rep.verdicts[0].status, VerifyStatus::HashMismatch);
}

#[test]
fn truncado_reprova_com_size_mismatch() {
    let dir = tempfile::tempdir().unwrap();
    let f = dir.path().join("dado.bin");
    std::fs::write(&f, b"0123456789ABCDEF").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();

    std::fs::write(&f, b"0123").unwrap();
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert_eq!(rep.verdicts[0].status, VerifyStatus::SizeMismatch);
}

#[test]
fn manifesto_vazio_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let mpath = save_manifest(dir.path(), vec![]);
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved, "manifesto sem arquivos não é dataset pronto");
    assert_eq!(rep.files_checked, 0);
}

#[test]
fn versao_incompativel_reprova_com_erro() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("a.txt"), b"oi").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mut raw = serde_json::to_value(&m).unwrap();
    raw["format_version"] = serde_json::json!(999u32);
    let mpath = dir.path().join("manifest.json");
    std::fs::write(&mpath, serde_json::to_string_pretty(&raw).unwrap()).unwrap();

    let err = verify(&mpath, dir.path()).unwrap_err();
    assert!(
        err.to_string().contains("incompatível"),
        "erro inesperado: {err:#}"
    );
    // Leitura direta também reprova.
    assert!(Manifest::load(&mpath).is_err());
}

#[test]
fn caminho_repetido_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let data = b"conteudo";
    std::fs::write(dir.path().join("a.txt"), data).unwrap();
    let h = sha_of(data);
    let entry = FileEntry {
        path: "a.txt".into(),
        size: data.len() as u64,
        sha256: h,
        file_type: "txt".into(),
        url: None,
    };
    let mpath = save_manifest(dir.path(), vec![entry.clone(), entry]);
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert!(rep
        .verdicts
        .iter()
        .all(|v| v.status == VerifyStatus::InvalidPath));
}

#[test]
fn travessia_e_caminhos_invalidos_reprovam() {
    for bad in [
        "../fora.txt",
        "/absoluto.txt",
        "",
        "a//b.txt",
        "a/./b.txt",
        "a/../b.txt",
        "sub/",
    ] {
        let dir = tempfile::tempdir().unwrap();
        let entry = FileEntry {
            path: bad.into(),
            size: 1,
            sha256: sha_of(b"x"),
            file_type: "txt".into(),
            url: None,
        };
        let mpath = save_manifest(dir.path(), vec![entry]);
        let rep = verify(&mpath, dir.path()).unwrap();
        assert!(!rep.approved, "caminho inválido deveria reprovar: {bad:?}");
        assert_eq!(rep.verdicts[0].status, VerifyStatus::InvalidPath);
    }
}

#[test]
fn raiz_inexistente_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let missing = dir.path().join("inexistente");
    assert!(tsepack::inspect::scan(&missing).is_err());
    assert!(Manifest::build_from_dir(&missing, "s").is_err());
}

#[test]
fn raiz_nao_diretorio_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let f = dir.path().join("arq.txt");
    std::fs::write(&f, b"oi").unwrap();
    assert!(tsepack::inspect::scan(&f).is_err());
    assert!(Manifest::build_from_dir(&f, "s").is_err());
}

#[test]
fn raiz_vazia_tem_inventario_explicito() {
    let dir = tempfile::tempdir().unwrap();
    let rep = tsepack::inspect::scan(dir.path()).unwrap();
    assert_eq!(rep.file_count, 0);
    assert_eq!(rep.total_bytes, 0);
    assert!(rep.by_type.is_empty());
    let m = Manifest::build_from_dir(dir.path(), "s").unwrap();
    assert!(m.files.is_empty());
    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();
    let v = verify(&mpath, dir.path()).unwrap();
    assert!(!v.approved);
}

#[cfg(unix)]
#[test]
fn link_legitimo_da_raiz_e_resolvido() {
    let dir = tempfile::tempdir().unwrap();
    let real = dir.path().join("real");
    std::fs::create_dir(&real).unwrap();
    std::fs::write(real.join("a.txt"), b"conteudo-legitimo").unwrap();
    let link = dir.path().join("ligacao");
    std::os::unix::fs::symlink(&real, &link).unwrap();

    let m = Manifest::build_from_dir(&link, "s").unwrap();
    assert_eq!(m.files.len(), 1);
    assert_eq!(m.files[0].path, "a.txt");
    let rep = tsepack::inspect::scan(&link).unwrap();
    assert_eq!(rep.file_count, 1);
}

#[cfg(unix)]
#[test]
fn symlink_interno_reprova_build() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("real.txt"), b"dados").unwrap();
    std::os::unix::fs::symlink(dir.path().join("real.txt"), dir.path().join("atalho.txt")).unwrap();
    let err = Manifest::build_from_dir(dir.path(), "s").unwrap_err();
    assert!(err.to_string().contains("symlink"), "erro: {err:#}");
    assert!(tsepack::inspect::scan(dir.path()).is_err());
}

#[cfg(unix)]
#[test]
fn symlink_no_arquivo_verificado_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let outside = dir.path().join("fora.txt");
    std::fs::write(&outside, b"segredo").unwrap();
    // Manifesto declara sub/link.txt mas link aponta para fora.
    let sub = dir.path().join("sub");
    std::fs::create_dir(&sub).unwrap();
    std::os::unix::fs::symlink(&outside, sub.join("link.txt")).unwrap();

    let entry = FileEntry {
        path: "sub/link.txt".into(),
        size: 7,
        sha256: sha_of(b"segredo"),
        file_type: "txt".into(),
        url: None,
    };
    let mpath = save_manifest(dir.path(), vec![entry]);
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert_eq!(rep.verdicts[0].status, VerifyStatus::InvalidPath);
}

#[cfg(unix)]
#[test]
fn arquivo_especial_fifo_reprova_build() {
    let dir = tempfile::tempdir().unwrap();
    let fifo = dir.path().join("canal.fifo");
    let st = std::process::Command::new("mkfifo")
        .arg(&fifo)
        .status()
        .expect("mkfifo disponível no ambiente de teste");
    assert!(st.success());
    let err = Manifest::build_from_dir(dir.path(), "s").unwrap_err();
    assert!(
        err.to_string().contains("especial") || err.to_string().contains("symlink"),
        "erro: {err:#}"
    );
}

#[cfg(unix)]
#[test]
fn erro_de_leitura_por_permissao_propaga() {
    let dir = tempfile::tempdir().unwrap();
    let sub = dir.path().join("restrito");
    std::fs::create_dir(&sub).unwrap();
    std::fs::write(sub.join("a.txt"), b"dados").unwrap();
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(&sub, std::fs::Permissions::from_mode(0o000)).unwrap();
    let res = Manifest::build_from_dir(dir.path(), "s");
    // Restaura para o TempDir conseguir limpar.
    std::fs::set_permissions(&sub, std::fs::Permissions::from_mode(0o700)).unwrap();
    assert!(res.is_err(), "travessia sem permissão deveria reprovar");
}

// ---- CLI: exit != 0 nos casos inválidos ----

fn bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_tsepack"))
}

fn run_cli(args: &[&str]) -> std::process::Output {
    std::process::Command::new(bin())
        .args(args)
        .output()
        .expect("executar tsepack")
}

#[test]
fn cli_verify_aprova_fonte_valida() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("ok.txt"), b"integro").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "s").unwrap();
    let mpath = dir.path().join("m.json");
    m.save(&mpath).unwrap();
    let out = run_cli(&[
        "verify",
        "--manifest",
        mpath.to_str().unwrap(),
        "--source",
        dir.path().to_str().unwrap(),
    ]);
    assert!(
        out.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn cli_verify_reprova_hash_e_versao_com_exit_nao_zero() {
    // Hash divergente.
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("a.txt"), b"um").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "s").unwrap();
    let mpath = dir.path().join("m.json");
    m.save(&mpath).unwrap();
    std::fs::write(dir.path().join("a.txt"), b"do").unwrap();
    let out = run_cli(&[
        "verify",
        "--manifest",
        mpath.to_str().unwrap(),
        "--source",
        dir.path().to_str().unwrap(),
    ]);
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains("HashMismatch"));

    // Versão incompatível.
    let dir2 = tempfile::tempdir().unwrap();
    std::fs::write(dir2.path().join("a.txt"), b"um").unwrap();
    let m2 = Manifest::build_from_dir(dir2.path(), "s").unwrap();
    let mut raw = serde_json::to_value(&m2).unwrap();
    raw["format_version"] = serde_json::json!(999u32);
    let mp2 = dir2.path().join("m.json");
    std::fs::write(&mp2, serde_json::to_string_pretty(&raw).unwrap()).unwrap();
    let out2 = run_cli(&[
        "verify",
        "--manifest",
        mp2.to_str().unwrap(),
        "--source",
        dir2.path().to_str().unwrap(),
    ]);
    assert!(!out2.status.success());
}

#[test]
fn cli_inspect_reprova_raiz_inexistente() {
    let dir = tempfile::tempdir().unwrap();
    let missing = dir.path().join("inexistente");
    let out = run_cli(&["inspect", "--input", missing.to_str().unwrap()]);
    assert!(!out.status.success());
}

#[cfg(unix)]
#[test]
fn diretorio_vazio_nao_utf8_e_rejeitado() {
    use std::os::unix::ffi::OsStringExt;
    let dir = tempfile::tempdir().unwrap();
    let name = std::ffi::OsString::from_vec(vec![0xff]);
    std::fs::create_dir(dir.path().join(name)).unwrap();
    assert!(tsepack::inspect::scan(dir.path()).is_err());
    assert!(Manifest::build_from_dir(dir.path(), "fixture-sintetica").is_err());
}

#[cfg(unix)]
#[test]
fn inventario_nao_gera_caminho_que_verify_rejeita() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("barra\\invertida.csv"),
        include_bytes!("fixtures/data/bu-amostra.csv"),
    )
    .unwrap();
    assert!(tsepack::inspect::scan(dir.path()).is_err());
    assert!(Manifest::build_from_dir(dir.path(), "fixture-sintetica").is_err());
}

#[test]
fn caminhos_windows_e_nul_reprovam_sem_depender_do_host() {
    for path in ["C:/fora.csv", "C:fora.csv", "bad\0name.csv"] {
        assert!(tsepack::traverse::validate_manifest_rel(path).is_err());
    }
}

// ---- Etapa 2: origem v1 congelado, v2 estrito, migração ----

fn sha_hex(data: &[u8]) -> String {
    tsepack::hash::sha256_bytes(data)
}

fn v1_json(path: &str, size: u64, sha: &str) -> serde_json::Value {
    serde_json::json!({
        "format_version": 1,
        "tool_version": "teste-e2",
        "source": "fixture-sintetica",
        "files": [{"path": path, "size": size, "sha256": sha,
                   "file_type": "csv", "url": null}]
    })
}

#[test]
fn origem_v2_escrita_por_padrao() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("a.csv"), b"conteudo").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "fixture-sintetica").unwrap();
    assert_eq!(m.format_version, tsepack::FORMAT_VERSION);
    assert_eq!(m.format_version, 2);
}

#[test]
fn origem_v1_congelado_carrega() {
    let dir = tempfile::tempdir().unwrap();
    let data = b"linhagem-v1";
    std::fs::write(dir.path().join("dado.csv"), data).unwrap();
    let mp = dir.path().join("m.json");
    std::fs::write(
        &mp,
        serde_json::to_string_pretty(&v1_json("dado.csv", data.len() as u64, &sha_hex(data)))
            .unwrap(),
    )
    .unwrap();
    let m = Manifest::load(&mp).unwrap();
    assert_eq!(m.format_version, 1);
    assert_eq!(m.files.len(), 1);
    let rep = verify(&mp, dir.path()).unwrap();
    assert!(rep.approved);
}

#[test]
fn origem_rejeita_campo_desconhecido() {
    let dir = tempfile::tempdir().unwrap();
    let data = b"conteudo";
    // Extra no nível do manifesto.
    let mut doc = v1_json("a.csv", data.len() as u64, &sha_hex(data));
    doc["garantia_futura"] = serde_json::json!("nao-transportar");
    let mp = dir.path().join("m.json");
    std::fs::write(&mp, serde_json::to_string(&doc).unwrap()).unwrap();
    assert!(Manifest::load(&mp).is_err());
    // Extra no nível do arquivo.
    let mut doc2 = v1_json("a.csv", data.len() as u64, &sha_hex(data));
    doc2["files"][0]["assinatura_nova"] = serde_json::json!("x");
    std::fs::write(&mp, serde_json::to_string(&doc2).unwrap()).unwrap();
    assert!(Manifest::load(&mp).is_err());
}

#[test]
fn origem_rejeita_versao_nao_suportada() {
    let dir = tempfile::tempdir().unwrap();
    for v in [0u32, 3, 999] {
        let mut doc = v1_json("a.csv", 1, &sha_hex(b"x"));
        doc["format_version"] = serde_json::json!(v);
        let mp = dir.path().join("m.json");
        std::fs::write(&mp, serde_json::to_string(&doc).unwrap()).unwrap();
        let err = Manifest::load(&mp).unwrap_err();
        assert!(err.to_string().contains("incompatível"), "v={v}: {err:#}");
        assert!(verify(&mp, dir.path()).is_err());
    }
}

#[test]
fn migracao_v1_para_v2_preserva_arquivos() {
    let dir = tempfile::tempdir().unwrap();
    let data = b"bytes-originais";
    std::fs::write(dir.path().join("a.csv"), data).unwrap();
    let mp1 = dir.path().join("m1.json");
    std::fs::write(
        &mp1,
        serde_json::to_string_pretty(&v1_json("a.csv", data.len() as u64, &sha_hex(data))).unwrap(),
    )
    .unwrap();
    let v1 = Manifest::load(&mp1).unwrap();
    // Migração: mesmos arquivos, versão de escrita atual.
    let v2 = Manifest {
        format_version: tsepack::FORMAT_VERSION,
        tool_version: v1.tool_version.clone(),
        source: v1.source.clone(),
        files: v1.files.clone(),
    };
    let mp2 = dir.path().join("m2.json");
    v2.save(&mp2).unwrap();
    let relido = Manifest::load(&mp2).unwrap();
    assert_eq!(relido.format_version, 2);
    assert_eq!(relido.files, v1.files);
    let rep = verify(&mp2, dir.path()).unwrap();
    assert!(rep.approved);
}
