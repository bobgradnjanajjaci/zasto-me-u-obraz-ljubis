from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import requests
import os
import re
import threading
import time
import random
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)

# 🔧 KONFIGURACIJA – OVO POPUNI (ili postavi u Railway Variables)
PANEL_URL = os.environ.get("PANEL_URL", "https://smmfrog.com/api/v2")
API_KEY = os.environ.get("API_KEY", "15a158fe55e7c21be7de194ef97ebfa5")
SERVICE_ID = int(os.environ.get("SERVICE_ID", 4120))  # TikTok Custom Comments na JAP-u

# 🔁 3 SETA KOMENTARA (Ubaci svoje komentare ovdje)

# ✅ SET 1
COMMENTS_SET_1 = [
    "not me reading The Alversett Effect by Nora Alversett in one sitting and finally understanding why the author completely disappeared from the internet after publishing it",
    "i almost wish i never read the alversett effect by nora alversett because once you see what she explains on page 13 you can never look at relationships the same way again",
    "a girl in another comment section mentioned the alversett effect by nora alversett and now i see why the author never shows her face in public anymore, page 24 is honestly not normal",
    "i used to overthink everything and always give too much until i read the alversett effect by nora alversett, it genuinely feels like having an unfair advantage in reading people",
    "no influencer or coach ever explained human behavior the way nora alversett did in the alversett effect, i finally get why she went completely offline after releasing this book",
    "once you read chapter 4 of the alversett effect by nora alversett and see how easily women are Conditioned to settle for less, you can never unsee it",
    "i know it sounds dramatic to talk about a book in the comments, but the alversett effect by nora alversett flipped a switch in my brain that i honestly cannot turn off",
    "doing the 17 questions from the alversett effect by nora alversett made me realize how much power i was giving away to people who didn't even deserve my attention",
    "men are honestly lucky most women still haven't discovered the alversett effect by nora alversett because chapter 3 alone changes the whole dynamic overnight",
    "sometimes a comment about a book finds you at the exact moment you need it, and for me it was the alversett effect by nora alversett, still crazy how the author just vanished after writing it"
]

# ✅ SET 2
COMMENTS_SET_2 = [
    "komentar 1 iz drugog seta",
    "komentar 2 iz drugog seta",
    "komentar 3 iz drugog seta",
    "komentar 4 iz drugog seta",
    "komentar 5 iz drugog seta",
    "komentar 6 iz drugog seta",
    "komentar 7 iz drugog seta",
    "komentar 8 iz drugog seta",
    "komentar 9 iz drugog seta",
    "komentar 10 iz drugog seta"
]

# ✅ SET 3
COMMENTS_SET_3 = [
    "komentar 1 iz treceg seta",
    "komentar 2 iz treceg seta",
    "komentar 3 iz treceg seta",
    "komentar 4 iz treceg seta",
    "komentar 5 iz treceg seta",
    "komentar 6 iz treceg seta",
    "komentar 7 iz treceg seta",
    "komentar 8 iz treceg seta",
    "komentar 9 iz treceg seta",
    "komentar 10 iz treceg seta"
]

# 🕒 GLOBALNO STANJE ZA RED ČEKANJA (QUEUE)
order_queue = []
log_lines = []
queue_lock = threading.Lock()
is_waiting = False
sent_ok_count = 0
sent_fail_count = 0

DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def add_log(msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    with queue_lock:
        log_lines.insert(0, f"[{now}] {msg}")
        if len(log_lines) > 300:
            log_lines.pop()


def convert_to_pc_link(raw_url: str) -> str:
    """
    Pretvara mobilni/skraćeni TikTok link (vm.tiktok.com, vt.tiktok.com, m.tiktok.com, /t/...)
    u čisti PC link formata: https://www.tiktok.com/@user/video/1234567890123456789
    """
    url = (raw_url or "").strip()
    if not url:
        return url

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Ako je već puni PC link (@user/video/ID ili @user/photo/ID), samo očisti query parametre (?is_from_webapp=...)
    pc_match = re.match(r"^https?://(?:www\.)?tiktok\.com/(@[^/?#]+/(?:video|photo)/\d+)", url)
    if pc_match:
        return f"https://www.tiktok.com/{pc_match.group(1)}"

    resolved_url = url
    try:
        # Prati redirect sa Desktop User-Agentom kako bi TikTok vratio PC verziju URL-a
        resp = requests.get(
            url,
            headers=DESKTOP_HEADERS,
            allow_redirects=True,
            timeout=15,
            stream=True,
        )
        resolved_url = resp.url
        resp.close()
    except Exception as e:
        add_log(f"⚠️ Neuspješno praćenje redirecta za {url}: {e}")

    # 1. Provjeri da li smo dobili standardni @username/video/ID ili @username/photo/ID
    match_standard = re.search(r"tiktok\.com/(@[^/?#]+/(?:video|photo)/\d+)", resolved_url)
    if match_standard:
        return f"https://www.tiktok.com/{match_standard.group(1)}"

    # 2. Ako je redirect završio na m.tiktok.com/v/123456789.html ili tiktok.com/video/123456789
    match_mobile_v = re.search(r"(?:m\.tiktok\.com/v/|tiktok\.com/(?:video|photo)/)(\d+)", resolved_url)
    if match_mobile_v:
        video_id = match_mobile_v.group(1)
        # Pokušaj još jednom preko www.tiktok.com/video/{id} dobiti tačan @username u URL-u
        try:
            resp2 = requests.get(
                f"https://www.tiktok.com/video/{video_id}",
                headers=DESKTOP_HEADERS,
                allow_redirects=True,
                timeout=10,
                stream=True,
            )
            url2 = resp2.url
            resp2.close()
            match_std2 = re.search(r"tiktok\.com/(@[^/?#]+/(?:video|photo)/\d+)", url2)
            if match_std2:
                return f"https://www.tiktok.com/{match_std2.group(1)}"
        except Exception:
            pass
        return f"https://www.tiktok.com/@tiktok/video/{video_id}"

    # 3. Fallback: ukloni query parametre (?...) i prebaci domenu na www.tiktok.com
    parsed = urlparse(resolved_url)
    clean_path = parsed.path.rstrip("/")
    if parsed.netloc.endswith("tiktok.com") and clean_path:
        return f"https://www.tiktok.com{clean_path}"

    return resolved_url.split("?")[0]


def parse_delay_to_seconds(raw_val: str) -> int:
    """
    Pretvara unos vremena u sekunde:
    - Cijeli broj (npr. '5') -> 5 minuta (300 sekundi)
    - Format sa tačkom ili zarezom (npr. '0.10' -> 10 sekundi, '0.5' ili '0.05' -> 5 sekundi, '1.30' -> 1 min i 30 sek)
    """
    val = (raw_val or "").strip().replace(",", ".")
    if not val:
        return 300
    try:
        if "." in val:
            parts = val.split(".", 1)
            mins = int(parts[0]) if parts[0] else 0
            secs = int(parts[1]) if parts[1] else 0
            return max(0, mins * 60 + secs)
        else:
            mins = int(val)
            return max(0, mins * 60)
    except ValueError:
        return 300


def format_delay(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} sek"
    elif seconds % 60 == 0:
        return f"{seconds // 60} min ({seconds} sek)"
    else:
        return f"{seconds // 60} min {seconds % 60} sek ({seconds} sek)"


def send_comments_order(video_link: str, comments_list: list[str]):
    """Šalje JEDAN order na JAP za TikTok custom comments (promiješa redoslijed komentara radi dodatne sigurnosti)."""
    shuffled_comments = comments_list.copy()
    random.shuffle(shuffled_comments)  # Svaki video dobija drugačiji redoslijed komentara unutar seta!
    comments_text = "\n".join(shuffled_comments)

    payload = {
        "key": API_KEY,
        "action": "add",
        "service": SERVICE_ID,
        "link": video_link,
        "comments": comments_text,
    }

    try:
        r = requests.post(PANEL_URL, data=payload, timeout=20)
        try:
            data = r.json()
        except Exception:
            return False, f"HTTP {r.status_code}, body={r.text[:200]}"

        if "order" in data:
            return True, f"order={data['order']}"
        else:
            return False, f"resp={data}"
    except Exception as e:
        return False, f"exception={e}"


def background_worker():
    """Pozadinski proces koji uzima 1 po 1 link iz reda, konvertuje u PC link i čeka zadani interval."""
    global is_waiting, sent_ok_count, sent_fail_count
    while True:
        task = None
        with queue_lock:
            if len(order_queue) > 0:
                task = order_queue.pop(0)

        if task:
            raw_link = task["link"]
            comments = task["comments"]
            set_name = task["set_name"]
            delay_seconds = task["delay"]

            # Konverzija mobilnog linka u PC link prije slanja na panel
            pc_link = convert_to_pc_link(raw_link)
            if pc_link != raw_link:
                add_log(f"🔄 Konvertovano: {raw_link} -> {pc_link}")

            add_log(f"⏳ Šaljem order za: {pc_link} ({set_name})...")
            ok, msg = send_comments_order(pc_link, comments)

            with queue_lock:
                if ok:
                    sent_ok_count += 1
                else:
                    sent_fail_count += 1

            if ok:
                add_log(f"✅ [OK] {pc_link} -> {msg}")
            else:
                add_log(f"❌ [FAIL] {pc_link} -> {msg}")

            with queue_lock:
                has_more = len(order_queue) > 0

            if has_more and delay_seconds > 0:
                is_waiting = True
                add_log(f"💤 Pauza {format_delay(delay_seconds)} do sljedećeg linka...")

                for _ in range(delay_seconds):
                    with queue_lock:
                        if len(order_queue) == 0:
                            break
                    time.sleep(1)
                is_waiting = False
        else:
            time.sleep(1)


worker_thread = threading.Thread(target=background_worker, daemon=True)
worker_thread.start()


HTML_TEMPLATE = """
<!doctype html>
<html lang="bs">
<head>
  <title>TikTok Custom Komentari - Drip-Feed Sender</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <style>
    * {
      box-sizing: border-box;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      margin: 0;
      padding: 0;
      background: #050816;
      color: #f9fafb;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      min-height: 100vh;
    }

    .container {
      max-width: 920px;
      width: 100%;
      padding: 24px 16px 48px;
    }

    .card {
      background: rgba(15, 23, 42, 0.95);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 20px 45px rgba(0, 0, 0, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.3);
    }

    h1 {
      font-size: 24px;
      margin: 0 0 6px 0;
      text-align: center;
      line-height: 1.25;
    }

    .subtitle {
      text-align: center;
      font-size: 13px;
      color: #9ca3af;
      margin-bottom: 18px;
      line-height: 1.45;
    }

    .status-banner {
      background: rgba(30, 41, 59, 0.9);
      border: 1px solid rgba(99, 102, 241, 0.4);
      border-radius: 12px;
      padding: 12px 16px;
      margin-bottom: 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 13px;
    }

    .status-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .badge {
      padding: 4px 10px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 12px;
      display: inline-block;
    }

    .badge-active { background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.5); }
    .badge-idle { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.5); }

    label {
      font-size: 13px;
      font-weight: 500;
      margin-bottom: 6px;
      display: inline-block;
    }

    textarea, input[type="text"] {
      width: 100%;
      background: rgba(15, 23, 42, 0.9);
      border-radius: 12px;
      border: 1px solid rgba(55, 65, 81, 0.9);
      padding: 12px;
      color: #e5e7eb;
      font-size: 14px;
      line-height: 1.4;
      outline: none;
    }

    textarea {
      min-height: 180px;
      resize: vertical;
    }

    .delay-input {
      max-width: 160px;
    }

    textarea:focus, input[type="text"]:focus {
      border-color: #6366f1;
      box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.6);
    }

    .hint {
      font-size: 11.5px;
      color: #9ca3af;
      margin-top: 6px;
      line-height: 1.45;
    }

    .live-delay-preview {
      font-size: 12.5px;
      color: #a5b4fc;
      margin-top: 8px;
      font-weight: 500;
    }

    .options-grid {
      display: flex;
      gap: 28px;
      flex-wrap: wrap;
      margin-top: 18px;
    }

    .options-col-sets {
      flex: 1;
      min-width: 260px;
    }

    .options-col-delay {
      min-width: 230px;
    }

    .btn-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      justify-content: center;
      margin: 22px 0 12px;
    }

    button {
      border: none;
      border-radius: 999px;
      padding: 12px 22px;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: transform 0.1s ease, box-shadow 0.1s ease;
    }

    .btn-primary {
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      color: white;
      box-shadow: 0 10px 25px rgba(79, 70, 229, 0.6);
    }

    .btn-danger {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.5);
    }

    .btn-primary:hover { transform: translateY(-1px); }
    .btn-primary:active, .btn-danger:active { transform: scale(0.98); }

    .log {
      margin-top: 10px;
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-all;
      overflow-wrap: anywhere;
      background: rgba(10, 15, 30, 0.9);
      border-radius: 12px;
      padding: 12px;
      border: 1px solid rgba(55,65,81,0.9);
      max-height: 280px;
      overflow-y: auto;
    }

    .radio-group {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 10px;
      font-size: 13px;
    }

    .radio-group label {
      font-weight: 400;
      margin: 0;
      cursor: pointer;
      display: flex;
      align-items: flex-start;
      gap: 8px;
      line-height: 1.35;
      padding: 6px 8px;
      border-radius: 8px;
      background: rgba(30, 41, 59, 0.45);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .radio-group input[type="radio"] {
      margin-top: 2px;
      transform: scale(1.15);
      accent-color: #6366f1;
    }

    /* 📱 RESPONSIVE DIZAJN ZA TELEFONE */
    @media (max-width: 640px) {
      .container {
        padding: 12px 10px 32px;
      }

      .card {
        padding: 16px 14px;
        border-radius: 16px;
      }

      h1 {
        font-size: 19px;
      }

      .subtitle {
        font-size: 12px;
        margin-bottom: 14px;
      }

      .status-banner {
        flex-direction: column;
        align-items: flex-start;
        padding: 12px;
        gap: 8px;
      }

      .status-item {
        width: 100%;
        justify-content: space-between;
      }

      /* 16px sprječava automatsko zumiranje na iPhoneu (iOS Safari) */
      textarea, input[type="text"] {
        font-size: 16px;
        padding: 12px;
      }

      textarea {
        min-height: 150px;
      }

      .options-grid {
        flex-direction: column;
        gap: 18px;
      }

      .options-col-sets, .options-col-delay {
        min-width: 100%;
        width: 100%;
      }

      .delay-input {
        max-width: 100%;
      }

      .radio-group label {
        padding: 10px;
        font-size: 13.5px;
      }

      .btn-row {
        flex-direction: column;
        gap: 10px;
      }

      button {
        width: 100%;
        padding: 14px 18px;
        font-size: 14px;
      }

      .log {
        font-size: 11px;
        max-height: 240px;
        padding: 10px;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>TikTok Drip-Feed — Custom Comments Sender</h1>
      <div class="subtitle">
        Ubaci 100+ mobilnih ili PC linkova odjednom — skripta ih automatski konvertuje u <b>PC linkove</b>, šalje <b>jedan po jedan</b> i miješa komentare (Service {{ service_id }}).
      </div>

      <div class="status-banner">
        <div class="status-item">
          <span>Status:</span>
          <span id="queue-badge" class="badge {% if queue_count > 0 or is_waiting %}badge-active{% else %}badge-idle{% endif %}">
            {% if queue_count > 0 or is_waiting %}⏳ U TOKU (Drip-feed radi){% else %}✅ SPREMNO (Red je prazan){% endif %}
          </span>
        </div>
        <div class="status-item">
          <span>U redu čekanja:</span>
          <span><b id="queue-count">{{ queue_count }}</b> linkova</span>
        </div>
        <div class="status-item">
          <span>Rezultat:</span>
          <span>Uspješno: <b id="sent-ok" style="color:#4ade80;">{{ sent_ok }}</b> | Fail: <b id="sent-fail" style="color:#f87171;">{{ sent_fail }}</b></span>
        </div>
      </div>

      <form method="post" action="/">
        <label for="input_links">Video linkovi — mobilni ili PC (jedan ispod drugog)</label>
        <textarea id="input_links" name="input_links" placeholder="https://vm.tiktok.com/ZMHTTNkcWmPVu-YrDtq/&#10;https://vt.tiktok.com/ZS1234567/&#10;https://www.tiktok.com/@user/video/1234567890123456789"></textarea>
        <div class="hint">
          Slobodno nalijepi mobilne skraćene linkove (<code>vm.tiktok.com</code>, <code>vt.tiktok.com</code>) — skripta ih sama pretvara u čiste PC linkove prije slanja na panel.
        </div>

        <div class="options-grid">
          <div class="options-col-sets">
            <span style="font-size:13px;font-weight:500;">Izaberi Anti-Spam set komentara:</span>
            <div class="radio-group">
              <label>
                <input type="radio" name="comment_set" value="rotate">
                <span>🔄 <b>AUTO-ROTACIJA (Preporučeno za 100 linkova)</b> — vrti Set 1, Set 2 pa Set 3 naizmjenično</span>
              </label>
              <label>
                <input type="radio" name="comment_set" value="set1" checked>
                <span>Set #1: Prva grupa komentara ({{ comments1_count }} kom)</span>
              </label>
              <label>
                <input type="radio" name="comment_set" value="set2">
                <span>Set #2: Druga grupa komentara ({{ comments2_count }} kom)</span>
              </label>
              <label>
                <input type="radio" name="comment_set" value="set3">
                <span>Set #3: Treća grupa komentara ({{ comments3_count }} kom)</span>
              </label>
            </div>
          </div>

          <div class="options-col-delay">
            <label for="delay_minutes">Razmak između ordera (min ili 0.sek):</label><br>
            <input type="text" id="delay_minutes" name="delay_minutes" class="delay-input" value="5" inputmode="decimal" oninput="updateDelayPreview()">
            <div id="delay-preview" class="live-delay-preview">⏱️ Razmak: 5 min (300 sek)</div>
            <div class="hint">
              • Cijeli broj = minute (npr. <b>5</b> = 5 min)<br>
              • Sa tačkom = sekunde (npr. <b>0.10</b> = 10 sek, <b>0.5</b> = 5 sek, <b>0.30</b> = 30 sek)
            </div>
          </div>
        </div>

        <div class="btn-row">
          <button type="submit" name="action" value="add" class="btn-primary">🚀 Dodaj u red čekanja (Start Drip-Feed)</button>
          <button type="submit" name="action" value="clear" class="btn-danger" onclick="return confirm('Sigurno želiš obrisati sve linkove koji čekaju u redu?');">🛑 Zaustavi i isprazni red</button>
        </div>
      </form>

      <div style="font-size: 12px; color: #9ca3af; margin-top: 14px;">
        <b>Live Log</b> (automatski se osvježava svake 2 sekunde):
      </div>
      <div class="log" id="log-box">{{ log or 'Još nema aktivnosti...' }}</div>
    </div>
  </div>

  <script>
    function updateDelayPreview() {
      const raw = (document.getElementById('delay_minutes').value || '').trim().replace(',', '.');
      const preview = document.getElementById('delay-preview');
      if (!raw) {
        preview.innerText = '⏱️ Razmak: 5 min (300 sek)';
        return;
      }
      let totalSec = 300;
      if (raw.includes('.')) {
        const parts = raw.split('.');
        const mins = parseInt(parts[0] || '0', 10);
        const secs = parseInt(parts[1] || '0', 10);
        if (!isNaN(mins) && !isNaN(secs)) {
          totalSec = Math.max(0, mins * 60 + secs);
        }
      } else {
        const mins = parseInt(raw, 10);
        if (!isNaN(mins)) {
          totalSec = Math.max(0, mins * 60);
        }
      }

      if (totalSec < 60) {
        preview.innerText = '⏱️ Razmak: ' + totalSec + ' sekundi';
      } else if (totalSec % 60 === 0) {
        preview.innerText = '⏱️ Razmak: ' + (totalSec / 60) + ' min (' + totalSec + ' sek)';
      } else {
        preview.innerText = '⏱️ Razmak: ' + Math.floor(totalSec / 60) + ' min ' + (totalSec % 60) + ' sek (' + totalSec + ' sek)';
      }
    }

    setInterval(async () => {
      try {
        const res = await fetch('/status');
        const data = await res.json();
        document.getElementById('queue-count').innerText = data.queue_count;
        document.getElementById('sent-ok').innerText = data.sent_ok;
        document.getElementById('sent-fail').innerText = data.sent_fail;
        document.getElementById('log-box').innerText = data.log || 'Još nema aktivnosti...';
        
        const badge = document.getElementById('queue-badge');
        if (data.queue_count > 0 || data.is_waiting) {
          badge.className = 'badge badge-active';
          badge.innerText = '⏳ U TOKU (Drip-feed radi)';
        } else {
          badge.className = 'badge badge-idle';
          badge.innerText = '✅ SPREMNO (Red je prazan)';
        }
      } catch (e) {}
    }, 2000);
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "clear":
            with queue_lock:
                cleared = len(order_queue)
                order_queue.clear()
            add_log(f"🛑 Red čekanja je ispražnjen (obrisano {cleared} linkova).")
            return redirect(url_for("index"))

        elif action == "add":
            raw_links = request.form.get("input_links", "")
            comment_set_choice = request.form.get("comment_set", "set1")
            raw_delay = request.form.get("delay_minutes", "5")
            delay_seconds = parse_delay_to_seconds(raw_delay)
            links = [line.strip() for line in raw_links.splitlines() if line.strip()]

            sets = [
                ("Set #1", COMMENTS_SET_1),
                ("Set #2", COMMENTS_SET_2),
                ("Set #3", COMMENTS_SET_3),
            ]

            with queue_lock:
                for idx, link in enumerate(links):
                    if comment_set_choice == "set1":
                        set_name, comments = sets[0]
                    elif comment_set_choice == "set2":
                        set_name, comments = sets[1]
                    elif comment_set_choice == "set3":
                        set_name, comments = sets[2]
                    else:
                        set_name, comments = sets[idx % len(sets)]

                    order_queue.append({
                        "link": link,
                        "comments": comments,
                        "set_name": set_name,
                        "delay": delay_seconds,
                    })

            if links:
                add_log(f"📥 Dodano {len(links)} linkova u red čekanja (razmak: {format_delay(delay_seconds)}, mod: {comment_set_choice}).")
            return redirect(url_for("index"))

    with queue_lock:
        q_count = len(order_queue)
        ok_c = sent_ok_count
        fail_c = sent_fail_count
        current_log = "\n".join(log_lines)
        waiting = is_waiting

    return render_template_string(
        HTML_TEMPLATE,
        service_id=SERVICE_ID,
        queue_count=q_count,
        is_waiting=waiting,
        sent_ok=ok_c,
        sent_fail=fail_c,
        comments1_count=len(COMMENTS_SET_1),
        comments2_count=len(COMMENTS_SET_2),
        comments3_count=len(COMMENTS_SET_3),
        log=current_log,
    )


@app.route("/status")
def status():
    with queue_lock:
        return jsonify({
            "queue_count": len(order_queue),
            "sent_ok": sent_ok_count,
            "sent_fail": sent_fail_count,
            "is_waiting": is_waiting,
            "log": "\n".join(log_lines),
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
