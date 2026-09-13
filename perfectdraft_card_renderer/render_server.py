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

# Waveshare 6-color Spectra Palette
PALETTE_COLORS = [
    (0, 0, 0),        # 0: Black
    (255, 255, 255),  # 1: White
    (255, 255, 0),    # 2: Yellow
    (255, 0, 0),      # 3: Red
    (0, 0, 255),      # 4: Blue
    (0, 255, 0)       # 5: Green
]

COLOR_MAP = {
    0: 0x0,  # Black
    1: 0x1,  # White
    2: 0x2,  # Yellow
    3: 0x3,  # Red
    4: 0x5,  # Blue
    5: 0x6   # Green
}

def log(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {message}", flush=True)

# Build fast 3D perceptual color LUT at startup
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
                # Perceptually weighted Euclidean distance (Green > Red > Blue)
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
    
    # 1. Edge Map for protecting text and fine outlines
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_data = list(edges.getdata())
    
    # 2. Extract color buffers
    pixels = list(img.getdata())
    arr_r = [float(p[0]) for p in pixels]
    arr_g = [float(p[1]) for p in pixels]
    arr_b = [float(p[2]) for p in pixels]
    
    out_indices = [0] * (width * height)
    
    # 3. Atkinson Error Diffusion Loop
    for y in range(height):
        y_offset = y * width
        for x in range(width):
            idx = y_offset + x
            
            r = int(arr_r[idx])
            g = int(arr_g[idx])
            b = int(arr_b[idx])
            
            # Clamp bounds
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
            
            # If on text or line art edge, freeze diffusion to keep stroke crisp
            if edge_data[idx] > 30:
                continue
                
            # Atkinson formula: diffuse 6/8ths (75%) of the error, discard 25%
            err_r = (r - pr) / 8.0
            err_g = (g - pg) / 8.0
            err_b = (b - pb) / 8.0
            
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

    # 1. Boost Color Saturation (enriches yellow beer liquid and brand hues)
    img = ImageEnhance.Color(img).enhance(1.35)

    # 2. Boost Contrast (deepens grey outlines to black, enriches background depth)
    img = ImageEnhance.Contrast(img).enhance(1.25)

    # 3. Gentle Gamma Lift (only 5% lift to avoid crushing shadows without bleaching)
    inv_gamma = 1.0 / 1.05
    gamma_lut = [int(pow(i / 255.0, inv_gamma) * 255.0 + 0.5) for i in range(256)]
    img = img.point(gamma_lut * 3)

    # 4. Sharpen outlines and typography
    img = ImageEnhance.Sharpness(img).enhance(1.35)

    log(f"Dithering '{beer_override or 'Live'}' via Continuous Atkinson...")
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
