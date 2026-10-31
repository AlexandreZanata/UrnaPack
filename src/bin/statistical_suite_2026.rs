//! Bateria exploratória simétrica. Alertas de modelos não classificam fraude.
use anyhow::{ensure, Context, Result};
use clap::Parser;
use csv::{ReaderBuilder, StringRecord};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use tsepack::statistics::{
    self as stats, Model, Moments, Observation, SplitMix64, FEATURE_COUNT, MODEL_NAMES,
    SECTION_HEADER,
};
#[path = "../audit_io.rs"]
mod audit_io;
use audit_io::{publish_file, HashingRead};

#[derive(Parser)]
struct Args {
    #[arg(long)]
    protocol: PathBuf,
    #[arg(long)]
    output: PathBuf,
    /// Troca só o caminho, mantendo tamanho e hash fixados no protocolo.
    #[arg(long)]
    sections: Option<PathBuf>,
    #[arg(long)]
    time_policy: Option<PathBuf>,
    #[arg(long)]
    log_report: Option<PathBuf>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Source {
    path: PathBuf,
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Protocol {
    format_version: u32,
    source_kind: String,
    scope: String,
    sections: Source,
    time_policy: Source,
    log_report: Option<Source>,
    permutations: usize,
    predictive_replicates: usize,
    seed: u64,
    folds: usize,
    minimum_training_sections: u64,
    size_bin_width: u64,
    maximum_rho: f64,
    alpha: f64,
}
struct Row {
    raw: StringRecord,
    key: String,
    municipality: String,
    zone: String,
    local: String,
    uf: usize,
    fold: usize,
    n: u64,
    k: u64,
    aptos: u64,
    turnout: u64,
    biometric: u64,
    invalid: u64,
    closing: Option<f64>,
    row_seed: u64,
}
fn limit(name: &str) -> Result<usize> {
    Ok(tsepack::limits::get(name)? as usize)
}
fn checked_bytes(source: &Source) -> Result<Vec<u8>> {
    ensure!(
        std::fs::metadata(&source.path)?.len() == source.bytes,
        "tamanho divergente: {}",
        source.path.display()
    );
    ensure!(
        source.bytes <= tsepack::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?,
        "metadados acima do limite"
    );
    let raw = std::fs::read(&source.path)?;
    ensure!(
        tsepack::hash::sha256_bytes(&raw) == source.sha256,
        "SHA-256 divergente: {}",
        source.path.display()
    );
    Ok(raw)
}
fn number(record: &StringRecord, index: usize) -> Result<u64> {
    record[index].parse::<u64>().with_context(|| {
        format!(
            "inteiro inválido em {}: {:?}",
            SECTION_HEADER[index], &record[index]
        )
    })
}
fn clock(text: &str) -> Result<f64> {
    ensure!(
        text.len() == 19 && text.starts_with("2026-10-25 "),
        "data/hora fora do escopo: {text}"
    );
    let parts: Vec<_> = text[11..].split(':').collect();
    ensure!(
        parts.len() == 3
            && parts
                .iter()
                .all(|x| x.len() == 2 && x.bytes().all(|b| b.is_ascii_digit())),
        "hora inválida"
    );
    let h: u32 = parts[0].parse()?;
    let m: u32 = parts[1].parse()?;
    let s: u32 = parts[2].parse()?;
    ensure!(h < 24 && m < 60 && s < 60, "hora inválida");
    Ok((h * 3600 + m * 60 + s) as f64)
}
fn load_rows(p: &Protocol, policy: &Value) -> Result<(Vec<Row>, Vec<String>)> {
    ensure!(policy["format_version"] == 1, "política incompatível");
    let shifts = policy["brt_shift_seconds_by_uf"]
        .as_object()
        .context("política sem UFs")?;
    let overrides = policy["municipality_overrides"]
        .as_object()
        .context("política sem exceções")?;
    let ufs: Vec<_> = shifts.keys().cloned().collect();
    ensure!(
        ufs.iter()
            .all(|s| s.len() == 2 && s.bytes().all(|b| b.is_ascii_uppercase())),
        "UF inválida"
    );
    ensure!(
        std::fs::metadata(&p.sections.path)?.len() == p.sections.bytes
            && p.sections.bytes <= tsepack::limits::get("MAX_SOURCE_FILE_BYTES")?,
        "tamanho da projeção divergente ou excessivo"
    );
    let stream = HashingRead {
        inner: std::fs::File::open(&p.sections.path)?,
        hash: Sha256::new(),
        bytes: 0,
    };
    let mut reader = ReaderBuilder::new().from_reader(stream);
    ensure!(
        reader.headers()?.iter().eq(SECTION_HEADER),
        "cabeçalho da projeção desconhecido"
    );
    let mut rows = Vec::new();
    let mut keys = BTreeSet::new();
    let mut found = BTreeSet::new();
    let cap = limit("MAX_STATS_COUNT_PER_SECTION")? as u64;
    let max_sections = limit("MAX_BWEB_OCCURRENCE_KEYS")?.min(limit("MAX_CSV_RECORDS")?);
    let max_field = limit("MAX_FIELD_BYTES")?;
    let max_record = limit("MAX_RECORD_BYTES")?;
    for record in reader.records() {
        let raw = record?;
        ensure!(rows.len() < max_sections, "limite de seções excedido");
        ensure!(
            raw.iter().all(|s| s.len() <= max_field) && raw.as_slice().len() <= max_record,
            "campo excessivo"
        );
        ensure!(
            &raw[0] == "2026"
                && &raw[1] == "3221"
                && &raw[2] == "6258"
                && &raw[3] == "2"
                && &raw[8] == "1",
            "pleito/turno/cargo incompatível"
        );
        let uf = ufs
            .binary_search(&raw[4].to_owned())
            .map_err(|_| anyhow::anyhow!("UF ausente da política"))?;
        found.insert(ufs[uf].clone());
        let municipality = format!("{}/{:05}", &raw[4], number(&raw, 5)?);
        let zone = format!("{municipality}/{:04}", number(&raw, 6)?);
        let key = format!("{zone}/{:04}", number(&raw, 7)?);
        ensure!(keys.insert(key.clone()), "chave duplicada: {key}");
        let local = format!("{zone}/{:04}", number(&raw, 9)?);
        number(&raw, 10)?;
        number(&raw, 12)?;
        let aptos = number(&raw, 13)?;
        let turnout = number(&raw, 14)?;
        let absence = number(&raw, 15)?;
        let biometric = number(&raw, 16)?;
        let k = number(&raw, 17)?;
        let other = number(&raw, 18)?;
        let blank = number(&raw, 19)?;
        let null = number(&raw, 20)?;
        ensure!(
            [aptos, turnout, absence, biometric, k, other, blank, null]
                .iter()
                .all(|x| *x <= cap),
            "contagem acima do limite"
        );
        ensure!(
            aptos == turnout + absence
                && turnout == k + other + blank + null
                && biometric <= turnout,
            "aritmética divergente: {key}"
        );
        let shift = overrides.get(&municipality).unwrap_or(&shifts[&ufs[uf]]);
        ensure!(
            shift.is_null() || shift.as_i64().is_some(),
            "deslocamento inválido"
        );
        let closing = if raw[11].is_empty() {
            None
        } else {
            let t = clock(&raw[11])?;
            shift.as_i64().map(|s| t + s as f64)
        };
        let hash = Sha256::digest(key.as_bytes());
        let row_seed = u64::from_le_bytes(hash[..8].try_into()?);
        rows.push(Row {
            raw,
            key,
            municipality,
            zone,
            local,
            uf,
            fold: (row_seed % p.folds as u64) as usize,
            n: k + other,
            k,
            aptos,
            turnout,
            biometric,
            invalid: blank + null,
            closing,
            row_seed,
        });
    }
    let checked = reader.into_inner();
    ensure!(
        checked.bytes == p.sections.bytes
            && hex::encode(checked.hash.finalize()) == p.sections.sha256,
        "SHA-256 divergente na projeção"
    );
    ensure!(
        !rows.is_empty() && rows.iter().any(|r| r.n > 0),
        "projeção vazia ou sem votos válidos"
    );
    if p.source_kind == "official_derived" {
        ensure!(
            found.into_iter().collect::<Vec<_>>() == ufs,
            "projeção nacional com cobertura parcial"
        );
    }
    rows.sort_by(|a, b| a.key.cmp(&b.key));
    Ok((rows, ufs))
}

struct Pools {
    national: Moments,
    uf: Vec<Moments>,
    municipal: BTreeMap<String, Moments>,
    uf_fold: Vec<Vec<Moments>>,
    municipal_fold: BTreeMap<String, Vec<Moments>>,
}
impl Pools {
    fn fit(rows: &[Row], ufs: usize, folds: usize) -> Self {
        let mut pools = Self {
            national: Moments::default(),
            uf: vec![Moments::default(); ufs],
            municipal: BTreeMap::new(),
            uf_fold: vec![vec![Moments::default(); folds]; ufs],
            municipal_fold: BTreeMap::new(),
        };
        for r in rows.iter().filter(|r| r.n > 0) {
            pools.national.add(r.k, r.n);
            pools.uf[r.uf].add(r.k, r.n);
            pools
                .municipal
                .entry(r.municipality.clone())
                .or_default()
                .add(r.k, r.n);
            pools.uf_fold[r.uf][r.fold].add(r.k, r.n);
            pools
                .municipal_fold
                .entry(r.municipality.clone())
                .or_insert_with(|| vec![Moments::default(); folds])[r.fold]
                .add(r.k, r.n);
        }
        pools
    }
    fn models(&self, r: &Row, p: &Protocol) -> Result<([Model; 4], u64, bool)> {
        let local =
            self.municipal[&r.municipality].without(self.municipal_fold[&r.municipality][r.fold]);
        let fallback = local.sections < p.minimum_training_sections;
        let training = if fallback {
            self.uf[r.uf].without(self.uf_fold[r.uf][r.fold])
        } else {
            local
        };
        ensure!(
            training.sections > 0,
            "fold sem treino independente: {}",
            r.key
        );
        Ok((
            [
                self.national.binomial(),
                self.uf[r.uf].binomial(),
                self.municipal[&r.municipality].binomial(),
                training.beta_binomial(p.maximum_rho),
            ],
            training.sections,
            fallback,
        ))
    }
}
struct Score {
    log_p: [f64; 4],
    log_holm: [f64; 4],
    models: [Model; 4],
    training: u64,
    fallback: bool,
    pit: f64,
    expected_tails: [[f64; 4]; 4],
}
struct Chunk {
    scores: Vec<Option<Score>>,
    expected: [f64; FEATURE_COUNT],
    simulated: Vec<[u64; FEATURE_COUNT]>,
}
fn score_chunk(rows: &[Row], pools: &Pools, p: &Protocol) -> Result<Chunk> {
    let mut chunk = Chunk {
        scores: Vec::new(),
        expected: [0.0; FEATURE_COUNT],
        simulated: vec![[0; FEATURE_COUNT]; p.predictive_replicates],
    };
    for r in rows {
        if r.n == 0 {
            chunk.scores.push(None);
            continue;
        }
        let (models, training, fallback) = pools.models(r, p)?;
        let mut score = Score {
            log_p: [0.0; 4],
            log_holm: [0.0; 4],
            models,
            training,
            fallback,
            pit: 0.0,
            expected_tails: [[0.0; 4]; 4],
        };
        for (i, model) in models.iter().enumerate() {
            let n = r.n as usize;
            let k = r.k as usize;
            let log = model.log_pmf(n)?;
            score.log_p[i] = stats::log_two_sided(&log, k);
            let threshold = 9 * n / 10 + 1;
            score.expected_tails[i] = [
                log[n].exp(),
                log[0].exp(),
                stats::log_sum(&log[threshold..]).exp(),
                stats::log_sum(&log[..=n - threshold]).exp(),
            ];
            if i == 3 {
                let mut cdf = Vec::with_capacity(n + 1);
                let mut sum = 0.0;
                for (j, lp) in log.iter().enumerate() {
                    let prob = lp.exp();
                    let f = stats::features(j, n);
                    for (dest, value) in chunk.expected.iter_mut().zip(f) {
                        *dest += prob * value as f64;
                    }
                    sum += prob;
                    cdf.push(sum);
                }
                ensure!((sum - 1.0).abs() < 1e-10, "CDF divergente");
                *cdf.last_mut().unwrap() = 1.0;
                let mut rng = SplitMix64(p.seed ^ r.row_seed ^ 0x87c37b91114253d5);
                score.pit = ((if k == 0 { 0.0 } else { cdf[k - 1] }) + rng.unit() * log[k].exp())
                    .clamp(0.0, 1.0);
                for simulated in &mut chunk.simulated {
                    let u = rng.unit();
                    let sample = cdf.partition_point(|v| *v <= u).min(n);
                    let f = stats::features(sample, n);
                    for (dest, value) in simulated.iter_mut().zip(f) {
                        *dest += value;
                    }
                }
            }
        }
        chunk.scores.push(Some(score));
    }
    Ok(chunk)
}
fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    publish_file(path, |f| {
        serde_json::to_writer_pretty(f, value)?;
        Ok(())
    })
}
fn observed_counts(rows: &[Row]) -> [u64; FEATURE_COUNT] {
    let mut counts = [0; FEATURE_COUNT];
    for r in rows.iter().filter(|r| r.n > 0) {
        let f = stats::features(r.k as usize, r.n as usize);
        for i in 0..FEATURE_COUNT {
            counts[i] += f[i];
        }
    }
    counts
}
fn report_models(rows: &[Row], scores: &[Option<Score>], ufs: &[String], p: &Protocol) -> Value {
    let mut by_scope = BTreeMap::new();
    for (scope, uf) in std::iter::once(("BR".to_string(), None))
        .chain(ufs.iter().enumerate().map(|(i, s)| (s.clone(), Some(i))))
    {
        let mut observed = [0_u64; 4];
        let mut expected = [[0.0; 4]; 4];
        let mut flags = [[0_u64; 2]; 4];
        let mut pit = [0_u64; 20];
        let mut tails = [0_u64; 4];
        let mut fallback = 0;
        let mut valid = 0;
        let mut rho_sum = 0.0;
        for (r, s) in rows.iter().zip(scores) {
            if uf.is_some_and(|u| r.uf != u) {
                continue;
            }
            let Some(s) = s else {
                continue;
            };
            valid += 1;
            for i in 0..4 {
                observed[i] += stats::features(r.k as usize, r.n as usize)[i];
                for (dest, value) in expected[i].iter_mut().zip(s.expected_tails[i]) {
                    *dest += value;
                }
                if s.log_holm[i] <= p.alpha.ln() {
                    flags[i][(r.k as f64 / (r.n as f64) < s.models[i].mean) as usize] += 1;
                }
            }
            pit[((s.pit * 20.0) as usize).min(19)] += 1;
            for (i, a) in [0.05_f64, 0.01, 0.001, 0.0001].iter().enumerate() {
                tails[i] += (s.log_p[3] <= a.ln()) as u64;
            }
            fallback += s.fallback as u64;
            rho_sum += s.models[3].rho;
        }
        by_scope.insert(scope,json!({"valid_sections":valid,"observed_tail_counts_order_13_unanimity_22_unanimity_13_gt90_22_gt90":observed,
            "expected_tail_counts_by_model":expected,"holm_nominal_flags_excess_13_excess_22_by_model":flags,"crossfit_pit_histogram_20_bins":pit,"crossfit_nominal_tail_levels":[0.05,0.01,0.001,0.0001],"crossfit_nominal_tail_counts":tails,"crossfit_fallback_to_uf":fallback,"crossfit_mean_rho":if valid>0 {Some(rho_sum/valid as f64)}else{None}}));
    }
    json!({"model_order":MODEL_NAMES,"scope":by_scope,"interpretation":"Scores/checagens nominais de modelos estimados. Desvios de calibração podem invalidar interpretação inferencial; não são probabilidades de fraude.","holm_family":"Todos os pares modelo × seção com válidos positivos, incluindo os quatro modelos; candidato complementar é a mesma hipótese bilateral."})
}
fn write_scores(out: &Path, rows: &[Row], scores: &[Option<Score>]) -> Result<()> {
    publish_file(out, |f| {
        let mut writer = csv::Writer::from_writer(f);
        let mut header: Vec<String> = SECTION_HEADER.iter().map(|s| s.to_string()).collect();
        header.extend(
            [
                "section_key",
                "fold",
                "training_sections",
                "training_fallback_uf",
                "crossfit_mean_13",
                "crossfit_rho",
                "randomized_pit",
            ]
            .map(str::to_string),
        );
        header.extend(MODEL_NAMES.iter().map(|s| format!("ln_p_{s}")));
        header.extend(MODEL_NAMES.iter().map(|s| format!("ln_holm_{s}")));
        header.push("score_status".into());
        writer.write_record(header)?;
        for (r, s) in rows.iter().zip(scores) {
            let mut record: Vec<String> = r.raw.iter().map(str::to_string).collect();
            record.extend([r.key.clone(), r.fold.to_string()]);
            if let Some(s) = s {
                record.extend([
                    s.training.to_string(),
                    s.fallback.to_string(),
                    s.models[3].mean.to_string(),
                    s.models[3].rho.to_string(),
                    s.pit.to_string(),
                ]);
                record.extend(s.log_p.map(|v| v.to_string()));
                record.extend(s.log_holm.map(|v| v.to_string()));
                record.push("nominal_model_score".into());
            } else {
                record.extend(std::iter::repeat_n(String::new(), 13));
                record.push("not_tested_zero_valid_votes".into());
            }
            writer.write_record(record)?;
        }
        writer.flush()?;
        Ok(())
    })
}
fn descriptive(rows: &[Row], ufs: &[String], out: &Path) -> Result<Value> {
    let mut urns: BTreeMap<u64, Vec<&Row>> = BTreeMap::new();
    let mut profiles: BTreeMap<(u64, u64, u64, u64), Vec<&Row>> = BTreeMap::new();
    let mut cells = vec![vec![vec![0_u64; 20]; 20]; ufs.len()];
    let mut raw_correlations = vec![[[0.0; 6]; 4]; ufs.len() + 1];
    let mut digits = vec![[[0_u64; 9]; 2]; ufs.len()];
    let mut no_valid = 0;
    let mut clock_missing = 0;
    let mut turnout100 = 0;
    let mut aptoszero = 0;
    let mut types = BTreeMap::new();
    for r in rows {
        let urn = r.raw[10].parse()?;
        urns.entry(urn).or_default().push(r);
        profiles
            .entry((r.k, r.n - r.k, r.raw[19].parse()?, r.raw[20].parse()?))
            .or_default()
            .push(r);
        *types.entry(r.raw[12].to_owned()).or_insert(0_u64) += 1;
        clock_missing += r.closing.is_none() as u64;
        aptoszero += (r.aptos == 0) as u64;
        turnout100 += (r.aptos > 0 && r.turnout == r.aptos) as u64;
        if r.n == 0 {
            no_valid += 1;
            continue;
        }
        if let Some(bin) = (20 * r.turnout).checked_div(r.aptos) {
            cells[r.uf][(bin as usize).min(19)][((20 * r.k / r.n) as usize).min(19)] += 1;
        }
        for (candidate, mut votes) in [r.k, r.n - r.k].into_iter().enumerate() {
            if votes > 0 {
                while votes >= 10 {
                    votes /= 10;
                }
                digits[r.uf][candidate][votes as usize - 1] += 1;
            }
        }
        let y = r.k as f64 / r.n as f64;
        let x = [
            (r.aptos > 0).then(|| r.turnout as f64 / r.aptos as f64),
            (r.turnout > 0).then(|| r.biometric as f64 / r.turnout as f64),
            (r.turnout > 0).then(|| r.invalid as f64 / r.turnout as f64),
            r.closing,
        ];
        for (j, x) in x.iter().enumerate() {
            if let Some(x) = x {
                for s in [0, r.uf + 1] {
                    let a = &mut raw_correlations[s][j];
                    a[0] += 1.0;
                    a[1] += x;
                    a[2] += y;
                    a[3] += x * x;
                    a[4] += y * y;
                    a[5] += x * y;
                }
            }
        }
    }
    let mut urn_groups = 0;
    let mut urn_rows = 0;
    let mut repeated_profiles = 0;
    let mut profile_rows = 0;
    let mut pairs = 0;
    publish_file(&out.join("repeated_urn_identifiers.csv"), |f| {
        let mut w = csv::Writer::from_writer(f);
        w.write_record(["urn_identifier", "section_key", "sections_with_identifier"])?;
        for (urn, list) in &urns {
            if list.len() > 1 {
                urn_groups += 1;
                urn_rows += list.len();
                for r in list {
                    w.write_record([urn.to_string(), r.key.clone(), list.len().to_string()])?;
                }
            }
        }
        w.flush()?;
        Ok(())
    })?;
    publish_file(&out.join("repeated_vote_profiles.csv"), |f| {
        let mut w = csv::Writer::from_writer(f);
        w.write_record([
            "votes_13",
            "votes_22",
            "blank",
            "null",
            "multiplicity",
            "distinct_municipalities",
            "distinct_voting_places",
        ])?;
        for (profile, list) in &profiles {
            if list.len() > 1 {
                repeated_profiles += 1;
                profile_rows += list.len();
                pairs += list.len() as u64 * (list.len() as u64 - 1) / 2;
                w.write_record([
                    profile.0.to_string(),
                    profile.1.to_string(),
                    profile.2.to_string(),
                    profile.3.to_string(),
                    list.len().to_string(),
                    list.iter()
                        .map(|r| &r.municipality)
                        .collect::<BTreeSet<_>>()
                        .len()
                        .to_string(),
                    list.iter()
                        .map(|r| &r.local)
                        .collect::<BTreeSet<_>>()
                        .len()
                        .to_string(),
                ])?;
            }
        }
        w.flush()?;
        Ok(())
    })?;
    let correlations:Vec<Value>=raw_correlations.into_iter().enumerate().map(|(scope,values)|json!({"scope":if scope==0{"BR".to_string()}else{ufs[scope-1].clone()},"metrics":values.iter().enumerate().map(|(j,a)|{let den=((a[0]*a[3]-a[1]*a[1])*(a[0]*a[4]-a[2]*a[2])).max(0.0).sqrt();json!({"variable":stats::METRICS[j],"n":a[0] as u64,"pearson_13":if den>0.0{Some((a[0]*a[5]-a[1]*a[2])/den)}else{None}})}).collect::<Vec<_>>()})).collect();
    Ok(
        json!({"sections":rows.len(),"zero_valid_sections":no_valid,"no_nominal_brt_closing":clock_missing,"zero_registered_sections":aptoszero,"full_turnout_sections":turnout100,"urn_types":types,
        "repeated_urn_identifiers":{"groups":urn_groups,"sections":urn_rows,"interpretation":"Reuso de identificador, sem deduzir hardware ou causa; arquivo conserva todas as chaves envolvidas."},
        "repeated_vote_profiles":{"groups":repeated_profiles,"sections":profile_rows,"unordered_pairs":pairs,"unique_profiles":profiles.len(),"interpretation":"Igualdade de contagens discretas é esperada em universos grandes; não equivale a clonagem de votos."},
        "fingerprint":{"uf_order":ufs,"candidate":"13; o complemento válido é 22","bins_per_axis":20,"row_axis":"comparecimento/aptos","column_axis":"votos13/válidos","last_bin_includes_one":true,"counts":cells},
        "first_significant_digit_counts":{"uf_order":ufs,"candidate_order":["13","22"],"counts":digits,"interpretation":"Descrição, sem teste de fraude por Benford."},"raw_correlations":correlations}),
    )
}

fn run(mut args: Args) -> Result<()> {
    ensure!(!args.output.exists(), "saída existente; preservar bytes");
    ensure!(
        std::fs::metadata(&args.protocol)?.len()
            <= tsepack::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?,
        "protocolo excessivo"
    );
    let raw_protocol = std::fs::read(&args.protocol)?;
    let protocol_hash = tsepack::hash::sha256_bytes(&raw_protocol);
    let mut p: Protocol = serde_json::from_slice(&raw_protocol)?;
    ensure!(
        p.format_version == 1
            && ["official_derived", "synthetic_fixture"].contains(&p.source_kind.as_str()),
        "protocolo incompatível"
    );
    ensure!(
        p.permutations > 0
            && p.permutations <= limit("MAX_STATS_REPLICATES")?
            && p.predictive_replicates > 0
            && p.predictive_replicates <= limit("MAX_STATS_REPLICATES")?,
        "réplicas fora dos limites"
    );
    ensure!(
        p.folds >= 2
            && p.folds <= limit("MAX_STATS_FOLDS")?
            && p.minimum_training_sections >= 2
            && p.size_bin_width > 0
            && p.size_bin_width <= tsepack::limits::get("MAX_STATS_COUNT_PER_SECTION")?
            && p.maximum_rho > 0.0
            && p.maximum_rho < 1.0
            && p.alpha > 0.0
            && p.alpha < 0.5,
        "parâmetros inválidos"
    );
    if let Some(path) = args.sections.take() {
        p.sections.path = path;
    }
    if let Some(path) = args.time_policy.take() {
        p.time_policy.path = path;
    }
    if let Some(path) = args.log_report.take() {
        p.log_report
            .as_mut()
            .context("protocolo não seleciona logs")?
            .path = path;
    }
    let policy: Value = serde_json::from_slice(&checked_bytes(&p.time_policy)?)?;
    let logs: Option<Value> = p
        .log_report
        .as_ref()
        .map(|s| -> Result<_> { Ok(serde_json::from_slice(&checked_bytes(s)?)?) })
        .transpose()?;
    if let Some(logs) = &logs {
        ensure!(
            logs["sections_export_sha256"] == p.sections.sha256,
            "diagnóstico de logs pertence a outra projeção"
        );
    }
    let (rows, ufs) = load_rows(&p, &policy)?;
    std::fs::create_dir(&args.output)?;
    eprintln!(
        "fontes e {} seções conferidas; ajustando modelos",
        rows.len()
    );
    let pools = Pools::fit(&rows, ufs.len(), p.folds);
    let chunks: Vec<Result<Chunk>> = rows
        .par_chunks(limit("STATS_CHUNK_SECTIONS")?)
        .map(|r| score_chunk(r, &pools, &p))
        .collect();
    let mut scores = Vec::new();
    let mut expected = [0.0; FEATURE_COUNT];
    let mut simulated = vec![[0_u64; FEATURE_COUNT]; p.predictive_replicates];
    for chunk in chunks {
        let chunk = chunk?;
        scores.extend(chunk.scores);
        for (dest, value) in expected.iter_mut().zip(chunk.expected) {
            *dest += value;
        }
        for (dest, src) in simulated.iter_mut().zip(chunk.simulated) {
            for j in 0..FEATURE_COUNT {
                dest[j] += src[j];
            }
        }
    }
    let mut logp = Vec::new();
    for s in scores.iter().flatten() {
        logp.extend(s.log_p);
    }
    let adjusted = stats::holm(&logp, logp.len());
    let mut pos = 0;
    for s in scores.iter_mut().flatten() {
        s.log_holm.copy_from_slice(&adjusted[pos..pos + 4]);
        pos += 4;
    }
    write_scores(&args.output.join("section_scores.csv"), &rows, &scores)?;
    let descriptive = descriptive(&rows, &ufs, &args.output)?;
    let observed = observed_counts(&rows);
    let obs_stats = stats::reference_statistics(&observed.map(|x| x as f64), &expected);
    let sim_stats: Vec<_> = simulated
        .iter()
        .map(|c| stats::reference_statistics(&c.map(|x| x as f64), &expected))
        .collect();
    let reference_p: Vec<f64> = (0..8)
        .map(|j| {
            stats::monte_carlo_p(
                sim_stats
                    .iter()
                    .filter(|s| s[j] + 1e-9 >= obs_stats[j])
                    .count() as u64,
                p.predictive_replicates,
            )
        })
        .collect();
    let ref_holm = stats::holm(&reference_p.iter().map(|v| v.ln()).collect::<Vec<_>>(), 8);
    publish_file(&args.output.join("predictive_replicates.csv"), |f| {
        let mut w = csv::Writer::from_writer(f);
        let mut h = vec!["replicate".to_string()];
        h.extend((0..FEATURE_COUNT).map(|i| format!("feature_{i}")));
        w.write_record(h)?;
        for (i, s) in simulated.iter().enumerate() {
            let mut r = vec![i.to_string()];
            r.extend(s.map(|v| v.to_string()));
            w.write_record(r)?;
        }
        w.flush()?;
        Ok(())
    })?;
    let mut tests = Vec::new();
    for (level, name) in [
        "municipality_size",
        "municipality_zone_size",
        "voting_place_size",
    ]
    .iter()
    .enumerate()
    {
        eprintln!("permutações: {name}, B={}", p.permutations);
        let obs: Vec<_> = rows
            .iter()
            .filter(|r| r.n > 0)
            .map(|r| Observation {
                stratum: format!(
                    "{}/{}",
                    match level {
                        0 => &r.municipality,
                        1 => &r.zone,
                        _ => &r.local,
                    },
                    r.n / p.size_bin_width
                ),
                uf: r.uf,
                x: [
                    (r.aptos > 0).then(|| r.turnout as f64 / r.aptos as f64),
                    (r.turnout > 0).then(|| r.biometric as f64 / r.turnout as f64),
                    (r.turnout > 0).then(|| r.invalid as f64 / r.turnout as f64),
                    r.closing,
                ],
                y: r.k as f64 / r.n as f64,
            })
            .collect();
        let result = stats::associations(
            &obs,
            &ufs,
            name,
            p.permutations,
            p.seed.wrapping_add(level as u64),
        );
        publish_file(&args.output.join(format!("permutations-{name}.csv")), |f| {
            let mut w = csv::Writer::from_writer(f);
            let mut h = vec!["replicate".to_string()];
            h.extend(
                result
                    .tests
                    .iter()
                    .map(|t| format!("{}:{}", t.scope, t.variable)),
            );
            w.write_record(h)?;
            for (i, r) in result.null_correlations.iter().enumerate() {
                let mut row = vec![i.to_string()];
                row.extend(r.iter().zip(&result.tests).map(|(v, t)| {
                    if t.p_mc.is_some() {
                        v.to_string()
                    } else {
                        String::new()
                    }
                }));
                w.write_record(row)?;
            }
            w.flush()?;
            Ok(())
        })?;
        tests.extend(result.tests);
    }
    let tested: Vec<_> = tests
        .iter()
        .enumerate()
        .filter_map(|(i, t)| t.p_mc.map(|v| (i, v.ln())))
        .collect();
    let adj = stats::holm(
        &tested.iter().map(|(_, p)| *p).collect::<Vec<_>>(),
        tests.len(),
    );
    for ((i, _), v) in tested.iter().zip(adj) {
        tests[*i].p_holm = Some(v.exp());
    }
    write_json(&args.output.join("associations.json"), &tests)?;
    let model_report = report_models(&rows, &scores, &ufs, &p);
    write_json(&args.output.join("models.json"), &model_report)?;
    let actual_totals = json!({"registered":rows.iter().map(|r|r.aptos).sum::<u64>(),"turnout":rows.iter().map(|r|r.turnout).sum::<u64>(),"biometric":rows.iter().map(|r|r.biometric).sum::<u64>(),"votes_13":rows.iter().map(|r|r.k).sum::<u64>(),"votes_22":rows.iter().map(|r|r.n-r.k).sum::<u64>(),"invalid":rows.iter().map(|r|r.invalid).sum::<u64>()});
    let associations_rejected = tests
        .iter()
        .filter(|t| t.p_holm.is_some_and(|v| v <= p.alpha))
        .count();
    let mut files = BTreeMap::new();
    for entry in std::fs::read_dir(&args.output)? {
        let entry = entry?;
        let path = entry.path();
        files.insert(
            entry.file_name().to_string_lossy().to_string(),
            json!({"bytes":entry.metadata()?.len(),"sha256":tsepack::hash::sha256_file(&path)?}),
        );
    }
    let report = json!({"format_version":1,"execution_success":true,"source_kind":p.source_kind,"protocol_sha256":protocol_hash,"effective_protocol":p,"time_policy":policy,
        "integrity_controls_passed":true,"log_reconciliation_passed":logs.as_ref().and_then(|r|r["success"].as_bool()),"log_diagnostics_preserved":logs,
        "totals":actual_totals,"descriptive":descriptive,"models":model_report,
        "association_family":{"planned_tests":tests.len(),"testable_tests":tested.len(),"holm_rejections":associations_rejected,"minimum_mc_p":1.0/(p.permutations+1) as f64,"interpretation":"Associação bilateral residual sob intercambialidade dentro dos estratos; não atribui causa nem voto individual."},
        "predictive_reference":{"scope":"Seções independentes sob parâmetros congelados ajustados fora do fold; probabilidades nominais de discrepância de modelo, não teste calibrado de fraude.","feature_order":["unanimity13","unanimity22","gt90_13","gt90_22","exact5percent13","exact5percent22","last_digit13_0..9","last_digit22_0..9"],"observed_counts":observed.as_slice(),"expected_counts":expected.as_slice(),"statistic_order":["unanimity13","unanimity22","gt90_13","gt90_22","exact5percent13","exact5percent22","last_digit_chisq13","last_digit_chisq22"],"observed_statistics":obs_stats,"mc_tail_fraction":reference_p,"holm_nominal_tail_fraction":ref_holm.iter().map(|v|v.exp()).collect::<Vec<_>>()},
        "artifacts":files,"limitations":["Exploratória; dados e resultados descritivos anteriores já eram conhecidos.","Não há calibração física de relógios, validação de assinaturas ou observação independente do voto.","Intercambialidade condicional e independência do modelo preditivo são pressupostos que podem falhar; modelos podem produzir alertas por heterogeneidade legítima.","Parâmetros estimados têm incerteza e dependência; as réplicas congeladas não refazem todo o ajuste.","O protocolo não estima probabilidade de fraude, total de votos irregulares ou autenticidade eleitoral."]});
    write_json(&args.output.join("report.json"), &report)?;
    eprintln!(
        "execução concluída; {} associações passam Holm sob os pressupostos declarados",
        associations_rejected
    );
    Ok(())
}
fn main() {
    if let Err(error) = run(Args::parse()) {
        eprintln!("bateria reprovada: {error:#}");
        std::process::exit(1);
    }
}
