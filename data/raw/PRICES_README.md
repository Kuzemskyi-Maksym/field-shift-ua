# Ціни (заповнює команда; модель лише перевіряє формат) — docs/decisions.md D13

Основний файл: `data/raw/prices_candidates.csv` (`model/optimize.yaml: prices_file`), зріз — `prices_snapshot`.
Колонки: `crop` (crop_id з model/crops.yaml), `price_uah_t` (> 0), `basis` (`EXW` | `avg_domestic` | `CPT_port`),
`date` (YYYY-MM-DD), `snapshot` (назва зрізу), `source` (URL/документ; «те саме» = джерело першого рядка зрізу), `note`.

- Один розрахунок = один зріз. Інший зріз — `python -m model.optimize ... --prices-snapshot EGB_2026-07`.
- Пріоритет ціни культури: EXW → avg_domestic (прапорець) → CPT_port лише з `--cpt-port-as-is` (чутливість).
- `data/raw/prices.csv` — порожній шаблон без зрізів (для тестів/нових даних).
