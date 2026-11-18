# NetPeek — простой гайд / Quick guide

**Коротко:** `netpeek` показывает, кто подключён к твоей сети, какие у тебя
IP, MAC, DNS и открытые порты, и ставит оценку безопасности твоему компьютеру.

Работает на **Windows**, **Linux** и **macOS**. Нужен только **Python 3.9+**.

> `netpeek` и `fsociety` — это **одна и та же программа**. Просто два имени,
> команды одинаковые. Что наберёшь — то и работает.

---

## 1. Установка (30 секунд)

### Windows

1. Скачай репозиторий: **Code → Download ZIP**, распакуй в любую папку
   (например `C:\netpeek`).
   Или через Git: `git clone https://github.com/dskil/netpeek.git`
2. Зайди в эту папку двойным кликом.
3. Запусти **`install.cmd`** — двойным кликом.

Скрипт сам создаст отдельное окружение `.venv`, поставит туда программу и
добавит её в PATH. Системный Python не трогается, права администратора не
нужны.

4. **Открой новое окно терминала** (важно: старое окно PATH не видит).
5. Проверь:

```powershell
netpeek --help
```

### Linux / macOS

```bash
git clone https://github.com/dskil/netpeek.git
cd netpeek
./install.sh
```

Потом **новый** терминал, или выполни `source ~/.bashrc` (для zsh —
`source ~/.zshrc`), и проверь:

```bash
netpeek --help
```

### Если установщик не хочешь запускать

Можно пользоваться прямо из папки репозитория, без установки:

```powershell
# Windows
netpeek.bat --help
fsociety.bat me
```

```bash
# Linux / macOS / Git Bash
./bin/netpeek --help
./bin/fsociety me
```

### Как удалить

```powershell
uninstall.cmd          # Windows
```
```bash
./uninstall.sh         # Linux / macOS
```

Удаляется `.venv` и запись в PATH. Больше ничего не остаётся.

---

## 2. Первые команды

Самые полезные — запомни три:

```bash
netpeek me        # всё про мой компьютер
netpeek scan      # кто в моей сети
netpeek --help    # список всех команд
```

### `netpeek me` — паспорт твоего устройства

Показывает сразу всё:

```
── THIS DEVICE ─────────────────────────────────────────
  hostname  : MY-PC
  workgroup : WORKGROUP

── IP ADDRESSES ────────────────────────────────────────
  Wi-Fi     : 192.168.0.42   (IPv4)
  Ethernet  : 10.0.0.15      (IPv4)
  public    : 203.0.113.7    (AS64500 Example ISP, XX)
  subnet    : 192.168.0.0/24

── MAC ADDRESSES ───────────────────────────────────────
  Wi-Fi     : A4:5E:60:12:34:56  (Apple, Inc.)

── GATEWAY & DNS ───────────────────────────────────────
  gateway   : 192.168.0.1
  dns       : 192.168.0.1, 8.8.8.8

── LISTENING PORTS (THIS DEVICE) ───────────────────────
  445    SMB      exposed     0.0.0.0    System   ⚠ SMB file sharing
  5000             localhost   127.0.0.1  python

── ACTIVE CONNECTIONS ──────────────────────────────────
  104.21.21.168   :443    HTTPS

── WI-FI ───────────────────────────────────────────────
  ssid      : HomeNet
  signal    : 84%
  security  : WPA2-Personal
```

Нужен только один раздел? Добавь флаг:

```bash
netpeek me --ip       # только IP
netpeek me --mac      # только MAC
netpeek me --dns      # только DNS
netpeek me --ports    # только мои порты
netpeek me --conns    # только соединения
netpeek me --wifi     # только Wi-Fi
```

### `netpeek scan` — кто в сети

```bash
netpeek scan
```

```
── DEVICES IN YOUR NETWORK ─────────────────────────────
  IP             MAC                VENDOR                     HOSTNAME
  ─────────────  ─────────────────  ─────────────────────────  ────────
  192.168.0.1    50:FF:20:76:59:50  Unknown vendor
  192.168.0.45   F6:F9:73:0E:71:AC  Private / randomized MAC
  192.168.0.103  AA:42:7A:83:0D:F6  Private / randomized MAC

  3 device(s) found
```

