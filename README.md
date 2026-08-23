# mtk-vcom-unbrick — гайд пользователя

[← English](README.md)

Простая инструкция: как оживить телефон Infinix/Tecno (MTK), который висит в bootloop
(перезагружается по кругу), если под рукой нет BROM-режима и SP Flash Tool пишет
`Locked`.

---

## Что нужно перед стартом

| Что | Где взять |
|---|---|
| ПК с Windows 10/11 | — |
| Python 3.10+ | python.org (при установке отметь **Add to PATH**) |
| Библиотеки: `pyserial`, `pyusb`, `pycryptodome` | `pip install pyserial pyusb pycryptodome` |
| mtkclient (распакованный) | github.com/bkerler/mtkclient → Code → Download ZIP |
| Драйвер MediaTek PreLoader VCOM | ставится обычно вместе с SP Flash Tool / ищется как «MediaTek USB VCOM drivers» |
| Стоковая прошивка твоего телефона | из неё нужны 2 файла: `vendor_boot.img` и `download_agent/DA_BR.bin` |
| Кабель USB | желательно хороший, без хабов |

> Важно: `DA_BR.bin` и `vendor_boot.img` должны быть **из одной и той же версии прошивки**.

---

## Шаг 1. Установка

1. Скачай папку с этим инструментом (UnbrickTool.py).
2. Запусти:
   ```
   python UnbrickTool.py
   ```
3. В окне программы укажи три пути:
   - **Папка mtkclient** — где лежит `mtk.py`
   - **DA_BR.bin**
   - **vendor_boot.img**

## Шаг 2. Пропатчить mtkclient

Нажми кнопку **«Пропатчить mtkclient»**.

Программа сама внесёт все исправления в код mtkclient (создаст резервные копии `.orig`):
- фикс разрыва порта WinError 31 после загрузки DA;
- ожидание ответа DA (без этого «тишина» после прыжка);
- обход падения check_sla;
- быстрые ретраи открытия порта.

Должно появиться: **«Все патчи на месте — mtkclient готов к работе.»**

## Шаг 3. Подключить телефон

1. Телефон должен быть в бутлупе (сам перезагружается) и вставлен в USB.
2. Нажми **«Проверить телефон»**.
   - 🟢 «ПОДКЛЮЧЁН (PreLoader VCOM)» — отлично, переходи к шагу 4.
   - 🔴 «НЕ НАЙДЕН» — зажми кнопку питания на 10–15 сек, отпусти. Телефон начнёт
     циклиться, индикатор станет зелёным. Если нет — проверь кабель/драйвер.

## Шаг 4. ПОЧИНИТЬ ТЕЛЕФОН

Нажми большую зелёную кнопку **«▶ ПОЧИНИТЬ ТЕЛЕФОН»** и не трогай компьютер.

Программа сама:
1. поймает короткое «окно» прелоадера (~2.5 сек);
2. загрузит DA и перепрыгнет в него;
3. пройдёт защиту Transsion (SLA);
4. запишет стоковый `vendor_boot` в раздел `vendor_boot_a` (~3 сек, 26 МБ/с);
5. при неудаче — повторит попытку снова и снова.

Следи за большим цветным баннером и чеклистом этапов:

```
✓ Поиск PreLoader VCOM      ← телефон циклится
✓ Хендшейк                  ← связь есть
✓ Загрузка DA               ← агент загружен
✓ Прыжок в DA               ← критический этап пройден
✓ CMD:START от DA           ← агент живой
✓ SLA Transsion             ← защита обошлена
✍ Запись vendor_boot_a      ← ИДЁТ ЗАПИСЬ — НЕ ТРОГАЙ КАБЕЛЬ!
🏁 Готово!
```

## Шаг 5. После записи

1. Дождись баннера **«🎉 ГОТОВО! ТЕЛЕФОН ПОЧИНЕН!»**
2. Отключи USB-кабель.
3. Зажми кнопку питания на 5–10 сек → отпусти.
4. Первое включение может занять больше обычного — это нормально.

---

## Если что-то пошло не так (FAQ)

**Экран телефона чёрный, программа молчит / этапы стоят.**
Телефон «уснул» в DA-режиме (так устроена прошивка). Зажми кнопку питания на
10–15 секунд, НЕ выключая программу. Телефон снова начнёт циклиться — попытки
продолжатся автоматически.

**🔴 Телефон не найден вообще.**
Проверь кабель и порт (лучше USB 2.0, без хаба). Проверь драйвер: диспетчер устройств →
должно быть «MediaTek PreLoader USB VCOM (Android)». Поставь батарею на зарядку — глубоко
разряженный телефон может не показывать PreLoader.

**Ошибка `Cannot configure port ... PermissionError(13)` в логе.**
Значит mtkclient НЕ пропатчен. Вернись к шагу 2.

**`SLA Key wasn't accepted`.**
Убедись, что DA_BR.bin взят из родной прошивки именно твоей модели. Другие версии DA
не примут подпись.

**Записалось, но всё равно бутлуп.**
Возможно, активный слот не `a`, либо повреждено что-то ещё (boot/recovery/vbmeta).
Открой issue с логом из окна программы.

---

## Как это работает (коротко)

Обычные инструменты падают на трёх вещах: порт умирает после загрузки DA (баг pyserial/
mtkclient), агент «молчит» из-за слишком короткого таймаута чтения, а SP Flash Tool
требует серверную подпись Transsion. Здесь: пропатченный клиент + подпись, встроенная в
стоковый DA от Transsion, + автоловля окон прелоадера. Подробности — в
`UNBRICK_GUIDE_X6833B.md`.

## Disclaimer

Используй только на своих устройствах. Прошивка чужими образами может окончательно
убить телефон. Всё делаешь на свой риск.

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
