import os
import io
import sys
import json
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageEnhance
from playwright.sync_api import sync_playwright

OPTIONS_PATH = "/data/options.json"

# Base fallbacks (no hardcoded credentials)
HA_URL = "http://127.0.0.1:8123"
HA_USERNAME = ""
HA_PASSWORD = ""
TARGET_URL = f"{HA_URL}/dashboard-entertainment/0"

# Load dynamic credentials from Home Assistant Configuration tab
if os.path.exists(OPTIONS_PATH):
    try:
        with open(OPTIONS_PATH, "r") as f:
            opts = json.load(f)
            HA_USERNAME = opts.get("ha_username", "").strip()
            HA_PASSWORD = opts.get("ha_password", "").strip()
            TARGET_URL = opts.get("dashboard_url", TARGET_URL).strip()
    except Exception as err:
        print(f"Warning: Failed to parse {OPTIONS_PATH}: {err}", flush=True)

OUTPUT_PNG = "/config/www/perfectdraft_card.png"
OUTPUT_BIN = "/config/www/perfectdraft_card.bin"
DEBUG_RAW = "/config/www/debug_raw_card.png"
DEBUG_PATH = "/config/www/debug_screenshot.png"
AUTH_CACHE = "/data/auth_state.json"

# Spectra 6 Hardware Palette: Black, White, Yellow, Red, Blue, Green
PALETTE = [
    0,   0,   0,      # 0: Black
    255, 255, 255,    # 1: White
    255, 255, 0,      # 2: Yellow
    255, 0,   0,      # 3: Red
    0,   0,   255,    # 4: Blue
    0,   255, 0       # 5: Green
] + [0] * (768 - 18)

COLOR_MAP = {
    0: 0x0,  # Black
    1: 0x1,  # White
    2: 0x2,  # Yellow
    3: 0x3,  # Red
    4: 0x5,  # Blue
    5: 0x6   # Green
}

