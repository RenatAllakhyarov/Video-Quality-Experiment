# Эксперимент устойчивости PSNR/SSIM/VMAF

В репозитории есть воспроизводимый CLI-пайплайн, который принимает manifest видео и конфигурацию, выполняет предобработку, кодирование H.264/H.265/AV1, расчёт PSNR/SSIM/VMAF и сохраняет журнал каждого запуска.

## Быстрый старт

1. Установить FFmpeg с `ffprobe` и сборкой `--enable-libvmaf`.
2. Скопировать `config/experiment.example.json` в `config/experiment.json`.
3. Заполнить `dataset/manifest.csv` по образцу, указав абсолютные пути и лицензии.
4. Выполнить `python -m video_quality.cli check --config config/experiment.json`.
5. Запустить `python -m video_quality.cli run --config config/experiment.json`.

Результаты сохраняются в `results/`: копия конфигурации, `results.csv`, каталог каждого прогона, команда и stderr.

## Методические решения

Референсом для обеих схем является исходное видео. В baseline кодируется исходник; в экспериментальной схеме сначала применяется преобразование, затем кодирование. Gamma использует проектную конвенцию `y = x^gamma` для нормированной яркости, контраст — линейное растяжение яркости 8-bit из `[x_min, x_max]` в `[0,255]`. Эти решения должны быть заменены только после получения или письменного согласования недостающей статьи Лосева.

VMAF является опциональным: если текущий FFmpeg не собран с libvmaf, PSNR/SSIM продолжают работать, а VMAF получает `null` с диагностикой в журнале.

## Запуск через Docker Compose

Docker-вариант изолирует Python и FFmpeg. Папка `video-tests` монтируется внутрь контейнера, а результаты сохраняются в проекте на компьютере.

Проверить окружение и тесты:

```powershell
docker compose run --rm video-quality python -m video_quality.cli check --config config/experiment.json
docker compose run --rm tests
```

Запустить эксперимент:

```powershell
docker compose run --rm video-quality
```

Остановить текущий запуск можно `Ctrl+C`. Благодаря `resume: true` повторный запуск продолжит работу с последнего успешного результата.

Проверить наличие контейнеров:

```powershell
docker compose ps
```
