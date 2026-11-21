# SashaLauncher — Minecraft лаунчер

Оффлайн + онлайн (Microsoft-лицензия, Ely.by) лаунчер на Python/CustomTkinter.
Скачивает официальные версии Mojang (jar, библиотеки, ассеты, natives) и запускает игру.

## Возможности

- **Офлайн-аккаунты** — просто имя игрока, как в пиратских лаунчерах
- **Microsoft** — вход по Device Code (лицензия), автообновление токена
- **Ely.by** — email+пароль, вход на лицензионные серверы через authlib-injector
- **Загрузчики** — выбор на вкладке «Играть»: **Ваниль / Fabric / Forge (1.13+) / NeoForge / Quilt**, Fabric работает с любым релизом 1.14+
- **Поиск по Modrinth** — вкладка «Моды»: ищешь мод, жмёшь «Скачать», зависимости (Fabric API и др.) подтягиваются автоматически
- Вкладка «Файлы»: моды / ресурспаки / шейдеры / датапаки — папки открываются в один клик, шейдеры требуют Fabric + Iris
- Любая официальная версия (релизы + снапшоты), установка в два клика
- Прогресс скачивания, живой консольный вывод игры, выбор ОЗУ до 32 ГБ, путь к java
- Параллельная загрузка файлов игры (24 потока)

## Запуск

```bash
pip install -r requirements.txt
python main.py
```

Windows: двойной клик по `launch.bat` (или `py -3 main.py`).
Linux/macOS: `./launch.sh`.

Игра и аккаунты лежат в `~/.sashalauncher/` (это НЕ папка `.minecraft`).

## Настройка Microsoft-входа (один раз)

1. Зайди на https://portal.azure.com → **Microsoft Entra ID** → **Регистрация приложений** → **Новая регистрация**
2. «Поддерживаемые типы учетных записей»: **любой организационный каталог + персональные (Microsoft)**
3. Redirect URI (тип «веб»): `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Скопируй **Application (client) ID** → вкладка «Настройки» лаунчера → поле Azure client_id → Сохранить

## Сборка своего .exe

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name SashaLauncher main.py
```

## Структура

```
main.py              GUI (CustomTkinter)
launcher/
  config.py          пути, настройки
  accounts.py        хранилище аккаунтов
  offline.py         офлайн-UUID (как у Mojang: md5 "OfflinePlayer:<name>")
  microsoft.py       Device Code OAuth → Xbox Live → XSTS → Minecraft
  elyby.py           Yggdrasil authserver.ely.by + authlib-injector
  versions.py        манифест версий Mojang (кэш 5 мин)
  installer.py       jar + библиотеки + ассеты (параллельно, по хэшам) + natives
  runner.py          поиск Java, JVM/GAME-аргументы, запуск процесса
tests/test_core.py   смок-тесты ядра: python3 tests/test_core.py
```

## Известные ограничения

- Поддерживаются Fabric, Forge (1.13+, через ForgeWrapper), NeoForge, Quilt
- Плагины ставятся только на сервер (Paper) — если нужно, попроси добавит запуск своего сервера
- Microsoft-вход требует своего Azure client_id (инструкция выше)
- authlib-injector для Ely.by скачивается автоматически при первом запуске Ely-аккаунта
