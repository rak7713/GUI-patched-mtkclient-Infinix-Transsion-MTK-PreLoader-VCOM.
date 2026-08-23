# Infinix X6833B (MT6789) Unbrick Guide — vendor_boot restore via mtkclient over Serial VCOM

> Полный мануал восстановления телефона из bootloop'а, когда SP Flash Tool блокируется
> (`SECURITY-SET-FLASH-POLICY: Server is not authenticated. Locked.`), а mtkclient падает с
> `Cannot configure port ... PermissionError(13, ..., 31)` на прыжке в Download Agent.
>
> Всё нижеописанное проверено на реальном железе: Infinix Note 30 (X6833B), MT6789/Helio G99,
> Windows 10/11, Python 3.12, mtkclient 2.1.4.1, подключение ТОЛЬКО через PreLoader VCOM (BROM недоступен).

---

## 1. Симптомы

| Симптом | Причина |
|---|---|
| Bootloop (логотип → ребут каждые ~15 сек) | Повреждён `vendor_boot_a` |
| SP Flash Tool: `Server is not authenticated. Locked.` | SLA-политика Transsion: серверная подпись не совпадает |
| mtkclient: handshake OK → DA1 upload OK → `Jump_DA Resp2 Cannot configure port` | **Баг №1** (см. §3.1): pyserial перенастраивает COM-port на каждом чтении; после burst-а записи драйвер MediaTek VCOM отвалится с WinError 31 |
| После фикса №1: прыжок `ok`, но тишина, `Failed to upload da` | **Баг №2**: `get_response()` читает с таймаутом 0.02 c — DA не успевает загрузиться и отправить `CMD:START` |
| `Overriding DA1 address` → телефон виснет намертво | **Не переопределяйте адрес**: DA1 должен грузиться по адресу из ЗАГОЛОВОКА САМОГО DA-файла (`region[1].m_start_addr` = 0x200000), а не из chipconfig (`da_payload_addr` = 0x201000) |
| `Auth send failed: unpack requires a buffer of 2 bytes` | PreLoader Transsion не отвечает на `SEND_AUTH` в preloader-mode. Auth не нужен/не поддерживается |
| Телефон «чёрный экран» и молчит после сеанса | DA остался в памяти с выключенным watchdog → софт-ханг. Лечится ТОЛЬКО power-cycle (зажать питание 10–15 сек) |

Ключевой факт: **в preloader-mode DA работает поверх ТОГО ЖЕ VCOM-порта** (VID 0E8D PID 2000),
отдельный «DA VCOM» не появляется. Поэтому переход порта переживать не нужно — нужно
починить клиентские таймауты.

---

## 2. Что понадобится

```
mtkclient 2.1.4.1+          (github.com/bkerler/mtkclient)
Python 3.10+                (+ pip install pyserial pyusb pycryptodome)
Стоковая прошивка           (fw_test\vXXXX\vendor_boot.img — раздел целиком)
DA_BR.bin                   из ТОЙ ЖЕ прошивки (download_agent\DA_BR.bin, MTK_DA_v6)
MediaTek PreLoader VCOM driver
USB-кабель БЕЗ хаба, порт USB 2.0 предпочтительнее
```

Проверить DA-файл: заголовок должен содержать `MTK_DA_v6_YYYY-MM-DD`, hw_code = 0x1208.

---

## 3. Патчи mtkclient

Все патчи применяются к распакованному mtkclient. Ниже — точные правки.

### 3.1 `mtkclient/Library/Connection/seriallib.py` — usbread(): НЕ трогать timeout без изменений

