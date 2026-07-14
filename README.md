# nosplash-portal

A 3-tier captive portal splash page + admin dashboard, built to run on a
Raspberry Pi 4 alongside **RaspAP** and its captive-portal plugin (built on
**nodogsplash**, sometimes shorthanded "nosplashdog"). Flask app, SQLite
database, Stripe checkout for paid tiers.

- **Tag 1** — free, gated by an access code you generate (promo/production/private)
- **Tag 2** — $10 / 12 hours
- **Tag 3** — $35 / 72 hours

All tiers require name, email, phone, age, gender, and consent. The app also
records OS, device type, browser, MAC, and IP for every signup, and exports
the whole thing as CSV from `/admin`.

---

## 1. What's actually in here

```
app.py                 Flask routes: splash page, registration, Stripe checkout, admin
config.py               ALL tier pricing/duration/throttle settings live here
database.py             SQLite access layer + CSV export
device_fingerprint.py   Parses User-Agent into OS/device/browser
nds_client.py           Calls ndsctl to grant network access + set rate limits
schema.sql               Table definitions
templates/               splash.html, payment_result.html, admin.html, admin_login.html
static/                  CSS (dog-tag themed) + portal.js
requirements.txt
.env.example             Copy to .env and fill in
```

Edit **`config.py`** for prices, durations, and bandwidth caps — nothing else
in the codebase needs to change to adjust those numbers.

---

## 2. Install on the Pi

```bash
sudo apt update && sudo apt install -y python3-venv
cd /opt
sudo git clone <your-repo-or-copy-these-files-here> nosplash-portal
cd nosplash-portal
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env    # fill in Stripe keys, admin password, PUBLIC_BASE_URL, secret key
```

Run it once manually to confirm it boots:

```bash
python3 app.py
# visit http://<pi-ip>:5000 from another device on the LAN
```

Then run it for real as a service so it survives reboots:

```ini
# /etc/systemd/system/nosplash-portal.service
[Unit]
Description=nosplash captive portal
After=network.target

[Service]
WorkingDirectory=/opt/nosplash-portal
ExecStart=/opt/nosplash-portal/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
EnvironmentFile=/opt/nosplash-portal/.env
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nosplash-portal
```

---

## 3. Wiring it into RaspAP's captive portal (nodogsplash)

RaspAP's captive-portal plugin runs **nodogsplash**, which redirects any
unauthenticated client to a splash page URL and appends query params
(`clientip`, `clientmac`, `gatewayname`, `redir`, `tok`, etc.) — this app
reads those in `nds_params()` at the top of `app.py`.

1. In the RaspAP web UI, open the **Captive Portal** tab and point the
   splash page / redirect URL at `http://<pi-lan-ip>:5000/` (or configure
   nodogsplash's `nodogsplash.conf` directly — `FirewallRuleSet`,
   `GatewayInterface`, and the splash page URL setting).
2. **Confirm the exact query-string param names** nodogsplash sends on your
   installed version — they've shifted slightly across releases. Check
   `/etc/nodogsplash/nodogsplash.conf` and `man nodogsplash.conf`, then
   adjust the `.get()` keys in `nds_params()` in `app.py` if needed.
3. This app grants access by calling `ndsctl auth <mac> sessionlength=...
   uploadrate=... downloadrate=...` directly as a local subprocess (see
   `nds_client.py`) rather than using nodogsplash's redirect-based FAS auth
   — since the Flask app runs on the Pi itself, this is simpler and lets us
   set a **different session length and bandwidth cap per tier** in one call.
4. **Before going live**, verify `ndsctl auth`'s exact argument syntax on
   your Pi (`ndsctl --help`) — it has changed between nodogsplash versions.
   `nds_client.py` flags this same warning inline; treat that one command as
   the thing to test first.
5. Set `NDS_ENABLE_LIVE_GRANT=true` in `.env` once verified. Until then it
   runs in dry-run mode (logs what it *would* do) so you can build and test
   the payment/registration flow off the router.
6. The Flask process needs permission to run `ndsctl` — either run it as
   root (fine for a dedicated kiosk Pi) or grant a narrow `sudoers` rule for
   just that binary to the service user.

---

## 4. Stripe setup (Apple Pay, Google Pay, Cash App Pay, card)

This uses **Stripe Checkout** (Stripe-hosted payment page), not a custom
payment form — that matters here because:
- Apple Pay and Google Pay appear **automatically** on Checkout for
  eligible devices/browsers once `card` is enabled — no separate
  integration needed, and no domain verification required on your end
  since the page is hosted on `checkout.stripe.com`, not your Pi.
