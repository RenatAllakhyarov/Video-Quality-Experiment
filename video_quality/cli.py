from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import ExperimentError, ffprobe, load_json, require_tool, run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(prog="video-quality")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="проверить внешние инструменты и конфигурацию")
    check.add_argument("--config", type=Path, default=Path("config/experiment.json"))
    run = sub.add_parser("run", help="запустить эксперимент")
    run.add_argument("--config", type=Path, default=Path("config/experiment.json"))
    args = parser.parse_args()
    try:
        if args.command == "check":
            config = load_json(args.config)
            print(json.dumps({"ffmpeg": require_tool("ffmpeg"), "ffprobe": require_tool("ffprobe"), "config": str(args.config), "encoders": config["encoders"]}, ensure_ascii=False, indent=2))
        else:
            results = run_experiment(args.config)
            print(json.dumps({"total": len(results), "success": sum(r.status == "success" for r in results), "skipped": sum(r.status == "skipped" for r in results), "error": sum(r.status == "error" for r in results)}, ensure_ascii=False))
        return 0
    except (ExperimentError, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