def render_card():
    os.makedirs(os.path.dirname(OUTPUT_PNG), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-cache",
                "--disk-cache-size=0"
            ]
        )
        context_args = {
            "viewport": {"width": 1280, "height": 800},
            "device_scale_factor": 2,
            "extra_http_headers": {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache"
            }
        }
        if os.path.exists(AUTH_CACHE) and os.path.getsize(AUTH_CACHE) > 0:
            context_args["storage_state"] = AUTH_CACHE

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded")

            if "auth" in page.url or page.locator("input[name='username']").is_visible():
                user_in = page.locator("input[name='username']").first
                user_in.wait_for(state="visible", timeout=8000)
                user_in.fill(HA_USERNAME)
                pass_in = page.locator("input[name='password']").first
                pass_in.fill(HA_PASSWORD)
                pass_in.press("Enter")
                page.wait_for_timeout(3000)
                page.goto(TARGET_URL, wait_until="domcontentloaded")

            loading = page.locator("ha-init-page")
            if loading.is_visible():
                loading.wait_for(state="detached", timeout=30000)

            page.wait_for_timeout(2000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(3500)

            card = page.locator("perfectdraft-card, ha-card:has-text('PerfectDraft'), ha-card:has-text('Perfect Draft')").first
            card.wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(2000)

            screenshot = card.screenshot()
            context.storage_state(path=AUTH_CACHE)
        except Exception as err:
            page.screenshot(path=DEBUG_PATH)
            browser.close()
            raise err
        browser.close()

    with open(DEBUG_RAW, "wb") as f:
        f.write(screenshot)

    # Load and scale to 600x400 landscape
    img = Image.open(io.BytesIO(screenshot)).convert("RGB")
    img = img.resize((600, 400), Image.Resampling.LANCZOS)
    px = img.load()

    # --- 1. DYNAMIC BRAND CLASSIFICATION VIA HSV ---
    sample_pts = [px[25, y] for y in (80, 130, 200, 270, 330)]
    avg_r = sum(p[0] for p in sample_pts) / len(sample_pts)
    avg_g = sum(p[1] for p in sample_pts) / len(sample_pts)
    avg_b = sum(p[2] for p in sample_pts) / len(sample_pts)

    bg_lum = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b
    c_max = max(avg_r, avg_g, avg_b)
    c_min = min(avg_r, avg_g, avg_b)
    chroma = c_max - c_min

    if chroma < 28:
        if bg_lum < 75:
            brand = "BLACK"
            brand_solid = (0, 0, 0)
            text_solid = (255, 255, 255)
        else:
            brand = "WHITE"
            brand_solid = (255, 255, 255)
            text_solid = (0, 0, 0)
    else:
        if c_max == avg_r:
            hue = (60 * ((avg_g - avg_b) / chroma) + 360) % 360
        elif c_max == avg_g:
            hue = (60 * ((avg_b - avg_r) / chroma) + 120) % 360
        else:
            hue = (60 * ((avg_r - avg_g) / chroma) + 240) % 360

        if hue >= 330 or hue < 20:
            brand = "RED"
            brand_solid = (255, 0, 0)
            text_solid = (255, 255, 255)
        elif 20 <= hue < 75:
            brand = "YELLOW"
            brand_solid = (255, 255, 0)
            text_solid = (0, 0, 0)
        elif 75 <= hue < 165:
            brand = "GREEN"
            brand_solid = (0, 255, 0)
            text_solid = (255, 255, 255)
        else:
            brand = "BLUE"
            brand_solid = (0, 0, 255)
            text_solid = (255, 255, 255)

    banner_width = 236
    for test_x in range(190, 260):
        r, g, b = px[test_x, 200]
        if r > 245 and g > 245 and b > 245:
            banner_width = test_x
            break

    print(f"Brand: {brand} (Chroma: {chroma:.1f}, Lum: {bg_lum:.1f}) -> Solid: {brand_solid}, Text: {text_solid}. Width: {banner_width}px", flush=True)

    # --- 2. ZONAL PRE-PROCESSING ---
    for y in range(400):
        bg_r, bg_g, bg_b = px[25, y]

        for x in range(600):
            r, g, b = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            px_chroma = max(r, g, b) - min(r, g, b)

            # === LEFT BANNER (Flush Full-Bleed) ===
            if x < banner_width:
                dist_bg = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)

                # Zone A: Typography (y >= 170) -> Text vs. Solid Background
                if y >= 170:
                    if text_solid == (0, 0, 0):
                        is_text = (lum < 125 or (r < bg_r - 40 and g < bg_g - 40))
                    else:
                        is_text = (lum > 135 or dist_bg > 55)

                    px[x, y] = text_solid if is_text else brand_solid

                # Zone B: Keg Area (y < 170) -> Solid Background, Untouched Keg
                else:
                    if x < 65 or x > 185 or y < 45:
                        px[x, y] = brand_solid
                    else:
                        if dist_bg < 38:
                            px[x, y] = brand_solid
                        # Keg contours, handles, and label remain in RGB for dithering

            # === RIGHT CANVAS (Beer Mugs & Volume Readout) ===
            else:
                # Bottom text readout "9 x 568 mL" (y > 310)
                if y > 310:
                    px[x, y] = (0, 0, 0) if lum < 140 else (255, 255, 255)
                # Pure white canvas background
                elif r > 244 and g > 244 and b > 244:
                    px[x, y] = (255, 255, 255)
                else:
                    # Glass handles, rims, reflections, and empty 10th glass (neutral tones)
                    if px_chroma < 30:
                        # Darken neutral glass tones by ~35% for clean dithered contours
                        dark_val = max(0, int(lum * 0.65))
                        px[x, y] = (dark_val, dark_val, dark_val)
                    else:
                        # Amber beer liquid: deepen contrast and saturation
                        deep_r = min(255, int(r * 1.15))
                        deep_g = max(0, int(g * 0.90))
                        deep_b = max(0, int(b * 0.40))
                        px[x, y] = (deep_r, deep_g, deep_b)

    # --- 3. ENHANCEMENT & FLOYD-STEINBERG QUANTIZATION ---
    enhanced = ImageEnhance.Color(img).enhance(1.3)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.15)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.3)

    pal = Image.new("P", (1, 1))
    pal.putpalette(PALETTE)

    quantized = enhanced.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
    quantized.convert("RGB").save(OUTPUT_PNG, "PNG")

    # --- 4. ROTATION (270°) & BINARY PACKING ---
    try:
        img_rot = quantized.transpose(Image.Transpose.ROTATE_270)
    except AttributeError:
        img_rot = quantized.transpose(Image.ROTATE_270)

    raw_pixels = list(img_rot.getdata())

    packed_bytes = bytearray(len(raw_pixels) // 2)
    for i in range(0, len(raw_pixels), 2):
        c1 = COLOR_MAP.get(raw_pixels[i], 0x1)
        c2 = COLOR_MAP.get(raw_pixels[i + 1], 0x1)
        packed_bytes[i // 2] = (c1 << 4) | (c2 & 0x0F)

    with open(OUTPUT_BIN, "wb") as f:
        f.write(packed_bytes)

    print(f"Success: wrote {OUTPUT_PNG} and {OUTPUT_BIN} ({len(packed_bytes)} bytes)", flush=True)

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            render_card()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        print(f"[HTTP] {format % args}", flush=True)

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8099), WebhookHandler)
    print("Renderer listening on port 8099...", flush=True)
    server.serve_forever()