Полезные варианты:

```bash
netpeek scan --no-sweep     # быстро, только из ARP-таблицы
netpeek scan --resolve      # ещё и имена устройств (медленнее)
```

> **Почему «Private / randomized MAC»?** Телефоны и ноутбуки специально
> меняют MAC-адрес для приватности. Это нормально, не ошибка.

---

## 3. Что ещё умеет

### Всё про свою сеть

| Команда | Что делает |
|---|---|
| `netpeek ip` | локальный и публичный IP |
| `netpeek mac` | MAC всех интерфейсов + производитель |
| `netpeek gateway` | шлюз и DNS |
| `netpeek myports` | какие порты слушает мой компьютер |
| `netpeek conns` | куда сейчас подключён |
| `netpeek wifi` | SSID, сигнал, шифрование |
| `netpeek myip` | публичный IP + страна/провайдер |
| `netpeek subnet` | разбор подсети: маска, диапазон, число хостов |

### Сеть вокруг

```bash
netpeek ports 192.168.0.1                 # открытые порты роутера
netpeek ports 192.168.0.1 --range 1-1024  # конкретный диапазон
netpeek banner 192.168.0.1 80             # что отвечает сервис
```

### Публичные данные

```bash
netpeek dns google.com     # DNS-записи + проверка SPF/DMARC/DKIM
netpeek whois google.com   # владелец домена, даты регистрации
netpeek tls google.com     # сертификат: кто выдал и когда истекает
```

### Безопасность моего компьютера

```bash
netpeek audit      # найти проблемы: опасные порты, фаервол, пароли
netpeek score      # оценка от 0 до 100
netpeek firewall   # включён ли фаервол
netpeek updates    # когда ставились обновления системы
```

### Отчёты

```bash
netpeek report                        # создаст report.md и report.json
netpeek report --output C:\reports    # в конкретную папку
netpeek export --format html          # красивый HTML-отчёт
```

---

## 4. Полезные флаги (работают у всех команд)

| Флаг | Что делает |
|---|---|
| `--help` | справка по команде |
| `--json` | вывод в JSON — удобно для скриптов |
| `--no-color` | без цветов (для логов и скриншотов) |

Примеры:

```bash
netpeek me --help                 # какие есть опции у `me`
netpeek me --ip --json            # данные в JSON
netpeek scan --json | Out-File scan.json
```

---

## 5. Частые вопросы

**«Пишет: command not found» / «не является внутренней командой»**
Ты не открыл новое окно терминала после установки. Закрой терминал и открой
снова. Если не помогло — запусти `install.cmd` ещё раз, он покажет, куда
добавил PATH.

**«Нужен ли Python?»**
Да, 3.9 или новее. Скачать: https://www.python.org/downloads/
При установке на Windows обязательно оставь галочку **«Add python.exe to
PATH»**.

**«Это законно?»**
Да, если речь про **твою** сеть. Программа только читает: она не взламывает,
не подбирает пароли и не меняет ничего в системе. Сканировать чужие сети без
письменного разрешения — незаконно, и программа специально отказывается это
делать: любой адрес вне твоей подсети она отклоняет с ошибкой.

```bash
netpeek ports 8.8.8.8
# ⚠ 8.8.8.8 is outside your local network (...) — отказ
```

**«Куда пишутся настройки?»**
Windows: `%APPDATA%\netpeek\`
Linux/macOS: `~/.config/netpeek/`
Там `config.toml` и история твоих команд. Отчёты `report.*` лежат в текущей
папке — они уже в `.gitignore`, в git не попадут.

**«Как сравнить два отчёта?»**
```bash
netpeek diff old.json new.json
```
Покажет, какие устройства появились, ушли или сменили MAC.

**«Хочу следить за сетью в реальном времени»**
```bash
netpeek watch --interval 60
```
Каждые 60 секунд сканирует сеть и печатает, кто подключился или отключился.
Остановить — `Ctrl+C`.

---

## 6. Полная справка

```bash
netpeek --help          # все команды
netpeek <команда> --help  # опции конкретной команды
```

Полное описание на английском: [README.md](README.md)

---

## Лицензия

MIT — делай что хочешь, но **используй только на своих сетях** или там, где
у тебя есть письменное разрешение.
