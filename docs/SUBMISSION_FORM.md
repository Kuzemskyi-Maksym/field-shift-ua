# Подача NASA Space Apps: готові тексти для форми

*Field Shift UA · 15.11.2026 (оновлено: техніка, маршрути, 16.5%, без MODIS 21/21) · тексти англійською, кількість символів указано*

## Project Name
Варіанти, обрати один:
- `Field Shift UA: field-level crop rotation advisor` (49 симв.)
- `Project Lesychky: Field Shift UA` (32 симв.), якщо «Lesychky» — назва команди і її треба лишити

## Summary
Ліміт 1500 символів, рекомендовано 50–200 слів. Тут **1093 символів, 175 слів**.

```text
Field Shift UA is a decision-support tool that tells a Ukrainian farmer what to sow next season and lays out a 4-year rotation (2027-2030) for a specific field - not a pixel or a district. We attach NASA data to 1.46 million real field boundaries (NASA Harvest), reconstruct what actually grew on each field from HLS 30 m NDVI (Landsat + Sentinel-2), and simulate every admissible rotation over 25 years of NASA POWER weather with an FAO-56 water-balance crop model. Each strategy - current practice, max-margin, min-risk, balanced, water-saving and "with your existing harvest machinery" - shows yield and margin for dry, typical and wet years, violations of Ukraine's crop-rotation law and data gaps for the agronomist. Margins use official Ukrainian statistics. A light market layer shows where Ukraine exports each crop and compares three sales routes (Black Sea port, Danube, EU border) by distance, sourced tariff and risk. The model beats simple baselines (16.5% vs 22% yield error) and is checked against ECOSTRESS evapotranspiration from the ISS, which showed where it is still wrong.
```

## Project Demonstration
Посилання на **відео ≤30 с з англійськими субтитрами** або на **≤7 слайдів англійською**. Публічне, без логіна: YouTube (Unlisted підходить), Google Slides або Drive («Anyone with the link»).
`TODO: посилання`

## Project
Публічне посилання: репозиторій GitHub (публічний) або GitHub Pages з `site/index.html`.
⚠ Посилання на артефакт claude.ai може вимагати входу в акаунт. Для форми надійніше GitHub Pages.
`TODO: посилання`

## Project Details
Ліміт не вказано. Тут **4881 символів, 772 слів**.

