# Start Telegram-Stremio on boot

This uses a **systemd user service** plus lingering, so it starts at boot without
requiring a login. No root access is needed.

## Install

```bash
mkdir -p ~/.config/systemd/user
cp deploy/telegram-stremio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now telegram-stremio
loginctl enable-linger "$USER"
```

The unit assumes the repo is at `~/Documents/Telegram-Stremio`. Edit
`WorkingDirectory` and `ExecStart` if it lives elsewhere.

## MongoDB containers

```bash
docker update --restart unless-stopped ts-mongo ts-mongo-storage
systemctl is-enabled docker   # must be enabled
```

## Commands

```bash
systemctl --user status telegram-stremio
journalctl --user -u telegram-stremio -f
systemctl --user restart telegram-stremio
systemctl --user stop telegram-stremio
systemctl --user disable --now telegram-stremio
```

## Notes

- `Restart=on-failure` retries the server every 10 seconds if Mongo is not ready
  yet at boot.
- The service runs in the user's session but `enable-linger` keeps it alive after
  logout.
- Delete `~/.config/systemd/user/telegram-stremio.service` and run
  `systemctl --user daemon-reload` to uninstall.
