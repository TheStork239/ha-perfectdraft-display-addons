import os
import io
import sys
import json
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageEnhance, ImageFilter
from playwright.sync_api import sync_playwright

OPTIONS_PATH = "/data/options.json"
OUTPUT_PNG = "/config/www/perfectdraft_card.png"
OUTPUT_BIN = "/config/www/perfectdraft_card.bin"
DEBUG_RAW = "/config/www/debug_raw_card.png"
DEBUG_PATH = "/config/www/debug_screenshot.png"
AUTH_CACHE = "/data/auth_state.json"

BANNER_WIDTH = 234

PALETTE_COLORS = [
    (0, 0, 0),        # 0: Black
    (255, 255, 255),  # 1: White
    (255, 255, 0),    # 2: Yellow
    (255, 0, 0),      # 3: Red
    (0, 0, 255),      # 4: Blue
    (0, 255, 0)       # 5: Green
]

COLOR_MAP = {
    0: 0x0,
    1: 0x1,
    2: 0x2,
    3: 0x3,
    4: 0x5,
    5: 0x6
}

def log(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {message}", flush=True)

# 32x32x32 perceptual color lookup table
log("Building 3D perceptual color LUT...")
LUT = []
for r_idx in range(32):
    r_val = r_idx * 255 // 31
    r_plane = []
    for g_idx in range(32):
        g_val = g_idx * 255 // 31
        g_line = []
        for b_idx in range(32):
            b_val = b_idx * 255 // 31
            best_idx = 0
            best_dist = 99999999
            for p_idx, (pr, pg, pb) in enumerate(PALETTE_COLORS):
                dr = r_val - pr
                dg = g_val - pg
                db = b_val - pb
                dist = 2 * dr * dr + 4 * dg * dg + 3 * db * db
                if dist < best_dist:
                    best_dist = dist
                    best_idx = p_idx
            pr, pg, pb = PALETTE_COLORS[best_idx]
            g_line.append((best_idx, pr, pg, pb))
        r_plane.append(g_line)
    LUT.append(r_plane)
log("3D Color LUT initialized.")

def load_config():
    opts = {}
    if os.path.exists(OPTIONS_PATH):
        try:
            with open(OPTIONS_PATH, "r") as f:
                opts = json.load(f)
        except Exception as e:
            log(f"Could not read options.json: {e}", level="WARN")

    username = opts.get("ha_username", "kiosk").strip()
    password = opts.get("ha_password", "").strip()
    target_url = opts.get("dashboard_url", "http://homeassistant:8123/dashboard-entertainment/0").strip()
    return username, password, target_url

def edge_preserving_atkinson(img):
    width, height = img.size
    
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_data = list(edges.getdata())
    
    pixels = list(img.getdata())
    arr_r = [float(p[0]) for p in pixels]
    arr_g = [float(p[1]) for p in pixels]
    arr_b = [float(p[2]) for p in pixels]
    
    out_indices = [0] * (width * height)
    
    for y in range(height):
        y_offset = y * width
        for x in range(width):
            idx = y_offset + x
            
            r = int(arr_r[idx])
            g = int(arr_g[idx])
            b = int(arr_b[idx])
            
            if r < 0: r = 0
            elif r > 255: r = 255
            if g < 0: g = 0
            elif g > 255: g = 255
            if b < 0: b = 0
            elif b > 255: b = 255
            
            ri = (r * 31) >> 8
            gi = (g * 31) >> 8
            bi = (b * 31) >> 8
            
            pal_idx, pr, pg, pb = LUT[ri][gi][bi]
            out_indices[idx] = pal_idx
            
            # Lock font strokes and fine lines from diffusing noise
            if edge_data[idx] > 32:
                continue
                
            err_r = (r - pr) / 8.0
            err_g = (g - pb) / 8.0
            err_b = (b - pg) / 8.0
            
            if x + 1 < width:
                n = idx + 1
                arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b
            if x + 2 < width:
                n = idx + 2
                arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b
                
            if y + 1 < height:
                row1 = (y + 1) * width
                if x - 1 >= 0:
                    n = row1 + x - 1
                    arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b
                n = row1 + x
                arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b
                if x + 1 < width:
                    n = row1 + x + 1
                    arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b
                    
            if y + 2 < height:
                n = (y + 2) * width + x
                arr_r[n] += err_r; arr_g[n] += err_g; arr_b[n] += err_b

    rgb_out = bytearray(width * height * 3)
    for i, p_idx in enumerate(out_indices):
        pr, pg, pb = PALETTE_COLORS[p_idx]
        rgb_out[i * 3] = pr
        rgb_out[i * 3 + 1] = pg
        rgb_out[i * 3 + 2] = pb
        
    return Image.frombytes("RGB", (width, height), bytes(rgb_out))

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

            needs_auth = False
            try:
                user_input = page.locator("input[name='username']").first
                user_input.wait_for(state="visible", timeout=4000)
                needs_auth = True
            except Exception:
                if "auth" in page.url:
                    needs_auth = True

            if needs_auth:
                log("Session expired or unauthenticated. Logging in...", level="AUTH")
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
                log("Authentication successful, storage state saved.", level="AUTH")

            card = page.locator("perfectdraft-card, perfectdraft-pro-card, ha-card").first
            card.wait_for(state="visible", timeout=20000)

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

    raw_img = Image.open(io.BytesIO(screenshot)).convert("RGB")
    img = raw_img.resize((600, 400), Image.Resampling.LANCZOS)
    px = img.load()

    # 1. Sample Background from Safe Margin
    sample_pts = [px[x, y] for x in (20, 30, 40) for y in (60, 80, 100)]
    avg_r = sum(p[0] for p in sample_pts) / len(sample_pts)
    avg_g = sum(p[1] for p in sample_pts) / len(sample_pts)
    avg_b = sum(p[2] for p in sample_pts) / len(sample_pts)

    bg_lum = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b
    is_light_banner = (bg_lum >= 135)

    # 2. Targeted Tone & Contrast Mapping
    for y in range(400):
        for x in range(600):
            r, g, b = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            chroma = max(r, g, b) - min(r, g, b)

            if x >= BANNER_WIDTH:
                # --- RIGHT PANEL (Mugs & Volume Text) ---
                if r > 225 and g > 225 and b > 225:
                    # Flush canvas background to pure white
                    px[x, y] = (255, 255, 255)
                elif chroma < 35 and lum < 185:
                    # Deepen glass borders, handles, and volume text to solid black
                    px[x, y] = (0, 0, 0)
                else:
                    # Deepen and warm the beer fill to rich amber
                    deep_r = min(255, int(r * 1.25))
                    deep_g = max(0, int(g * 0.90))
                    deep_b = max(0, int(b * 0.15))
                    px[x, y] = (deep_r, deep_g, deep_b)
            else:
                # --- LEFT BANNER (Brand, Keg, Text) ---
                if y >= 165:
                    dist_bg = abs(r - avg_r) + abs(g - avg_g) + abs(b - avg_b)
                    
                    if is_light_banner:
                        # Light banner (Corona, Camden Top, Ginette) -> solid black text
                        if lum < 135 or dist_bg > 50:
                            px[x, y] = (0, 0, 0)
                    else:
                        # Dark or saturated banner -> high-contrast text
                        if dist_bg > 42:
                            if r > 130 and g > 100 and b < 100 and (r - b) > 35:
                                px[x, y] = (255, 255, 0)  # Gold/Yellow text
                            elif r > 140 and g < 75 and b < 75:
                                px[x, y] = (255, 0, 0)    # Red text (Trooper)
                            else:
                                px[x, y] = (255, 255, 255)  # Crisp white text & snowflake
                else:
                    # Clean banner shoulders outside 3D keg
                    if x < 45 or x > 195 or y < 25:
                        dist_bg = abs(r - avg_r) + abs(g - avg_g) + abs(b - avg_b)
                        if dist_bg < 45:
                            px[x, y] = (int(avg_r), int(avg_g), int(avg_b))

    # 3. Boost Saturation & Edge Acutance
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.30)

    log(f"Dithering '{beer_override or 'Live'}' via Contrast-Preserving Atkinson...")
    dithered_rgb = edge_preserving_atkinson(img)
    dithered_rgb.save(OUTPUT_PNG, "PNG")

    # Rotate 270 degrees for Waveshare panel orientation
    try:
        dithered_rot = dithered_rgb.transpose(Image.Transpose.ROTATE_270)
    except AttributeError:
        dithered_rot = dithered_rgb.transpose(Image.ROTATE_270)

    pal_img = Image.new("P", (1, 1))
    flat_pal = []
    for c in PALETTE_COLORS:
        flat_pal.extend(c)
    flat_pal += [0] * (768 - len(flat_pal))
    pal_img.putpalette(flat_pal)

    rot_quant = dithered_rot.quantize(palette=pal_img, dither=Image.Dither.NONE)
    raw_pixels = list(rot_quant.getdata())

    packed_bytes = bytearray(len(raw_pixels) // 2)
    for i in range(0, len(raw_pixels), 2):
        c1 = COLOR_MAP.get(raw_pixels[i], 0x1)
        c2 = COLOR_MAP.get(raw_pixels[i + 1], 0x1)
        packed_bytes[i // 2] = (c1 << 4) | (c2 & 0x0F)

    with open(OUTPUT_BIN, "wb") as f:
        f.write(packed_bytes)

    log(f"Render complete: {OUTPUT_PNG} and {OUTPUT_BIN} updated.")

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
        log(format % args, level="HTTP")

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8099), WebhookHandler)
    log("Renderer listening on port 8099...")
    server.serve_forever()
