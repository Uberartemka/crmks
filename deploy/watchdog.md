# Watchdog deployment

The watchdog is a standalone process that requeues stalled `job_queue` tasks
and cleans up orphan Chromium processes. It must run as its own service,
independent of the FastAPI app and the queue worker.

## Install

```bash
# 1. Copy the unit file
sudo cp deploy/watchdog.service /etc/systemd/system/

# 2. Adjust paths inside the unit if your layout differs
sudo nano /etc/systemd/system/watchdog.service

# 3. Reload systemd and enable
sudo systemctl daemon-reload
sudo systemctl enable --now watchdog

# 4. Verify
sudo systemctl status watchdog
sudo journalctl -u watchdog -f
```

## Operation

- **Scan interval:** 60 s (see `backend/watchdog/config.py`).
- **Stall timeouts:** per task_type — `email_invoice`/`crm_lead` 60 s,
  `1c_sync`/`generate_pdf` 600 s.
- **Backoff:** failed tasks are deferred by `2^attempt × (1+jitter)` seconds,
  capped at attempt 6.

## Restart behaviour

`Restart=always` with `RestartSec=10`: if the watchdog crashes, systemd
brings it back in 10 s. A stuck scan does not affect the FastAPI app or the
queue worker — they continue independently.

## Why a separate process

- If the queue worker dies, the watchdog still requeues its in-flight tasks.
- If the FastAPI app is redeployed, the watchdog keeps running.
- One watchdog per cluster — do NOT run multiple instances, or tasks may be
  requeued redundantly. The unit file enforces a single instance.
