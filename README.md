# mtk-vcom-unbrick

[![RU](https://img.shields.io/badge/doc-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-blue)](README.ru.md)

GUI tool + a patched **mtkclient** flow to unbrick MediaTek phones stuck in bootloop
**via PreLoader VCOM only** — no BROM, no test-point, no SP Flash Tool auth servers.

Verified on **Infinix Note 30 (X6833B, Helio G99 / MT6789)** — should work on other
Transsion-family (Infinix / Tecno / itel) and generally any MTK device reachable through
`MediaTek PreLoader USB VCOM`.

---

## Why it exists

Flashing `vendor_boot` back onto a bootlooping X6833B hits three walls:

| # | Wall | Root cause | Fix |
|---|------|-----------|-----|
| 1 | `Jump_DA Resp2 Cannot configure port ... PermissionError(13)` right after DA upload | mtkclient re-assigns `serial.device.timeout` on **every read**; pyserial then calls `_reconfigure_port()` → `SetCommState` storm kills the MediaTek VCOM driver after large writes (upstream [#274](https://github.com/bkerler/mtkclient/issues/274), Bug 4) | Guard the timeout assignment |
| 2 | Jump succeeds (`Jumping to 0x200000: ok.`) but DA seems dead — no `CMD:START` | XML frame reader uses a 0.02 s timeout; the DA simply hasn't finished booting yet over a 115200-style serial link | Byte-polling `get_response()` + active wait loop after `jump_da()` |
| 3 | SLA policy `Locked` in SP Flash Tool | Transsion server-side signature check | mtkclient ships a hardcoded Transsion SLA signature that the stock v6 DA accepts |

Also handled: `Port.serialportname` reconnect bug (#274 Bug 2), `check_sla()` crash on bool
responses (#296), heapbait exploit corrupting genuine signed DAs → tool runs mtkclient with `--stock`.

## What's inside

```
UnbrickTool.py            # GUI (tkinter, stdlib only)
UNBRICK_GUIDE_X6833B.md   # full step-by-step manual (RU) with all patch diffs & timeline
```

### UnbrickTool.py

* 🟢 live phone-presence indicator (auto-refresh)
* big colored status banner per phase
* 10-stage pipeline checklist (search → handshake → DA1 → jump → CMD:START → SLA → DA2 → GPT → write → done)
* write progress bar parsed from mtkclient output (~26 MB/s on this device)
* auto-retry: catches each PreLoader VCOM window of the bootloop until success
* one-click **“Patch mtkclient”** — applies all fixes to any local mtkclient copy (idempotent, keeps `.orig` backups)

### Patches applied to mtkclient

| File | Patch |
|------|-------|
| `Library/Connection/seriallib.py` | don't touch `device.timeout` unless changed (WinError 31); skip `comports()` scan for explicit port; fast open-retry inside the ~2.5 s preloader window |
| `Library/Port.py` | store `self.serialportname` (reconnect paths) |
| `Library/DA/xmlflash/xml_lib.py` | byte-polling `get_response()`; wait-for-`CMD:START` after jump; `check_sla()` bool guard |

Run mtkclient with `--stock` so carbonara/heapbait never touch your **genuine signed DA**.
Do **not** override the DA load address — use the address from the DA header itself
(`0x200000` here, not chipconfig's `0x201000`).

## Usage

```text
1. Phone in bootloop, plugged into PC (PreLoader VCOM appears/disappears every few sec).
2. Install MediaTek PreLoader VCOM driver + Python 3.10+ (pyserial, pyusb, pycryptodome).
3. Point the tool to:
     - your mtkclient folder,
     - DA_BR.bin from the STOCK firmware (download_agent/DA_BR.bin),
     - stock vendor_boot.img from the same firmware.
4. “Пропатчить mtkclient” once → then “ПОЧИНИТЬ ТЕЛЕФОН”.
5. When done: unplug, power on.
```

If the screen goes black and the phone goes silent mid-flow: the DA is still in SRAM with
watchdog disabled — hold **Power 10–15 s**, the tool resumes catching windows automatically.

## Disclaimer

Use on devices you own. Flashing wrong images can hard-brick. No warranty.

## Credits

* [bkerler/mtkclient](https://github.com/bkerler/mtkclient) — and issues [#274](https://github.com/bkerler/mtkclient/issues/274), [#296](https://github.com/bkerler/mtkclient/issues/296) for root-cause analysis of the serial bugs.
