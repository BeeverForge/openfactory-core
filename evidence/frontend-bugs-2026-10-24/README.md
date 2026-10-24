# Frontend bug hunt: visual evidence

Browser captures and observations for issues #1102–#1111, reproduced against commit `8958262abfccd7a6c3c3ed957b5b376a38ba36a4` on 2026-10-24.

Each PNG contains actual screenshots, before/after captions, and a separate box of measured diagnostics. Response delays, the pending chart script, the failed Save request, and the seeded journal are explicitly identified in their respective reports.

Environment: Playwright 1.64.1 / Chromium 156; isolated local Uvicorn panel; disposable registry, SQLite board and journals. No coding agents or durable jobs were started.

| Issue | Visual evidence |
| --- | --- |
| [#1102](https://github.com/Open-Factory-Digital/openfactory-core/issues/1102) | [The visible card and the POST target disagree](issue-1102.png) |
| [#1103](https://github.com/Open-Factory-Digital/openfactory-core/issues/1103) | [One double-click created two cards](issue-1103.png) |
| [#1104](https://github.com/Open-Factory-Digital/openfactory-core/issues/1104) | [A completed POST erased a newer unsent draft](issue-1104.png) |
| [#1105](https://github.com/Open-Factory-Digital/openfactory-core/issues/1105) | [A card deep link becomes a board link and loses the card on reload](issue-1105.png) |
| [#1106](https://github.com/Open-Factory-Digital/openfactory-core/issues/1106) | [The phone viewport hides Cost and Board beyond its right edge](issue-1106.png) |
| [#1107](https://github.com/Open-Factory-Digital/openfactory-core/issues/1107) | [Tab skips the project tile and pickup switch](issue-1107.png) |
| [#1108](https://github.com/Open-Factory-Digital/openfactory-core/issues/1108) | [Keyboard focus escaped the modal and activated the background theme](issue-1108.png) |
| [#1109](https://github.com/Open-Factory-Digital/openfactory-core/issues/1109) | [The Cost overlay has no close control while loading](issue-1109.png) |
| [#1110](https://github.com/Open-Factory-Digital/openfactory-core/issues/1110) | [Revisiting Logs hides a new run that reload reveals](issue-1110.png) |
| [#1111](https://github.com/Open-Factory-Digital/openfactory-core/issues/1111) | [Save failed, but the form shows no error](issue-1111.png) |

[Complete measured observations](observations.json)

The evidence is hosted on a separate branch so the issue reports can embed stable image URLs.
