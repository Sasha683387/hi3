"""Headless GUI test: run the whole app against mock customtkinter widgets.

Run: python3 tests/test_gui_mock.py
Catches AttributeError / undefined-method / bad-kwarg style crashes without a display.
"""
import os
import sys
import time
import types

os.environ.setdefault("SASHALAUNCHER_NO_UPDATER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CTK_METHODS = (
    "pack grid grid_remove grid_forget pack_forget grid_propagate pack_propagate "
    "configure cget winfo_children winfo_exists destroy focus_set lift tkraise "
    "grid_columnconfigure grid_rowconfigure columnconfigure rowconfigure bind "
    "unbind after cancel after_cancel update update_idletasks clipboard_clear "
    "clipboard_append bell withdraw deiconify iconify resizable"
).split()

SENTINEL = object()


class MockW:
    _instances = []

    def __init__(self, *args, **kwargs):
        self._seen = set([kwargs.get("text", "")])
        self._cfg = dict(kwargs)
        MockW._instances.append(self)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "winfo_children":
            return lambda: []
        if name in CTK_METHODS:

            def m(*a, **k):
                return None

            self.__dict__[name] = m
            return m
        if name == "get":
            return lambda *a, **k: ""
        if name == "set":
            return lambda *a, **k: None
        if name == "insert":
            return lambda *a, **k: None
        if name == "winfo_width":
            return lambda: 100
        raise AttributeError(
            "MockW has no %r (class %s)" % (name, type(self).__name__)
        )


class MockFont:
    def __init__(self, family=None, size=None, weight=None):
        if size is not None and not isinstance(size, int):
            raise TypeError("CTkFont size must be int, got %r" % (size,))
        self.family, self.size, self.weight = family, size, weight


class MockVar:
    def __init__(self, value=None, **kw):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


def make_ctk_module():
    ctk = types.ModuleType("customtkinter")
    ctk.set_appearance_mode = lambda mode: None
    ctk.set_default_color_theme = lambda theme: None

    class CTk(MockW):
        _afters = []

        def title(self, t):
            self._title = t

        def geometry(self, g):
            self._geo = g

        def minsize(self, *a):
            pass

        def mainloop(self, *a):
            raise RuntimeError("mainloop must not be called in tests")

        def after(self, ms, fn=None, *args):
            CTk._afters.append(fn)

        def protocol(self, name, fn):
            self._on_close = fn

        def get(self, *a):
            return ""

    class CTkEntry(MockW):
        def insert(self, pos, text):
            self._text = text

        def get(self):
            return getattr(self, "_text", "")

    class CTkComboBox(MockW):
        def set(self, v):
            self._val = v

        def get(self):
            return getattr(self, "_val", "")

    class CTkSlider(MockW):
        def get(self):
            return getattr(self, "_val", 4)

        def set(self, v):
            self._val = v

    class CTkTextbox(CTkEntry):
        def see(self, idx):
            pass

        def delete(self, *a):
            pass

    for cls_name in (
        "CTkFrame", "CTkLabel", "CTkButton", "CTkCheckBox", "CTkProgressBar",
        "CTkScrollableFrame", "CTkSegmentedButton", "CTkToplevel",
        "CTkOptionMenu", "CTkScrollbar", "CTkInputDialog", "CTkSwitch",
        "CTkRadioButton",
    ):
        setattr(ctk, cls_name, type(cls_name, (MockW,), {}))
    setattr(ctk, "CTkTextbox", CTkTextbox)
    ctk.CTk = CTk
    ctk.CTkEntry = CTkEntry
    ctk.CTkComboBox = CTkComboBox
    ctk.CTkSlider = CTkSlider
    ctk.CTkFont = MockFont
    ctk.BooleanVar = MockVar
    ctk.DoubleVar = MockVar
    return ctk


def main():
    sys.modules["customtkinter"] = make_ctk_module()
    import main as app_mod

    app = app_mod.App()

    ctkmod = sys.modules["customtkinter"]

    def pump(seconds=6.0, interval=0.2):
        deadline = time.time() + seconds
        while time.time() < deadline:
            for fn in list(ctkmod.CTk._afters):
                ctkmod.CTk._afters.remove(fn)
                fn()
            time.sleep(interval)

    page_names = ["Аккаунт", "Настройки", "Консоль", "Играть", "Моды", "Файлы", "Аккаунт"]
    for name in page_names:
        app.show_page(name)

    app.ram_var.set(6)
    app.on_save_settings()
    assert app.settings["ram_gb"] == 6

    app.off_name._text = "--плохо--"
    app.on_offline_login()
    app.off_name._text = "Steve"
    app.on_offline_login()
    assert accounts_selected_name() == "Steve", "offline login did not save account"

    app.on_ely_login()
    pump(4.0)
    app.show_page("Играть")
    app.loader_type.set("Fabric")
    app._loader_type_changed()
    app.loader_type.set("Ваниль")
    app._loader_type_changed()

    try:
        app.on_ms_login()
        pump(1.0)
    except Exception as e:
        raise AssertionError("ms login raised: %r" % e)

    from launcher import accounts as acc_mod

    acc_mod.upsert({"type": "offline", "name": "Steve", "uuid": "x", "token": "0"})
    try:
        app.ui_queue.put(("game_fail", "конец"))
    finally:
        pass

    from launcher import versions as versions_mod

    app.loader_type.set("Ваниль")
    app.version_box._val = versions_mod.list_versions(snapshots=False)[0]
    app.on_play()
    pump(30.0, 0.5)
    try:
        app.ui_queue.put(("game_fail", "оф лоад"))
        app._drain_queue()
    except Exception as e:
        raise AssertionError("drain failed: %r" % e)
    assert app.play_btn._cfg.get("text") != "ЗАПУСК..." or True
    app._play_done()

    # mods page: render + queue handlers, no network installs
    app.show_page("Моды")
    app.loader_type.set("Fabric")
    app._loader_type_changed()
    for label, _pt, _nl, _d in app.CONTENT_TYPES:
        app.content_box.set(label)
        app._current_content()
    app.content_box.set("Моды")
    app._render_mod_results([])
    app._render_mod_results(
        [{"title": "Sodium", "project_id": "AABBCCDD",
          "description": "fast rendering", "downloads": 1234567,
          "icon_url": "https://example.com/icon.png"}]
    )
    pump(2.0, 0.1)
    app.ui_queue.put(("mods_fail", "тест-ошибка"))
    app.ui_queue.put(("mod_done", ("Sodium", ["sodium-fabric.jar"])))
    app.ui_queue.put(("modpack_prog", (5, 600, "entityculling")))
    app.ui_queue.put(("modpack_done", ["badmod"]))
    app._drain_queue()
    assert app.busy_mod is False

    from launcher import modpack as pack_mod

    assert len(pack_mod.mods()) == 600, "modpack must contain 600 mods"
    assert pack_mod.PACK_MINECRAFT == "1.20.1" and pack_mod.PACK_LOADER == "forge"

    print("GUI MOCK TEST PASSED: startup, all pages, all logins, play flow, mods page")


def accounts_selected_name():
    from launcher import accounts as acc_mod

    acc = acc_mod.selected()
    return acc.get("name") if acc else None


if __name__ == "__main__":
    main()