```text
WHAT IT DOES
Field Shift UA answers one question for a Ukrainian farmer: what should I sow on this field next season, and what rotation should follow? It compares the farmer's current rotation with alternatives and shows, for each, yield and margin in a dry, typical and wet year, cumulative 4-year money, legal compliance, the harvest machinery it needs, where the crop can be sold and what an agronomist should verify. The tool supports the farmer and agronomist; it does not replace them.

HOW IT WORKS
1. Field: real field boundaries from NASA Harvest (1,455,645 fields in 22 regions) give area and location; NASA POWER, SMAP, SRTM and SoilGrids describe climate, moisture, elevation and soil texture.
2. History: HLS 30 m NDVI (Landsat + Sentinel-2, 2016-2025) classifies each season as winter or spring crop, with early/late subtypes; the farmer can confirm the actual crop.
3. Climate shift: 2016-2025 versus 2001-2010 from NASA POWER.
4. Crop model: FAO-56 Penman-Monteith reference ET, crop coefficients and a daily soil water balance; yield loss from water stress with FAO-33/66 Ky. Soil moisture carries over between seasons. Spring sowing date is dynamic: the first day NASA POWER soil temperature reaches the threshold from Ukrainian agronomic recommendations.
5. Optimizer: every 4-year rotation is filtered by Ukraine's crop-rotation regulation (Cabinet Resolution No. 164), sowing-calendar conflicts and the field history, then simulated over 25 weather years 2001-2025. Repeated sunflower is penalised by a published yield effect. Margin = price x yield - full production cost (official statistics). A Pareto front gives max-margin, min-risk, balanced and water-saving strategies.
6. Machinery (mentor feedback): we infer which harvest equipment a farm already uses from its HLS history. Strategies that need new equipment (e.g. a sugar beet harvester) are flagged, and a separate "with existing machinery" strategy is shown. It is a warning, not a ban: equipment can be rented.
7. Market (light): where Ukraine exported each crop in 2024 (Statistics Ukraine), and three sales routes per field - nearest Black Sea port, Danube port, EU border crossing - with road distance (OSRM), a tariff only where a dated source exists, and route risks. We give no combined score: the choice depends on buyer terms on the day.
8. Explanation: every number is a P10/P50/P90 range with its source and flags.

VALIDATION (we show where it fails, too)
- Yield model, leave-one-year-out against official regional yields (48 cases): 16.5% error vs 22% for the multi-year average and 36% for a rainfall-only baseline; Spearman 0.91.
- Sugar beet margin with full costs: model -58.5 vs official -59.4 thousand UAH/ha (Poltava), loss-making in both.
- ECOSTRESS (ISS, 70 m) evapotranspiration vs model on five pilot fields: r = 0.81 over the year (n = 300 daytime overpasses), but the model overestimates summer ET, so it underestimates drought. We did not tune the model to ECOSTRESS; this is our next fix.
- Automated tests (FAO-56 worked example, regulation rules, mass balance); old strategies are re-checked to be identical after every change.

BENEFITS AND IMPACT
Ukraine's forest-steppe is drifting towards steppe conditions, and in half of the country a typical field is smaller than one MODIS pixel, so field-level advice needs 30 m data. Across 250 real fields in five regions the tool shows where changing the rotation pays and where it does not: in the Mykolaiv window the balanced strategy adds about 94.5 million UAH over four years (P50) versus current practice, while in Poltava and Vinnytsia the current maize-heavy practice is hard to beat - and we say so. In Volyn the highest-margin rotation needs a sugar beet harvester; the tool shows that and what the farm earns without it.

CREATIVITY
Field-level instead of pixel-level; the farmer's actual rotation recovered from space; dynamic sowing dates from NASA soil temperature; legal rules as hard constraints; machinery and sales routes as real-world limits; uncertainty as ranges; independent validation with ISS data.

NEXT STEPS
A pilot with one real farm or holding to test what they actually need; pest-risk forecasts from soil moisture and temperature; field sensors and yearly soil samples; on-premise deployment and custom presets for holdings that keep their data private.

TOOLS
Python (numpy, pandas, scipy, pyyaml, pytest), NASA AppEEARS API, NASA POWER API, Statistics Ukraine SDMX API, OSRM, d3.js. Code was written with AI assistance (Claude) and reviewed by the team. Part of the code was written before the event with the organizer's permission.

LIMITATIONS
Weather is a ~50 km grid cell; yields are regional statistics; the summer ET bias above; machinery is inferred, not reported; delivery cost is not in the margin; barley, rapeseed and alfalfa lack a published Ky and are excluded from ranking.
```

## Use of Super Intelligence (SI)
Відмітити все, що підходить (точних назв опцій ми не бачили, тож орієнтуйся на зміст):
- **генерація або допомога з кодом** — так: Python-модель, оптимізатор і сайт писали з AI-асистентами (Claude, CLI-агент), людина ставила задачі, рецензувала, тестувала й приймала рішення;
- **текст** — так: допомога з документацією, перекладом і цим описом;
- **аналіз даних і пошук джерел** — так: пошук джерел і агрегація статистики (усі числа взято з першоджерел, посилання в репозиторії);
- **зображення й відео** — лише якщо генерували. Тоді на кожному обов'язкова видима водяна позначка «SI-generated». Логотипи NASA не використовувати.

У README додати рядок: *«Code and documentation were developed with AI assistance (Claude); all data values come from cited primary sources; design decisions and validation were reviewed by the team.»*

## NASA Data
Кожен рядок — окреме посилання (Link Text | Link Url):

