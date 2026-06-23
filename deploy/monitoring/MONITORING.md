# NC VPN — Monitoring with UptimeRobot only

Bot and panel URLs are **grey-cloud DNS → Germany IP**. They are **not reachable from Iran without VPN**, but **UptimeRobot probes from the internet** (US/Europe) — so cloud monitoring works 24/7 without your Mac.

Local Mac/server monitors were removed on purpose. Use this guide only.

---

## What UptimeRobot can cover

| Alert | Monitor | URL |
|-------|---------|-----|
| Bot down | HTTPS keyword | `https://bot.nexoranode.xyz:8443/health` → body contains `OK` |
| Panel down | HTTPS keyword | `https://manage.nexoranode.xyz:2053/api/health` → body contains `"status":"ok"` |
| Germany server down | Same as above | If bot+panel fail, VPS or nginx is likely down |
| 3X-UI panel (optional) | HTTPS | `https://p.nexoranode.xyz:2057/` (login page loads) |

**Cannot automate via UptimeRobot:**

- Per-node xray sync (PL/SG/US) — needs SSH. Run manually: `./scripts/verify-node-sync.sh` when on VPN.
- Subscription URL quality — test manually after changes.

---

## Step 1 — Create UptimeRobot account

1. Go to [https://uptimerobot.com](https://uptimerobot.com) and sign up (free tier: 50 monitors, 5‑min interval).
2. Confirm your email.

---

## Step 2 — Telegram alert contact

1. UptimeRobot → **My Settings** → **Alert Contacts** → **Add Alert Contact**
2. Type: **Telegram**
3. Follow the link to connect your Telegram account (use the same account as `ADMIN_CHAT_ID`)
4. Save — note the contact name (e.g. `Telegram - Mobin`)

---

## Step 3 — Monitor: Telegram bot

1. **Add New Monitor**
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** `NC VPN — Bot`
4. **URL:** `https://bot.nexoranode.xyz:8443/health`
5. **Monitoring Interval:** 5 minutes
6. **Monitor Timeout:** 30 seconds
7. **HTTP Method:** GET
8. Enable **Keyword monitoring**
   - **Keyword type:** Keyword Exists
   - **Keyword:** `OK`
9. **Alert Contacts:** your Telegram contact
10. Create monitor

---

## Step 4 — Monitor: Admin panel

1. **Add New Monitor**
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** `NC VPN — Panel`
4. **URL:** `https://manage.nexoranode.xyz:2053/api/health`
5. **Interval:** 5 minutes
6. **Keyword Exists:** `"status":"ok"`
7. **Alert Contacts:** Telegram
8. Create monitor

---

## Step 5 — Monitor: 3X-UI panel (optional)

1. **URL:** `https://p.nexoranode.xyz:2057/` (or your panel path)
2. **Keyword:** e.g. `login` or `3x-ui` (whatever appears on the login page)
3. Alerts if the VPN control panel is unreachable.

---

## Step 6 — Test

1. In UptimeRobot, open each monitor → **Test Alert Contact** (or wait for first check).
2. You should see **Up** (green) when services are healthy.
3. Optional: on the server, `docker stop nexoranode-bot` for 1 minute — UptimeRobot should alert within ~5 min, then restart the container.

---

## Alert behaviour

- **Down** → Telegram message from UptimeRobot (not your bot — that’s expected when the bot is down).
- **Up again** → recovery notification (enable in alert contact settings if you want).

---

## If you installed old local monitors — remove them

**Mac:**

```bash
launchctl bootout "gui/$(id -u)/com.nc.vpn.monitor" 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.nc.vpn.monitor.plist
rm -rf ~/.config/nc-vpn/monitor-state ~/.config/nc-vpn/monitor-logs
# optional: rm ~/.config/nc-vpn/monitor.env
```

**Germany server:**

```bash
sudo systemctl disable --now nc-vpn-watchdog.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/nc-vpn-watchdog.{service,timer}
sudo systemctl daemon-reload
sudo rm -rf /usr/local/lib/nc-vpn-monitor /var/lib/nc-vpn-monitor /etc/nc-vpn/monitor.env
```

---

## Backup failure alerts (still on server)

Backup scripts can still Telegram-alert on **failed export** via `notify_failure` in `deploy/backup/lib.sh` (uses bot token when the server is up). That is separate from uptime monitoring.

---

## Node / config sync (manual)

When you change nodes or users report connection issues (on VPN):

```bash
export API_TOKEN="..."
./scripts/verify-node-sync.sh
```

Add new locations only in `scripts/nodes.conf` — verify picks up all nodes automatically.

---

## Summary

| Layer | Tool | 24/7 | Needs Mac | Needs Iran VPN |
|-------|------|------|-----------|----------------|
| Bot / panel / server up | **UptimeRobot** | ✅ | ❌ | ❌ |
| Mac backup | `pull-backup-to-mac.sh` | Only if Mac awake | ✅ | SSH needs VPN |
| Node xray sync | `verify-node-sync.sh` | Manual | ✅ | SSH needs VPN |
