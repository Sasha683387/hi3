import json
import os

APP_NAME = "SashaLauncher"

APP_DIR = os.path.join(os.path.expanduser("~"), ".sashalauncher")
GAME_DIR = os.path.join(APP_DIR, "game")
VERSIONS_DIR = os.path.join(GAME_DIR, "versions")
ASSETS_DIR = os.path.join(GAME_DIR, "assets")
LIBS_DIR = os.path.join(GAME_DIR, "libraries")
ACCOUNTS_FILE = os.path.join(APP_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
MANIFEST_CACHE = os.path.join(APP_DIR, "manifest_cache.json")
AUTHLIB_DIR = os.path.join(APP_DIR, "authlib-injector.jar")
MODS_DIR = os.path.join(GAME_DIR, "mods")
RPACKS_DIR = os.path.join(GAME_DIR, "resourcepacks")
SHADERS_DIR = os.path.join(GAME_DIR, "shaderpacks")
SAVES_DIR = os.path.join(GAME_DIR, "saves")
DATAPACKS_DIR = os.path.join(GAME_DIR, "datapacks")
PLUGINS_DIR = os.path.join(GAME_DIR, "plugins")
ICONS_DIR = os.path.join(APP_DIR, "icons")

DEFAULT_SETTINGS = {
    "ram_gb": 4,
    "java_path": "",
    "auto_java": True,
    "azure_client_id": "",
    "snapshots": False,
    "last_version": "",
    "window_theme": "dark",
}

os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(GAME_DIR, exist_ok=True)


def load_settings():
    merged = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            merged.update(json.load(f))
    except (OSError, ValueError):
        pass
    return merged


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def ensure_dirs():
    for d in (APP_DIR, GAME_DIR, VERSIONS_DIR, ASSETS_DIR, LIBS_DIR,
              MODS_DIR, RPACKS_DIR, SHADERS_DIR, SAVES_DIR,
              DATAPACKS_DIR, PLUGINS_DIR, ICONS_DIR):
        os.makedirs(d, exist_ok=True)