| Link Text | Link Url |
|---|---|
| NASA POWER (daily agroclimatology: T2M, precipitation, RH, wind, radiation, dew point, TSOIL1) | https://power.larc.nasa.gov/ |
| HLS Sentinel-2 HLSS30 v2.0 (30 m NDVI, crop-season classification) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlss30-2.0 |
| HLS Landsat HLSL30 v2.0 (30 m NDVI, crop-season classification) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlsl30-2.0 |
| MODIS MOD13Q1 v061 NDVI 250 m | https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061 |
| MODIS MOD16A2GF v061 evapotranspiration | https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod16a2gf-061 |
| SMAP SPL3SMP_E v6 soil moisture 9 km | https://nsidc.org/data/spl3smp_e |
| ECOSTRESS ECO_L3T_JET v002 evapotranspiration 70 m (ISS) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-eco-l3t-jet-002 |
| ECOSTRESS ECO_L2T_LSTE v002 cloud mask | https://www.earthdata.nasa.gov/data/catalog/lpcloud-eco-l2t-lste-002 |
| SRTM SRTMGL1 v003 elevation | https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003 |
| NASA Harvest - Ukraine Field Boundary Delineation 2023 (Sadeh et al., Scientific Data 2025, CC BY 4.0) | https://data.harvestportal.org/dataset/39597661-59b1-4069-a2aa-5c26e5c9fd8a |
| NASA AppEEARS (data extraction API) | https://appeears.earthdatacloud.nasa.gov/ |

## Space Agency Partner & Other Data
| Link Text | Link Url |
|---|---|
| ESA Copernicus Sentinel-2 (inside NASA HLS S30) | https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2 |
| Statistics Ukraine SDMX API - crop yields 2015-2025 | https://stat.gov.ua/uk/datasets/ploshchi-valovi-zbory-ta-urozhaynist-silskohospodarskykh-kultur-richna |
| Statistics Ukraine - sale prices of agricultural products | https://stat.gov.ua/uk/datasets/realizatsiya-produktsiyi-silskoho-hospodarstva-pidpryyemstvamy-ta-hospodarstvamy |
| Statistics Ukraine - production costs and profitability | https://stat.gov.ua/uk/datasets/vytraty-na-vyrobnytstvo-produktsiyi-robit-posluh-silskoho-hospodarstva |
| ISRIC SoilGrids 2.0 (soil texture, water content) | https://soilgrids.org/ |
| FAO Irrigation and Drainage Paper 56 (crop evapotranspiration) | https://www.fao.org/4/X0490E/x0490e00.htm |
| FAO Irrigation and Drainage Paper 66 (crop yield response to water) | https://www.fao.org/4/i2800e/i2800e00.htm |
| Cabinet of Ministers of Ukraine Resolution No. 164 (crop rotation norms) | https://kodeksy.com.ua/norm_akt/source-КМУ/type-Постанова/164-2010-п-11.02.2010.htm |
| Institute of Agriculture of Polissia NAAS - sowing recommendations 2026 | https://www.isgpnaan.org/upload/rekomendatsii-posiv-2026.pdf |
| Plant Production Institute n.a. V.Ya. Yuriev NAAS - sowing recommendations | https://yuriev.com.ua/assets/files/navchalni-posibnyky/osinnij-kompleks-2023.pdf |
| Institute of Climate-Smart Agriculture NAAS - winter crop sowing, Southern Steppe | https://dspace.mnau.edu.ua/jspui/bitstream/123456789/4638/1/Ahrotekhnolohichni%20umovy_2019.pdf |
| geoBoundaries (Ukraine administrative boundaries) | https://www.geoboundaries.org/ |
| D3.js (web visualization library) | https://d3js.org/ |

Плюс бібліотеки: Python, numpy, pandas, scipy, pyyaml, pytest, Playwright (тести), а також код репозиторію з ліцензією.

## Чекліст перед натисканням Submit
- [ ] Демо ≤30 с з англійськими субтитрами або ≤7 слайдів англійською, з публічним посиланням.
- [ ] Посилання Project відкривається в режимі інкогніто без логіна.
- [ ] README: джерела, ліцензія NASA Harvest (CC BY, Sadeh et al. 2025), розділ про AI, «частину коду написано до 14.11 з дозволу організатора».
- [ ] Усі URL повні, з https://.
- [ ] Дедлайн — 15.11, 23:59 за часом локації (перевірити в акаунті).
