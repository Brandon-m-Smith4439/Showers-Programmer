#!/usr/bin/env python3
"""Small Tkinter front end for shower batch programming."""

from __future__ import annotations

import os
import hashlib
import html
import json
import math
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from pypdf import PdfReader, PdfWriter

import shower_batch
import shower_programmer as programmer

_SCRIPT_PROJECT_ROOT = programmer.project_root()


def _gui_project_root() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates = [executable_dir, executable_dir.parent, Path.cwd()]
        for candidate in candidates:
            try:
                candidate = candidate.resolve()
            except OSError:
                continue
            if (candidate / "Input").exists() and (candidate / "Output").exists() and (candidate / "Assets").exists():
                return candidate
        return executable_dir
    return _SCRIPT_PROJECT_ROOT


programmer.project_root = _gui_project_root

try:
    import customtkinter as ctk
except Exception:
    ctk = None

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = None
    ImageDraw = None
    ImageTk = None


class ModernProgressBar:
    """Small CustomTkinter progress wrapper with the ttk Progressbar methods this app uses."""

    def __init__(self, parent: Any, app: "ShowerProgrammerApp", height: int = 12) -> None:
        self.app = app
        self.maximum = 100.0
        self.value = 0.0
        self.mode = "determinate"
        self.widget = ctk.CTkProgressBar(
            parent,
            mode="determinate",
            height=height,
            corner_radius=max(6, height // 2),
            border_width=0,
            fg_color=app.PROGRESS_TRACK,
            progress_color=app.PROGRESS_FILL,
        )
        self.widget.set(0.0)

    def configure(self, **kwargs: Any) -> None:
        if "maximum" in kwargs:
            try:
                self.maximum = max(float(kwargs.pop("maximum")), 1.0)
            except (TypeError, ValueError):
                self.maximum = 100.0
        if "mode" in kwargs:
            self.mode = str(kwargs.pop("mode") or "determinate")
            try:
                self.widget.configure(mode=self.mode)
            except tk.TclError:
                pass
        if "value" in kwargs:
            try:
                self.value = float(kwargs.pop("value"))
            except (TypeError, ValueError):
                self.value = 0.0
            self._sync_value()
        if "progress_color" not in kwargs:
            kwargs["progress_color"] = self.app.PROGRESS_FILL
        if "fg_color" not in kwargs:
            kwargs["fg_color"] = self.app.PROGRESS_TRACK
        try:
            self.widget.configure(**kwargs)
        except tk.TclError:
            pass

    config = configure

    def _sync_value(self) -> None:
        ratio = max(0.0, min(1.0, self.value / max(self.maximum, 1.0)))
        try:
            self.widget.set(ratio)
        except tk.TclError:
            pass

    def step(self, amount: float = 1.0) -> None:
        try:
            self.value += float(amount)
        except (TypeError, ValueError):
            self.value += 1.0
        self._sync_value()

    def start(self, *_args: Any) -> None:
        try:
            self.widget.configure(mode="indeterminate")
            self.widget.start()
        except tk.TclError:
            pass

    def stop(self) -> None:
        try:
            self.widget.stop()
            self.widget.configure(mode=self.mode)
        except tk.TclError:
            pass

    def grid(self, *args: Any, **kwargs: Any) -> Any:
        return self.widget.grid(*args, **kwargs)

    def pack(self, *args: Any, **kwargs: Any) -> Any:
        return self.widget.pack(*args, **kwargs)

    def place(self, *args: Any, **kwargs: Any) -> Any:
        return self.widget.place(*args, **kwargs)

    def destroy(self) -> None:
        self.widget.destroy()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.widget, name)


