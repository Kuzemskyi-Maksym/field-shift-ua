# Параметри культур: значення × джерело / TODO

Згенеровано `python -m model.crops --report`. Не редагувати вручну.

## Готовність до оптимізації

### Зона `steppe` (allow_stubs=False): готово 7 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.steppe.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.steppe.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Буряк цукровий | ⛔ заблоковано | calendar.steppe: заглушка STUB_NO_SOURCE (дозволити --allow-stubs) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.steppe.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.steppe.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

### Зона `forest_steppe` (allow_stubs=False): готово 7 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.forest_steppe.sow: TODO (R2/R3) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.forest_steppe.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.forest_steppe.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Буряк цукровий | ⛔ заблоковано | calendar.forest_steppe: заглушка STUB_NO_SOURCE (дозволити --allow-stubs) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.forest_steppe.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.forest_steppe.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

### Зона `polissia` (allow_stubs=False): готово 7 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.polissia.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.polissia.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Буряк цукровий | ⛔ заблоковано | calendar.polissia: заглушка STUB_NO_SOURCE (дозволити --allow-stubs) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.polissia.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.polissia.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

### Зона `steppe` (allow_stubs=True): готово 8 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.steppe.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.steppe.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.steppe.sow: TODO (R2/R3) |
| Буряк цукровий | ✅ готово | STUB: календар steppe — заглушка без джерела (STUB_NO_SOURCE); довжини фаз FAO-56 Т11 для іншого регіону (Sugarbeet, April, Idaho USA) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.steppe.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.steppe.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

### Зона `forest_steppe` (allow_stubs=True): готово 8 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.forest_steppe.sow: TODO (R2/R3) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.forest_steppe.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.forest_steppe.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.forest_steppe.sow: TODO (R2/R3) |
| Буряк цукровий | ✅ готово | STUB: календар forest_steppe — заглушка без джерела (STUB_NO_SOURCE); довжини фаз FAO-56 Т11 для іншого регіону (Sugarbeet, April, Idaho USA) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.forest_steppe.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.forest_steppe.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

### Зона `polissia` (allow_stubs=True): готово 8 з 20

