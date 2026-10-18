from __future__ import annotations

import csv
import ctypes
import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ExperimentError(RuntimeError):
    pass


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ExperimentError(f"Не найден внешний инструмент: {name}")
    return path


def run_command(command: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    log_path.write_text(
        f"COMMAND: {subprocess.list2cmdline(command)}\n"
        f"DURATION_SECONDS: {time.time() - started:.3f}\n"
        f"RETURN_CODE: {result.returncode}\n\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n",
        encoding="utf-8",
    )
    if result.returncode:
        raise ExperimentError(f"Команда завершилась с кодом {result.returncode}: {log_path}")
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"id", "path", "license", "content_type"}
    if not rows or not required.issubset(rows[0]):
        raise ExperimentError(f"Manifest должен содержать столбцы: {', '.join(sorted(required))}")
    for row in rows:
        if not Path(row["path"]).is_file():
            raise ExperimentError(f"Видео не найдено: {row['path']}")
        if not row["license"].strip():
            raise ExperimentError(f"Не указана лицензия для {row['id']}")
    return rows


def discover_videos(directory: Path, default_license: str = "VERIFY_LICENSE") -> list[dict[str, str]]:
    """Discover every supported video file in a directory for batch testing."""
    extensions = {".mp4", ".mkv", ".mov", ".y4m", ".yuv", ".avi", ".webm"}
    rows: list[dict[str, str]] = []
    for path in sorted(directory.glob("**/*")):
        if path.is_file() and path.suffix.lower() in extensions:
            rows.append({"id": path.stem, "path": str(path), "license": default_license, "content_type": "unknown"})
    if not rows:
        raise ExperimentError(f"В папке не найдено поддерживаемых видео: {directory}")
    return rows


