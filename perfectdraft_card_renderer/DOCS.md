# PerfectDraft Card Renderer

This add-on captures the PErfectDraft integration dashboard card in HomeAssistant Lovelace, processes it with **Edge-Preserving Atkinson error diffusion** for a 4-inch 6-color Spectra 6 E-Ink display (Black, White, Yellow, Red, Blue, Green), and writes both the visual PNG preview and raw 4-bit packed ESPHome binary directly to your Home Assistant `www` directory.

---

## Prerequisites

* A Waveshare Spectra 6 (E6) E-Ink display managed via ESPHome.
* A configured Lovelace dashboard containing your PerfectDraft card (e.g., `/dashboard-entertainment/0`).
* A dedicated Home Assistant local user account (a non-admin `kiosk` user is recommended).

---

## Installation & Setup

1. Add this repository URL to your Home Assistant Add-on Store:
   ```text
   [https://github.com/TheStork239/ha-perfectdraft-display-addons](https://github.com/TheStork239/ha-perfectdraft-display-addons)
   ```
2. Install the **PerfectDraft Card Renderer** add-on.
3. Open the add-on's **Configuration** tab:
   * Enter your Home Assistant username (`ha_username`).
   * Enter your user password (`ha_password`).
   * Verify the internal dashboard URL:
     ```text
     http://homeassistant:8123/dashboard-entertainment/0
     ```
4. Click **Save**, navigate to the **Info** tab, and click **Start**.

---

## Configuration Options

| Option | Type | Default | Description |
|---|---|---|---|
| `ha_username` | string | `kiosk` | Local Home Assistant user account for dashboard access. |
| `ha_password` | password | *(blank)* | Password for the authentication user. |
| `dashboard_url` | string | `http://homeassistant:8123/...` | Internal Docker URL to the dashboard view hosting the card. |

---

## How It Works

1. **Headless Screen Capture:** Playwright loads your dashboard headlessly inside the container, authenticates if the cached session has expired, and captures a 2× high-DPI rasterization of the card element.
2. **Acutance & Gamut Adjustment:** The render is resized to 600×400 and mapped through tuned contrast (1.25×) and saturation (1.35×) curves with a subtle gamma lift (γ = 1.05) to optimize reflective e-paper contrast.
3. **Edge-Gated Atkinson Dithering:**
   - A spatial edge filter (`ImageFilter.FIND_EDGES`) isolates font contours, temperature icons, and glass boundaries.
   - Continuous-tone regions (3D barrel lighting and background gradients) diffuse using Bill Atkinson's 6/8 error distribution algorithm against a fast 3D perceptual color LUT.
   - Diffusion is frozen across edge boundaries (`edge > 30`), keeping fine text, brewery sub-lines, and outlines crisp without grain erosion.
4. **Binary Packing:** The quantized canvas is rotated 270° for panel mounting orientation and serialized into 4-bit nibbles (2 pixels per byte) for Waveshare controller transmission.

---

## Output Files

Artifacts are written to `/config/www/`:

* `/config/www/perfectdraft_card.png` — RGB preview image viewable via `http://homeassistant.local:8123/local/perfectdraft_card.png`.
* `/config/www/perfectdraft_card.bin` — Raw 4-bit packed binary for ESPHome e-Paper drivers.
* `/config/www/debug_screenshot.png` — Diagnostic screenshot captured if card extraction encounters an error.

---

## REST Command Configuration

Add the following to your Home Assistant `configuration.yaml` to trigger rendering via service calls:

```yaml
rest_command:
  generate_perfectdraft_image:
    url: "[http://127.0.0.1:8099](http://127.0.0.1:8099)"
    method: POST
    timeout: 30
```

---

## Automation Example

To automatically refresh the e-paper panel whenever remaining beer volume or keg temperature updates:

```yaml
alias: "PerfectDraft: Update Colour E-Ink Display"
description: "Re-renders the Lovelace card and triggers an ESPHome e-paper refresh on state changes."
trigger:
  - platform: state
    entity_id:
      - sensor.perfectdraft_pro_keg_remaining
      - sensor.perfectdraft_pro_temperature
actions:
  - action: rest_command.generate_perfectdraft_image
  - delay: "00:00:08"
  - action: button.press
    target:
      entity_id: button.perfectdraft_colour_e_ink_refresh_screen
mode: queued
```

---

## Manual Webhook API

You can manually trigger renders or test specific beer cards from any terminal or script:

```bash
# Render the live dashboard card:
curl -X POST [http://127.0.0.1:8099](http://127.0.0.1:8099)

# Test render an arbitrary beer override:
curl -X POST -H "Content-Type: application/json" \
  -d '{"beer_name": "Stella Artois"}' \
  [http://127.0.0.1:8099](http://127.0.0.1:8099)
```
