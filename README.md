# Field Shift UA

Field-level crop rotation advisor for Ukraine, built for NASA Space Apps 2026.

## What it does

Field Shift UA helps a Ukrainian farmer decide what to sow on a specific field next season and which 4-year rotation (2027–2030) should follow. It works on real field polygons from NASA Harvest: 1,455,645 fields in 22 oblasts (`n` in [`site/fields_grid.json`](site/fields_grid.json)). The tool:

- reconstructs what grew on each field from HLS 30 m NDVI;
- simulates every rotation allowed by Ukrainian law over 25 years of NASA POWER weather (2001–2025) with an FAO-56 water-balance crop model;
- compares the farmer's current practice with max-margin, min-risk, balanced and, in the steppe, water-saving strategies.

Each strategy shows its yield and margin in dry, typical and wet years (P10 / P50 / P90), its violations of the crop-rotation regulation, its effect on soil moisture, and the data gaps an agronomist should check. The tool supports the farmer and the agronomist; it does not replace them.

The web front end is a single static page, [`site/index.html`](site/index.html), with the data embedded.

## Data

### NASA data

| Dataset | Used for | Link |
|---|---|---|
| NASA POWER: daily agroclimatology (T2M, precipitation, RH, wind, radiation, dew point, TSOIL1) | weather for the crop model, climate shift, sowing dates | https://power.larc.nasa.gov/ |
| HLS Sentinel-2 HLSS30 v2.0 | 30 m NDVI, crop-season classification | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlss30-2.0 |
| HLS Landsat HLSL30 v2.0 | 30 m NDVI, crop-season classification | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlsl30-2.0 |
| MODIS MOD13Q1 v061, NDVI 250 m | point comparison with HLS | https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061 |
| MODIS MOD16A2GF v061 | evapotranspiration | https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod16a2gf-061 |
| SMAP SPL3SMP_E v6 | soil moisture, 9 km | https://nsidc.org/data/spl3smp_e |
| ECOSTRESS ECO_L3T_JET v002 (ISS) | 70 m evapotranspiration, independent model check | https://www.earthdata.nasa.gov/data/catalog/lpcloud-eco-l3t-jet-002 |
| ECOSTRESS ECO_L2T_LSTE v002 | cloud mask | https://www.earthdata.nasa.gov/data/catalog/lpcloud-eco-l2t-lste-002 |
| SRTM SRTMGL1 v003 | elevation | https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003 |
| NASA Harvest: Ukraine Field Boundary Delineation 2023 | field polygons | https://data.harvestportal.org/dataset/39597661-59b1-4069-a2aa-5c26e5c9fd8a |
| NASA AppEEARS | extraction API for HLS, ECOSTRESS and MODIS | https://appeears.earthdatacloud.nasa.gov/ |

### Partner and other data

| Source | Used for | Link |
|---|---|---|
| ESA Copernicus Sentinel-2, via NASA HLS S30 | 30 m NDVI | https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2 |
| State Statistics Service of Ukraine (SSSU / Держстат): crop yields 2015–2025 | yield calibration and validation | https://stat.gov.ua/uk/datasets/ploshchi-valovi-zbory-ta-urozhaynist-silskohospodarskykh-kultur-richna |
| SSSU: sale prices of agricultural products | prices for the margin | https://stat.gov.ua/uk/datasets/realizatsiya-produktsiyi-silskoho-hospodarstva-pidpryyemstvamy-ta-hospodarstvamy |
| SSSU: production costs and profitability | costs for the margin | https://stat.gov.ua/uk/datasets/vytraty-na-vyrobnytstvo-produktsiyi-robit-posluh-silskoho-hospodarstva |
| SSSU SDMX: exports by country (DF_EXTERNAL_TRADE_INDIVIDUAL_GOODS_BY_COUNTRIES) | market block | https://stat.gov.ua/ |
| ISRIC SoilGrids 2.0 | soil texture and water content | https://soilgrids.org/ |
| FAO Irrigation and Drainage Paper 56 | crop evapotranspiration | https://www.fao.org/4/X0490E/x0490e00.htm |
| FAO Irrigation and Drainage Paper 66 | crop yield response to water | https://www.fao.org/4/i2800e/i2800e00.htm |
| Cabinet of Ministers of Ukraine Resolution No. 164 | crop-rotation norms | https://kodeksy.com.ua/norm_akt/source-КМУ/type-Постанова/164-2010-п-11.02.2010.htm |
| Institute of Agriculture of Polissia NAAS: sowing recommendations 2026 | sowing calendar | https://www.isgpnaan.org/upload/rekomendatsii-posiv-2026.pdf |
| Plant Production Institute n.a. V.Ya. Yuriev NAAS: sowing recommendations | sowing calendar | https://yuriev.com.ua/assets/files/navchalni-posibnyky/osinnij-kompleks-2023.pdf |
| Institute of Climate-Smart Agriculture NAAS: winter crop sowing, Southern Steppe | sowing calendar | https://dspace.mnau.edu.ua/jspui/bitstream/123456789/4638/1/Ahrotekhnolohichni%20umovy_2019.pdf |
| geoBoundaries: Ukraine ADM1 | oblast boundaries | https://www.geoboundaries.org/ |
| OSRM demo server with OpenStreetMap data | road distance to ports (10 points) | https://router.project-osrm.org/ |
| Port coordinates (Wikipedia) and market prices and tariffs (graintrade.com.ua, AgroNews, Latifundist.com) | market block | a URL and quote in each row of [`data/raw/market/`](data/raw/market/) and [`data/raw/prices_candidates.csv`](data/raw/prices_candidates.csv) |

