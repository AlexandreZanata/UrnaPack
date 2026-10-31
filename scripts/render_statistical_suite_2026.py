#!/usr/bin/env python3
"""Gera relatório legível exclusivamente dos resultados medidos da bateria."""
import argparse
import json
from pathlib import Path


def number(value, digits=4):
    if value is None:
        return 'não testável'
    if isinstance(value, int):
        return f'{value:,}'.replace(',', '.')
    return f'{value:.{digits}g}'


def render(report, associations):
    if report.get('execution_success') is not True:
        raise ValueError('não apresentar execução incompleta como resultado')
    br = report['models']['scope']['BR']
    description = report['descriptive']
    family = report['association_family']
    reference = report['predictive_reference']
    lines = ['# Bateria estatística exploratória — Presidente 2026/t2', '',
        f"Natureza da entrada: **{report['source_kind']}**. Protocolo SHA-256: `{report['protocol_sha256']}`.", '',
        'Os mesmos critérios foram aplicados aos dois candidatos. Testes de troca de rótulos verificam a invariância dos scores bilaterais e das associações. Réplicas preditivas têm variação Monte Carlo e pressupostos de modelo declarados.', '',
        f"Foram preservadas **{number(description['sections'])} seções**; **{number(description['zero_valid_sections'])}** não têm válidos e permanecem fora dos scores com motivo explícito. Total de comparecimento: **{number(report['totals']['turnout'])}**.", '',
        f"Integridade estrutural aprovada: `{report['integrity_controls_passed']}`. Conciliação anterior dos logs: `{report['log_reconciliation_passed']}`. O segundo resultado não é convertido em aprovação pelos testes estatísticos.", '',
        '## Referências de extremos e sensibilidade ao modelo', '',
        'Contagens observadas: unanimidade 13/22 = **'+ '/'.join(number(v) for v in br['observed_tail_counts_order_13_unanimity_22_unanimity_13_gt90_22_gt90'][:2])+'**; estritamente >90% = **'+'/'.join(number(v) for v in br['observed_tail_counts_order_13_unanimity_22_unanimity_13_gt90_22_gt90'][2:])+'**.', '',
        '| Modelo | Unanimidade esperada 13 / 22 | >90% esperado 13 / 22 | Alertas Holm nominais: excesso 13 / 22 |',
        '|---|---:|---:|---:|']
    for i, model in enumerate(report['models']['model_order']):
        e = br['expected_tail_counts_by_model'][i]
        flags = br['holm_nominal_flags_excess_13_excess_22_by_model'][i]
        lines.append(f"| {model} | {number(e[0])} / {number(e[1])} | {number(e[2])} / {number(e[3])} | {number(flags[0])} / {number(flags[1])} |")
    lines += ['', 'A diferença entre esses modelos mede sensibilidade à referência adotada. Binomial homogênea não é um modelo suficiente da composição social das seções. Alertas preditivos continuam nominais, mesmo após Holm; parâmetros estimados e dependência podem invalidar a interpretação como p calibrado.', '',
        '## Calibração fora do fold', '',
        f"Seções válidas: {number(br['valid_sections'])}; fallback municipal→UF: {number(br['crossfit_fallback_to_uf'])}; rho médio ajustado: {number(br['crossfit_mean_rho'])}.", '',
        '| Limiar nominal bilateral | Caudas observadas | Referência N × limiar |', '|---|---:|---:|']
    for alpha, count in zip(br['crossfit_nominal_tail_levels'], br['crossfit_nominal_tail_counts']):
        lines.append(f"| {alpha:g} | {number(count)} | {number(br['valid_sections']*alpha)} |")
    lines += ['', 'Para dados discretos, a taxa nominal não é uma igualdade obrigatória. Excesso de cauda ou PIT não uniforme indica inadequação potencial do modelo; não identifica sua causa. O histograma PIT completo está em models.json para todas as UFs.', '',
        '## Associações com controle geográfico e de tamanho', '',
        f"Família planejada: **{number(family['planned_tests'])}**; testáveis: **{number(family['testable_tests'])}**; rejeições após Holm global: **{number(family['holm_rejections'])}**. Menor p de Monte Carlo representável: **{family['minimum_mc_p']:g}**. Não se afirma precisão abaixo dessa resolução.", '',
        'Os coeficientes abaixo são do candidato 13; para 22, o sinal se inverte e o teste bilateral é o mesmo. Cada linha pressupõe intercambialidade entre seções dentro do estrato. Não demonstra causalidade, voto individual ou irregularidade.', '',
        '| Estrato + faixa de válidos | Variável | Seções permutáveis | Correlação residual 13 | p MC | p Holm global |', '|---|---|---:|---:|---:|---:|']
    for t in associations:
        if t['scope'] == 'BR':
            lines.append(f"| {t['stratum_level']} | {t['variable']} | {number(t['permutable_sections'])} | {number(t['partial_pearson_13'], 6)} | {number(t['p_mc'])} | {number(t['p_holm'])} |")
    lines += ['', 'Todos os resultados por UF, inclusive os nulos e não testáveis, estão em associations.json. Todas as réplicas estão nos três CSVs de permutação. Efeito pequeno pode produzir p pequeno com muitas seções; tamanho do efeito deve acompanhar o p.', '',
        '## Dígitos, percentuais exatos e extremos sob referência preditiva', '',
        'Não se pressupõe uniformidade dos dígitos nem Benford como certificador. As réplicas usam o tamanho real de cada seção e o ajuste beta-binomial fora do fold, com parâmetros congelados e seções simuladas independentemente. As frações abaixo são diagnósticos desse modelo, sem refazer a estimação dos parâmetros.', '',
        '| Checagem global bilateral | Fração Monte Carlo | Fração corrigida por Holm, nominal |', '|---|---:|---:|']
    for name, p, adjusted in zip(reference['statistic_order'], reference['mc_tail_fraction'], reference['holm_nominal_tail_fraction']):
        lines.append(f'| {name} | {number(p)} | {number(adjusted)} |')
    urn = description['repeated_urn_identifiers']
    profiles = description['repeated_vote_profiles']
    lines += ['', '## Controles de repetição e cobertura', '',
        f"Identificadores de urna repetidos: **{number(urn['groups'])} grupos**, abrangendo **{number(urn['sections'])} seções**; todas as chaves constam de repeated_urn_identifiers.csv. Reuso de identificador não determina hardware nem causa.", '',
        f"Perfis idênticos de quatro contagens de votos: **{number(profiles['groups'])} grupos**, **{number(profiles['sections'])} seções**, **{number(profiles['unordered_pairs'])} pares**. Contagens inteiras repetem em universos grandes; isso não é sinônimo de clonagem. A lista completa está em repeated_vote_profiles.csv.", '',
        f"Sem encerramento BRT nominal utilizável: **{number(description['no_nominal_brt_closing'])}**. ZZ não recebe fuso nacional; ausência não é imputada. Seções com comparecimento igual a aptos positivos: **{number(description['full_turnout_sections'])}**.", '',
        '## Leitura dos achados', '',
        'Um desvio pode representar heterogeneidade legítima, falta de intercambialidade, inadequação do modelo, problema do arquivo ou irregularidade. A bateria não distingue automaticamente essas causas. Não estima votos fraudulentos nem probabilidade de fraude e não certifica todo o processo eleitoral.', '',
        'Os diagnósticos dos logs anteriores permanecem integralmente no report.json, com fonte fixada por hash. Assinaturas, relógios físicos, coação, demografia rural e transmissão não foram certificados por esta bateria.', '',
        '## Reprodução e rastreabilidade', '',
        'Protocolo e referências: auditoria/2026/suite/PROTOCOLO.md. Executável: statistical_suite_2026. Roteiro: scripts/reproduce_statistical_suite_2026.sh. Conferência independente: scripts/check_statistical_suite_2026.py. Todos os campos de todas as seções são confrontados; scores amostrados por hash usam uma implementação independente com math.lgamma.', '',
        'section_scores.csv conserva os 21 campos de entrada e acrescenta scores no log, correções, fold, treino e PIT. É uma transformação semântica; o pacote inclui também a projeção de entrada original para repetir os bytes e cálculos. As versões completas dos dados TSE continuam vinculadas pelos manifestos da auditoria inicial.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.result/'report.json').read_bytes())
    tests = json.loads((args.result/'associations.json').read_bytes())
    text = render(report, tests)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(text)


if __name__ == '__main__':
    main()
