"""Ejecutor headless de pruebas de estrés (Locust) para el SGR.

Envuelve el CLI de Locust en modo headless y extrae del CSV de estadísticas
las métricas de aceptación (tasa de error, p95, p99) para no depender de la
interfaz web. Solo para entornos de PRUEBAS.

Uso:
    python run_headless.py --host http://127.0.0.1:8000 \\
        --users 50 --spawn-rate 5 --run-time 5m
"""
import argparse
import csv
import subprocess
import sys
import tempfile
import os
from pathlib import Path


def _csv_of(base):
    return Path(f"{base}_stats.csv")


def main():
    ap = argparse.ArgumentParser(description="Prueba de estrés headless con Locust")
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--users", "-u", default="50")
    ap.add_argument("--spawn-rate", "-r", default="5")
    ap.add_argument("--run-time", "-t", default="5m")
    ap.add_argument("--user", default=os.getenv("LOCUST_USER", "funcionario"))
    ap.add_argument("--password", default=os.getenv("LOCUST_PASSWORD", "Demo2026!"))
    args = ap.parse_args()

    locustfile = Path(__file__).with_name("locustfile.py")
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "sgr")
        cmd = [
            sys.executable, "-m", "locust",
            "-f", str(locustfile),
            "--host", args.host,
            "--headless",
            "--users", args.users,
            "--spawn-rate", args.spawn_rate,
            "--run-time", args.run_time,
            "--csv", base,
        ]
        env = os.environ.copy()
        env["LOCUST_USER"] = args.user
        env["LOCUST_PASSWORD"] = args.password
        proc = subprocess.run(cmd, env=env)
        if proc.returncode not in (0, 1):  # locust usa 1 ante fallos de requests
            print(f"locust terminó con código {proc.returncode}")
            return proc.returncode

        stats = _csv_of(base)
        if not stats.exists():
            print("No se generó el CSV de estadísticas.")
            return 2

        total_req = 0
        total_fail = 0
        p95s = []
        p99s = []
        with open(stats, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Name"] == "Aggregated":
                    total_req = int(row["Request Count"])
                    total_fail = int(row["Failure Count"])
                    p95 = float(row["95%"])
                    p99 = float(row["99%"])
                    print(f"REQ={total_req} FAIL={total_fail} p95={p95:.0f}ms p99={p99:.0f}ms")
                    break
        if total_req == 0:
            print("Sin requests registrados.")
            return 3
        err_rate = 100.0 * total_fail / total_req
        print(f"ERR_RATE={err_rate:.2f}%")
        print("RESUMEN_LISTO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())