## How the model works

1. **Field.** A NASA Harvest polygon gives the field's area and location. NASA POWER, SMAP, SRTM and SoilGrids describe its climate, moisture, elevation and soil.
2. **History.** HLS 30 m NDVI (2016–2025) classifies each season as a winter crop, a spring crop (early or late) or fallow. HLS cannot identify the crop itself, so an unconfirmed early spring season is treated as "possibly sunflower". The plan is computed for the stricter branch, and the farmer can confirm the actual crop ([D3](docs/decisions.md), [D22](docs/decisions.md)).
3. **Crop model.**
   - FAO-56 Penman–Monteith reference ET, crop coefficients and a daily soil water balance.
   - Yield loss from water stress with the FAO-33/66 yield response factor Ky.
   - Soil moisture carries over between seasons, so the previous crop matters.
   - Spring sowing is dynamic: the first day NASA POWER `TSOIL1` reaches the threshold from Ukrainian agronomic recommendations. Winter-crop phases come from our HLS phenology ([D17](docs/decisions.md)).
   - Potential yield is calibrated on SSSU oblast yields ([D1](docs/decisions.md)).
4. **Regulation No. 164.** Return intervals (e.g. sunflower at least 7 years, [`model/rules.yaml`](model/rules.yaml)) and maize-run limits are hard constraints, applied to the field history plus the plan ([D3](docs/decisions.md)). The farmer's current practice is still evaluated and shown with its violations, without a penalty ([D16](docs/decisions.md), [D21](docs/decisions.md)).
5. **Optimizer.**
   - Every admissible 4-year rotation is simulated over all 25 weather years.
   - Margin = price × simulated yield − full production cost, from official regional statistics ([D15](docs/decisions.md), [D16](docs/decisions.md)).
   - A Pareto front yields the max-margin, min-risk and balanced strategies, plus a water-saving one for the steppe.
6. **Sunflower effect** ([D20](docs/decisions.md)). Sunflower yield drops when it returns too soon. The multiplier is ×0.80 after 0–1 years between sowings and ×0.90 after 2 years, interpolated to ×1.0 at 6 years or more. It comes from the Poltava long-term trial 1999–2016 (Kohan et al. 2016). [`reports/money.md`](reports/money.md) shows results with and without the effect.
7. **Harvest machinery** ([D27](docs/decisions.md), [`model/machinery.yaml`](model/machinery.yaml)). Each crop maps to a machinery group, each with a manufacturer source or a flag for the agronomist to check. The groups are grain header, corn header, sunflower header, sugar-beet harvester and silage.
   - **Owned machinery** is inferred from the field's HLS history 2021–2025. The grain header is treated as base combine equipment whenever HLS sees any combine-harvested crop. This is a flagged team assumption.
   - **Badges.** Every strategy shows "new machinery needed: …".
   - **"With existing machinery" strategy.** The highest-margin rotation that needs no new machinery. It is picked from the rotations the optimizer has already evaluated, so the model runs no extra simulation.
   - **Old strategies are unchanged.** Before and after this change, the 5 pilots and the 250 portfolio fields were compared exactly.
   - It is a constraint, not a ban: machinery can be rented or harvesting hired.

Every number on the site comes as a P10/P50/P90 range with its source and flags (stub data, missing costs, costs borrowed from other oblasts). Design decisions and deviations from the spec are logged in [`docs/decisions.md`](docs/decisions.md).

## Validation

Nothing was tuned to the validation data.

- **Yield, SSSU oblast yields.** Leave-one-year-out on 48 pilot × crop × year pairs ([`reports/step3_validation.md`](reports/step3_validation.md), [D1](docs/decisions.md)):

  | Method | MAPE | Spearman |
  |---|---|---|
  | Our model | 16.5% | 0.91 |
  | Multi-year average | 22.0% | 0.8 |
  | Rainfall-only regression | 36.3% | 0.65 |

