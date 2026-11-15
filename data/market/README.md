# data/market — ринок (ТЗ A4). Заповнюють люди, модель лише перевіряє формат.

- `buyers.csv`: buyer_id, type (elevator|port|processor|feed_mill), name, lat, lon, crop (crop_id), price_uah_t, basis (EXW|CPT|FCA), date, source
- `transport.yaml`: tariff_uah_t_km, fixed_uah_t, road_factor — кожне `{value, source}`
- ціни однією цифрою на культуру — `data/raw/prices.csv` (див. data/raw/PRICES_README.md)

Порожні файли → «логістику не враховано»; немає цін → дохід не рахується, оптимізатор ранжує за відносним врожаєм.
