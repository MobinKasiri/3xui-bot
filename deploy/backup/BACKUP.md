# NC VPN — Full-server backup (Mac pull)

Daily at **3:00 AM** your Mac SSHes to the Germany VPS, runs a full export, and rsyncs it to `~/NCBackups/`. Only the **last 2 backups** are kept (on server and Mac).

## What is backed up

- 3X-UI + `/etc/x-ui` + xray config
- 3X-UI PostgreSQL (`xui`) + bot PostgreSQL (`nexorabot`)
- Bot, panel, data dirs (`/opt/nexoranode-*`)
- TLS certs, host nginx, UFW, SSH, systemd units, Docker config
- DR inventory (`meta/dr-inventory.txt`, optional `xui-nodes.conf`)

**Full disaster recovery:** see **[DISASTER-RECOVERY.md](./DISASTER-RECOVERY.md)** (~30 min restore to a new VPS).

Panel Telegram 6h backup is **panel DB only** — not a substitute for this.

## Step 1 — Install on Germany server

```bash
cd /opt/nexoranode-bot
git pull
sudo bash deploy/backup/install-local-backup.sh
```

Edit config:

```bash
sudo nano /etc/nc-vpn/backup.env
```

Set `XUI_PG_PASSWORD` (from 3X-UI panel settings).

Test export:

```bash
sudo /usr/local/lib/nc-vpn-backup/run-local-backup.sh
ls -la /var/lib/nc-vpn-backup/export/latest/
```

## Step 2 — Install on your Mac

From the repo (after `git pull`):

```bash
cd bot/3xui-shop
bash deploy/backup/mac/install-mac-backup.sh
```

Edit SSH settings:

```bash
nano ~/.config/nc-vpn/mac-backup.env
```

Set `SERVER_HOST`, `SERVER_SSH_PORT`, and `SSH_IDENTITY_FILE`.

Test a manual pull:

```bash
bash deploy/backup/mac/pull-backup-to-mac.sh
ls -la ~/NCBackups/latest/
```

## Step 3 — Verify schedule

```bash
launchctl print gui/$(id -u)/com.nc.vpn.backup-pull
```

Logs: `~/NCBackups/logs/`

## Retention (2 versions)

When the 3rd backup runs, the oldest dated folder is deleted automatically:

| Location | Path | Setting |
|----------|------|---------|
| Server | `/var/lib/nc-vpn-backup/export/` | `KEEP_LOCAL_VERSIONS=2` in `/etc/nc-vpn/backup.env` |
| Mac | `~/NCBackups/` | `KEEP_LOCAL_VERSIONS=2` in `~/.config/nc-vpn/mac-backup.env` |

## Restore to a new server

1. Copy a backup folder to the new VPS (or use `scp -r ~/NCBackups/latest root@NEW_IP:/root/restore/`).
2. Copy `/etc/nc-vpn/backup.env` from your password manager.
3. On fresh Ubuntu 24.04:

```bash
cd /opt/nexoranode-bot   # after cloning repos
sudo bash deploy/backup/restore-full-server.sh \
  --confirm-new-server \
  --from-dir /root/restore/latest
```

4. Update DNS if IP changed.
5. On Mac: `./scripts/update-pull-sync.sh`

## Useful commands

| Task | Command |
|------|---------|
| Manual server export | `sudo /usr/local/lib/nc-vpn-backup/run-local-backup.sh` |
| Manual Mac pull | `bash deploy/backup/mac/pull-backup-to-mac.sh` |
| Rsync only (skip remote export) | `bash deploy/backup/mac/pull-backup-to-mac.sh --skip-remote` |
| List Mac backups | `ls -la ~/NCBackups/` |

## Security

- Never commit `/etc/nc-vpn/backup.env` or `~/.config/nc-vpn/mac-backup.env` to git.
- Store `backup.env` in your password manager.
- Mac backups contain full DB dumps and `.env` files — encrypt your Mac disk (FileVault).
