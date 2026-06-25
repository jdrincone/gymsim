"""CLI del simulador.

Tres comandos:
  - `gymsim tick`      Llenado autónomo: inserta en la BD los eventos desde el último checkpoint.
  - `gymsim simulate`  Backfill o inspección: genera un horizonte fijo a Postgres o a un JSONL.
  - `gymsim transform` Analítica: ejecuta los SQL raw→staging→curated (idempotente).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import SimConfig, load_config


def _load_config(path: str | None, days: int | None = None, seed: int | None = None) -> SimConfig:
    config = load_config(path) if path and Path(path).exists() else SimConfig()
    if days is not None:
        config.time.horizon_days = days
    if seed is not None:
        config.seed = seed
    return config


def _export_ground_truth(result, path: str) -> None:
    """Exporta las visitas reales (ground-truth) en JSONL para validar la analítica."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for v in result.visits:
            f.write(
                json.dumps(
                    {
                        "visit_id": v.visit_id,
                        "member_external_id": v.member.external_id,
                        "archetype": v.member.archetype.value,
                        "group_id": v.member.group_id,
                        "ts_in": v.ts_in.isoformat(),
                        "ts_out": v.ts_out.isoformat(),
                        "duration_min": round(v.duration_min, 2),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"[ground-truth] {len(result.visits)} visitas -> {p}")


def cmd_tick(args) -> int:
    """Inserta en la BD los eventos ocurridos desde el último checkpoint (llenado autónomo)."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: define DATABASE_URL (en .env o como variable de entorno)")
        return 2
    config = _load_config(args.config, seed=args.seed)

    from .live import run_tick

    print("tick:", json.dumps(run_tick(config, dsn, args.accel), ensure_ascii=False))
    return 0


def cmd_simulate(args) -> int:
    """Genera un horizonte completo de una vez y lo vuelca a Postgres o a un archivo JSONL."""
    config = _load_config(args.config, days=args.days, seed=args.seed)

    if args.sink == "postgres":
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            print("ERROR: define DATABASE_URL para el sink postgres")
            return 2
        from .sinks.postgres import PostgresSink

        sink = PostgresSink(dsn, devices=config.devices, site_id=config.site_id)
    elif args.sink == "jsonl":
        from .sinks.jsonl import JsonlSink

        sink = JsonlSink(args.out)
    else:
        from .sinks.memory import MemorySink

        sink = MemorySink()

    from .simulation.engine import run

    print(
        f"Simulando {config.population.size} socios, {config.time.horizon_days} días, "
        f"seed={config.seed}, sink={args.sink}"
    )
    result = run(config, sink)
    print("Resumen:", json.dumps(result.summary(), ensure_ascii=False, indent=2))
    if args.ground_truth:
        _export_ground_truth(result, args.ground_truth)
    return 0


def cmd_transform(args) -> int:
    """Ejecuta los SQL de analítica (raw→staging→curated) sobre la BD."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: define DATABASE_URL para ejecutar los transforms")
        return 2

    from .transform import run_transforms

    print("transform:", json.dumps(run_transforms(dsn, args.transforms_dir), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gymsim", description="Simulador de la registradora de un gimnasio")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("tick", help="Llenado autónomo: inserta los eventos desde el último checkpoint")
    t.add_argument("--config", default=os.environ.get("GYM_CONFIG", "configs/gym.yaml"))
    t.add_argument("--seed", type=int, default=None)
    t.add_argument(
        "--accel",
        type=float,
        default=float(os.environ.get("SIM_ACCEL", "1")),
        help="aceleración: 1=ritmo real; >1 llena más rápido (env SIM_ACCEL)",
    )
    t.set_defaults(func=cmd_tick)

    s = sub.add_parser("simulate", help="Backfill/inspección: genera un horizonte fijo a Postgres o JSONL")
    s.add_argument("--config", default=os.environ.get("GYM_CONFIG", "configs/gym.yaml"))
    s.add_argument("--sink", choices=["postgres", "jsonl", "memory"], default="jsonl")
    s.add_argument("--out", default="data/events.jsonl", help="ruta JSONL (sink jsonl)")
    s.add_argument("--days", type=int, default=None, help="horizonte en días")
    s.add_argument("--seed", type=int, default=None)
    s.add_argument("--ground-truth", default=None, help="ruta JSONL para exportar el ground-truth")
    s.set_defaults(func=cmd_simulate)

    x = sub.add_parser("transform", help="Analítica: ejecuta los SQL raw→staging→curated")
    x.add_argument(
        "--transforms-dir",
        default=os.environ.get("GYM_TRANSFORMS_DIR", "sql/transforms"),
        help="directorio con los .sql (se aplican en orden alfabético)",
    )
    x.set_defaults(func=cmd_transform)
    return p


def main(argv: list[str] | None = None) -> int:
    try:  # consola Windows (cp1252) → fuerza UTF-8 para acentos/símbolos
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:  # carga DATABASE_URL desde .env
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
