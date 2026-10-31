#!/usr/bin/env python3
"""Executa importações independentes por UF; preserva cada falha e recibo.

Não transforma uma cobertura parcial em resultado nacional. A consolidação
analítica e suas somas são feitas pelo binário Rust, em etapa separada.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys

from acquire_2026 import limits_at, write_json

UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ".split()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "catalog", "sections", "export-receipt", "policy", "out-root", "zero-sections"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--binary", type=Path, default=Path("target/release/audit_logs_2026"))
    p.add_argument("--limits", type=Path, default=Path(__file__).with_name("limits.env"))
    p.add_argument("--ufs", nargs="+", default=UFS, choices=UFS)
    args = p.parse_args()
    if len(set(args.ufs)) != len(args.ufs):
        raise ValueError("UF repetida no lote")
    values = limits_at(args.limits)
    workers = None
    for line in args.limits.read_text().splitlines():
        if line.startswith("AUDIT_LOG_WORKERS="):
            workers = int(line.split("=", 1)[1])
    if not workers or workers <= 0 or workers > values["AUDIT_FETCH_WORKERS"]:
        raise ValueError("concorrência de logs ausente ou excessiva")
    args.out_root.mkdir(parents=True, exist_ok=False)

    def run(uf):
        destination = args.out_root / uf
        command = [sys.executable, str(Path(__file__).with_name("import_logs_2026.py")), "--uf", uf,
                   "--out-dir", str(destination)]
        for name in ("root", "catalog", "sections", "export_receipt", "policy", "zero_sections", "binary", "limits"):
            command += ["--" + name.replace("_", "-"), str(getattr(args, name))]
        with (args.out_root / (uf + ".stdout.txt")).open("wb") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        return {"uf": uf, "exit_code": result.returncode, "command": command,
                "import_receipt": str(destination / "import-run.json")}

    runs = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, uf): uf for uf in args.ufs}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                result = {"uf": futures[future], "exit_code": 1, "error": f"{type(exc).__name__}: {exc}"}
            runs.append(result)
            write_json(args.out_root / "runs.json", {"format_version": 1, "expected_ufs": args.ufs,
                       "runs": sorted(runs, key=lambda run: run["uf"]), "complete": len(runs) == len(args.ufs)})
            print(result["uf"], "exit", result["exit_code"], flush=True)
    return 0 if all(run["exit_code"] == 0 for run in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