- Cash App Pay is enabled explicitly (`"cashapp"` in
  `payment_method_types` in `app.py`) and needs to be turned on for your
  account first.

Setup:
1. In the Stripe Dashboard (business account) → **Settings → Payment
   methods**, enable Cash App Pay, Apple Pay, and Google Pay.
2. Copy your **live** secret/publishable keys into `.env`.
3. Set `PUBLIC_BASE_URL` in `.env` to a URL the *guest's phone* can reach
   after paying — this is what Stripe redirects back to. On a plain LAN
   this is your Pi's LAN IP; it works because the guest device is on your
   Wi-Fi and gets pre-auth access to the splash page's own IP even before
   full internet access is granted (this is how nodogsplash pre-auth
   generally works — confirm the splash-page host is in nodogsplash's
   allowed pre-auth destinations).
4. **Webhooks are optional here.** The payment-confirmation flow in
   `/payment/complete` verifies the Checkout Session directly with Stripe's
   API when the guest's browser redirects back, so you don't need an
   inbound webhook for the core flow. A webhook is still nice to have for
   edge cases (guest closes the tab right after paying) but requires a
   public HTTPS endpoint reaching your Pi, which usually means a tunnel
   (Cloudflare Tunnel or ngrok) since most home/venue connections don't
   have a static public IP. Add that later if you want extra reliability —
   it's not required to take payments.
5. PayPal isn't wired in — Stripe alone covers all three payment methods
   you asked for (Apple Pay, Google Pay/"Android Pay", Cash App). If you
   want PayPal as a fourth option too, that's a separate Checkout branch
   using PayPal's own SDK; ask and I'll add it.

---

## 5. About the throttling — what this does and doesn't do

Every tier gets a bandwidth cap (`download_kbits` / `upload_kbits` in
`config.py`, defaulted to ~4 Mbps down / 1 Mbps up) applied per-client via
`ndsctl auth`'s rate-limit arguments. That's a blunt cap, not "block
streaming" — a slow connection will make most video buffer badly or fail to
start, but it won't selectively allow, say, a phone call while blocking
Netflix.

If you want something closer to true app-level blocking, that requires
either:
- **DNS-based blocking** of major streaming domains (Netflix, YouTube,
  Twitch, etc.) via `dnsmasq`'s `address=` overrides on the Pi — effective
  and simple, but a blocklist you maintain and users can bypass with a
  different DNS/VPN.
- **DPI/traffic-shaping** (e.g. classifying flows by SNI or port and
  applying `tc`/`iptables` rules) — meaningfully more work to build and
  keep working as services change their infrastructure.

The bandwidth-cap approach in this build is the practical default; happy to
add a `dnsmasq` blocklist file alongside it if you want a belt-and-suspenders
version — say the word and I'll generate one.

---

## 6. Data collected, and the legal fine print worth knowing

You're collecting name, email, phone, age, and gender, plus device/network
identifiers, from every guest. A few things worth doing regardless of
jurisdiction:

- The consent checkbox on the form is required to submit — keep it, and
  keep the language accurate to what you actually do with the data.
- **Texting guests** (e.g. marketing texts) using the phone numbers you
  collect here is separately regulated in the US (TCPA) — collecting the
  number for session management is fine, but sending marketing messages
  needs its own opt-in language, which isn't included here.
- `config.MIN_AGE` defaults to 13 — set it to whatever your venue's policy
  actually requires; collecting data from minors carries extra obligations
  (COPPA in the US, for example) depending on your age floor.
- This isn't legal advice — worth a quick pass by whoever handles
  compliance for the venue before you go live, especially if you're in the
  EU/UK (GDPR) or California (CCPA/CPRA), given you're storing PII tied to
  device identifiers.

---

## 7. Admin dashboard

`http://<pi-ip>:5000/admin` — login with `ADMIN_USERNAME` / `ADMIN_PASSWORD`
from `.env`. From there you can:
- View all signups (name, email, phone, age, gender, OS, device type, MAC,
  payment status, amount paid, session end time)
- Export everything as CSV (`/admin/export.csv`)
- Generate new Tier-1 access codes with their own use limits, duration, and
  bandwidth caps

The admin login is a simple password gate, fine for a single-operator kiosk
setup, but it's reachable from anywhere on your LAN by default. If the Pi
ever gets a public-facing address (e.g. via a tunnel for webhooks), put the
`/admin` routes behind your router's firewall or an additional layer (VPN,
IP allowlist) rather than relying on the password alone.
