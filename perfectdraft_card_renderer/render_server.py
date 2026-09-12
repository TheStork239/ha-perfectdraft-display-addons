import os
import io
import sys
import json
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageEnhance
from playwright.sync_api import sync_playwright

OPTIONS_PATH = "/data/options.json"
OUTPUT_PNG = "/config/www/perfectdraft_card.png"
OUTPUT_BIN = "/config/www/perfectdraft_card.bin"
DEBUG_RAW = "/config/www/debug_raw_card.png"
DEBUG_PATH = "/config/www/debug_screenshot.png"
AUTH_CACHE = "/data/auth_state.json"

PALETTE = [
    0,   0,   0,      # 0: Black
    255, 255, 255,    # 1: White
    255, 255, 0,      # 2: Yellow
    255, 0,   0,      # 3: Red
    0,   0,   255,    # 4: Blue
    0,   255, 0       # 5: Green
] + [0] * (768 - 18)

COLOR_MAP = {
    0: 0x0,
    1: 0x1,
    2: 0x2,
    3: 0x3,
    4: 0x5,
    5: 0x6
}

def load_config():
    opts = {}
    if os.path.exists(OPTIONS_PATH):
        try:
            with open(OPTIONS_PATH, "r") as f:
                opts = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read options.json: {e}", flush=True)
    
    username = opts.get("ha_username", "kiosk").strip()
    password = opts.get("ha_password", "").strip()
    target_url = opts.get("dashboard_url", "http://homeassistant:8123/dashboard-entertainment/0").strip()
    return username, password, target_url

def render_card(beer_override=None):
    os.makedirs(os.path.dirname(OUTPUT_PNG), exist_ok=True)
    ha_username, ha_password, target_url = load_config()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context_args = {
            "viewport": {"width": 1280, "height": 800},
            "device_scale_factor": 2,
        }
        if os.path.exists(AUTH_CACHE) and os.path.getsize(AUTH_CACHE) > 0:
            context_args["storage_state"] = AUTH_CACHE

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)

            # Re-authenticate if session dropped or redirected to auth
            needs_auth = False
            try:
                user_input = page.locator("input[name='username']").first
                user_input.wait_for(state="visible", timeout=4000)
                needs_auth = True
            except Exception:
                if "auth" in page.url:
                    needs_auth = True

            if needs_auth:
                print("Session expired or unauthenticated. Logging in...", flush=True)
                user_input = page.locator("input[name='username']").first
                user_input.fill(ha_username)
                pass_input = page.locator("input[name='password']").first
                pass_input.fill(ha_password)
                pass_input.press("Enter")
                user_input.wait_for(state="detached", timeout=15000)
                page.wait_for_url(lambda u: "auth" not in u, timeout=15000)
                page.wait_for_timeout(2000)
                if "/dashboard-entertainment" not in page.url:
                    page.goto(target_url, wait_until="networkidle", timeout=30000)
                context.storage_state(path=AUTH_CACHE)

            card = page.locator("perfectdraft-card, perfectdraft-pro-card, ha-card").first
            card.wait_for(state="visible", timeout=20000)

            # Dynamically override the beer in browser memory if requested
            if beer_override:
                card.evaluate("""(el, name) => {
                    const cfg = Object.assign({}, el._config || {}, { beer_name: name });
                    el.setConfig(cfg);
                }""", beer_override)
                page.wait_for_timeout(1200)

            page.wait_for_timeout(600)
            screenshot = card.screenshot()
        except Exception as err:
            page.screenshot(path=DEBUG_PATH)
            browser.close()
            raise err
        browser.close()

    with open(DEBUG_RAW, "wb") as f:
        f.write(screenshot)

    img = Image.open(io.BytesIO(screenshot)).convert("RGB")
    img = img.resize((600, 400), Image.Resampling.LANCZOS)
    px = img.load()

    # Dynamic Brand Classification
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

    print(f"Beer: {beer_override or 'Live'} | Brand: {brand} (Chroma: {chroma:.1f}) -> Solid: {brand_solid}", flush=True)

    for y in range(400):
        bg_r, bg_g, bg_b = px[25, y]
        for x in range(600):
            r, g, b = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            px_chroma = max(r, g, b) - min(r, g, b)

            if x < banner_width:
                dist_bg = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
                if y >= 170:
                    if text_solid == (0, 0, 0):
                        is_text = (lum < 125 or (r < bg_r - 40 and g < bg_g - 40))
                    else:
                        is_text = (lum > 135 or dist_bg > 55)
                    px[x, y] = text_solid if is_text else brand_solid
                else:
                    if x < 65 or x > 185 or y < 45:
                        px[x, y] = brand_solid
                    else:
                        if dist_bg < 38:
                            px[x, y] = brand_solid
            else:
                if y > 310:
                    px[x, y] = (0, 0, 0) if lum < 140 else (255, 255, 255)
                elif r > 244 and g > 244 and b > 244:
                    px[x, y] = (255, 255, 255)
                else:
                    if px_chroma < 30:
                        dark_val = max(0, int(lum * 0.65))
                        px[x, y] = (dark_val, dark_val, dark_val)
                    else:
                        deep_r = min(255, int(r * 1.15))
                        deep_g = max(0, int(g * 0.90))
                        deep_b = max(0, int(b * 0.40))
                        px[x, y] = (deep_r, deep_g, deep_b)

    enhanced = ImageEnhance.Color(img).enhance(1.3)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.15)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.3)

    pal = Image.new("P", (1, 1))
    pal.putpalette(PALETTE)

    quantized = enhanced.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
    quantized.convert("RGB").save(OUTPUT_PNG, "PNG")

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

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            beer_override = None
            if content_length > 0:
                body = self.rfile.read(content_length)
                try:
                    payload = json.loads(body.decode())
                    beer_override = payload.get("beer_name")
                except Exception:
                    pass

            render_card(beer_override=beer_override)
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