class ShowerProgrammerApp:
    APP_BG = "#f3f6fb"
    CARD_BG = "#ffffff"
    SOFT_CARD_BG = "#f8fbff"
    PANEL_BG = "#f6f9fd"
    BORDER = "#d8e1ec"
    ACCENT = "#2563eb"
    ACCENT_DARK = "#1d4ed8"
    ACCENT_LIGHT = "#eaf2ff"
    TEXT = "#111827"
    MUTED = "#667085"
    SUCCESS = "#12b76a"
    WARNING = "#f79009"
    DANGER = "#d92d20"
    SIDEBAR_BG = "#101828"
    SIDEBAR_CARD_BG = "#182230"
    SIDEBAR_TEXT = "#f9fafb"
    SIDEBAR_MUTED = "#98a2b3"
    SIDEBAR_BORDER = "#344054"
    REVIEW_RENDER_DPI = 96
    GITHUB_UPDATE_OWNER = "Brandon-m-Smith4439"
    GITHUB_UPDATE_REPO = "Showers-Programmer"
    GITHUB_UPDATE_BRANCH = "main"
    SHOP_SKETCHES_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\Sketches")
    SHOP_PROGRAMS_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\Programs")
    EDI_IMPORT_ORDERS_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\EDIImportSG\Showers Programmer Input")
    APP_ICON_PATH = programmer.project_root() / "Assets" / "ShowersProgrammer.ico"
    APP_ICON_PNG_PATH = programmer.project_root() / "Assets" / "ShowersProgrammer.png"
    IMPORT_STAGING_FOLDER_NAME = "Showers Programmer Input"
    ORDER_FILE_EXTENSIONS = {".pdf", ".dxf"}
    PROCESS_LIST_FILE_EXTENSIONS = shower_batch.PROCESS_LIST_EXTENSIONS
    INPUT_ARCHIVE_FOLDER_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
    HARDWARE_LIST_PREFIX = "hardware list"
    UI_SETTINGS_FILE_NAME = "shower_programmer_ui_settings.json"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Shower Programmer")
        self.root.geometry("1180x720")
        self.root.minsize(980, 560)
        self.set_window_icon(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.runtime_root = self.ensure_internal_runtime_folders()
        self.folder_var = tk.StringVar(value=str(self.internal_orders_dir()))
        self.import_source_var = tk.StringVar(value=str(self.EDI_IMPORT_ORDERS_DIR))
        self.process_list_var = tk.StringVar(value=str(self.internal_process_list_dir()))
        self.output_dir_var = tk.StringVar(value=str(self.internal_output_dir()))
        self.ui_settings = self.load_ui_settings()
        self.dark_mode_var = tk.BooleanVar(value=bool(self.ui_settings.get("dark_mode", False)))
        self.force_var = tk.BooleanVar(value=False)
        self.skip_dxf_var = tk.BooleanVar(value=False)
        self.remake_var = tk.BooleanVar(value=False)
        self.remake_items_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Scan the process list to begin.")
        self.summary_var = tk.StringVar(value="Orders 0   Ready 0   Issues 0   Processed 0   Checked 0")
        self.summary_count_vars = {
            "orders": tk.StringVar(value="0"),
            "ready": tk.StringVar(value="0"),
            "issues": tk.StringVar(value="0"),
            "processed": tk.StringVar(value="0"),
            "checked": tk.StringVar(value="0"),
        }

        self.orders: list[shower_batch.ProcessOrder] = []
        self.order_by_aw: dict[str, shower_batch.ProcessOrder] = {}
        self.tree_rows: dict[str, str] = {}
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_reports: shower_batch.BatchRunResult | None = None
        self.last_run_folder: Path | None = None
        self.is_busy = False
        self.background_progress_percent = 0.0
        self.send_review_window: tk.Toplevel | None = None
        self.send_review_progress: ttk.Progressbar | None = None
        self.send_review_status_var: tk.StringVar | None = None
        self.ui_icon_cache: dict[tuple[str, int, str], tk.PhotoImage] = {}
        self.ui_icon_pil_cache: dict[tuple[str, int, str], Any] = {}
        self.ctk_icon_cache: dict[tuple[str, int, str], Any] = {}
        self.review_context_cache: dict[str, dict[str, Any]] = {}
        self.review_context_cache_lock = threading.Lock()
        self.review_cache_generation = 0
        self.review_cache_worker_active = False
        self.active_themed_context_popup: tk.Toplevel | None = None
        self.active_themed_context_binding: tuple[tk.Widget, str, str] | None = None
        self.pending_update_script: Path | None = None
        self.pending_update_message = ""

        self.configure_styles()
        self.build_ui()
        self.force_main_window_maximized()
        self.root.after(75, self.drain_worker_queue)
        self.root.after_idle(lambda: self.root.after(850, self.scan_orders))

    def force_main_window_maximized(self) -> None:
        """Keep the main application maximized after theme/startup rebuilds."""
        def maximize() -> None:
            try:
                self.root.update_idletasks()
                self.maximize_window(self.root)
            except tk.TclError:
                pass

        maximize()
        for delay in (50, 200, 650):
            try:
                self.root.after(delay, maximize)
            except tk.TclError:
                pass

    @classmethod
    def preferred_runtime_root(cls) -> Path:
        root = programmer.project_root()
        try:
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=True, dir=str(root), encoding="utf-8"):
                pass
            return root
        except Exception:
            appdata = os.environ.get("APPDATA")
            base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
            return base / "Shower Programmer"

    def ensure_internal_runtime_folders(self) -> Path:
        root = self.preferred_runtime_root()
        self.ensure_workflow_folders(
            root / "Input" / "Orders",
            root / "Input" / "Process List",
            root / "Output",
        )
        return root

    @staticmethod
    def ensure_workflow_folders(order_folder: Path, process_list_path: Path, output_dir: Path) -> list[Path]:
        process_list_is_file = process_list_path.is_file() or process_list_path.suffix.lower() in ShowerProgrammerApp.PROCESS_LIST_FILE_EXTENSIONS
        process_list_dir = process_list_path.parent if process_list_is_file else process_list_path
        folders = [
            order_folder,
            process_list_dir,
            output_dir,
            output_dir / "Runs",
            output_dir / "Updates",
        ]
        created: list[Path] = []
        for folder in folders:
            existed = folder.exists()
            if existed and not folder.is_dir():
                raise NotADirectoryError(f"Required workflow path is not a folder: {folder}")
            folder.mkdir(parents=True, exist_ok=True)
            if not existed:
                created.append(folder)
        return created

    def internal_orders_dir(self) -> Path:
        return Path(getattr(self, "runtime_root", self.preferred_runtime_root())) / "Input" / "Orders"

    def internal_process_list_dir(self) -> Path:
        return Path(getattr(self, "runtime_root", self.preferred_runtime_root())) / "Input" / "Process List"

    def internal_output_dir(self) -> Path:
        return Path(getattr(self, "runtime_root", self.preferred_runtime_root())) / "Output"

    @staticmethod
    def set_window_icon(window: Any) -> None:
        png_path = ShowerProgrammerApp.APP_ICON_PNG_PATH
        if png_path.exists():
            try:
                photo = tk.PhotoImage(file=str(png_path))
                window.iconphoto(True, photo)
                window._shower_programmer_icon = photo
            except tk.TclError:
                pass
        icon_path = ShowerProgrammerApp.APP_ICON_PATH
        if not icon_path.exists():
            return
        try:
            window.iconbitmap(str(icon_path))
        except tk.TclError:
            pass

    @staticmethod
    def maximize_window(window: Any) -> None:
        try:
            window.state("zoomed")
            return
        except tk.TclError:
            pass

        try:
            window.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass

        try:
            window.attributes("-fullscreen", True)
        except tk.TclError:
            pass

    @staticmethod
    def toggle_window_maximize(window: Any) -> None:
        try:
            window.state("normal" if window.state() == "zoomed" else "zoomed")
            return
        except tk.TclError:
            pass
        try:
            window.attributes("-fullscreen", not bool(window.attributes("-fullscreen")))
        except tk.TclError:
            pass

    def position_child_window(self, window: tk.Toplevel, width: int, height: int) -> None:
        try:
            self.root.update_idletasks()
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_w = max(self.root.winfo_width(), 1)
            root_h = max(self.root.winfo_height(), 1)
            x = root_x + max(24, min(80, root_w // 12))
            y = root_y + max(24, min(80, root_h // 12))
            window.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            window.geometry(f"{width}x{height}")

    def bring_window_to_front(self, window: tk.Toplevel, make_transient: bool = True) -> None:
        def apply_focus() -> None:
            try:
                window.deiconify()
            except tk.TclError:
                pass
            if make_transient:
                try:
                    window.transient(self.root)
                except tk.TclError:
                    pass
            try:
                window.lift()
                window.focus_force()
            except tk.TclError:
                pass
            try:
                window.attributes("-topmost", True)
                window.after(350, lambda: window.attributes("-topmost", False))
            except tk.TclError:
                pass

        try:
            window.after(75, apply_focus)
        except tk.TclError:
            pass


    def close_active_themed_context_menu(self) -> None:
        binding = self.active_themed_context_binding
        if binding is not None:
            widget, sequence, funcid = binding
            try:
                widget.unbind(sequence, funcid)
            except tk.TclError:
                pass
            self.active_themed_context_binding = None

        popup = self.active_themed_context_popup
        self.active_themed_context_popup = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except tk.TclError:
                pass

    def show_themed_context_menu(
        self,
        parent: tk.Widget,
        x_root: int,
        y_root: int,
        title: str,
        subtitle: str,
        actions: list[dict[str, object]],
    ) -> None:
        self.close_active_themed_context_menu()
        if ctk is None:
            menu = tk.Menu(parent, tearoff=False)
            for action in actions:
                if action.get("separator"):
                    menu.add_separator()
                    continue
                command = action.get("command")
                menu.add_command(label=str(action.get("text", "")), command=command if callable(command) else None)
            try:
                menu.tk_popup(x_root, y_root)
            finally:
                menu.grab_release()
            return

        popup = ctk.CTkToplevel(parent)
        self.active_themed_context_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(fg_color=self.CARD_BG)
        try:
            popup.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass

        shell = ctk.CTkFrame(
            popup,
            fg_color=self.CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        shell.pack(fill=tk.BOTH, expand=True)

        header = ctk.CTkFrame(shell, fg_color=self.SOFT_CARD_BG, corner_radius=10)
        header.pack(fill=tk.X, padx=8, pady=(8, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            font=("Segoe UI", 13, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=(8, 0))
        ctk.CTkLabel(
            header,
            text=subtitle,
            font=("Segoe UI", 10),
            text_color=self.MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 8))
        ctk.CTkButton(
            header,
            text="",
            command=popup.destroy,
            width=28,
            height=28,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.ACCENT_LIGHT,
            text_color=self.MUTED,
            **self.ctk_button_icon("close", 13, self.MUTED, "left"),
        ).grid(row=0, column=1, rowspan=2, sticky="ne", padx=(0, 8), pady=8)

        body = ctk.CTkFrame(shell, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        def run_and_close(command: object) -> None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            if callable(command):
                try:
                    parent.after(20, command)
                except tk.TclError:
                    command()

        for action in actions:
            if action.get("separator"):
                ctk.CTkFrame(body, fg_color=self.DIVIDER, height=1, corner_radius=0).pack(fill=tk.X, padx=6, pady=6)
                continue
            destructive = bool(action.get("destructive"))
            icon_color = self.DANGER if destructive else self.ACCENT_DARK
            text_color = self.DANGER if destructive else self.TEXT
            hover_color = "#fee4e2" if destructive and not self.dark_mode_var.get() else ("#3b1f24" if destructive else self.ACCENT_LIGHT)
            ctk.CTkButton(
                body,
                text=str(action.get("text", "")),
                command=lambda command=action.get("command"): run_and_close(command),
                height=36,
                corner_radius=8,
                fg_color="transparent",
                hover_color=hover_color,
                text_color=text_color,
                font=("Segoe UI", 11, "bold"),
                anchor="w",
                **self.ctk_button_icon(str(action.get("icon", "info")), 16, icon_color, "left"),
            ).pack(fill=tk.X, pady=1)

        def cleanup_menu_state(_event: tk.Event | None = None) -> None:
            if self.active_themed_context_popup is popup:
                self.active_themed_context_popup = None
            binding = self.active_themed_context_binding
            if binding is not None:
                widget, sequence, funcid = binding
                try:
                    widget.unbind(sequence, funcid)
                except tk.TclError:
                    pass
                if self.active_themed_context_binding == binding:
                    self.active_themed_context_binding = None

        popup.bind("<Destroy>", cleanup_menu_state, add="+")

        popup.update_idletasks()
        try:
            screen_x = popup.winfo_vrootx()
            screen_y = popup.winfo_vrooty()
            screen_w = popup.winfo_vrootwidth()
            screen_h = popup.winfo_vrootheight()
        except tk.TclError:
            screen_x = 0
            screen_y = 0
            screen_w = popup.winfo_screenwidth()
            screen_h = popup.winfo_screenheight()
        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()
        x_min = screen_x + 8
        y_min = screen_y + 8
        x_max = screen_x + screen_w - width - 12
        y_max = screen_y + screen_h - height - 48
        x = max(x_min, min(int(x_root), x_max))
        y = max(y_min, min(int(y_root), y_max))
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        try:
            popup.focus_force()
        except tk.TclError:
            pass

        def close_menu(_event: tk.Event | None = None) -> str:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            return "break"

        # Do not close this popup on FocusOut. On initial review-window open,
        # Windows/Tk can fire FocusOut immediately after an overrideredirect
        # popup is shown. Instead, install a delayed outside-click handler.
        # The delay keeps the original right-click that opened the menu from
        # immediately closing it again, while still letting a normal click away
        # close the menu and letting a second right-click replace it.
        popup.bind("<Escape>", close_menu)

        def install_outside_click_close() -> None:
            try:
                owner = parent.winfo_toplevel()
            except tk.TclError:
                return
            if self.active_themed_context_popup is not popup:
                return

            def close_if_clicked_outside(_event: tk.Event) -> None:
                if self.active_themed_context_popup is popup:
                    self.close_active_themed_context_menu()

            try:
                funcid = owner.bind("<ButtonPress>", close_if_clicked_outside, add="+")
                self.active_themed_context_binding = (owner, "<ButtonPress>", funcid)
            except tk.TclError:
                pass

        try:
            popup.after(125, install_outside_click_close)
        except tk.TclError:
            pass

    def ask_themed_text(
        self,
        parent: tk.Widget,
        title: str,
        message: str,
        initialvalue: str = "",
    ) -> str | None:
        if ctk is None:
            return simpledialog.askstring(title, message, initialvalue=initialvalue, parent=parent)

        result: dict[str, str | None] = {"value": None}
        prompt = ctk.CTkToplevel(parent)
        prompt.title(title)
        prompt.configure(fg_color=self.APP_BG)
        prompt.resizable(False, False)
        self.set_window_icon(prompt)
        try:
            prompt.transient(parent.winfo_toplevel())
            prompt.grab_set()
        except tk.TclError:
            pass

        shell = ctk.CTkFrame(
            prompt,
            fg_color=self.CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        shell.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        shell.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            shell,
            text=title,
            font=("Segoe UI", 17, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            shell,
            text=message,
            font=("Segoe UI", 11),
            text_color=self.MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        text_box = ctk.CTkTextbox(
            shell,
            width=430,
            height=110,
            corner_radius=9,
            border_width=1,
            border_color=self.BORDER,
            fg_color=self.ENTRY_BG,
            text_color=self.TEXT,
            font=("Segoe UI", 12),
        )
        text_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        text_box.insert("1.0", str(initialvalue).replace("\\n", "\n"))

        button_row = ctk.CTkFrame(shell, fg_color="transparent")
        button_row.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 14))

        def cancel() -> None:
            result["value"] = None
            prompt.destroy()

        def save() -> None:
            result["value"] = text_box.get("1.0", "end-1c").strip()
            prompt.destroy()

        ctk.CTkButton(
            button_row,
            text="Cancel",
            command=cancel,
            width=96,
            height=36,
            corner_radius=8,
            fg_color=self.BUTTON_BG,
            hover_color=self.BUTTON_HOVER,
            border_width=1,
            border_color=self.BORDER,
            text_color=self.BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(
            button_row,
            text="Save Text",
            command=save,
            width=116,
            height=36,
            corner_radius=8,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_DARK,
            text_color="#ffffff",
            font=("Segoe UI", 11, "bold"),
            **self.ctk_button_icon("check", 15, "#ffffff", "left"),
        ).pack(side=tk.LEFT)

        prompt.update_idletasks()
        owner = parent.winfo_toplevel()
        try:
            x = owner.winfo_rootx() + max(40, (owner.winfo_width() - prompt.winfo_reqwidth()) // 2)
            y = owner.winfo_rooty() + max(40, (owner.winfo_height() - prompt.winfo_reqheight()) // 3)
            prompt.geometry(f"{prompt.winfo_reqwidth()}x{prompt.winfo_reqheight()}+{x}+{y}")
        except tk.TclError:
            pass

        def keep_text_prompt_in_front() -> None:
            try:
                owner.deiconify()
                owner.lift()
            except tk.TclError:
                pass
            try:
                prompt.deiconify()
                prompt.lift(owner)
                prompt.focus_force()
            except tk.TclError:
                pass
            try:
                prompt.attributes("-topmost", True)
                prompt.after(350, lambda: prompt.attributes("-topmost", False))
            except tk.TclError:
                pass
            try:
                text_box.focus_set()
            except tk.TclError:
                pass

        keep_text_prompt_in_front()
        prompt.after(100, keep_text_prompt_in_front)
        prompt.protocol("WM_DELETE_WINDOW", cancel)
        prompt.bind("<Escape>", lambda _event: cancel())
        prompt.wait_window()
        try:
            owner.deiconify()
            owner.lift()
            owner.focus_force()
        except tk.TclError:
            pass
        return result["value"]


    @classmethod
    def preferred_ui_settings_path(cls) -> Path:
        project_path = programmer.project_root() / cls.UI_SETTINGS_FILE_NAME
        try:
            project_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=True, dir=str(project_path.parent), encoding="utf-8"):
                pass
            return project_path
        except Exception:
            appdata = os.environ.get("APPDATA")
            base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
            return base / "Shower Programmer" / cls.UI_SETTINGS_FILE_NAME

    def load_ui_settings(self) -> dict[str, object]:
        path = self.preferred_ui_settings_path()
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
        return {}

    def save_ui_settings(self) -> None:
        path = self.preferred_ui_settings_path()
        data = {
            "dark_mode": bool(self.dark_mode_var.get()),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
            self.ui_settings = data
        except Exception:
            pass

    def on_close(self) -> None:
        self.save_ui_settings()
        self.root.destroy()

    def apply_ui_mode_palette(self) -> None:
        dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())
        self.is_dark_mode = dark
        if dark:
            self.APP_BG = "#111827"
            self.CARD_BG = "#1f2937"
            self.SOFT_CARD_BG = "#243145"
            self.PANEL_BG = "#182230"
            self.BORDER = "#344054"
            self.ACCENT = "#3b82f6"
            self.ACCENT_DARK = "#60a5fa"
            self.ACCENT_LIGHT = "#1e3a5f"
            self.TEXT = "#f9fafb"
            self.MUTED = "#98a2b3"
            self.SUCCESS = "#32d583"
            self.WARNING = "#fdb022"
            self.DANGER = "#f97066"
            self.SIDEBAR_BG = "#030712"
            self.SIDEBAR_CARD_BG = "#111827"
            self.SIDEBAR_TEXT = "#f9fafb"
            self.SIDEBAR_MUTED = "#98a2b3"
            self.SIDEBAR_BORDER = "#374151"
            self.ENTRY_BG = "#111827"
            self.BUTTON_BG = "#243145"
            self.BUTTON_HOVER = "#2f3f56"
            self.BUTTON_TEXT = "#f9fafb"
            self.TREE_BG = "#111827"
            self.TREE_HEADER_BG = "#1f2937"
            self.TREE_HEADER_TEXT = "#d0d5dd"
            self.TREE_SELECTED_BG = "#1d4ed8"
            self.TREE_SELECTED_TEXT = "#ffffff"
            self.PREVIEW_BG = "#0f172a"
            self.PREVIEW_CARD_BG = "#111827"
            self.DIVIDER = "#344054"
            self.METRIC_ICON_BG = "#0f172a"
            self.PROGRESS_TRACK = "#0b1220"
            self.PROGRESS_FILL = "#3b82f6"
            self.SCROLL_TRACK = "#111827"
            self.SCROLL_THUMB = "#475467"
            self.SCROLL_ACTIVE = "#667085"
        else:
            self.APP_BG = "#e7edf5"
            self.CARD_BG = "#ffffff"
            self.SOFT_CARD_BG = "#f3f7fc"
            self.PANEL_BG = "#f6f9fd"
            self.BORDER = "#cbd6e2"
            self.ACCENT = "#2563eb"
            self.ACCENT_DARK = "#1d4ed8"
            self.ACCENT_LIGHT = "#eaf2ff"
            self.TEXT = "#111827"
            self.MUTED = "#667085"
            self.SUCCESS = "#12b76a"
            self.WARNING = "#f79009"
            self.DANGER = "#d92d20"
            self.SIDEBAR_BG = "#ffffff"
            self.SIDEBAR_CARD_BG = "#f8fbff"
            self.SIDEBAR_TEXT = self.TEXT
            self.SIDEBAR_MUTED = self.MUTED
            self.SIDEBAR_BORDER = self.BORDER
            self.ENTRY_BG = "#ffffff"
            self.BUTTON_BG = "#ffffff"
            self.BUTTON_HOVER = "#eaf2ff"
            self.BUTTON_TEXT = "#344054"
            self.TREE_BG = "#ffffff"
            self.TREE_HEADER_BG = "#f1f5fb"
            self.TREE_HEADER_TEXT = "#344054"
            self.TREE_SELECTED_BG = "#dbeafe"
            self.TREE_SELECTED_TEXT = "#111827"
            self.PREVIEW_BG = "#eef4fa"
            self.PREVIEW_CARD_BG = "#fbfdff"
            self.DIVIDER = "#eef2f7"
            self.METRIC_ICON_BG = "#ffffff"
            self.PROGRESS_TRACK = "#d7e2ee"
            self.PROGRESS_FILL = "#2563eb"
            self.SCROLL_TRACK = "#e2e8f0"
            self.SCROLL_THUMB = "#98a2b3"
            self.SCROLL_ACTIVE = "#667085"

    def capture_tree_snapshot(self) -> tuple[list[tuple[tuple[str, ...], tuple[str, ...]]], list[str]]:
        if not hasattr(self, "tree"):
            return [], []
        rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        selection_orders: list[str] = []
        try:
            selected_rows = set(self.tree.selection())
            for row_id in self.tree.get_children():
                values = tuple(str(value) for value in self.tree.item(row_id, "values"))
                tags = tuple(str(tag) for tag in self.tree.item(row_id, "tags"))
                rows.append((values, tags))
                if row_id in selected_rows and len(values) >= 5:
                    selection_orders.append(values[4])
        except tk.TclError:
            return [], []
        return rows, selection_orders

    def restore_tree_snapshot(
        self,
        rows: list[tuple[tuple[str, ...], tuple[str, ...]]],
        selection_orders: list[str],
    ) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree_rows.clear()
        selected_row_ids: list[str] = []
        for values, tags in rows:
            row_id = self.tree.insert("", tk.END, values=values, tags=tags)
            if len(values) >= 5:
                aw_order = values[4]
                self.tree_rows[aw_order] = row_id
                if aw_order in selection_orders:
                    selected_row_ids.append(row_id)
        if selected_row_ids:
            self.tree.selection_set(*selected_row_ids)
        self.update_summary_strip()

    def toggle_color_mode(self) -> None:
        if self.is_busy:
            self.dark_mode_var.set(not self.dark_mode_var.get())
            self.status_var.set("Finish the current task before changing the color mode.")
            return
        rows, selection_orders = self.capture_tree_snapshot()
        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self.ui_icon_cache.clear()
        self.ui_icon_pil_cache.clear()
        self.ctk_icon_cache.clear()
        self.configure_styles()
        self.build_ui()
        self.restore_tree_snapshot(rows, selection_orders)
        self.force_main_window_maximized()
        self.save_ui_settings()
        mode_name = "Dark shop mode" if self.dark_mode_var.get() else "Light mode"
        self.status_var.set(f"{mode_name} enabled.")

    def configure_styles(self) -> None:
        self.apply_ui_mode_palette()
        if ctk is not None:
            ctk.set_appearance_mode("Dark" if self.dark_mode_var.get() else "Light")
            ctk.set_default_color_theme("blue")

        self.root.configure(bg=self.APP_BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.APP_BG)
        style.configure("Card.TFrame", background=self.CARD_BG)
        style.configure("SectionBody.TFrame", background=self.CARD_BG)
        style.configure("Toolbar.TFrame", background=self.CARD_BG)
        style.configure("Metric.TFrame", background=self.SOFT_CARD_BG)

        style.configure("TLabel", background=self.APP_BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.CARD_BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Metric.TLabel", background=self.SOFT_CARD_BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.APP_BG, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Summary.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=self.APP_BG, foreground=self.TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabel", background=self.CARD_BG, foreground=self.TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("PanelHeader.TFrame", background=self.SOFT_CARD_BG)
        style.configure("PanelHeader.TLabel", background=self.SOFT_CARD_BG, foreground=self.TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("InfoStrip.TLabel", background=self.SOFT_CARD_BG, foreground=self.MUTED, font=("Segoe UI", 9))

        style.configure(
            "TEntry",
            padding=(8, 6),
            fieldbackground=self.ENTRY_BG,
            foreground=self.TEXT,
            bordercolor="#cfd8e3",
            lightcolor="#e4eaf1",
            darkcolor="#cfd8e3",
            insertcolor=self.TEXT,
        )

        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
        style.configure(
            "Accent.TButton",
            padding=(16, 8),
            font=("Segoe UI", 9, "bold"),
            background=self.ACCENT,
            foreground="#ffffff",
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.ACCENT_DARK), ("pressed", "#1e40af"), ("disabled", "#9db7e9")],
            foreground=[("disabled", "#f3f8ff")],
        )
        style.configure(
            "Action.TButton",
            padding=(13, 8),
            font=("Segoe UI", 9, "bold"),
            background=self.BUTTON_BG,
            foreground=self.BUTTON_TEXT,
        )
        style.map("Action.TButton", background=[("active", self.ACCENT_LIGHT), ("pressed", self.BUTTON_HOVER)])
        style.configure(
            "Primary.Action.TButton",
            padding=(13, 8),
            font=("Segoe UI", 9, "bold"),
            background=self.ACCENT,
            foreground="#ffffff",
        )
        style.map(
            "Primary.Action.TButton",
            background=[("active", self.ACCENT_DARK), ("pressed", "#1e40af")],
            foreground=[("disabled", "#eaf2ff")],
        )

        style.configure("TCheckbutton", background=self.CARD_BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=self.PROGRESS_TRACK,
            background=self.PROGRESS_FILL,
            bordercolor=self.PROGRESS_TRACK,
            lightcolor=self.PROGRESS_FILL,
            darkcolor=self.PROGRESS_FILL,
            thickness=12,
        )
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background=self.SCROLL_THUMB,
            darkcolor=self.SCROLL_THUMB,
            lightcolor=self.SCROLL_THUMB,
            troughcolor=self.SCROLL_TRACK,
            bordercolor=self.SCROLL_TRACK,
            arrowcolor=self.MUTED,
            relief="flat",
            width=14,
        )
        style.configure(
            "Horizontal.TScrollbar",
            gripcount=0,
            background=self.SCROLL_THUMB,
            darkcolor=self.SCROLL_THUMB,
            lightcolor=self.SCROLL_THUMB,
            troughcolor=self.SCROLL_TRACK,
            bordercolor=self.SCROLL_TRACK,
            arrowcolor=self.MUTED,
            relief="flat",
            width=14,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", self.SCROLL_ACTIVE), ("pressed", self.SCROLL_ACTIVE)],
            arrowcolor=[("active", self.TEXT)],
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[("active", self.SCROLL_ACTIVE), ("pressed", self.SCROLL_ACTIVE)],
            arrowcolor=[("active", self.TEXT)],
        )
        try:
            style.layout(
                "Vertical.TScrollbar",
                [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})],
            )
            style.layout(
                "Horizontal.TScrollbar",
                [("Horizontal.Scrollbar.trough", {"sticky": "ew", "children": [("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})],
            )
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            rowheight=34,
            fieldbackground=self.TREE_BG,
            background=self.TREE_BG,
            foreground=self.TEXT,
            bordercolor=self.BORDER,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background=self.TREE_HEADER_BG,
            foreground=self.TREE_HEADER_TEXT,
            relief="flat",
            padding=(10, 9),
        )
        style.map(
            "Treeview",
            background=[("selected", self.TREE_SELECTED_BG)],
            foreground=[("selected", self.TREE_SELECTED_TEXT)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.ENTRY_BG,
            background=self.BUTTON_BG,
            foreground=self.TEXT,
            arrowcolor=self.TEXT,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            insertcolor=self.TEXT,
            selectbackground=self.ENTRY_BG,
            selectforeground=self.TEXT,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.ENTRY_BG), ("disabled", self.PANEL_BG)],
            background=[("readonly", self.BUTTON_BG), ("active", self.BUTTON_HOVER)],
            foreground=[("readonly", self.TEXT), ("disabled", self.MUTED)],
            selectbackground=[("readonly", self.ENTRY_BG)],
            selectforeground=[("readonly", self.TEXT)],
            arrowcolor=[("readonly", self.TEXT), ("disabled", self.MUTED)],
        )
        style.configure(
            "Review.TCombobox",
            fieldbackground=self.ENTRY_BG,
            background=self.BUTTON_BG,
            foreground=self.TEXT,
            arrowcolor=self.TEXT,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            selectbackground=self.ENTRY_BG,
            selectforeground=self.TEXT,
            padding=(8, 6),
        )
        style.map(
            "Review.TCombobox",
            fieldbackground=[("readonly", self.ENTRY_BG), ("disabled", self.PANEL_BG)],
            background=[("readonly", self.BUTTON_BG), ("active", self.BUTTON_HOVER)],
            foreground=[("readonly", self.TEXT), ("disabled", self.MUTED)],
            selectbackground=[("readonly", self.ENTRY_BG)],
            selectforeground=[("readonly", self.TEXT)],
            arrowcolor=[("readonly", self.TEXT), ("disabled", self.MUTED)],
        )
        try:
            self.root.option_add("*TCombobox*Listbox.background", self.ENTRY_BG)
            self.root.option_add("*TCombobox*Listbox.foreground", self.TEXT)
            self.root.option_add("*TCombobox*Listbox.selectBackground", self.ACCENT)
            self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        except tk.TclError:
            pass
        try:
            style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        except tk.TclError:
            pass
    def ui_icon(self, name: str, size: int = 18, color: str = "#1f5fa8") -> tk.PhotoImage | None:
        legacy_key = (name, size, color)
        key = (name, size, color, "modern_v2")
        cached = self.ui_icon_cache.get(key)
        if cached is None:
            cached = self.ui_icon_cache.get(legacy_key)
        if cached is not None:
            return cached
        if Image is None or ImageDraw is None or ImageTk is None:
            return None

        scale = 5
        canvas_size = max(1, size * scale)
        image = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        stroke = max(2, int(round(size * scale / 12)))
        thin = max(1, int(round(stroke * 0.72)))
        view = 24.0
        unit = canvas_size / view

        def xy(x: float, y: float) -> tuple[int, int]:
            return int(round(x * unit)), int(round(y * unit))

        def box(x1: float, y1: float, x2: float, y2: float) -> tuple[int, int, int, int]:
            return (*xy(x1, y1), *xy(x2, y2))

        def line(points: list[tuple[float, float]], width: int | None = None) -> None:
            draw.line([xy(x, y) for x, y in points], fill=color, width=width or stroke, joint="curve")

        def rect(x1: float, y1: float, x2: float, y2: float, radius: float = 3.0, width: int | None = None, fill: str | None = None) -> None:
            draw.rounded_rectangle(box(x1, y1, x2, y2), radius=int(round(radius * unit)), outline=color, width=width or stroke, fill=fill)

        def circle(cx: float, cy: float, r: float, width: int | None = None, fill: str | None = None) -> None:
            draw.ellipse(box(cx - r, cy - r, cx + r, cy + r), outline=color, width=width or stroke, fill=fill)

        def poly(points: list[tuple[float, float]], fill: str | None = None, outline: str | None = None, width: int | None = None) -> None:
            scaled = [xy(x, y) for x, y in points]
            draw.polygon(scaled, fill=fill, outline=outline)
            if outline and width:
                draw.line(scaled + [scaled[0]], fill=outline, width=width, joint="curve")

        def arc(x1: float, y1: float, x2: float, y2: float, start: float, end: float, width: int | None = None) -> None:
            draw.arc(box(x1, y1, x2, y2), start=start, end=end, fill=color, width=width or stroke)

        def document_icon(label: str | None = None) -> None:
            line([(7, 3), (14, 3), (18, 7), (18, 21), (6, 21), (6, 3), (7, 3)])
            line([(14, 3.2), (14, 7.2), (18, 7.2)], thin)
            if label == "dxf":
                line([(8.6, 14.8), (11.0, 12.0), (13.0, 15.0), (15.5, 11.0)], thin)
                circle(8.6, 14.8, 0.75, fill=color, width=thin)
                circle(15.5, 11.0, 0.75, fill=color, width=thin)
            elif label == "orders":
                line([(9, 10), (15, 10)], thin)
                line([(9, 13), (15, 13)], thin)
                line([(9, 16), (14, 16)], thin)
                circle(7.6, 10, 0.35, fill=color, width=thin)
                circle(7.6, 13, 0.35, fill=color, width=thin)
                circle(7.6, 16, 0.35, fill=color, width=thin)
            else:
                line([(8.7, 11), (15.3, 11)], thin)
                line([(8.7, 14), (15.3, 14)], thin)
                line([(8.7, 17), (13.8, 17)], thin)

        icon = name.lower().replace("-", "_")
        if icon in {"folder", "open_folder"}:
            rect(3, 7.5, 21, 19, radius=2.6)
            line([(4.5, 8), (8.7, 8), (10.1, 10.3), (19.5, 10.3)], thin)
        elif icon in {"scan", "search"}:
            circle(10.5, 10.5, 5.8)
            line([(15.0, 15.0), (20.0, 20.0)], stroke)
            circle(10.5, 10.5, 2.0, width=thin)
        elif icon in {"check", "check_circle", "ready", "checked"}:
            circle(12, 12, 8.3)
            line([(7.7, 12.2), (10.5, 15.0), (16.7, 8.7)], stroke)
        elif icon == "play":
            circle(12, 12, 8.5, width=thin)
            poly([(10, 8), (16.2, 12), (10, 16)], fill=color)
        elif icon == "eye":
            line([(3.8, 12), (6.8, 8.3), (12, 6.8), (17.2, 8.3), (20.2, 12), (17.2, 15.7), (12, 17.2), (6.8, 15.7), (3.8, 12)], thin)
            circle(12, 12, 2.7, fill=color, width=thin)
        elif icon == "trash":
            line([(5.5, 7), (18.5, 7)], stroke)
            line([(9, 4.7), (15, 4.7)], thin)
            rect(7, 7.5, 17, 20, radius=2.0, width=thin)
            line([(10, 10.2), (10, 17.2)], thin)
            line([(14, 10.2), (14, 17.2)], thin)
        elif icon == "refresh":
            arc(4.7, 5.0, 19.3, 19.6, 35, 305)
            poly([(17.8, 5.3), (20.8, 5.5), (19.2, 8.2)], fill=color)
        elif icon == "rotate_left":
            arc(5, 5, 19, 19, 70, 340)
            poly([(6.9, 4.9), (4.3, 8.1), (8.4, 8.0)], fill=color)
        elif icon == "rotate_right":
            arc(5, 5, 19, 19, 200, 110)
            poly([(17.1, 4.9), (19.7, 8.1), (15.6, 8.0)], fill=color)
        elif icon == "link":
            rect(3.8, 9.4, 12.6, 15.2, radius=2.8, width=thin)
            rect(11.4, 8.8, 20.2, 14.6, radius=2.8, width=thin)
            line([(9.0, 12.3), (15.0, 11.7)], thin)
        elif icon == "clock":
            circle(12, 12, 8.5)
            line([(12, 7.3), (12, 12.3), (15.7, 14.2)], thin)
        elif icon in {"file", "pdf"}:
            document_icon("pdf")
        elif icon in {"dxf", "program"}:
            document_icon("dxf")
        elif icon == "orders":
            document_icon("orders")
        elif icon == "save":
            rect(4.5, 4.5, 19.5, 19.5, radius=2.5)
            rect(7.4, 5.7, 16.4, 10.0, radius=1.0, width=thin)
            line([(8, 17), (16, 17)], thin)
            line([(16.5, 4.8), (19.1, 7.4)], thin)
        elif icon == "indicator":
            circle(12, 12, 4.4, fill=color)
            line([(12, 3.8), (12, 7.0)], thin)
            line([(12, 17.0), (12, 20.2)], thin)
            line([(3.8, 12), (7.0, 12)], thin)
            line([(17.0, 12), (20.2, 12)], thin)
        elif icon == "flip":
            line([(5, 8), (18, 8)], stroke)
            poly([(18, 5.2), (21, 8), (18, 10.8)], fill=color)
            line([(19, 16), (6, 16)], stroke)
            poly([(6, 13.2), (3, 16), (6, 18.8)], fill=color)
        elif icon == "text":
            line([(5, 6), (19, 6)], stroke)
            line([(12, 6), (12, 18)], stroke)
            line([(8.4, 18), (15.6, 18)], stroke)
        elif icon in {"x", "close"}:
            circle(12, 12, 8.5, width=thin)
            line([(8.5, 8.5), (15.5, 15.5)], stroke)
            line([(15.5, 8.5), (8.5, 15.5)], stroke)
        elif icon == "chevron_left":
            line([(14.7, 6.2), (8.7, 12), (14.7, 17.8)], stroke)
        elif icon == "chevron_right":
            line([(9.3, 6.2), (15.3, 12), (9.3, 17.8)], stroke)
        elif icon == "chevron_up":
            line([(6.2, 14.7), (12, 8.7), (17.8, 14.7)], stroke)
        elif icon == "chevron_down":
            line([(6.2, 9.3), (12, 15.3), (17.8, 9.3)], stroke)
        elif icon in {"send", "paper_plane"}:
            poly([(3.8, 5.2), (21, 3.2), (14.9, 20.8), (11.5, 13.3)], outline=color, width=thin)
            line([(11.5, 13.3), (21, 3.2)], thin)
        elif icon == "image":
            rect(4, 5, 20, 19, radius=2.2)
            circle(8, 9, 1.3, fill=color, width=thin)
            line([(5.8, 17), (10, 12.7), (12.4, 15.0), (15.8, 11.2), (19, 17)], thin)
        elif icon == "info":
            circle(12, 12, 8.5)
            circle(12, 8.1, 0.9, fill=color, width=thin)
            line([(12, 11), (12, 16.4)], stroke)
        elif icon == "warning":
            poly([(12, 3.7), (21, 20), (3, 20)], outline=color, width=stroke)
            line([(12, 9), (12, 14.4)], stroke)
            circle(12, 17.0, 0.85, fill=color, width=thin)
        elif icon == "minus_circle":
            circle(12, 12, 8.5)
            line([(8, 12), (16, 12)], stroke)
        elif icon == "plus":
            circle(12, 12, 8.5, width=thin)
            line([(12, 7.5), (12, 16.5)], stroke)
            line([(7.5, 12), (16.5, 12)], stroke)
        else:
            document_icon(None)

        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        image = image.resize((size, size), resampling)
        self.ui_icon_pil_cache[key] = image.copy()
        self.ui_icon_pil_cache[legacy_key] = image.copy()
        photo = ImageTk.PhotoImage(image)
        self.ui_icon_cache[key] = photo
        self.ui_icon_cache[legacy_key] = photo
        return photo

    def ctk_button_icon(self, name: str, size: int = 16, color: str = "#1f5fa8", compound: str = "left") -> dict[str, object]:
        if ctk is None:
            return {}
        key = (name, size, color)
        cached = self.ctk_icon_cache.get(key)
        if cached is None:
            self.ui_icon(name, size=size, color=color)
            image = self.ui_icon_pil_cache.get(key)
            if image is None:
                return {}
            cached = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
            self.ctk_icon_cache[key] = cached
        return {"image": cached, "compound": compound}

    def button_icon(self, name: str, size: int = 16, color: str = "#1f5fa8", compound: str = tk.LEFT) -> dict[str, object]:
        icon = self.ui_icon(name, size=size, color=color)
        if icon is None:
            return {}
        return {"image": icon, "compound": compound}

    def app_logo_image(self, size: int = 24) -> Any:
        if ctk is None or Image is None:
            return self.ctk_button_icon("dxf", size, self.ACCENT_DARK).get("image")
        if bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get()):
            return self.ctk_button_icon("dxf", size, self.ACCENT_DARK).get("image")
        key = ("app_logo", size, "native")
        cached = self.ctk_icon_cache.get(key)
        if cached is not None:
            return cached
        image = None
        if self.APP_ICON_PNG_PATH.exists():
            try:
                image = Image.open(self.APP_ICON_PNG_PATH).convert("RGBA")
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                image.thumbnail((size, size), resampling)
                canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
                canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
                image = canvas
            except Exception:
                image = None
        if image is None:
            self.ui_icon("dxf", size=size, color=self.ACCENT_DARK)
            image = self.ui_icon_pil_cache.get(("dxf", size, self.ACCENT_DARK))
        if image is None:
            return None
        cached = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
        self.ctk_icon_cache[key] = cached
        return cached

    def make_app_header(self, parent: Any, title: str, padx: int = 0) -> Any:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill=tk.X, padx=padx, pady=(0, 12))

        row = ctk.CTkFrame(header, fg_color="transparent", height=48)
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        icon_box = ctk.CTkFrame(
            row,
            fg_color=self.SOFT_CARD_BG if not self.dark_mode_var.get() else self.PANEL_BG,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
            width=42,
            height=42,
        )
        icon_box.pack(side=tk.LEFT, pady=3)
        icon_box.pack_propagate(False)
        logo = self.app_logo_image(30)
        ctk.CTkLabel(icon_box, text="", image=logo, width=34, height=34).pack(expand=True)

        title_stack = ctk.CTkFrame(row, fg_color="transparent")
        title_stack.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=(12, 0))
        ctk.CTkLabel(
            title_stack,
            text=title,
            font=("Segoe UI", 22, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            title_stack,
            text="Production-ready shower sketch and DXF workflow",
            font=("Segoe UI", 11),
            text_color=self.MUTED,
            anchor="w",
        ).pack(anchor=tk.W, pady=(0, 2))
        return header
    def icon_label(self, parent: ttk.Frame, icon_name: str, size: int = 18, color: str = "#1f5fa8", style: str = "Card.TLabel") -> None:
        icon = self.ui_icon(icon_name, size=size, color=color)
        if icon is not None:
            ttk.Label(parent, image=icon, style=style).pack(side=tk.LEFT, padx=(0, 8))

    def build_ui(self) -> None:
        if ctk is None:
            raise RuntimeError("CustomTkinter is required for the modern Shower Programmer GUI.")

        outer = ctk.CTkFrame(self.root, fg_color=self.APP_BG, corner_radius=0)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        outer.grid_columnconfigure(0, weight=0)
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(
            outer,
            fg_color=self.SIDEBAR_BG,
            corner_radius=18,
            border_width=1,
            border_color=self.SIDEBAR_BORDER,
            width=268,
        )
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_rowconfigure(7, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 14))
        brand.grid_columnconfigure(1, weight=1)

        logo_box = ctk.CTkFrame(
            brand,
            fg_color="#eaf2ff" if not self.dark_mode_var.get() else self.SIDEBAR_CARD_BG,
            corner_radius=12,
            width=44,
            height=44,
        )
        logo_box.grid(row=0, column=0, rowspan=2, sticky="w")
        logo_box.grid_propagate(False)
        ctk.CTkLabel(logo_box, text="", image=self.app_logo_image(32)).pack(expand=True)
        ctk.CTkLabel(
            brand,
            text="Shower Programmer",
            font=("Segoe UI", 16, "bold"),
            text_color=self.SIDEBAR_TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0))
        ctk.CTkLabel(
            brand,
            text="CNC batch control",
            font=("Segoe UI", 11),
            text_color=self.SIDEBAR_MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(12, 0))

        center_stack = ctk.CTkFrame(sidebar, fg_color="transparent")
        center_stack.grid(row=2, column=0, sticky="ew")
        center_stack.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            center_stack,
            text="WORKFLOW",
            font=("Segoe UI", 10, "bold"),
            text_color=self.SIDEBAR_MUTED,
            anchor="center",
        ).pack(fill=tk.X, padx=18, pady=(0, 7))

        workflow = ctk.CTkFrame(center_stack, fg_color="transparent")
        workflow.pack(fill=tk.X, padx=12)
        self.make_sidebar_button(workflow, "Scan Orders", "scan", self.scan_orders, primary=True).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(workflow, "Process Selected", "check_circle", self.process_selected).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(workflow, "Process All", "play", self.process_all_orders).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(workflow, "Review Order", "eye", self.open_order_review).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(workflow, "Mark Checked", "check", self.mark_selected_orders_checked).pack(fill=tk.X)

        options_card = ctk.CTkFrame(
            center_stack,
            fg_color=self.SIDEBAR_CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=self.SIDEBAR_BORDER,
        )
        options_card.pack(fill=tk.X, padx=12, pady=(18, 0))
        ctk.CTkLabel(
            options_card,
            text="Run Options",
            font=("Segoe UI", 12, "bold"),
            text_color=self.SIDEBAR_TEXT,
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(12, 8))
        self.make_option_switch(options_card, "Overwrite outputs", self.force_var).pack(fill=tk.X, padx=14, pady=(0, 8))
        self.make_option_switch(options_card, "Skip DXF output", self.skip_dxf_var).pack(fill=tk.X, padx=14, pady=(0, 8))
        self.make_option_switch(options_card, "REMAKE batch", self.remake_var).pack(fill=tk.X, padx=14, pady=(0, 14))

        ctk.CTkLabel(
            center_stack,
            text="TOOLS",
            font=("Segoe UI", 10, "bold"),
            text_color=self.SIDEBAR_MUTED,
            anchor="center",
        ).pack(fill=tk.X, padx=18, pady=(18, 7))

        tools = ctk.CTkFrame(center_stack, fg_color="transparent")
        tools.pack(fill=tk.X, padx=12)
        self.make_sidebar_button(tools, "Clear Sketch Memory", "trash", self.clear_sketch_memory, compact=True).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(tools, "Check for Updates", "refresh", self.check_for_updates, compact=True).pack(fill=tk.X, pady=(0, 8))
        self.make_sidebar_button(tools, "Install Shortcut", "link", self.install_shortcut, compact=True).pack(fill=tk.X)

        send_card = ctk.CTkFrame(
            sidebar,
            fg_color="#0b5ed7",
            corner_radius=14,
            border_width=1,
            border_color="#2e90fa",
        )
        send_card.grid(row=8, column=0, sticky="ew", padx=12, pady=(14, 16))
        ctk.CTkLabel(
            send_card,
            text="Ready for shop?",
            font=("Segoe UI", 13, "bold"),
            text_color="#ffffff",
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(12, 2))
        ctk.CTkLabel(
            send_card,
            text="Review generated sketches and send the selected batch.",
            font=("Segoe UI", 10),
            text_color="#dbeafe",
            justify="left",
            anchor="w",
            wraplength=210,
        ).pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkButton(
            send_card,
            text="Select All Orders",
            command=lambda: self.select_all_orders(),
            height=36,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#1d4ed8",
            border_width=1,
            border_color="#93c5fd",
            text_color="#ffffff",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            **self.ctk_button_icon("check_circle", 16, "#ffffff", "left"),
        ).pack(fill=tk.X, padx=14, pady=(0, 8))
        ctk.CTkButton(
            send_card,
            text="Review / Send",
            command=self.send_all_to_shop,
            height=42,
            corner_radius=10,
            fg_color="#ffffff" if not self.dark_mode_var.get() else self.ACCENT,
            hover_color="#eaf2ff" if not self.dark_mode_var.get() else self.ACCENT_DARK,
            text_color="#1849a9" if not self.dark_mode_var.get() else "#ffffff",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
            **self.ctk_button_icon("send", 17, "#1849a9" if not self.dark_mode_var.get() else "#ffffff", "left"),
        ).pack(fill=tk.X, padx=14, pady=(0, 14))

        content = ctk.CTkFrame(outer, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(4, weight=1)

        top_bar = ctk.CTkFrame(content, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_bar.grid_columnconfigure(0, weight=1)

        title_stack = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_stack.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            title_stack,
            text="Production Dashboard",
            font=("Segoe UI", 25, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            title_stack,
            text="Import orders, process CNC files, review output, and send to the shop from one screen.",
            font=("Segoe UI", 12),
            text_color=self.MUTED,
            anchor="w",
        ).pack(anchor=tk.W, pady=(1, 0))

        header_actions = ctk.CTkFrame(top_bar, fg_color="transparent")
        header_actions.grid(row=0, column=1, sticky="e")
        ctk.CTkSwitch(
            header_actions,
            text="Dark mode",
            variable=self.dark_mode_var,
            command=self.toggle_color_mode,
            progress_color=self.ACCENT,
            button_color="#ffffff",
            button_hover_color="#f2f4f7",
            fg_color="#98a2b3" if not self.dark_mode_var.get() else "#475467",
            text_color=self.TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 12))
        self.make_tool_button(header_actions, "Open Input", "folder", self.open_input_folder, width=140).pack(side=tk.LEFT, padx=(0, 8))
        self.make_tool_button(header_actions, "Latest Batch", "clock", self.open_latest_batch, width=145).pack(side=tk.LEFT)

        metrics = ctk.CTkFrame(content, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.add_metric_card(metrics, "orders", "Orders", "orders", self.ACCENT_DARK)
        self.add_metric_card(metrics, "ready", "Ready", "check_circle", self.SUCCESS)
        self.add_metric_card(metrics, "issues", "Issues", "warning", self.WARNING)
        self.add_metric_card(metrics, "processed", "Processed", "refresh", "#7c3aed")
        self.add_metric_card(metrics, "checked", "Checked", "checked", self.ACCENT_DARK)

        paths, paths_body = self.make_collapsible_section(content, "Folder Setup", "folder", expanded=False)
        paths.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.add_path_row(paths_body, 0, "Orders", self.folder_var, self.choose_folder)
        self.add_path_row(paths_body, 1, "Import From", self.import_source_var, self.choose_import_source)
        self.add_path_row(paths_body, 2, "Process Lists", self.process_list_var, self.choose_process_list)
        self.add_path_row(paths_body, 3, "Output", self.output_dir_var, self.choose_output_dir)

        table_outer = self.make_section(content, "Orders", "orders")
        table_outer.grid(row=4, column=0, sticky="nsew")
        table_outer.grid_columnconfigure(0, weight=1)
        table_outer.grid_rowconfigure(1, weight=1)

        table_frame = ctk.CTkFrame(table_outer, fg_color="transparent")
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("status", "processed", "last_processed", "delivery", "order", "job", "customer", "items", "review", "pdf", "issues")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = {
            "status": "Status",
            "processed": "Processed",
            "last_processed": "Last Processed",
            "delivery": "Delivery",
            "order": "A&W",
            "job": "Job",
            "customer": "Customer",
            "items": "Items",
            "review": "Review",
            "pdf": "PDF",
            "issues": "Issues",
        }
        widths = {
            "status": 88,
            "processed": 92,
            "last_processed": 142,
            "delivery": 102,
            "order": 88,
            "job": 260,
            "customer": 210,
            "items": 110,
            "review": 134,
            "pdf": 230,
            "issues": 380,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            min_width = 62 if col in {"status", "processed"} else 74
            stretch = col in {"job", "customer", "pdf", "issues"}
            self.tree.column(col, width=widths[col], minwidth=min_width, anchor=tk.W, stretch=stretch)

        self.tree.tag_configure("OK", foreground=self.SUCCESS)
        self.tree.tag_configure("READY", foreground=self.ACCENT_DARK)
        self.tree.tag_configure("ISSUES", foreground=self.WARNING)
        self.tree.tag_configure("FAILED", foreground=self.DANGER)
        self.tree.tag_configure("SKIPPED", foreground=self.DANGER)
        self.tree.bind("<Double-1>", self.open_order_review)
        self.tree.bind("<Button-3>", self.open_orders_context_menu)
        self.tree.bind("<Control-a>", self.select_all_orders)
        self.tree.bind("<Control-A>", self.select_all_orders)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        bottom = ctk.CTkFrame(
            content,
            fg_color=self.CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=self.BORDER,
        )
        bottom.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=0)
        self.progress = ModernProgressBar(bottom, self, height=14)
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 0), ipady=2)
        self.status_label = ctk.CTkLabel(
            bottom,
            textvariable=self.status_var,
            anchor="w",
            text_color=self.MUTED,
            font=("Segoe UI", 12),
            width=520,
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(9, 12))
    def make_sidebar_button(
        self,
        parent: Any,
        text: str,
        icon_name: str,
        command: Callable[..., object],
        primary: bool = False,
        compact: bool = False,
    ) -> Any:
        dark = bool(self.dark_mode_var.get())
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=42 if compact else 48,
            corner_radius=11,
            fg_color=self.ACCENT if primary else "transparent",
            hover_color=self.ACCENT_DARK if primary else ("#263445" if dark else self.ACCENT_LIGHT),
            border_width=0 if primary else 1,
            border_color=self.SIDEBAR_BORDER,
            text_color="#ffffff" if primary else self.SIDEBAR_TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            **self.ctk_button_icon(icon_name, 17, "#ffffff" if primary else ("#d0d5dd" if dark else self.ACCENT_DARK), "left"),
        )

    def make_option_switch(self, parent: Any, text: str, variable: tk.BooleanVar) -> Any:
        dark = bool(self.dark_mode_var.get())
        return ctk.CTkSwitch(
            parent,
            text=text,
            variable=variable,
            progress_color=self.ACCENT if dark else "#1d4ed8",
            button_color="#f9fafb" if dark else "#ffffff",
            button_hover_color="#e5e7eb" if dark else "#eff6ff",
            fg_color="#344054" if dark else "#b7c6d8",
            text_color=self.SIDEBAR_TEXT if dark else "#1f2937",
            font=("Segoe UI", 11, "bold"),
        )

    def make_main_action_button(
        self,
        parent: Any,
        text: str,
        icon_name: str,
        command: Callable[[], object],
        primary: bool = False,
    ) -> Any:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=124,
            height=72,
            corner_radius=13,
            fg_color=self.ACCENT if primary else self.BUTTON_BG,
            hover_color=self.ACCENT_DARK if primary else self.BUTTON_HOVER,
            border_width=0 if primary else 1,
            border_color=self.BORDER,
            text_color="#ffffff" if primary else self.BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
            **self.ctk_button_icon(icon_name, 24, "#ffffff" if primary else self.ACCENT_DARK, "top"),
        )

    def make_tool_button(
        self,
        parent: Any,
        text: str,
        icon_name: str,
        command: Callable[..., object],
        width: int = 180,
    ) -> Any:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=36,
            corner_radius=10,
            fg_color=self.BUTTON_BG,
            hover_color=self.BUTTON_HOVER,
            border_width=1,
            border_color=self.BORDER,
            text_color=self.BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
            **self.ctk_button_icon(icon_name, 15, self.ACCENT_DARK, "left"),
        )

    def make_section(self, parent: Any, title: str, icon_name: str | None = None) -> Any:
        frame = ctk.CTkFrame(
            parent,
            fg_color=self.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=self.BORDER,
        )
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent", height=48)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.grid_propagate(False)

        title_cluster = ctk.CTkFrame(header, fg_color="transparent")
        title_cluster.pack(side=tk.LEFT, fill=tk.Y)
        if icon_name:
            ctk.CTkLabel(
                title_cluster,
                text="",
                image=self.ctk_button_icon(icon_name, 17, self.ACCENT_DARK).get("image"),
                width=24,
            ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkLabel(
            title_cluster,
            text=title,
            font=("Segoe UI", 14, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkFrame(frame, fg_color=self.DIVIDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew", padx=14)
        return frame

    def make_collapsible_section(
        self,
        parent: Any,
        title: str,
        icon_name: str | None = None,
        expanded: bool = False,
    ) -> tuple[Any, Any]:
        frame = ctk.CTkFrame(
            parent,
            fg_color=self.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=self.BORDER,
        )
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent", height=48)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.grid_propagate(False)
        if icon_name:
            ctk.CTkLabel(
                header,
                text="",
                image=self.ctk_button_icon(icon_name, 17, self.ACCENT_DARK).get("image"),
                width=24,
            ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkLabel(
            header,
            text=title,
            font=("Segoe UI", 14, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(side=tk.LEFT)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        collapsed = tk.BooleanVar(value=not expanded)

        def toggle() -> None:
            if collapsed.get():
                body.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
                toggle_button.configure(text="Hide", **self.ctk_button_icon("chevron_up", 14, self.ACCENT_DARK, "left"))
                collapsed.set(False)
            else:
                body.grid_forget()
                toggle_button.configure(text="Show", **self.ctk_button_icon("chevron_down", 14, self.ACCENT_DARK, "left"))
                collapsed.set(True)

        toggle_button = ctk.CTkButton(
            header,
            text="Show",
            command=toggle,
            width=86,
            height=30,
            corner_radius=10,
            fg_color=self.BUTTON_BG,
            hover_color=self.BUTTON_HOVER,
            border_width=1,
            border_color=self.BORDER,
            text_color=self.BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
            **self.ctk_button_icon("chevron_down", 14, self.ACCENT_DARK, "left"),
        )
        toggle_button.pack(side=tk.RIGHT)
        ctk.CTkFrame(frame, fg_color=self.DIVIDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew", padx=14)

        if expanded:
            body.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
            toggle_button.configure(text="Hide", **self.ctk_button_icon("chevron_up", 14, self.ACCENT_DARK, "left"))
        return frame, body

    def add_metric_card(
        self,
        parent: Any,
        key: str,
        caption: str,
        icon_name: str | None = None,
        icon_color: str = "#1f5fa8",
    ) -> None:
        self.add_count_card(parent, self.summary_count_vars[key], caption, icon_name, icon_color)

    def metric_tint(self, icon_color: str) -> tuple[str, str]:
        color = icon_color.lower()
        if self.dark_mode_var.get():
            if color in {"#32d583", "#12b76a", "#15945b", "#14915a"}:
                return "#102a23", "#1d6b4f"
            if color in {"#fdb022", "#f79009", "#d97706", "#f08c00"}:
                return "#2f2410", "#8a5a0a"
            if color in {"#f97066", "#d92d20", "#c92a2a", "#b42318"}:
                return "#331714", "#8a2a22"
            if color in {"#7c3aed", "#6b4bb5"}:
                return "#201a3d", "#51459b"
            return "#13233f", "#285592"
        if color in {"#12b76a", "#15945b", "#14915a"}:
            return "#ecfdf3", "#abefc6"
        if color in {"#f79009", "#d97706", "#f08c00"}:
            return "#fffaeb", "#fedf89"
        if color in {"#d92d20", "#c92a2a", "#b42318"}:
            return "#fef3f2", "#fecdca"
        if color in {"#7c3aed", "#6b4bb5"}:
            return "#f4f3ff", "#d9d6fe"
        return "#eff6ff", "#bfdbfe"

    def add_count_card(
        self,
        parent: Any,
        number_var: tk.StringVar,
        caption: str,
        icon_name: str | None = None,
        icon_color: str = "#1f5fa8",
    ) -> Any:
        tint, border = self.metric_tint(icon_color)
        card = ctk.CTkFrame(
            parent,
            fg_color=tint,
            corner_radius=14,
            border_width=1,
            border_color=border,
            height=76,
        )
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        card.pack_propagate(False)

        if icon_name:
            icon_box = ctk.CTkFrame(card, fg_color=self.METRIC_ICON_BG, corner_radius=11, width=42, height=42)
            icon_box.pack(side=tk.LEFT, padx=(14, 10), pady=16)
            icon_box.pack_propagate(False)
            ctk.CTkLabel(icon_box, text="", image=self.ctk_button_icon(icon_name, 23, icon_color).get("image")).pack(expand=True)

        text_stack = ctk.CTkFrame(card, fg_color="transparent")
        text_stack.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=13)
        ctk.CTkLabel(
            text_stack,
            textvariable=number_var,
            font=("Segoe UI", 20, "bold"),
            text_color=icon_color,
            anchor="w",
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            text_stack,
            text=caption,
            font=("Segoe UI", 10, "bold"),
            text_color=self.MUTED if not self.dark_mode_var.get() else "#d0d5dd",
            anchor="w",
        ).pack(anchor=tk.W)
        return card

    def add_path_row(self, parent: Any, row: int, label: str, var: tk.StringVar, command) -> None:
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill=tk.X, pady=(0, 7))
        row_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_frame,
            text=label,
            width=118,
            text_color=self.TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        ctk.CTkEntry(
            row_frame,
            textvariable=var,
            height=36,
            corner_radius=10,
            border_color=self.BORDER,
            fg_color=self.ENTRY_BG,
            text_color=self.TEXT,
            font=("Segoe UI", 11),
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        self.make_tool_button(
            row_frame,
            text="Browse",
            icon_name="folder",
            command=command,
            width=104,
        ).grid(row=0, column=2, sticky=tk.E)
    def choose_folder(self) -> None:
        path = filedialog.askdirectory(initialdir=self.folder_var.get())
        if path:
            self.folder_var.set(path)

    def choose_import_source(self) -> None:
        path = filedialog.askdirectory(initialdir=self.import_source_var.get())
        if path:
            self.import_source_var.set(path)

    def choose_process_list(self) -> None:
        current = Path(self.process_list_var.get())
        initial = current if current.is_dir() else current.parent
        path = filedialog.askdirectory(initialdir=str(initial), title="Select process-list folder")
        if path:
            self.process_list_var.set(path)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    def apply_import_source_dir(self) -> Path:
        path = Path(self.import_source_var.get()).resolve()
        type(self).EDI_IMPORT_ORDERS_DIR = path
        return path

    def scan_orders(self) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            self.apply_import_source_dir()
            process_list = Path(self.process_list_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            self.ensure_workflow_folders(folder, process_list, output_dir)
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_background_activity("Scanning process lists and importing matching EDI order files...", maximum=5)
        worker = threading.Thread(
            target=self.worker_scan_orders,
            args=(folder, process_list, output_dir),
            daemon=True,
        )
        worker.start()

    def import_edi_orders(self) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            self.apply_import_source_dir()
            process_list = Path(self.process_list_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            self.ensure_workflow_folders(folder, process_list, output_dir)
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_background_activity("Importing matching EDI order files...", maximum=4)
        worker = threading.Thread(
            target=self.worker_import_edi_orders,
            args=(folder, process_list, output_dir),
            daemon=True,
        )
        worker.start()

    def start_background_activity(self, message: str, maximum: int | None = None) -> None:
        self.is_busy = True
        self.background_progress_percent = 0.0
        self.set_controls_enabled(False)
        self.progress.stop()
        if maximum:
            self.progress.configure(mode="determinate", maximum=100, value=0)
        else:
            self.progress.configure(mode="indeterminate", maximum=100, value=0)
            self.progress.start(12)
        self.status_var.set(message)

    def finish_background_activity(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.background_progress_percent = 0.0
        self.is_busy = False
        self.set_controls_enabled(True)

    def worker_scan_orders(self, folder: Path, process_list: Path, output_dir: Path) -> None:
        try:
            self.ensure_workflow_folders(folder, process_list, output_dir)
            progress_value = 0
            progress_max = 5
            self.queue_scan_progress(progress_value, progress_max, "Loading configuration...")
            config = self.config_with_manual_overrides(folder, output_dir)
            progress_value += 1
            self.queue_scan_progress(progress_value, progress_max, "Copying process lists into the local input folder...")

            def process_list_progress(done: int, total: int, source: Path, copied: bool) -> None:
                action = "Copied" if copied else "Checked"
                self.queue_scan_progress(
                    progress_value + done,
                    max(progress_max, progress_value + total + 4),
                    f"{action} process list {done}/{total}: {source.name}",
                )

            process_list_import_summary = self.copy_process_lists_from_import_folder(
                process_list,
                progress_callback=process_list_progress,
            )
            progress_value += int(process_list_import_summary.get("considered", 0) or 0)
            process_list_files = shower_batch.process_list_files(process_list)
            progress_value += 1
            self.queue_scan_progress(progress_value, max(progress_max, progress_value + 3), f"Reading {len(process_list_files)} process list file(s)...")
            orders = shower_batch.visible_orders(shower_batch.load_process_orders(process_list), config)

            def order_file_progress(done: int, total: int, source: Path, copied: bool) -> None:
                action = "Copied" if copied else "Checked"
                self.queue_scan_progress(
                    progress_value + done,
                    max(progress_max, progress_value + total + 2),
                    f"{action} order file {done}/{total}: {source.name}",
                )

            self.queue_scan_progress(progress_value, max(progress_max, progress_value + 2), f"Copying matching order PDFs/DXFs for {len(orders)} order(s)...")
            import_summary = self.copy_edi_orders_for_process_orders(
                folder,
                orders,
                progress_callback=order_file_progress,
            )
            orders, retired_sent_orders = self.filter_retired_sent_orders(orders, folder, output_dir)
            progress_value += int(import_summary.get("considered", 0) or 0)
            progress_value += 1
            self.queue_scan_progress(progress_value, max(progress_value + 1, progress_max), "Building order preview list...")
            previews = shower_batch.preview_orders(orders, folder)
            self.queue_scan_progress(progress_value + 1, progress_value + 1, f"Scan complete: {len(orders)} order(s).")
            self.worker_queue.put(
                (
                    "scan_done",
                    {
                        "orders": orders,
                        "previews": previews,
                        "process_list_count": len(process_list_files),
                        "process_list_import_summary": process_list_import_summary,
                        "import_summary": import_summary,
                        "retired_sent_orders": retired_sent_orders,
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("scan_error", str(exc)))

    def worker_import_edi_orders(self, folder: Path, process_list: Path, output_dir: Path) -> None:
        try:
            progress_value = 0
            progress_max = 4

            def process_list_progress(done: int, total: int, source: Path, copied: bool) -> None:
                action = "Copied" if copied else "Checked"
                self.queue_scan_progress(
                    progress_value + done,
                    max(progress_max, progress_value + total + 3),
                    f"{action} process list {done}/{total}: {source.name}",
                )

            self.queue_scan_progress(progress_value, progress_max, "Copying process lists into the local input folder...")
            process_list_import_summary = self.copy_process_lists_from_import_folder(
                process_list,
                progress_callback=process_list_progress,
            )
            progress_value += int(process_list_import_summary.get("considered", 0) or 0)
            if self.orders:
                orders = self.orders
                process_list_count = 0
            else:
                progress_value += 1
                self.queue_scan_progress(progress_value, max(progress_max, progress_value + 2), "Reading process lists...")
                config = self.config_with_manual_overrides(folder, output_dir)
                process_list_files = shower_batch.process_list_files(process_list)
                process_list_count = len(process_list_files)
                orders = shower_batch.visible_orders(shower_batch.load_process_orders(process_list), config)

            def order_file_progress(done: int, total: int, source: Path, copied: bool) -> None:
                action = "Copied" if copied else "Checked"
                self.queue_scan_progress(
                    progress_value + done,
                    max(progress_max, progress_value + total + 1),
                    f"{action} order file {done}/{total}: {source.name}",
                )

            self.queue_scan_progress(progress_value, max(progress_max, progress_value + 1), f"Copying matching order PDFs/DXFs for {len(orders)} order(s)...")
            import_summary = self.copy_edi_orders_for_process_orders(
                folder,
                orders,
                progress_callback=order_file_progress,
            )
            progress_value += int(import_summary.get("considered", 0) or 0)
            self.queue_scan_progress(progress_value + 1, progress_value + 1, "Import complete.")
            self.worker_queue.put(
                (
                    "import_done",
                    {
                        "orders": orders,
                        "process_list_count": process_list_count,
                        "process_list_import_summary": process_list_import_summary,
                        "import_summary": import_summary,
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("scan_error", str(exc)))

    def queue_scan_progress(self, value: int, maximum: int, message: str) -> None:
        self.worker_queue.put(
            (
                "scan_progress",
                {
                    "value": value,
                    "maximum": maximum,
                    "message": message,
                },
            )
        )

    def config_path(self, folder: Path) -> Path:
        return programmer.resolve_config_path(programmer.DEFAULT_CONFIG_NAME, folder)

    def config_with_manual_overrides(self, folder: Path, output_dir: Path) -> dict[str, object]:
        config = programmer.load_config(self.config_path(folder))
        manual = self.load_manual_overrides_for_output(output_dir)
        return programmer.merge_item_overrides(config, manual)

    def manual_overrides_path(self) -> Path:
        return Path(self.output_dir_var.get()).resolve() / "manual_overrides.json"

    def processing_history_path(self) -> Path:
        return Path(self.output_dir_var.get()).resolve() / "processing_history.json"

    @staticmethod
    def load_manual_overrides_for_output(output_dir: Path) -> dict[str, object]:
        path = output_dir / "manual_overrides.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}

    def load_manual_overrides(self) -> dict[str, object]:
        return self.load_manual_overrides_for_output(Path(self.output_dir_var.get()).resolve())

    def save_manual_overrides(self, data: dict[str, object]) -> None:
        path = self.manual_overrides_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    @staticmethod
    def load_processing_history_for_output(output_dir: Path) -> dict[str, object]:
        path = output_dir / "processing_history.json"
        if not path.exists():
            return {"orders": {}}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {"orders": {}}

    def load_processing_history(self) -> dict[str, object]:
        return self.load_processing_history_for_output(Path(self.output_dir_var.get()).resolve())

    def save_processing_history(self, data: dict[str, object]) -> None:
        path = self.processing_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    @staticmethod
    def sent_process_signature(order: shower_batch.ProcessOrder) -> str:
        payload = ShowerProgrammerApp.process_order_signature(order)
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def filter_retired_sent_orders(
        cls,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        output_dir: Path,
    ) -> tuple[list[shower_batch.ProcessOrder], list[str]]:
        try:
            history = cls.load_processing_history_for_output(output_dir)
        except Exception:
            return orders, []

        candidates: list[shower_batch.ProcessOrder] = []
        for order in orders:
            entry = cls.history_entry_from_data(history, order.aw_order)
            if not entry.get("sent_at"):
                continue
            if str(entry.get("sent_process_signature", "")) != cls.sent_process_signature(order):
                continue
            candidates.append(order)
        if not candidates:
            return orders, []

        root_inputs = (
            [
                path
                for path in order_folder.iterdir()
                if path.is_file() and path.suffix.lower() in cls.ORDER_FILE_EXTENSIONS
            ]
            if order_folder.exists()
            else []
        )
        fresh_aw_orders: set[str] = set()
        for order in candidates:
            name_matches = cls.paths_matching_order_by_name(root_inputs, order)
            content_matches = cls.matching_order_files(
                order_folder,
                [order],
                root_only=True,
                inspect_pdf_text=True,
            )
            if name_matches or content_matches:
                fresh_aw_orders.add(str(order.aw_order))
        retired_aw_orders = {
            str(order.aw_order)
            for order in candidates
            if str(order.aw_order) not in fresh_aw_orders
        }
        kept = [order for order in orders if str(order.aw_order) not in retired_aw_orders]
        return kept, sorted(retired_aw_orders)

    def mark_orders_sent(
        self,
        orders_sent: list[shower_batch.ProcessOrder],
        copied: list[Path],
        archived: list[Path],
    ) -> None:
        if not orders_sent:
            return
        history = self.load_processing_history()
        history_orders = history.setdefault("orders", {})
        if not isinstance(history_orders, dict):
            history_orders = {}
            history["orders"] = history_orders
        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for order in orders_sent:
            entry = history_orders.setdefault(str(order.aw_order), {})
            if not isinstance(entry, dict):
                entry = {}
                history_orders[str(order.aw_order)] = entry
            entry["sent_at"] = sent_at
            entry["sent_process_signature"] = self.sent_process_signature(order)
            entry["sent_files"] = [path.name for path in copied if path in self.paths_for_order(copied, order.aw_order)]
            entry["archived_inputs"] = [path.name for path in self.paths_matching_order_by_name(archived, order)]
        self.save_processing_history(history)

    def history_for_order(self, aw_order: str) -> dict[str, object]:
        try:
            data = self.load_processing_history()
        except Exception:
            return {}
        return self.history_entry_from_data(data, aw_order)

    @staticmethod
    def history_entry_from_data(data: dict[str, object], aw_order: str) -> dict[str, object]:
        orders = data.get("orders", {})
        if not isinstance(orders, dict):
            return {}
        entry = orders.get(str(aw_order), {})
        return entry if isinstance(entry, dict) else {}

    def history_for_order_from_output(self, aw_order: str, output_dir: Path) -> dict[str, object]:
        try:
            data = self.load_processing_history_for_output(output_dir)
        except Exception:
            return {}
        return self.history_entry_from_data(data, aw_order)

    def clear_remake_history_for_orders(self, aw_orders: list[str]) -> None:
        if not aw_orders:
            return
        try:
            history = self.load_processing_history()
        except Exception:
            return
        orders = history.get("orders", {})
        if not isinstance(orders, dict):
            return
        changed = False
        for aw_order in aw_orders:
            entry = orders.get(str(aw_order))
            if isinstance(entry, dict) and "remake_items" in entry:
                entry.pop("remake_items", None)
                changed = True
        if changed:
            self.save_processing_history(history)

    def insert_or_update_result(self, result: shower_batch.BatchJobResult) -> None:
        processed, last_processed = self.processed_summary_for_order(result.aw_order)
        values = (
            result.status,
            processed,
            last_processed,
            result.delivery_date,
            result.aw_order,
            result.job_name,
            result.customer,
            result.items,
            self.review_status_for_order(result.aw_order),
            result.input_pdf.name if result.input_pdf else "",
            self.issue_summary(result.issues),
        )
        row_id = self.tree_rows.get(result.aw_order)
        tag = result.status if result.status in {"OK", "READY", "ISSUES", "FAILED", "SKIPPED"} else ""
        if row_id:
            self.tree.item(row_id, values=values, tags=(tag,))
        else:
            row_id = self.tree.insert("", tk.END, values=values, tags=(tag,))
            self.tree_rows[result.aw_order] = row_id
        self.update_summary_strip()

    def update_summary_strip(self) -> None:
        total = 0
        ready = 0
        issues = 0
        processed = 0
        checked = 0
        for row_id in self.tree.get_children():
            values = self.tree.item(row_id, "values")
            if len(values) < 9:
                continue
            total += 1
            status = str(values[0]).upper()
            if status in {"READY", "OK"}:
                ready += 1
            elif status in {"ISSUES", "FAILED"}:
                issues += 1
            if str(values[1]).lower() in {"yes", "remake"}:
                processed += 1
            if "checked" in str(values[8]).lower():
                checked += 1
        self.summary_var.set(
            f"Orders {total}   Ready {ready}   Issues {issues}   Processed {processed}   Checked {checked}"
        )
        self.summary_count_vars["orders"].set(str(total))
        self.summary_count_vars["ready"].set(str(ready))
        self.summary_count_vars["issues"].set(str(issues))
        self.summary_count_vars["processed"].set(str(processed))
        self.summary_count_vars["checked"].set(str(checked))

    @staticmethod
    def issue_summary(issues: list[str]) -> str:
        if not issues:
            return ""
        concise = [ShowerProgrammerApp.concise_issue_text(issue) for issue in issues]
        visible = concise[:3]
        text = "; ".join(visible)
        if len(concise) > len(visible):
            text += f"; +{len(concise) - len(visible)} more"
        return text

    @staticmethod
    def concise_issue_text(issue: str) -> str:
        text = re.sub(r"\s+", " ", issue).strip()
        replacements = [
            (r"^Process list item\(s\) missing from PDF: ", "Missing sketch: "),
            (r"^Missing sketch page: ", "Missing sketch: "),
            (r"^Notice: PDF piece\(s\) not in process list; crossed out/not programmed \(possible REMAKE\): ", "Crossed out: "),
            (r"^Sketch page not in list; crossed out: ", "Crossed out: "),
            (r"^P(\d+): No matching process-list item row found\.$", r"P\1: no process row"),
            (r"^P(\d+): no process-list row$", r"P\1: no process row"),
            (r"^P(\d+): missing source DXF$", r"P\1: missing DXF"),
            (r"^P(\d+): Label placed in best available open area inside glass\.$", r"P\1: label placed inside"),
            (r"^P(\d+): label placed inside best open area$", r"P\1: label placed inside"),
            (r"^P(\d+): FP-S cut-in/cut-out detected; manual DXF review required\.$", r"P\1: FP-S cut; review DXF"),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        return text

    def processed_summary_for_order(self, aw_order: str) -> tuple[str, str]:
        history = self.history_for_order(aw_order)
        last_processed = str(history.get("last_processed", ""))
        if last_processed:
            return ("REMAKE" if self.history_has_remake(history) else "Yes"), last_processed
        output_dir = Path(self.output_dir_var.get()).resolve()
        sketch_path = self.find_order_sketch_path(aw_order, output_dir)
        if sketch_path.exists():
            return "Yes", datetime.fromtimestamp(sketch_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return "No", ""

    @staticmethod
    def history_has_remake(history: dict[str, object]) -> bool:
        return isinstance(history.get("remake_items"), list)

    def remake_badge_for_order(self, aw_order: str) -> str:
        history = self.history_for_order(aw_order)
        value = history.get("remake_items")
        if not isinstance(value, list):
            return ""
        items = sorted(int(item) for item in value if str(item).strip().isdigit())
        return "REMAKE" if not items else "REMAKE " + ",".join(f"P{item}" for item in items)

    def output_dirs_for_run(self, run_folder: Path) -> tuple[Path, Path, Path]:
        return run_folder / "Sketches", run_folder / "Programs", run_folder / "Reports"

    def run_folder_for_order(self, aw_order: str, output_dir: Path) -> Path | None:
        history = self.history_for_order_from_output(aw_order, output_dir)
        run_value = str(history.get("run_folder", "")).strip()
        if run_value:
            run_folder = Path(run_value)
            if not run_folder.is_absolute():
                run_folder = output_dir / run_folder
            if run_folder.exists() and (run_folder / "Sketches" / f"{aw_order}.pdf").exists():
                return run_folder
        runs_dir = output_dir / "Runs"
        if runs_dir.exists():
            run_folders = sorted(
                self.output_search_roots(output_dir),
                key=lambda path: path.stat().st_mtime if path.exists() else 0,
                reverse=True,
            )
            for run_folder in run_folders:
                if run_folder == output_dir:
                    continue
                if (run_folder / "Sketches" / f"{aw_order}.pdf").exists():
                    return run_folder
        return None

    def output_dirs_for_order(self, aw_order: str, output_dir: Path) -> tuple[Path | None, Path, Path, Path]:
        run_folder = self.run_folder_for_order(aw_order, output_dir)
        if run_folder is not None:
            sketch_dir, programs_dir, report_dir = self.output_dirs_for_run(run_folder)
            return run_folder, sketch_dir, programs_dir, report_dir
        return None, output_dir / "Sketches", output_dir / "Programs", output_dir / "Reports"

    def find_order_sketch_path(self, aw_order: str, output_dir: Path) -> Path:
        _run_folder, sketch_dir, _programs_dir, _report_dir = self.output_dirs_for_order(aw_order, output_dir)
        path = sketch_dir / f"{aw_order}.pdf"
        if path.exists():
            return path
        return output_dir / "Sketches" / f"{aw_order}.pdf"

    @staticmethod
    def file_signature(path: Path | None) -> tuple[str, int, int]:
        if path is None:
            return ("", 0, 0)
        try:
            resolved = str(path.resolve())
            stat = path.stat()
            return (resolved, stat.st_mtime_ns, stat.st_size)
        except OSError:
            return (str(path), 0, 0)

    @classmethod
    def review_raster_cache_key(cls, pdf_path: Path, dpi: int) -> str:
        signature = cls.file_signature(pdf_path)
        raw = "|".join(str(part) for part in (*signature, dpi))
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]

    @classmethod
    def review_raster_cache_dir(cls, output_dir: Path, pdf_path: Path, dpi: int) -> Path:
        return output_dir / ".review_preview_cache" / cls.review_raster_cache_key(pdf_path, dpi)

    @classmethod
    def review_raster_page_path(cls, output_dir: Path, pdf_path: Path, dpi: int, page_index: int) -> Path:
        return cls.review_raster_cache_dir(output_dir, pdf_path, dpi) / f"page_{page_index + 1:03d}.png"

    @staticmethod
    def close_pdfium_object(obj: Any) -> None:
        close = getattr(obj, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    def render_pdfium_page_to_file(
        self,
        document: Any,
        page_index: int,
        output_path: Path,
        dpi: int,
    ) -> bool:
        if pdfium is None or Image is None:
            return False
        page = None
        bitmap = None
        temp_path = output_path.with_name(f"{output_path.stem}.{threading.get_ident()}.tmp{output_path.suffix}")
        try:
            page = document[page_index]
            bitmap = page.render(scale=max(0.1, dpi / 72.0))
            image = bitmap.to_pil().convert("RGB")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(temp_path, format="PNG")
            temp_path.replace(output_path)
            return True
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False
        finally:
            self.close_pdfium_object(bitmap)
            self.close_pdfium_object(page)

    def render_pdfium_single_page_to_file(
        self,
        pdf_path: Path,
        page_index: int,
        output_path: Path,
        dpi: int,
    ) -> bool:
        if pdfium is None:
            return False
        document = None
        try:
            document = pdfium.PdfDocument(str(pdf_path))
            if page_index < 0 or page_index >= len(document):
                return False
            return self.render_pdfium_page_to_file(document, page_index, output_path, dpi)
        except Exception:
            return False
        finally:
            self.close_pdfium_object(document)

    def render_pdfium_pages_to_cache(
        self,
        pdf_path: Path,
        expected_paths: list[Path],
        dpi: int,
    ) -> bool:
        if pdfium is None:
            return False
        document = None
        try:
            document = pdfium.PdfDocument(str(pdf_path))
            page_total = min(len(document), len(expected_paths))
            if page_total <= 0:
                return False
            for page_index in range(page_total):
                output_path = expected_paths[page_index]
                if output_path.exists():
                    continue
                if not self.render_pdfium_page_to_file(document, page_index, output_path, dpi):
                    return False
            return all(path.exists() for path in expected_paths[:page_total])
        except Exception:
            return False
        finally:
            self.close_pdfium_object(document)

    def ensure_review_pdf_raster_cache(
        self,
        pdf_path: Path,
        page_count: int,
        output_dir: Path,
        dpi: int | None = None,
    ) -> bool:
        render_dpi = int(dpi or self.REVIEW_RENDER_DPI)
        if page_count <= 0:
            return False
        cache_dir = self.review_raster_cache_dir(output_dir, pdf_path, render_dpi)
        expected = [cache_dir / f"page_{page_index + 1:03d}.png" for page_index in range(page_count)]
        if expected and all(path.exists() for path in expected):
            return True
        if self.render_pdfium_pages_to_cache(pdf_path, expected, render_dpi):
            return True
        ghostscript = self.ghostscript_executable()
        if ghostscript is None:
            return False
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = cache_dir / "page_%03d.png"
        command = [
            str(ghostscript),
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=png16m",
            f"-r{render_dpi}",
            "-dFirstPage=1",
            f"-dLastPage={page_count}",
            f"-sOutputFile={output_pattern}",
            str(pdf_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=max(30, page_count * 12))
        except Exception:
            return False
        return all(path.exists() for path in expected)

    def start_async_review_raster_render(
        self,
        pdf_path: Path,
        page_count: int,
        output_dir: Path,
        state: dict[str, Any],
        redraw_callback: Callable[[], object] | None = None,
    ) -> None:
        render_dpi = self.REVIEW_RENDER_DPI
        cache_key = (str(pdf_path.resolve()), self.file_signature(pdf_path), page_count, render_dpi)
        rendering = state.setdefault("raster_rendering", set())
        if cache_key in rendering:
            return
        rendering.add(cache_key)

        root = state.get("render_root")

        def worker() -> None:
            ok = self.ensure_review_pdf_raster_cache(pdf_path, page_count, output_dir, render_dpi)

            def finish() -> None:
                state.setdefault("raster_rendering", set()).discard(cache_key)
                if ok and redraw_callback is not None:
                    try:
                        redraw_callback()
                    except tk.TclError:
                        pass

            try:
                if root is not None:
                    root.after(0, finish)
                else:
                    finish()
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def process_order_signature(order: shower_batch.ProcessOrder) -> tuple[object, ...]:
        items: list[tuple[object, ...]] = []
        for item_number in order.item_numbers:
            item = order.items[item_number]
            items.append(
                (
                    item_number,
                    item.width_text,
                    item.height_text,
                    item.delivery_date,
                    item.customer,
                    tuple(item.processing),
                    tuple(item.machine_hints),
                )
            )
        return (order.aw_order, order.job_name, order.customer, tuple(items))

    def review_context_cache_key(
        self,
        order: shower_batch.ProcessOrder,
        folder: Path,
        output_dir: Path,
        sketch_path: Path,
    ) -> tuple[object, ...]:
        return (
            str(folder.resolve()),
            str(output_dir.resolve()),
            self.process_order_signature(order),
            self.file_signature(sketch_path),
            self.file_signature(output_dir / "manual_overrides.json"),
        )

    def clear_review_context_cache(self, aw_order: str | None = None) -> None:
        with self.review_context_cache_lock:
            if aw_order is None:
                self.review_context_cache.clear()
            else:
                self.review_context_cache.pop(str(aw_order), None)
            self.review_cache_generation += 1

    def prepare_order_review_context(
        self,
        process_order: shower_batch.ProcessOrder,
        folder: Path,
        output_dir: Path,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        run_folder, sketch_dir, programs_dir, report_dir = self.output_dirs_for_order(process_order.aw_order, output_dir)
        sketch_path = sketch_dir / f"{process_order.aw_order}.pdf"
        if not sketch_path.exists():
            raise FileNotFoundError("Process this order first so the marked sketch exists.")

        cache_key = self.review_context_cache_key(process_order, folder, output_dir, sketch_path)
        if use_cache:
            with self.review_context_cache_lock:
                cached = self.review_context_cache.get(process_order.aw_order)
            if cached and cached.get("cache_key") == cache_key:
                source_path = cached.get("source_pdf_path")
                if not isinstance(source_path, Path) or self.file_signature(source_path) == cached.get("source_pdf_signature"):
                    return cached

        config = self.config_with_manual_overrides(folder, output_dir)
        job, source_reader, issues = shower_batch.prepare_job(
            folder,
            sketch_dir,
            programs_dir,
            report_dir,
            config,
            process_order,
            remake_items=self.editor_remake_items(process_order.aw_order, output_dir),
        )
        sketch_reader = PdfReader(str(sketch_path))
        context = {
            "cache_key": cache_key,
            "folder": folder,
            "output_dir": output_dir,
            "run_folder": run_folder,
            "sketch_dir": sketch_dir,
            "programs_dir": programs_dir,
            "report_dir": report_dir,
            "sketch_path": sketch_path,
            "config": config,
            "job": job,
            "source_reader": source_reader,
            "issues": issues,
            "sketch_reader": sketch_reader,
            "source_pdf_path": job.pdf_path,
            "source_pdf_signature": self.file_signature(job.pdf_path),
        }
        with self.review_context_cache_lock:
            if len(self.review_context_cache) > 30:
                self.review_context_cache.clear()
            self.review_context_cache[process_order.aw_order] = context
        return context

    def start_review_cache_warmup(self, orders: list[shower_batch.ProcessOrder] | None = None) -> None:
        if self.review_cache_worker_active:
            return
        orders_to_warm = list(orders if orders is not None else self.orders)
        if not orders_to_warm:
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
        except Exception:
            return
        with self.review_context_cache_lock:
            self.review_cache_generation += 1
            generation = self.review_cache_generation
        self.review_cache_worker_active = True
        worker = threading.Thread(
            target=self.worker_warm_review_cache,
            args=(orders_to_warm, folder, output_dir, generation),
            daemon=True,
        )
        worker.start()

    def worker_warm_review_cache(
        self,
        orders: list[shower_batch.ProcessOrder],
        folder: Path,
        output_dir: Path,
        generation: int,
    ) -> None:
        try:
            for order in orders:
                with self.review_context_cache_lock:
                    if generation != self.review_cache_generation:
                        return
                try:
                    context = self.prepare_order_review_context(order, folder, output_dir, use_cache=True)
                    job = context.get("job")
                    source_reader = context.get("source_reader")
                    if isinstance(job, programmer.Job) and isinstance(source_reader, PdfReader):
                        self.ensure_review_pdf_raster_cache(job.pdf_path, len(source_reader.pages), output_dir)
                except Exception:
                    continue
        finally:
            self.review_cache_worker_active = False

    def review_status_for_order(self, aw_order: str) -> str:
        try:
            data = self.load_manual_overrides()
        except Exception:
            return ""
        item_overrides = data.get("item_overrides", {})
        if not isinstance(item_overrides, dict):
            return ""
        order_overrides = item_overrides.get(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            return ""
        if bool(order_overrides.get("_order_checked")):
            return "Order checked"
        checked: list[str] = []
        for key, value in order_overrides.items():
            if not str(key).isdigit() or not isinstance(value, dict):
                continue
            if bool(value.get("checked")):
                checked.append(f"P{int(key)} checked")
        return ", ".join(sorted(checked, key=lambda text: int(text.split()[0][1:])))

    def order_review_is_complete(self, order: shower_batch.ProcessOrder) -> bool:
        try:
            data = self.load_manual_overrides()
        except Exception:
            return False
        item_overrides = data.get("item_overrides", {})
        if not isinstance(item_overrides, dict):
            return False
        order_overrides = item_overrides.get(str(order.aw_order), {})
        if not isinstance(order_overrides, dict):
            return False
        if bool(order_overrides.get("_order_checked")):
            return True
        item_numbers = set(getattr(order, "item_numbers", set()) or set())
        if not item_numbers:
            return False
        for item in item_numbers:
            item_override = order_overrides.get(str(item), {})
            if not isinstance(item_override, dict) or not bool(item_override.get("checked")):
                return False
        return True

    def tree_values_for_order(self, aw_order: str) -> tuple[str, ...]:
        row_id = self.tree_rows.get(aw_order)
        if not row_id:
            return ()
        values = self.tree.item(row_id, "values")
        return tuple(str(value) for value in values)

    def tree_issue_text_for_order(self, aw_order: str) -> str:
        values = self.tree_values_for_order(aw_order)
        return values[10] if len(values) > 10 else ""

    def mark_selected_orders_checked(self) -> None:
        orders = self.selected_orders()
        if not orders:
            messagebox.showinfo("No selection", "Select one or more orders first.")
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        for order in orders:
            order_overrides = item_overrides.setdefault(order.aw_order, {})
            if not isinstance(order_overrides, dict):
                order_overrides = {}
                item_overrides[order.aw_order] = order_overrides
            order_overrides["_order_checked"] = True
            row_id = self.tree_rows.get(order.aw_order)
            if row_id:
                values = list(self.tree.item(row_id, "values"))
                if len(values) >= 9:
                    values[8] = "Order checked"
                    self.tree.item(row_id, values=values)
        self.save_manual_overrides(data)
        self.update_summary_strip()
        self.status_var.set(f"Marked {len(orders)} order(s) checked.")

    def order_for_tree_row(self, row_id: str) -> shower_batch.ProcessOrder | None:
        if not row_id:
            return None
        try:
            values = self.tree.item(row_id, "values")
        except tk.TclError:
            return None
        if len(values) < 5:
            return None
        return self.order_by_aw.get(str(values[4]))

    def open_orders_context_menu(self, event: tk.Event) -> str:
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            self.close_active_themed_context_menu()
            return "break"

        if row_id not in self.tree.selection():
            self.tree.selection_set(row_id)
            self.tree.focus(row_id)
        order = self.order_for_tree_row(row_id)
        if order is None:
            return "break"

        selected_count = len(self.selected_orders())
        title = "Order Actions"
        subtitle = f"{selected_count} selected order(s)" if selected_count > 1 else f"{order.aw_order}  {order.job_name}"
        actions = [
            {
                "text": "Delete Local Input Files",
                "icon": "trash",
                "destructive": True,
                "command": self.delete_selected_local_order_inputs,
            },
        ]
        self.show_themed_context_menu(self.root, event.x_root, event.y_root, title, subtitle, actions)
        return "break"

    def delete_selected_local_order_inputs(self) -> None:
        orders = self.selected_orders()
        if not orders:
            messagebox.showinfo("No selection", "Select one or more orders first.")
            return
        try:
            local_order_folder = Path(self.folder_var.get()).resolve()
        except Exception as exc:
            messagebox.showerror("Invalid order folder", str(exc))
            return

        files = self.matching_order_files(
            local_order_folder,
            orders,
            root_only=True,
            inspect_pdf_text=True,
        )
        order_names = ", ".join(order.aw_order for order in orders[:8])
        if len(orders) > 8:
            order_names += f", +{len(orders) - 8} more"
        if files:
            file_preview = "\n".join(path.name for path in files[:12])
            if len(files) > 12:
                file_preview += f"\n...and {len(files) - 12} more"
            message = (
                "Delete the local copied order PDF/DXF files for these order(s)?\n\n"
                f"Orders: {order_names}\n\n"
                f"Local folder only:\n{local_order_folder}\n\n"
                f"Files to delete:\n{file_preview}\n\n"
                "This will not delete anything from the shared Showers Programmer Input folder."
            )
        else:
            message = (
                "No matching local PDF/DXF files were found for the selected order(s).\n\n"
                f"Orders: {order_names}\n\n"
                "Remove the selected order(s) from the current orders list anyway?"
            )
        if not messagebox.askyesno("Delete local order input", message):
            return

        deleted: list[Path] = []
        warnings: list[str] = []
        local_root = local_order_folder.resolve()
        for path in files:
            try:
                resolved = path.resolve()
                if resolved.parent != local_root:
                    warnings.append(f"Skipped outside local order folder: {path.name}")
                    continue
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                warnings.append(f"Could not delete {path.name}: {exc}")

        deleted_aw_orders = {order.aw_order for order in orders}
        for aw_order in deleted_aw_orders:
            row_id = self.tree_rows.pop(aw_order, None)
            if row_id:
                try:
                    self.tree.delete(row_id)
                except tk.TclError:
                    pass
            self.order_by_aw.pop(aw_order, None)
        self.orders = [order for order in self.orders if order.aw_order not in deleted_aw_orders]
        self.update_summary_strip()

        detail = f"Deleted {len(deleted)} local file(s) and removed {len(deleted_aw_orders)} order(s) from the list."
        if warnings:
            detail += "\n\n" + "\n".join(warnings[:8])
            if len(warnings) > 8:
                detail += f"\n...and {len(warnings) - 8} more"
        self.status_var.set(detail.split("\n", 1)[0])
        messagebox.showinfo("Local order input deleted", detail)

    def selected_orders(self) -> list[shower_batch.ProcessOrder]:
        selected = []
        for row_id in self.tree.selection():
            values = self.tree.item(row_id, "values")
            if len(values) >= 5:
                order = self.order_by_aw.get(values[4])
                if order:
                    selected.append(order)
        return selected

    def select_all_orders(self, _event: tk.Event | None = None) -> str | None:
        row_ids = self.tree.get_children()
        if not row_ids:
            self.status_var.set("No scanned orders to select.")
            return "break" if _event is not None else None
        self.tree.selection_set(*row_ids)
        self.tree.focus(row_ids[0])
        self.tree.see(row_ids[0])
        self.status_var.set(f"Selected {len(row_ids)} order(s).")
        return "break" if _event is not None else None

    def selected_or_visible_aw_orders(self) -> list[str]:
        selected = [order.aw_order for order in self.selected_orders()]
        if selected:
            return selected
        aw_orders: list[str] = []
        for row_id in self.tree.get_children():
            values = self.tree.item(row_id, "values")
            if len(values) >= 5 and values[4]:
                aw_orders.append(str(values[4]))
        return aw_orders

    def process_selected(self) -> None:
        orders = self.selected_orders()
        if not orders:
            messagebox.showinfo("No selection", "Select one or more orders first.")
            return
        remake_items_by_order = None
        if self.remake_var.get():
            self.remake_items_var.set("")
            remake_items_by_order = {order.aw_order: set() for order in orders}
        self.run_orders(
            orders,
            apply=True,
            remake_items_by_order=remake_items_by_order,
            force_override=True if remake_items_by_order is not None else None,
        )

    def process_all_orders(self) -> None:
        orders = list(self.orders)
        if not orders:
            messagebox.showinfo("No orders", "Scan the process list first.")
            return
        remake_items_by_order = None
        if self.remake_var.get():
            self.remake_items_var.set("")
            remake_items_by_order = {order.aw_order: set() for order in orders}
        self.run_orders(
            orders,
            apply=True,
            remake_items_by_order=remake_items_by_order,
            force_override=True if remake_items_by_order is not None else None,
        )

    def run_orders(
        self,
        orders: list[shower_batch.ProcessOrder],
        apply: bool,
        remake_items_by_order: dict[str, set[int]] | None = None,
        force_override: bool | None = None,
        skip_dxf_override: bool | None = None,
    ) -> None:
        if self.is_busy:
            messagebox.showinfo("Batch running", "A batch is already running.")
            return
        if not orders:
            messagebox.showinfo("No orders", "Scan the process list first.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            process_list_path = Path(self.process_list_var.get()).resolve()
            force = self.force_var.get() if force_override is None else force_override
            skip_dxf = self.skip_dxf_var.get() if skip_dxf_override is None else skip_dxf_override
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        if remake_items_by_order is None:
            self.clear_remake_history_for_orders([order.aw_order for order in orders])
        if apply and not force:
            conflicts = self.existing_output_conflicts(orders, output_dir, skip_dxf)
            if conflicts:
                preview = "\n".join(conflicts[:8])
                if len(conflicts) > 8:
                    preview += f"\n...and {len(conflicts) - 8} more"
                if not messagebox.askyesno(
                    "Existing outputs found",
                    "Some selected outputs already exist:\n\n"
                    f"{preview}\n\nOverwrite only the selected order files in the dated batch folder?",
                ):
                    return
                force = True

        self.is_busy = True
        self.set_controls_enabled(False)
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=len(orders), value=0)
        self.status_var.set(("Processing" if apply else "Dry running") + f" {len(orders)} order(s)...")

        worker = threading.Thread(
            target=self.worker_run_batch,
            args=(orders, apply, folder, output_dir, process_list_path, force, skip_dxf, remake_items_by_order),
            daemon=True,
        )
        worker.start()

    def existing_output_conflicts(
        self,
        orders: list[shower_batch.ProcessOrder],
        output_dir: Path,
        skip_dxf: bool,
    ) -> list[str]:
        conflicts: list[str] = []
        for order in orders:
            for root in self.output_search_roots(output_dir):
                sketch = root / "Sketches" / f"{order.aw_order}.pdf"
                if sketch.exists():
                    conflicts.append(str(sketch.relative_to(output_dir)))
                programs_dir = root / "Programs"
                if not skip_dxf and programs_dir.exists():
                    for path in sorted(programs_dir.glob(f"{order.aw_order}*.dxf")):
                        conflicts.append(str(path.relative_to(output_dir)))
        return conflicts

    def worker_run_batch(
        self,
        orders: list[shower_batch.ProcessOrder],
        apply: bool,
        folder: Path,
        output_dir: Path,
        process_list_path: Path,
        force: bool,
        skip_dxf: bool,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        try:
            run_folder = self.next_batch_run_folder(output_dir, process_list_path) if apply else output_dir / "Reviews" / "DryRun"
            sketch_dir, programs_dir, report_dir = self.output_dirs_for_run(run_folder)
            if apply and force:
                self.clear_existing_outputs_for_orders(orders, output_dir, skip_dxf)
            config = self.config_with_manual_overrides(folder, output_dir)
            run = shower_batch.run_batch(
                orders=orders,
                folder=folder,
                sketch_output_dir=sketch_dir,
                dxf_output_dir=programs_dir,
                report_dir=report_dir,
                config=config,
                apply=apply,
                force=force,
                skip_pdf=False,
                skip_dxf=skip_dxf,
                remake_items_by_order=remake_items_by_order,
                progress=lambda result: self.worker_queue.put(("result", result)),
            )
            if apply:
                processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.write_run_manifest(run, run_folder, sketch_dir, programs_dir, report_dir, processed_at, remake_items_by_order)
                self.update_processing_history(run, output_dir, processed_at, run_folder, remake_items_by_order)
            self.worker_queue.put(("done", (run, run_folder)))
        except Exception as exc:
            self.worker_queue.put(("error", str(exc)))

    def write_run_manifest(
        self,
        run: shower_batch.BatchRunResult,
        run_folder: Path,
        sketch_dir: Path,
        programs_dir: Path,
        report_dir: Path,
        processed_at: str,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        run_folder.mkdir(parents=True, exist_ok=True)
        manifest = {
            "created": processed_at,
            "sketches": str(sketch_dir),
            "programs": str(programs_dir),
            "reports": str(report_dir),
            "remake_items_by_order": {
                order: sorted(items) for order, items in (remake_items_by_order or {}).items()
            },
        }
        with (run_folder / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

    @staticmethod
    def clear_existing_outputs_for_orders(
        orders: list[shower_batch.ProcessOrder],
        output_dir: Path,
        skip_dxf: bool,
    ) -> int:
        removed = 0
        for order in orders:
            candidates: list[Path] = []
            for root in ShowerProgrammerApp.output_search_roots(output_dir):
                candidates.extend(
                    [
                        root / "Sketches" / f"{order.aw_order}.pdf",
                        root / "Reports" / f"{order.aw_order}_programming_report.txt",
                    ]
                )
                programs_dir = root / "Programs"
                if not skip_dxf and programs_dir.exists():
                    candidates.extend(sorted(programs_dir.glob(f"{order.aw_order}*.dxf")))
            for path in candidates:
                if not path.exists() or not path.is_file():
                    continue
                if not path.resolve().is_relative_to(output_dir.resolve()):
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    @staticmethod
    def output_search_roots(output_dir: Path) -> list[Path]:
        roots = [output_dir]
        runs_dir = output_dir / "Runs"
        if not runs_dir.exists():
            return roots
        for path in runs_dir.rglob("*"):
            if not path.is_dir():
                continue
            if (path / "Sketches").exists() or (path / "Programs").exists() or (path / "Reports").exists() or (path / "manifest.json").exists():
                roots.append(path)
        return roots

    @staticmethod
    def next_indexed_run_folder(output_dir: Path) -> Path:
        runs_dir = output_dir / "Runs" / ShowerProgrammerApp.dated_archive_folder_name()
        runs_dir.mkdir(parents=True, exist_ok=True)
        indexes = [
            int(path.name)
            for path in runs_dir.iterdir()
            if path.is_dir() and path.name.isdigit()
        ]
        return runs_dir / str((max(indexes) if indexes else 0) + 1)

    def next_batch_run_folder(self, output_dir: Path, process_list_path: Path) -> Path:
        runs_dir = output_dir / "Runs" / self.dated_archive_folder_name()
        runs_dir.mkdir(parents=True, exist_ok=True)
        label = self.process_list_run_label(process_list_path)
        if not label:
            return self.next_indexed_run_folder(output_dir)
        return runs_dir / label

    @staticmethod
    def process_list_run_label(process_list_path: Path) -> str:
        try:
            files = shower_batch.process_list_files(process_list_path)
        except Exception:
            files = [process_list_path] if process_list_path.is_file() else []
        stems = [path.stem for path in files if path.name and not path.name.startswith("~$")]
        if not stems:
            return ""
        raw = stems[0] if len(stems) == 1 else f"{stems[0]}_plus{len(stems) - 1}"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")[:80]

    def update_processing_history(
        self,
        run: shower_batch.BatchRunResult,
        output_dir: Path,
        processed_at: str,
        run_folder: Path,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        history = self.load_processing_history()
        orders = history.setdefault("orders", {})
        if not isinstance(orders, dict):
            orders = {}
            history["orders"] = orders
        for result in run.results:
            if result.status not in {"OK", "ISSUES"}:
                continue
            entry = orders.setdefault(result.aw_order, {})
            if not isinstance(entry, dict):
                entry = {}
                orders[result.aw_order] = entry
            entry["last_processed"] = processed_at
            entry["delivery_date"] = result.delivery_date
            entry["status"] = result.status
            entry["run_folder"] = str(run_folder)
            entry["output_pdf"] = str(result.output_pdf or "")
            entry["report_path"] = str(result.report_path or "")
            if remake_items_by_order and result.aw_order in remake_items_by_order:
                entry["remake_items"] = sorted(remake_items_by_order[result.aw_order])
            else:
                entry.pop("remake_items", None)
        self.save_processing_history(history)

    def latest_run_folder(self, output_dir: Path) -> Path | None:
        runs = [path for path in self.output_search_roots(output_dir) if path != output_dir]
        return max(runs, key=lambda path: path.stat().st_mtime) if runs else None

    def drain_worker_queue(self) -> None:
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "result":
                    result = payload
                    assert isinstance(result, shower_batch.BatchJobResult)
                    self.insert_or_update_result(result)
                    self.progress.step(1)
                    self.status_var.set(f"{result.status}: {result.aw_order} {result.job_name}")
                elif kind == "scan_progress":
                    data = payload
                    assert isinstance(data, dict)
                    maximum = int(data.get("maximum", 100) or 100)
                    value = int(data.get("value", 0) or 0)
                    message = str(data.get("message", "Scanning..."))
                    percent = 100.0 if value >= maximum else max(0.0, min(99.0, (value / max(maximum, 1)) * 100.0))
                    if percent < self.background_progress_percent:
                        percent = self.background_progress_percent
                    else:
                        self.background_progress_percent = percent
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=100, value=percent)
                    self.status_var.set(message)
                    if self.send_review_progress is not None:
                        try:
                            self.send_review_progress.configure(mode="determinate", maximum=100, value=percent)
                        except tk.TclError:
                            self.send_review_progress = None
                    if self.send_review_status_var is not None:
                        self.send_review_status_var.set(message)
                elif kind == "done":
                    run, run_folder = payload
                    assert isinstance(run, shower_batch.BatchRunResult)
                    self.last_reports = run
                    self.last_run_folder = run_folder if isinstance(run_folder, Path) else self.latest_run_folder(Path(self.output_dir_var.get()).resolve())
                    self.is_busy = False
                    self.set_controls_enabled(True)
                    for result in run.results:
                        self.insert_or_update_result(result)
                    counts = shower_batch.count_statuses(run.results)
                    self.status_var.set("Done. " + ", ".join(f"{k}={v}" for k, v in counts.items()))
                    self.clear_review_context_cache()
                    self.start_review_cache_warmup(self.orders)
                    messagebox.showinfo("Batch complete", "Processing complete.")
                elif kind == "error":
                    self.finish_background_activity()
                    self.status_var.set("Error")
                    messagebox.showerror("Batch failed", str(payload))
                elif kind == "scan_done":
                    data = payload
                    assert isinstance(data, dict)
                    orders = data.get("orders", [])
                    previews = data.get("previews", [])
                    process_list_count = int(data.get("process_list_count", 0))
                    process_list_import_summary = data.get("process_list_import_summary", {})
                    import_summary = data.get("import_summary", {})
                    retired_sent_orders = data.get("retired_sent_orders", [])
                    assert isinstance(orders, list)
                    assert isinstance(previews, list)
                    assert isinstance(retired_sent_orders, list)
                    self.orders = orders
                    self.order_by_aw = {order.aw_order: order for order in self.orders}
                    self.tree.delete(*self.tree.get_children())
                    self.tree_rows.clear()
                    self.update_summary_strip()
                    for result in previews:
                        assert isinstance(result, shower_batch.BatchJobResult)
                        self.insert_or_update_result(result)
                    self.finish_background_activity()
                    scan_message = self.scan_status_message(
                        len(self.orders),
                        process_list_count,
                        import_summary,
                        process_list_import_summary,
                    )
                    if retired_sent_orders:
                        scan_message += f" Kept {len(retired_sent_orders)} previously sent order(s) retired."
                    self.status_var.set(scan_message)
                    self.start_review_cache_warmup(self.orders)
                elif kind == "import_done":
                    data = payload
                    assert isinstance(data, dict)
                    orders = data.get("orders", [])
                    process_list_count = int(data.get("process_list_count", 0))
                    process_list_import_summary = data.get("process_list_import_summary", {})
                    import_summary = data.get("import_summary", {})
                    if orders:
                        assert isinstance(orders, list)
                        self.orders = orders
                        self.order_by_aw = {order.aw_order: order for order in self.orders}
                    self.finish_background_activity()
                    messages = [
                        self.process_list_import_status_message(process_list_import_summary),
                        self.import_status_message(import_summary, process_list_count),
                    ]
                    self.status_var.set(" ".join(message for message in messages if message))
                elif kind == "scan_error":
                    self.finish_background_activity()
                    message = str(payload)
                    lowered = message.lower()
                    if "process list" in lowered and ("no " in lowered or "not " in lowered or "missing" in lowered):
                        self.orders = []
                        self.order_by_aw = {}
                        self.tree.delete(*self.tree.get_children())
                        self.tree_rows.clear()
                        self.update_summary_strip()
                        self.status_var.set(f"Scan complete: {message}")
                    else:
                        self.status_var.set("Scan failed")
                        messagebox.showerror("Scan failed", message)
                elif kind == "send_done":
                    data = payload
                    assert isinstance(data, dict)
                    copied = data.get("copied", [])
                    missing = data.get("missing", [])
                    archived = data.get("archived", [])
                    archive_warnings = data.get("archive_warnings", [])
                    import_deleted = data.get("import_deleted", [])
                    input_cleanup_warnings = data.get("input_cleanup_warnings", [])
                    sent_orders = data.get("sent_orders", [])
                    assert isinstance(copied, list)
                    assert isinstance(missing, list)
                    assert isinstance(archived, list)
                    assert isinstance(archive_warnings, list)
                    assert isinstance(import_deleted, list)
                    assert isinstance(input_cleanup_warnings, list)
                    assert isinstance(sent_orders, list)
                    self.finish_background_activity()
                    if not copied:
                        messagebox.showinfo("Nothing sent", "No matching generated files were found.")
                        self.status_var.set("No matching generated files were found.")
                        continue
                    try:
                        self.mark_orders_sent(sent_orders, copied, archived)
                    except Exception as exc:
                        input_cleanup_warnings.append(f"Could not save sent-order receipt: {exc}")
                    details = self.send_complete_details(
                        copied,
                        missing,
                        archived,
                        archive_warnings,
                        import_deleted,
                        input_cleanup_warnings,
                    )
                    self.status_var.set(details)
                    if self.send_review_status_var is not None:
                        self.send_review_status_var.set("Send complete.")
                    if self.send_review_progress is not None:
                        try:
                            self.send_review_progress.configure(mode="determinate", maximum=100, value=100)
                        except tk.TclError:
                            self.send_review_progress = None
                    if self.send_review_window is not None:
                        try:
                            self.send_review_window.destroy()
                        except tk.TclError:
                            pass
                        self.send_review_window = None
                        self.send_review_progress = None
                        self.send_review_status_var = None
                    messagebox.showinfo("Send complete", details)
                    self.root.after(100, self.scan_orders)
                elif kind == "send_error":
                    self.finish_background_activity()
                    self.status_var.set("Send failed")
                    if self.send_review_status_var is not None:
                        self.send_review_status_var.set("Send failed.")
                    messagebox.showerror("Send failed", str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self.drain_worker_queue)

    @staticmethod
    def scan_status_message(
        order_count: int,
        process_list_count: int,
        import_summary: object,
        process_list_import_summary: object | None = None,
    ) -> str:
        message = f"Found {order_count} orders from {process_list_count} process list(s)."
        process_list_message = ShowerProgrammerApp.process_list_import_status_message(process_list_import_summary)
        if process_list_message:
            message += " " + process_list_message
        import_message = ShowerProgrammerApp.import_status_message(import_summary, 0)
        if import_message:
            message += " " + import_message
        return message

    @staticmethod
    def process_list_import_status_message(import_summary: object) -> str:
        if not isinstance(import_summary, dict):
            return ""
        copied = import_summary.get("copied", [])
        skipped = int(import_summary.get("skipped", 0) or 0)
        source_missing = bool(import_summary.get("source_missing", False))
        direct = bool(import_summary.get("direct", False))
        if source_missing:
            return ""
        if direct:
            return "Using process lists directly from the dedicated input folder."
        copied_count = len(copied) if isinstance(copied, list) else 0
        if copied_count:
            return f"Imported/updated {copied_count} process list file(s); {skipped} already current."
        if skipped:
            return f"No process list files needed copying; {skipped} already current."
        return ""

    @staticmethod
    def import_status_message(import_summary: object, process_list_count: int) -> str:
        if not isinstance(import_summary, dict):
            return ""
        copied = import_summary.get("copied", [])
        skipped = int(import_summary.get("skipped", 0) or 0)
        hardware_deleted = import_summary.get("hardware_deleted", [])
        source_missing = bool(import_summary.get("source_missing", False))
        direct = bool(import_summary.get("direct", False))
        hardware_count = len(hardware_deleted) if isinstance(hardware_deleted, list) else 0
        hardware_note = f" Removed {hardware_count} hardware list PDF(s)." if hardware_count else ""
        if source_missing:
            return f"EDI import skipped; source folder not found: {import_summary.get('source', '')}"
        if direct:
            return "Using order PDFs/DXFs directly from the dedicated input folder." + hardware_note
        copied_count = len(copied) if isinstance(copied, list) else 0
        if copied_count:
            return f"Imported/updated {copied_count} matching EDI file(s); {skipped} already current." + hardware_note
        if process_list_count:
            return f"No EDI files needed copying for {process_list_count} process list(s); {skipped} already current." + hardware_note
        return f"No EDI files needed copying; {skipped} already current." + hardware_note

    def set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for child in self.root.winfo_children():
            self.set_child_state(child, state)

    def set_child_state(self, widget: tk.Widget, state: str) -> None:
        try:
            if isinstance(widget, (ttk.Button, ttk.Checkbutton, ttk.Entry)):
                widget.configure(state=state)
            elif ctk is not None and isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry, ctk.CTkComboBox)):
                widget.configure(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self.set_child_state(child, state)

    def review_sketches(self) -> None:
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            sketch_dir = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
            paths = self.generated_sketch_paths(output_dir, sketch_dir)
            if not paths:
                if sketch_dir.exists():
                    os.startfile(sketch_dir)
                else:
                    messagebox.showinfo("No sketches", "No generated sketch PDFs were found.")
                return

            review_dir = output_dir / "Reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            review_path = review_dir / f"sketch_review_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            config = self.config_with_manual_overrides(
                Path(self.folder_var.get()).resolve(),
                output_dir,
            )
            writer = PdfWriter()
            added_pages = 0
            for path in paths:
                reader = PdfReader(str(path))
                aw_order = path.stem
                for page_index in self.sketch_review_page_indices(reader, aw_order, config):
                    writer.add_page(reader.pages[page_index])
                    added_pages += 1
            if not added_pages:
                messagebox.showinfo("No sketch pages", "No piece pages were found in the generated sketches.")
                return
            with review_path.open("wb") as handle:
                writer.write(handle)
            os.startfile(review_path)
            self.status_var.set(f"Opened sketch review: {review_path.name}")
        except Exception as exc:
            messagebox.showerror("Review sketches failed", str(exc))

    def generated_sketch_paths(self, output_dir: Path, sketch_dir: Path) -> list[Path]:
        aw_orders = self.selected_or_visible_aw_orders()
        if aw_orders:
            return self.generated_sketch_paths_for_orders(aw_orders, output_dir)
        return sorted(sketch_dir.glob("*.pdf")) if sketch_dir.exists() else []

    def generated_sketch_paths_for_orders(self, aw_orders: list[str], output_dir: Path) -> list[Path]:
        paths: list[Path] = []
        for aw_order in aw_orders:
            path = self.find_order_sketch_path(aw_order, output_dir)
            if path.exists():
                paths.append(path)
        return paths

    def sketch_review_page_indices(
        self,
        reader: PdfReader,
        aw_order: str,
        config: dict[str, object],
    ) -> list[int]:
        try:
            panels = programmer.analyze_panels(reader, config, aw_order)
            indexes = sorted({panel.page_index for panel in panels if 0 <= panel.page_index < len(reader.pages)})
            if indexes:
                return indexes
        except Exception:
            pass
        return list(range(len(reader.pages)))

    def review_dxfs(self) -> None:
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
            paths = self.generated_dxf_paths(output_dir, programs_dir)
            if not paths:
                if programs_dir.exists():
                    os.startfile(programs_dir)
                else:
                    messagebox.showinfo("No DXFs", "No generated DXF files were found.")
                return
            review_dir = output_dir / "Reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            review_path = review_dir / f"dxf_review_{datetime.now():%Y%m%d_%H%M%S}.html"
            review_path.write_text(self.build_dxf_review_html(paths), encoding="utf-8")
            webbrowser.open(review_path.resolve().as_uri())
            self.status_var.set(f"Opened DXF review: {review_path.name}")
        except Exception as exc:
            messagebox.showerror("Review DXFs failed", str(exc))

    def generated_dxf_paths(self, output_dir: Path, programs_dir: Path) -> list[Path]:
        aw_orders = self.selected_or_visible_aw_orders()
        if aw_orders:
            return self.generated_dxf_paths_for_orders(aw_orders, output_dir)
        return sorted(programs_dir.glob("*.dxf")) if programs_dir.exists() else []

    def generated_dxf_paths_for_orders(self, aw_orders: list[str], output_dir: Path) -> list[Path]:
        paths: list[Path] = []
        for aw_order in aw_orders:
            _run_folder, _sketch_dir, order_programs_dir, _report_dir = self.output_dirs_for_order(aw_order, output_dir)
            paths.extend(sorted(order_programs_dir.glob(f"{aw_order}*.dxf")))
        return paths

    def build_dxf_review_html(self, paths: list[Path]) -> str:
        cards = "\n".join(self.dxf_preview_card(path) for path in paths)
        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>DXF Review</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 18px; color: #1f2933; }}
h1 {{ font-size: 22px; margin: 0 0 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
.card {{ border: 1px solid #cfd8e3; border-radius: 6px; padding: 10px; background: #fff; }}
.name {{ font-weight: 700; margin-bottom: 4px; overflow-wrap: anywhere; }}
.meta {{ color: #536471; font-size: 12px; margin-bottom: 8px; }}
svg {{ width: 100%; height: 240px; background: #f8fafc; border: 1px solid #e2e8f0; }}
line {{ stroke: #1f4e79; stroke-width: 2; vector-effect: non-scaling-stroke; }}
a {{ color: #1f4e79; }}
</style>
</head>
<body>
<h1>DXF Review</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""

    def dxf_preview_card(self, path: Path) -> str:
        title = html.escape(path.name)
        link = html.escape(path.resolve().as_uri(), quote=True)
        try:
            preview_data = self.order_review_dxf_preview_data(path)
            segments = preview_data["segments"]
        except Exception as exc:
            return (
                "<div class='card'>"
                f"<div class='name'><a href='{link}'>{title}</a></div>"
                f"<div class='meta'>Could not read DXF: {html.escape(str(exc))}</div>"
                "</div>"
            )
        if not segments:
            return (
                "<div class='card'>"
                f"<div class='name'><a href='{link}'>{title}</a></div>"
                "<div class='meta'>No drawable DXF entities found.</div>"
                "</div>"
            )
        points = [point for segment in segments for point in segment]
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        width = max(max_x - min_x, 0.001)
        height = max(max_y - min_y, 0.001)
        scale = min(260 / width, 210 / height)
        margin = 15.0

        def map_point(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            return margin + (x - min_x) * scale, margin + (max_y - y) * scale

        lines = []
        for start, end in segments:
            x1, y1 = map_point(start)
            x2, y2 = map_point(end)
            lines.append(f"<line x1='{x1:.2f}' y1='{y1:.2f}' x2='{x2:.2f}' y2='{y2:.2f}' />")
        svg_width = width * scale + margin * 2
        svg_height = height * scale + margin * 2
        meta = f"{width:g} x {height:g} | {len(segments)} segment(s)"
        internal_radii = preview_data.get("internal_radii", [])
        if internal_radii:
            radius_text = self.dxf_internal_radius_text(internal_radii, preview_data["inches_per_unit"])
            meta += f" | Internal cut radius: {radius_text}"
        return (
            "<div class='card'>"
            f"<div class='name'><a href='{link}'>{title}</a></div>"
            f"<div class='meta'>{html.escape(meta)}</div>"
            f"<svg viewBox='0 0 {svg_width:.2f} {svg_height:.2f}'>{''.join(lines)}</svg>"
            "</div>"
        )

    def open_order_review(self, event: tk.Event | None = None) -> None:
        if event is not None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
        selected = self.selected_orders()
        if len(selected) != 1:
            messagebox.showinfo("Select one order", "Select exactly one scanned order to review.")
            return
        process_order = selected[0]
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            self.status_var.set(f"Preparing review for {process_order.aw_order}...")
            self.root.update_idletasks()
            context = self.prepare_order_review_context(process_order, folder, output_dir, use_cache=True)
            run_folder = context["run_folder"]
            sketch_dir = context["sketch_dir"]
            programs_dir = context["programs_dir"]
            report_dir = context["report_dir"]
            sketch_path = context["sketch_path"]
            config = context["config"]
            job = context["job"]
            source_reader = context["source_reader"]
            issues = context["issues"]
            sketch_reader = context["sketch_reader"]
        except Exception as exc:
            if isinstance(exc, FileNotFoundError):
                messagebox.showinfo("No sketch yet", str(exc))
            else:
                messagebox.showerror("Order review failed", str(exc))
            return
        if not job.panels:
            messagebox.showinfo("No pieces", "No piece pages were found for this order.")
            return

        dialog = ctk.CTkToplevel(self.root) if ctk is not None else tk.Toplevel(self.root)
        dialog.title(f"Review Order - {process_order.aw_order}")
        self.position_child_window(dialog, 1180, 820)
        dialog.minsize(980, 560)
        dialog.resizable(True, True)
        self.set_window_icon(dialog)
        dialog.configure(fg_color=self.APP_BG) if ctk is not None else dialog.configure(bg=self.APP_BG)
        dialog.after(0, lambda: self.maximize_window(dialog))

        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        rotation_var = tk.IntVar(value=0)
        item_var = tk.StringVar(value=f"P{job.panels[0].item}")
        page_count_var = tk.StringVar(value=f"1/{len(job.panels)}")
        status = tk.StringVar(value="Start at Review Sketch, make only needed edits, then save/process before marking checked.")
        review_info_var = tk.StringVar(value="")

        header = ctk.CTkFrame(dialog, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 10))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            title_group,
            text=f"Review Order {process_order.aw_order}",
            font=("Segoe UI", 24, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            title_group,
            text=f"{process_order.job_name or 'No job name'}  -  {process_order.customer or 'No customer'}",
            font=("Segoe UI", 12),
            text_color=self.MUTED,
            anchor="w",
        ).pack(anchor=tk.W, pady=(2, 0))

        header_actions = ctk.CTkFrame(header, fg_color="transparent")
        header_actions.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            header_actions,
            text="Fit-to-window review",
            font=("Segoe UI", 11, "bold"),
            text_color=self.ACCENT_DARK,
            fg_color=self.SOFT_CARD_BG,
            corner_radius=999,
            padx=12,
            pady=7,
        ).pack(side=tk.RIGHT)

        workspace = ctk.CTkFrame(dialog, fg_color="transparent")
        workspace.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        workspace.grid_columnconfigure(0, weight=0, minsize=286)
        workspace.grid_columnconfigure(1, weight=9)
        workspace.grid_columnconfigure(2, weight=3)
        workspace.grid_rowconfigure(0, weight=1)

        control_panel = ctk.CTkFrame(
            workspace,
            fg_color=self.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=self.BORDER,
            width=286,
        )
        control_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        control_panel.grid_propagate(False)
        control_panel.grid_columnconfigure(0, weight=1)
        control_panel.grid_rowconfigure(7, weight=1)

        def control_section(parent: Any, row: int, title: str) -> Any:
            section = ctk.CTkFrame(parent, fg_color="transparent")
            section.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 14))
            section.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                section,
                text=title,
                font=("Segoe UI", 10, "bold"),
                text_color=self.MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", pady=(0, 7))
            return section

        step_header = ctk.CTkFrame(control_panel, fg_color="transparent")
        step_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        step_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            step_header,
            text="Review workflow",
            font=("Segoe UI", 16, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            step_header,
            text="1 Review  -  2 Adjust  -  3 Save  -  4 Process",
            font=("Segoe UI", 10),
            text_color=self.MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        piece_section = control_section(control_panel, 1, "PIECE NAVIGATION")
        piece_card = ctk.CTkFrame(piece_section, fg_color=self.SOFT_CARD_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
        piece_card.grid(row=1, column=0, sticky="ew")
        piece_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(piece_card, text="Piece", font=("Segoe UI", 11, "bold"), text_color=self.TEXT).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        item_box = ttk.Combobox(
            piece_card,
            textvariable=item_var,
            values=[f"P{panel.item}" for panel in job.panels],
            state="readonly",
            width=8,
            style="Review.TCombobox",
        )
        item_box.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=(12, 6))
        ctk.CTkLabel(piece_card, text="Position", font=("Segoe UI", 10), text_color=self.MUTED).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkLabel(piece_card, textvariable=page_count_var, font=("Segoe UI", 14, "bold"), text_color=self.ACCENT_DARK).grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(0, 12))
        nav_buttons = ctk.CTkFrame(piece_card, fg_color="transparent")
        nav_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        nav_buttons.grid_columnconfigure((0, 1), weight=1)
        self.make_tool_button(nav_buttons, "Previous", "chevron_left", lambda: change_piece(-1), width=112).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.make_tool_button(nav_buttons, "Next", "chevron_right", lambda: change_piece(1), width=92).grid(row=0, column=1, sticky="ew")

        primary_section = control_section(control_panel, 2, "PRIMARY ACTIONS")
        primary_grid = ctk.CTkFrame(primary_section, fg_color="transparent")
        primary_grid.grid(row=1, column=0, sticky="ew")
        primary_grid.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            primary_grid,
            text="Save Sketch Edits",
            command=lambda: save_review_edits(),
            height=42,
            corner_radius=10,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_DARK,
            text_color="#ffffff",
            font=("Segoe UI", 12, "bold"),
            **self.ctk_button_icon("save", 16, "#ffffff", "left"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.make_tool_button(primary_grid, "Process DXF Again", "play", lambda: process_review_order(), width=250).grid(row=1, column=0, sticky="ew")

        edit_section = control_section(control_panel, 3, "MARKUP TOOLS")
        edit_grid = ctk.CTkFrame(edit_section, fg_color="transparent")
        edit_grid.grid(row=1, column=0, sticky="ew")
        edit_grid.grid_columnconfigure((0, 1), weight=1)
        self.make_tool_button(edit_grid, "Indicator", "indicator", lambda: add_indicator_mark(), width=120).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 7))
        self.make_tool_button(edit_grid, "Flip", "flip", lambda: flip_indicator_sides(), width=120).grid(row=0, column=1, sticky="ew", pady=(0, 7))
        self.make_tool_button(edit_grid, "Text Box", "text", lambda: add_text_box(), width=120).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.make_tool_button(edit_grid, "Add X", "x", lambda: add_x_mark(), width=120).grid(row=1, column=1, sticky="ew")

        view_section = control_section(control_panel, 4, "VIEW")
        view_grid = ctk.CTkFrame(view_section, fg_color="transparent")
        view_grid.grid(row=1, column=0, sticky="ew")
        view_grid.grid_columnconfigure((0, 1), weight=1)
        self.make_tool_button(view_grid, "Rotate Left", "rotate_left", lambda: rotate_view(-90), width=120).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 7))
        self.make_tool_button(view_grid, "Rotate Right", "rotate_right", lambda: rotate_view(90), width=120).grid(row=0, column=1, sticky="ew", pady=(0, 7))
        self.make_tool_button(view_grid, "Open Sketch", "pdf", lambda: os.startfile(sketch_path), width=120).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.make_tool_button(view_grid, "Open DXF", "dxf", lambda: open_current_dxf(), width=120).grid(row=1, column=1, sticky="ew")

        status_card = ctk.CTkFrame(control_panel, fg_color=self.PANEL_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
        status_card.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 14))
        ctk.CTkLabel(
            status_card,
            text="Current status",
            font=("Segoe UI", 10, "bold"),
            text_color=self.MUTED,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 3))
        ctk.CTkLabel(
            status_card,
            textvariable=status,
            font=("Segoe UI", 11),
            text_color=self.TEXT,
            anchor="w",
            justify="left",
            wraplength=238,
        ).pack(fill=tk.X, padx=12, pady=(0, 12))

        complete_card = ctk.CTkFrame(control_panel, fg_color=self.CARD_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
        complete_card.grid(row=9, column=0, sticky="ew", padx=14, pady=(0, 14))
        ctk.CTkLabel(
            complete_card,
            text="Complete this order",
            font=("Segoe UI", 10, "bold"),
            text_color=self.MUTED,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 6))
        ctk.CTkButton(
            complete_card,
            text="Mark Order Checked & Close",
            command=lambda: complete_order_review(),
            height=44,
            corner_radius=10,
            fg_color=self.SUCCESS,
            hover_color="#039855" if not self.dark_mode_var.get() else "#12b76a",
            text_color="#ffffff",
            font=("Segoe UI", 12, "bold"),
            **self.ctk_button_icon("check", 17, "#ffffff", "left"),
        ).pack(fill=tk.X, padx=12, pady=(0, 12))

        sketch_frame = ctk.CTkFrame(workspace, fg_color=self.CARD_BG, corner_radius=16, border_width=1, border_color=self.BORDER)
        sketch_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        sketch_frame.grid_columnconfigure(0, weight=1)
        sketch_frame.grid_rowconfigure(1, weight=1)

        sketch_header = ctk.CTkFrame(sketch_frame, fg_color="transparent", height=48)
        sketch_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        sketch_header.grid_propagate(False)
        ctk.CTkLabel(sketch_header, text="", image=self.ctk_button_icon("pdf", 18, self.ACCENT_DARK).get("image"), width=24).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkLabel(sketch_header, text="Sketch Preview", font=("Segoe UI", 15, "bold"), text_color=self.TEXT).pack(side=tk.LEFT)
        ctk.CTkLabel(
            sketch_header,
            text="No scrollbars - preview auto-fits the available space",
            font=("Segoe UI", 10),
            text_color=self.MUTED,
        ).pack(side=tk.RIGHT)
        sketch_canvas = tk.Canvas(sketch_frame, background=self.PREVIEW_BG, highlightthickness=0, bd=0)
        sketch_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        reference_panel = ctk.CTkFrame(workspace, fg_color="transparent")
        reference_panel.grid(row=0, column=2, sticky="nsew")
        reference_panel.grid_columnconfigure(0, weight=1)
        reference_panel.grid_rowconfigure(1, weight=1)

        details_card = ctk.CTkFrame(reference_panel, fg_color=self.CARD_BG, corner_radius=16, border_width=1, border_color=self.BORDER)
        details_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            details_card,
            text="Piece Details",
            font=("Segoe UI", 14, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(12, 4))
        ctk.CTkLabel(
            details_card,
            textvariable=review_info_var,
            font=("Segoe UI", 11),
            text_color=self.MUTED,
            anchor="w",
            justify="left",
            wraplength=310,
        ).pack(fill=tk.X, padx=14, pady=(0, 14))

        dxf_frame = ctk.CTkFrame(reference_panel, fg_color=self.CARD_BG, corner_radius=16, border_width=1, border_color=self.BORDER)
        dxf_frame.grid(row=1, column=0, sticky="nsew")
        dxf_frame.grid_columnconfigure(0, weight=1)
        dxf_frame.grid_rowconfigure(1, weight=1)
        dxf_header = ctk.CTkFrame(dxf_frame, fg_color="transparent", height=48)
        dxf_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        dxf_header.grid_propagate(False)
        ctk.CTkLabel(dxf_header, text="", image=self.ctk_button_icon("dxf", 18, self.ACCENT_DARK).get("image"), width=24).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkLabel(dxf_header, text="DXF Reference", font=("Segoe UI", 15, "bold"), text_color=self.TEXT).pack(side=tk.LEFT)
        dxf_canvas = tk.Canvas(dxf_frame, background=self.PREVIEW_CARD_BG, highlightthickness=0, bd=0)
        dxf_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        state: dict[str, Any] = {
            "objects": {},
            "positions": {},
            "dirty": set(),
            "drag_key": None,
            "selected_key": None,
            "last_x": 0.0,
            "last_y": 0.0,
            "page_images": [],
            "render_cache": {},
            "overlay_cache": {},
            "dxf_preview_cache": {},
            "render_temp_dir": tempfile.mkdtemp(prefix="shower_order_review_"),
            "render_root": dialog,
            "output_dir": output_dir,
            "pdf_page_count": len(source_reader.pages),
            "raster_rendering": set(),
            "current_item": job.panels[0].item,
            "viewed_items": {job.panels[0].item},
            "pending_items": set(),
            "needs_output_save": False,
            "redraw_after_id": None,
        }

        def selected_panel() -> programmer.Panel:
            item = int(item_var.get().replace("P", ""))
            return next(panel for panel in job.panels if panel.item == item)

        def has_pending_item_edits(item_number: int | None = None) -> bool:
            dirty = state.get("dirty", set())
            pending = state.get("pending_items", set())
            if item_number is None:
                return bool(dirty or pending or state.get("needs_output_save"))
            return any(item == item_number for item, _key in dirty) or item_number in pending

        def discard_pending_item_edits(item_number: int | None = None) -> None:
            if item_number is None:
                state.get("dirty", set()).clear()
                state.get("positions", {}).clear()
                state.get("pending_items", set()).clear()
                state["needs_output_save"] = False
                return
            state["dirty"] = {entry for entry in state.get("dirty", set()) if entry[0] != item_number}
            state["positions"] = {
                entry: position
                for entry, position in state.get("positions", {}).items()
                if entry[0] != item_number
            }
            state.get("pending_items", set()).discard(item_number)
            state["needs_output_save"] = bool(state.get("dirty") or state.get("pending_items"))

        def confirm_save_before_leaving(item_number: int | None = None) -> bool:
            if not has_pending_item_edits(item_number):
                return True
            label = f"P{item_number}" if item_number is not None else "this order"
            answer = messagebox.askyesnocancel(
                "Save sketch edits?",
                f"Save edits for {label} before leaving?",
                parent=dialog,
            )
            if answer is None:
                return False
            if answer:
                return save_review_edits(show_no_edits=False)
            discard_pending_item_edits(item_number)
            return True

        def set_piece(value: str) -> bool:
            try:
                next_item = int(value.replace("P", ""))
            except ValueError:
                return False
            current_item = int(state.get("current_item", selected_panel().item))
            if next_item != current_item and not confirm_save_before_leaving(current_item):
                item_var.set(f"P{current_item}")
                return False
            state["current_item"] = next_item
            state.setdefault("viewed_items", set()).add(next_item)
            item_var.set(f"P{next_item}")
            rotation_var.set(0)
            redraw()
            return True

        def change_piece(delta: int) -> str:
            values = [f"P{panel.item}" for panel in job.panels]
            if not values:
                return "break"
            try:
                index = values.index(item_var.get())
            except ValueError:
                index = 0
            set_piece(values[(index + delta) % len(values)])
            return "break"

        def piece_wheel(event: tk.Event) -> str:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return "break"
            return change_piece(-1 if delta > 0 else 1)

        def rotate_view(delta: int) -> None:
            rotation_var.set((rotation_var.get() + delta) % 360)
            redraw()

        def open_current_dxf() -> None:
            panel = selected_panel()
            path = panel.output_dxf if panel.output_dxf and panel.output_dxf.exists() else panel.source_dxf
            if path and path.exists():
                os.startfile(str(path.resolve()))
                status.set(f"Opened DXF: {path.resolve()}")
            else:
                messagebox.showinfo("No DXF", "No matching DXF exists for this piece.", parent=dialog)

        def start_drag(event: tk.Event, key: str) -> None:
            if rotation_var.get() % 360:
                status.set("Set sketch view back to 0 deg before dragging marks.")
                return
            state["selected_key"] = key
            if state.get("objects", {}).get(key, {}).get("kind") == "x":
                status.set("X marks can be deleted from the popup, but they are not draggable.")
                return
            state["drag_key"] = key
            state["last_x"] = float(sketch_canvas.canvasx(event.x))
            state["last_y"] = float(sketch_canvas.canvasy(event.y))

        def drag(event: tk.Event) -> None:
            key = state.get("drag_key")
            if not key:
                return
            x = float(sketch_canvas.canvasx(event.x))
            y = float(sketch_canvas.canvasy(event.y))
            dx = x - float(state["last_x"])
            dy = y - float(state["last_y"])
            state["last_x"] = x
            state["last_y"] = y
            sketch_canvas.move(f"edit_{key}", dx, dy)
            obj = state["objects"][key]
            scale = float(obj.get("scale", 1.0))
            obj["x"] += dx / scale
            obj["y"] -= dy / scale
            item_number = int(obj.get("item", selected_panel().item))
            item_key = (item_number, str(obj.get("key", key)))
            state["dirty"].add(item_key)
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            position = {"x": obj["x"], "y": obj["y"]}
            if obj.get("key") == "indicator":
                corner = programmer.nearest_indicator_corner_for_point(
                    obj["machine"],
                    (obj["x"], obj["y"]),
                    obj.get("anchor_bbox"),
                    float(obj["page_width"]),
                    float(obj["page_height"]),
                    obj["pdf_cfg"],
                    precise_edges=bool(obj.get("precise_edges")),
                )
                position["indicator_corner"] = corner
                machine = str(obj["machine"])
                if machine.startswith("DENVER") or machine == "WJ":
                    raw_corner = programmer.nearest_indicator_corner_for_point(
                        obj["machine"],
                        (obj["x"], obj["y"]),
                        obj.get("anchor_bbox"),
                        float(obj["page_width"]),
                        float(obj["page_height"]),
                        obj["pdf_cfg"],
                        precise_edges=bool(obj.get("precise_edges")),
                        allowed_denver_only=False,
                        allowed_waterjet_only=False,
                    )
                    position["raw_indicator_corner"] = raw_corner
                    if machine == "WJ":
                        position["indicator_corner"] = raw_corner
            state["positions"][item_key] = position
            status.set(f"Moved {obj['name']} on {job.aw_order}.{item_number}")

        def release(_event: tk.Event) -> None:
            state["drag_key"] = None

        def regenerate_review_sketch() -> bool:
            nonlocal job, source_reader, sketch_reader, issues, config
            try:
                refreshed_config = self.config_with_manual_overrides(folder, output_dir)
                remake_items = self.editor_remake_items(process_order.aw_order)
                refreshed_job, refreshed_reader, refreshed_issues = shower_batch.prepare_job(
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    process_order,
                    remake_items=remake_items,
                )
                programmer.write_marked_pdf(refreshed_job, refreshed_reader, refreshed_config, force=True)
                job = refreshed_job
                source_reader = PdfReader(str(job.pdf_path))
                sketch_reader = PdfReader(str(sketch_path))
                issues = refreshed_issues
                config = refreshed_config
                state.get("pending_items", set()).clear()
                state["needs_output_save"] = False
                self.clear_review_context_cache(process_order.aw_order)
                return True
            except Exception as exc:
                messagebox.showerror("Save sketch failed", str(exc), parent=dialog)
                return False

        def save_review_edits(show_no_edits: bool = True) -> bool:
            dirty = bool(state.get("dirty"))
            pending_output = bool(state.get("pending_items") or state.get("needs_output_save"))
            if dirty and not self.save_editor_state_positions(job, state, config, dialog, show_no_edits=show_no_edits):
                return False
            if dirty or pending_output:
                if not regenerate_review_sketch():
                    return False
                status.set("Saved edits and overwrote the sketch PDF.")
                redraw()
                return True
            if show_no_edits:
                messagebox.showinfo("No edits", "Nothing has been changed yet.", parent=dialog)
            return False

        def process_review_order() -> None:
            nonlocal job, source_reader, sketch_reader, issues, config
            if has_pending_item_edits() and not save_review_edits(show_no_edits=False):
                return
            try:
                refreshed_config = self.config_with_manual_overrides(folder, output_dir)
                remake_items = self.editor_remake_items(process_order.aw_order)
                result = shower_batch.process_one_order(
                    process_order,
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    apply=True,
                    force=True,
                    skip_pdf=False,
                    skip_dxf=False,
                    remake_items=remake_items,
                )
                job, source_reader, issues = shower_batch.prepare_job(
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    process_order,
                    remake_items=remake_items,
                )
                config = refreshed_config
                sketch_reader = PdfReader(str(sketch_path))
                self.insert_or_update_result(result)
                self.clear_review_context_cache(process_order.aw_order)
                status.set(f"Processed {job.aw_order}; DXF preview refreshed.")
                redraw()
            except Exception as exc:
                messagebox.showerror("Process DXF failed", str(exc), parent=dialog)

        def refresh_prepared_job() -> None:
            nonlocal job, source_reader, issues, config
            config = self.config_with_manual_overrides(folder, output_dir)
            job, source_reader, issues = shower_batch.prepare_job(
                folder,
                sketch_dir,
                programs_dir,
                report_dir,
                config,
                process_order,
                remake_items=self.editor_remake_items(process_order.aw_order, output_dir),
            )
            self.clear_review_context_cache(process_order.aw_order)

        def delete_selected_mark() -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No mark selected", "Click a blue mark first.", parent=dialog)
                return
            obj = state["objects"][key]
            item_number = int(obj.get("item", selected_panel().item))
            mark_key = str(obj.get("key", "")).strip()
            if not mark_key:
                return
            if mark_key == "manual_x":
                self.set_manual_x_override(job.aw_order, item_number, False)
                refresh_prepared_job()
                state["selected_key"] = None
                state.get("pending_items", set()).add(item_number)
                state["needs_output_save"] = True
                status.set(f"Deleted manual X on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
                redraw()
                return
            self.set_mark_hidden(job.aw_order, item_number, mark_key, hidden=True)
            refresh_prepared_job()
            state["selected_key"] = None
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Deleted {obj.get('name', mark_key)} on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
            redraw()

        def add_indicator_mark() -> None:
            panel = selected_panel()
            self.set_mark_hidden(job.aw_order, panel.item, "indicator", hidden=False)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Restored indicator on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def flip_indicator_sides() -> None:
            panel = selected_panel()
            current = panel.indicator_corner or (
                programmer.default_waterjet_indicator_corner(panel)
                if panel.machine == "WJ"
                else programmer.denver_grabber_corner_for_panel(panel, panel.rotation_degrees)
            )
            corner = self.flipped_indicator_corner(current)
            self.set_indicator_corner_override(job.aw_order, panel.item, corner, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Flipped indicator side to {corner} on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def add_x_mark() -> None:
            panel = selected_panel()
            self.set_manual_x_override(job.aw_order, panel.item, True)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Added X-out mark on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def add_text_box() -> None:
            panel = selected_panel()
            initial = panel.label_text or f"{job.aw_order}.{panel.item}\n{panel.machine or ''}".strip()
            value = self.ask_themed_text(
                dialog,
                "Add Text Box",
                "Enter sketch text. Put each line on its own row.",
                initialvalue=initial,
            )
            if value is None:
                return
            self.set_label_text_and_detect_machine(job.aw_order, panel.item, value, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Added text box on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def set_current_indicator_machine(machine_kind: str) -> None:
            panel = selected_panel()
            self.set_indicator_machine_override(job.aw_order, panel.item, machine_kind, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Changed indicator/machine for {job.aw_order}.{panel.item} to {machine_kind}. Click Save Edits to overwrite the sketch.")
            redraw()

        def resize_selected_mark(direction: int) -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No mark selected", "Click a blue mark first, then use Size - or Size +.", parent=dialog)
                return
            obj = state["objects"][key]
            item_number = int(obj.get("item", selected_panel().item))
            mark_key = str(obj.get("key", "")).strip()
            if not mark_key:
                return
            panel = next(panel for panel in job.panels if panel.item == item_number)
            new_size = self.set_mark_size_override(job.aw_order, item_number, mark_key, direction, obj, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Changed {obj.get('name', mark_key)} size on {job.aw_order}.{item_number} to {new_size:g}. Click Save Edits to overwrite the sketch.")
            redraw()

        def edit_selected_text() -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No text selected", "Click a blue text mark first.", parent=dialog)
                return
            obj = state["objects"][key]
            if obj.get("kind") != "text":
                messagebox.showinfo("Not text", "Select a blue text mark to edit.", parent=dialog)
                return
            mark_key = str(obj.get("key", "")).strip()
            item_number = int(obj.get("item", selected_panel().item))
            current = "\\n".join(str(line) for line in obj.get("lines", []))
            value = self.ask_themed_text(
                dialog,
                "Edit Text",
                "Edit generated text. Put each line on its own row.",
                initialvalue=current,
            )
            if value is None:
                return
            self.set_mark_text_override(job.aw_order, item_number, mark_key, value)
            refresh_prepared_job()
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Edited {obj.get('name', mark_key)} on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
            redraw()

        def show_mark_menu(event: tk.Event, key: str) -> str:
            if key not in state.get("objects", {}):
                return "break"
            state["selected_key"] = key
            obj = state["objects"][key]
            kind = str(obj.get("kind", "mark")).strip().lower()
            mark_name = str(obj.get("name") or obj.get("key") or "Sketch Mark")
            item_number = int(obj.get("item", selected_panel().item))
            title = f"P{item_number} - {mark_name}"
            subtitle = "Choose an action for this sketch mark."

            def select_then(command: Callable[[], object]) -> Callable[[], object]:
                def wrapper() -> object:
                    state["selected_key"] = key
                    return command()
                return wrapper

            actions: list[dict[str, object]] = []
            if kind != "x":
                actions.extend(
                    [
                        {"text": "Increase Size", "icon": "plus", "command": select_then(lambda: resize_selected_mark(1))},
                        {"text": "Decrease Size", "icon": "minus_circle", "command": select_then(lambda: resize_selected_mark(-1))},
                    ]
                )
            if kind == "text":
                actions.append({"text": "Edit Text", "icon": "text", "command": select_then(edit_selected_text)})
            if obj.get("key") == "indicator":
                actions.extend(
                    [
                        {"separator": True},
                        {"text": "Make Water Jet", "icon": "indicator", "command": lambda: set_current_indicator_machine("WJ")},
                        {"text": "Make Denver", "icon": "program", "command": lambda: set_current_indicator_machine("DENVER")},
                    ]
                )
            actions.extend(
                [
                    {"separator": True},
                    {"text": "Delete Mark", "icon": "trash", "destructive": True, "command": select_then(delete_selected_mark)},
                ]
            )
            self.show_themed_context_menu(dialog, event.x_root, event.y_root, title, subtitle, actions)
            return "break"

        def redraw() -> None:
            after_id = state.get("redraw_after_id")
            if after_id is not None:
                try:
                    dialog.after_cancel(after_id)
                except tk.TclError:
                    pass
            state["redraw_after_id"] = None
            panel = selected_panel()
            state.setdefault("viewed_items", set()).add(panel.item)
            ordered_items = [current.item for current in sorted(job.panels, key=lambda current: current.item)]
            if panel.item in ordered_items:
                page_count_var.set(f"{ordered_items.index(panel.item) + 1}/{len(ordered_items)}")
            try:
                self.draw_order_review_sketch(
                    sketch_canvas,
                    source_reader,
                    job.pdf_path,
                    job,
                    panel,
                    config,
                    rotation_var.get(),
                    state,
                )
            except Exception as exc:
                sketch_canvas.delete("all")
                sketch_canvas.create_rectangle(
                    0,
                    0,
                    sketch_canvas.winfo_width(),
                    sketch_canvas.winfo_height(),
                    fill=self.PREVIEW_BG,
                    outline="",
                )
                sketch_canvas.create_text(16, 16, anchor=tk.NW, text=f"Sketch preview failed: {exc}", fill=self.DANGER)
            dxf_path = panel.output_dxf if panel.output_dxf and panel.output_dxf.exists() else panel.source_dxf
            try:
                self.draw_order_review_dxf(dxf_canvas, dxf_path, panel, state)
            except Exception as exc:
                dxf_canvas.delete("all")
                dxf_canvas.create_rectangle(0, 0, dxf_canvas.winfo_width(), dxf_canvas.winfo_height(), fill=self.PREVIEW_CARD_BG, outline="")
                dxf_canvas.create_text(16, 16, anchor=tk.NW, text=f"DXF preview failed: {exc}", fill=self.DANGER)
            issue_text = "; ".join(issues[:2]) if issues else ""
            rotation_text = self.panel_rotation_summary(panel)
            review_info_var.set(
                "\n".join(
                    [
                        f"Order: {job.aw_order}",
                        f"Piece: P{panel.item}",
                        f"Machine: {panel.machine or 'Label Only'}",
                        f"DXF rotation: {rotation_text}",
                        f"Job: {process_order.job_name or '-'}",
                        f"Customer: {process_order.customer or '-'}",
                    ]
                )
            )
            status.set(
                f"{job.aw_order}.{panel.item}  {panel.machine or 'LABEL ONLY'}  "
                f"Sketch view {rotation_var.get()} deg  |  {rotation_text}"
                + (f"  |  {issue_text}" if issue_text else "")
            )

        def schedule_redraw(delay: int = 90) -> None:
            after_id = state.get("redraw_after_id")
            if after_id is not None:
                try:
                    dialog.after_cancel(after_id)
                except tk.TclError:
                    pass
            state["redraw_after_id"] = dialog.after(delay, redraw)

        state["render_callback"] = lambda: schedule_redraw(1)

        def complete_order_review() -> None:
            if not confirm_save_before_leaving(None):
                return
            all_items = {panel.item for panel in job.panels}
            viewed_items = set(state.get("viewed_items", set()))
            unviewed_items = sorted(all_items - viewed_items)
            if unviewed_items:
                unviewed_text = ", ".join(f"P{item}" for item in unviewed_items)
                if not messagebox.askyesno(
                    "Unviewed pieces",
                    "Are you sure you want to mark this order checked?\n\n"
                    f"You have not viewed: {unviewed_text}",
                    parent=dialog,
                ):
                    return

            data = self.load_manual_overrides()
            item_overrides = data.setdefault("item_overrides", {})
            if not isinstance(item_overrides, dict):
                item_overrides = {}
                data["item_overrides"] = item_overrides
            order_overrides = item_overrides.setdefault(process_order.aw_order, {})
            if not isinstance(order_overrides, dict):
                order_overrides = {}
                item_overrides[process_order.aw_order] = order_overrides
            order_overrides["_order_checked"] = True
            self.save_manual_overrides(data)

            row_id = self.tree_rows.get(process_order.aw_order)
            if row_id:
                values = list(self.tree.item(row_id, "values"))
                if len(values) >= 9:
                    values[8] = "Order checked"
                    self.tree.item(row_id, values=values)
            self.update_summary_strip()
            self.status_var.set(f"Marked order {process_order.aw_order} checked.")
            cleanup_render_temp()
            dialog.destroy()

        def cleanup_render_temp(_event: tk.Event | None = None) -> None:
            temp_dir = state.get("render_temp_dir")
            if _event is not None and _event.widget is not dialog:
                return
            if isinstance(temp_dir, str):
                shutil.rmtree(temp_dir, ignore_errors=True)

        def request_close() -> None:
            if confirm_save_before_leaving(None):
                cleanup_render_temp()
                dialog.destroy()

        item_box.bind("<<ComboboxSelected>>", lambda _event: set_piece(item_var.get()))
        item_box.bind("<MouseWheel>", piece_wheel)
        sketch_canvas.bind("<Configure>", lambda _event: schedule_redraw())
        dxf_canvas.bind("<Configure>", lambda _event: schedule_redraw())
        sketch_canvas.bind("<B1-Motion>", drag)
        sketch_canvas.bind("<ButtonRelease-1>", release)
        sketch_canvas.bind("<MouseWheel>", lambda event: "break")
        sketch_canvas.bind("<Shift-MouseWheel>", lambda event: "break")
        dialog.bind("<Control-MouseWheel>", piece_wheel)
        dialog.bind("<MouseWheel>", lambda event: "break")
        state["start_drag"] = start_drag
        state["show_mark_menu"] = show_mark_menu
        dialog.protocol("WM_DELETE_WINDOW", request_close)
        dialog.bind("<Destroy>", cleanup_render_temp, add="+")
        dialog.after(100, redraw)

    def draw_order_review_sketch(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        sketch_path: Path,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
        rotation_degrees: int,
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["objects"] = {}
        state["page_images"] = []
        page = reader.pages[panel.page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        view_width = page_height if rotation_degrees % 180 else page_width
        view_height = page_width if rotation_degrees % 180 else page_height
        available_width = max(200, canvas.winfo_width() - 16)
        available_height = max(200, canvas.winfo_height() - 16)
        fit_scale = min(available_width / max(view_width, 1), available_height / max(view_height, 1))
        scale = round(min(2.0, max(0.18, fit_scale)), 3)
        image = self.editor_page_image(
            sketch_path,
            panel.page_index,
            page_width,
            page_height,
            scale,
            state,
            rotation_degrees=rotation_degrees,
        )
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill=self.PREVIEW_BG, outline="")
        if image is None:
            message = "Rendering sketch preview..." if state.get("raster_rendering") else "Could not render sketch preview."
            canvas.create_text(16, 16, anchor=tk.NW, text=message, fill=self.MUTED)
            return
        state["page_images"].append(image)
        x = max(8.0, (canvas.winfo_width() - image.width()) / 2)
        y = max(8.0, (canvas.winfo_height() - image.height()) / 2)
        canvas.create_image(x, y, image=image, anchor=tk.NW)
        objects = self.editor_overlay_objects(
            reader,
            job,
            panel,
            config,
            state.setdefault("overlay_cache", {}),
        )
        for obj in objects:
            obj["item"] = panel.item
            obj["scale"] = scale
            self.draw_editor_object(
                canvas,
                obj,
                scale,
                x,
                page_height,
                state,
                top_offset=y - x,
                page_width=page_width,
                rotation_degrees=rotation_degrees,
            )
        if rotation_degrees % 360 != 0:
            canvas.create_text(
                x + 8,
                y + 8,
                anchor=tk.NW,
                text="Rotated view is visual only. Return to 0 deg to drag marks.",
                fill=self.WARNING,
                font=("Arial", 10, "bold"),
            )
        canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), canvas.winfo_height()))

    def draw_order_review_dxf(
        self,
        canvas: tk.Canvas,
        path: Path | None,
        panel: programmer.Panel,
        state: dict[str, Any] | None = None,
    ) -> None:
        canvas.delete("all")
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill=self.PREVIEW_CARD_BG, outline="")
        canvas_width = max(520, canvas.winfo_width())
        rotation_text = self.panel_rotation_summary(panel)
        col_1 = 18
        col_2 = max(190, int(canvas_width * 0.42))
        col_3 = max(340, int(canvas_width * 0.72))
        canvas.create_text(
            col_1,
            16,
            anchor=tk.NW,
            text="DXF File",
            fill=self.MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        canvas.create_text(
            col_3,
            16,
            anchor=tk.NW,
            text="DXF Rotation",
            fill=self.MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        canvas.create_text(
            col_3,
            38,
            anchor=tk.NW,
            text=rotation_text,
            fill=self.ACCENT_DARK,
            font=("Segoe UI", 10, "bold"),
        )
        if path is None or not path.exists():
            canvas.create_text(col_1, 38, anchor=tk.NW, text="No DXF for this piece.", fill=self.TEXT, font=("Segoe UI", 10))
            return
        try:
            preview_data = self.order_review_dxf_preview_data(path, state)
            segments = preview_data["segments"]
            unit_label = preview_data["unit_label"]
            inches_per_unit = preview_data["inches_per_unit"]
            internal_radii = preview_data["internal_radii"]
            internal_radius_samples = preview_data["internal_radius_samples"]
        except Exception as exc:
            canvas.create_text(col_1, 38, anchor=tk.NW, text=f"Could not read DXF: {exc}", fill=self.DANGER, font=("Segoe UI", 10))
            return
        canvas.create_text(
            col_1,
            38,
            anchor=tk.NW,
            text=path.name,
            fill=self.TEXT,
            font=("Segoe UI", 10),
        )
        canvas.create_text(
            col_2,
            16,
            anchor=tk.NW,
            text="DXF Units",
            fill=self.MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        canvas.create_text(
            col_2,
            38,
            anchor=tk.NW,
            text=self.dxf_units_text(unit_label, inches_per_unit),
            fill=self.TEXT,
            font=("Segoe UI", 10),
        )
        is_pph = programmer.has_pph_hinge(panel)
        show_internal_radius = panel.machine == "WJ" or is_pph
        header_height = 132.0 if show_internal_radius else 116.0
        legend_y = 98 if show_internal_radius else 76
        if show_internal_radius:
            radius_label = "PPH Hinge Radii" if is_pph else "Internal Cut Radius"
            canvas.create_text(
                col_1,
                70,
                anchor=tk.NW,
                text=radius_label,
                fill=self.MUTED,
                font=("Segoe UI", 9, "bold"),
            )
            radius_x = col_1 + 126
            radius_color = self.ACCENT_DARK if internal_radii else self.MUTED
            radius_font = ("Segoe UI", 10, "bold")
            if is_pph:
                hinge_radii = programmer.pph_hinge_internal_radii_inches(
                    internal_radius_samples,
                    segments,
                    inches_per_unit,
                )
                radius_text, radius_ok = self.dxf_pph_hinge_radius_status(hinge_radii)
                radius_color = self.SUCCESS if radius_ok else self.DANGER
                radius_font = ("Segoe UI", 11, "bold")
                canvas.create_oval(
                    radius_x,
                    74,
                    radius_x + 8,
                    82,
                    fill=radius_color,
                    outline="",
                )
                radius_x += 14
            else:
                radius_text = self.dxf_internal_radius_text(internal_radii, inches_per_unit)
            canvas.create_text(
                radius_x,
                70,
                anchor=tk.NW,
                text=radius_text,
                fill=radius_color,
                font=radius_font,
            )
        if not segments:
            canvas.create_text(col_1, legend_y, anchor=tk.NW, text="No drawable DXF entities found.", fill=self.TEXT, font=("Segoe UI", 10))
            return
        points = [point for segment in segments for point in segment]
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        width = max(max_x - min_x, 0.001)
        height = max(max_y - min_y, 0.001)
        margin = 34.0
        scale = min(
            max(20, canvas.winfo_width() - margin * 2) / width,
            max(20, canvas.winfo_height() - margin * 2 - header_height) / height,
        )

        def map_point(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            return margin + (x - min_x) * scale, header_height + (max_y - y) * scale

        long_side = max(width, height)
        highlight_segments = self.out_of_square_preview_segments(segments, long_side, inches_per_unit)
        for start, end in segments:
            x1, y1 = map_point(start)
            x2, y2 = map_point(end)
            highlight = (start, end) in highlight_segments
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=self.WARNING if highlight else self.ACCENT_DARK,
                width=4 if highlight else 2,
            )
            if highlight:
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                canvas.create_text(
                    mx,
                    my - 12,
                    anchor=tk.CENTER,
                    text=self.out_of_square_segment_label(start, end, inches_per_unit),
                    fill=self.WARNING,
                    font=("Arial", 9, "bold"),
                )
        if highlight_segments:
            canvas.create_text(
                col_1,
                legend_y,
                anchor=tk.NW,
                text="Orange = angled/out-of-square side",
                fill=self.WARNING,
                font=("Segoe UI", 9, "bold"),
            )
        canvas.create_text(
            col_1,
            canvas.winfo_height() - 18,
            anchor=tk.SW,
            text=f"{self.dxf_dimension_text(width, height, unit_label, inches_per_unit)} | {len(segments)} segment(s)",
            fill=self.MUTED,
            font=("Segoe UI", 9),
        )

    def order_review_dxf_preview_data(self, path: Path, state: dict[str, Any] | None = None) -> dict[str, Any]:
        cache: dict[Any, dict[str, Any]] | None = None
        if state is not None:
            cache = state.setdefault("dxf_preview_cache", {})
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if cache is not None and key in cache:
            return cache[key]

        segments = programmer.collect_dxf_preview_segments(path)
        internal_radius_samples = programmer.collect_dxf_internal_cut_radius_samples(path)
        internal_radii = programmer.unique_dxf_internal_cut_radii(internal_radius_samples)
        insunits = self.dxf_insunits(path)
        inches_per_unit = {
            "1": 1.0,
            "2": 12.0,
            "4": 1.0 / 25.4,
            "5": 1.0 / 2.54,
            "6": 39.37007874015748,
        }.get(insunits, 1.0)
        unit_label = {
            "1": "in",
            "2": "ft",
            "4": "mm",
            "5": "cm",
            "6": "m",
        }.get(insunits, "units")
        data = {
            "segments": segments,
            "internal_radii": internal_radii,
            "internal_radius_samples": internal_radius_samples,
            "unit_label": unit_label,
            "inches_per_unit": inches_per_unit,
        }
        if cache is not None:
            if len(cache) > 80:
                cache.clear()
            cache[key] = data
        return data

    @classmethod
    def dxf_internal_radius_text(cls, radii: list[float], inches_per_unit: float = 1.0) -> str:
        values: list[float] = []
        for radius in sorted(abs(value * inches_per_unit) for value in radii if value > 0):
            if not values or abs(radius - values[-1]) > max(1e-7, radius * 1e-7):
                values.append(radius)
        if not values:
            return "Not detected"
        labels = [cls.format_inches(value) for value in values[:4]]
        if len(values) > 4:
            labels.append(f"+{len(values) - 4} more")
        return ", ".join(labels)

    @classmethod
    def dxf_pph_hinge_radius_status(cls, hinge_radii: list[list[float]]) -> tuple[str, bool]:
        expected = 5.0 / 16.0
        if not hinge_radii:
            return "Not detected - check DXF", False
        labels: list[str] = []
        radius_ok = True
        for index, radii in enumerate(hinge_radii, start=1):
            values: list[float] = []
            for radius in sorted(abs(value) for value in radii if value > 0):
                if not values or abs(radius - values[-1]) > max(1e-7, radius * 1e-7):
                    values.append(radius)
            value_text = ", ".join(cls.format_inches(value) for value in values) or "Not detected"
            labels.append(f"Hinge {index}: {value_text}")
            if len(values) != 1 or abs(values[0] - expected) > 1e-4:
                radius_ok = False
        return "  |  ".join(labels), radius_ok

    @classmethod
    def out_of_square_preview_segments(
        cls,
        segments: list[tuple[tuple[float, float], tuple[float, float]]],
        long_side: float,
        inches_per_unit: float = 1.0,
    ) -> set[tuple[tuple[float, float], tuple[float, float]]]:
        angled: list[tuple[tuple[float, float], tuple[float, float]]] = []
        horizontal: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for start, end in segments:
            if not cls.is_out_of_square_preview_segment(start, end, long_side, inches_per_unit):
                continue
            angled.append((start, end))
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            angle = math.degrees(math.atan2(dy, dx))
            horizontal_deviation = abs(programmer.normalize_axis_deviation(angle))
            vertical_deviation = abs(programmer.normalize_axis_deviation(angle - 90))
            if horizontal_deviation <= vertical_deviation:
                horizontal.append((start, end))
        return set(angled)

    @classmethod
    def out_of_square_segment_label(
        cls,
        start: tuple[float, float],
        end: tuple[float, float],
        inches_per_unit: float = 1.0,
    ) -> str:
        amount = cls.out_of_square_segment_amount(start, end) * inches_per_unit
        return f"{cls.format_inches(amount)} OOS"

    @staticmethod
    def out_of_square_segment_amount(start: tuple[float, float], end: tuple[float, float]) -> float:
        dx = abs(end[0] - start[0])
        dy = abs(end[1] - start[1])
        return min(dx, dy)

    @staticmethod
    def format_inches(value: float) -> str:
        nearest_sixteenth = int(round(abs(value) * 16))
        if nearest_sixteenth == 0:
            return f'{abs(value):.3f}"'
        whole = nearest_sixteenth // 16
        numerator = nearest_sixteenth % 16
        if numerator == 0:
            return f'{whole}"'
        divisor = math.gcd(numerator, 16)
        numerator //= divisor
        denominator = 16 // divisor
        if whole:
            return f'{whole}-{numerator}/{denominator}"'
        return f'{numerator}/{denominator}"'

    @staticmethod
    def is_out_of_square_preview_segment(
        start: tuple[float, float],
        end: tuple[float, float],
        long_side: float,
        inches_per_unit: float = 1.0,
    ) -> bool:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        safe_inches_per_unit = inches_per_unit if inches_per_unit > 0 else 1.0
        if length < max(4.0 / safe_inches_per_unit, long_side * 0.12):
            return False
        angle = math.degrees(math.atan2(dy, dx))
        deviation = abs(programmer.normalize_axis_deviation(angle))
        deviation = min(deviation, abs(programmer.normalize_axis_deviation(angle - 90)))
        amount = ShowerProgrammerApp.out_of_square_segment_amount(start, end) * inches_per_unit
        return deviation >= 0.015 or amount >= 0.03125

    @staticmethod
    def dxf_inches_per_unit(path: Path) -> float:
        insunits = ShowerProgrammerApp.dxf_insunits(path)
        return {
            "1": 1.0,  # inches
            "2": 12.0,  # feet
            "4": 1.0 / 25.4,  # millimeters
            "5": 1.0 / 2.54,  # centimeters
            "6": 39.37007874015748,  # meters
        }.get(insunits, 1.0)

    @staticmethod
    def dxf_unit_label(path: Path) -> str:
        return {
            "1": "in",
            "2": "ft",
            "4": "mm",
            "5": "cm",
            "6": "m",
        }.get(ShowerProgrammerApp.dxf_insunits(path), "units")

    @staticmethod
    def dxf_units_text(unit_label: str, inches_per_unit: float) -> str:
        if unit_label == "in" and abs(inches_per_unit - 1.0) <= 1e-9:
            return "DXF units: inches"
        if unit_label == "mm":
            return "DXF units: millimeters"
        return f"DXF units: {unit_label}"

    @staticmethod
    def dxf_insunits(path: Path) -> str:
        try:
            pairs = programmer.read_dxf_pairs(path)
        except Exception:
            return "1"
        for index, pair in enumerate(pairs):
            if pair[0].strip() != "9" or pair[1].strip().upper() != "$INSUNITS":
                continue
            for target in range(index + 1, min(index + 8, len(pairs))):
                code = pairs[target][0].strip()
                if code == "9":
                    break
                if code == "70":
                    return pairs[target][1].strip()
        return "1"

    @classmethod
    def dxf_dimension_text(cls, width: float, height: float, unit_label: str, inches_per_unit: float) -> str:
        if abs(inches_per_unit - 1.0) <= 1e-9 and unit_label == "in":
            return f"{width:g} x {height:g} in"
        width_inches = width * inches_per_unit
        height_inches = height * inches_per_unit
        return (
            f"{width:g} x {height:g} {unit_label} "
            f"({cls.format_inches(width_inches)} x {cls.format_inches(height_inches)})"
        )

    @staticmethod
    def format_degrees(value: float) -> str:
        text = f"{value:.8f}".rstrip("0").rstrip(".")
        return text if text else "0"

    @staticmethod
    def panel_rotation_summary(panel: programmer.Panel) -> str:
        base = panel.rotation_degrees
        if base is None:
            return "DXF rotation: none"
        total = base + panel.angle_correction_degrees
        if abs(panel.angle_correction_degrees) > 1e-9:
            return (
                f"DXF rotation: {ShowerProgrammerApp.format_degrees(total)} deg "
                f"({ShowerProgrammerApp.format_degrees(base)} + "
                f"{ShowerProgrammerApp.format_degrees(panel.angle_correction_degrees)} correction)"
            )
        return f"DXF rotation: {ShowerProgrammerApp.format_degrees(base)} deg"

    def save_editor_state_positions(
        self,
        job: programmer.Job,
        state: dict[str, Any],
        config: dict[str, object],
        parent: tk.Widget | None,
        show_no_edits: bool = True,
    ) -> bool:
        dirty = state.get("dirty")
        if not dirty:
            if show_no_edits:
                messagebox.showinfo("No edits", "Nothing has been moved yet.", parent=parent)
            return False
        try:
            data = self.load_manual_overrides()
            item_overrides = data.setdefault("item_overrides", {})
            if not isinstance(item_overrides, dict):
                item_overrides = {}
                data["item_overrides"] = item_overrides
            order_overrides = item_overrides.setdefault(job.aw_order, {})
            if not isinstance(order_overrides, dict):
                order_overrides = {}
                item_overrides[job.aw_order] = order_overrides
            for item_number, key in sorted(dirty):
                position = state.get("positions", {}).get((item_number, key))
                if position is None:
                    continue
                panel = next(panel for panel in job.panels if panel.item == item_number)
                item_override = order_overrides.setdefault(str(item_number), {})
                if not isinstance(item_override, dict):
                    item_override = {}
                    order_overrides[str(item_number)] = item_override
                if key == "label":
                    item_override["label_x"] = round(float(position["x"]), 3)
                    item_override["label_y"] = round(float(position["y"]), 3)
                elif key == "indicator":
                    corner = str(position.get("indicator_corner") or panel.indicator_corner or "").strip().lower()
                    if corner:
                        raw_corner = str(position.get("raw_indicator_corner") or corner).strip().lower()
                        if (
                            (panel.machine.startswith("DENVER") or panel.machine == "WJ")
                            and raw_corner in {"bottom_left", "bottom_right", "top_left", "top_right"}
                        ):
                            corner = raw_corner
                            item_override["manual_indicator_corner"] = True
                        else:
                            item_override.pop("manual_indicator_corner", None)
                        item_override["indicator_x"] = round(float(position["x"]), 3)
                        item_override["indicator_y"] = round(float(position["y"]), 3)
                        panel.indicator_x = float(position["x"])
                        panel.indicator_y = float(position["y"])
                        programmer.apply_indicator_corner_override_with_options(
                            panel,
                            corner,
                            config,
                            allow_manual_denver_corner=bool(item_override.get("manual_indicator_corner")),
                            allow_manual_waterjet_corner=bool(item_override.get("manual_indicator_corner")),
                        )
                        item_override["indicator_corner"] = corner
                        if panel.rotation_degrees is not None:
                            item_override["rotation_degrees"] = round(float(panel.rotation_degrees), 6)
                        if panel.machine == "DENVER 1" and programmer.has_door_programming_evidence(panel, config):
                            if panel.hinge_side:
                                item_override["hinge_side"] = panel.hinge_side
                            item_override["hinges_up"] = bool(panel.hinges_up)
                        else:
                            item_override.pop("hinge_side", None)
                            item_override.pop("hinges_up", None)
                elif key == "diamon_fusion":
                    item_override["diamon_fusion_x"] = round(float(position["x"]), 3)
                    item_override["diamon_fusion_y"] = round(float(position["y"]), 3)
                elif key == "remake":
                    item_override["remake_x"] = round(float(position["x"]), 3)
                    item_override["remake_y"] = round(float(position["y"]), 3)
            self.save_manual_overrides(data)
            state["dirty"].clear()
            state["positions"].clear()
            return True
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=parent)
            return False

    def set_mark_hidden(self, aw_order: str, item_number: int, mark_key: str, hidden: bool) -> None:
        field_by_key = {
            "label": "hide_label",
            "indicator": "hide_indicator",
            "diamon_fusion": "hide_diamon_fusion",
            "remake": "hide_remake",
        }
        field = field_by_key.get(mark_key)
        if field is None:
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        if hidden:
            item_override[field] = True
        else:
            item_override.pop(field, None)
            if mark_key == "indicator":
                for key in ("indicator_x", "indicator_y", "manual_indicator_corner"):
                    item_override.pop(key, None)
        self.save_manual_overrides(data)

    def set_manual_x_override(self, aw_order: str, item_number: int, enabled: bool) -> None:
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        if enabled:
            item_override["manual_x"] = True
        else:
            item_override.pop("manual_x", None)
        self.save_manual_overrides(data)

    def set_mark_text_override(self, aw_order: str, item_number: int, mark_key: str, value: str) -> None:
        field_by_key = {
            "label": "label_text",
            "diamon_fusion": "diamon_fusion_text",
            "remake": "remake_text",
        }
        field = field_by_key.get(mark_key)
        if field is None:
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        text = value.replace("\\n", "\n").strip()
        if text:
            item_override[field] = text
        else:
            item_override.pop(field, None)
        self.save_manual_overrides(data)

    def set_label_text_and_detect_machine(
        self,
        aw_order: str,
        item_number: int,
        value: str,
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> None:
        text = value.replace("\\n", "\n").strip()
        if not text:
            return
        self.set_mark_hidden(aw_order, item_number, "label", hidden=False)
        self.set_mark_text_override(aw_order, item_number, "label", text)
        upper = text.upper()
        if "WATER" in upper or re.search(r"\bWJ\b", upper):
            self.set_indicator_machine_override(aw_order, item_number, "WJ", panel, config)
        elif "DENVER 1" in upper or "DENVER1" in upper:
            self.set_indicator_machine_override(aw_order, item_number, "DENVER 1", panel, config)
        elif "DENVER 2" in upper or "DENVER2" in upper:
            self.set_indicator_machine_override(aw_order, item_number, "DENVER 2", panel, config)
        elif "DENVER" in upper:
            self.set_indicator_machine_override(aw_order, item_number, "DENVER", panel, config)

    @staticmethod
    def flipped_indicator_corner(corner: str | None) -> str:
        return {
            "top_left": "top_right",
            "top_right": "top_left",
            "bottom_right": "bottom_left",
            "bottom_left": "bottom_right",
        }.get(str(corner or "").strip().lower(), "top_right")

    def set_indicator_corner_override(
        self,
        aw_order: str,
        item_number: int,
        corner: str,
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> None:
        corner = str(corner).strip().lower()
        if corner not in {"bottom_left", "bottom_right", "top_left", "top_right"}:
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override

        programmer.apply_indicator_corner_override_with_options(
            panel,
            corner,
            config,
            allow_manual_denver_corner=True,
            allow_manual_waterjet_corner=True,
        )
        item_override["indicator_corner"] = corner
        item_override["manual_indicator_corner"] = True
        item_override["skip_dxf"] = False
        item_override.pop("hide_indicator", None)
        item_override.pop("indicator_x", None)
        item_override.pop("indicator_y", None)
        if panel.rotation_degrees is not None:
            item_override["rotation_degrees"] = round(float(panel.rotation_degrees), 6)
        if panel.machine == "DENVER 1" and programmer.has_door_programming_evidence(panel, config):
            if panel.hinge_side:
                item_override["hinge_side"] = panel.hinge_side
            item_override["hinges_up"] = bool(panel.hinges_up)
        else:
            item_override.pop("hinge_side", None)
            item_override.pop("hinges_up", None)
        self.save_manual_overrides(data)

    def set_indicator_machine_override(
        self,
        aw_order: str,
        item_number: int,
        machine_kind: str,
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> None:
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override

        kind = machine_kind.strip().upper()
        if kind == "WJ":
            item_override["machine"] = "WJ"
            item_override["indicator_corner"] = programmer.default_waterjet_indicator_corner(panel)
            item_override["rotation_degrees"] = -90 if panel.height and panel.width and panel.height > panel.width else 0
        else:
            if kind in {"DENVER 1", "DENVER1"}:
                machine = "DENVER 1"
            elif kind in {"DENVER 2", "DENVER2"}:
                machine = "DENVER 2"
            else:
                machine = "DENVER 1" if programmer.has_door_programming_evidence(panel, config) else "DENVER 2"
            rotation = 90 if panel.height and panel.width and panel.height > panel.width else 0
            item_override["machine"] = machine
            item_override["indicator_corner"] = programmer.denver_grabber_corner_for_panel(panel, rotation)
            item_override["rotation_degrees"] = rotation

        item_override["skip_dxf"] = False
        item_override.pop("hide_indicator", None)
        item_override.pop("indicator_x", None)
        item_override.pop("indicator_y", None)
        item_override.pop("manual_indicator_corner", None)
        item_override.pop("hinge_side", None)
        item_override.pop("hinges_up", None)
        self.save_manual_overrides(data)

    def set_mark_size_override(
        self,
        aw_order: str,
        item_number: int,
        mark_key: str,
        direction: int,
        obj: dict[str, Any],
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> float:
        pdf_cfg = config.get("pdf", {})
        if not isinstance(pdf_cfg, dict):
            pdf_cfg = {}

        if mark_key == "label":
            field = "label_font_size"
            current = panel.label_font_size or float(obj.get("font_size") or pdf_cfg.get("label_font_size", 21))
            step = 2.0
            minimum = 6.0
        elif mark_key == "diamon_fusion":
            field = "diamon_fusion_font_size"
            current = panel.diamon_fusion_font_size or float(obj.get("font_size") or pdf_cfg.get("diamon_fusion_font_size", 36))
            step = 4.0
            minimum = 10.0
        elif mark_key == "remake":
            field = "remake_font_size"
            remake_cfg = pdf_cfg.get("remake", {}) if isinstance(pdf_cfg.get("remake", {}), dict) else {}
            current = panel.remake_font_size or float(obj.get("font_size") or remake_cfg.get("font_size", 40))
            step = 4.0
            minimum = 10.0
        elif mark_key == "indicator":
            if str(obj.get("machine") or panel.machine).upper() == "WJ":
                field = "waterjet_indicator_size"
                current = panel.waterjet_indicator_size or float(obj.get("size") or pdf_cfg.get("waterjet_indicator_size", 30))
                step = 4.0
                minimum = 8.0
            else:
                field = "indicator_size"
                current = panel.indicator_size or float(obj.get("size") or pdf_cfg.get("indicator_size", 18))
                step = 2.0
                minimum = 6.0
        else:
            raise ValueError(f"Unsupported mark size key: {mark_key}")

        new_size = max(minimum, float(current) + step * (1 if direction > 0 else -1))

        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override

        item_override[field] = round(new_size, 3)
        self.save_manual_overrides(data)
        return new_size

    def check_for_updates(self) -> None:
        repo = self.update_install_root()
        git = shutil.which("git")
        # A PyInstaller executable cannot use the source checkout path inside the
        # bundle. In frozen mode, update the executable folder with the GitHub zip
        # updater instead of trying to pull a developer repository.
        if getattr(sys, "frozen", False) or not git or not (repo / ".git").exists():
            self.check_for_updates_without_git(repo)
            return
        try:
            status = subprocess.run(
                [git, "status", "--porcelain"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            fetch = subprocess.run(
                [git, "fetch", "origin", "main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=90,
            )
            if fetch.returncode != 0:
                messagebox.showerror("Update check failed", fetch.stderr.strip() or fetch.stdout.strip())
                return
            current = subprocess.run(
                [git, "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            remote = subprocess.run(
                [git, "rev-parse", "origin/main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            base = subprocess.run(
                [git, "merge-base", "HEAD", "origin/main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
        except Exception as exc:
            messagebox.showerror("Update check failed", str(exc))
            return

        if current == remote:
            self.status_var.set("Program is already up to date with origin/main.")
            messagebox.showinfo("No updates", "This program is already up to date with the GitHub main branch.")
            return
        if status:
            self.status_var.set("Updates are available, but local changes must be committed or stashed first.")
            messagebox.showwarning(
                "Updates available",
                "GitHub has newer code, but this working folder has local changes. "
                "Commit or stash them before using automatic update.",
            )
            return
        if base == current:
            if not messagebox.askyesno("Update program?", "Updates are available on GitHub main. Pull them now?"):
                return
            pull = subprocess.run(
                [git, "pull", "--ff-only", "origin", "main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=120,
            )
            if pull.returncode != 0:
                messagebox.showerror("Update failed", pull.stderr.strip() or pull.stdout.strip())
                return
            self.write_update_metadata(repo, remote, "git")
            self.status_var.set("Program updated from GitHub main. Restart the GUI to use the new code.")
            messagebox.showinfo("Updated", "The program was updated. Close and reopen the GUI to use the new code.")
            return
        if base == remote:
            messagebox.showinfo("Local branch ahead", "This folder has local commits that are not on GitHub main.")
            return
        messagebox.showwarning(
            "Branches diverged",
            "This folder and GitHub main both have different changes. Update manually with Git.",
        )

    def update_install_root(self) -> Path:
        if getattr(sys, "frozen", False):
            executable_dir = Path(sys.executable).resolve().parent
            parent = executable_dir.parent
            for candidate in (parent, executable_dir):
                if (candidate / "Backend").exists() and (candidate / "Assets").exists():
                    return candidate
                if (candidate / "Input").exists() and (candidate / "Output").exists() and (candidate / "Assets").exists():
                    return candidate
            return executable_dir
        return programmer.project_root()

    @staticmethod
    def frozen_app_dir() -> Path | None:
        if not getattr(sys, "frozen", False):
            return None
        return Path(sys.executable).resolve().parent

    @staticmethod
    def should_update_source_tree(repo: Path, app_dir: Path | None) -> bool:
        if app_dir is None:
            return True
        try:
            if repo.resolve() == app_dir.resolve():
                return False
        except OSError:
            return False
        return (repo / "Backend").exists() or (repo / "Assets").exists()

    def check_for_updates_without_git(self, repo: Path) -> None:
        owner, repo_name = self.github_update_repo(repo)
        try:
            latest_sha, latest_date = self.github_latest_commit(owner, repo_name, self.GITHUB_UPDATE_BRANCH)
        except Exception as exc:
            messagebox.showerror("Update check failed", f"Could not check GitHub for updates:\n\n{exc}")
            return

        current_sha = self.current_update_revision(repo)
        if current_sha and current_sha == latest_sha:
            self.status_var.set("Program is already up to date with GitHub main.")
            messagebox.showinfo("No updates", "This program is already up to date with the GitHub main branch.")
            return
        if getattr(sys, "frozen", False):
            remote_exe_hash = self.github_packaged_exe_hash(owner, repo_name, self.GITHUB_UPDATE_BRANCH)
            local_exe_hash = self.current_packaged_exe_hash()
            if remote_exe_hash and local_exe_hash and remote_exe_hash == local_exe_hash:
                self.write_update_metadata(repo, latest_sha, "bundle-match")
                self.status_var.set("Program is already up to date with the packaged GitHub release.")
                messagebox.showinfo("No updates", "This packaged program is already up to date.")
                return

        if current_sha:
            prompt = (
                "Updates are available on GitHub main.\n\n"
                f"Latest update: {latest_date or latest_sha[:12]}\n\n"
                "Download, install, and restart the program now?"
            )
        else:
            prompt = (
                "Git is not installed, so this computer cannot compare local Git history.\n\n"
                f"Latest GitHub update: {latest_date or latest_sha[:12]}\n\n"
                "Download, install, and restart with the latest GitHub main files now?"
            )
        if not messagebox.askyesno("Update program?", prompt):
            return

        try:
            self.install_update_zip(repo, owner, repo_name, self.GITHUB_UPDATE_BRANCH, latest_sha)
        except Exception as exc:
            messagebox.showerror("Update failed", str(exc))
            return
        if self.pending_update_script is not None:
            try:
                self.status_var.set("Update downloaded. Restarting to install it...")
                subprocess.Popen(["cmd", "/c", str(self.pending_update_script)], cwd=str(self.pending_update_script.parent))
                self.on_close()
            except Exception as exc:
                messagebox.showerror("Update restart failed", str(exc))
            return
        self.write_update_metadata(repo, latest_sha, "zip")
        if getattr(sys, "frozen", False):
            self.status_var.set("Support files were updated. A new EXE was not found in the update package.")
            messagebox.showinfo(
                "Update downloaded",
                "The update package was installed into this program folder, but it did not contain a replacement EXE. "
                "Bundled executable code changes only take effect when the GitHub update package includes a new EXE/release bundle."
            )
            return
        self.status_var.set("Program updated from GitHub main. Restart the GUI to use the new code.")
        messagebox.showinfo("Updated", "The program was updated. Close and reopen the GUI to use the new code.")

    def github_update_repo(self, repo: Path) -> tuple[str, str]:
        config_path = repo / ".git" / "config"
        if config_path.exists():
            try:
                text = config_path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"url\s*=\s*(?:https://github\.com/|git@github\.com:)([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$", text, re.MULTILINE)
                if match:
                    return match.group(1), match.group(2)
            except OSError:
                pass
        return self.GITHUB_UPDATE_OWNER, self.GITHUB_UPDATE_REPO

    @staticmethod
    def github_json(url: str) -> dict[str, object]:
        data = ShowerProgrammerApp.download_text(url, timeout=45)
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise RuntimeError("GitHub returned an unexpected response.")
        return parsed

    def github_latest_commit(self, owner: str, repo_name: str, branch: str) -> tuple[str, str]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{branch}"
        data = self.github_json(url)
        sha = str(data.get("sha", "")).strip()
        if not sha:
            raise RuntimeError("GitHub did not return a commit id.")
        commit = data.get("commit", {})
        latest_date = ""
        if isinstance(commit, dict):
            committer = commit.get("committer", {})
            if isinstance(committer, dict):
                latest_date = str(committer.get("date", "")).strip()
        return sha, latest_date

    @staticmethod
    def github_packaged_exe_hash(owner: str, repo_name: str, branch: str) -> str:
        url = (
            f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/"
            "Shower%20Programmer/.shower_update.json"
        )
        try:
            data = json.loads(ShowerProgrammerApp.download_text(url, timeout=30))
        except Exception:
            return ""
        return str(data.get("exe_sha256", "")).strip().lower() if isinstance(data, dict) else ""

    @staticmethod
    def current_packaged_exe_hash() -> str:
        if not getattr(sys, "frozen", False):
            return ""
        executable = Path(sys.executable)
        try:
            digest = hashlib.sha256()
            with executable.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest().lower()
        except OSError:
            return ""

    def current_update_revision(self, repo: Path) -> str:
        for metadata_path in self.update_metadata_paths(repo):
            if not metadata_path.exists():
                continue
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                sha = str(data.get("sha", "")).strip() if isinstance(data, dict) else ""
                if sha:
                    return sha
            except Exception:
                pass
        app_dir = self.frozen_app_dir()
        if app_dir is not None:
            packaged_metadata = app_dir / ".shower_update.json"
            if packaged_metadata.exists():
                try:
                    data = json.loads(packaged_metadata.read_text(encoding="utf-8"))
                    sha = str(data.get("sha", "")).strip() if isinstance(data, dict) else ""
                    if sha:
                        return sha
                except Exception:
                    pass
        return self.git_head_without_git(repo)

    @staticmethod
    def update_metadata_paths(repo: Path) -> list[Path]:
        paths = [
            repo / "Output" / "update_metadata.json",
            repo / ".shower_update.json",
        ]
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "Shower Programmer" / "update_metadata.json")
        return paths

    @staticmethod
    def writable_update_metadata_path(repo: Path) -> Path | None:
        for metadata_path in ShowerProgrammerApp.update_metadata_paths(repo):
            try:
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", delete=True, dir=str(metadata_path.parent), encoding="utf-8"):
                    pass
                return metadata_path
            except Exception:
                continue
        return None

    @staticmethod
    def update_metadata_payload(sha: str, method: str) -> dict[str, str]:
        return {
            "sha": sha,
            "method": method,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def git_head_without_git(repo: Path) -> str:
        git_dir = repo / ".git"
        head_path = git_dir / "HEAD"
        if not head_path.exists():
            return ""
        try:
            head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""
        if not head.startswith("ref:"):
            return head
        ref = head.split(":", 1)[1].strip().replace("/", os.sep)
        ref_path = git_dir / ref
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                return ""
        packed_refs = git_dir / "packed-refs"
        if packed_refs.exists():
            try:
                for line in packed_refs.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref.replace(os.sep, "/"):
                        return parts[0]
            except OSError:
                return ""
        return ""

    def install_update_zip(self, repo: Path, owner: str, repo_name: str, branch: str, latest_sha: str) -> None:
        updates_dir = self.update_work_dir(repo) / f"update_{datetime.now():%Y%m%d_%H%M%S}"
        updates_dir.mkdir(parents=True, exist_ok=True)
        archive_path = updates_dir / "main.zip"
        extract_dir = updates_dir / "extract"
        backup_dir = updates_dir / "backup"
        zip_url = f"https://codeload.github.com/{owner}/{repo_name}/zip/refs/heads/{branch}"
        self.pending_update_script = None
        self.pending_update_message = ""
        self.status_var.set("Downloading update from GitHub...")
        self.download_file(zip_url, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)
        roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not roots:
            raise RuntimeError("Downloaded update package was empty.")
        source_root = roots[0]
        self.status_var.set("Installing update files...")
        if getattr(sys, "frozen", False):
            current_exe = Path(sys.executable).resolve()
            app_dir = current_exe.parent
            staged_metadata = updates_dir / "update_metadata.json"
            staged_metadata.write_text(
                json.dumps(self.update_metadata_payload(latest_sha, "zip"), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            metadata_target = self.writable_update_metadata_path(repo)
            replacement_app_dir = self.find_replacement_app_bundle(source_root, current_exe.name)
            if replacement_app_dir is not None:
                self.pending_update_script = self.stage_app_bundle_replacement(
                    app_dir,
                    replacement_app_dir,
                    current_exe.name,
                    updates_dir,
                    staged_metadata,
                    metadata_target,
                )
                self.pending_update_message = (
                    "Downloaded a replacement Shower Programmer app folder. "
                    "The app will close, replace the bundled EXE and _internal runtime folder, and reopen."
                )
                if self.should_update_source_tree(repo, app_dir):
                    self.copy_update_tree(source_root, repo, backup_dir, skip_names={replacement_app_dir.name})
                (updates_dir / "installed_commit.txt").write_text(latest_sha + "\n", encoding="utf-8")
                return
            replacement_exe = self.find_replacement_exe(source_root, current_exe.name)
            if replacement_exe is not None:
                self.pending_update_script = self.stage_exe_replacement(
                    current_exe,
                    replacement_exe,
                    updates_dir,
                    staged_metadata,
                    metadata_target,
                )
                self.pending_update_message = (
                    f"Downloaded a replacement executable for {current_exe.name}. "
                    "The app will close, replace the EXE in this folder, and reopen."
                )
                if self.should_update_source_tree(repo, app_dir):
                    self.copy_update_tree(source_root, repo, backup_dir, skip_names={app_dir.name})
                (updates_dir / "installed_commit.txt").write_text(latest_sha + "\n", encoding="utf-8")
                return
            if not self.should_update_source_tree(repo, app_dir):
                raise RuntimeError(
                    "The GitHub update was downloaded, but it did not contain a packaged "
                    "'Shower Programmer' folder or replacement EXE. Rebuild and publish the "
                    "folder EXE before using Check for Updates on packaged computers."
                )
        self.copy_update_tree(source_root, repo, backup_dir)
        (updates_dir / "installed_commit.txt").write_text(latest_sha + "\n", encoding="utf-8")

    def update_work_dir(self, repo: Path) -> Path:
        candidates = [repo / "Output" / "Updates", self.internal_output_dir() / "Updates"]
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Shower Programmer" / "Updates")
        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", delete=True, dir=str(candidate), encoding="utf-8"):
                    pass
                return candidate
            except Exception:
                continue
        fallback = Path(tempfile.gettempdir()) / "Shower Programmer Updates"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    @staticmethod
    def find_replacement_app_bundle(source_root: Path, current_exe_name: str) -> Path | None:
        candidates: list[Path] = []
        for path in source_root.rglob(current_exe_name):
            if not path.is_file() or path.suffix.lower() != ".exe":
                continue
            parent = path.parent
            if (parent / "_internal").is_dir():
                candidates.append(parent)
        if not candidates:
            return None
        candidates.sort(
            key=lambda path: (
                0 if path.name.lower() == "shower programmer" else 1,
                0 if any(part.lower() in {"dist", "release"} for part in path.parts) else 1,
                len(path.parts),
            )
        )
        return candidates[0]

    @staticmethod
    def find_replacement_exe(source_root: Path, current_exe_name: str) -> Path | None:
        exact = [
            path
            for path in source_root.rglob("*.exe")
            if path.is_file() and path.name.lower() == current_exe_name.lower()
        ]
        if exact:
            exact.sort(key=lambda path: (0 if "dist" in [part.lower() for part in path.parts] else 1, len(path.parts)))
            return exact[0]
        shower_exes = [
            path
            for path in source_root.rglob("*.exe")
            if path.is_file() and "shower" in path.name.lower() and "program" in path.name.lower()
        ]
        if shower_exes:
            shower_exes.sort(key=lambda path: (0 if "dist" in [part.lower() for part in path.parts] else 1, len(path.parts)))
            return shower_exes[0]
        return None

    @staticmethod
    def stage_app_bundle_replacement(
        app_dir: Path,
        replacement_app_dir: Path,
        current_exe_name: str,
        updates_dir: Path,
        staged_metadata: Path | None = None,
        metadata_target: Path | None = None,
    ) -> Path:
        replacement_exe = replacement_app_dir / current_exe_name
        replacement_internal = replacement_app_dir / "_internal"
        if not replacement_exe.is_file() or replacement_exe.stat().st_size <= 0:
            raise RuntimeError(f"The downloaded app bundle is missing {current_exe_name}.")
        if not replacement_internal.is_dir() or not any(replacement_internal.iterdir()):
            raise RuntimeError("The downloaded app bundle is missing its _internal runtime folder.")
        staged_dir = updates_dir / "staged_app"
        staged_app_dir = staged_dir / app_dir.name
        if staged_app_dir.exists():
            shutil.rmtree(staged_app_dir)
        shutil.copytree(replacement_app_dir, staged_app_dir)
        script_path = updates_dir / "apply_update.cmd"
        backup_dir = updates_dir / "backup_app"
        pid = os.getpid()
        metadata_commands = ""
        if staged_metadata is not None and metadata_target is not None:
            metadata_commands = (
                f'if not exist "{metadata_target.parent}" mkdir "{metadata_target.parent}" >nul 2>nul\n'
                f'copy /Y "{staged_metadata}" "{metadata_target}" >nul\n'
            )
        script = (
            "@echo off\n"
            "setlocal\n"
            f"set \"APP_DIR={app_dir}\"\n"
            f"set \"STAGED_APP={staged_app_dir}\"\n"
            f"set \"EXE_NAME={current_exe_name}\"\n"
            f"set \"BACKUP_DIR={backup_dir}\"\n"
            f"set \"PID={pid}\"\n"
            "\n"
            ":wait_for_app\n"
            "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul\n"
            "if not errorlevel 1 (\n"
            "    timeout /t 1 /nobreak >nul\n"
            "    goto wait_for_app\n"
            ")\n"
            "\n"
            "if exist \"%BACKUP_DIR%\" rmdir /S /Q \"%BACKUP_DIR%\"\n"
            "mkdir \"%BACKUP_DIR%\" >nul 2>nul\n"
            "if exist \"%APP_DIR%\\%EXE_NAME%\" copy /Y \"%APP_DIR%\\%EXE_NAME%\" \"%BACKUP_DIR%\\%EXE_NAME%\" >nul\n"
            "if exist \"%APP_DIR%\\_internal\" robocopy \"%APP_DIR%\\_internal\" \"%BACKUP_DIR%\\_internal\" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul\n"
            "\n"
            "if exist \"%APP_DIR%\\_internal\" rmdir /S /Q \"%APP_DIR%\\_internal\"\n"
            "robocopy \"%STAGED_APP%\" \"%APP_DIR%\" /E /R:5 /W:1 /NFL /NDL /NJH /NJS /NP\n"
            "set \"COPY_CODE=%ERRORLEVEL%\"\n"
            "if %COPY_CODE% GEQ 8 goto update_failed\n"
            "\n"
            f"{metadata_commands}"
            "start \"\" \"%APP_DIR%\\%EXE_NAME%\"\n"
            "exit /b 0\n"
            "\n"
            ":update_failed\n"
            "if exist \"%APP_DIR%\\_internal\" rmdir /S /Q \"%APP_DIR%\\_internal\"\n"
            "if exist \"%BACKUP_DIR%\\_internal\" robocopy \"%BACKUP_DIR%\\_internal\" \"%APP_DIR%\\_internal\" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul\n"
            "if exist \"%BACKUP_DIR%\\%EXE_NAME%\" copy /Y \"%BACKUP_DIR%\\%EXE_NAME%\" \"%APP_DIR%\\%EXE_NAME%\" >nul\n"
            "start \"\" \"%APP_DIR%\\%EXE_NAME%\"\n"
            "echo The update could not be installed. The previous version was restored.\n"
            "echo Update files and logs remain in \"%~dp0\".\n"
            "pause\n"
            "exit /b 1\n"
        )
        script_path.write_text(script, encoding="utf-8")
        return script_path

    @staticmethod
    def stage_exe_replacement(
        current_exe: Path,
        replacement_exe: Path,
        updates_dir: Path,
        staged_metadata: Path | None = None,
        metadata_target: Path | None = None,
    ) -> Path:
        if not replacement_exe.is_file() or replacement_exe.stat().st_size <= 0:
            raise RuntimeError("The downloaded replacement EXE is empty or missing.")
        staged_dir = updates_dir / "staged_exe"
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged_exe = staged_dir / current_exe.name
        shutil.copy2(replacement_exe, staged_exe)
        script_path = updates_dir / "apply_update.cmd"
        backup_exe = updates_dir / "backup_exe" / current_exe.name
        pid = os.getpid()
        metadata_commands = ""
        if staged_metadata is not None and metadata_target is not None:
            metadata_commands = (
                f'if not exist "{metadata_target.parent}" mkdir "{metadata_target.parent}" >nul 2>nul\n'
                f'copy /Y "{staged_metadata}" "{metadata_target}" >nul\n'
            )
        script = (
            "@echo off\n"
            "setlocal\n"
            f"set \"CURRENT_EXE={current_exe}\"\n"
            f"set \"STAGED_EXE={staged_exe}\"\n"
            f"set \"BACKUP_EXE={backup_exe}\"\n"
            f"set \"PID={pid}\"\n"
            "\n"
            ":wait_for_app\n"
            "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul\n"
            "if not errorlevel 1 (\n"
            "    timeout /t 1 /nobreak >nul\n"
            "    goto wait_for_app\n"
            ")\n"
            "\n"
            "if not exist \"%~dp0backup_exe\" mkdir \"%~dp0backup_exe\" >nul 2>nul\n"
            "if exist \"%CURRENT_EXE%\" copy /Y \"%CURRENT_EXE%\" \"%BACKUP_EXE%\" >nul\n"
            "copy /Y \"%STAGED_EXE%\" \"%CURRENT_EXE%\"\n"
            "if errorlevel 1 (\n"
            "    if exist \"%BACKUP_EXE%\" copy /Y \"%BACKUP_EXE%\" \"%CURRENT_EXE%\" >nul\n"
            "    start \"\" \"%CURRENT_EXE%\"\n"
            "    echo The update could not be installed. The previous EXE was restored.\n"
            "    pause\n"
            "    exit /b 1\n"
            ")\n"
            f"{metadata_commands}"
            "start \"\" \"%CURRENT_EXE%\"\n"
            "exit /b 0\n"
        )
        script_path.write_text(script, encoding="utf-8")
        return script_path

    @staticmethod
    def download_file(url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "Showers-Programmer-Updater"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except Exception as exc:
            try:
                ShowerProgrammerApp.download_file_with_powershell(url, destination, timeout=120)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Python HTTPS download failed:\n{exc}\n\n"
                    f"PowerShell HTTPS fallback also failed:\n{fallback_exc}"
                ) from exc

    @staticmethod
    def download_text(url: str, timeout: int) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "Showers-Programmer-Updater"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            try:
                return ShowerProgrammerApp.download_text_with_powershell(url, timeout=timeout)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Python HTTPS request failed:\n{exc}\n\n"
                    f"PowerShell HTTPS fallback also failed:\n{fallback_exc}"
                ) from exc

    @staticmethod
    def powershell_exe() -> str:
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise RuntimeError("PowerShell was not found for HTTPS fallback.")
        return exe

    @staticmethod
    def powershell_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def download_text_with_powershell(url: str, timeout: int) -> str:
        url_literal = ShowerProgrammerApp.powershell_literal(url)
        script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$client = New-Object Net.WebClient
$client.Headers.Set('User-Agent', 'Showers-Programmer-Updater')
try {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $client.DownloadString({url_literal})
}} finally {{
    $client.Dispose()
}}
"""
        result = subprocess.run(
            [ShowerProgrammerApp.powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=max(timeout, 30),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PowerShell download failed.")
        return result.stdout

    @staticmethod
    def download_file_with_powershell(url: str, destination: Path, timeout: int) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        url_literal = ShowerProgrammerApp.powershell_literal(url)
        destination_literal = ShowerProgrammerApp.powershell_literal(str(destination))
        script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$client = New-Object Net.WebClient
$client.Headers.Set('User-Agent', 'Showers-Programmer-Updater')
try {{
    $client.DownloadFile({url_literal}, {destination_literal})
}} finally {{
    $client.Dispose()
}}
"""
        result = subprocess.run(
            [ShowerProgrammerApp.powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=max(timeout, 30),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PowerShell download failed.")

    def copy_update_tree(self, source_root: Path, repo: Path, backup_dir: Path, skip_names: set[str] | None = None) -> None:
        skip_root_names = {".git", ".github", ".agents", ".codex", "Input", "Output", "build", "__pycache__"}
        if skip_names:
            skip_root_names.update(skip_names)
        for source in source_root.iterdir():
            if source.name in skip_root_names:
                continue
            self.copy_update_item(source, repo / source.name, backup_dir / source.name)

    def copy_update_item(self, source: Path, target: Path, backup: Path) -> None:
        if source.name == "__pycache__" or source.suffix.lower() in {".pyc", ".pyo"}:
            return
        if getattr(sys, "frozen", False) and source.suffix.lower() == ".exe":
            try:
                if target.resolve() == Path(sys.executable).resolve():
                    return
            except OSError:
                return
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                self.copy_update_item(child, target / child.name, backup / child.name)
            return
        if target.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    @staticmethod
    def write_update_metadata(repo: Path, sha: str, method: str) -> None:
        metadata = ShowerProgrammerApp.update_metadata_payload(sha, method)
        for metadata_path in ShowerProgrammerApp.update_metadata_paths(repo):
            try:
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
                return
            except Exception:
                continue

    def send_sketches_to_shop(self) -> None:
        self.send_outputs_to_shop(include_sketches=True, include_programs=False, archive_inputs=False, review_before_send=True)

    def send_programs_to_shop(self) -> None:
        self.send_outputs_to_shop(include_sketches=False, include_programs=True, archive_inputs=False, review_before_send=True)

    def send_all_to_shop(self) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            row_ids = self.tree.get_children()
            if row_ids and not self.tree.selection():
                self.tree.selection_set(*row_ids)
                self.tree.focus(row_ids[0])
                self.tree.see(row_ids[0])
                self.status_var.set(f"No orders were selected, so Review / Send is using all {len(row_ids)} visible order(s).")
            elif self.tree.selection():
                self.status_var.set(f"Preparing Review / Send for {len(self.tree.selection())} selected order(s)...")
        except tk.TclError:
            pass
        self.progress.stop()
        self.progress.configure(mode="indeterminate", maximum=100, value=0)
        self.progress.start(12)
        if not self.status_var.get().startswith("Preparing Review / Send") and "Review / Send" not in self.status_var.get():
            self.status_var.set("Preparing Review / Send...")
        self.root.after(
            50,
            lambda: self.send_outputs_to_shop(
                include_sketches=True,
                include_programs=True,
                archive_inputs=True,
                review_before_send=True,
            ),
        )

    def send_outputs_to_shop(
        self,
        *,
        include_sketches: bool,
        include_programs: bool,
        archive_inputs: bool = False,
        review_before_send: bool = False,
    ) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            self.apply_import_source_dir()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            sketch_dir = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
            programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
            aw_orders = self.selected_or_visible_aw_orders()
            if not aw_orders:
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=100, value=0)
                messagebox.showinfo("No orders", "Scan orders first. No scanned orders are available to send.")
                self.status_var.set("No scanned orders are available to send.")
                return
            sketch_paths: list[Path] = []
            dxf_paths: list[Path] = []
            missing: list[str] = []
            if include_sketches:
                sketch_paths = (
                    self.generated_sketch_paths_for_orders(aw_orders, output_dir)
                    if aw_orders
                    else self.generated_sketch_paths(output_dir, sketch_dir)
                )
                if not sketch_paths:
                    missing.append("sketches")
            if include_programs:
                dxf_paths = (
                    self.generated_dxf_paths_for_orders(aw_orders, output_dir)
                    if aw_orders
                    else self.generated_dxf_paths(output_dir, programs_dir)
                )
                if not dxf_paths:
                    missing.append("programs")
            if not sketch_paths and not dxf_paths:
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=100, value=0)
                messagebox.showinfo("Nothing sent", "No matching generated files were found.")
                return
            orders = [self.order_by_aw[aw_order] for aw_order in aw_orders if aw_order in self.order_by_aw]
            order_folder = Path(self.folder_var.get()).resolve()
            process_list_path = Path(self.process_list_var.get()).resolve()
        except Exception as exc:
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100, value=0)
            messagebox.showerror("Send failed", str(exc))
            return

        if review_before_send and orders:
            self.open_send_review_dialog(
                output_dir,
                include_sketches,
                include_programs,
                archive_inputs,
                orders,
                sketch_paths,
                dxf_paths,
                missing,
                order_folder,
                process_list_path,
            )
            return

        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.start_send_outputs_worker(
            sketch_paths,
            dxf_paths,
            missing,
            archive_inputs,
            orders,
            order_folder,
            process_list_path,
            include_sketches=include_sketches,
            include_programs=include_programs,
        )

    def orders_cover_all_scanned_orders(self, orders: list[shower_batch.ProcessOrder]) -> bool:
        selected_aw_orders = {str(order.aw_order) for order in orders if str(order.aw_order)}
        all_aw_orders = {str(aw_order) for aw_order in self.order_by_aw if str(aw_order)}
        return bool(selected_aw_orders) and bool(all_aw_orders) and all_aw_orders.issubset(selected_aw_orders)

    def start_send_outputs_worker(
        self,
        sketch_paths: list[Path],
        dxf_paths: list[Path],
        missing: list[str],
        archive_inputs: bool,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        process_list_path: Path,
        *,
        include_sketches: bool,
        include_programs: bool,
    ) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        self.ensure_workflow_folders(order_folder, process_list_path, output_dir)
        send_steps = max(1, len(sketch_paths) + len(dxf_paths) + (1 if archive_inputs else 0))
        archive_process_lists = self.orders_cover_all_scanned_orders(orders)
        self.start_background_activity("Sending generated files to shop folders...", maximum=send_steps)
        worker = threading.Thread(
            target=self.worker_send_outputs,
            args=(
                sketch_paths,
                dxf_paths,
                missing,
                include_sketches,
                include_programs,
                archive_inputs,
                archive_process_lists,
                orders,
                order_folder,
                process_list_path,
            ),
            daemon=True,
        )
        worker.start()

    def open_send_review_dialog(
        self,
        output_dir: Path,
        include_sketches: bool,
        include_programs: bool,
        archive_inputs: bool,
        orders: list[shower_batch.ProcessOrder],
        sketch_paths: list[Path],
        dxf_paths: list[Path],
        missing: list[str],
        order_folder: Path,
        process_list_path: Path,
    ) -> None:
        dialog = ctk.CTkToplevel(self.root) if ctk is not None else tk.Toplevel(self.root)
        dialog.title("Review / Send Output")
        self.position_child_window(dialog, 1180, 760)
        dialog.minsize(960, 560)
        dialog.resizable(True, True)
        self.set_window_icon(dialog)
        dialog.configure(fg_color=self.APP_BG) if ctk is not None else dialog.configure(bg=self.APP_BG)
        dialog.after(0, lambda: self.maximize_window(dialog))
        self.send_review_window = dialog

        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(dialog, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Review / Send Batch",
            font=("Segoe UI", 24, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text="Confirm checked orders, generated sketches, DXF programs, and archive actions before sending to the shop folders.",
            font=("Segoe UI", 12),
            text_color=self.MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # Use the native Windows title-bar controls only.
        # The extra in-window minimize/maximize/close buttons were removed to avoid duplicate controls.

        workspace = ctk.CTkFrame(dialog, fg_color="transparent")
        workspace.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        workspace.grid_columnconfigure(0, weight=0, minsize=308)
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)

        rail = ctk.CTkFrame(
            workspace,
            fg_color=self.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=self.BORDER,
            width=308,
        )
        rail.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            rail,
            text="Send workflow",
            font=("Segoe UI", 17, "bold"),
            text_color=self.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 3))
        ctk.CTkLabel(
            rail,
            text="1 Checked  -  2 Review files  -  3 Send  -  4 Archive",
            font=("Segoe UI", 10),
            text_color=self.MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

        summary_frame = ctk.CTkFrame(rail, fg_color="transparent")
        summary_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        summary_frame.grid_columnconfigure((0, 1), weight=1)
        ready_count_var = tk.StringVar(value="0")
        blocked_count_var = tk.StringVar(value="0")
        warning_count_var = tk.StringVar(value="0")
        sketch_count_var = tk.StringVar(value=str(len(sketch_paths)))
        program_count_var = tk.StringVar(value=str(len(dxf_paths)))

        def mini_metric(row: int, column: int, number_var: tk.StringVar, label: str, color: str, icon: str) -> None:
            card = ctk.CTkFrame(summary_frame, fg_color=self.PANEL_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
            card.grid(row=row, column=column, sticky="ew", padx=(0, 7) if column == 0 else (7, 0), pady=(0, 10))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text="", image=self.ctk_button_icon(icon, 18, color).get("image"), width=24).grid(row=0, column=0, rowspan=2, padx=(10, 7), pady=10)
            ctk.CTkLabel(card, textvariable=number_var, font=("Segoe UI", 17, "bold"), text_color=color, anchor="w").grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(8, 0))
            ctk.CTkLabel(card, text=label, font=("Segoe UI", 9, "bold"), text_color=self.MUTED, anchor="w").grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 8))

        mini_metric(0, 0, ready_count_var, "Ready", self.SUCCESS, "check_circle")
        mini_metric(0, 1, blocked_count_var, "Blocked", self.DANGER, "minus_circle")
        mini_metric(1, 0, warning_count_var, "Warnings", self.WARNING, "warning")
        mini_metric(1, 1, sketch_count_var, "Sketches", self.ACCENT_DARK, "pdf")
        mini_metric(2, 0, program_count_var, "Programs", "#7c3aed" if not self.dark_mode_var.get() else "#a78bfa", "program")

        notes_card = ctk.CTkFrame(rail, fg_color=self.PANEL_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
        notes_card.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkLabel(notes_card, text="Send rules", font=("Segoe UI", 11, "bold"), text_color=self.TEXT, anchor="w").pack(fill=tk.X, padx=12, pady=(10, 3))
        ctk.CTkLabel(
            notes_card,
            text="Unchecked orders stay blocked. Checked orders with warnings can still send after confirmation. Archive runs only with the full checked-order send.",
            font=("Segoe UI", 10),
            text_color=self.MUTED,
            justify="left",
            anchor="w",
            wraplength=250,
        ).pack(fill=tk.X, padx=12, pady=(0, 12))

        action_panel = ctk.CTkFrame(rail, fg_color="transparent")
        action_panel.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 16))
        action_panel.grid_columnconfigure(0, weight=1)

        main = ctk.CTkFrame(workspace, fg_color=self.CARD_BG, corner_radius=16, border_width=1, border_color=self.BORDER)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        main_header = ctk.CTkFrame(main, fg_color="transparent", height=58)
        main_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        main_header.grid_propagate(False)
        ctk.CTkLabel(main_header, text="Send plan", font=("Segoe UI", 16, "bold"), text_color=self.TEXT).pack(side=tk.LEFT)
        ctk.CTkLabel(
            main_header,
            text="Expand an order to see sketches, programs, archive files, and warnings.",
            font=("Segoe UI", 10),
            text_color=self.MUTED,
        ).pack(side=tk.LEFT, padx=(10, 0))

        tree_frame = ctk.CTkFrame(main, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        columns = ("status", "source", "destination", "note")
        tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", selectmode="browse")
        tree.heading("#0", text="Order / Action")
        tree.heading("status", text="Status")
        tree.heading("source", text="Source")
        tree.heading("destination", text="Destination")
        tree.heading("note", text="Note")
        tree.column("#0", width=255, minwidth=190, stretch=True)
        tree.column("status", width=118, minwidth=88, stretch=False)
        tree.column("source", width=270, minwidth=180, stretch=True)
        tree.column("destination", width=250, minwidth=180, stretch=True)
        tree.column("note", width=250, minwidth=150, stretch=True)
        tree.tag_configure("ready", foreground=self.SUCCESS)
        tree.tag_configure("warning", foreground=self.WARNING)
        tree.tag_configure("blocked", foreground=self.DANGER)
        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        status_footer = ctk.CTkFrame(main, fg_color=self.PANEL_BG, corner_radius=13, border_width=1, border_color=self.BORDER)
        status_footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        status_footer.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(status_footer, text="Status", font=("Segoe UI", 10, "bold"), text_color=self.MUTED).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.send_review_status_var = tk.StringVar(value="Review the send plan. Unchecked orders are blocked and will not send.")
        ctk.CTkLabel(status_footer, textvariable=self.send_review_status_var, font=("Segoe UI", 11), text_color=self.TEXT, anchor="w").grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        self.send_review_progress = ModernProgressBar(status_footer, self, height=12)
        self.send_review_progress.configure(mode="determinate", maximum=100, value=0)
        self.send_review_progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12), ipady=2)

        archive_candidates = (
            self.matching_order_files(order_folder, orders, root_only=True, inspect_pdf_text=False)
            if archive_inputs
            else []
        )
        checked_orders: list[shower_batch.ProcessOrder] = []
        checked_aw_orders: list[str] = []
        blocked_count = 0
        warning_count = 0
        checked_warning_count = 0

        for order in orders:
            checked = self.order_review_is_complete(order)
            remake_badge = self.remake_badge_for_order(order.aw_order)
            order_sketches = self.paths_for_order(sketch_paths, order.aw_order)
            order_dxfs = self.paths_for_order(dxf_paths, order.aw_order)
            order_archive_files = (
                self.paths_matching_order_by_name(archive_candidates, order)
                if archive_inputs
                else []
            )
            warnings = self.send_plan_warnings_for_order(
                order,
                include_sketches=include_sketches,
                include_programs=include_programs,
                sketch_paths=order_sketches,
                dxf_paths=order_dxfs,
            )
            if not checked:
                blocked_count += 1
                warnings.insert(0, "Not marked checked; this order will not send.")
            if warnings:
                warning_count += 1
                if checked:
                    checked_warning_count += 1
            if checked:
                checked_orders.append(order)
                checked_aw_orders.append(order.aw_order)

            tag = "blocked" if not checked else "warning" if warnings else "ready"
            status_text = "Blocked" if not checked else "Warnings" if warnings else "Ready"
            parent = tree.insert(
                "",
                tk.END,
                text=f"{order.aw_order}  {remake_badge + '  ' if remake_badge else ''}{order.job_name}",
                values=(status_text, "", "", "; ".join(warnings[:2])),
                open=bool(warnings) or len(orders) <= 6,
                tags=(tag,),
            )
            if not checked:
                tree.insert(parent, tk.END, text="Blocked", values=("Blocked", "", "", "Open the order review and mark it checked first."), tags=("blocked",))
                continue
            if include_sketches:
                if order_sketches:
                    for path in order_sketches:
                        tree.insert(parent, tk.END, text="Sketch PDF", values=("Ready", path.name, str(self.SHOP_SKETCHES_DIR), ""), tags=("ready",))
                else:
                    tree.insert(parent, tk.END, text="Sketch PDF", values=("Missing", "", str(self.SHOP_SKETCHES_DIR), "No sketch PDF found."), tags=("warning",))
            if include_programs:
                if order_dxfs:
                    for path in order_dxfs:
                        tree.insert(parent, tk.END, text="Program DXF", values=("Ready", path.name, str(self.SHOP_PROGRAMS_DIR), ""), tags=("ready",))
                else:
                    tree.insert(parent, tk.END, text="Program DXF", values=("Missing", "", str(self.SHOP_PROGRAMS_DIR), "No program DXF found."), tags=("warning",))
            if archive_inputs:
                if order_archive_files:
                    for path in order_archive_files:
                        tree.insert(parent, tk.END, text="Archive input", values=("Ready", path.name, "dated input archive", ""), tags=("ready",))
                else:
                    tree.insert(parent, tk.END, text="Archive input", values=("Missing", "", "dated input archive", "No matching input file found."), tags=("warning",))
            for warning in warnings:
                tree.insert(parent, tk.END, text="Warning", values=("Review", "", "", warning), tags=("warning",))

        show_process_list_archive = archive_inputs and checked_orders and self.orders_cover_all_scanned_orders(checked_orders)
        process_list_files = self.archive_process_list_files(process_list_path) if show_process_list_archive else []
        if process_list_files:
            parent = tree.insert("", tk.END, text="Process Lists", values=("Ready", "", "dated process-list archive", ""), open=False, tags=("ready",))
            for path in process_list_files:
                tree.insert(parent, tk.END, text="Archive process list", values=("Ready", path.name, "dated process-list archive", ""), tags=("ready",))

        send_sketch_paths = self.generated_sketch_paths_for_orders(checked_aw_orders, output_dir) if include_sketches else []
        send_dxf_paths = self.generated_dxf_paths_for_orders(checked_aw_orders, output_dir) if include_programs else []
        send_missing: list[str] = []
        if include_sketches and not send_sketch_paths:
            send_missing.append("sketches")
        if include_programs and not send_dxf_paths:
            send_missing.append("programs")

        ready_count_var.set(str(len(checked_orders)))
        blocked_count_var.set(str(blocked_count))
        warning_count_var.set(str(warning_count))
        sketch_count_var.set(str(len(send_sketch_paths)))
        program_count_var.set(str(len(send_dxf_paths)))
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)

        def close_dialog() -> None:
            if self.send_review_window is dialog:
                self.send_review_window = None
                self.send_review_progress = None
                self.send_review_status_var = None
            dialog.destroy()

        send_action_buttons: list[Any] = []

        def begin_send(send_sketches: bool, send_programs: bool, do_archive: bool) -> None:
            if not checked_orders:
                messagebox.showinfo("Nothing ready", "No checked orders are ready to send.", parent=dialog)
                return
            chosen_sketches = send_sketch_paths if send_sketches else []
            chosen_dxfs = send_dxf_paths if send_programs else []
            if not chosen_sketches and not chosen_dxfs:
                messagebox.showinfo("Nothing ready", "No generated files were found for the checked orders.", parent=dialog)
                return
            if checked_warning_count and not messagebox.askyesno(
                "Warnings found",
                "Some checked orders have warnings. Send the checked orders anyway?",
                parent=dialog,
            ):
                return
            chosen_missing: list[str] = []
            if send_sketches and not chosen_sketches:
                chosen_missing.append("sketches")
            if send_programs and not chosen_dxfs:
                chosen_missing.append("programs")
            for button in send_action_buttons:
                button.configure(state=tk.DISABLED)
            close_button.configure(text="Close")
            self.send_review_status_var.set("Sending checked orders...")
            self.start_send_outputs_worker(
                chosen_sketches,
                chosen_dxfs,
                chosen_missing,
                bool(do_archive),
                checked_orders,
                order_folder,
                process_list_path,
                include_sketches=send_sketches,
                include_programs=send_programs,
            )

        ctk.CTkButton(
            action_panel,
            text="Send All Checked Orders",
            command=lambda: begin_send(True, True, archive_inputs),
            height=46,
            corner_radius=11,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_DARK,
            text_color="#ffffff",
            font=("Segoe UI", 13, "bold"),
            **self.ctk_button_icon("send", 17, "#ffffff", "left"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 9))
        send_all_button = action_panel.grid_slaves(row=0, column=0)[0]

        two_col = ctk.CTkFrame(action_panel, fg_color="transparent")
        two_col.grid(row=1, column=0, sticky="ew", pady=(0, 9))
        two_col.grid_columnconfigure((0, 1), weight=1)
        send_sketches_button = self.make_tool_button(two_col, "Sketches", "image", lambda: begin_send(True, False, False), width=120)
        send_sketches_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        send_programs_button = self.make_tool_button(two_col, "Programs", "program", lambda: begin_send(False, True, False), width=120)
        send_programs_button.grid(row=0, column=1, sticky="ew")
        close_button = self.make_tool_button(action_panel, "Cancel", "x", close_dialog, width=250)
        close_button.grid(row=2, column=0, sticky="ew")

        send_action_buttons.extend([send_sketches_button, send_programs_button, send_all_button])
        if not checked_orders:
            for button in send_action_buttons:
                button.configure(state=tk.DISABLED)
        if not send_sketch_paths:
            send_sketches_button.configure(state=tk.DISABLED)
        if not send_dxf_paths:
            send_programs_button.configure(state=tk.DISABLED)
        if not send_sketch_paths and not send_dxf_paths:
            send_all_button.configure(state=tk.DISABLED)

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self.bring_window_to_front(dialog, make_transient=False)

    @staticmethod
    def paths_for_order(paths: list[Path], aw_order: str) -> list[Path]:
        prefixes = (f"{aw_order}.", f"{aw_order}_", f"{aw_order}-")
        matched: list[Path] = []
        for path in paths:
            stem = path.stem
            if stem == aw_order or any(stem.startswith(prefix) for prefix in prefixes):
                matched.append(path)
                continue
            suffix = stem[len(aw_order):] if stem.startswith(aw_order) else ""
            if suffix.isdigit():
                matched.append(path)
        return matched

    @classmethod
    def paths_matching_order_by_name(cls, paths: list[Path], order: shower_batch.ProcessOrder) -> list[Path]:
        aw_order = str(order.aw_order)
        matched: list[Path] = []
        normalized_jobs = [programmer.normalize_lookup(order.job_name)] if order.job_name else []
        for path in paths:
            if path.suffix.lower() == ".pdf":
                if cls.pdf_file_matches_jobs(path, normalized_jobs, {aw_order}, inspect_pdf_text=False):
                    matched.append(path)
            elif path in cls.paths_for_order([path], aw_order):
                matched.append(path)
        return matched

    def send_plan_warnings_for_order(
        self,
        order: shower_batch.ProcessOrder,
        *,
        include_sketches: bool,
        include_programs: bool,
        sketch_paths: list[Path],
        dxf_paths: list[Path],
    ) -> list[str]:
        warnings: list[str] = []
        if include_sketches and not sketch_paths:
            warnings.append("Missing generated sketch PDF.")
        if include_programs and not dxf_paths:
            warnings.append("Missing generated program DXF.")
        issue_text = self.tree_issue_text_for_order(order.aw_order)
        if issue_text:
            warnings.append(f"Issues: {issue_text}")
        lower_issue = issue_text.lower()
        if any(token in lower_issue for token in ("manual", "review", "mismatch", "orientation", "dxf")):
            warnings.append("Possible sketch/DXF review item.")
        return warnings

    def worker_send_outputs(
        self,
        sketch_paths: list[Path],
        dxf_paths: list[Path],
        missing: list[str],
        include_sketches: bool,
        include_programs: bool,
        archive_inputs: bool,
        archive_process_lists: bool,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        process_list_path: Path,
    ) -> None:
        try:
            copied: list[Path] = []
            archived: list[Path] = []
            archive_warnings: list[str] = []
            import_deleted: list[Path] = []
            input_cleanup_warnings: list[str] = []
            progress_value = 0
            progress_max = max(1, len(sketch_paths) + len(dxf_paths) + (1 if archive_inputs else 0))

            def advance(message: str, remaining_hint: int = 1) -> None:
                nonlocal progress_value, progress_max
                progress_value += 1
                progress_max = max(progress_max, progress_value + max(remaining_hint, 0))
                self.queue_scan_progress(progress_value, progress_max, message)

            if sketch_paths:
                copied.extend(
                    self.copy_outputs_to_folder(
                        sketch_paths,
                        self.SHOP_SKETCHES_DIR,
                        progress_callback=lambda source, _target: advance(f"Sent sketch: {source.name}", len(dxf_paths) + 1),
                    )
                )
            if dxf_paths:
                copied.extend(
                    self.copy_outputs_to_folder(
                        dxf_paths,
                        self.SHOP_PROGRAMS_DIR,
                        progress_callback=lambda source, _target: advance(f"Sent program: {source.name}", 1),
                    )
                )
            sent_orders = self.successfully_sent_orders(
                orders,
                sketch_paths,
                dxf_paths,
                copied,
                include_sketches=include_sketches,
                include_programs=include_programs,
            )
            archive_all_process_lists = archive_process_lists and len(sent_orders) == len(orders)
            if sent_orders and archive_inputs:
                advance("Archiving sent input files...", 2)
                def archive_progress(done: int, total: int, source: Path) -> None:
                    advance(f"Archived input {done}/{total}: {source.name}", total - done + 1)

                archived, archive_warnings = self.archive_sent_input_files_for_orders(
                    sent_orders,
                    order_folder,
                    process_list_path,
                    include_process_lists=archive_all_process_lists,
                    progress_callback=archive_progress,
                )

                def cleanup_progress(done: int, total: int, source: Path) -> None:
                    advance(f"Cleared input staging {done}/{total}: {source.name}", total - done)

                advance("Clearing Showers Programmer Input...", 1)
                import_deleted, input_cleanup_warnings = self.clear_import_staging_folder(
                    sent_orders,
                    include_process_lists=archive_all_process_lists,
                    progress_callback=cleanup_progress,
                )
            self.queue_scan_progress(progress_value + 1, progress_value + 1, "Send complete.")
            self.worker_queue.put(
                (
                    "send_done",
                    {
                        "copied": copied,
                        "missing": missing,
                        "archived": archived,
                        "archive_warnings": archive_warnings,
                        "import_deleted": import_deleted,
                        "input_cleanup_warnings": input_cleanup_warnings,
                        "sent_orders": sent_orders if archive_inputs else [],
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("send_error", str(exc)))

    @classmethod
    def successfully_sent_orders(
        cls,
        orders: list[shower_batch.ProcessOrder],
        sketch_paths: list[Path],
        dxf_paths: list[Path],
        copied: list[Path],
        *,
        include_sketches: bool,
        include_programs: bool,
    ) -> list[shower_batch.ProcessOrder]:
        copied_names = {path.name.lower() for path in copied}

        def paths_were_copied(paths: list[Path]) -> bool:
            return bool(paths) and all(path.name.lower() in copied_names for path in paths)

        sent: list[shower_batch.ProcessOrder] = []
        for order in orders:
            order_sketches = cls.paths_for_order(sketch_paths, order.aw_order)
            order_dxfs = cls.paths_for_order(dxf_paths, order.aw_order)
            if include_sketches and not paths_were_copied(order_sketches):
                continue
            if include_programs and not paths_were_copied(order_dxfs):
                continue
            if not include_sketches and not include_programs:
                continue
            sent.append(order)
        return sent

    @staticmethod
    def send_complete_details(
        copied: list[Path],
        missing: list[str],
        archived: list[Path],
        archive_warnings: list[str],
        import_deleted: list[Path] | None = None,
        input_cleanup_warnings: list[str] | None = None,
    ) -> str:
        import_deleted = import_deleted or []
        input_cleanup_warnings = input_cleanup_warnings or []
        def copied_order_number(path: Path) -> str | None:
            stem = path.stem
            dxf_match = re.match(r"^(\d{6})\d{2}$", stem)
            if dxf_match:
                return dxf_match.group(1)
            match = re.match(r"(\d{5,})", stem)
            return match.group(1) if match else None

        order_numbers = sorted({order for path in copied for order in [copied_order_number(path)] if order})
        sketch_count = sum(1 for path in copied if path.suffix.lower() == ".pdf")
        program_count = sum(1 for path in copied if path.suffix.lower() == ".dxf")
        order_text = ", ".join(order_numbers[:12]) if order_numbers else "selected orders"
        if len(order_numbers) > 12:
            order_text += f", +{len(order_numbers) - 12} more"
        details = (
            f"Sent {len(order_numbers) or 'selected'} order(s) to the shop folders.\n"
            f"Orders: {order_text}\n"
            f"Sketches: {sketch_count}   Programs: {program_count}"
        )
        if missing:
            details += "\nMissing: " + " or ".join(missing)
        if archived:
            details += f"\nArchived inputs: {len(archived)}"
        if archive_warnings:
            details += f"\nArchive notes: {len(archive_warnings)}"
        if import_deleted:
            details += f"\nCleared staging files: {len(import_deleted)}"
        if input_cleanup_warnings:
            details += f"\nInput cleanup notes: {len(input_cleanup_warnings)}"
        return details

    def copy_outputs_to_folder(
        self,
        paths: list[Path],
        target_dir: Path,
        progress_callback: Callable[[Path, Path], None] | None = None,
    ) -> list[Path]:
        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for source in paths:
            if not source.exists() or not source.is_file():
                continue
            target = target_dir / source.name
            shutil.copy2(source, target)
            copied.append(target)
            if progress_callback is not None:
                progress_callback(source, target)
        return copied

    def archive_sent_input_files(self, aw_orders: list[str]) -> tuple[list[Path], list[str]]:
        if not aw_orders:
            return [], ["No scanned or selected orders were available to archive."]
        orders = [self.order_by_aw[aw_order] for aw_order in aw_orders if aw_order in self.order_by_aw]
        return self.archive_sent_input_files_for_orders(
            orders,
            Path(self.folder_var.get()).resolve(),
            Path(self.process_list_var.get()).resolve(),
            include_process_lists=self.orders_cover_all_scanned_orders(orders),
        )

    def archive_sent_input_files_for_orders(
        self,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        process_list_path: Path,
        include_process_lists: bool = True,
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> tuple[list[Path], list[str]]:
        if not orders:
            return [], ["No matching scanned order records were available to archive."]

        dated_name = self.dated_archive_folder_name()
        order_archive_dir = self.archive_dir_for_input_root(order_folder, dated_name)
        archived: list[Path] = []
        warnings: list[str] = []

        order_files = self.matching_order_files(order_folder, orders, root_only=True, inspect_pdf_text=True)
        if not order_files:
            warnings.append("No root-level order PDF/DXF input files matched the sent orders.")

        process_list_files = self.archive_process_list_files(process_list_path) if include_process_lists else []

        process_sources: list[Path] = []
        if include_process_lists:
            if process_list_files:
                process_archive_dir = self.process_list_archive_dir(process_list_path, dated_name)
                for source in process_list_files:
                    if source.parent.resolve() == process_archive_dir.resolve():
                        continue
                    process_sources.append(source)
            else:
                warnings.append("No process-list files were available to archive.")

        total_sources = len(order_files) + len(process_sources)
        done = 0
        for source in order_files:
            archived.append(self.move_file_to_folder(source, order_archive_dir))
            done += 1
            if progress_callback is not None:
                progress_callback(done, total_sources, source)
        if process_sources:
            process_archive_dir = self.process_list_archive_dir(process_list_path, dated_name)
            for source in process_sources:
                archived.append(self.move_file_to_folder(source, process_archive_dir))
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total_sources, source)

        return archived, warnings

    @staticmethod
    def archive_process_list_files(process_list_path: Path) -> list[Path]:
        if process_list_path.is_file():
            return [process_list_path] if shower_batch.is_process_list_file(process_list_path) else []
        if not process_list_path.exists() or not process_list_path.is_dir():
            return []
        return sorted(
            (
                candidate
                for candidate in process_list_path.iterdir()
                if shower_batch.is_process_list_file(candidate)
            ),
            key=lambda candidate: candidate.name.lower(),
        )

    @staticmethod
    def archive_dir_for_input_root(input_root: Path, dated_name: str) -> Path:
        if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(input_root.name):
            return input_root
        return input_root / dated_name

    @staticmethod
    def process_list_archive_dir(process_list_path: Path, dated_name: str) -> Path:
        if process_list_path.is_file():
            if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(process_list_path.parent.name):
                return process_list_path.parent
            return process_list_path.parent / dated_name
        if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(process_list_path.name):
            return process_list_path
        return process_list_path / dated_name

    @staticmethod
    def dated_archive_folder_name(moment: datetime | None = None) -> str:
        moment = moment or datetime.now()
        return f"{moment.month}.{moment.day}.{moment:%y}"

    @staticmethod
    def move_file_to_folder(source: Path, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = ShowerProgrammerApp.unique_target_path(target_dir / source.name)
        shutil.move(str(source), str(target))
        return target

    @staticmethod
    def unique_target_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        for index in range(2, 10_000):
            candidate = path.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not choose a unique archive name for {path}")

    @classmethod
    def clear_import_staging_folder(
        cls,
        orders: list[shower_batch.ProcessOrder] | None = None,
        include_process_lists: bool = False,
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> tuple[list[Path], list[str]]:
        source_dir = cls.EDI_IMPORT_ORDERS_DIR
        deleted: list[Path] = []
        warnings: list[str] = []
        if not source_dir.exists():
            return deleted, [f"Input staging folder was not found: {source_dir}"]
        if not source_dir.is_dir():
            return deleted, [f"Input staging path is not a folder: {source_dir}"]
        if source_dir.name.lower() != cls.IMPORT_STAGING_FOLDER_NAME.lower():
            return deleted, [f"Skipped input cleanup because the configured folder is not named {cls.IMPORT_STAGING_FOLDER_NAME}."]

        if orders:
            target_paths = {
                path.resolve()
                for path in cls.matching_order_files(source_dir, orders, root_only=True, inspect_pdf_text=True)
            }
            if include_process_lists:
                target_paths.update(path.resolve() for path in cls.importable_process_list_files(source_dir))
            entries = [path for path in sorted(source_dir.iterdir(), key=lambda candidate: candidate.name.lower()) if path.resolve() in target_paths]
        else:
            entries = sorted(source_dir.iterdir(), key=lambda candidate: candidate.name.lower())
        file_entries = [path for path in entries if path.is_file() and not path.is_symlink()]
        total = len(file_entries)
        done = 0
        for path in entries:
            if path.is_dir():
                warnings.append(f"Skipped folder {path.name}.")
                continue
            if path.is_symlink():
                warnings.append(f"Skipped linked file {path.name}.")
                continue
            if not path.is_file():
                continue
            try:
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                warnings.append(f"Could not delete {path.name}: {exc}")
            done += 1
            if progress_callback is not None:
                progress_callback(done, max(total, 1), path)
        return deleted, warnings

    @classmethod
    def copy_process_lists_from_import_folder(
        cls,
        process_list_path: Path,
        progress_callback: Callable[[int, int, Path, bool], None] | None = None,
    ) -> dict[str, object]:
        source_dir = cls.EDI_IMPORT_ORDERS_DIR
        summary: dict[str, object] = {
            "copied": [],
            "skipped": 0,
            "source": str(source_dir),
            "source_missing": False,
            "direct": False,
            "considered": 0,
        }
        if not source_dir.exists():
            summary["source_missing"] = True
            return summary

        target_dir = cls.process_list_import_target_dir(process_list_path)
        if cls.same_path(source_dir, target_dir):
            summary["direct"] = True
            return summary
        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        skipped = 0
        sources = cls.importable_process_list_files(source_dir)
        summary["considered"] = len(sources)
        for index, source in enumerate(sources, start=1):
            target = target_dir / source.name
            did_copy = cls.copy_file_if_needed(source, target)
            if did_copy:
                copied.append(target)
            else:
                skipped += 1
            if progress_callback is not None:
                progress_callback(index, len(sources), source, did_copy)
        summary["copied"] = copied
        summary["skipped"] = skipped
        return summary

    @classmethod
    def importable_process_list_files(cls, source_dir: Path) -> list[Path]:
        files = [
            candidate
            for candidate in source_dir.iterdir()
            if candidate.is_file()
            and not candidate.name.startswith("~$")
            and candidate.suffix.lower() in cls.PROCESS_LIST_FILE_EXTENSIONS
        ]
        return sorted(files, key=lambda candidate: candidate.name.lower())

    @staticmethod
    def process_list_import_target_dir(process_list_path: Path) -> Path:
        if process_list_path.suffix:
            return process_list_path.parent
        return process_list_path

    @classmethod
    def copy_edi_orders_for_process_orders(
        cls,
        target_dir: Path,
        orders: list[shower_batch.ProcessOrder],
        progress_callback: Callable[[int, int, Path, bool], None] | None = None,
    ) -> dict[str, object]:
        source_dir = cls.EDI_IMPORT_ORDERS_DIR
        summary: dict[str, object] = {
            "copied": [],
            "skipped": 0,
            "source": str(source_dir),
            "source_missing": False,
            "direct": False,
            "considered": 0,
            "hardware_deleted": [],
            "hardware_warnings": [],
        }
        if not orders:
            return summary
        if not source_dir.exists():
            summary["source_missing"] = True
            return summary
        hardware_deleted, hardware_warnings = cls.delete_hardware_list_pdfs(source_dir)
        summary["hardware_deleted"] = hardware_deleted
        summary["hardware_warnings"] = hardware_warnings
        if cls.same_path(source_dir, target_dir):
            summary["direct"] = True
            return summary

        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        skipped = 0
        sources = cls.matching_order_files(source_dir, orders, root_only=True, inspect_pdf_text=True)
        summary["considered"] = len(sources)
        for index, source in enumerate(sources, start=1):
            target = target_dir / source.name
            did_copy = cls.copy_file_if_needed(source, target)
            if did_copy:
                copied.append(target)
            else:
                skipped += 1
            if progress_callback is not None:
                progress_callback(index, len(sources), source, did_copy)
        summary["copied"] = copied
        summary["skipped"] = skipped
        return summary

    @classmethod
    def delete_hardware_list_pdfs(cls, source_dir: Path) -> tuple[list[Path], list[str]]:
        deleted: list[Path] = []
        warnings: list[str] = []
        if not source_dir.exists() or not source_dir.is_dir():
            return deleted, warnings
        for path in sorted(source_dir.iterdir(), key=lambda candidate: candidate.name.lower()):
            if not cls.is_hardware_list_pdf(path):
                continue
            try:
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                warnings.append(f"Could not delete hardware list {path.name}: {exc}")
        return deleted, warnings

    @classmethod
    def is_hardware_list_pdf(cls, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".pdf" and path.name.lower().startswith(cls.HARDWARE_LIST_PREFIX)

    @classmethod
    def matching_order_files(
        cls,
        folder: Path,
        orders: list[shower_batch.ProcessOrder],
        *,
        root_only: bool,
        inspect_pdf_text: bool,
    ) -> list[Path]:
        if not folder.exists():
            return []
        normalized_jobs = [
            programmer.normalize_lookup(order.job_name)
            for order in orders
            if programmer.normalize_lookup(order.job_name)
        ]
        aw_orders = {str(order.aw_order) for order in orders if str(order.aw_order)}
        candidates = folder.glob("*") if root_only else folder.rglob("*")
        matched: list[Path] = []
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in cls.ORDER_FILE_EXTENSIONS:
                continue
            if cls.is_hardware_list_pdf(path):
                continue
            suffix = path.suffix.lower()
            if suffix == ".dxf":
                if cls.file_matches_process_orders(path, orders, inspect_pdf_text=False):
                    matched.append(path)
                continue
            if cls.pdf_file_matches_jobs(path, normalized_jobs, aw_orders, inspect_pdf_text=inspect_pdf_text):
                matched.append(path)
        return sorted(matched, key=lambda candidate: candidate.name.lower())

    @staticmethod
    def pdf_file_matches_jobs(
        path: Path,
        normalized_jobs: list[str],
        aw_orders: set[str],
        *,
        inspect_pdf_text: bool,
    ) -> bool:
        if not normalized_jobs and not aw_orders:
            return False
        stem = path.stem
        norm_stem = programmer.normalize_lookup(stem)
        if any(aw_order and aw_order in stem for aw_order in aw_orders):
            return True
        if any(norm_job in norm_stem for norm_job in normalized_jobs):
            return True
        guessed_job = programmer.job_from_filename(path.name)
        if guessed_job:
            norm_guess = programmer.normalize_lookup(guessed_job)
            if any(norm_job in norm_guess for norm_job in normalized_jobs):
                return True
        if not inspect_pdf_text:
            return False
        try:
            extracted_job = programmer.extract_job_from_pdf(path)
        except Exception:
            return False
        norm_extracted = programmer.normalize_lookup(extracted_job)
        return bool(norm_extracted and any(norm_job in norm_extracted for norm_job in normalized_jobs))

    @staticmethod
    def same_path(first: Path, second: Path) -> bool:
        try:
            return first.resolve() == second.resolve()
        except Exception:
            return str(first).lower() == str(second).lower()

    @staticmethod
    def file_matches_process_orders(
        path: Path,
        orders: list[shower_batch.ProcessOrder],
        *,
        inspect_pdf_text: bool,
    ) -> bool:
        suffix = path.suffix.lower()
        norm_stem = programmer.normalize_lookup(path.stem)
        for order in orders:
            norm_job = programmer.normalize_lookup(order.job_name)
            if not norm_job:
                continue
            if suffix == ".dxf":
                if any(programmer.dxf_match_score(path, norm_job, item) is not None for item in order.item_numbers):
                    return True
                continue
            if suffix == ".pdf":
                if norm_job in norm_stem:
                    return True
                guessed_job = programmer.job_from_filename(path.name)
                if guessed_job and norm_job in programmer.normalize_lookup(guessed_job):
                    return True
                if inspect_pdf_text:
                    try:
                        extracted_job = programmer.extract_job_from_pdf(path)
                    except Exception:
                        extracted_job = ""
                    if extracted_job and norm_job in programmer.normalize_lookup(extracted_job):
                        return True
        return False

    @staticmethod
    def copy_file_if_needed(source: Path, target: Path) -> bool:
        if source.resolve() == target.resolve():
            return False
        if target.exists():
            try:
                source_stat = source.stat()
                target_stat = target.stat()
                if source_stat.st_size == target_stat.st_size and target_stat.st_mtime >= source_stat.st_mtime:
                    return False
            except OSError:
                pass
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True

    def autocad_save_as_programs(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
        paths = self.generated_dxf_paths(output_dir, programs_dir)
        if not paths:
            messagebox.showinfo("No DXFs", "No generated program DXFs were found.")
            return
        if not messagebox.askyesno(
            "AutoCAD Save-As DXFs?",
            f"Open and Save-As {len(paths)} generated program DXF file(s) through AutoCAD?",
        ):
            return
        temp_file: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
                temp_file = Path(handle.name)
                for path in paths:
                    handle.write(str(path.resolve()) + "\n")
            list_literal = str(temp_file).replace("'", "''")
            script = f"""
$ErrorActionPreference = 'Stop'
$files = Get-Content -LiteralPath '{list_literal}'
try {{
    $acad = [Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application')
}} catch {{
    $acad = New-Object -ComObject AutoCAD.Application
}}
$count = 0
foreach ($file in $files) {{
    if (-not (Test-Path -LiteralPath $file)) {{ continue }}
    $doc = $acad.Documents.Open($file)
    try {{
        $doc.SaveAs($file)
        $count += 1
    }} finally {{
        $doc.Close($false)
    }}
}}
Write-Output "AutoCAD saved $count DXF file(s)."
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                text=True,
                capture_output=True,
                timeout=max(120, len(paths) * 30),
            )
            if result.returncode != 0:
                messagebox.showerror("AutoCAD Save-As failed", result.stderr.strip() or result.stdout.strip())
                return
            message = result.stdout.strip() or f"AutoCAD saved {len(paths)} DXF file(s)."
            self.status_var.set(message)
            messagebox.showinfo("AutoCAD Save-As complete", message)
        except Exception as exc:
            messagebox.showerror("AutoCAD Save-As failed", str(exc))
        finally:
            if temp_file is not None:
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear_sketch_memory(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        if not messagebox.askyesno(
            "Clear sketch memory?",
            "This deletes generated sketch PDFs, clears sketch history pointers, and removes "
            "saved sketch-edit positions from manual_overrides.json. Machine overrides, DXFs, "
            "and process-list data are kept.",
        ):
            return
        removed_files = 0
        folders_and_patterns: list[tuple[Path, tuple[str, ...]]] = [
            (output_dir / "Sketches", ("*.pdf",)),
            (output_dir / "Reviews", ("sketch_review_*.pdf", "debug_*.png", "clean_*.png")),
        ]
        runs_dir = output_dir / "Runs"
        if runs_dir.exists():
            for run_folder in runs_dir.iterdir():
                if not run_folder.is_dir():
                    continue
                folders_and_patterns.append((run_folder / "Sketches", ("*.pdf",)))
                folders_and_patterns.append((run_folder / "Reviews", ("sketch_review_*.pdf", "debug_*.png", "clean_*.png")))
        for folder, patterns in folders_and_patterns:
            if not folder.exists():
                continue
            for pattern in patterns:
                for path in folder.glob(pattern):
                    try:
                        path.unlink()
                        removed_files += 1
                    except OSError:
                        pass
        for folder in output_dir.glob("DebugClean*"):
            if folder.is_dir():
                try:
                    shutil.rmtree(folder)
                    removed_files += 1
                except OSError:
                    pass
        changed_fields = self.clear_manual_sketch_fields()
        history_entries = self.clear_processing_history_sketch_fields()
        self.last_run_folder = None
        for aw_order, row_id in self.tree_rows.items():
            values = list(self.tree.item(row_id, "values"))
            if len(values) >= 9:
                values[1] = "No"
                values[2] = ""
                values[8] = self.review_status_for_order(aw_order)
                self.tree.item(row_id, values=values)
        self.status_var.set(
            f"Cleared {removed_files} sketch file(s), {changed_fields} saved sketch field(s), "
            f"and {history_entries} history entries."
        )
        messagebox.showinfo(
            "Sketch memory cleared",
            f"Deleted {removed_files} sketch/review file(s).\n"
            f"Removed {changed_fields} saved sketch field(s).\n"
            f"Cleared {history_entries} sketch history entries.",
        )

    def convert_programs_to_ac1032(self) -> None:
        self.autocad_save_as_programs()

    def clear_manual_sketch_fields(self) -> int:
        path = self.manual_overrides_path()
        if not path.exists():
            return 0
        data = self.load_manual_overrides()
        item_overrides = data.get("item_overrides", {})
        if not isinstance(item_overrides, dict):
            return 0
        sketch_fields = {
            "label_x",
            "label_y",
            "indicator_x",
            "indicator_y",
            "indicator_corner",
            "manual_indicator_corner",
            "rotation_degrees",
            "hinge_side",
            "hinges_up",
            "diamon_fusion_x",
            "diamon_fusion_y",
            "remake_x",
            "remake_y",
            "label_nudge_x",
            "label_nudge_y",
            "indicator_nudge_x",
            "indicator_nudge_y",
            "diamon_fusion_nudge_x",
            "diamon_fusion_nudge_y",
            "label_font_size",
            "diamon_fusion_font_size",
            "remake_font_size",
            "indicator_size",
            "waterjet_indicator_size",
            "checked",
            "hide_label",
            "hide_indicator",
            "hide_diamon_fusion",
            "hide_remake",
            "manual_x",
            "label_text",
            "diamon_fusion_text",
            "remake_text",
        }
        removed = 0
        empty_orders: list[str] = []
        for aw_order, order_overrides in item_overrides.items():
            if not isinstance(order_overrides, dict):
                continue
            if "_order_checked" in order_overrides:
                del order_overrides["_order_checked"]
                removed += 1
            empty_items: list[str] = []
            for item_key, override in order_overrides.items():
                if not isinstance(override, dict):
                    continue
                for field in list(override.keys()):
                    if field in sketch_fields:
                        del override[field]
                        removed += 1
                if not override:
                    empty_items.append(str(item_key))
            for item_key in empty_items:
                order_overrides.pop(item_key, None)
            if not order_overrides:
                empty_orders.append(str(aw_order))
        for aw_order in empty_orders:
            item_overrides.pop(aw_order, None)
        self.save_manual_overrides(data)
        return removed

    def clear_processing_history_sketch_fields(self) -> int:
        path = self.processing_history_path()
        if not path.exists():
            return 0
        data = self.load_processing_history()
        orders = data.get("orders", {})
        if not isinstance(orders, dict):
            return 0
        history_fields = {
            "last_processed",
            "output_pdf",
            "report_path",
            "run_folder",
            "status",
            "remake_items",
        }
        changed = 0
        empty_orders: list[str] = []
        for aw_order, entry in orders.items():
            if not isinstance(entry, dict):
                continue
            removed_any = False
            for field in history_fields:
                if field in entry:
                    del entry[field]
                    removed_any = True
            if removed_any:
                changed += 1
            if not entry:
                empty_orders.append(str(aw_order))
        for aw_order in empty_orders:
            orders.pop(aw_order, None)
        self.save_processing_history(data)
        return changed

    def open_sketch_editor(self) -> None:
        selected = self.selected_orders()
        if len(selected) != 1:
            messagebox.showinfo("Select one order", "Select exactly one scanned order to edit.")
            return
        process_order = selected[0]
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            config = self.config_with_manual_overrides(folder, output_dir)
            remake_items = self.editor_remake_items(process_order.aw_order)
            job, reader, issues = shower_batch.prepare_job(
                folder,
                output_dir / "Sketches",
                output_dir / "Programs",
                output_dir / "Reports",
                config,
                process_order,
                remake_items=remake_items,
            )
        except Exception as exc:
            messagebox.showerror("Sketch editor failed", str(exc))
            return
        if not job.panels:
            messagebox.showinfo("No pieces", "No editable piece pages were found for this order.")
            return
        if issues:
            self.status_var.set("; ".join(issues[:3]))

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Sketch - {process_order.aw_order}")
        self.position_child_window(dialog, 1040, 820)
        dialog.transient(self.root)

        toolbar = ttk.Frame(dialog, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Piece").pack(side=tk.LEFT)
        item_var = tk.StringVar(value=f"P{job.panels[0].item}")
        item_values = [f"P{panel.item}" for panel in job.panels]
        item_box = ttk.Combobox(toolbar, textvariable=item_var, values=item_values, state="readonly", width=8)
        item_box.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Flip Sides", command=lambda: flip_indicator_sides(), **self.button_icon("flip")).pack(side=tk.LEFT, padx=(0, 12))
        editor_status = tk.StringVar(value="Drag blue markings, then save.")
        ttk.Label(toolbar, textvariable=editor_status).pack(side=tk.LEFT, fill=tk.X, expand=True)

        canvas_frame = ttk.Frame(dialog)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(canvas_frame, background="#e8edf3", highlightthickness=0)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        state: dict[str, Any] = {
            "objects": {},
            "positions": {},
            "dirty": set(),
            "drag_key": None,
            "last_x": 0.0,
            "last_y": 0.0,
            "scale": 1.0,
            "current_panel": job.panels[0],
            "page_offsets": {},
            "page_images": [],
            "render_cache": {},
            "render_temp_dir": tempfile.mkdtemp(prefix="shower_sketch_editor_"),
        }

        def selected_panel() -> programmer.Panel:
            item = int(item_var.get().replace("P", ""))
            return next(panel for panel in job.panels if panel.item == item)

        def redraw() -> None:
            self.draw_editor_all_panels(canvas, reader, job, config, state)
            editor_status.set(f"Editing {job.aw_order}. Scroll to any piece, drag blue markings, then save.")

        def start_drag(event: tk.Event, key: str) -> None:
            state["drag_key"] = key
            state["last_x"] = float(canvas.canvasx(event.x))
            state["last_y"] = float(canvas.canvasy(event.y))

        def drag(event: tk.Event) -> None:
            key = state.get("drag_key")
            if not key:
                return
            x = float(canvas.canvasx(event.x))
            y = float(canvas.canvasy(event.y))
            dx = x - float(state["last_x"])
            dy = y - float(state["last_y"])
            state["last_x"] = x
            state["last_y"] = y
            canvas.move(f"edit_{key}", dx, dy)
            obj = state["objects"][key]
            scale = float(obj.get("scale", state["scale"]))
            obj["x"] += dx / scale
            obj["y"] -= dy / scale
            item_number = int(obj.get("item", state["current_panel"].item))
            item_key = (item_number, str(obj.get("key", key)))
            state["dirty"].add(item_key)
            position = {"x": obj["x"], "y": obj["y"]}
            if obj.get("key") == "indicator":
                corner = programmer.nearest_indicator_corner_for_point(
                    obj["machine"],
                    (obj["x"], obj["y"]),
                    obj.get("anchor_bbox"),
                    float(obj["page_width"]),
                    float(obj["page_height"]),
                    obj["pdf_cfg"],
                    precise_edges=bool(obj.get("precise_edges")),
                )
                position["indicator_corner"] = corner
                machine = str(obj["machine"])
                if machine.startswith("DENVER") or machine == "WJ":
                    raw_corner = programmer.nearest_indicator_corner_for_point(
                        obj["machine"],
                        (obj["x"], obj["y"]),
                        obj.get("anchor_bbox"),
                        float(obj["page_width"]),
                        float(obj["page_height"]),
                        obj["pdf_cfg"],
                        precise_edges=bool(obj.get("precise_edges")),
                        allowed_denver_only=False,
                        allowed_waterjet_only=False,
                    )
                    position["raw_indicator_corner"] = raw_corner
                    if machine == "WJ":
                        position["indicator_corner"] = raw_corner
            state["positions"][item_key] = position
            editor_status.set(f"Moved {obj['name']} on {job.aw_order}.{item_number}")

        def release(_event: tk.Event) -> None:
            state["drag_key"] = None

        def save() -> bool:
            try:
                dirty = state["dirty"]
                if not dirty:
                    messagebox.showinfo("No edits", "Nothing has been moved yet.", parent=dialog)
                    return False
                data = self.load_manual_overrides()
                item_overrides = data.setdefault("item_overrides", {})
                if not isinstance(item_overrides, dict):
                    item_overrides = {}
                    data["item_overrides"] = item_overrides
                order_overrides = item_overrides.setdefault(job.aw_order, {})
                if not isinstance(order_overrides, dict):
                    order_overrides = {}
                    item_overrides[job.aw_order] = order_overrides
                for item_number, key in sorted(dirty):
                    position = state["positions"].get((item_number, key))
                    if position is None:
                        continue
                    panel = next(panel for panel in job.panels if panel.item == item_number)
                    item_override = order_overrides.setdefault(str(item_number), {})
                    if not isinstance(item_override, dict):
                        item_override = {}
                        order_overrides[str(item_number)] = item_override
                    if key == "label":
                        item_override["label_x"] = round(float(position["x"]), 3)
                        item_override["label_y"] = round(float(position["y"]), 3)
                        panel.label_x = float(position["x"])
                        panel.label_y = float(position["y"])
                    elif key == "indicator":
                        corner = str(position.get("indicator_corner") or panel.indicator_corner or "").strip().lower()
                        if corner:
                            raw_corner = str(position.get("raw_indicator_corner") or corner).strip().lower()
                            if (
                                (panel.machine.startswith("DENVER") or panel.machine == "WJ")
                                and raw_corner in {"bottom_left", "bottom_right", "top_left", "top_right"}
                            ):
                                corner = raw_corner
                                item_override["manual_indicator_corner"] = True
                            else:
                                item_override.pop("manual_indicator_corner", None)
                            item_override["indicator_x"] = round(float(position["x"]), 3)
                            item_override["indicator_y"] = round(float(position["y"]), 3)
                            panel.indicator_x = float(position["x"])
                            panel.indicator_y = float(position["y"])
                            programmer.apply_indicator_corner_override_with_options(
                                panel,
                                corner,
                                config,
                                allow_manual_denver_corner=bool(item_override.get("manual_indicator_corner")),
                                allow_manual_waterjet_corner=bool(item_override.get("manual_indicator_corner")),
                            )
                            item_override["indicator_corner"] = corner
                            if panel.rotation_degrees is not None:
                                item_override["rotation_degrees"] = round(float(panel.rotation_degrees), 6)
                            if panel.machine == "DENVER 1" and programmer.has_door_programming_evidence(panel, config):
                                if panel.hinge_side:
                                    item_override["hinge_side"] = panel.hinge_side
                                item_override["hinges_up"] = bool(panel.hinges_up)
                            else:
                                item_override.pop("hinge_side", None)
                                item_override.pop("hinges_up", None)
                    elif key == "diamon_fusion":
                        item_override["diamon_fusion_x"] = round(float(position["x"]), 3)
                        item_override["diamon_fusion_y"] = round(float(position["y"]), 3)
                        panel.diamon_fusion_x = float(position["x"])
                        panel.diamon_fusion_y = float(position["y"])
                    elif key == "remake":
                        item_override["remake_x"] = round(float(position["x"]), 3)
                        item_override["remake_y"] = round(float(position["y"]), 3)
                        panel.remake_x = float(position["x"])
                        panel.remake_y = float(position["y"])
                self.save_manual_overrides(data)
                state["dirty"].clear()
                state["positions"].clear()
                editor_status.set(f"Saved manual positions to {self.manual_overrides_path().name}")
                return True
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc), parent=dialog)
                return False

        def save_and_process() -> None:
            if save():
                dialog.destroy()
                remake_map = None if remake_items is None else {process_order.aw_order: set(remake_items)}
                self.run_orders([process_order], apply=True, remake_items_by_order=remake_map, force_override=True)

        def flip_indicator_sides() -> None:
            panel = selected_panel()
            current = panel.indicator_corner or (
                programmer.default_waterjet_indicator_corner(panel)
                if panel.machine == "WJ"
                else programmer.denver_grabber_corner_for_panel(panel, panel.rotation_degrees)
            )
            corner = self.flipped_indicator_corner(current)
            self.set_indicator_corner_override(job.aw_order, panel.item, corner, panel, config)
            editor_status.set(f"Flipped indicator side to {corner} on {job.aw_order}.{panel.item}.")
            redraw()

        def mark_checked(item_number: int | None = None) -> None:
            try:
                data = self.load_manual_overrides()
                item_overrides = data.setdefault("item_overrides", {})
                if not isinstance(item_overrides, dict):
                    item_overrides = {}
                    data["item_overrides"] = item_overrides
                order_overrides = item_overrides.setdefault(job.aw_order, {})
                if not isinstance(order_overrides, dict):
                    order_overrides = {}
                    item_overrides[job.aw_order] = order_overrides
                if item_number is None:
                    order_overrides["_order_checked"] = True
                    editor_status.set(f"Marked {job.aw_order} as reviewed.")
                else:
                    item_override = order_overrides.setdefault(str(item_number), {})
                    if not isinstance(item_override, dict):
                        item_override = {}
                        order_overrides[str(item_number)] = item_override
                    item_override["checked"] = True
                    editor_status.set(f"Marked {job.aw_order}.{item_number} as reviewed.")
                self.save_manual_overrides(data)
                row_id = self.tree_rows.get(job.aw_order)
                if row_id:
                    values = list(self.tree.item(row_id, "values"))
                    if len(values) >= 9:
                        values[8] = self.review_status_for_order(job.aw_order)
                        self.tree.item(row_id, values=values)
            except Exception as exc:
                messagebox.showerror("Review mark failed", str(exc), parent=dialog)

        def jump_to_selected() -> None:
            offsets = state.get("page_offsets", {})
            offset = offsets.get(selected_panel().item) if isinstance(offsets, dict) else None
            region = canvas.bbox("all")
            if offset is None or not region:
                return
            total_height = max(1.0, float(region[3] - region[1]))
            canvas.yview_moveto(max(0.0, min(1.0, float(offset) / total_height)))

        item_box.bind("<<ComboboxSelected>>", lambda _event: jump_to_selected())
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        canvas.bind("<Enter>", lambda _event: canvas.focus_set())
        canvas.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event))
        dialog.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event))
        canvas.bind("<Shift-MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event, horizontal=True))
        canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-3, "units"))
        canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(3, "units"))

        buttons = ttk.Frame(dialog, padding=(8, 0, 8, 8))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Save Edits", command=save, **self.button_icon("save")).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save + Overwrite Sketch", command=save_and_process, **self.button_icon("save")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Mark P Checked", command=lambda: mark_checked(selected_panel().item), **self.button_icon("check_circle")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Mark Order Checked", command=lambda: mark_checked(None), **self.button_icon("checked")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy, **self.button_icon("x")).pack(side=tk.RIGHT)

        state["start_drag"] = start_drag
        def cleanup_render_temp(_event: tk.Event | None = None) -> None:
            if _event is not None and _event.widget is not dialog:
                return
            temp_dir = state.get("render_temp_dir")
            if isinstance(temp_dir, str):
                shutil.rmtree(temp_dir, ignore_errors=True)

        dialog.bind("<Destroy>", cleanup_render_temp, add="+")
        dialog.after(100, redraw)

    def editor_remake_items(self, aw_order: str, output_dir: Path | None = None) -> set[int] | None:
        history = self.history_for_order_from_output(aw_order, output_dir) if output_dir is not None else self.history_for_order(aw_order)
        value = history.get("remake_items")
        if isinstance(value, list):
            return {int(item) for item in value if str(item).strip().isdigit()}
        return None

    def remake_items_from_report(self, aw_order: str) -> set[int] | None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        _run_folder, _sketch_dir, _programs_dir, report_dir = self.output_dirs_for_order(aw_order, output_dir)
        report_path = report_dir / f"{aw_order}_programming_report.txt"
        if not report_path.exists():
            return None
        try:
            text = report_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
        match = re.search(r"^Remake:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        value = match.group(1).strip()
        if value.lower() == "all pieces":
            return set()
        items = {int(part) for part in re.findall(r"\bP?(\d+)\b", value, flags=re.IGNORECASE)}
        return items

    def scroll_editor_canvas(self, canvas: tk.Canvas, event: tk.Event, horizontal: bool = False) -> str:
        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return "break"
        units = -1 if delta > 0 else 1
        if horizontal:
            canvas.xview_scroll(units * 4, "units")
        else:
            canvas.yview_scroll(units * 4, "units")
        return "break"

    def draw_editor_all_panels(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        job: programmer.Job,
        config: dict[str, object],
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["objects"] = {}
        state["page_offsets"] = {}
        state["page_images"] = []
        y_cursor = 12.0
        max_width = 0.0
        for panel in job.panels:
            page = reader.pages[panel.page_index]
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            scale = min(940 / page_width, 640 / page_height)
            margin = 16.0
            header_height = 28.0
            page_top = y_cursor + header_height
            canvas_width = page_width * scale + margin * 2
            canvas_height = page_height * scale + margin * 2
            state["page_offsets"][panel.item] = y_cursor
            max_width = max(max_width, canvas_width)

            def to_canvas(x: float, y: float) -> tuple[float, float]:
                return margin + x * scale, page_top + margin + (page_height - y) * scale

            canvas.create_rectangle(0, y_cursor, canvas_width, page_top + canvas_height, fill="#e8edf3", outline="")
            canvas.create_text(
                margin,
                y_cursor + 8,
                text=f"P{panel.item}  {job.aw_order}.{panel.item}",
                anchor=tk.NW,
                fill="#1f2933",
                font=("Arial", 12, "bold"),
            )
            canvas.create_rectangle(
                margin,
                page_top + margin,
                canvas_width - margin,
                page_top + canvas_height - margin,
                fill="white",
                outline="#9aa7b5",
            )

            page_image = self.editor_page_image(job.pdf_path, panel.page_index, page_width, page_height, scale, state)
            if page_image is not None:
                state["page_images"].append(page_image)
                canvas.create_image(margin, page_top + margin, image=page_image, anchor=tk.NW)
            else:
                for start, end, _length in programmer.collect_page_line_segments(reader, panel.page_index, min_length=1.0):
                    x1, y1 = to_canvas(*start)
                    x2, y2 = to_canvas(*end)
                    canvas.create_line(x1, y1, x2, y2, fill="#3f4750", width=max(1, int(scale)))
                self.draw_editor_page_text(canvas, page, page_height, scale, margin, top_offset=page_top)
            objects = self.editor_overlay_objects(reader, job, panel, config)
            for obj in objects:
                obj["item"] = panel.item
                obj["scale"] = scale
                self.draw_editor_object(canvas, obj, scale, margin, page_height, state, top_offset=page_top)
            y_cursor = page_top + canvas_height + 20

        canvas.configure(scrollregion=(0, 0, max_width + 24, y_cursor))

    def draw_editor_panel(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["page_images"] = []
        page = reader.pages[panel.page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        scale = min(940 / page_width, 700 / page_height)
        margin = 16.0
        state["scale"] = scale
        state["objects"] = {}

        def to_canvas(x: float, y: float) -> tuple[float, float]:
            return margin + x * scale, margin + (page_height - y) * scale

        canvas_width = page_width * scale + margin * 2
        canvas_height = page_height * scale + margin * 2
        canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#e8edf3", outline="")
        canvas.create_rectangle(margin, margin, canvas_width - margin, canvas_height - margin, fill="white", outline="#9aa7b5")

        page_image = self.editor_page_image(job.pdf_path, panel.page_index, page_width, page_height, scale, state)
        if page_image is not None:
            state["page_images"].append(page_image)
            canvas.create_image(margin, margin, image=page_image, anchor=tk.NW)
        else:
            for start, end, _length in programmer.collect_page_line_segments(reader, panel.page_index, min_length=1.0):
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                canvas.create_line(x1, y1, x2, y2, fill="#3f4750", width=max(1, int(scale)))
            self.draw_editor_page_text(canvas, page, page_height, scale, margin)
        objects = self.editor_overlay_objects(reader, job, panel, config)
        for obj in objects:
            self.draw_editor_object(canvas, obj, scale, margin, page_height, state)

    def editor_page_image(
        self,
        pdf_path: Path,
        page_index: int,
        page_width: float,
        page_height: float,
        scale: float,
        state: dict[str, Any],
        rotation_degrees: int = 0,
    ) -> Any | None:
        if Image is None or ImageTk is None:
            return None
        cache = state.setdefault("render_cache", {})
        normalized_rotation = rotation_degrees % 360
        key = (str(pdf_path), page_index, round(scale, 4), normalized_rotation)
        if isinstance(cache, dict) and key in cache:
            return cache[key]

        output_dir = state.get("output_dir")
        page_count = int(state.get("pdf_page_count") or 0)
        render_dpi = self.REVIEW_RENDER_DPI
        cached_page_path: Path | None = None
        if isinstance(output_dir, Path):
            cached_page_path = self.review_raster_page_path(output_dir, pdf_path, render_dpi, page_index)
            cache_dir = self.review_raster_cache_dir(output_dir, pdf_path, render_dpi)
            all_pages_cached = page_count > 0 and all(
                (cache_dir / f"page_{idx + 1:03d}.png").exists()
                for idx in range(page_count)
            )
            if not cached_page_path.exists() and page_count > 0:
                self.render_pdfium_single_page_to_file(pdf_path, page_index, cached_page_path, render_dpi)
                all_pages_cached = page_count > 0 and all(
                    (cache_dir / f"page_{idx + 1:03d}.png").exists()
                    for idx in range(page_count)
                )
            if cached_page_path.exists() and page_count > 1 and not all_pages_cached:
                callback = state.get("render_callback")
                self.start_async_review_raster_render(
                    pdf_path,
                    page_count,
                    output_dir,
                    state,
                    callback if callable(callback) else None,
                )
            if not cached_page_path.exists() and page_count > 0:
                callback = state.get("render_callback")
                self.start_async_review_raster_render(
                    pdf_path,
                    page_count,
                    output_dir,
                    state,
                    callback if callable(callback) else None,
                )
                return None
            output_path = cached_page_path
        else:
            temp_dir = Path(str(state.get("render_temp_dir") or tempfile.gettempdir()))
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = temp_dir / f"page_{page_index + 1}_{abs(hash(key))}.png"
            if not self.render_pdfium_single_page_to_file(pdf_path, page_index, output_path, render_dpi):
                ghostscript = self.ghostscript_executable()
                if ghostscript is None:
                    return None
                command = [
                    str(ghostscript),
                    "-q",
                    "-dSAFER",
                    "-dBATCH",
                    "-dNOPAUSE",
                    "-sDEVICE=png16m",
                    f"-r{render_dpi}",
                    f"-dFirstPage={page_index + 1}",
                    f"-dLastPage={page_index + 1}",
                    f"-sOutputFile={output_path}",
                    str(pdf_path),
                ]
                try:
                    subprocess.run(command, check=True, capture_output=True, timeout=30)
                except Exception:
                    return None
        try:
            image = Image.open(output_path).convert("RGB")
            if normalized_rotation:
                image = image.rotate(-normalized_rotation, expand=True)
            if normalized_rotation % 180:
                target_size = (max(1, int(round(page_height * scale))), max(1, int(round(page_width * scale))))
            else:
                target_size = (max(1, int(round(page_width * scale))), max(1, int(round(page_height * scale))))
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image = image.resize(target_size, resampling)
            photo = ImageTk.PhotoImage(image)
        except Exception:
            return None
        finally:
            if cached_page_path is None:
                try:
                    output_path.unlink(missing_ok=True)
                except Exception:
                    pass
        if isinstance(cache, dict):
            cache[key] = photo
        return photo

    @staticmethod
    def ghostscript_executable() -> Path | None:
        for name in ("gswin64c", "gswin32c", "gs"):
            found = shutil.which(name)
            if found:
                return Path(found)
        candidates = [
            Path(r"C:\Program Files\gs\gs10.05.1\bin\gswin64c.exe"),
            Path(r"C:\Program Files\gs\gs10.04.0\bin\gswin64c.exe"),
            Path(r"C:\Program Files\gs\gs10.03.1\bin\gswin64c.exe"),
            Path(r"C:\Program Files (x86)\GPLGS\gswin32c.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def draw_editor_page_text(
        self,
        canvas: tk.Canvas,
        page: Any,
        page_height: float,
        scale: float,
        margin: float,
        top_offset: float = 0.0,
        page_width: float | None = None,
        rotation_degrees: int = 0,
    ) -> None:
        def to_canvas(x: float, y: float) -> tuple[float, float]:
            rotation = rotation_degrees % 360
            if rotation == 90:
                view_x, view_y = y, x
            elif rotation == 180:
                width = float(page_width or 0)
                view_x, view_y = width - x, y
            elif rotation == 270:
                width = float(page_width or 0)
                view_x, view_y = page_height - y, width - x
            else:
                view_x, view_y = x, page_height - y
            return margin + view_x * scale, top_offset + margin + view_y * scale

        def visitor(text: str, _cm: Any, tm: Any, _font_dict: Any, font_size: float) -> None:
            value = str(text).strip()
            if not value:
                return
            try:
                x, y = programmer.text_origin_from_matrices(_cm, tm)
            except Exception:
                return
            if not (0 <= x <= 620 and 0 <= y <= 800):
                return
            cx, cy = to_canvas(x, y)
            size = max(5, min(12, int(float(font_size) * scale)))
            canvas.create_text(cx, cy, text=value[:80], anchor=tk.SW, fill="#4b5563", font=("Arial", size))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            return

    def editor_overlay_objects(
        self,
        reader: PdfReader,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
        geometry_cache: dict[Any, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        page = reader.pages[panel.page_index]
        cache_key = (id(reader), panel.page_index, round(float(panel.width), 4), round(float(panel.height), 4))
        cached_geometry = geometry_cache.get(cache_key) if geometry_cache is not None else None
        pdf_cfg = config.get("pdf", {})
        if cached_geometry is None:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            cached_geometry = {
                "width": width,
                "height": height,
                "bbox": programmer.estimate_panel_bbox(reader, panel.page_index),
                "indicator_bbox": programmer.estimate_panel_bbox(reader, panel.page_index, use_outer_edges=True),
                "marker_bbox": programmer.estimate_panel_outline_bbox(reader, panel.page_index, panel.width, panel.height),
                "obstacles": programmer.collect_page_obstacles(reader, panel.page_index),
            }
            if geometry_cache is not None:
                if len(geometry_cache) > 80:
                    geometry_cache.clear()
                geometry_cache[cache_key] = cached_geometry
        width = float(cached_geometry["width"])
        height = float(cached_geometry["height"])
        bbox = cached_geometry["bbox"]
        indicator_bbox = cached_geometry["indicator_bbox"]
        marker_bbox = cached_geometry["marker_bbox"]
        obstacles = cached_geometry["obstacles"]
        label_bbox = marker_bbox or bbox
        active_marker_bbox = marker_bbox or (indicator_bbox if panel.machine == "WJ" and indicator_bbox is not None else bbox)

        objects: list[dict[str, Any]] = []
        avoid_rects: list[tuple[float, float, float, float]] = []
        marker_rect = (
            programmer.indicator_marker_rect(
                panel.machine,
                panel.indicator_corner,
                active_marker_bbox,
                width,
                height,
                pdf_cfg,
                precise_edges=marker_bbox is not None,
                panel=panel,
            )
            if panel.indicator_corner and panel.machine
            else None
        )
        if marker_rect is not None:
            avoid_rects.append(marker_rect)

        if panel.remake_excluded or panel.manual_x:
            remake_cfg = pdf_cfg.get("remake", {}) if isinstance(pdf_cfg.get("remake", {}), dict) else {}
            x_margin = programmer.parse_float(remake_cfg.get("x_margin", 48), 48)
            line_width = programmer.parse_float(remake_cfg.get("x_line_width", 10), 10)
            x_key = "manual_x" if panel.manual_x else "remake_xout"
            objects.append({
                "key": x_key,
                "name": "manual X" if panel.manual_x else "remake X-out",
                "kind": "x",
                "lines": [
                    ((x_margin, x_margin), (width - x_margin, height - x_margin)),
                    ((x_margin, height - x_margin), (width - x_margin, x_margin)),
                ],
                "line_width": line_width,
                "rect": (x_margin, x_margin, width - x_margin, height - x_margin),
            })
            return objects

        remake_rect: tuple[float, float, float, float] | None = None
        if panel.remake and not panel.hide_remake:
            remake_text = panel.remake_text or "REMAKE"
            remake_x, remake_y, remake_font, remake_rect = programmer.choose_remake_banner_position(
                width,
                height,
                pdf_cfg,
                bbox,
                indicator_bbox,
                panel,
                remake_text,
            )
            objects.append({
                "key": "remake",
                "name": remake_text,
                "kind": "text",
                "lines": [remake_text],
                "x": remake_x,
                "y": remake_y,
                "font_size": remake_font,
                "rect": remake_rect,
            })
            avoid_rects.append(remake_rect)

        if panel.diamon_fusion and not panel.hide_diamon_fusion:
            diamon_text = panel.diamon_fusion_text or "DIAMON FUSION"
            df_font = panel.diamon_fusion_font_size or float(pdf_cfg.get("diamon_fusion_font_size", 36))
            if remake_rect is not None:
                df_x, df_y, df_rect = programmer.choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
            else:
                df_x, df_y, df_font, df_rect = programmer.choose_diamon_banner_position(
                    width,
                    height,
                    pdf_cfg,
                    bbox,
                    indicator_bbox,
                    diamon_text,
                    df_font,
                    obstacles,
                    avoid_rects,
                    panel,
                )
            if panel.diamon_fusion_x is not None and panel.diamon_fusion_y is not None:
                df_x, df_y = panel.diamon_fusion_x, panel.diamon_fusion_y
                df_width = programmer.stringWidth(diamon_text, "Helvetica-Bold", df_font) + 12
                df_height = df_font + 10
                df_rect = (df_x - df_width / 2, df_y - 4, df_x + df_width / 2, df_y + df_height)
                if remake_rect is not None and programmer.rects_overlap(programmer.pad_rect(df_rect, 4), programmer.pad_rect(remake_rect, 2)):
                    df_x, df_y, df_rect = programmer.choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
            objects.append({
                "key": "diamon_fusion",
                "name": diamon_text,
                "kind": "text",
                "lines": [diamon_text],
                "x": df_x,
                "y": df_y,
                "font_size": df_font,
                "rect": df_rect,
            })
            avoid_rects.append(df_rect)

        label_lines = programmer.override_text_lines(panel.label_text) or [f"{job.aw_order}.{panel.item}"]
        if panel.machine and not panel.label_text:
            label_lines.append(panel.machine)
        font_size = panel.label_font_size or float(pdf_cfg.get("label_font_size", 21))
        label_x, label_y = programmer.choose_label_position(
            width,
            height,
            label_bbox,
            label_lines,
            font_size,
            obstacles,
            avoid_rects,
            panel,
            pdf_cfg,
        )
        if panel.label_x is not None and panel.label_y is not None:
            label_x, label_y = panel.label_x, panel.label_y
        if not panel.hide_label:
            objects.append({
                "key": "label",
                "name": "order/machine label",
                "kind": "text",
                "lines": label_lines,
                "x": label_x,
                "y": label_y,
                "font_size": font_size,
                "rect": programmer.label_rect(label_lines, label_x, label_y, font_size),
            })

        if panel.indicator_corner and panel.machine and not panel.hide_indicator:
            geometry = programmer.indicator_marker_geometry(
                panel.machine,
                panel.indicator_corner,
                active_marker_bbox,
                width,
                height,
                pdf_cfg,
                precise_edges=marker_bbox is not None,
                panel=panel,
            )
            if geometry is not None:
                geometry.update({
                    "key": "indicator",
                    "name": "indicator",
                    "x": geometry["point"][0],
                    "y": geometry["point"][1],
                    "machine": panel.machine,
                    "anchor_bbox": active_marker_bbox,
                    "page_width": width,
                    "page_height": height,
                    "pdf_cfg": pdf_cfg,
                    "precise_edges": marker_bbox is not None,
                })
                objects.append(geometry)
        return objects

    def draw_editor_object(
        self,
        canvas: tk.Canvas,
        obj: dict[str, Any],
        scale: float,
        margin: float,
        page_height: float,
        state: dict[str, Any],
        top_offset: float = 0.0,
        page_width: float | None = None,
        rotation_degrees: int = 0,
    ) -> None:
        key = obj["key"]
        object_key = f"{obj.get('item')}_{key}" if obj.get("item") is not None else str(key)
        tag = f"edit_{object_key}"
        effective_page_width = page_width if page_width is not None else float(obj.get("page_width", 0.0))
        if effective_page_width <= 0:
            effective_page_width = float(obj.get("page_height", page_height))
        page_pixel_width = effective_page_width * scale
        page_pixel_height = page_height * scale
        rotation = rotation_degrees % 360

        def to_canvas(x: float, y: float) -> tuple[float, float]:
            image_x = x * scale
            image_y = (page_height - y) * scale
            if rotation == 90:
                image_x, image_y = page_pixel_height - image_y, image_x
            elif rotation == 180:
                image_x, image_y = page_pixel_width - image_x, page_pixel_height - image_y
            elif rotation == 270:
                image_x, image_y = image_y, page_pixel_width - image_x
            return margin + image_x, top_offset + margin + image_y

        def bind_item(item_id: int) -> None:
            canvas.addtag_withtag(tag, item_id)
            canvas.addtag_withtag("editable_mark", item_id)

        blue = "#0078d4"
        if obj["kind"] == "text":
            font_size = max(1, int(round(float(obj["font_size"]) * scale)))
            leading = float(obj["font_size"]) * 1.18
            first_y = float(obj["y"]) + leading * (len(obj["lines"]) - 1) / 2
            baseline_center_offset = float(obj["font_size"]) * 0.35
            for index, line in enumerate(obj["lines"]):
                cx, cy = to_canvas(float(obj["x"]), first_y - index * leading + baseline_center_offset)
                bind_item(canvas.create_text(cx, cy, text=line, fill=blue, font=("Arial", -font_size, "bold"), anchor=tk.CENTER))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        elif obj.get("kind") == "wj":
            for start, end in obj["lines"]:
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                bind_item(canvas.create_line(x1, y1, x2, y2, fill=blue, width=max(1, int(round(float(obj["line_width"]) * scale)))))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        elif obj.get("kind") == "x":
            for start, end in obj["lines"]:
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                bind_item(canvas.create_line(x1, y1, x2, y2, fill=blue, width=max(2, int(round(float(obj["line_width"]) * scale)))))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        else:
            cx, cy = to_canvas(*obj["center"])
            radius = max(1.0, float(obj["radius"]) * scale)
            bind_item(canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=blue, outline=blue))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))

        state["objects"][object_key] = obj
        canvas.tag_bind(tag, "<ButtonPress-1>", lambda event, object_key=object_key: state["start_drag"](event, object_key))
        show_mark_menu = state.get("show_mark_menu")
        if callable(show_mark_menu):
            canvas.tag_bind(tag, "<Button-3>", lambda event, object_key=object_key: show_mark_menu(event, object_key))
            canvas.tag_bind(tag, "<Double-Button-1>", lambda event, object_key=object_key: show_mark_menu(event, object_key))

    def open_last_report(self) -> None:
        if not self.last_reports:
            messagebox.showinfo("No report yet", "Run a batch first.")
            return
        webbrowser.open(self.last_reports.html_report.resolve().as_uri())

    def open_output_folder(self) -> None:
        path = Path(self.output_dir_var.get()).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_latest_batch(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        if run_folder is None or not run_folder.exists():
            messagebox.showinfo("No batch yet", "No generated batch folder was found.")
            return
        os.startfile(run_folder)

    def open_input_folder(self) -> None:
        path = Path(self.folder_var.get()).resolve()
        if path.name.lower() == "orders":
            path = path.parent
        if not path.exists():
            messagebox.showerror("Input folder not found", f"Could not find:\n{path}")
            return
        os.startfile(path)

    def install_shortcut(self) -> None:
        script = programmer.project_root() / "Create-ShowerProgrammerShortcut.ps1"
        if not script.exists():
            messagebox.showerror("Shortcut installer missing", f"Could not find {script.name}.")
            return
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(programmer.project_root()),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            messagebox.showerror("Install shortcut failed", str(exc))
            return
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
        if result.returncode != 0:
            messagebox.showerror("Install shortcut failed", output or f"PowerShell exited with {result.returncode}.")
            return
        messagebox.showinfo("Shortcut installed", output or "Shortcut installed.")

    def open_sketches_folder(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        path = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_programs_folder(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        path = (run_folder / "Programs") if run_folder else output_dir / "Programs"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_config(self) -> None:
        path = self.config_path(Path(self.folder_var.get()).resolve())
        if not path.exists():
            messagebox.showerror("Config not found", f"Could not find:\n{path}")
            return
        os.startfile(path)


def main() -> None:
    root = ctk.CTk() if ctk is not None else tk.Tk()
    app = ShowerProgrammerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