| Культура | Статус | Причини / прапорці |
|---|---|---|
| Пшениця озима | ✅ готово | фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11 |
| Ячмінь озимий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1) |
| Жито озиме | ⛔ заблоковано | kc_ini: TODO (жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура)); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі) |
| Ячмінь ярий | ⛔ заблоковано | ky: TODO (ячменю немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Овес | ⛔ заблоковано | ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Пшениця яра | ✅ готово | сівба: поріг гороху (4 °C) застосовано до ранніх ярих: джерела дають «ранні строки, щойно дозволяє стан ґрунту» без температури; довжини фаз FAO-56 Т11 для іншого регіону (Barley/Oats/Wheat, March/Apr, 35–45°) |
| Кукурудза | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35]) |
| Кукурудза на силос | ⛔ заблоковано | kc_mid: TODO (силосної кукурудзи немає в Табл. 12); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (Maize 1.25 — для зерна; для силосу джерела немає); calendar.polissia.sow: TODO (R2/R3) |
| Соняшник | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Sunflower, April/May, Medit.; California) |
| Сорго | ⛔ заблоковано | calendar.polissia.sow: TODO (R2/R3) |
| Просо | ⛔ заблоковано | ky: TODO (проса немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Соя | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote)); stages_days: середина діапазону без примітки FAO |
| Горох | ✅ готово | довжини фаз FAO-56 Т11 для іншого регіону (Peas, May, Europe (Табл. 11 не розрізняє fresh/dry)) |
| Нут | ⛔ заблоковано | stages_days: TODO (нуту немає в Табл. 11); ky: TODO (нуту немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Ріпак озимий | ⛔ заблоковано | ky: TODO (ріпаку немає в Табл. 24 / FAO-66 Табл. 1) |
| Льон | ⛔ заблоковано | ky: TODO (льону немає в Табл. 24 / FAO-66 Табл. 1); calendar.polissia.sow: TODO (R2/R3) |
| Буряк цукровий | ✅ готово | STUB: календар polissia — заглушка без джерела (STUB_NO_SOURCE); довжини фаз FAO-56 Т11 для іншого регіону (Sugarbeet, April, Idaho USA) |
| Люцерна | ⛔ заблоковано | stages_days: TODO (Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури); calendar.polissia.sow: TODO (R2/R3) |
| Чорний пар | ✅ готово |  |
| Сидерат (гірчиця/редька олійна) | ⛔ заблоковано | kc_ini: TODO (у Табл. 12 є лише Radish (овочева) — інша культура); kc_mid: TODO (немає в джерелі); kc_end: TODO (немає в джерелі); stages_days: TODO (немає в джерелі); ky: TODO (немає в джерелі); zr_m: TODO (немає в джерелі); p: TODO (немає в джерелі); calendar.polissia.sow: TODO (R2/R3) |

**Чекають джерела Ky:** Ячмінь озимий, Жито озиме, Ячмінь ярий, Овес, Кукурудза на силос, Просо, Нут, Ріпак озимий, Льон, Сидерат (гірчиця/редька олійна)

## Культура × параметр × джерело

| Культура | Параметр | Значення | Джерело | Примітка |
|---|---|---|---|---|
| Пшениця озима | kc_ini | 0.4 | FAO56_T12 | Winter Wheat — with frozen soils (зими в Україні з промерзанням) |
| Пшениця озима | kc_mid | 1.15 | FAO56_T12 |  |
| Пшениця озима | kc_end | 0.25 | FAO56_T12 | діапазон 0.25–0.4, прим. 10 → нижня (механізоване) |
| Пшениця озима | stages_days | [160, 75, 75, 25] | FAO56_T11 | Winter Wheat, Idaho USA, сівба October; не Україна |
| Пшениця озима | ky | 1.0 | FAO66_T2 | рішення 12.11: 1.00 за FAO-66 Табл. 2 (FAO Tr-0000); FAO-56 Т24 і FAO-66 Т1 дають 1.05 — у чутливості |
| Пшениця озима | zr_m | 1.8 | FAO56_T22 | діапазон 1.5–1.8, верхня межа |
| Пшениця озима | p | 0.55 | FAO56_T22 |  |
| Пшениця озима | calendar.steppe.sow | 09-28 | IZZ2018_OZYMI | |
| Пшениця озима | calendar.forest_steppe.sow | 09-18 | YURIEV2023_OSIN | |
| Пшениця озима | calendar.polissia.sow | 09-18 | ISGP2026_POSIV | |
| Ячмінь озимий | kc_ini | 0.3 | FAO56_T12 | Barley; Kc_ini з рядка групи i. Cereals |
| Ячмінь озимий | kc_mid | 1.15 | FAO56_T12 |  |
| Ячмінь озимий | kc_end | 0.25 | FAO56_T12 |  |
| Ячмінь озимий | stages_days | **TODO** | FAO56_T11 | у Табл. 11 немає рядка для озимого ячменю помірних широт |
| Ячмінь озимий | ky | **TODO** | FAO56_T24 | ячменю немає в Табл. 24 / FAO-66 Табл. 1 |
| Ячмінь озимий | zr_m | 1.5 | FAO56_T22 | Barley 1.0–1.5, верхня межа |
| Ячмінь озимий | p | 0.55 | FAO56_T22 |  |
| Ячмінь озимий | calendar.steppe.sow | 09-25 | IZZ2018_OZYMI | |
| Ячмінь озимий | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Ячмінь озимий | calendar.polissia.sow | 09-25 | ISGP2026_POSIV | |
| Жито озиме | kc_ini | **TODO** | FAO56_T12 | жита (зернового) немає в Табл. 12 (є лише Rye Grass hay — інша культура) |
| Жито озиме | kc_mid | **TODO** | FAO56_T12 |  |
| Жито озиме | kc_end | **TODO** | FAO56_T12 |  |
| Жито озиме | stages_days | **TODO** | FAO56_T11 |  |
| Жито озиме | ky | **TODO** | FAO56_T24 |  |
| Жито озиме | zr_m | **TODO** | FAO56_T22 |  |
| Жито озиме | p | **TODO** | FAO56_T22 |  |
| Жито озиме | calendar.steppe.sow | 09-20 | IZZ2018_OZYMI | |
| Жито озиме | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Жито озиме | calendar.polissia.sow | 09-15 | ISGP2026_POSIV | |
| Ячмінь ярий | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Ячмінь ярий | kc_mid | 1.15 | FAO56_T12 |  |
| Ячмінь ярий | kc_end | 0.25 | FAO56_T12 |  |
| Ячмінь ярий | stages_days | [20, 25, 60, 30] | FAO56_T11 | Barley/Oats/Wheat, March/Apr, 35–45° широти; Україна 45–52° |
| Ячмінь ярий | ky | **TODO** | FAO56_T24 | ячменю немає в Табл. 24 / FAO-66 Табл. 1 |
| Ячмінь ярий | zr_m | 1.5 | FAO56_T22 |  |
| Ячмінь ярий | p | 0.55 | FAO56_T22 |  |
| Ячмінь ярий | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Ячмінь ярий | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Ячмінь ярий | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Овес | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Овес | kc_mid | 1.15 | FAO56_T12 |  |
| Овес | kc_end | 0.25 | FAO56_T12 |  |
| Овес | stages_days | [20, 25, 60, 30] | FAO56_T11 | Barley/Oats/Wheat, March/Apr, 35–45° |
| Овес | ky | **TODO** | FAO56_T24 | вівса немає в Табл. 24 / FAO-66 Табл. 1 |
| Овес | zr_m | 1.5 | FAO56_T22 |  |
| Овес | p | 0.55 | FAO56_T22 |  |
| Овес | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Овес | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Овес | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Пшениця яра | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Пшениця яра | kc_mid | 1.15 | FAO56_T12 |  |
| Пшениця яра | kc_end | 0.25 | FAO56_T12 | 0.25–0.4, прим. 10 → нижня |
| Пшениця яра | stages_days | [20, 25, 60, 30] | FAO56_T11 | Barley/Oats/Wheat, March/Apr, 35–45° |
| Пшениця яра | ky | 1.15 | FAO56_T24 | = FAO66_T1 = FAO66_T2 |
| Пшениця яра | zr_m | 1.5 | FAO56_T22 |  |
| Пшениця яра | p | 0.55 | FAO56_T22 |  |
| Пшениця яра | calendar.steppe.sow | dynamic | ISGP2026_VPR | |
| Пшениця яра | calendar.forest_steppe.sow | dynamic | ISGP2026_VPR | |
| Пшениця яра | calendar.polissia.sow | dynamic | ISGP2026_VPR | |
| Кукурудза | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Кукурудза | kc_mid | 1.2 | FAO56_T12 |  |
| Кукурудза | kc_end | 0.35 | FAO56_T12 | 0.60–0.35, прим. 11 → друге (досушування в полі) |
| Кукурудза | stages_days | [30, 40, 50, 50] | FAO56_T11 | Maize (grain), Idaho USA, April; baseline v0 мав [25,40,45,35] |
| Кукурудза | ky | 1.25 | FAO56_T24 |  |
| Кукурудза | zr_m | 1.7 | FAO56_T22 | 1.0–1.7, верхня |
| Кукурудза | p | 0.55 | FAO56_T22 |  |
| Кукурудза | calendar.steppe.sow | dynamic | ISGP2026_VPR | |
| Кукурудза | calendar.forest_steppe.sow | dynamic | ISGP2026_VPR | |
| Кукурудза | calendar.polissia.sow | dynamic | ISGP2026_VPR | |
| Кукурудза на силос | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Кукурудза на силос | kc_mid | **TODO** | FAO56_T12 | силосної кукурудзи немає в Табл. 12 |
| Кукурудза на силос | kc_end | **TODO** | FAO56_T12 |  |
| Кукурудза на силос | stages_days | **TODO** | FAO56_T11 |  |
| Кукурудза на силос | ky | **TODO** | FAO56_T24 | Maize 1.25 — для зерна; для силосу джерела немає |
| Кукурудза на силос | zr_m | 1.7 | FAO56_T22 | рядок Maize, Field — коренева система та сама |
| Кукурудза на силос | p | 0.55 | FAO56_T22 |  |
| Кукурудза на силос | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Кукурудза на силос | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Кукурудза на силос | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Соняшник | kc_ini | 0.35 | FAO56_T12 | Kc_ini групи h. Oil Crops |
| Соняшник | kc_mid | 1.0 | FAO56_T12 | 1.0–1.15, прим. 9 → нижня (богара) |
| Соняшник | kc_end | 0.35 | FAO56_T12 |  |
| Соняшник | stages_days | [25, 35, 45, 25] | FAO56_T11 | Sunflower, April/May, Medit.; California |
| Соняшник | ky | 0.95 | FAO56_T24 |  |
| Соняшник | zr_m | 1.5 | FAO56_T22 | 0.8–1.5, верхня |
| Соняшник | p | 0.45 | FAO56_T22 |  |
| Соняшник | calendar.steppe.sow | dynamic | ISGP2026_VPR | |
| Соняшник | calendar.forest_steppe.sow | dynamic | ISGP2026_VPR | |
| Соняшник | calendar.polissia.sow | dynamic | ISGP2026_VPR | |
| Сорго | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Сорго | kc_mid | 1.05 | FAO56_T12 | Sorghum grain 1.00–1.10 без примітки → середина |
| Сорго | kc_end | 0.55 | FAO56_T12 |  |
| Сорго | stages_days | [20, 35, 40, 30] | FAO56_T11 | Sorghum, May/June, USA/Pakis./Med. |
| Сорго | ky | 0.9 | FAO56_T24 |  |
| Сорго | zr_m | 2.0 | FAO56_T22 | grain 1.0–2.0, верхня |
| Сорго | p | 0.55 | FAO56_T22 |  |
| Сорго | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Сорго | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Сорго | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Просо | kc_ini | 0.3 | FAO56_T12 | Kc_ini групи i. Cereals |
| Просо | kc_mid | 1.0 | FAO56_T12 |  |
| Просо | kc_end | 0.3 | FAO56_T12 |  |
| Просо | stages_days | [20, 30, 55, 35] | FAO56_T11 | Millet, April, Central USA |
| Просо | ky | **TODO** | FAO56_T24 | проса немає в Табл. 24 / FAO-66 Табл. 1 |
| Просо | zr_m | 2.0 | FAO56_T22 | 1.0–2.0, верхня |
| Просо | p | 0.55 | FAO56_T22 |  |
| Просо | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Просо | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Просо | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Соя | kc_ini | 0.4 | FAO56_T12 | Kc_ini групи e. Legumes |
| Соя | kc_mid | 1.15 | FAO56_T12 |  |
| Соя | kc_end | 0.5 | FAO56_T12 |  |
| Соя | stages_days | [20, 32, 60, 25] | FAO56_T11 | Soybeans, May, Central USA; Ldev 30/35 без примітки → 32.5, ціле вниз (rules_of_choice.range_no_footnote) |
| Соя | ky | 0.85 | FAO56_T24 |  |
| Соя | zr_m | 1.3 | FAO56_T22 | 0.6–1.3, верхня |
| Соя | p | 0.5 | FAO56_T22 |  |
| Соя | calendar.steppe.sow | dynamic | ISGP2026_VPR | |
| Соя | calendar.forest_steppe.sow | dynamic | ISGP2026_VPR | |
| Соя | calendar.polissia.sow | dynamic | ISGP2026_VPR | |
| Горох | kc_ini | 0.4 | FAO56_T12 | Peas Dry/Seed; Kc_ini групи e. Legumes |
| Горох | kc_mid | 1.15 | FAO56_T12 |  |
| Горох | kc_end | 0.3 | FAO56_T12 | Dry/Seed |
| Горох | stages_days | [15, 25, 35, 15] | FAO56_T11 | Peas, May, Europe (Табл. 11 не розрізняє fresh/dry) |
| Горох | ky | 1.15 | FAO56_T24 | у джерелі надруковано «1,15» |
| Горох | zr_m | 1.0 | FAO56_T22 | Dry/Seed 0.6–1.0, верхня |
| Горох | p | 0.4 | FAO56_T22 | Dry/Seed |
| Горох | calendar.steppe.sow | dynamic | ISGP2026_VPR | |
| Горох | calendar.forest_steppe.sow | dynamic | ISGP2026_VPR | |
| Горох | calendar.polissia.sow | dynamic | ISGP2026_VPR | |
| Нут | kc_ini | 0.4 | FAO56_T12 | Kc_ini групи e. Legumes |
| Нут | kc_mid | 1.0 | FAO56_T12 |  |
| Нут | kc_end | 0.35 | FAO56_T12 |  |
| Нут | stages_days | **TODO** | FAO56_T11 | нуту немає в Табл. 11 |
| Нут | ky | **TODO** | FAO56_T24 | нуту немає в Табл. 24 / FAO-66 Табл. 1 |
| Нут | zr_m | 1.0 | FAO56_T22 | 0.6–1.0, верхня |
| Нут | p | 0.5 | FAO56_T22 |  |
| Нут | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Нут | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Нут | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Ріпак озимий | kc_ini | 0.35 | FAO56_T12 | Kc_ini групи h. Oil Crops |
| Ріпак озимий | kc_mid | 1.0 | FAO56_T12 | Rapeseed, Canola 1.0–1.15, прим. 9 → нижня |
| Ріпак озимий | kc_end | 0.35 | FAO56_T12 |  |
| Ріпак озимий | stages_days | **TODO** | FAO56_T11 | ріпаку немає в Табл. 11 |
| Ріпак озимий | ky | **TODO** | FAO56_T24 | ріпаку немає в Табл. 24 / FAO-66 Табл. 1 |
| Ріпак озимий | zr_m | 1.5 | FAO56_T22 | 1.0–1.5, верхня |
| Ріпак озимий | p | 0.6 | FAO56_T22 |  |
| Ріпак озимий | calendar.steppe.sow | 09-05 | IZZ2018_OZYMI | |
| Ріпак озимий | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Ріпак озимий | calendar.polissia.sow | 08-20 | ISGP2026_POSIV | |
| Льон | kc_ini | 0.35 | FAO56_T12 | Kc_ini групи g. Fibre Crops |
| Льон | kc_mid | 1.1 | FAO56_T12 |  |
| Льон | kc_end | 0.25 | FAO56_T12 |  |
| Льон | stages_days | [25, 35, 50, 40] | FAO56_T11 | Flax, April, Europe |
| Льон | ky | **TODO** | FAO56_T24 | льону немає в Табл. 24 / FAO-66 Табл. 1 |
| Льон | zr_m | 1.5 | FAO56_T22 | 1.0–1.5, верхня |
| Льон | p | 0.5 | FAO56_T22 |  |
| Льон | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Льон | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Льон | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Буряк цукровий | kc_ini | 0.35 | FAO56_T12 |  |
| Буряк цукровий | kc_mid | 1.2 | FAO56_T12 |  |
| Буряк цукровий | kc_end | 0.7 | FAO56_T12 | прим. 5: без поливу в останній місяць; до 1.0 за значних дощів |
| Буряк цукровий | stages_days | [50, 40, 50, 40] | FAO56_T11 | Sugarbeet, April, Idaho USA |
| Буряк цукровий | ky | 1.0 | FAO56_T24 |  |
| Буряк цукровий | zr_m | 1.2 | FAO56_T22 | 0.7–1.2, верхня |
| Буряк цукровий | p | 0.55 | FAO56_T22 |  |
| Буряк цукровий | calendar.steppe.sow | 04-15 (stub) | STUB_NO_SOURCE | |
| Буряк цукровий | calendar.forest_steppe.sow | 04-15 (stub) | STUB_NO_SOURCE | |
| Буряк цукровий | calendar.polissia.sow | 04-15 (stub) | STUB_NO_SOURCE | |
| Люцерна | kc_ini | 0.4 | FAO56_T12 | Alfalfa Hay — averaged cutting effects |
| Люцерна | kc_mid | 0.95 | FAO56_T12 | averaged cutting effects (прим. 13) |
| Люцерна | kc_end | 0.9 | FAO56_T12 |  |
| Люцерна | stages_days | **TODO** | FAO56_T11 | Табл. 11: ini 10, dev 30, далі var. — сезон від останнього −4°C навесні до першого −4°C восени; потрібна реалізація багаторічної культури |
| Люцерна | ky | 1.1 | FAO56_T24 |  |
| Люцерна | zr_m | 2.0 | FAO56_T22 | for hay 1.0–2.0, верхня |
| Люцерна | p | 0.55 | FAO56_T22 |  |
| Люцерна | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Люцерна | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Люцерна | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |
| Чорний пар | kc_method | fao56_annex7 | FAO56_CH11 | Kc голого ґрунту = Kc_ini за рівн. 7-3 (FAO56_A7) з погоди вікна; див. model/soils.yaml |
| Чорний пар | calendar.steppe.sow | none | FAO56_CH11 | |
| Чорний пар | calendar.forest_steppe.sow | none | FAO56_CH11 | |
| Чорний пар | calendar.polissia.sow | none | FAO56_CH11 | |
| Сидерат (гірчиця/редька олійна) | kc_ini | **TODO** | FAO56_T12 | у Табл. 12 є лише Radish (овочева) — інша культура |
| Сидерат (гірчиця/редька олійна) | kc_mid | **TODO** | FAO56_T12 |  |
| Сидерат (гірчиця/редька олійна) | kc_end | **TODO** | FAO56_T12 |  |
| Сидерат (гірчиця/редька олійна) | stages_days | **TODO** | FAO56_T11 |  |
| Сидерат (гірчиця/редька олійна) | calendar.steppe.sow | **TODO** | NAAN_R2R3 | |
| Сидерат (гірчиця/редька олійна) | calendar.forest_steppe.sow | **TODO** | NAAN_R2R3 | |
| Сидерат (гірчиця/редька олійна) | calendar.polissia.sow | **TODO** | NAAN_R2R3 | |

**Джерела**

- `FAO56_T11` — FAO-56 (Allen et al., 1998), Table 11 — Lengths of crop development stages. https://www.fao.org/4/X0490E/x0490e0b.htm
- `FAO56_T12` — FAO-56, Table 12 — Single (time-averaged) crop coefficients Kc. https://www.fao.org/4/X0490E/x0490e0b.htm
- `FAO56_T22` — FAO-56, Table 22 — Max effective rooting depth Zr and depletion fraction p. https://www.fao.org/4/X0490E/x0490e0e.htm
- `FAO56_T24` — FAO-56, Table 24 — Seasonal yield response factors Ky (from FAO-33). https://www.fao.org/4/X0490E/x0490e0e.htm
- `FAO66_T1` — FAO-66 (Steduto et al., 2012), ch. 2, Table 1 — Seasonal Ky values from FAO-33. https://www.fao.org/4/i2800e/i2800e02.pdf
- `FAO66_T2` — FAO-66, ch. 2, Table 2 — Ky FAO-33 vs IAEA, column FAO Tr-0000. https://www.fao.org/4/i2800e/i2800e02.pdf
- `FAO56_CH11` — FAO-56, Chapter 11 — ETc during non-growing periods: bare soil / residue Kc = Kc_ini (Fig. 29–30). https://www.fao.org/4/X0490E/x0490e0h.htm
- `FAO56_A7` — FAO-56, Annex 7 — Eq. 7-1…7-10, parameters reproducing Fig. 29/30a/30b. https://www.fao.org/4/X0490E/x0490e0o.htm
- `NAAN_R2R3` — TODO — календарі сівби/збирання НААН по зонах, передають R2/R3
- `ISGP2026_POSIV` — Рижук С.М., Савчук О.І. та ін. Рекомендації щодо сівби озимих… ІСГП НААН; Житомирська ОДА, 2026. https://www.isgpnaan.org/upload/rekomendatsii-posiv-2026.pdf
- `ISGP2026_VPR` — Рижук С.М., Савчук О.І. та ін. Рекомендації з проведення весняно-польових робіт 2026. ІСГП НААН, 2026. https://isgpnaan.org/upload/1-rekomendatsii-vpr-2026.pdf
- `YURIEV2023_OSIN` — Особливості проведення осіннього комплексу польових робіт… Інститут рослинництва ім. В.Я. Юр'єва НААН, 2023, розд. 5, с. 18. https://yuriev.com.ua/assets/files/navchalni-posibnyky/osinnij-kompleks-2023.pdf
- `YURIEV2019_VPR` — Агротехнологічна стратегія проведення весняно-польових робіт… 2019. Інститут рослинництва ім. В.Я. Юр'єва НААН. https://yuriev.com.ua/assets/files/knigi/vpr-2019.pdf
- `IZZ2018_OZYMI` — Вожегова Р.А., Заєць С.О., Коваленко А.М. та ін. Агротехнологічні вимоги до сівби озимих культур під урожай 2019 року у Південному Степу України. ІЗЗ НААН, 2018. https://dspace.mnau.edu.ua/jspui/bitstream/123456789/4638/1/Ahrotekhnolohichni%20umovy_2019.pdf
- `HLS_PHENO` — Наші дані: HLS 30 м, 250 полів, 2016–2025 — data/raw/hls_phenology_by_oblast.csv (клас W, медіана областей зони); фази з NDVI полів, не з агрономічних джерел
- `POWER_TSOIL1` — NASA POWER daily, community=AG, TSOIL1 — Soil Temperatures Layer 1, 0.018–0.0988 m (MERRA-2); data/raw/power/tsoil_<вузол>.csv (scripts/fetch_power.py --tsoil)
- `BASELINE_V0` — baseline_model.py v0 — ЗАГЛУШКА без джерела (орієнтовний календар); дозволена лише з прапорцем --allow-stubs і лише для дат календаря
- `STUB_NO_SOURCE` — заглушка без джерела — лише дати календаря, лише з --allow-stubs, лише для прототипу до 13.11.2026; дата = місяць сівби з того самого рядка FAO-56 Т11, що й довжини фаз, день 15 (або 01 для «March/Apr»)