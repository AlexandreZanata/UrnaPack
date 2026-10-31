//! Ferramentas da bateria exploratória. Probabilidade de modelo não é de fraude.
use anyhow::{ensure, Result};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use statrs::function::beta::checked_ln_beta;
use std::collections::BTreeMap;

pub const SECTION_HEADER: [&str; 21] = [
    "ANO_ELEICAO",
    "CD_PLEITO",
    "CD_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_CARGO_PERGUNTA",
    "NR_LOCAL_VOTACAO",
    "NR_URNA_EFETIVADA",
    "DT_ENCERRAMENTO",
    "CD_TIPO_URNA",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCOES",
    "QT_ELEI_BIOM_SEM_HABILITACAO",
    "VOTOS_13",
    "VOTOS_22",
    "VOTOS_BRANCOS",
    "VOTOS_NULOS",
];
pub const METRICS: [&str; 4] = [
    "turnout_rate",
    "biometric_rate",
    "invalid_rate",
    "closing_brt_seconds",
];
pub const MODEL_NAMES: [&str; 4] = [
    "national_binomial",
    "uf_binomial",
    "municipality_binomial",
    "crossfit_municipality_beta_binomial",
];
pub const FEATURE_COUNT: usize = 26;

/// RNG de simulação reprodutível; não fornece hashes nem segurança criptográfica.
pub struct SplitMix64(pub u64);
impl SplitMix64 {
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }
    pub fn unit(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / 9007199254740992.0
    }
    pub fn index(&mut self, bound: usize) -> usize {
        assert!(bound > 0);
        let b = bound as u64;
        let threshold = b.wrapping_neg() % b;
        loop {
            let n = self.next_u64();
            if n >= threshold {
                return (n % b) as usize;
            }
        }
    }
    pub fn shuffle<T>(&mut self, values: &mut [T]) {
        for i in (1..values.len()).rev() {
            let j = self.index(i + 1);
            values.swap(i, j);
        }
    }
}

#[derive(Default, Clone, Copy, Serialize)]
pub struct Moments {
    pub sections: u64,
    pub k: u64,
    pub n: u64,
    pub sum_p: f64,
    pub sum_p2: f64,
    pub sum_inverse_n: f64,
}
impl Moments {
    pub fn add(&mut self, k: u64, n: u64) {
        assert!(n > 0 && k <= n);
        let p = k as f64 / n as f64;
        self.sections += 1;
        self.k += k;
        self.n += n;
        self.sum_p += p;
        self.sum_p2 += p * p;
        self.sum_inverse_n += 1.0 / n as f64;
    }
    pub fn without(&self, other: Self) -> Self {
        Self {
            sections: self.sections - other.sections,
            k: self.k - other.k,
            n: self.n - other.n,
            sum_p: self.sum_p - other.sum_p,
            sum_p2: self.sum_p2 - other.sum_p2,
            sum_inverse_n: self.sum_inverse_n - other.sum_inverse_n,
        }
    }
    pub fn binomial(&self) -> Model {
        Model {
            mean: (self.k as f64 + 0.5) / (self.n as f64 + 1.0),
            rho: 0.0,
        }
    }
    pub fn beta_binomial(&self, max_rho: f64) -> Model {
        assert!(self.sections > 0);
        let s = self.sections as f64;
        let raw_mean = self.sum_p / s;
        let mean = (self.sum_p + 0.5) / (s + 1.0);
        let variance = (self.sum_p2 / s - raw_mean * raw_mean).max(0.0);
        let inv = self.sum_inverse_n / s;
        let rho = if inv < 1.0 && raw_mean > 0.0 && raw_mean < 1.0 {
            ((variance / (raw_mean * (1.0 - raw_mean)) - inv) / (1.0 - inv)).clamp(0.0, max_rho)
        } else {
            0.0
        };
        Model {
            mean,
            rho: if rho < 1e-6 { 0.0 } else { rho },
        }
    }
}

