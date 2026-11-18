# Internet Mode Deployment

Customer location invitations only work if the customer's phone can open an **HTTPS** URL that is reachable from the Internet. Browsers block the Geolocation API on non-secure origins, and `localhost` / `192.168.x.x` / `10.x.x.x` addresses are not reachable by customers. The application enforces this: until a valid public HTTPS URL is configured, invitation creation is disabled and the UI lists the steps below.

Everything else in the application works without Internet Mode.

## Option comparison

| Option | Mandatory cost | Requires | Suitability |
|---|---|---|---|
| **1. Cloudflare Quick Tunnel** (public-only port) | **0** | Free `cloudflared` binary; **no account** | Pilot / low volume. URL changes on each restart; no uptime guarantee. |
| 2. Own office PC with public IP + free DNS + Caddy | 0 if the ISP provides a public, reachable IP | Router port-forwarding, free dynamic-DNS name, Caddy | Many Egyptian residential lines are behind carrier-grade NAT – confirm with your ISP. |
| 3. VPS + domain + Caddy | **Paid (VPS, domain)** – needs explicit approval | VPS account and payment | Production, multi-user over Internet. |

No VPS option is listed as "free": the well-known always-free cloud tiers require a payment card for verification, which conflicts with the zero-cost policy.

## Option 1 – Zero cost: Cloudflare Quick Tunnel to the public-only port

Only the consent page (`/p/<token>`) is exposed. The admin UI and API stay on `127.0.0.1`.

1. Download `cloudflared` for Windows from Cloudflare's official GitHub releases (`github.com/cloudflare/cloudflared/releases`, Apache-2.0).
2. Start Tahqiq with the public listener:
   * Desktop: create a shortcut to `Tahqiq.exe --public-port 8001`, or
   * Source/web: `python -m app.serve --public-only --port 8001` in a second terminal, with `TAHQIQ_TRUST_PROXY=1`.
3. Run: `cloudflared tunnel --url http://127.0.0.1:8001`
4. Copy the printed `https://<random-words>.trycloudflare.com` URL.
5. In Tahqiq: **Settings → Public access URL** → paste → Save. The dashboard shows "Internet Mode enabled".
6. Create an invitation and send it via copy / WhatsApp / SMS from your own phone.

Limitations to accept consciously:
* The URL is random and changes every time `cloudflared` restarts → update the setting; earlier unanswered links stop working.
* Cloudflare positions quick tunnels for testing/development, without uptime guarantees.
* The PC and `cloudflared` must be running while customers open their links.

## Option 2 – Own machine with a public IP

1. Confirm with the ISP that the line has a public IPv4 (not CGNAT) and that inbound ports 80/443 are allowed.
2. Get a free dynamic-DNS hostname (e.g. DuckDNS) pointing to the public IP.
3. Forward router ports 80 and 443 to the Tahqiq machine.
4. Install Caddy (free). Caddyfile – expose only the consent page:
   ```
   your-name.duckdns.org {
       handle /p/* {
           reverse_proxy 127.0.0.1:8001
       }
       handle {
           respond 404
       }
   }
   ```
   Caddy obtains a free Let's Encrypt certificate automatically.
5. Run the public-only server on 8001 (as in Option 1, step 2) with `TAHQIQ_TRUST_PROXY=1`.
6. Set **Public access URL** to `https://your-name.duckdns.org`.

## Option 3 – VPS (paid, requires approval)

Use when operators need access from outside the office. Ubuntu 24.04 example:

```bash
sudo adduser --system --group tahqiq
sudo mkdir -p /opt/tahqiq /var/lib/tahqiq && sudo chown tahqiq: /var/lib/tahqiq
sudo git clone <repo> /opt/tahqiq && cd /opt/tahqiq
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)          # or copy a prebuilt dist/
sudo cp deploy/tahqiq.service /etc/systemd/system/ # edit domain
sudo systemctl enable --now tahqiq
sudo -u tahqiq TAHQIQ_DATA_DIR=/var/lib/tahqiq .venv/bin/python -m app.serve create-admin admin   # run from /opt/tahqiq/backend
sudo apt install caddy && sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
Firewall: allow 22, 80, 443 only. The app listens on `127.0.0.1:8000` behind Caddy. Set `TAHQIQ_PUBLIC_BASE_URL` in the unit file. Cookies are marked `Secure` automatically when requests arrive over HTTPS through the proxy.

Resource needs are small (1 vCPU, 1 GB RAM is sufficient for 1–5 users). SQLite is adequate for this load; see the PostgreSQL migration guide if usage grows.

## After any option – verification

1. Dashboard shows *Internet Mode enabled*.
2. Create an invitation; open the link on a phone using mobile data (not office Wi-Fi).
3. Accept → the investigation's Location tab shows one historical point with collection time; the audit log shows `invitation.opened` and `invitation.shared`.