Корневой баг (upstream issue bkerler/mtkclient#274, Bug 4).
pyserial при присвоении `device.timeout` вызывает `_reconfigure_port()` →
`SetCommTimeouts/SetCommState` на КАЖДОЕ чтение. После большой записи (404 КБ DA1)
это убивает линк: `PermissionError(13)` / WinError 31.

```python
# БЫЛО:
self.device.timeout = timeout

# СТАЛО:
if self.device.timeout != timeout:
    self.device.timeout = timeout
```

### 3.2 `seriallib.py` — connect(): не сканировать порты при явном имени + ретраи открытия

Окно PreLoader ~2.5 сек. Полный скан `comports()` съедает окно; открытие «только что
возникшего» порта может упасть в транзитном состоянии.

```python
def connect(self, ep_in=-1, ep_out=-1):
    if self.connected:
        self.close()
        self.connected = False

    # Явный порт (--serialport COMx) — открываем сразу, без скана
    port = None
    if self.portname not in (None, "", "DETECT"):
        port = self.portname
    else:
        ports = self.detectdevices()
        if ports:
            port = ports[0]
    if port is None:
        return False

    dev = None
    for attempt in range(20):
        try:
            dev = serial.Serial(port=port, baudrate=115200, bytesize=serial.EIGHTBITS,
                                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                timeout=500, xonxoff=False, dsrdtr=False, rtscts=False)
            break
        except Exception as e:
            self.debug(f"Port {port} open attempt {attempt} failed: {e}")
            time.sleep(0.02)          # быстро! окно 2.5с
    if dev is None:
        return False
    self.device = dev
    self.portname = port
    # ... далее без изменений (device._reset_input_buffer и т.д.)
```

### 3.3 `mtkclient/Library/Port.py` — сохранить serialportname (upstream #274, Bug 2)

Без этого reconnect-пути (`crasher()`, `bypass_security()`) теряют порт:

```python
if serialportname is not None and serialportname != "":
    self.cdc = SerialClass(portconfig=portconfig, loglevel=loglevel, devclass=10)
    self.cdc.setportname(serialportname)
    self.serialportname = serialportname      # <-- добавить эту строку
```

### 3.4 `mtkclient/Library/DA/xmlflash/xml_lib.py` — get_response(): байтовый поллинг

Вторая ключевая правка. Стандартный код читает 12-байтный заголовок фрейма с таймаутом
0.02 c сразу после прыжка — DA ещё грузится, фрейм не пришёл, всё умирает.
Поллинг реальных байтов решает раз и навсегда (работает для ВСЕХ XML-фреймов сессии):

```python
def get_response(self, raw: bool = False) -> str:
    import time as _t
    cdc = self.mtk.port.cdc

    def _waiting():
        try:
            return cdc.device.in_waiting if cdc.device is not None else 0
        except Exception:
            return 0

    sync = bytearray()
    deadline = _t.time() + 8
    while len(sync) < 12:
        n = _waiting()
        if n:
            sync.extend(self.usbread(min(n, 12 - len(sync))))
            continue
        if _t.time() > deadline:
            break
        _t.sleep(0.02)
    if len(sync) == 12 and int.from_bytes(sync[:4], 'little') == 0xfeeeeeef \
            and int.from_bytes(sync[4:8], 'little') == 0x1:
        length = int.from_bytes(sync[8:12], 'little')
        data = bytearray()
        ddeadline = _t.time() + 15
        while len(data) < length and _t.time() < ddeadline:
            n = _waiting()
            if n:
                data.extend(self.usbread(min(n, length - len(data))))
                continue
            _t.sleep(0.02)
        if len(data) == length:
            if raw:
                return data
            return data.rstrip(b"\x00").decode('utf-8')
    return ""
```

Формат фрейма (для отладки), приходит ровно такой:
```
EF EE EE FE | 01 00 00 00 | <len:u32 LE> | <?xml ...><host>...<command>CMD:START</command></host> | 00
```

### 3.5 `xml_lib.py` — upload_da1(): дождаться CMD:START после прыжка

```python
if self.mtk.preloader.jump_da(da1address):
    import time as _t
    cdc = self.mtk.port.cdc
    got_start = False
    deadline = _t.time() + 20
    while _t.time() < deadline:
        try:
            n = cdc.device.in_waiting
        except Exception:
            n = 0
        if n >= 12:
            _t.sleep(0.05)                      # дать фрейму прийти целиком
            cmd, result = self.get_command_result()
            if cmd == "CMD:START":
                got_start = True
                break
        _t.sleep(0.05)
    if got_start:
        self.setup_env()
        self.setup_hw_init()
        self.setup_host_info()
        return True
    else:
        self.error("No CMD:START from DA within 20s.")
        return False
```

### 3.6 `xml_lib.py` — check_sla(): защита от bool (upstream #296)

```python
data = self.get_sys_property(key="DA.SLA", length=0x200000)
if data is None or data is False:
    return False
data = data.decode('utf-8')
```

### 3.7 Запуск с `--stock` — ОБЯЗАТЕЛЬНО для подлинного DA

`python mtk.py w ... --stock` отключает carbonara/heapbait-эксплойты. Для корректно
подписанного стокового DA они не нужны, а heapbait ломает живой DA-сеанс даже на
genuine-подписи (upstream #296). SLA проходится встроенной Transsion-подписью внутри
mtkclient (ветка `b"Transsion" in da2` → hardcoded signature).

### 3.8 Чего делать НЕ надо

- ❌ Не переопределять `da1address` на `chipconfig.da_payload_addr` (0x201000) —
  DA собран под базу из собственного заголовка (0x200000). Ошибка базы =
  мгновенный краш DA + софт-ханг телефона (watchdog уже выключен!).
- ❌ Не слать auth-файл в preloader-mode — Transsion preloader не отвечает на SEND_AUTH.
- ❌ Не «помогать» реконнектом на другой COM — DA живёт на том же порту.

---

## 4. Процедура восстановления

### 4.1 Проверка окна PreLoader

Телефон в bootloop циклится: PreLoader VCOM виден ~2.5 сек каждые ~16–20 сек.
Проверка из PowerShell:

```powershell
Get-CimInstance Win32_PnPEntity | ? { $_.PNPDeviceID -like "*VID_0E8D*" } | % Name
# -> MediaTek PreLoader USB VCOM (Android) (COM3)
```

Если устройство есть, но порт не открывается («device not working») — stale devnode:
переткнуть кабель или power-cycle.

### 4.2 Автопилот (PowerShell)

Ловит окно, крутит попытки, глушит зависшие. Полный текст — `autopilot4.ps1`
(в этом репозитории/папке). Ключевая команда:

```powershell
python -u mtk.py w vendor_boot_a "$vb" --loader "$loader" --stock --serialport COM3 --loglevel 1
```

Маркеры прогресса в логе:

```
Successfully uploaded stage 1     <- DA1 принят
Jumping to 0x200000: ok.          <- ПРЫЖОК ПРОШЁЛ (после фикса 3.1)
CMD:START / DA LINK UP            <- DA ответил (после фиксов 3.4/3.5)
SLA checkpoint                    -> "SLA Signature was accepted."
Wrote ...vendor_boot.img to sector NNNNN with sector count NNNNN.   <- УСПЕХ
```

Скорости на этом железе: DA1 (404 КБ) ~3 c; DA2 (356 КБ) ~2 c @180 KB/s;
раздел 64 МБ ~2.5 c @26 MB/s.

### 4.3 Если телефон «чёрный экран» и молчит

Это софт-ханг: DA остался в SRAM с выключенным watchdog. Лечение одно:

> Зажать кнопку питания на 10–15 секунд (можно с подключённым кабелем).

После этого bootloop возобновится, окна вернутся, автопилот продолжит.

### 4.4 После успешной записи

mtkclient завершает сеанс штатно; телефон остаётся держать VCOM-порт.
**Отключить USB и нажать кнопку питания** — телефон стартует с восстановленным
`vendor_boot_a`. Первая загрузка может быть долгой.

---

## 5. Диагностические команды (если что-то идёт не так)

```powershell
# Все события USB по MediaTek (реальные появления/исчезновения):
Get-CimInstance Win32_PnPEntity | ? { $_.PNPDeviceID -like "*VID_0E8D*" } |
    % { "{0} code{1}" -f $_.Name, $_.ConfigManagerErrorCode }

# Ручной тест порта (ответ прелоадера на sync-байт):
python -c "import serial,time;s=serial.Serial('COM3',115200,timeout=0.5);s.write(b'\xa0');time.sleep(0.3);print(s.read(1).hex())"
# ожидание: 5f (инверсия a0). Если NONE/crash — окно закрыто либо stale-devnode.
```

Логи автопилота: `autopilot4.log`, попытки: `a4_N.out.log`.

---

## 6. Хронология этого конкретного кейса (для истории)

1. SFT + свой DA → упирается в SLA-policy `Locked` (серверная подпись).
2. mtkclient 2.1.4.1 + DA_BR.bin из стоковой прошивки v240502V576:
   handshake OK, но прыжок в DA убивал порт (WinError 31).
3. Найден upstream-issue #274 (тот же MT6789!): причина — перезапись
   `device.timeout` в каждом `usbread()` → `_reconfigure_port()` шторм → смерть VCOM.
4. После фикса: `Jumping to 0x200000: ok.` — прыжок подтверждён впервые.
5. Вторая стена: DA молчит после прыжка → перехватили трафик: `CMD:START` ПРИХОДИТ,
   но парсер читал с таймаутом 0.02 c раньше его прибытия → байтовый поллинг (§3.4/3.5).
6. Третья стена: ACK после загрузки DA2 съедается тем же таймаутом → тот же фикс
   в `get_response` закрыл и её.
7. Итог: `SLA Signature was accepted.` → `Wrote vendor_boot.img to sector 199168`
   (64 МБ, 26 MB/s) → телефон восстановлен.

## 7. Благодарности

- bkerler/mtkclient и авторы issues #274, #296 — анализ корней серийных багов.
- Команда mtkclient за hardcoded Transsion SLA-подпись в ветке Infinix.
