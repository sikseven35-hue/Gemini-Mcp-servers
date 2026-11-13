# GeminiMCP CLI (`v0.1.0`)

**Credits:** Fikus & Hydrogen

Интерактивный CLI-мост, который подключает любую папку на вашем ПК к веб-версии **Gemini (`gemini.google.com`)** через **MCP (Model Context Protocol)** и **ngrok**.  
Позволяет моделям на сайте Gemini (включая Hydrogen / Argon и другие) читать, искать, создавать, редактировать файлы и при желании выполнять команды прямо в вашем проекте.

---

## Возможности
- **Один `.exe` файл** — работает без установленного Python на ПК.
- **Авто-настройка `ngrok`** — при первом запуске сам скачивает `ngrok.exe` и сохраняет ваш бесплатный токен.
- **Живое переключение проектов (`/folder`)** — меняйте папку на лету, **не переподключая URL в Gemini**.
- **Сессии (`/session`, `/sessions`)** — сохраняйте разные проекты (папка + права `/exec`) и переключайтесь между ними одной командой.
- **Терминал по требованию (`/exec on` / `off`)** — включайте или выключайте `run_command` в любой момент прямо во время работы.
- **Мониторинг (`/logs`, `/ls`, `/status`)** — видно в реальном времени, какие файлы читает и правит Gemini.

---

## Быстрый старт (через готовый `.exe`)

1. Скачайте **`gemini-mcp.exe`** из раздела [Releases](../../releases).
2. Получите бесплатный `ngrok` authtoken на [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken) (вход через Google в 1 клик).
3. Запустите `gemini-mcp.exe` (двойным кликом или из терминала):
   ```powershell
   gemini-mcp.exe "C:\Projects\MyApp"
   ```
   При первом запуске программа сама скачает `ngrok` и попросит вставить токен, после чего **скопирует готовую `https://.../mcp` ссылку в буфер обмена**.

---

## Как подключить к сайту Gemini (`gemini.google.com`)

1. Откройте [gemini.google.com](https://gemini.google.com/) (в настройках аккаунта должна быть включена **История действий / Keep Activity**).
2. Перейдите в **Меню → Настройки → Подключённые приложения (Connected Apps)**.
3. Нажмите **`+` (или `+ Інша` / Custom)** в правом верхнем углу.
4. Вставьте скопированную ссылку вида:
   ```text
   https://xxxx-xxxx.ngrok-free.dev/mcp
   ```
   Поля **Client ID** и **Client Secret** оставьте пустыми → нажмите **Next / Далі** → **Connect / Підключити**.
5. В чате вызовите `@Local PC Files GeminiMCP` и попросите прочитать или создать файлы!

---

## Команды внутри CLI (для вайбкодинга)

| Команда | Что делает |
| :--- | :--- |
| `/web` | Режим вайбкодинга на сайте: открывает `gemini.google.com`, копирует MCP URL и стримит live-логи в консоль (нажмите `Enter` для возврата в CLI) |
| `/attach <путь>` | Прикрепить файл, фото или видео в `_attachments/` (можно просто **перетащить файл (Drag & Drop)** в окно CLI и нажать `Enter`) |
| `/folder <путь>` | Переключить рабочую папку на лету (URL в Gemini остаётся тем же) |
| `/session <имя>` | Переключиться на сессию или создать новую (запоминает папку и `/exec`) |
| `/sessions` | Показать список всех сохранённых сессий |
| `/session del <имя>` | Удалить сохранённую сессию |
| `/exec on` / `/exec off` | Включить или выключить выполнение shell-команд (`run_command`) |
| `/url` | Показать и снова скопировать `https://.../mcp` в буфер обмена |
| `/ls [подпапка]` | Показать файлы в текущей рабочей папке |
| `/logs [N]` | Показать последние `N` вызовов инструментов от Gemini |
| `/status` | Показать активную сессию, папку, статус `/exec` и URL |
| `/clear` | Очистить экран |
| `/help` | Справка по командам |
| `/exit` | Остановить туннель и сервер |

### Флаги запуска
```powershell
gemini-mcp.exe [путь] [--session имя] [--port 8000] [--token NGROK_TOKEN] [--allow-exec] [--no-tunnel]
```

---

## Запуск и сборка из исходников

```powershell
cd source
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python gemini_mcp_cli.py
```

Сборка в `.exe` (PyInstaller):
```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\pyinstaller --noconfirm --onefile --console --name gemini-mcp `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.lifespan.on `
  gemini_mcp_cli.py
```

---

## Безопасность
- Все файловые операции жёстко ограничены выбранной корневой папкой (защита от `../` path traversal).
- Инструмент `run_command` **выключен по умолчанию** — включается только явно через `/exec on` или `--allow-exec`.
- Туннель работает только пока открыто окно `gemini-mcp.exe`.
