# PerfectDraft Card Renderer

This add-on captures a Home Assistant Lovelace dashboard card, processes it with multi-pigment Floyd-Steinberg dithering for a 6-color Spectra 6 E-Ink display, and serves the resulting PNG and raw ESPHome binary.

## Prerequisites

- A Waveshare Spectra 6 E-Ink display running ESPHome.
- A configured Lovelace dashboard containing your PerfectDraft card (e.g., `/dashboard-entertainment/0`).

## Installation & Setup

1. Add this repository URL to your Home Assistant Add-on Store.
2. Install the **PerfectDraft Card Renderer** add-on.
3. Go to the add-on's **Configuration** tab.
4. Enter your Home Assistant username and password (a dedicated `kiosk` user is recommended).
5. Input your exact dashboard URL (e.g., `http://127.0.0.1:8123/dashboard-entertainment/0`).
6. Click **Save** and then **Start**.

## Automation Example

To refresh your display automatically when states change or your keg updates, use an automation that triggers your render webhook followed by your ESPHome refresh button:

```yaml
alias: "PerfectDraft: Update Colour E-Ink Display"
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