# Changelog

## [1.0.32] - 2026-09-13

### Changed
- **Rendering Engine Overhaul:** Replaced the fragile solid-color heuristic and legacy Floyd-Steinberg error diffusion with an **Edge-Preserving Atkinson Error Diffusion** pipeline. Error propagation is capped at 75% ($6/8$) with 25% discarded, preventing muddy midtone cascades and directional "worm" artifacts.
- **Precomputed 3D Color LUT:** Introduced an in-memory $32 \times 32 \times 32$ perceptual color lookup table initialized at container startup, executing perceptually weighted Euclidean distance mapping ($2\Delta R^2 + 4\Delta G^2 + 3\Delta B^2$) across the 6-color Spectra palette in sub-second time.
- **Edge-Gated Stroke Locking:** Integrated spatial edge detection (`ImageFilter.FIND_EDGES`) that halts error diffusion across font contours, temperature readouts, and icon glyphs (`edge > 30`), locking typography to solid, high-contrast palette values without grain or stroke erosion.
- **Optimized Dynamic Range & Vibrancy:** Replaced heavy gamma lifting with a balanced tone curve: mild 5% shadow expansion ($\gamma = 1.05$), $1.25\times$ contrast acutance, and $1.35\times$ color boost. This renders pint glass borders in solid black, deepens amber beer fills, and prevents pastel background bleaching.

### Removed
- Removed all hardcoded pixel coordinate overrides, banner width splitting (`BANNER_WIDTH`), and color distance heuristics (`dist_bg`) that previously caused diagonal tears and inverted shadow wedges.

### Fixed
- Resolved washed-out white typography on light-colored cards (*Ginette Bio White*, *Leffe Blanche*) and dark slate banners (*Trooper Original*, *Camden Hells*).
- Eliminated faint, indistinct glass borders in the serving counter column.
- Fixed 3D barrel lighting clipping across all 114 catalog beers.

## [1.0.31_6] - 2026-09-13

### Added
- **Dynamic Webhook Injections:** Support for optional JSON payloads (`{"beer_name": "..."}`) via POST to inject overrides directly into the Lovelace card via `setConfig()` in browser memory, bypassing live sensor polling and entity locks.
- **Branded Font Color Mapping:** Automatic detection and palette mapping for non-white typography, accurately rendering gold/yellow text (Stella Artois, Franziskaner, Hertog Jan, Singha) and red text (Trooper) on dark banners.
- **Timestamped Logging:** Standardized ISO timestamps (`[YYYY-MM-DD HH:MM:SS]`) across all internal application events, auth transitions, and HTTP server logs.
- **Add-on Repository Metadata:** Added the `url:` key in `config.yaml` linking directly to GitHub for seamless in-app navigation from the Home Assistant Add-on UI.
- **Divider Separation for Light Banners:** Automatic 1px vertical border insertion for pure white cards (e.g., Leffe Blanche, Ginette Bio White) to cleanly delineate the banner from the glass panel.

### Fixed
- **Host Volume Mapping:** Added `map: - config:rw` to `config.yaml`, ensuring output images (`perfectdraft_card.png`, `perfectdraft_card.bin`, and `debug_screenshot.png`) write directly to `/config/www` on the host rather than private container storage.
- **Playwright Authentication Handling:** Resolved DOM-load race condition during login by introducing explicit username field polling and session state caching (`/data/auth_state.json`).
- **Card Selector Robustness:** Broadened locator from `ha-card:has-text('PerfectDraft')` to `perfectdraft-card, perfectdraft-pro-card, ha-card`, preventing timeout crashes when the card is in a disconnected or "No keg detected" state.
- **Banner Bleach & Text Vanishing Bug:** Replaced fragile global luminance thresholds with relative background distance formulas (`dist_bg`), eliminating diagonal white tears across saturated red, green, blue, and amber banners.
- **Banner Boundary Overflow:** Replaced dynamic edge-scanning with a deterministic 234px width boundary, preventing right-pane bleed and false audit warnings on light-themed kegs.
- **SVG Shadow Inversion:** Neutralized soft gradient drop-shadows under fallback lettered kegs (A, B, C...), removing jagged black triangular artifacts.
- **Rounded Corner Clipping:** Squared banner margin checks to prevent white card backdrops from leaking through rounded container corners.
- **Internal Docker Network Routing:** Updated default dashboard URL from `127.0.0.1` to the internal Docker DNS hostname (`http://homeassistant:8123`) to prevent connection-refused errors.
- **Syntax Parsing Collisions:** Resolved duplicate trailing code blocks and server execution syntax errors in `render_server.py`.

## 1.0.28
- **UI Configuration**: Moved Home Assistant username, password, and dashboard URL to the native Add-on Configuration tab (`options.json`).
- **Display Fix**: Removed corner cutouts to provide clean, full-bleed banner framing across all edges.
- **Icon Contrast**: Deepened neutral glass outlines and empty pint contours for crisp dithering against the white canvas.
- **Brand Theming**: Integrated HSV polar color analysis to automatically map dark-on-light (Leffe Blonde) and light-on-dark (BrewDog, Stella) themes.

## 1.0.27
- **Hardware Quantization**: Dynamic 6-color Spectra 6 palette mapping.
- **Typography Engine**: Zero-error background pre-snapping for sharp typography and icon rendering.

## 1.0.26
- **Fix**: Full-bleed banner edges eliminating corner cutouts.
- **Enhancement**: Contrast curves for mug glass rims and empty pint outlines.
- **Dynamic Themes**: HSV-based auto-classification for all beer styles and brands.

## 1.0.25
- **Feature**: Added Leffe Blonde gold/yellow support with black text inversion.
- **Fix**: Resolved Chromium session cache lockup.

## 1.0.0
- Initial multi-pigment Floyd-Steinberg renderer for Waveshare 4 inch Spectra 6 E-Ink Display.
