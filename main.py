"""SashaLauncher — GUI (CustomTkinter)."""

import os
import queue
import subprocess
import sys
import threading
import webbrowser

import customtkinter as ctk

from launcher import __version__ as APP_VERSION
from launcher import accounts, config, doctor, elyby, fabric, installer, microsoft, modrinth, offline, runner, updater, versions

ctk.set_appearance_mode("dark")

BGC = "#12151a"
PANEL = "#191d24"
CARD = "#1f2530"
CARD_HOVER = "#28303d"
SIDEBAR = "#14171d"
ACCENT = "#3aa856"
ACCENT_HOVER = "#4cc36d"
TEXT = "#e8ecf1"
MUTED = "#8b93a1"
DANGER = "#8a3b3b"
DANGER_HOVER = "#a34747"


def font(size, bold=False):
    return ctk.CTkFont(
        "Segoe UI", size=int(round(size)), weight="bold" if bold else "normal"
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        config.ensure_dirs()
        self.settings = config.load_settings()
        from launcher import http_util as _http

        _http.use_mirror = bool(self.settings.get("mirror", True))
        self.title("SashaLauncher %s" % APP_VERSION)
        self.geometry("940x620")
        self.minsize(820, 540)
        self.configure(fg_color=BGC)

        self.proc = None
        self.busy = False
        self.busy_mod = False
        self.ui_queue = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=BGC, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self._page_play = self._build_play_page()
        self._page_mods = self._build_mods_page()
        self._page_files = self._build_files_page()
        self._page_account = self._build_account_page()
        self._page_settings = self._build_settings_page()
        self._page_console = self._build_console_page()
        for name, page in [
            ("Играть", self._page_play),
            ("Моды", self._page_mods),
            ("Файлы", self._page_files),
            ("Аккаунт", self._page_account),
            ("Настройки", self._page_settings),
            ("Консоль", self._page_console),
        ]:
            self.pages[name] = page
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

        self.show_page("Играть")
        self._loader_type_changed()
        self.after(250, self._drain_queue)
        self._doctor_evt = threading.Event()
        self._doctor_answer = False
        self.after(2500, self._auto_update, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_versions()
        self._refresh_account_header()

    # ================= sidebar =================

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=SIDEBAR)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(10, weight=1)

        head = ctk.CTkFrame(bar, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 2))
        ctk.CTkLabel(
            head, text="SashaLauncher", font=font(19, True), text_color=TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(head, text=APP_VERSION, font=font(11), text_color=MUTED).pack(
            anchor="w"
        )

        self.nav_buttons = {}
        for i, name in enumerate(
            ["Играть", "Моды", "Файлы", "Аккаунт", "Настройки", "Консоль"], start=1
        ):
            b = ctk.CTkButton(
                bar, text=name, height=40, corner_radius=10, anchor="w",
                font=font(14), fg_color="transparent", hover_color=CARD_HOVER,
                text_color=MUTED, command=lambda n=name: self.show_page(n),
            )
            b.grid(row=i, column=0, sticky="ew", padx=10, pady=3)
            self.nav_buttons[name] = b

        chip = ctk.CTkFrame(bar, corner_radius=10, fg_color=CARD)
        chip.grid(row=20, column=0, sticky="ew", padx=10, pady=(0, 16))
        self.chip_label = ctk.CTkLabel(
            chip, text="нет аккаунта", font=font(12), text_color=MUTED,
            justify="left",
        )
        self.chip_label.pack(anchor="w", padx=12, pady=8)

    def show_page(self, name):
        for p in self.pages.values():
            p.grid_remove()
        self.pages[name].grid()
        if name == "Файлы":
            self.refresh_files()
        for n, b in self.nav_buttons.items():
            active = n == name
            b.configure(
                fg_color=CARD if active else "transparent",
                text_color=TEXT if active else MUTED,
            )

    # ================= play page =================

    def _build_play_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))

        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 14))
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(side="left")
        ctk.CTkLabel(inner, text="ВЕРСИЯ MINECRAFT", font=font(11), text_color=MUTED).pack(
            anchor="w"
        )
        self.version_box = ctk.CTkComboBox(
            inner, values=["загрузка..."], width=280, height=36,
            corner_radius=10, border_width=0, fg_color="#262d3a",
            button_color=CARD_HOVER, button_hover_color="#323c4c",
            dropdown_fg_color="#262d3a", dropdown_hover_color=CARD_HOVER,
            text_color=TEXT, font=font(14),
        )
        self.version_box.pack(anchor="w", pady=(4, 0))
        self.snap_var = ctk.BooleanVar(value=bool(self.settings.get("snapshots")))
        ctk.CTkCheckBox(
            row, text="снапшоты", variable=self.snap_var,
            command=self._snap_toggled, font=font(12), text_color=MUTED,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
        ).pack(side="right", pady=(0, 2))
        self.loader_box = ctk.CTkComboBox(
            row, values=["..."], width=150, height=34, corner_radius=10,
            border_width=0, fg_color="#262d3a", button_color=CARD_HOVER,
            button_hover_color="#323c4c", dropdown_fg_color="#262d3a",
            dropdown_hover_color=CARD_HOVER, text_color=TEXT, font=font(13),
        )
        self.loader_type = ctk.CTkComboBox(
            row, values=["Ваниль", "Fabric", "Forge", "NeoForge", "Quilt"],
            width=130, height=38, corner_radius=10, border_width=0,
            fg_color="#262d3a", button_color=CARD_HOVER,
            button_hover_color="#323c4c", dropdown_fg_color="#262d3a",
            dropdown_hover_color=CARD_HOVER, text_color=TEXT,
            font=font(13), command=self._loader_type_changed,
        )
        prev = self.settings.get("loader_type") or (
            "Fabric" if self.settings.get("fabric") else "Ваниль"
        )
        if prev not in ("Ваниль", "Fabric", "Forge", "NeoForge", "Quilt"):
            prev = "Ваниль"
        self.loader_type.set(prev)
        self.loader_type.pack(side="right", padx=(0, 10), pady=(0, 2))

        chips = ctk.CTkFrame(page, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", padx=18)
        self.chip_ram = ctk.CTkLabel(
            chips, text="", font=font(12), text_color=MUTED, justify="left"
        )
        self.chip_ram.pack(side="left")
        ctk.CTkLabel(chips, text="  ·  ", font=font(12), text_color="#3a4250").pack(
            side="left"
        )
        ctk.CTkLabel(chips, text="  ·  ", font=font(12), text_color="#3a4250").pack(
            side="left"
        )
        self.chip_loader = ctk.CTkLabel(
            chips, text="", font=font(12), text_color=MUTED, justify="left"
        )
        self.chip_loader.pack(side="left")
        ctk.CTkLabel(chips, text="  ·  ", font=font(12), text_color="#3a4250").pack(
            side="left"
        )
        self.chip_acc = ctk.CTkLabel(
            chips, text="", font=font(12), text_color=MUTED, justify="left"
        )
        self.chip_acc.pack(side="left")

        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=18, pady=(6, 18))
        bottom.grid_columnconfigure(0, weight=1)

        self.play_btn = ctk.CTkButton(
            bottom, text="▶   ИГРАТЬ", height=60, corner_radius=16,
            font=font(21, True), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#0f130e", command=self.on_play,
        )
        self.play_btn.grid(row=0, column=0, sticky="ew")

        self.progress = ctk.CTkProgressBar(bottom, height=6, corner_radius=3)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.set(0)
        self.status = ctk.CTkLabel(
            bottom, text="готово к запуску", font=font(12), text_color=MUTED,
            anchor="w",
        )
        self.status.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self._update_chips()
        return page

    LOADER_KEYS = {
        "Fabric": "fabric",
        "Forge": "forge",
        "NeoForge": "neoforge",
        "Quilt": "quilt",
    }

    CONTENT_TYPES = [
        ("Моды", "mod", True, "mods"),
        ("Плагины", "plugin", True, "plugins"),
        ("Ресурспаки", "resourcepack", False, "rpacks"),
        ("Шейдеры", "shader", False, "shaders"),
        ("Датапаки", "datapack", False, "datapacks"),
    ]
    _DEST = {
        "mods": config.MODS_DIR,
        "plugins": config.PLUGINS_DIR,
        "rpacks": config.RPACKS_DIR,
        "shaders": config.SHADERS_DIR,
        "datapacks": config.DATAPACKS_DIR,
    }

    def _current_loader_type(self):
        lt = getattr(self, "loader_type", None)
        return lt.get() if lt else "Ваниль"

    def _loader_type_changed(self, choice=None):
        on = choice in self.LOADER_KEYS if choice else (
            self._current_loader_type() in self.LOADER_KEYS
        )
        if on:
            self.loader_box.pack_forget()
            self.loader_box.pack(
                side="right", padx=(0, 10), pady=(0, 2), before=self.loader_type
            )
            if self.loader_box.get() in ("...", "", "загрузка...", "—"):
                self.loader_box.set("загрузка...")
                threading.Thread(target=self._loaders_thread, daemon=True).start()
        else:
            self.loader_box.pack_forget()
        self.settings["loader_type"] = self._current_loader_type()
        self.settings["fabric"] = self.settings["loader_type"] == "Fabric"
        config.save_settings(self.settings)
        self._update_chips()

    def _loaders_thread(self):
        try:
            key = self.LOADER_KEYS.get(self._current_loader_type())
            if key == "fabric":
                vals = fabric.loader_versions()[:12]
            else:
                game = self.settings.get("last_version") or ""
                if not game:
                    raise ValueError("сначала выбери версию Minecraft")
                from launcher import loaders

                vals = loaders.loader_versions(key, game)[:12]
            if not vals:
                raise ValueError(
                    "нет сборок для Minecraft %s — выбери другую версию игры"
                    % (self.settings.get("last_version") or "?")
                )
            self.ui_queue.put(("loaders", vals))
        except Exception as e:
            self.ui_queue.put(("versions_fail", "%s: %s" % (self._current_loader_type(), e)))
            self.ui_queue.put(("loaders", ["—"]))

    def _snap_toggled(self):
        self.settings["snapshots"] = bool(self.snap_var.get())
        config.save_settings(self.settings)
        self._refresh_versions()

    def _update_chips(self):
        self.chip_ram.configure(
            text="ОЗУ: %d ГБ" % int(self.settings.get("ram_gb") or 4)
        )
        acc = accounts.selected()
        if acc:
            mark = {"offline": "офлайн", "microsoft": "Microsoft",
                    "elyby": "Ely.by"}.get(acc.get("type"), acc.get("type"))
            self.chip_acc.configure(text="Аккаунт: %s (%s)" % (acc.get("name", "?"), mark))
        else:
            self.chip_acc.configure(text="Аккаунт: не выбран", text_color="#d8a24a")
        lt = self._current_loader_type()
        if lt in self.LOADER_KEYS:
            self.chip_loader.configure(
                text="Загрузчик: %s %s" % (lt, self.loader_box.get())
            )
        else:
            self.chip_loader.configure(text="Загрузчик: ваниль")

    def _refresh_versions(self):
        snap = bool(self.settings.get("snapshots"))

        def work():
            try:
                ids = versions.list_versions(snapshots=snap)
            except Exception as e:
                ids = []
                self.ui_queue.put(("versions_fail", str(e)))
            else:
                self.ui_queue.put(("versions", ids))

        threading.Thread(target=work, daemon=True).start()

    def _apply_versions(self, ids):
        self.version_box.configure(values=ids)
        last = self.settings.get("last_version")
        if last in ids:
            self.version_box.set(last)
        elif ids:
            self.version_box.set(ids[0])

    # ================= mods page =================

    def _build_mods_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        search_card = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        search_card.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        ctk.CTkLabel(
            search_card, text="MODRINTH · ПОИСК КОНТЕНТА", font=font(13, True),
            text_color=TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(
            search_card,
            text="Моды и плагины требуют загрузчик (Fabric / Forge / NeoForge / Quilt) "
                 "на вкладке «Играть». Ресурспаки, шейдеры и датапаки ставятся на любую версию. "
                 "Зависимости качаются сами.",
            font=font(11.5), text_color=MUTED, justify="left", wraplength=620,
        ).pack(anchor="w", padx=16)
        row = ctk.CTkFrame(search_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 14))
        self.content_box = ctk.CTkComboBox(
            row, values=[t[0] for t in self.CONTENT_TYPES], width=140,
            height=36, corner_radius=10, border_width=0, fg_color="#262d3a",
            button_color=CARD_HOVER, button_hover_color="#323c4c",
            dropdown_fg_color="#262d3a", dropdown_hover_color=CARD_HOVER,
            text_color=TEXT, font=font(13), state="readonly",
        )
        self.content_box.set(self.CONTENT_TYPES[0][0])
        self.content_box.pack(side="left", padx=(0, 10))
        self.mods_query = ctk.CTkEntry(
            row, placeholder_text="Например: sodium, create, iris…", height=38,
            corner_radius=10, fg_color="#262d3a", border_width=0, font=font(14),
        )
        self.mods_query.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            row, text="🔎  Найти", height=38, width=110, corner_radius=10,
            font=font(13), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#0f130e", command=self.on_mod_search,
        ).pack(side="left", padx=(10, 0))

        pack_card = ctk.CTkFrame(page, corner_radius=14, fg_color="#1a241d")
        pack_card.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            pack_card, text="НАШ МОДПАК · 600 МОДОВ", font=font(13, True),
            text_color="#7ee2a0",
        ).pack(anchor="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            pack_card,
            text="SashaLauncher ModPack: топ-600 модов с Modrinth для Minecraft 1.20.1 + Forge. "
                 "Ставится одним нажатием, уже скачанное не перекачивается.",
            font=font(11.5), text_color=MUTED, justify="left", wraplength=620,
        ).pack(anchor="w", padx=16)
        prow = ctk.CTkFrame(pack_card, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(8, 14))
        self.modpack_btn = ctk.CTkButton(
            prow, text="⚙  Установить модпак", height=40, width=220,
            corner_radius=10, font=font(13), fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color="#0f130e",
            command=self.on_modpack_install,
        )
        self.modpack_btn.pack(side="left")
        self.modpack_hint = ctk.CTkLabel(
            prow, text="поставь игру 1.20.1 + Forge, потом жми кнопку",
            font=font(11), text_color="#5f7a68",
        )
        self.modpack_hint.pack(side="left", padx=12)

        self.mod_status = ctk.CTkLabel(
            page, text="", font=font(12), text_color=MUTED, anchor="w", justify="left"
        )
        self.mod_status.grid(row=2, column=0, sticky="ew", padx=20)

        self.mods_results = ctk.CTkFrame(page, fg_color="transparent")
        self.mods_results.grid(row=3, column=0, sticky="ew", padx=18, pady=(6, 18))
        self._mod_rows = []
        self._mod_page = page
        return page

    def _current_content(self):
        name = self.content_box.get() if getattr(self, "content_box", None) else "Моды"
        for t in self.CONTENT_TYPES:
            if t[0] == name:
                return t
        return self.CONTENT_TYPES[0]

    def _apply_mod_icon(self, lbl, path):
        try:
            from PIL import Image

            img = ctk.CTkImage(light_image=Image.open(path),
                               dark_image=Image.open(path), size=(44, 44))
            lbl.configure(image=img, text="")
            lbl._ctk_image = img
        except Exception:
            pass

    def _icon_thread(self, lbl, project_id, icon_url):
        p = modrinth.icon(project_id, icon_url)
        if p:
            try:
                self.after(0, self._apply_mod_icon, lbl, p)
            except Exception:
                pass

    def on_mod_search(self):
        label, ptype, needs_loader, _dest = self._current_content()
        query = self.mods_query.get().strip()
        game = self.settings.get("last_version") or ""
        loader_key = self.LOADER_KEYS.get(self._current_loader_type())
        if needs_loader and not loader_key:
            self.mod_status.configure(
                text="%s требуют загрузчик — выбери Fabric / Forge / NeoForge / Quilt "
                     "на вкладке «Играть»" % label,
                text_color="#d8a24a",
            )
            return
        self.mod_status.configure(text="Ищу по Modrinth...")
        threading.Thread(
            target=self._mods_search_thread,
            args=(query, game, ptype, loader_key if needs_loader else None),
            daemon=True,
        ).start()

    def _mods_search_thread(self, query, game, ptype, loader):
        try:
            hits = modrinth.search(
                query, limit=12, project_type=ptype,
                game_version=game or None, loader=loader,
            )
            self.ui_queue.put(("mod_results", hits))
        except Exception as e:
            self.ui_queue.put(("mods_fail", "Поиск: %s" % e))

    def _render_mod_results(self, hits):
        for w in self.mods_results.winfo_children():
            w.destroy()
        if not hits:
            ctk.CTkLabel(self.mods_results, text="ничего не найдено",
                         font=font(12), text_color=MUTED).pack(anchor="w", padx=4)
            return
        for h in hits:
            row = ctk.CTkFrame(self.mods_results, corner_radius=12, fg_color=CARD)
            row.pack(fill="x", pady=4, padx=2)
            icon_lbl = ctk.CTkLabel(row, text="", width=52)
            icon_lbl.pack(side="left", padx=(12, 0))
            if h.get("icon_url"):
                threading.Thread(
                    target=self._icon_thread,
                    args=(icon_lbl, h["project_id"], h["icon_url"]), daemon=True,
                ).start()
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            ctk.CTkLabel(
                info, text="%s   ·   ⬇ %s" % (h.get("title", "?"),
                                              modrinth.fmt_downloads(h.get("downloads"))),
                font=font(13, True), text_color=TEXT, anchor="w",
            ).pack(anchor="w")
            desc = (h.get("description") or "")[:130]
            ctk.CTkLabel(info, text=desc, font=font(11.5), text_color=MUTED,
                         anchor="w", justify="left", wraplength=500).pack(anchor="w")
            ctk.CTkButton(
                row, text="Скачать", width=100, height=36, corner_radius=9,
                font=font(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                text_color="#0f130e",
                command=lambda p=h["project_id"], t=h.get("title", "контент"):
                    self.on_mod_install(p, t),
            ).pack(side="right", padx=12)

    def on_mod_install(self, project_id, title):
        if self.busy_mod:
            return
        label, ptype, needs_loader, dest = self._current_content()
        game = self.settings.get("last_version") or ""
        loader_key = self.LOADER_KEYS.get(self._current_loader_type())
        if not game and needs_loader:
            self.mod_status.configure(text="Сначала выбери версию на вкладке «Играть»",
                                      text_color="#d8a24a")
            return
        if needs_loader and not loader_key:
            self.mod_status.configure(
                text="Выбери загрузчик (Fabric / Forge / NeoForge / Quilt) на вкладке «Играть»",
                text_color="#d8a24a",
            )
            return
        if not game:
            self.mod_status.configure(text="Сначала выбери версию на вкладке «Играть»",
                                      text_color="#d8a24a")
            return
        self.busy_mod = True
        self.mod_status.configure(text="Скачиваю %s (%s)..." % (title, label),
                                  text_color=MUTED)
        threading.Thread(
            target=self._mod_install_thread,
            args=(project_id, game, loader_key if needs_loader else None,
                  self._DEST[dest], title),
            daemon=True,
        ).start()

    def _mod_install_thread(self, project_id, game, loader, dest, title):
        try:
            names = modrinth.install(project_id, game, loader, dest)
            self.ui_queue.put(("mod_done", (title, names)))
        except Exception as e:
            self.ui_queue.put(("mods_fail", "%s: %s" % (title, e)))

    def on_modpack_install(self):
        if self.busy_mod:
            return
        from launcher import modpack

        try:
            mods = modpack.mods()
        except Exception as e:
            self.mod_status.configure(text="Модпак не найден: %s" % e,
                                      text_color="#d8a24a")
            return
        if not mods:
            self.mod_status.configure(text="Список модов пуст", text_color="#d8a24a")
            return
        self.busy_mod = True
        self.modpack_btn.configure(state="disabled")
        self.mod_status.configure(
            text="Модпак: ставлю %d модов (Minecraft %s + %s)..."
                 % (len(mods), modpack.PACK_MINECRAFT, modpack.PACK_LOADER),
            text_color=MUTED,
        )
        threading.Thread(target=self._modpack_thread, daemon=True).start()

    def _modpack_thread(self):
        from launcher import modpack

        def progress(done, total, slug):
            self.ui_queue.put(("modpack_prog", (done, total, slug)))

        failed = modpack.download_all(progress)
        self.ui_queue.put(("modpack_done", failed))

    # ================= files page =================

    def _build_files_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure((0, 1), weight=1, uniform="f")

        defs = [
            ("mods", "МОДЫ", config.MODS_DIR,
             ".jar файлы модов. Ищи на вкладке «Моды» или кидай вручную — нужен "
             "загрузчик (Fabric / Forge / …) на вкладке «Играть».", (".jar",)),
            ("rpacks", "РЕСУРСПАКИ", config.RPACKS_DIR,
             ".zip файлы. Включаются в игре: Настройки → Наборы ресурсов.", (".zip",)),
            ("shaders", "ШЕЙДЕРЫ", config.SHADERS_DIR,
             ".zip пакеты шейдеров. Нужен мод-шейдерлоадер (Iris / Oculus). "
             "В игре: Настройки → Видео → Шейдеры.", (".zip",)),
            ("datapacks", "ДАТАПАКИ", config.DATAPACKS_DIR,
             ".zip кладутся в папку конкретного мира: saves/<твой мир>/datapacks. "
             "Здесь — общая папка; Modrinth-поиск ставит сюда.", (".zip",)),
            ("plugins", "ПЛАГИНЫ", config.PLUGINS_DIR,
             ".jar плагины для серверов (Paper / Spigot). Для обычной игры не нужны.", (".jar",)),
        ]
        self.file_cards = {}
        for i, (key, title, folder, hint, ext) in enumerate(defs):
            card = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
            card.grid(row=i // 2, column=i % 2, sticky="nsew",
                      padx=(18 if i % 2 == 0 else 6, 6 if i % 2 == 0 else 18),
                      pady=(14 if i < 2 else 8, 0))
            ctk.CTkLabel(card, text=title, font=font(13, True), text_color=TEXT).pack(
                anchor="w", padx=16, pady=(14, 0)
            )
            ctk.CTkLabel(card, text=hint, font=font(11.5), text_color=MUTED,
                         justify="left", wraplength=340).pack(anchor="w", padx=16)
            count_label = ctk.CTkLabel(
                card, text="", font=font(12), text_color=TEXT, anchor="w",
                justify="left",
            )
            count_label.pack(anchor="w", padx=16, pady=(6, 0), fill="x")
            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(fill="x", padx=16, pady=(8, 14))
            ctk.CTkButton(
                btns, text="Открыть папку", height=34, corner_radius=9,
                font=font(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                text_color="#0f130e",
                command=lambda d=folder: self._open_folder(d),
            ).pack(side="left")
            ctk.CTkButton(
                btns, text="Обновить", height=34, width=100, corner_radius=9,
                font=font(12), fg_color=CARD_HOVER, hover_color="#323c4c",
                command=lambda k=key: self.refresh_files(),
            ).pack(side="left", padx=8)
            self.file_cards[key] = (folder, count_label, ext)
        self.refresh_files()
        return page

    def refresh_files(self):
        import os as _os

        for key, (folder, label, ext) in getattr(self, "file_cards", {}).items():
            try:
                names = sorted(
                    f for f in _os.listdir(folder)
                    if f.lower().endswith(ext) and not f.startswith(".")
                )
            except OSError:
                names = []
            if names:
                label.configure(
                    text="%d файл(ов):\n · %s"
                    % (len(names), "\n · ".join(names[:12]))
                    + ("\n …" if len(names) > 12 else "")
                )
            else:
                label.configure(
                    text="пусто (или расширения не .%s)" % "/.".join(e[1:] for e in ext)
                )

    # ================= account page =================

    def _build_account_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")

        cards = []
        # offline card
        c1 = self._card2(page, "ОФФЛАЙН", "Пиратский вход — просто имя")
        e = ctk.CTkEntry(
            c1, placeholder_text="Имя игрока", height=38, corner_radius=10,
            fg_color="#262d3a", border_width=0, font=font(14),
        )
        e.pack(fill="x", padx=16, pady=(10, 8))
        self.off_name = e
        self._btn(
            c1, "Войти офлайн", self.on_offline_login
        ).pack(fill="x", padx=16, pady=(0, 16))
        cards.append(c1)

        # microsoft card
        c2 = self._card2(page, "MICROSOFT", "Лицензия, вход по коду с сайта")
        ctk.CTkLabel(
            c2, text=(
                "Нужен Azure client_id — вкладка\n«Настройки». Лаунчер даст код,\n"
                "введи его на microsoft.com/link"
            ), font=font(11.5), text_color=MUTED, justify="left",
        ).pack(anchor="w", padx=16)
        self.ms_status = ctk.CTkLabel(c2, text="", font=font(11.5),
                                      text_color="#7fc7ff", justify="left",
                                      wraplength=230)
        self.ms_status.pack(anchor="w", padx=16, pady=(6, 0))
        self._btn(
            c2, "Войти через Microsoft", self.on_ms_login
        ).pack(fill="x", padx=16, pady=(10, 16))
        cards.append(c2)

        # ely.by card
        c3 = self._card2(page, "ELY.BY", "Своя авторизация, скины и плащи")
        ee = ctk.CTkEntry(
            c3, placeholder_text="email", height=36, corner_radius=10,
            fg_color="#262d3a", border_width=0, font=font(13),
        )
        ee.pack(fill="x", padx=16, pady=(10, 6))
        ep = ctk.CTkEntry(
            c3, placeholder_text="пароль", show="•", height=36, corner_radius=10,
            fg_color="#262d3a", border_width=0, font=font(13),
        )
        ep.pack(fill="x", padx=16, pady=(0, 8))
        self.ely_email = ee
        self.ely_pass = ep
        self._btn(
            c3, "Войти через Ely.by", self.on_ely_login
        ).pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkButton(
            c3, text="регистрация на ely.by →", height=28,
            fg_color="transparent", hover_color=CARD_HOVER,
            text_color=MUTED, font=font(11),
            command=lambda: webbrowser.open("https://ely.by"),
        ).pack(fill="x", padx=16, pady=(0, 12))
        cards.append(c3)

        for i, card in enumerate(cards):
            card.grid(row=0, column=i, sticky="nsew", padx=(18 if i == 0 else 6, 6 if i < 2 else 18), pady=(14, 10))

        saved = self._card2(page, "СОХРАНЁННЫЕ АККАУНТЫ", "")
        saved.grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=(4, 18))
        self.acc_rows = ctk.CTkFrame(saved, fg_color="transparent")
        self.acc_rows.pack(fill="x", padx=16, pady=(4, 14))
        self._render_accounts()
        return page

    @staticmethod
    def _card2(parent, title, subtitle):
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD)
        ctk.CTkLabel(card, text=title, font=font(13, True), text_color=TEXT).pack(
            anchor="w", padx=16, pady=(14, 0)
        )
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=font(11.5), text_color=MUTED).pack(
                anchor="w", padx=16
            )
        return card

    @staticmethod
    def _btn(parent, text, cmd):
        return ctk.CTkButton(
            parent, text=text, height=40, corner_radius=10, font=font(13),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#0f130e",
            command=cmd,
        )

    def _render_accounts(self):
        for w in self.acc_rows.winfo_children():
            w.destroy()
        accs = accounts.all_accounts()
        if not accs:
            ctk.CTkLabel(
                self.acc_rows, text="пока пусто — войди любым способом выше",
                font=font(12), text_color=MUTED,
            ).pack(anchor="w", pady=6)
            return
        for acc in accs:
            row = ctk.CTkFrame(self.acc_rows, corner_radius=10, fg_color="#262d3a")
            row.pack(fill="x", pady=3)
            icon = {"offline": "○", "microsoft": "●", "elyby": "e"}.get(
                acc.get("type"), "?"
            )
            mark = {"offline": "офлайн", "microsoft": "Microsoft",
                    "elyby": "Ely.by"}.get(acc.get("type"), "?")
            label = "%s  %s   ·   %s" % (icon, acc.get("name", "?"), mark)
            ctk.CTkButton(
                row, text=label, anchor="w", fg_color="transparent",
                hover_color=CARD_HOVER, font=font(13),
                command=lambda a=acc: self._pick_account(a),
            ).pack(side="left", fill="x", expand=True, padx=4, pady=4)
            ctk.CTkButton(
                row, text="✕", width=36, height=32, corner_radius=8,
                fg_color="transparent", hover_color=DANGER_HOVER,
                text_color=DANGER, font=font(13),
                command=lambda a=acc: self._remove_account(a),
            ).pack(side="right", padx=6, pady=4)

    def _pick_account(self, acc):
        accounts.select(accounts.key_hint(acc))
        self._refresh_account_header()

    def _remove_account(self, acc):
        accounts.remove(accounts.key_hint(acc))
        self._refresh_account_header()

    def _refresh_account_header(self):
        acc = accounts.selected()
        if acc:
            icon = {"offline": "○", "microsoft": "●", "elyby": "e"}.get(
                acc.get("type"), "?"
            )
            self.chip_label.configure(
                text="%s  %s" % (icon, acc.get("name", "?")),
                text_color=TEXT,
            )
        else:
            self.chip_label.configure(
                text="нет аккаунта — вкладка «Аккаунт»", text_color="#d8a24a"
            )
        self._render_accounts()
        self._update_chips()

    def _finish_login(self, acc):
        accounts.upsert(acc)
        self._refresh_account_header()
        self.show_page("Играть")

    def on_offline_login(self):
        try:
            acc = offline.offline_account(self.off_name.get())
        except ValueError as e:
            self.set_status(str(e))
            self.log_line("[вход] %s" % e)
            return
        self._finish_login(acc)
        self.set_status("Вход: %s (офлайн)" % acc["name"])

    def on_ms_login(self):
        if self.busy:
            return
        client_id = self.settings.get("azure_client_id", "")
        self.busy = True
        self.ms_status.configure(text="Соединяюсь с Microsoft...")

        def work():
            try:
                acc = microsoft.full_login(
                    client_id, progress=lambda m: self.ui_queue.put(("ms", m))
                )
                self.ui_queue.put(("login_done", acc))
            except Exception as e:
                self.ui_queue.put(("login_fail", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def on_ely_login(self):
        email = self.ely_email.get()
        password = self.ely_pass.get()
        self.set_status("Ely.by: проверяю...")

        def work():
            try:
                acc = elyby.authenticate(email, password)
                self.ui_queue.put(("login_done", acc))
            except Exception as e:
                self.ui_queue.put(("login_fail", "Ely.by: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    # ================= settings page =================

    def _build_settings_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        c1 = self._build_settings_card(
            page, "ПАМЯТЬ",
            "Сколько ОЗУ отдать игре (лучше 4–8 ГБ для новых версий)",
        )
        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(6, 16))
        self.ram_var = ctk.DoubleVar(value=float(self.settings.get("ram_gb") or 4))
        self.ram_slider = ctk.CTkSlider(
            row, from_=1, to=32, variable=self.ram_var,
            button_color=ACCENT, progress_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER, height=22,
        )
        self.ram_slider.pack(side="left", fill="x", expand=True, pady=8)
        self.ram_label = ctk.CTkLabel(row, text="%d ГБ" % int(self.ram_var.get()),
                                      font=font(14), text_color=TEXT, width=70)
        self.ram_label.pack(side="right", padx=(14, 0))
        self.ram_slider.configure(
            command=lambda v: self.ram_label.configure(text="%d ГБ" % int(v))
        )
        c1.pack(fill="x", padx=18, pady=(14, 10))

        c4 = self._build_settings_card(
            page, "СКАЧИВАНИЕ ЧЕРЕЗ ЗЕРКАЛО",
            "Если файлы Minecraft качаются с ошибками сети — включай: "
            "лаунчер будет пробовать зеркало bmclapi для серверов Mojang "
            "(манифест, клиент, библиотеки, ресурсы).",
        )
        self.mirror_var = ctk.BooleanVar(
            value=bool(self.settings.get("mirror", True))
        )
        self.doctor_var = ctk.BooleanVar(
            value=bool(self.settings.get("doctor_autofix", True))
        )
        ctk.CTkCheckBox(
            c4, text="использовать зеркало", variable=self.mirror_var,
            font=font(12), text_color=MUTED, fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        ).pack(anchor="w", padx=16, pady=(6, 4))
        ctk.CTkCheckBox(
            c4, text="Лекарь сам удаляет проблемные моды", variable=self.doctor_var,
            font=font(12), text_color=MUTED, fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        ).pack(anchor="w", padx=16, pady=(4, 14))
        c4.pack(fill="x", padx=18, pady=10)

        c2 = self._build_settings_card(
            page, "JAVA",
            "Путь к java.exe (пусто — найти автоматически). Нужна Java 17+ для версий 1.17+ (adoptium.net)",
        )
        self.java_entry = ctk.CTkEntry(
            c2, height=38, corner_radius=10, fg_color="#262d3a", border_width=0,
            font=font(13),
        )
        self.java_entry.insert(0, self.settings.get("java_path", ""))
        self.java_entry.pack(fill="x", padx=16, pady=(8, 16))
        c2.pack(fill="x", padx=18, pady=10)

        c3 = self._build_settings_card(
            page, "AZURE CLIENT_ID (для входа Microsoft)",
            "portal.azure.com → Microsoft Entra ID → Регистрация приложений → Новая регистрация "
            "(все типы аккаунтов). Redirect URI: "
            "https://login.microsoftonline.com/common/oauth2/nativeclient. "
            "Скопируй «Application (client) ID»."
        )
        self.client_entry = ctk.CTkEntry(
            c3, height=38, corner_radius=10, fg_color="#262d3a", border_width=0,
            font=font(13),
        )
        self.client_entry.insert(0, self.settings.get("azure_client_id", ""))
        self.client_entry.pack(fill="x", padx=16, pady=(8, 6))
        ctk.CTkButton(
            c3, text="открыть portal.azure.com →", height=30,
            fg_color="transparent", hover_color=CARD_HOVER, text_color=MUTED,
            font=font(11),
            command=lambda: webbrowser.open("https://portal.azure.com"),
        ).pack(anchor="w", padx=16, pady=(0, 16))
        c3.pack(fill="x", padx=18, pady=10)

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(14, 18))
        self._btn(actions, "Сохранить настройки", self.on_save_settings).pack(
            side="left"
        )
        self._btn(actions, "Проверить обновления", lambda: self._auto_update(True)).pack(
            side="left", padx=10
        )
        ctk.CTkButton(
            actions, text="Открыть папку игры", height=40, corner_radius=10,
            font=font(13), fg_color=CARD_HOVER, hover_color="#323c4c",
            command=lambda: self._open_folder(config.GAME_DIR),
        ).pack(side="left", padx=10)
        return page

    @staticmethod
    def _build_settings_card(parent, title, hint):
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD)
        ctk.CTkLabel(card, text=title, font=font(13, True), text_color=TEXT).pack(
            anchor="w", padx=16, pady=(14, 0)
        )
        ctk.CTkLabel(
            card, text=hint, font=font(11.5), text_color=MUTED, justify="left",
            wraplength=620,
        ).pack(anchor="w", padx=16)
        return card

    def on_save_settings(self):
        self.settings["ram_gb"] = max(1, int(self.ram_var.get()))
        self.settings["java_path"] = self.java_entry.get().strip()
        self.settings["azure_client_id"] = self.client_entry.get().strip()
        self.settings["mirror"] = bool(self.mirror_var.get())
        self.settings["doctor_autofix"] = bool(self.doctor_var.get())
        from launcher import http_util as _http

        _http.use_mirror = self.settings["mirror"]
        config.save_settings(self.settings)
        self._update_chips()
        self.set_status("Настройки сохранены ✓")

    @staticmethod
    def _open_folder(path):
        import os
        import subprocess

        os.makedirs(path, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(path)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError:
            pass

    # ================= console page =================

    def _build_console_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        ctk.CTkLabel(bar, text="КОНСОЛЬ", font=font(13, True), text_color=TEXT).pack(
            side="left"
        )
        ctk.CTkButton(
            bar, text="Очистить", height=28, width=90, corner_radius=8,
            fg_color=CARD_HOVER, hover_color="#323c4c", font=font(11),
            command=lambda: self.log.delete("1.0", "end"),
        ).pack(side="right")

        self.log = ctk.CTkTextbox(
            page, font=("Consolas", 12), fg_color=PANEL, corner_radius=12,
            border_width=0, text_color="#c7d0db",
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        return page

    def log_line(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    # ================= play flow =================

    def on_play(self):
        if self.busy:
            return
        acc = accounts.selected()
        if not acc:
            self.set_status("Сначала добавь аккаунт — раздел «Аккаунт»")
            self.show_page("Консоль")
            self.log_line("[ошибка] нет аккаунта — открой «Аккаунт» и войди")
            return
        version_id = self.version_box.get().strip()
        if not version_id or version_id == "загрузка...":
            self.set_status("Версии ещё загружаются, секунду")
            return
        use_loader = self.LOADER_KEYS.get(self._current_loader_type())
        loader = self.loader_box.get()
        self.busy = True
        self.play_btn.configure(state="disabled", text="ЗАПУСК...")
        self.settings["last_version"] = version_id
        self.settings["loader_type"] = self._current_loader_type()
        self.settings["fabric"] = use_loader == "fabric"
        self.settings["loader"] = loader
        config.save_settings(self.settings)
        self.show_page("Консоль")
        self.log_line(
            "=== подготовка %s (%s) ==="
            % (version_id, self._current_loader_type() + " " + loader if use_loader else "ваниль")
        )

        def work():
            try:
                if use_loader:
                    if loader in ("...", "загрузка...", "—", ""):
                        raise ValueError(
                            "Выбери версию загрузчика %s рядом с выбором типа"
                            % self._current_loader_type()
                        )
                    game = self.settings["last_version"]
                    try:
                        if use_loader == "fabric":
                            version_id = fabric.profile(game, loader)["id"]
                        else:
                            from launcher import loaders

                            version_id = loaders.version_id(use_loader, loader, game)
                            loaders.patch(use_loader, loader, game)
                    except Exception:
                        raise ValueError(
                            "%s не доступен для версии %s — попробуй другую версию"
                            % (self._current_loader_type(), game)
                        ) from None
                    self.ui_queue.put(("prog", ("Лоадер", 0, 1, version_id)))
                active = self._ensure_token(acc)
                meta = installer.install_version(
                    version_id,
                    progress=lambda s, d, t, lbl: self.ui_queue.put(
                        ("prog", (s, d, t, lbl))
                    ),
                )
                findings = doctor.scan(
                    config.MODS_DIR,
                    self.settings.get("last_version") or "",
                    use_loader or "vanilla",
                )
                if findings and self.settings.get("doctor_autofix", True):
                    self.ui_queue.put(("doctor_fixing", len(findings)))
                    fixed, findings = doctor.autofix(
                        config.MODS_DIR,
                        self.settings.get("last_version") or "",
                        use_loader or "vanilla",
                    )
                    self.ui_queue.put(("doctor_fixed", fixed))
                    if findings:
                        _dep, _fail, findings = doctor.install_missing(
                            config.MODS_DIR,
                            self.settings.get("last_version") or "",
                            use_loader or "vanilla",
                            log=lambda m: self.ui_queue.put(("doctor_dep", m)),
                        )
                        self.ui_queue.put(("doctor_dep_fail", _fail))
                if findings:
                    self._doctor_answer = False
                    self._doctor_evt.clear()
                    self.ui_queue.put(("doctor", findings))
                    if not self._doctor_evt.wait(900):
                        raise ValueError("запуск отменён — жми «Играть» ещё раз")
                    if not self._doctor_answer:
                        raise ValueError(
                            "запуск отменён — исправь проблемы из «Лекаря» и жми «Играть» снова"
                        )
                _req = runner.required_java_major(meta)
                try:
                    _jpath = runner.find_java(
                        self.settings.get("java_path", ""), _req
                    )
                    _jmajor = runner.java_major(_jpath)
                except runner.JavaNotFound:
                    _jpath, _jmajor = "", 0
                if _jmajor < _req and self.settings.get("auto_java", True):
                    try:
                        _jpath = runner.ensure_java(
                            _req,
                            log=lambda m: self.ui_queue.put(
                                ("doctor_dep", "[java] " + m)
                            ),
                        )
                        _jmajor = runner.java_major(_jpath)
                    except Exception as _je:
                        self.ui_queue.put(
                            ("doctor_dep", "[java] не смог скачать: %s" % _je)
                        )
                        _jpath, _jmajor = "", 0
                if _jmajor < _req:
                    raise ValueError(
                        "Для этой версии нужна Java %d+, а найдена Java %s (%s). "
                        "Установи Temurin %d с adoptium.net и укажи путь к java.exe "
                        "в Настройках (или оставь поле пустым — лаунчер сам найдёт)."
                        % (_req, _jmajor or "?", _jpath or "не найдена", _req)
                    )
                self.ui_queue.put(("launching", version_id))
                self.proc = runner.launch(
                    meta, active, self.settings,
                    on_stdout=lambda line: self.ui_queue.put(("game", line)),
                )
                self.ui_queue.put(("game_started", version_id))
            except Exception as e:
                self.ui_queue.put(("game_fail", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _ensure_token(self, acc):
        import time as _time

        if acc.get("type") == "microsoft" and (
            not acc.get("expires_at") or acc["expires_at"] < _time.time() + 120
        ):
            self.ui_queue.put(("ms", "Обновляю Microsoft-токен..."))
            acc2 = microsoft.refresh(acc, self.settings.get("azure_client_id", ""))
            accounts.upsert(acc2)
            self.ui_queue.put(("header", None))
            return acc2
        if acc.get("type") == "elyby" and not elyby.validate(acc.get("token", "")):
            self.ui_queue.put(("ms", "Обновляю Ely.by-токен..."))
            acc2 = elyby.refresh(acc)
            accounts.upsert(acc2)
            self.ui_queue.put(("header", None))
            return acc2
        return acc

    # ================= queue / status =================

    def set_status(self, text):
        self.status.configure(text=text)

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "versions":
                    self._apply_versions(payload)
                elif kind == "loaders":
                    self.loader_box.configure(values=payload)
                    last = self.settings.get("loader")
                    self.loader_box.set(last if last in payload else payload[0])
                elif kind == "mod_results":
                    self.mod_status.configure(
                        text="Нашёл %d позиций — жми «Скачать»" % len(payload)
                    )
                    self._render_mod_results(payload)
                elif kind == "modpack_prog":
                    done, total, slug = payload
                    self.mod_status.configure(
                        text="Модпак: %d из %d · %s" % (done, total, slug)
                    )
                elif kind == "modpack_done":
                    self.busy_mod = False
                    failed = payload
                    self.modpack_btn.configure(state="normal")
                    if failed:
                        self.mod_status.configure(
                            text="Модпак: готово, но не удалось: %s"
                            % (", ".join(failed[:6]) + ("…" if len(failed) > 6 else "")),
                            text_color="#d8a24a",
                        )
                    else:
                        self.mod_status.configure(
                            text="✔ Модпак установлен полностью!",
                            text_color="#7ee2a0",
                        )
                    self.refresh_files()
                elif kind == "mod_done":
                    title, names = payload
                    self.busy_mod = False
                    self.mod_status.configure(
                        text="✔ %s установлен: %s"
                        % (title, ", ".join(names) if names else "?")
                    )
                    self.refresh_files()
                elif kind == "mods_fail":
                    self.busy_mod = False
                    self.mod_status.configure(text=str(payload), text_color="#d8a24a")
                    if getattr(self, "modpack_btn", None):
                        self.modpack_btn.configure(state="normal")
                elif kind == "versions_fail":
                    self.set_status("Сеть: не получил список версий (%s)" % payload[:80])
                elif kind == "prog":
                    stage, done, total, label = payload
                    if total:
                        self.progress.set(min(1.0, done / total))
                        self.set_status("%s · %s (%d из %d)" % (stage, label, done, total))
                elif kind == "ms":
                    self.ms_status.configure(text=payload)
                elif kind == "header":
                    self._refresh_account_header()
                elif kind == "launching":
                    self.set_status("Запускаю %s..." % payload)
                elif kind == "game_started":
                    self.log_line("=== игра %s запущена (PID %s) ===" % (payload, self.proc.pid))
                    self.set_status("Игра запущена ✓ (лог в консоли)")
                    self._play_done()
                elif kind == "login_done":
                    self.busy = False
                    self._finish_login(payload)
                    self.set_status("Вход: %s" % payload.get("name", ""))
                elif kind == "login_fail":
                    self.busy = False
                    self.set_status("Ошибка входа: %s" % payload)
                    self.log_line("[ошибка входа] %s" % payload)
                    self.show_page("Аккаунт")
                elif kind == "game_fail":
                    self.log_line("[ошибка] %s" % payload)
                    self.set_status("Ошибка: %s" % payload)
                    self._play_done()
                elif kind == "game":
                    self.log_line(payload)
                elif kind == "doctor":
                    self._show_doctor(payload)
                elif kind == "doctor_fixing":
                    self.set_status("Лекарь: нашёл %d проблем — сам убираю…" % payload)
                    self.log_line("[лекарь] нашёл %d проблем — чиню автоматически" % payload)
                elif kind == "doctor_fixed":
                    for fn, lvl in payload:
                        self.log_line("[лекарь] убрал %s (%s) → trash" % (fn, lvl))
                    if payload:
                        self.set_status("Лекарь починил %d файлов ✓" % len(payload))
                elif kind == "doctor_dep":
                    self.log_line("[лекарь] %s" % payload)
                elif kind == "doctor_dep_fail":
                    for name, why in payload:
                        self.log_line("[лекарь] не смог поставить %s: %s" % (name, why))
                    if payload:
                        self.set_status("Лекарь: не смог поставить %d зав. — смотри консоль" % len(payload))
                elif kind == "update_status":
                    self.log_line("[обновление] %s" % payload)
                    self.set_status(str(payload))
                elif kind == "update_done":
                    self.log_line("[обновление] готово — перезапускаю лаунчер")
                    self.set_status("Обновление установлено ✓")
                    try:
                        app_path = updater.app_dir()
                        subprocess.Popen(
                            [sys.executable, os.path.join(app_path, "main.py")],
                            cwd=app_path,
                        )
                    except Exception as e:
                        self.log_line("[обновление] перезапусти вручную: %s" % e)
                    self.after(1200, self.destroy)
        except queue.Empty:
            pass
        self.after(250, self._drain_queue)

    # ================= лекарь (проверка перед запуском) =================

    def _doctor_decide(self, ok):
        self._doctor_answer = bool(ok)
        self._doctor_evt.set()

    def _doctor_fix_and_run(self):
        if getattr(self, "_doctor_win", None) is not None:
            try:
                self._doctor_win.destroy()
            except Exception:
                pass
        self.set_status("Лекарь чинит файлы…")
        threading.Thread(target=self._doctor_fix_thread, daemon=True).start()

    def _doctor_loader(self):
        return (
            self.LOADER_KEYS.get(self.settings.get("loader_type") or "")
            or "vanilla"
        )

    def _doctor_fix_thread(self):
        gv = self.settings.get("last_version") or ""
        ld = self._doctor_loader()
        try:
            self.set_status("Лекарь: ставлю недостающие зависимости с Modrinth…")
            fixed, findings = doctor.autofix(config.MODS_DIR, gv, ld)
            self.ui_queue.put(("doctor_fixed", fixed))
            attempted = set()
            fresh = set()
            for _ in range(3):
                missing_ids = set()
                for f in findings:
                    mt = f.get("missing")
                    mt = [mt] if isinstance(mt, str) else (mt or [])
                    for t in mt:
                        if t.lower() not in attempted:
                            missing_ids.add(t)
                if not missing_ids:
                    break
                _deps, _fail, findings = doctor.install_missing(
                    config.MODS_DIR, gv, ld, skip=attempted,
                    log=lambda m: self.ui_queue.put(("doctor_dep", m)),
                )
                attempted |= missing_ids
                attempted |= {t for t, _w in _fail}
                for _t, names in _deps:
                    fresh |= set(names)
                self.ui_queue.put(("doctor_dep_fail", _fail))
                if _fail:
                    fixed2, findings = doctor.purge_failed(
                        config.MODS_DIR, gv, ld, [t for t, _w in _fail],
                        fresh=fresh,
                    )
                    self.ui_queue.put(("doctor_fixed", fixed2))
            if findings:
                self.ui_queue.put(("doctor", findings))
                return
            self.set_status("Лекарь: всё починил — запускаю ✓")
            self._doctor_decide(True)
        except Exception as e:
            self.log_line("[лекарь] не смог починить сам: %s" % e)
            self._doctor_decide(False)

    def _show_doctor(self, findings):
        errs = sum(1 for f in findings if f.get("level") == "error")
        warns = len(findings) - errs
        self.set_status(
            "Лекарь: %d ошибок, %d предупреждений — смотри список" % (errs, warns)
        )
        for f in findings:
            tag = "ОШИБКА" if f.get("level") == "error" else "предупреждение"
            self.log_line("[лекарь][%s] %s" % (tag, f["text"]))
        top = ctk.CTkToplevel(self)
        self._doctor_win = top
        top.title("Лекарь — проверка перед запуском")
        top.geometry("660x560")
        head = "Лекарь нашёл проблемы перед запуском"
        if errs:
            head += "\nСоветую исправить ошибки — они почти наверняка уронят игру"
        else:
            head += "\nКритичных ошибок нет, только предупреждения"
        ctk.CTkLabel(
            top,
            text=head,
            font=font(20, True),
            justify="center",
        ).pack(pady=(18, 8), padx=20)
        box = ctk.CTkScrollableFrame(top, fg_color="#1a1214")
        box.pack(fill="both", expand=True, padx=16, pady=6)
        for f in findings:
            ctk.CTkLabel(
                box,
                text=("⛔ " if f.get("level") == "error" else "⚠ ") + f["text"],
                justify="left",
                anchor="w",
                wraplength=580,
                text_color=("#ff6b6b" if f.get("level") == "error" else "#ffd75b"),
            ).pack(fill="x", padx=8, pady=4)
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(
            btns,
            text="🛠 Починить и запустить",
            fg_color="#2d5a3a",
            hover_color="#376b46",
            command=self._doctor_fix_and_run,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btns,
            text="▶ Запустить всё равно",
            fg_color="#3a5546",
            hover_color="#376b46",
            command=lambda: self._doctor_decide(True),
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btns,
            text="Отмена",
            fg_color="#5a2d2d",
            hover_color="#6b3737",
            command=lambda: self._doctor_decide(False),
        ).pack(side="left")
        top.protocol("WM_DELETE_WINDOW", lambda: self._doctor_decide(False))

    # ================= self-update =================

    def _auto_update(self, force=False):
        if os.environ.get("SASHALAUNCHER_NO_UPDATER"):
            return
        threading.Thread(
            target=self._update_work, args=(bool(force),), daemon=True
        ).start()

    def _update_work(self, force):
        try:
            local = updater.local_stamp()
            if not local and not force:
                return
            remote = updater.remote_stamp()
            if not remote or (remote == local and not force):
                return
            self.ui_queue.put(("update_status", "Появилась новая версия — обновляю…"))
            updater.install_update()
            self.ui_queue.put(("update_done", None))
        except Exception as e:
            if force:
                self.ui_queue.put(("update_status", "Обновление не удалось: %s" % e))

    def _play_done(self):
        self.busy = False
        self.play_btn.configure(state="normal", text="▶   ИГРАТЬ")

    # ================= lifecycle =================

    def _on_close(self):
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
