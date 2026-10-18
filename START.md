# How to Run the Video Quality Experiment

This guide runs the project in Docker. It uses the videos in `video-tests/` and saves results in the project folder.

## 1. Start Docker Desktop

Open Docker Desktop and wait until it shows that Docker is running.

Make sure Docker is using Linux containers.

## 2. Open PowerShell in the project folder

```powershell
cd "C:\Users\Renat's laptop\Desktop\Arseniy Project"
```

Check Docker:

```powershell
docker --version
docker compose version
docker info
```

If `docker info` fails, Docker Desktop is not ready.

## 3. Build the Docker image

Run this once, or again after changing `Dockerfile`:

```powershell
docker compose build
```

The image contains Python, FFmpeg, ffprobe, H.264, H.265 and AV1. The Debian FFmpeg package may not include the optional `libvmaf` filter; PSNR/SSIM still work and VMAF is recorded as unavailable in that case.

## 4. Run the tests

```powershell
docker compose run --rm tests
```

Expected result:

```text
Ran 3 tests
OK
```

## 5. Check the video environment

```powershell
docker compose run --rm video-quality `
  python -m video_quality.cli check `
  --config config/experiment.json
```

This checks FFmpeg, ffprobe and the configured encoders.

## 6. Run the experiment

```powershell
docker compose run --rm video-quality
```

The current configuration automatically discovers supported files in `video-tests/`.

The current experiment contains:

```text
11 videos × 3 preprocessing modes × 3 codecs = 99 runs
```

Progress is printed in the terminal:

```text
[1/99] START ...
[1/99] OK ...
[2/99] START ...
```

Do not start a second experiment in another terminal. AV1 and 4K processing can take a long time.

## 7. Stop and resume

Stop the current run with:

```text
Ctrl+C
```

Run the same command again:

```powershell
docker compose run --rm video-quality
```

The configuration uses `resume: true`, so successful runs are skipped and the experiment continues from the next unfinished run.

## 8. Inspect the results

Results are written to:

```text
results_all/
```

Read the summary:

```powershell
Get-Content results_all\results.csv
```

Group results by status:

```powershell
Import-Csv results_all\results.csv | Group-Object status
```

Each run directory contains its result JSON, encoded video, command logs and metric logs.

## 9. Run VMAF separately

The default configuration disables VMAF to make the first pass faster:

```json
"metrics": {
  "vmaf": false,
  "vmaf_subsample": 4
}
```

After PSNR/SSIM processing has completed, edit `config/experiment.json`:

```json
"metrics": {
  "vmaf": true,
  "vmaf_subsample": 4
}
```

Also change the output directory so VMAF results are kept separately:

```json
"output_dir": "../results_vmaf"
```

Run again:

```powershell
docker compose run --rm video-quality
```

For final measurements, use:

```json
"vmaf_subsample": 1
```

This is slower, especially for 4K videos. `vmaf_subsample: 4` is suitable for a pilot run.

## 10. Add more videos

Copy new supported files into:

```text
video-tests/
```

Supported extensions include `.mp4`, `.mkv`, `.mov`, `.y4m`, `.yuv`, `.avi` and `.webm`.

With `auto_discover: true`, the next run will find them automatically.

For the final study, update the license and scene type information in `dataset/manifest.csv`.

## Troubleshooting

### Docker engine is unavailable

Start or restart Docker Desktop, then run:

```powershell
docker info
```

### The run appears stuck

Check whether FFmpeg is still running:

```powershell
Get-Process ffmpeg,python -ErrorAction SilentlyContinue
```

4K encoding and AV1 can be slow. Do not start another copy of the experiment.

### A video fails

The error is saved in that run's `result.json` and log files. One failed video should not stop the remaining batch.

### Rebuild the container

After changing the Dockerfile or Python dependencies:

```powershell
docker compose down
docker compose build --no-cache
```