- **Margin, sugar beet with full costs** ([`reports/margin.md`](reports/margin.md), [D16](docs/decisions.md)):
  - Poltava: model P50 −58.5 vs SSSU −59.4 thousand UAH/ha;
  - Vinnytsia: −166 vs −131 thousand UAH/ha.

  The crop is loss-making in both, so it drops out of the strategies.
- **ECOSTRESS evapotranspiration vs the model** on five pilot fields, daytime overpasses ([`reports/ecostress.md`](reports/ecostress.md), [D18](docs/decisions.md)):

  | Period | n | r | Bias, model − ECO | MAE |
  |---|---|---|---|---|
  | Whole year | 300 | 0.81 | +0.39 mm/day | 0.67 mm/day |
  | April–September | 144 | 0.60 | +0.65 mm/day | 1.10 mm/day |

  The model overestimates summer ET, most for maize (+0.84 mm/day), so it underestimates drought. This fails the pre-set target of MAE ≤ 1.0 mm/day. It is our next fix.

## Market & logistics (light)

A separate block, "Куди продати" ("Where to sell"), on the field card. It does not change the strategy model.

- **Export destinations** ([D23](docs/decisions.md)). Top-5 countries for each crop's product from SSSU export statistics 2021–2024 ([`data/raw/market/derzhstat_export_by_country.csv`](data/raw/market/derzhstat_export_by_country.csv)). Unit check: wheat 2024 = 20.66 Mt. For sunflower, the card notes that Ukraine exports mostly oil and meal, not seed.
- **Three sales routes** ([D24](docs/decisions.md), [D28](docs/decisions.md)). The site shows three alternatives side by side:
  - the nearest sea port of Greater Odesa;
  - the Danube (Izmail or Reni);
  - the nearest western border crossing to the EU.

  Coordinates come from Wikipedia with a URL in [`data/raw/market/ports.csv`](data/raw/market/ports.csv) and [`data/raw/market/border_crossings.csv`](data/raw/market/border_crossings.csv). For each route the table shows:
  - distance: by road (OSRM, cached in [`data/raw/market/osrm_cache.json`](data/raw/market/osrm_cache.json)) for the 5 pilots and 5 window centres, and straight-line elsewhere;
  - tariff, only where a sourced one exists;
  - risks, as plain text.

  There is no combined score or weighting, because the choice depends on the buyer's terms on the day of sale. OSRM routes may cross Moldova: Volyn → Reni is 819 km by road. Border queues are not modelled.
- **Port vs elevator spread** ([D25](docs/decisions.md)). Only computed when both prices come from the same snapshot and date. The only such case is maize, 08.07.2026: 10,660 − 9,151 = 1,509 UAH/t ([`data/raw/prices_candidates.csv`](data/raw/prices_candidates.csv)).
- **Delivery cost is not in the margin** ([D26](docs/decisions.md)). A sourced truck tariff ([`data/raw/market/transport_rates.csv`](data/raw/market/transport_rates.csv)) covers only one of our oblasts (Mykolaiv), and only on the site. Elsewhere the site says the delivery cost is not included.

## Limitations

- Weather is one NASA POWER grid cell per field (0.5° × 0.625°, see the file names in `data/raw/power/`), not the field itself.
- Yields are calibrated and validated on oblast statistics, not farm records.
- The model overestimates summer ET (see ECOSTRESS above), so drought risk is understated.
- HLS separates winter, spring and fallow seasons but cannot identify the crop. The "current practice" is a guess until the farmer confirms it.
- There is no sourced cost for bare fallow, so fallow is allowed only in the water-saving strategy ([D16](docs/decisions.md)).
- Crops without a published Ky (e.g. millet) cannot be computed ([D19](docs/decisions.md)).
- Prices (DSSU 2025) and full costs (2025) are official statistics, not the farm's own. Logistics is not in the margin.
- Owned harvest machinery is inferred from HLS, not reported by the farmer. The grain-header rule is a team assumption ([D27](docs/decisions.md)).

## Next steps (mentor feedback)

- **Pilot with one real farm or agricultural holding.** Use its field records, actual crops, machinery and costs instead of HLS guesses and oblast statistics.
- **Pest-risk forecasts.** Add disease and pest risk to the strategies, next to the drought risk.
- **Field sensors and yearly soil samples.** Replace SoilGrids and the POWER grid cell with measurements from the field itself.
- **On-premise deployment for holdings.** Add custom presets: the holding's own rotations, machinery fleet, prices and constraints.

## How to run

Requirements: Python with `numpy`, `pandas`, `pyyaml`, `requests`, `matplotlib` and `pytest`. Developed on Python 3.13.

