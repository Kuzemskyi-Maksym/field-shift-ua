# Контракт `strategies_<field>.json` (ТЗ A9 + розширення, погоджено 12.11.2026)

Генерує `python -m model.optimize`; файл — `out/strategies/strategies_<field_id з ":" → "_">.json`.
**A9** — поля з ТЗ (обов'язкові). **EXT** — розширення. Усі суми — «валовий дохід, без витрат».

## Верхній рівень

| Поле | Тип | Статус | Опис |
|---|---|---|---|
| `field_id` | str | A9 | `berezivka_od` (пілот) або `<oblast>:f<fid>` (HLS-поле) |
| `area_ha` | float | A9 | площа полігона NASA Harvest |
| `oblast`, `zone` | str | EXT | область (як у Держстаті), зона календаря (`steppe`/`forest_steppe`/`polissia`) |
| `ranking` | obj | EXT | `{mode, unit, label, flags, prices_file, prices_snapshot, prices_fallback, yield_file, costs_file, cost_year, cost_column}`; `mode`: `margin` (основний) \| `money` \| `feed_energy` \| `feed_protein` \| `yield_index` \| `none`. Для `yield_index` `label` = «ранжування без цін — демо механіки» — **показувати на фронті** |
| `next_season` | obj | A9 | `{crop, why}` + EXT `crop_uk`; `crop = null`, якщо ранжування немає (`why` пояснює) |
| `strategies` | list | A9 | див. нижче; `name`: `current` \| `max_income` \| `min_risk` \| `balanced` \| `water` (EXT, лише зона `steppe`; D16). У `max_income`/`min_risk`/`balanced` чорного пару немає (немає витрат на пар з джерелом — прапорець у gaps); пар — лише у `water` |
| `candidates_without_data` | list | EXT | культури без т/га (немає Yx Держстату): `{crop, crop_uk, rel_yield_single_season{dry,typical,wet}, flags}` — «перспективні, але без даних для т/га»; у стратегіях не беруть участі |
| `history` | list | EXT | `{year, c (W\|S\|F\|?), sub (early\|late\|""), confirmed_crop}` — історія HLS + підтвердження |
| `history_confirmed` | obj | EXT | `{"<рік>": crop_id}` — що підтвердив фермер (див. «Підтвердження історії») |
| `history_branches` | list | EXT | `{label, n_candidates, n_pareto, strategies{name: [crop…]}}` — гілки «можливо соняшник»; основна — остання (суворіша) |
| `run` | obj | EXT | службове: час, к-сть допустимих планів, причини відсікання, `strategy_crops`, `yx_t_ha`, прапорці ринку/тваринництва |

## `strategies[]`

| Поле | Статус | Опис |
|---|---|---|
| `name`, `sequence`, `per_year`, `metrics`, `calendar`, `explain`, `confidence` | A9 | як у ТЗ |
| `sequence_uk` | EXT | назви культур українською |
| `assumption` | EXT, лише `current` | яке припущення для невідомих років HLS (`"2022=W"`, `"за класами HLS"`) |
| `variants` | EXT, лише `current` | інші варіанти невідомих років: `{assumption, sequence, sequence_uk, violations_164, rank_value_p50, yield_index_p50}` |
| `name = own_machinery` | EXT, D27 | «З наявною технікою»: найвищий P50 маржі серед уже порахованих кандидатів без нових груп техніки; може бути відсутня |
| `machinery` | EXT, D27, усі стратегії | `{groups, new, new_uk, text, sources, owned, owned_flags, note}` — групи техніки з `model/machinery.yaml`; `text` — «потрібна нова техніка: …» або null |

### `per_year[]`
A9: `year, crop, yield_t_ha{dry,typical,wet}, yield_t_field{…}, channel, revenue_uah_ha{…}, flags`.
EXT: `season` (рік урожаю), `crop_uk`, `rel_yield{dry,typical,wet}` (Ya/Yx), `cost_uah_ha` (фіксовані витрати на га, колонка `ranking.cost_column`, основна — `full_cost_uah_ha`; пар — **null** з прапорцем «витрати на пар не враховано»),
`margin_uah_ha{dry,typical,wet}` = `revenue_uah_ha` − `cost_uah_ha` (`revenue_uah_ha` — валовий дохід); для пару — **null** (не 0).
`dry/typical/wet` = P10/P50/P90 розподілу за 25 роками погоди. `yield_t_ha = null` — немає Yx (не має траплятися в ранжованих стратегіях).

`channel` — A9: `type (sale|feed)`, `buyer_id`, `net_price_uah_t`, `alternatives`; EXT: `type: "none"` для пару, `why`,
`breakeven_port_km`, `feed_value_uah_t`, `feed_species`.

### `metrics`
A9: `income_p50`, `income_p10` (валовий дохід, грн/га/рік — у режимах `margin`/`money`; інакше null), `water_deficit_mm`, `legume_share`,
`bare_days`, `feed_self_sufficiency` (поки null + gap).
EXT: **`margin_p50`, `margin_p10`** (основна метрика в режимі `margin`, грн/га/рік), `margin_p90`, `income_p90` (лише для відображення смуги P10–P90), `rank_mode`, `rank_value_unit`, `rank_value_p50/p10` (у одиницях режиму), `yield_index_p50/p10` (Ya/Yx, лише довідково),
`end_moisture_frac`, `drying_share`, `margin_excludes_fallow_cost` (true → у послідовності є пар, у `margin_p50/p10` він = 0 грн, бо витрат на пар немає; маржа завищена, `confidence` ≤ medium), **`violations_164: {count, list}`** — порушення №164 всередині послідовності
(для `current` — фактична практика; ранжовані стратегії — завжди 0, бо відфільтровані).
EXT (D19, лише режим `margin`, інакше null): **`money`** — `{area_ha, years: [{season, margin_ha, cumulative_ha, cumulative_field}],
total_ha, total_field, excludes_fallow_cost, note}`, кожне значення `{p10, p50, p90}` грн; накопичена рахується в кожному році погоди
(P50 суми ≠ сума P50). **`vs_current`** (не для `current`): `{delta_vs_current_uah_ha, delta_vs_current_uah_field: {p50, p10},
years: [{season, delta_ha_p50, cum_delta_ha_p50, cum_delta_field_p50}], drawdown_year, drawdown_years, breakeven_year,
current_violates_164, rule}` — різниця з поточною в тих самих роках погоди; drawdown_year — перший сезон, де P50 річної різниці < 0;
breakeven_year — перший сезон, з якого накопичена P50 ≥ 0 до кінця плану (null — не окупається).

### `presets[]` (верхній рівень, D19)
Фіксовані сівозміни з `model/presets.yaml`, оцінені без пошуку (як `current`): `{id, name_uk, src, rotation, sequence (K років,
ротація по колу), sequence_uk, plan_note, status: ok|no_data, reasons[], violations_164, metrics: {margin_p10/p50/p90,
end_moisture_frac, water_deficit_mm, margin_excludes_fallow_cost} | null, money | null, vs_current | null}`. Культура без
параметрів / т/га / ціни / календаря → `status: no_data`, числа null, причина в `reasons` — нічого не підставляється.
Сайт: `presets[]` у FieldPlan (`site/strategies.json`), `strategies[].money`, `strategies[].vs`.

### `explain`
A9: `why`, `data`, `benefits`, `gaps`, `agronomist_check`. EXT: `profitability` (рядки рентабельності Держстату за 2025 рік),
`why_not_repeat` (лише `current` з порушеннями №164): `{title: "чому не повторювати поточну", compare_with: "balanced",
recommended_sequence_uk, rows: [{metric: violations_164|end_moisture_frac|drying_share, label, current, recommended}], lines}` — без штрафу.
Порядок `gaps`: «маржа близька до нуля …» (якщо є) → «УВАГА: … збиткова …» → решта.

### `calendar[]`
A9: `year, crop, sow (MM-DD), harvest (MM-DD), bare [MM-DD, MM-DD], risks`.
EXT: `sow_date`, `harvest_date` (YYYY-MM-DD), `stub` (дата-заглушка → позначати на Ганті), `flags`.
EXT (D17, лише ярі з динамічною сівбою): `sow`/`harvest` — медіана по 25 роках погоди; `sow_range`, `harvest_range`
[MM-DD P10, MM-DD P90]; `sow_rule` — текст правила (TSOIL1 ≥ поріг, 5-денна середня, джерело). Сайт: `cal[].sow_range`, `cal[].harvest_range`.
Пар: `sow = harvest = null`, `bare` — увесь проміжок. `bare = null` — без голого проміжку.

### `explain`
A9: `why, data, benefits, gaps, agronomist_check`. Правила:
- `current` з порушенням №164: `why` і `gaps[0]` починаються з «поточна сівозміна порушує №164 — ризик хвороб і висушення ґрунту».
- `ranking.mode = yield_index`: `why` починається з «ранжування без цін — демо механіки».
- `gaps` — усі прапорці (STUB, немає Yx/цін, попередник не підтверджений, ефект попередника не враховано, гілки історії…).

- `profitability` (EXT): рядки «рентабельність «культура» в області (… обл.) за Держстатом, 2025: X%»; від'ємна рентабельність →
  `gaps` починаються з «УВАГА: … збиткова …».

### `confidence`
`low` — є STUB, немає Yx або режим `yield_index`/`none`; `medium` — ранжування не за грошима; `high` — гроші, без заглушок.

## Підтвердження історії (`history_confirmed`) — для демо

Фермер у UI підтверджує культури за останні роки → фронт перезапускає оптимізатор з цими значеннями:
- CLI: `python -m model.optimize --field <id> --allow-stubs --rank yield_index --confirm 2022=winter_wheat --confirm 2026=maize`
- Python: `optimize_field(field_id, ..., history_confirmed={2022: "winter_wheat"})`
- Постійно: `data/fields/confirmed.yaml` → `{<field_id>: {<рік>: crop_id}}` (UI-підтвердження перекривають файл).

Ефект: підтверджений рік перестає бути невідомим → зникають гілки «можливо соняшник» / варіанти `current` для цього року,
№164 перевіряється за фактичною культурою, `history_confirmed` у відповіді містить застосовані значення.
Рік, якого немає в HLS (напр. 2026), теж можна підтвердити — він додається до історії.
Значення `not_sunflower` — «це був не соняшник» (культура невідома): знімає гілку «можливо соняшник» для року; №164 для інших культур
у цьому році не перевіряється (невідомо); для поточної практики рік береться як W (прапорець).

## Модуль ринку (D23+): `site/market.json`

Файл лежить у `site/` (не `out/site/`), його підхоплює `site/build_site.py` тим самим циклом, що й strategies/portfolio.
Ключі: `market_export` (етап 1, `scripts/market_export.py`), `market_ports` (етапи 2–3, `scripts/market_ports.py`).

### `market_export`
`{year, source, source_short, units, crop_products: {crop_id: [product]}, crop_notes: {crop_id: текст}, products: {product: …}}`.
`products[p]`: `{product, name_uk, uktzed, year, total: {value_musd, volume_mt, price_usd_t}, top: [{country_uk, area,
share_pct, value_musd, volume_kt, price_usd_t | null}] (топ-5 за вартістю), top_share_pct, top1_trend: {country_uk,
share_pct: {"2021", "2024"}}, series: [{year, value_musd, volume_mt, price_usd_t}] (_T, 2021–2024), note, source}`.
`price_usd_t` = null, якщо обсяг 0. `crop_products[c] = []` → `crop_notes[c]` = «немає даних експорту».

### `data/raw/market/ports.csv`
`port_id,name_uk,lat,lon,source_url` — рядок без `source_url` (http…) не береться. Кеш OSRM `data/raw/market/osrm_cache.json`:
`{"<lat>,<lon>-><port_id>": {road_km, date, url}}`.

### `market_ports`
`{ports: [рядки ports.csv], road_source, straight_note, window_centre_note, road_note, fields: {id: …}, basis: {crop_id: …}, basis_note}`.
`fields` — ключі: пілот (`berezivka_od`, …, `volyn:f3735`), центр вікна `window:<вікно>`, поле портфеля `<вікно>:f<fid>`.
`fields[id]`: `{lat, lon, kind: pilot|window_centre|portfolio, nearest: {port_id, name_uk, km, distance_type: road|straight,
distance_label: «дорогою»|«по прямій»}}` + для пілотів і центрів `ports: [{port_id, name_uk, distance_straight_km,
distance_road_km | null, road_date | null}]` (центри — ще `n_fields`), для портфеля — `straight_km: {port_id: км}`.
`basis[crop]`: `{status: ok|no_data, crop_uk, basis_spread_uah_t | null, text}`; при `ok` ще `cpt_port_uah_t, exw_uah_t, snapshot,
date, source}` — обидві ціни з одного snapshot і дати; `no_data` → `text` = «немає ціни обох базисів з одного джерела».
`tariffs`: `{oblast: {rate_min_uah_t, rate_max_uah_t, destination_uk, vat, period, source, source_url, quote, text}}` — з
`data/raw/market/transport_rates.csv` (`origin_oblast,origin_uk,destination_gen_uk,rate_min_uah_t,rate_max_uah_t,vat,period,
published,source,source_url,quote`); `fields[id].oblast` → тариф; немає → `no_tariff_text`.

### `market_ports.fields[*].routes` і `data/raw/market/border_crossings.csv` (D28)

- `routes[]`: `{route: sea|danube|west, name_uk, point_id, point_uk, point_note, km, distance_type: road|straight, distance_label,
  road_date, tariff_text, risk}` — рівно 3, без ваг і балів. `market_ports.routes_note` — підпис над таблицею;
  `market_ports.crossings` — пункти пропуску, що пройшли фільтр.
- `border_crossings.csv`: `crossing_id,name_uk,neighbour_uk,modes_uk,lat,lon,source_url,quote`; рядок без координат або URL не береться.