def ffprobe(path: Path, log_path: Path) -> dict[str, Any]:
    result = run_command([
        require_tool("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ], log_path)
    return json.loads(result.stdout)


def gamma_expression(gamma: float) -> str:
    if gamma <= 0:
        raise ValueError("gamma должен быть > 0")
    # Project convention: normalized luma y = x ** gamma, 8-bit clipping.
    return f"clip(255*pow(val/255\\,{gamma}),0,255)"


def contrast_expression(x_min: int, x_max: int) -> str:
    if not 0 <= x_min < x_max <= 255:
        raise ValueError("Ожидаются 0 <= x_min < x_max <= 255")
    return f"clip((val-{x_min})*255/({x_max}-{x_min}),0,255)"


def filter_path(path: Path) -> str:
    """Return a path safe for FFmpeg filter syntax, including Windows usernames."""
    resolved = path.resolve()
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        parent = str(resolved.parent)
        length = ctypes.windll.kernel32.GetShortPathNameW(parent, buffer, len(buffer))
        if length:
            resolved = Path(buffer.value) / resolved.name
    return resolved.as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def preprocessing_filter(spec: dict[str, Any]) -> str:
    kind = spec.get("kind", "none")
    if kind == "none":
        return "format=yuv420p"
    if kind == "gamma":
        return f"lut=y='{gamma_expression(float(spec['gamma']))}':u=128:v=128,format=yuv420p"
    if kind == "contrast":
        return f"lut=y='{contrast_expression(int(spec['x_min']), int(spec['x_max']))}':u=128:v=128,format=yuv420p"
    raise ValueError(f"Неизвестная предобработка: {kind}")


def encode(source: Path, output: Path, encoder: dict[str, Any], filter_text: str, log_path: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [require_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if filter_text:
        command += ["-vf", filter_text]
    command += ["-c:v", encoder["name"]]
    for key, value in encoder.get("options", {}).items():
        command += [f"-{key}", str(value)]
    command += ["-an", str(output)]
    run_command(command, log_path)


def _metric_command(distorted: Path, reference: Path, filter_name: str) -> list[str]:
    graph = (
        f"[0:v]settb=AVTB,setpts=PTS-STARTPTS[dist];"
        f"[1:v]settb=AVTB,setpts=PTS-STARTPTS[ref];"
        f"[dist][ref]{filter_name}"
    )
    return [require_tool("ffmpeg"), "-hide_banner", "-loglevel", "info", "-i", str(distorted), "-i", str(reference), "-lavfi", graph, "-f", "null", "-"]


def parse_last_float(text: str, key: str) -> float | None:
    values = re.findall(rf"{re.escape(key)}:([0-9.+-]+)", text)
    return float(values[-1]) if values else None


def calculate_metrics(distorted: Path, reference: Path, output_dir: Path, vmaf_enabled: bool = True, vmaf_subsample: int = 1) -> dict[str, float | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    values: dict[str, float | None] = {"psnr": None, "ssim": None, "vmaf": None}
    for metric, filter_name, key in [("psnr", "psnr", "psnr_avg"), ("ssim", "ssim", "All")]:
        stats = output_dir / f"{metric}.log"
        command = _metric_command(distorted, reference, filter_name)
        result = run_command(command, output_dir / f"{metric}_command.log")
        text = result.stderr + result.stdout
        if metric == "ssim":
            match = re.findall(r"All:([0-9.]+)", text)
            values[metric] = float(match[-1]) if match else None
        else:
            match = re.findall(r"average:([0-9.]+)", text)
            values[metric] = float(match[-1]) if match else None

    if vmaf_enabled and shutil.which("ffmpeg"):
        graph = "[0:v]settb=AVTB,setpts=PTS-STARTPTS[dist];[1:v]settb=AVTB,setpts=PTS-STARTPTS[ref];[dist][ref]libvmaf"
        if vmaf_subsample > 1:
            graph += f":n_subsample={int(vmaf_subsample)}"
        try:
            result = run_command([require_tool("ffmpeg"), "-hide_banner", "-loglevel", "info", "-i", str(distorted), "-i", str(reference), "-lavfi", graph, "-f", "null", "-"], output_dir / "vmaf_command.log")
            text = result.stderr + result.stdout
            match = re.findall(r"VMAF score:\s*([0-9.]+)", text)
            values["vmaf"] = float(match[-1]) if match else None
        except (ExperimentError, OSError):
            values["vmaf"] = None
    return values


@dataclass
class RunResult:
    run_id: str
    status: str
    values: dict[str, Any]


def run_experiment(config_path: Path) -> list[RunResult]:
    config = load_json(config_path)
    root = config_path.parent
    if config.get("auto_discover", False):
        manifest = discover_videos((root / config["dataset_dir"]).resolve(), config.get("default_license", "VERIFY_LICENSE"))
    else:
        manifest = load_manifest((root / config["dataset_manifest"]).resolve())
    output_root = (root / config["output_dir"]).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    results: list[RunResult] = []
    preprocessings = config["preprocessing"]
    total_runs = len(manifest) * len(preprocessings) * len(config["encoders"])
    completed_runs = 0
    started_at = time.time()
    print(f"Эксперимент: {len(manifest)} видео × {len(preprocessings)} предобработки × {len(config['encoders'])} кодека = {total_runs} запусков", flush=True)
    for video in manifest:
        source = Path(video["path"]).resolve()
        for prep in preprocessings:
            for encoder in config["encoders"]:
                run_id = f"{video['id']}__{prep['id']}__{encoder['id']}"
                run_dir = output_root / run_id
                result_file = run_dir / "result.json"
                if result_file.exists() and config.get("resume", True):
                    previous = load_json(result_file)
                    if previous.get("status") == "success":
                        completed_runs += 1
                        print(f"[{completed_runs}/{total_runs}] SKIP {run_id} (уже готово)", flush=True)
                        results.append(RunResult(run_id, "skipped", previous))
                        continue
                run_dir.mkdir(parents=True, exist_ok=True)
                print(f"[{completed_runs + 1}/{total_runs}] START {run_id}", flush=True)
                try:
                    encoded = run_dir / "encoded.mkv"
                    encode(source, encoded, encoder, preprocessing_filter(prep), run_dir / "encode.log")
                    metric_config = config.get("metrics", {})
                    metrics = calculate_metrics(
                        encoded,
                        source,
                        run_dir / "metrics",
                        vmaf_enabled=bool(metric_config.get("vmaf", True)),
                        vmaf_subsample=int(metric_config.get("vmaf_subsample", 1)),
                    )
                    payload = {"run_id": run_id, "status": "success", "video": video, "preprocessing": prep, "encoder": encoder, "metrics": metrics}
                    result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    results.append(RunResult(run_id, "success", payload))
                    completed_runs += 1
                    print(f"[{completed_runs}/{total_runs}] OK {run_id} ({time.time() - started_at:.1f} s)", flush=True)
                except Exception as exc:  # per-run failure must not stop a batch
                    payload = {"run_id": run_id, "status": "error", "error": str(exc), "video": video, "preprocessing": prep, "encoder": encoder}
                    result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    results.append(RunResult(run_id, "error", payload))
                    completed_runs += 1
                    print(f"[{completed_runs}/{total_runs}] ERROR {run_id}: {exc}", flush=True)
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["run_id", "status", "video_id", "preprocessing_id", "encoder_id", "psnr", "ssim", "vmaf"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in results:
            writer.writerow({"run_id": item.run_id, "status": item.status, "video_id": item.values.get("video", {}).get("id", ""), "preprocessing_id": item.values.get("preprocessing", {}).get("id", ""), "encoder_id": item.values.get("encoder", {}).get("id", ""), **item.values.get("metrics", {})})
    return results
