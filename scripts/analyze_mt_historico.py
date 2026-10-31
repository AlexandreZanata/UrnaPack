#!/usr/bin/env python3
"""Análise histórica MT 2000-2026 (descritiva, sem alegar fraude/autenticidade).

Percorre /data/urnapack/brutos/<ano>/MT/*.zip (e legado 2026/t1/MT),
lê cada membro CSV em streaming (Latin-1, ';'), sem converter identificadores,
sem deduplicar, sem presumir layout único:

- registra header, fingerprint, registros, colunas presentes/ausentes;
- se QT_VOTOS + chave de cargo/turno existirem: soma votos por ano/turno/cargo;
- se QT_APTOS/QT_COMPARECIMENTO/QT_ABSTENCOES existirem: verifica
  aptos=comp+abst por linha, conta falhas, agrega contexto uma vez por
  grupo seção/cargo (igualdade verificada), e confronta soma votos do grupo
  vs comparecimento (flag, não bloqueio);
- cobertura observada: municípios, zonas, seções, cargos, turnos;
- flags de anomalia observada (não conclusão): zeros, 100% abstenção,
  votos>aptos no grupo, duplicatas de ocorrência, divergência de contexto.

Saídas: relatorios-locais/mt-historico/analysis.json + REPORT.md.
Limites de scripts/limits.env. Falha explícita, nunca dado fictício.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from acquire_2026 import safe_path, relative_url, check_pinned
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from map_raw_data import KNOWN_LAYOUTS  # noqa: E402  cabeçalhos canônicos

SENTINELS = {"#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", ""}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_limits():
    vals = {}
    with open(ROOT / "limits.env", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip()
    return vals


def fingerprint(header):
    return hashlib.sha256(
        json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def analyze_member(zf, info, limits):
    if info.file_size > int(limits["MAX_ZIP_MEMBER_BYTES"]):
        raise ValueError("MAX_ZIP_MEMBER_BYTES excedido")
    raw = zf.read(info)
    member_sha = hashlib.sha256(raw).hexdigest()
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="latin-1", newline="")
    reader = csv.reader(text, delimiter=";", quotechar='"', doublequote=True, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        return {"member": info.filename, "error": "csv_vazio", "records": 0}
    if len(header) != len(set(header)) or len(header) > int(limits["MAX_CSV_FIELDS"]):
        raise ValueError("cabeçalho duplicado ou excessivo")
    cols = {name: idx for idx, name in enumerate(header)}
    if "QT_VOTOS" in cols and (not {"CD_ELEICAO", "NR_TURNO", "NR_VOTAVEL"}.issubset(cols)
            or not ({"CD_CARGO", "CD_CARGO_PERGUNTA"} & set(cols))):
        raise ValueError("votos sem identificadores suficientes; agregação bloqueada")
    result = {
        "member": info.filename,
        "header": header,
        "fingerprint": fingerprint(header),
        "records": 0,
        "has_qt_votos": "QT_VOTOS" in cols,
        "has_context": all(
            c in cols for c in ("QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES")
        ),
    }
    # Unidade comparável exige eleição (CD_ELEICAO), não só cargo/turno:
    # o mesmo arquivo pode misturar pleitos (ex.: votação 2018 contém
    # 297 regular + 438 suplementar). Sem CD_ELEICAO, a agregação por
    # cargo/turno mistura universos distintos.
    votes_by_eleicao = collections.Counter()
    arithmetic_fail = 0
    arithmetic_ok = 0
    occurrences = {}
    dup = rep = conf = 0
    contexts = {}
    ctx_div = 0
    votes_per_group = collections.Counter()
    flags = collections.Counter()
    turnos = set()
    cargos = set()
    municipios = set()
    zonas = set()

    occ_fields = [c for c in ("ANO_ELEICAO", "CD_PLEITO", "CD_ELEICAO", "NR_TURNO", "SG_UF",
                              "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
                              "CD_CARGO", "NR_VOTAVEL") if c in cols]
    ctx_fields = [c for c in ("ANO_ELEICAO", "CD_PLEITO", "CD_ELEICAO", "NR_TURNO", "SG_UF",
                              "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
                              "CD_CARGO") if c in cols]

    for row in reader:
        if len(row) != len(header):
            raise ValueError("largura divergente; agregação do membro bloqueada")
        result["records"] += 1
        if result["records"] > int(limits["MAX_CSV_RECORDS"]):
            raise ValueError("MAX_CSV_RECORDS excedido; agregação bloqueada")
        get = lambda name: row[cols[name]] if name in cols else ""

        if "NR_TURNO" in cols:
            turnos.add(get("NR_TURNO"))
        cargo = get("CD_CARGO_PERGUNTA") or get("CD_CARGO")
        if cargo:
            cargos.add(cargo)
        if "CD_MUNICIPIO" in cols:
            municipios.add(get("CD_MUNICIPIO"))
        if "NR_ZONA" in cols and "CD_MUNICIPIO" in cols:
            zonas.add((get("CD_MUNICIPIO"), get("NR_ZONA")))

        # votos por (eleição, turno, cargo) — sem misturar pleitos
        if "QT_VOTOS" in cols:
            try:
                votos = int(get("QT_VOTOS"))
                if votos < 0:
                    raise ValueError("QT_VOTOS negativo")
                else:
                    turno = get("NR_TURNO") or "?"
                    eleicao = get("CD_ELEICAO") or "?"
                    votes_by_eleicao[(eleicao, turno, cargo or "?")] += votos
            except ValueError:
                raise ValueError("QT_VOTOS inválido; agregação bloqueada")

        # contexto aritmético
        if result["has_context"]:
            try:
                aptos = int(get("QT_APTOS"))
                comp = int(get("QT_COMPARECIMENTO"))
                abst = int(get("QT_ABSTENCOES"))
            except ValueError:
                raise ValueError("contexto não numérico; agregação bloqueada")
            if min(aptos, comp, abst) < 0:
                raise ValueError("contexto negativo; agregação bloqueada")
            if comp + abst == aptos:
                arithmetic_ok += 1
            else:
                arithmetic_fail += 1
            if aptos == 0:
                flags["grupo_zero_aptos_linha"] += 1
            if aptos > 0 and abst == aptos:
                flags["linha_100_abstencao"] += 1

        # ocorrência e contexto só fazem sentido para bweb/votação
        # (exigem QT_VOTOS ou QT_APTOS; CESP/CEFT têm outra granularidade).
        interpretable = result["has_qt_votos"] or result["has_context"]
        if occ_fields and interpretable:
            key = tuple(get(c) for c in occ_fields)
            digest = hashlib.sha256(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()
            if key in occurrences:
                dup += 1
                if occurrences[key] == digest:
                    rep += 1
                else:
                    conf += 1
            else:
                occurrences[key] = digest
                if len(occurrences) > int(limits["MAX_BWEB_OCCURRENCE_KEYS"]):
                    raise ValueError("MAX_BWEB_OCCURRENCE_KEYS excedido")

        # contexto uma vez por grupo
        if ctx_fields and result["has_context"]:
            key = tuple(get(c) for c in ctx_fields)
            entry = contexts.get(key)
            current = (get("QT_APTOS"), get("QT_COMPARECIMENTO"), get("QT_ABSTENCOES"))
            if entry is None:
                contexts[key] = {"context": current, "votes": 0}
                if len(contexts) > int(limits["MAX_BWEB_OCCURRENCE_KEYS"]):
                    raise ValueError("limite de contextos excedido")
            else:
                if entry["context"] != current:
                    ctx_div += 1
                    entry["divergent"] = True
            if "QT_VOTOS" in cols:
                try:
                    contexts[key]["votes"] += int(get("QT_VOTOS"))
                except ValueError:
                    pass

    # confronto votos do grupo vs comparecimento.
    # Regra conhecida: Senador pode ter 2 vagas (votos=2×comparecimento);
    # conta como observação, não como erro — exige confronto com documentação
    # oficial do pleito antes de qualquer inferência.
    votos_vs_comp_divergentes = 0
    votos_maior_aptos = 0
    votos_dobro_comp_grupos = 0
    for key, entry in contexts.items():
        if entry.get("divergent"):
            continue
        try:
            aptos, comp, _ = (int(v) for v in entry["context"])
        except ValueError:
            continue
        if entry["votes"] != comp:
            votos_vs_comp_divergentes += 1
            if comp > 0 and entry["votes"] == 2 * comp:
                votos_dobro_comp_grupos += 1
        if entry["votes"] > aptos:
            votos_maior_aptos += 1

    result.update({
        "member_sha256": member_sha,
        "bytes": len(raw),
        "turnos": sorted(turnos),
        "cargos": sorted(cargos),
        "municipios": len(municipios),
        "zonas": len(zonas),
        "votes_by_eleicao_turno_cargo": [
            {"eleicao": eleicao, "turno": turno, "cargo": cargo, "votos": votos}
            for (eleicao, turno, cargo), votos in sorted(votes_by_eleicao.items())
        ],
        "arithmetic_ok": arithmetic_ok,
        "arithmetic_fail": arithmetic_fail,
        "duplicates": dup,
        "repeated": rep,
        "conflicts": conf,
        "context_groups": len(contexts),
        "context_divergent_groups": ctx_div,
        "grupos_votos_vs_comparecimento_divergentes": votos_vs_comp_divergentes,
        "grupos_votos_igual_dobro_comparecimento": votos_dobro_comp_grupos,
        "grupos_votos_maior_aptos": votos_maior_aptos,
        "flags": dict(sorted(flags.items())),
        "aggregation_complete": True,
        "quality_approved": arithmetic_fail == 0 and dup == 0 and ctx_div == 0,
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--brutos")
    source.add_argument("--catalog", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", default="relatorios-locais/mt-historico-v2")
    args = parser.parse_args()
    limits = load_limits()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=False)

    files = []
    fixed_by_path = {}
    catalog_reference = None
    if args.catalog:
        if args.root is None:
            raise ValueError("--catalog exige --root")
        raw_catalog=args.catalog.read_bytes();fixed=json.loads(raw_catalog)
        if fixed.get("format_version")!=1 or len({i["url"] for i in fixed["items"]})!=len(fixed["items"]):
            raise ValueError("catálogo inválido/duplicado")
        for item in fixed["items"]:
            if relative_url(item["url"])!=item["path"] or not {"expected_bytes","expected_sha256"}.issubset(item):
                raise ValueError("catálogo sem fixação ou caminho divergente")
            if item["url"].lower().endswith(".zip"):
                path=safe_path(args.root,item["path"])
                if path in fixed_by_path:
                    raise ValueError("colisão de caminho no catálogo")
                fixed_by_path[path]=item;files.append(path)
        catalog_reference={"path":str(args.catalog),"bytes":len(raw_catalog),"sha256":hashlib.sha256(raw_catalog).hexdigest(),
            "selected_zip_resources":len(files),"nonzip_resources_not_aggregated":len(fixed["items"])-len(files)}
    elif args.root is not None:
        raise ValueError("--root exige --catalog")
    for year_dir in ([] if args.catalog else sorted(Path(args.brutos or "/data/urnapack/brutos").glob("[12]*"))):
        mt = year_dir / "MT"
        legacy = year_dir / "t1" / "MT"
        for base in (mt, legacy):
            if not base.is_dir():
                continue
            for path in sorted(base.glob("*.zip")):
                if path.suffixes[-2:] == [".zip", ".sha512"] or path.name.endswith((".sha512", ".sha1")):
                    continue
                files.append(path)
    # Caminhos repetidos por conteúdo continuam no relatório, com alias explícito.
    seen_sha = {}
    unique = []
    for path in files:
        try:
            digest = sha256_file(str(path))
            if path in fixed_by_path:
                check_pinned(fixed_by_path[path],{"bytes":path.stat().st_size,"sha256":digest})
        except OSError as exc:
            print(f"leitura {path}: {exc}", file=sys.stderr)
            return 2
        if digest in seen_sha:
            print(f"conteúdo repetido preservado: {path} (= {seen_sha[digest]})")
        seen_sha[digest] = str(path)
        unique.append(path)

    report = {"format_version": 2, "files": [], "errors": [], "archive_members": [], "success": False,
              "source_catalog":catalog_reference}
    if not unique:
        report["errors"].append("nenhum ZIP selecionado; não aprovar execução vazia")
    for path in unique:
        try:
            zip_sha = sha256_file(str(path))
            size = path.stat().st_size
            if size > int(limits["MAX_SOURCE_FILE_BYTES"]):
                raise ValueError("MAX_SOURCE_FILE_BYTES excedido")
        except (OSError, ValueError) as exc:
            report["errors"].append(f"{path}: {exc}")
            continue
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            report["errors"].append(f"{path}: zip inválido ({exc})")
            continue
        with zf:
            infos = zf.infolist()
            report["archive_members"].append({"zip": str(path), "zip_sha256": zip_sha,
                "members": [{"ordinal": n, "name": i.filename, "bytes": i.file_size, "crc32": f"{i.CRC:08x}"} for n, i in enumerate(infos)]})
            if len(infos) > int(limits["MAX_ZIP_MEMBERS"]) or len({i.filename for i in infos}) != len(infos):
                report["errors"].append(f"{path}: índice excessivo ou nomes repetidos; sem selecionar membro por nome")
                continue
            for info in infos:
                if info.is_dir() or not info.filename.lower().endswith((".csv", ".txt")):
                    continue
                # .txt antigos sem cabeçalho: cataloga sem interpretar como votacao/bweb
                if info.filename.lower().endswith(".txt"):
                    if info.file_size > int(limits["MAX_ZIP_MEMBER_BYTES"]):
                        report["errors"].append(f"{path}#{info.filename}: tamanho excedido")
                        continue
                    raw = zf.read(info)
                    report["files"].append({
                        "zip": str(path),
                        "zip_sha256": zip_sha,
                        "zip_bytes": size,
                        "member": info.filename,
                        "member_sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                        "records": None,
                        "layout": "txt_sem_cabecalho_presumido",
                        "nota": "variante antiga sem cabeçalho canônico; bytes preservados, sem agregação automática",
                    })
                    continue
                try:
                    member = analyze_member(zf, info, limits)
                except Exception as exc:  # falha explícita por membro
                    report["errors"].append(f"{path}#{info.filename}: {exc}")
                    continue
                member.update({"zip": str(path), "zip_sha256": zip_sha, "zip_bytes": size})
                report["files"].append(member)
                if member.get("error") or member.get("quality_approved") is False:
                    report["errors"].append(f"{path}#{info.filename}: controles do membro reprovados")
                print(f"{path.name}#{info.filename}: {member.get('records')} registros")

    report["success"] = not report["errors"]
    with open(out_dir / "analysis.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    # REPORT.md legível
    lines = ["# MT 2000-2026 — descritiva e inconsistências observadas", "",
             "Sem conclusão de fraude/autenticidade. Flags são observações que exigem confronto com fonte/documentação.",
             "", f"Arquivos ZIP selecionados (inclusive conteúdo repetido): {len(unique)}; membros analisados: {len(report['files'])}.",
             "", "| arquivo | membro | registros | turnos | cargos | municípios | aritmética falha | duplicatas | ctx divergentes | votos≠comp grupos |",
             "|---|---|---:|---|---|---:|---:|---:|---:|---:|"]
    for item in sorted(report["files"], key=lambda x: (x.get("zip", ""), x.get("member", ""))):
        if item.get("records") is None:
            lines.append(f"| {Path(item['zip']).name} | {item['member']} | n/a (txt) | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {Path(item['zip']).name} | {item['member']} | {item['records']} "
            f"| {','.join(item.get('turnos', [])) or '—'} | {','.join(item.get('cargos', [])) or '—'} "
            f"| {item.get('municipios')} | {item.get('arithmetic_fail', '—')} | {item.get('duplicates', '—')} "
            f"| {item.get('context_divergent_groups', '—')} | {item.get('grupos_votos_vs_comparecimento_divergentes', '—')} |"
        )
    if report["errors"]:
        lines += ["", "## Erros (falha explícita, sem dado silencioso)", ""]
        lines += [f"- {e}" for e in report["errors"][:50]]
    lines += ["", "## Limitações e leitura das flags",
              "- Layouts variam por ano (bweb .txt 31-32 cols 2012-2016 sem cabeçalho, bweb 42 cols 2018, bweb 45 cols 2020-2026; votação 23 vs 26 cols).",
              "- .txt antigos preservados sem agregação automática.",
              "- Votos somados por votável; contexto contado uma vez por grupo seção/cargo; cargos diferentes nunca somados em eleitores.",
              "- Senador com 2 vagas soma 2×comparecimento por grupo (ex.: 2026 e 2018); `votos=2×comp` é observação de regra eleitoral, não inconsistência.",
              "- `votos≠comp` fora dessa regra, aritmética `aptos≠comp+abst`, duplicatas e divergências de contexto são observações que exigem confronto com fonte/documentação; nenhuma conclui fraude/autenticidade.",
              "- Segundo turno parcial conforme acervo; ausência no disco não prova inexistência no universo."]
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Diagnóstico: {len(report['files'])} membros, erros={len(report['errors'])}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