#[derive(Clone, Copy, Serialize, Deserialize)]
pub struct Model {
    pub mean: f64,
    pub rho: f64,
}
impl Model {
    /// PMF inteira no log, renormalizada para remover erro de arredondamento.
    pub fn log_pmf(&self, n: usize) -> Result<Vec<f64>> {
        ensure!(
            self.mean > 0.0 && self.mean < 1.0 && self.rho >= 0.0 && self.rho < 1.0,
            "parâmetro de modelo inválido"
        );
        let mut log = vec![0.0; n + 1];
        if self.rho == 0.0 {
            log[0] = n as f64 * (-self.mean).ln_1p();
            for k in 0..n {
                log[k + 1] = log[k] + ((n - k) as f64 / (k + 1) as f64).ln() + self.mean.ln()
                    - (-self.mean).ln_1p();
            }
        } else {
            let c = 1.0 / self.rho - 1.0;
            let a = self.mean * c;
            let b = (1.0 - self.mean) * c;
            log[0] = checked_ln_beta(a, b + n as f64)? - checked_ln_beta(a, b)?;
            for k in 0..n {
                log[k + 1] = log[k] + ((n - k) as f64 / (k + 1) as f64).ln() + (a + k as f64).ln()
                    - (b + (n - k - 1) as f64).ln();
            }
        }
        ensure!(log.iter().all(|v| v.is_finite()), "PMF não finita");
        let norm = log_sum(&log);
        ensure!(norm.abs() < 1e-7, "normalização da PMF divergente: {norm}");
        for x in &mut log {
            *x -= norm;
        }
        Ok(log)
    }
}
pub fn log_sum(xs: &[f64]) -> f64 {
    let m = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if !m.is_finite() {
        return m;
    }
    m + xs.iter().map(|x| (*x - m).exp()).sum::<f64>().ln()
}
pub fn log_two_sided(log: &[f64], k: usize) -> f64 {
    (2.0_f64.ln() + log_sum(&log[..=k]).min(log_sum(&log[k..]))).min(0.0)
}

/// Holm no log. total inclui hipóteses planejadas não testáveis, sem inventar p.
pub fn holm(log_p: &[f64], total: usize) -> Vec<f64> {
    assert!(total >= log_p.len() && log_p.iter().all(|x| x.is_finite() && *x <= 0.0));
    let mut order: Vec<_> = (0..log_p.len()).collect();
    order.sort_by(|a, b| log_p[*a].total_cmp(&log_p[*b]).then(a.cmp(b)));
    let mut result = vec![0.0; log_p.len()];
    let mut largest = f64::NEG_INFINITY;
    for (i, j) in order.into_iter().enumerate() {
        largest = largest.max(log_p[j] + ((total - i) as f64).ln());
        result[j] = largest.min(0.0);
    }
    result
}
pub fn monte_carlo_p(exceedances: u64, replicates: usize) -> f64 {
    (exceedances + 1) as f64 / (replicates + 1) as f64
}

pub fn features(k: usize, n: usize) -> [u64; FEATURE_COUNT] {
    let mut v = [0; FEATURE_COUNT];
    v[0] = (k == n) as u64;
    v[1] = (k == 0) as u64;
    v[2] = (10 * k > 9 * n) as u64;
    v[3] = (10 * (n - k) > 9 * n) as u64;
    v[4] = (20 * k).is_multiple_of(n) as u64;
    v[5] = (20 * (n - k)).is_multiple_of(n) as u64;
    v[6 + k % 10] = 1;
    v[16 + (n - k) % 10] = 1;
    v
}
pub fn chi_square(observed: &[f64], expected: &[f64]) -> Result<f64> {
    ensure!(
        observed.len() == expected.len(),
        "número de classes divergente"
    );
    ensure!(
        observed
            .iter()
            .chain(expected)
            .all(|v| v.is_finite() && *v >= 0.0),
        "frequência inválida"
    );
    ensure!(
        observed
            .iter()
            .zip(expected)
            .all(|(o, e)| *e > 0.0 || *o == 0.0),
        "expectativa numérica zero com observação positiva; revisar suporte/underflow"
    );
    Ok(observed
        .iter()
        .zip(expected)
        .map(|(o, e)| if *e > 0.0 { (o - e).powi(2) / e } else { 0.0 })
        .sum())
}
pub fn reference_statistics(
    counts: &[f64; FEATURE_COUNT],
    expected: &[f64; FEATURE_COUNT],
) -> Result<[f64; 8]> {
    let mut s = [0.0; 8];
    for i in 0..6 {
        s[i] = (counts[i] - expected[i]).abs();
    }
    s[6] = chi_square(&counts[6..16], &expected[6..16])?;
    s[7] = chi_square(&counts[16..26], &expected[16..26])?;
    Ok(s)
}