```bash
pip install numpy pandas pyyaml requests matplotlib pytest

# rebuild site data from the cached inputs in the repo (no network)
python scripts/export_site_strategies.py          # strategies -> site/strategies.json
python scripts/market_export.py                   # export by country -> site/market.json
python scripts/market_ports.py                    # ports, spread, tariff -> site/market.json (cache only)
python site/build_site.py out site/ndvi_seasons.csv site/data.json   # -> site/index.html

# tests
python -m pytest -q
```

To open the site, open `site/index.html` in a browser. It loads d3 and fonts from a CDN.

Every push to `main` that changes `site/index.html` publishes the page to GitHub Pages ([`.github/workflows/pages.yml`](.github/workflows/pages.yml)).

Fetching raw data again needs network access:

- `scripts/fetch_power.py` and `scripts/fetch_soilgrids.py` download NASA POWER and SoilGrids data;
- `appeears_hls.py` and `appeears_ecostress.py` call NASA AppEEARS and need an Earthdata login, passed in the `EARTHDATA_USER` / `EARTHDATA_PASS` environment variables or typed at the prompt;
- `python scripts/market_ports.py --fetch` queries OSRM.

`test_speed` is a timing test and may fail on slower machines.

## Licences and attribution

Each data licence below was checked on the source's own site on 15.11.2026.

| Source | Licence | Attribution / where stated |
|---|---|---|
| **NASA Harvest**, Ukraine Field Boundary Delineation 2023 | Creative Commons Attribution, per the [dataset page](https://data.harvestportal.org/dataset/39597661-59b1-4069-a2aa-5c26e5c9fd8a) | Cite: Sadeh, Y., Wagner, J., Nair, S.S. et al. *National-Scale In-Season Field Boundaries of Ukraine Using Remote Sensing.* Sci Data 12, 833 (2025). https://doi.org/10.1038/s41597-025-05190-7. The field polygons in `out/fields/` and `site/` are derived from this dataset. |
| **NASA POWER** | The POWER site states no licence. The [AWS Open Data registry entry](https://registry.opendata.aws/nasa-power/) says "There are no restrictions on the use, access, and/or download of data from the NASA POWER Project" and lists CC BY 4.0. | Acknowledgement requested by [POWER referencing](https://power.larc.nasa.gov/docs/referencing/): "The data was obtained from National Aeronautics and Space Administration (NASA) Langley Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA Earth Science Division." Files are in `data/raw/power/`. |
| **Other NASA Earthdata** (HLS, MODIS, SMAP, ECOSTRESS, SRTM) | CC0 for data from NASA-led missions, per the [Earthdata data use policy](https://www.earthdata.nasa.gov/learn/use-data/data-use-policy) | Citation strongly requested. Dataset links are in the table above. |
| **ISRIC SoilGrids 2.0** | CC BY 4.0: "The SoilGrids maps are publicly available under the CC-BY 4.0 License" ([ISRIC docs](https://docs.isric.org/globaldata/soilgrids/)) | Data: ISRIC – World Soil Information, SoilGrids 2.0, https://soilgrids.org/. Files are in `data/raw/soil/`. |
| **State Statistics Service of Ukraine** (Держстат) | CC BY 4.0: "All content is available under the Creative Commons Attribution 4.0 International license" (footer of [stat.gov.ua](https://stat.gov.ua/en/node/5269)) | Source: State Statistics Service of Ukraine, https://stat.gov.ua/. Used in `data/raw/yield/`, `data/raw/prices_derzhstat*.csv`, `data/raw/costs_derzhstat.csv` and `data/raw/market/derzhstat_export_by_country.csv`. |
| **OpenStreetMap**, via the OSRM demo server | ODbL ([openstreetmap.org/copyright](https://www.openstreetmap.org/copyright)). The OSRM demo server is for "reasonable, non-commercial use-cases", max 1 request per second ([OSRM wiki](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server)). | Road distances in `data/raw/market/osrm_cache.json`: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), available under the Open Database License. |
| geoBoundaries | licence not verified | https://www.geoboundaries.org/ |
| ESA Copernicus Sentinel-2 | licence not verified separately; used only inside NASA HLS | https://sentinels.copernicus.eu/ |
| Wikipedia port coordinates; graintrade.com.ua, AgroNews and Latifundist.com prices and tariffs | licence not verified; short quotes with URL in each row | `data/raw/market/`, `data/raw/prices_candidates.csv` |

**Code.** The code is under the MIT licence ([`LICENSE`](LICENSE)). The data in `data/raw/`, `out/` and `site/` keeps the licences of its sources listed above.

## Use of AI

- The code was written with the help of AI agents (Claude, as a CLI coding agent). The team set the tasks, reviewed the changes, ran the tests and made the design decisions.
- Data and numbers were checked by people. Every data value comes from a primary source cited in the repository.
