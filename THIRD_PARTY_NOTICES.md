# Avvisi sulle componenti di terze parti / Third-party notices

MeshLens (GPL-3.0, Copyright © 2026 iw8ffg) include o usa le componenti seguenti, ciascuna con la propria licenza. / MeshLens includes or uses the following components, each under its own license.

## Python (versione installata / installed build)

Elenco generato con `pip-licenses` sull'ambiente del progetto, limitato alle dipendenze di esecuzione. / Generated with `pip-licenses` against the project environment, limited to runtime dependencies.

| Pacchetto / Package | Versione / Version | Licenza / License |
|---|---|---|
| annotated-doc | 0.0.7 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.2.0 | MIT |
| bleak | 3.1.0 | MIT |
| certifi | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.165.0 | MIT |
| h11 | 0.16.0 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.9.0 | MIT |
| httpx | 0.28.1 | BSD License |
| idna | 3.20 | BSD-3-Clause |
| meshtastic | 2.7.11 | GNU General Public License v3 (GPLv3) |
| numpy | 2.5.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| paho-mqtt | 2.2.0 | EPL-2.0 OR BSD-3-Clause |
| pmtiles | 3.8.1 | BSD License |
| protobuf | 7.36.2 | 3-Clause BSD License |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.4 | MIT |
| pydantic_core | 2.50.5 | MIT |
| Pypubsub | 4.0.7 | BSD-2-Clause |
| pyserial | 3.5 | BSD License |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT License |
| requests | 2.34.2 | Apache Software License |
| shapely | 2.2.0 | BSD-3-Clause |
| starlette | 1.10.0 | BSD-3-Clause |
| tabulate | 0.9.0 | MIT License |
| typing-inspection | 0.4.5 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchfiles | 1.3.0 | MIT License |
| websockets | 17.4 | BSD-3-Clause |
| winrt-runtime | 4.2.0 | MIT |
| winrt-Windows.Devices.Bluetooth | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Devices.Bluetooth.Advertisement | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Devices.Bluetooth.GenericAttributeProfile | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Devices.Enumeration | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Devices.Radios | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Foundation | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Foundation.Collections | 4!10.0.28000.2957 | MIT |
| winrt-Windows.Storage.Streams | 4!10.0.28000.2957 | MIT |
| pystray | (build installata) | LGPL-3.0 |
| Pillow | (build installata) | MIT-CMU (HPND) |

`meshtastic` è GPL-3.0, compatibile con la licenza di MeshLens. / `meshtastic` is GPL-3.0, compatible with MeshLens' license.

## JavaScript (interfaccia, dipendenze di produzione / UI, production dependencies)

| Pacchetto / Package | Versione / Version | Licenza / License |
|---|---|---|
| @protomaps/basemaps | 5.7.2 | BSD-3-Clause |
| maplibre-gl | 6.19.0 | BSD-3-Clause |

## Strumenti e risorse / Tools and assets

| Componente / Component | Licenza / License | Note |
|---|---|---|
| [go-pmtiles](https://github.com/protomaps/go-pmtiles) | BSD-3-Clause | incluso come `tools\pmtiles.exe` / bundled as `tools\pmtiles.exe` |
| Noto Sans (Regular, Medium, Italic) | SIL OFL-1.1 | glifi in `web/public/map-assets/fonts`, Copyright dei Noto Project Authors, via [protomaps/basemaps-assets](https://github.com/protomaps/basemaps-assets) |
| Sprite Protomaps / tangrams icons | MIT | `web/public/map-assets/sprites` |
| [Natural Earth](https://www.naturalearthdata.com) | Pubblico dominio / Public domain | confini delle nazioni (`countries.geojson`) / country borders |

## Dati / Data

- **OpenStreetMap**: © OpenStreetMap contributors, dati sotto licenza [ODbL 1.0](https://opendatacommons.org/licenses/odbl/). Le mappe (Protomaps PMTiles e OpenFreeMap) derivano da questi dati; è richiesta l'attribuzione. / Maps (Protomaps PMTiles and OpenFreeMap) derive from this data; attribution is required.