#[derive(Clone)]
pub struct Observation {
    pub stratum: String,
    pub uf: usize,
    pub x: [Option<f64>; 4],
    pub y: f64,
}
#[derive(Serialize)]
pub struct AssociationTest {
    pub stratum_level: String,
    pub scope: String,
    pub variable: String,
    pub available_sections: u64,
    pub permutable_sections: u64,
    pub partial_pearson_13: Option<f64>,
    pub partial_pearson_22: Option<f64>,
    pub p_mc: Option<f64>,
    pub p_holm: Option<f64>,
    pub status: String,
}
pub struct AssociationRun {
    pub tests: Vec<AssociationTest>,
    pub null_correlations: Vec<Vec<f64>>,
}

pub fn associations(
    data: &[Observation],
    ufs: &[String],
    level: &str,
    replicates: usize,
    seed: u64,
) -> AssociationRun {
    // Padrão de ausência também condicionado: nunca imputar horário ao exterior.
    let mut map: BTreeMap<(String, u8), Vec<&Observation>> = BTreeMap::new();
    for row in data {
        let mask = row
            .x
            .iter()
            .enumerate()
            .fold(0_u8, |m, (j, x)| m | ((x.is_some() as u8) << j));
        map.entry((row.stratum.clone(), mask))
            .or_default()
            .push(row);
    }
    let scopes = ufs.len() + 1;
    let mut available = vec![[0; 4]; scopes];
    let mut permutable = available.clone();
    let mut xv = vec![[0.0; 4]; scopes];
    let mut yv = xv.clone();
    let mut observed = xv.clone();
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut groups = Vec::new();
    for ((_, mask), rows) in map {
        let uf = rows[0].uf + 1;
        let len = rows.len();
        let my = if rows.iter().all(|r| r.y == rows[0].y) {
            rows[0].y
        } else {
            rows.iter().map(|r| r.y).sum::<f64>() / len as f64
        };
        let mx: [f64; 4] = std::array::from_fn(|j| {
            if rows.iter().all(|r| r.x[j] == rows[0].x[j]) {
                rows[0].x[j].unwrap_or(0.0)
            } else {
                rows.iter().map(|r| r.x[j].unwrap_or(0.0)).sum::<f64>() / len as f64
            }
        });
        let start = xs.len();
        for r in rows {
            let y = r.y - my;
            let x: [f64; 4] = std::array::from_fn(|j| {
                if mask & (1 << j) != 0 {
                    r.x[j].unwrap() - mx[j]
                } else {
                    0.0
                }
            });
            for j in 0..4 {
                if mask & (1 << j) != 0 {
                    available[uf][j] += 1;
                    if len > 1 {
                        permutable[uf][j] += 1;
                    }
                    xv[uf][j] += x[j] * x[j];
                    yv[uf][j] += y * y;
                    observed[uf][j] += x[j] * y;
                }
            }
            xs.push(x);
            ys.push(y);
        }
        if len > 1 {
            groups.push((start, xs.len(), uf));
        }
    }
    for s in 1..scopes {
        for j in 0..4 {
            available[0][j] += available[s][j];
            permutable[0][j] += permutable[s][j];
            xv[0][j] += xv[s][j];
            yv[0][j] += yv[s][j];
            observed[0][j] += observed[s][j];
        }
    }
    let denominator: Vec<[f64; 4]> = xv
        .iter()
        .zip(&yv)
        .map(|(x, y)| std::array::from_fn(|j| (x[j] * y[j]).sqrt()))
        .collect();
    let null_correlations: Vec<Vec<f64>> = (0..replicates)
        .into_par_iter()
        .map(|b| {
            let mut rng =
                SplitMix64(seed.wrapping_add((b as u64).wrapping_mul(0xd1342543de82ef95)));
            let mut perm = ys.clone();
            let mut sums = vec![[0.0; 4]; scopes];
            for &(start, end, uf) in &groups {
                rng.shuffle(&mut perm[start..end]);
                for i in start..end {
                    for j in 0..4 {
                        sums[uf][j] += xs[i][j] * perm[i];
                    }
                }
            }
            for s in 1..scopes {
                let current = sums[s];
                for (dest, value) in sums[0].iter_mut().zip(current) {
                    *dest += value;
                }
            }
            (0..scopes)
                .flat_map(|s| {
                    let sums = &sums;
                    let d = &denominator;
                    (0..4).map(move |j| {
                        if d[s][j] > 0.0 {
                            sums[s][j] / d[s][j]
                        } else {
                            0.0
                        }
                    })
                })
                .collect()
        })
        .collect();
    let mut tests = Vec::new();
    for s in 0..scopes {
        for j in 0..4 {
            let r = (denominator[s][j] > 0.0).then(|| observed[s][j] / denominator[s][j]);
            let p = r.map(|r| {
                monte_carlo_p(
                    null_correlations
                        .iter()
                        .filter(|v| v[s * 4 + j].abs() + 1e-12 >= r.abs())
                        .count() as u64,
                    replicates,
                )
            });
            tests.push(AssociationTest {
                stratum_level: level.into(),
                scope: if s == 0 {
                    "BR".into()
                } else {
                    ufs[s - 1].clone()
                },
                variable: METRICS[j].into(),
                available_sections: available[s][j],
                permutable_sections: permutable[s][j],
                partial_pearson_13: r,
                partial_pearson_22: r.map(|x| -x),
                p_mc: p,
                p_holm: None,
                status: if r.is_some() {
                    "conditional_exchangeability_test"
                } else {
                    "not_testable_zero_variance_or_no_coverage"
                }
                .into(),
            });
        }
    }
    AssociationRun {
        tests,
        null_correlations,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_binomial_enumeration_and_tails() {
        let p = Model {
            mean: 0.5,
            rho: 0.0,
        }
        .log_pmf(4)
        .unwrap();
        for (a, b) in p.iter().zip([1., 4., 6., 4., 1.]) {
            assert!((a.exp() - b / 16.).abs() < 1e-12);
        }
        assert!((log_two_sided(&p, 0).exp() - 0.125).abs() < 1e-12);
    }
    #[test]
    fn beta_binomial_uniform_and_candidate_symmetry() {
        for n in [1, 10, 100, 930] {
            let p = Model {
                mean: 0.5,
                rho: 1.0 / 3.0,
            }
            .log_pmf(n)
            .unwrap();
            assert!(p
                .iter()
                .all(|v| (v.exp() - 1.0 / (n + 1) as f64).abs() < 1e-10));
            let a = Model {
                mean: 0.8,
                rho: 0.03,
            }
            .log_pmf(n)
            .unwrap();
            let b = Model {
                mean: 0.2,
                rho: 0.03,
            }
            .log_pmf(n)
            .unwrap();
            for k in 0..=n {
                assert!((log_two_sided(&a, k) - log_two_sided(&b, n - k)).abs() < 1e-8);
            }
        }
    }
    #[test]
    fn underflow_is_retained_as_finite_log() {
        let p = Model {
            mean: 0.001,
            rho: 0.0,
        }
        .log_pmf(930)
        .unwrap();
        let v = log_two_sided(&p, 930);
        assert!(v < -6000.0 && v.is_finite());
    }
    #[test]
    fn holm_known_solution_and_dependence() {
        let p = [0.01_f64, 0.04, 0.03, 0.2];
        let a = holm(&p.map(f64::ln), 4);
        for (v, e) in a.iter().zip([0.04, 0.09, 0.09, 0.2]) {
            assert!((v.exp() - e).abs() < 1e-12);
        }
        assert!(holm(&[(-10000.0_f64)], 1)[0].is_finite());
    }
    #[test]
    fn monte_carlo_never_claims_zero() {
        assert_eq!(monte_carlo_p(0, 999), 0.001);
        assert_eq!(monte_carlo_p(999, 999), 1.0);
    }

    #[test]
    fn chi_square_never_silently_drops_positive_mass_in_zero_expected_bin() {
        assert!(chi_square(&[1.0], &[0.0])
            .unwrap_err()
            .to_string()
            .contains("zero"));
        assert!(chi_square(&[1.0, 2.0], &[1.0]).is_err());
        assert!(chi_square(&[f64::NAN], &[1.0]).is_err());
    }
    #[test]
    fn chi_square_accepts_empty_support_cells_with_both_counts_zero() {
        assert_eq!(chi_square(&[0.0, 3.0], &[0.0, 2.0]).unwrap(), 0.5);
    }
    #[test]
    fn injected_association_detected_and_reproducible() {
        let data: Vec<_> = (0..32)
            .map(|i| Observation {
                stratum: "synthetic".into(),
                uf: 0,
                x: [Some(i as f64); 4],
                y: i as f64 / 32.0,
            })
            .collect();
        let a = associations(&data, &["SYNTHETIC".into()], "synthetic", 199, 1);
        let b = associations(&data, &["SYNTHETIC".into()], "synthetic", 199, 1);
        assert_eq!(a.null_correlations, b.null_correlations);
        assert_eq!(a.tests[0].p_mc, Some(0.005));
        assert!((a.tests[0].partial_pearson_13.unwrap() - 1.).abs() < 1e-12);
        let mut inverse = data.clone();
        for row in &mut inverse {
            row.y = 1. - row.y;
        }
        let inv = associations(&inverse, &["SYNTHETIC".into()], "synthetic", 199, 1);
        assert_eq!(a.tests[0].p_mc, inv.tests[0].p_mc);
    }
    #[test]
    fn zero_variance_and_singletons_are_not_significance() {
        let data: Vec<_> = (0..8)
            .map(|i| Observation {
                stratum: format!("synthetic-{i}"),
                uf: 0,
                x: [Some(i as f64); 4],
                y: i as f64,
            })
            .collect();
        let a = associations(&data, &["SYNTHETIC".into()], "synthetic", 9, 3);
        assert!(a
            .tests
            .iter()
            .all(|t| t.p_mc.is_none() && t.permutable_sections == 0));
    }
    #[test]
    fn apparent_geographic_effect_vanishes_after_conditioning() {
        let data: Vec<_> = (0..20)
            .map(|i| Observation {
                stratum: format!("synthetic-{}", i / 10),
                uf: 0,
                x: [Some((i / 10) as f64); 4],
                y: (i / 10) as f64,
            })
            .collect();
        assert!(
            associations(&data, &["SYNTHETIC".into()], "synthetic", 9, 3)
                .tests
                .iter()
                .all(|t| t.p_mc.is_none())
        );
    }
    #[test]
    fn folds_training_excludes_held_out_counts() {
        let mut all = Moments::default();
        all.add(10, 10);
        all.add(0, 10);
        let mut held = Moments::default();
        held.add(10, 10);
        let train = all.without(held);
        assert_eq!(train.k, 0);
        assert_eq!(train.sections, 1);
    }

    #[test]
    fn small_exact_permutation_reference_and_decimal_constant() {
        let data: Vec<_> = (0..3)
            .map(|i| Observation {
                stratum: "synthetic".into(),
                uf: 0,
                x: [Some(i as f64); 4],
                y: i as f64,
            })
            .collect();
        let r = associations(&data, &["SYNTHETIC".into()], "synthetic", 5999, 123);
        // Duas das seis permutações têm |r|=1: p exato bilateral=1/3.
        assert!((r.tests[0].p_mc.unwrap() - 1.0 / 3.0).abs() < 0.03);
        let data: Vec<_> = (0..17)
            .map(|i| Observation {
                stratum: "synthetic".into(),
                uf: 0,
                x: [Some(0.1); 4],
                y: i as f64,
            })
            .collect();
        assert!(
            associations(&data, &["SYNTHETIC".into()], "synthetic", 9, 123)
                .tests
                .iter()
                .all(|t| t.p_mc.is_none())
        );
    }
    #[test]
    fn null_control_does_not_flag_every_synthetic_dataset() {
        let mut rng = SplitMix64(891);
        let mut hits = 0;
        for repeat in 0..100 {
            let mut y: Vec<_> = (0..16).collect();
            rng.shuffle(&mut y);
            let data: Vec<_> = y
                .iter()
                .enumerate()
                .map(|(i, y)| Observation {
                    stratum: "synthetic".into(),
                    uf: 0,
                    x: [Some(i as f64); 4],
                    y: *y as f64,
                })
                .collect();
            let result = associations(&data, &["SYNTHETIC".into()], "synthetic", 199, repeat + 700);
            hits += (result.tests[0].p_mc.unwrap() <= 0.05) as usize;
        }
        // Há falsos positivos estocásticos; não se exige zero, e não são votos observados.
        assert!(hits <= 16, "calibração sintética excessiva: {hits}/100");
    }
}
