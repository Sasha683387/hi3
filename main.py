"""SashaLauncher — GUI (CustomTkinter)."""

import queue
import threading
import webbrowser

import customtkinter as ctk

from launcher import __version__ as APP_VERSION
from launcher import accounts, config, elyby, fabric, installer, microsoft, offline, runner, versions

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
        self.title("SashaLauncher %s" % APP_VERSION)
        self.geometry("940x620")
        self.minsize(820, 540)
        self.configure(fg_color=BGC)

        self.proc = None
        self.busy = False
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
        self._page_files = self._build_files_page()
        self._page_account = self._build_account_page()
        self._page_settings = self._build_settings_page()
        self._page_console = self._build_console_page()
        for name, page in [
            ("Играть", self._page_play),
            ("Файлы", self._page_files),
            ("Аккаунт", self._page_account),
            ("Настройки", self._page_settings),
            ("Консоль", self._page_console),
        ]:
            self.pages[name] = page
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

        self.show_page("Играть")
        if self.fabric_var.get():
            self._fabric_toggled()
        self.after(250, self._drain_queue)
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
            ["Играть", "Файлы", "Аккаунт", "Настройки", "Консоль"], start=1
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
        self.fabric_var = ctk.BooleanVar(
            value=bool(self.settings.get("fabric", False))
        )
        ctk.CTkCheckBox(
            row, text="Fabric (моды)", variable=self.fabric_var,
            command=self._fabric_toggled, font=font(12), text_color=MUTED,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
        ).pack(side="right", pady=(0, 2))
        self.snap_var = ctk.BooleanVar(value=bool(self.settings.get("snapshots")))
        ctk.CTkCheckBox(
            row, text="снапшоты", variable=self.snap_var,
            command=self._snap_toggled, font=font(12), text_color=MUTED,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
        ).pack(side="right", pady=(24, 0))
        self.loader_box = ctk.CTkComboBox(
            row, values=["..."], width=170, height=34, corner_radius=10,
            border_width=0, fg_color="#262d3a", button_color=CARD_HOVER,
            button_hover_color="#323c4c", dropdown_fg_color="#262d3a",
            dropdown_hover_color=CARD_HOVER, text_color=TEXT, font=font(13),
        )
        self.loader_box.pack(side="right", padx=(0, 10), pady=(0, 2))
        self.loader_box.grid_remove()

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

    def _fabric_toggled(self):
        on = bool(self.fabric_var.get())
        if on:
            self.loader_box.grid()
            if self.loader_box.get() in ("...", ""):
                self.loader_box.set("загрузка...")
                threading.Thread(target=self._loaders_thread, daemon=True).start()
        else:
            self.loader_box.grid_remove()
        self.settings["fabric"] = on
        config.save_settings(self.settings)
        self._update_chips()

    def _loaders_thread(self):
        try:
            vals = fabric.loader_versions()[:12]
            self.ui_queue.put(("loaders", vals))
        except Exception as e:
            self.ui_queue.put(("versions_fail", "Fabric: %s" % e))

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
        if getattr(self, "fabric_var", None) and self.fabric_var.get():
            self.chip_loader.configure(
                text="Загрузчик: Fabric %s" % self.loader_box.get()
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

    # ================= files page =================

    def _build_files_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure((0, 1), weight=1, uniform="f")

        defs = [
            ("mods", "МОДЫ", config.MODS_DIR,
             ".jar файлы модов. Нужен Fabric: включи галочку Fabric на вкладке «Играть». "
             "Шейдеры требуют мод Iris (для новых версий).", (".jar",)),
            ("rpacks", "РЕСУРСПАКИ", config.RPACKS_DIR,
             ".zip файлы. Включаются в игре: Настройки → Наборы ресурсов.", (".zip",)),
            ("shaders", "ШЕЙДЕРЫ", config.SHADERS_DIR,
             ".zip пакеты шейдеров. Требуется Fabric + мод Iris: "
             "modrinth.com/mod/iris. В игре: Настройки → Видео → Шейдеры.", (".zip",)),
            ("datapacks", "ДАТАПАКИ", config.SAVES_DIR,
             ".zip кладут в папку конкретного мира: saves/<твой мир>/datapacks. "
             "Кнопка ниже открывает папку миров.", (".zip",)),
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
            row, from_=1, to=16, variable=self.ram_var,
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
        use_fabric = bool(self.fabric_var.get())
        loader = self.loader_box.get()
        self.busy = True
        self.play_btn.configure(state="disabled", text="ЗАПУСК...")
        self.settings["last_version"] = version_id
        self.settings["fabric"] = use_fabric
        self.settings["loader"] = loader
        config.save_settings(self.settings)
        self.show_page("Консоль")
        self.log_line(
            "=== подготовка %s (%s) ==="
            % (version_id, "Fabric " + loader if use_fabric else "ваниль")
        )

        def work():
            try:
                if use_fabric:
                    if loader in ("...", "загрузка...", ""):
                        raise ValueError(
                            "Выбери версию Fabric loader рядом с галочкой Fabric"
                        )
                    version_id = fabric.profile(self.settings["last_version"], loader)["id"]
                    self.ui_queue.put(("prog", ("Fabric", 0, 1, version_id)))
                active = self._ensure_token(acc)
                meta = installer.install_version(
                    version_id,
                    progress=lambda s, d, t, lbl: self.ui_queue.put(
                        ("prog", (s, d, t, lbl))
                    ),
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
        except queue.Empty:
            pass
        self.after(250, self._drain_queue)

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
