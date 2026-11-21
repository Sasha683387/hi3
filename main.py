"""SashaLauncher — GUI (CustomTkinter)."""

import os
import queue
import subprocess
import threading
import webbrowser

import customtkinter as ctk

from launcher import accounts, config, elyby, installer, microsoft, offline, runner, versions

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENTS = "#2f7d4f"
ACCENT_HOVER = "#3f9c64"
STATUS_IDLE = ">_ готово"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        config.ensure_dirs()
        self.settings = config.load_settings()
        self.title("SashaLauncher — Minecraft")
        self.geometry("760x560")
        self.minsize(680, 500)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.proc = None
        self.busy = False
        self.ui_queue = queue.Queue()

        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            header, text="SashaLauncher", font=("Segoe UI", 26, "bold")
        ).pack(side="left")
        self.acc_label = ctk.CTkLabel(header, text="", font=("Segoe UI", 13))
        self.acc_label.pack(side="right")

        self.tabs = ctk.CTabView(
            self, corner_radius=12, segmented_button_selected_color=ACCENTS,
            segmented_button_selected_hover_color=ACCENT_HOVER,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 12))
        self.tab_play = self.tabs.add("Игра")
        self.tab_accounts = self.tabs.add("Аккаунт")
        self.tab_settings = self.tabs.add("Настройки")
        self.tab_log = self.tabs.add("Консоль")

        self._build_play_tab()
        self._build_accounts_tab()
        self._build_settings_tab()
        self._build_log_tab()

        self.after(250, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_account_header()
        self._refresh_versions()

    # ---------- play tab ----------

    def _build_play_tab(self):
        t = self.tab_play
        t.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(t, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        ctk.CTkLabel(row, text="Версия:", font=("Segoe UI", 14)).pack(side="left")
        self.version_box = ctk.CTkComboBox(row, values=["..."], width=260)
        self.version_box.pack(side="left", padx=10)
        self.snap_var = ctk.BooleanVar(value=bool(self.settings.get("snapshots")))
        ctk.CTkCheckBox(
            row, text="снапшоты", variable=self.snap_var, command=self._refresh_versions
        ).pack(side="left")

        self.play_btn = ctk.CTkButton(
            t, text="▶  ИГРАТЬ", height=58, corner_radius=14,
            font=("Segoe UI", 22, "bold"),
            fg_color=ACCENTS, hover_color=ACCENT_HOVER,
            command=self.on_play,
        )
        self.play_btn.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 8))

        self.progress = ctk.CTkProgressBar(t)
        self.progress.grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 0))
        self.progress.set(0)
        self.status = ctk.CTkLabel(
            t, text=STATUS_IDLE, font=("Segoe UI", 13), anchor="w"
        )
        self.status.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 14))

    def _refresh_versions(self):
        self.settings["snapshots"] = bool(self.snap_var.get())
        config.save_settings(self.settings)

        def work():
            ids = versions.list_versions(snapshots=self.settings["snapshots"])
            self.ui_queue.put(("versions", ids))

        threading.Thread(target=work, daemon=True).start()

    def _apply_versions(self, ids):
        self.version_box.configure(values=ids)
        last = self.settings.get("last_version")
        if last in ids:
            self.version_box.set(last)
        elif ids:
            self.version_box.set(ids[0])

    # ---------- accounts tab ----------

    def _build_accounts_tab(self):
        t = self.tab_accounts
        t.grid_columnconfigure(0, weight=1)

        seg = ctk.CTkSegmentedButton(
            t, values=["Офлайн", "Microsoft (лицензия)", "Ely.by"],
            command=self._on_auth_mode, selected_color=ACCENTS,
            selected_hover_color=ACCENT_HOVER,
        )
        seg.set("Офлайн")
        seg.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))

        self.auth_stack = ctk.CTkFrame(t, fg_color="transparent")
        self.auth_stack.grid(row=1, column=0, sticky="ew", padx=18)
        self.auth_stack.grid_columnconfigure(0, weight=1)

        # offline
        f_off = ctk.CTkFrame(self.auth_stack, fg_color="transparent")
        self._grid(f_off, 0)
        ctk.CTkLabel(f_off, text="Имя игрока (пиратский / офлайн вход):").grid(
            row=0, column=0, sticky="w", pady=(6, 2)
        )
        self.off_name = ctk.CTkEntry(
            f_off, placeholder_text="Steve", width=280
        )
        self.off_name.grid(row=1, column=0, sticky="w")
        ctk.CTkButton(f_off, text="Войти офлайн", command=self.on_offline_login).grid(
            row=2, column=0, sticky="w", pady=(10, 2)
        )
        ctk.CTkLabel(
            f_off,
            text="Работает на самых дешёвых серверах и в одиночной игре.",
            text_color="#9aa3ad", justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        # microsoft
        f_ms = ctk.CTkFrame(self.auth_stack, fg_color="transparent")
        self._grid(f_ms, 1)
        ctk.CTkLabel(
            f_ms, justify="left", text=(
                "Вход лицензией Microsoft — Device Code:\n"
                "1. жми Войти, открой ссылку и введи код\n"
                "2. нужен Azure client_id (см. вкладку Настройки)"
            ),
        ).grid(row=0, column=0, sticky="w", pady=(6, 2))
        self.ms_status = ctk.CTkLabel(f_ms, text="", text_color="#8fd0ff", justify="left")
        self.ms_status.grid(row=1, column=0, sticky="w")
        ctk.CTkButton(f_ms, text="Войти через Microsoft", command=self.on_ms_login).grid(
            row=2, column=0, sticky="w", pady=(10, 2)
        )

        # ely.by
        f_ely = ctk.CTkFrame(self.auth_stack, fg_color="transparent")
        self._grid(f_ely, 2)
        ctk.CTkLabel(f_ely, text="Логин (email) и пароль аккаунта Ely.by:").grid(
            row=0, column=0, sticky="w", pady=(6, 2)
        )
        self.ely_email = ctk.CTkEntry(f_ely, placeholder_text="email", width=280)
        self.ely_email.grid(row=1, column=0, sticky="w", pady=(2, 4))
        self.ely_pass = ctk.CTkEntry(f_ely, placeholder_text="пароль", show="•", width=280)
        self.ely_pass.grid(row=2, column=0, sticky="w")
        ctk.CTkButton(f_ely, text="Войти через Ely.by", command=self.on_ely_login).grid(
            row=3, column=0, sticky="w", pady=(10, 2)
        )
        ctk.CTkButton(
            f_ely, text="Нет аккаунта? Регистрация на ely.by", width=220,
            fg_color="transparent", border_width=1, border_color="#5a6673",
            hover_color="#2c3340",
            command=lambda: webbrowser.open("https://ely.by"),
        ).grid(row=4, column=0, sticky="w", pady=(6, 0))

        saved = ctk.CTkFrame(t, fg_color="transparent")
        saved.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 10))
        ctk.CTkLabel(saved, text="Сохранённые аккаунты:", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        self.acc_rows = ctk.CTkFrame(saved, fg_color="transparent")
        self.acc_rows.pack(fill="x")
        self._render_accounts()

    @staticmethod
    def _grid(frame, row):
        frame.grid(row=row, column=0, sticky="ew")

    def _on_auth_mode(self, mode):
        idx = {"Офлайн": 0, "Microsoft (лицензия)": 1, "Ely.by": 2}[mode]
        for i, child in enumerate(self.auth_stack.winfo_children()):
            child.grid_remove()
            if i == idx:
                child.grid()

    def _render_accounts(self):
        for w in self.acc_rows.winfo_children():
            w.destroy()
        for acc in accounts.all_accounts():
            row = ctk.CTkFrame(self.acc_rows, corner_radius=8, fg_color="#242832")
            row.pack(fill="x", pady=3)
            icon = {"offline": "🞄", "microsoft": "✔", "elyby": "E"}.get(
                acc.get("type"), "?"
            )
            label = "%s  %s  (%s)" % (icon, acc.get("name", "?"), acc.get("type", "?"))
            pick = ctk.CTkButton(
                row, text=label, anchor="w", fg_color="transparent",
                hover_color="#2c3340",
                command=lambda a=acc: self._pick_account(a),
            )
            pick.pack(side="left", fill="x", expand=True, padx=4, pady=4)
            ctk.CTkButton(
                row, text="✕", width=34, fg_color="#5c3030",
                hover_color="#7c3d3d",
                command=lambda a=acc: self._remove_account(a),
            ).pack(side="right", padx=6, pady=4)

    def _pick_account(self, acc):
        accounts.select(accounts.key_hint(acc))
        self._refresh_account_header()
        self._render_accounts()

    def _remove_account(self, acc):
        accounts.remove(accounts.key_hint(acc))
        self._refresh_account_header()
        self._render_accounts()

    def _refresh_account_header(self):
        acc = accounts.selected()
        if acc:
            icon = {"offline": "🞄", "microsoft": "✔", "elyby": "E"}.get(
                acc.get("type"), "?"
            )
            self.acc_label.configure(text="%s  %s" % (icon, acc.get("name", "?")))
        else:
            self.acc_label.configure(text="нет аккаунта — вкладка «Аккаунт»")
        self._render_accounts()

    def _finish_login(self, acc):
        accounts.upsert(acc)
        self._refresh_account_header()
        self.tabs.set("Игра")

    def on_offline_login(self):
        try:
            acc = offline.offline_account(self.off_name.get())
            self.set_status("Офлайн: %s" % acc["name"])
            self._finish_login(acc)
        except ValueError as e:
            self.set_status(str(e))

    def on_ms_login(self):
        if self.busy:
            return
        client_id = self.settings.get("azure_client_id", "")
        self.busy = True

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

    # ---------- settings tab ----------

    def _build_settings_tab(self):
        t = self.tab_settings
        t.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(t, text="Память (ГБ):").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 2)
        )
        self.ram_var = ctk.DoubleVar(value=float(self.settings.get("ram_gb") or 4))
        self.ram_label = ctk.CTkLabel(t, text="%d ГБ" % int(self.ram_var.get()))
        self.ram_slider = ctk.CTkSlider(
            t, from_=1, to=16, variable=self.ram_var,
            command=lambda v: self.ram_label.configure(text="%d ГБ" % int(v)),
            button_color=ACCENTS, progress_color=ACCENT_HOVER,
        )
        self.ram_slider.grid(row=1, column=0, sticky="ew", padx=18)
        self.ram_label.grid(row=2, column=0, sticky="e", padx=20)

        ctk.CTkLabel(t, text="Путь к java.exe (пусто — авто):").grid(
            row=3, column=0, sticky="w", padx=18, pady=(14, 2)
        )
        self.java_entry = ctk.CTkEntry(t, width=460)
        self.java_entry.insert(0, self.settings.get("java_path", ""))
        self.java_entry.grid(row=4, column=0, sticky="ew", padx=18)

        ctk.CTkLabel(
            t, justify="left", text=(
                "Azure client_id для Microsoft-входа:\n"
                "1. portal.azure.com → «Регистрация приложений» → Новая регистрация\n"
                "   (Accounts in any organizational directory + Personal Microsoft accounts)\n"
                "2. Redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient\n"
                "3. Скопируй «Application (client) ID» сюда"
            ),
        ).grid(row=5, column=0, sticky="w", padx=18, pady=(14, 2))
        self.client_entry = ctk.CTkEntry(t, width=460)
        self.client_entry.insert(0, self.settings.get("azure_client_id", ""))
        self.client_entry.grid(row=6, column=0, sticky="ew", padx=18)

        ctk.CTkButton(t, text="Сохранить настройки", command=self.on_save_settings).grid(
            row=7, column=0, sticky="w", padx=18, pady=(14, 6)
        )
        ctk.CTkButton(
            t, text="Открыть папку игры", fg_color="#33404f",
            command=lambda: self._open_folder(config.GAME_DIR),
        ).grid(row=8, column=0, sticky="w", padx=18, pady=(4, 0))

    def on_save_settings(self):
        self.settings["ram_gb"] = max(1, int(self.ram_var.get()))
        self.settings["java_path"] = self.java_entry.get().strip()
        self.settings["azure_client_id"] = self.client_entry.get().strip()
        config.save_settings(self.settings)
        self.set_status("Настройки сохранены")

    @staticmethod
    def _open_folder(path):
        os.makedirs(path, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(path)  # noqa: S606
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError:
            pass

    # ---------- log tab ----------

    def _build_log_tab(self):
        t = self.tab_log
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(0, weight=1)
        self.log = ctk.CTkTextbox(t, font=("Consolas", 12))
        self.log.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    def log_line(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    # ---------- play flow ----------

    def on_play(self):
        if self.busy:
            return
        acc = accounts.selected()
        if not acc:
            self.set_status("Сначала добавь аккаунт — вкладка «Аккаунт»")
            return
        version_id = self.version_box.get().strip()
        if not version_id or version_id == "...":
            self.set_status("Версии ещё загружаются, секунду")
            return
        self.busy = True
        self.play_btn.configure(state="disabled", text="ЗАПУСК...")
        self.settings["last_version"] = version_id
        config.save_settings(self.settings)
        self.tabs.set("Консоль")

        def work():
            try:
                acc = self._ensure_token(acc)
                meta = installer.install_version(
                    version_id,
                    progress=lambda s, d, t, lbl: self.ui_queue.put(("prog", (s, d, t, lbl))),
                )
                self.ui_queue.put(("launching", version_id))
                self.proc = runner.launch(
                    meta, acc, self.settings, on_stdout=lambda line: self.ui_queue.put(("game", line))
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
            try:
                acc = microsoft.refresh(acc, self.settings.get("azure_client_id", ""))
            except Exception:
                self.ui_queue.put(("ms", "Microsoft-токен истёк — войди заново (вкладка Аккаунт)"))
                raise
            accounts.upsert(acc)
            self._refresh_account_header()
        if acc.get("type") == "elyby" and not elyby.validate(acc.get("token", "")):
            acc = elyby.refresh(acc)
            accounts.upsert(acc)
            self._refresh_account_header()
        return acc

    # ---------- queue / status ----------

    def set_status(self, text):
        self.status.configure(text=text)

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "versions":
                    self._apply_versions(payload)
                elif kind == "prog":
                    stage, done, total, label = payload
                    if total:
                        self.progress.set(min(1.0, done / total))
                        self.set_status("%s: %s (%d/%d)" % (stage, label, done, total))
                elif kind == "ms":
                    self.ms_status.configure(text=payload)
                elif kind == "launching":
                    self.set_status("Запускаю %s..." % payload)
                elif kind == "game_started":
                    self.log_line("=== Игра %s запущена (PID %s) ===" % (payload, self.proc.pid))
                    self.set_status("Игра запущена!")
                    self._play_done()
                elif kind == "login_done":
                    self.busy = False
                    self._finish_login(payload)
                    self.set_status("Вход: %s" % payload.get("name", ""))
                elif kind == "login_fail":
                    self.busy = False
                    self.set_status(str(payload))
                    self.log_line("[ошибка входа] %s" % payload)
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
        self.play_btn.configure(state="normal", text="▶  ИГРАТЬ")

    # ---------- lifecycle ----------

    def _on_close(self):
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
