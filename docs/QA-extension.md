# Chrome extension: manual QA checklist

Build: `cd extension && npm install && npm run build`, then chrome://extensions → Developer mode → Load unpacked → `extension/dist`.
Start the backend first: `cd backend && uv run reviewring serve`.

| # | Check | Expected |
|---|---|---|
| 1 | Load unpacked | No errors on the extension card; the ReviewRing icon appears in the toolbar. |
| 2 | Open a Google Maps place that has been analysed | The badge shows the level, the rating without rings and the analysis age. |
| 3 | Open a place that hasn't been analysed | The badge says "Check reviews". |
| 4 | Click the badge | The side panel opens with the estimated cost, the budget left this month and this hour, and a "Run analysis" button. Nothing is searched yet. |
| 5 | Side panel open fails (Chrome refuses a relayed open) | The badge changes to "Click the ReviewRing icon for details"; clicking the toolbar icon opens the panel. |
| 6 | Click "Run analysis" | Progress with a searches counter; at the end: level, adjusted rating, rings found, top 3 evidence sentences and "Open full report". |
| 7 | Move between places (click another result) | The badge updates once per place. |
| 8 | Pan and zoom the map without changing place | No new lookups (check the backend log / Network tab of the service worker): the badge doesn't flicker. |
| 9 | Stop the backend and open a place | The badge says "Backend not running"; the side panel explains how to start it. |
| 10 | Backend in demo mode | The side panel says demo mode can't match real Maps pages and links to the web app demo. |
| 11 | Options: presentation mode on | The side panel shows pseudonymized titles. |
| 12 | Options: a non-local backend URL | Refused with a message. |
