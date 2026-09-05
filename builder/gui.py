import datetime
import os
import platform
import subprocess
import sys
from pathlib import Path
from queue import Empty, Queue
from typing import List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from builder.pipeline import (
    STEP_COUNT,
    STEP_NAMES,
    BuildPipeline,
)
from builder.utils import _external_base

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Step indicator states
STATE_PENDING = "pending"
STATE_ACTIVE = "active"
STATE_DONE = "done"
STATE_ERROR = "error"

_ICONS = {
    STATE_PENDING: "○",
    STATE_ACTIVE:  "⟳",
    STATE_DONE:    "✓",
    STATE_ERROR:   "✗",
}
_COLORS = {
    STATE_PENDING: "gray60",
    STATE_ACTIVE:  "#3B8BEB",
    STATE_DONE:    "#2ECC71",
    STATE_ERROR:   "#E74C3C",
}

# GUI step labels (shorter than internal names for the 2-column layout)
_GUI_STEP_LABELS = [
    "Validate",
    "Extract RSDK",
    "Compress SFX",
    "Re-encode Videos",
    "Resize Images",
    "Apply Mods",
    "Repack & Build",  # steps 6+7 shown as one row entry
]

# Which internal step indices map to each GUI row (steps 6 and 7 share row 6)
_GUI_STEP_MAP = [0, 1, 2, 3, 4, 5, 6]  # GUI row → first pipeline step


class BuilderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sonic Mania Xbox ISO Builder")
        self.geometry("680x620")
        self.resizable(False, False)

        self._queue: Queue = Queue()
        self._pipeline: Optional[BuildPipeline] = None
        self._step_states: List[str] = [STATE_PENDING] * STEP_COUNT
        self._step_labels: List[ctk.CTkLabel] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 6}

        # Title
        title = ctk.CTkLabel(
            self, text="Sonic Mania Xbox ISO Builder",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.pack(pady=(18, 4))

        # RSDK path row
        path_frame = ctk.CTkFrame(self, fg_color="transparent")
        path_frame.pack(fill="x", **pad)

        ctk.CTkLabel(path_frame, text="Data.rsdk:", width=80, anchor="w").pack(side="left")
        self._rsdk_var = ctk.StringVar()
        path_entry = ctk.CTkEntry(path_frame, textvariable=self._rsdk_var, width=420)
        path_entry.pack(side="left", padx=(4, 6))
        ctk.CTkButton(
            path_frame, text="Browse", width=80,
            command=self._browse_rsdk,
        ).pack(side="left")

        # Plus DLC toggle. Off by default: enabling it is a deliberate choice by someone
        # who owns a Plus Data.rsdk, since the engine assumes those assets are present
        # and nothing inspects the archive to check.
        self._plus_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self,
            text="Enable Plus Content (Requires Data.rsdk from Sonic Mania Plus)",
            variable=self._plus_var,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=(4, 8))

        # Separator
        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=20, pady=2)

        # Steps grid (2 columns, 4 rows)
        steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        steps_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(steps_frame, text="Build Steps:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )

        # 7 GUI steps in 2 columns: left col = 0,1,2,3  right col = 4,5,6
        gui_labels = [
            "Validate",
            "Extract RSDK",
            "Compress SFX",
            "Re-encode Videos",
            "Resize Images",
            "Apply Mods",
            "Repack & Build",
        ]

        self._step_labels = []
        for i, label in enumerate(gui_labels):
            col_base = 0 if i < 4 else 2
            row = 1 + (i % 4)
            lbl = ctk.CTkLabel(
                steps_frame,
                text=f"{_ICONS[STATE_PENDING]}  {label}",
                font=ctk.CTkFont(size=13),
                text_color=_COLORS[STATE_PENDING],
                anchor="w",
                width=200,
            )
            lbl.grid(row=row, column=col_base, sticky="w", padx=(0, 20), pady=2)
            self._step_labels.append(lbl)

        steps_frame.columnconfigure(0, weight=1)
        steps_frame.columnconfigure(1, weight=0)
        steps_frame.columnconfigure(2, weight=1)
        steps_frame.columnconfigure(3, weight=0)

        # Separator
        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=20, pady=2)

        # Progress bar
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", padx=20, pady=(8, 2))

        self._progress_bar = ctk.CTkProgressBar(prog_frame, width=530)
        self._progress_bar.set(0)
        self._progress_bar.pack(side="left")

        self._pct_label = ctk.CTkLabel(prog_frame, text=" 0%", width=40)
        self._pct_label.pack(side="left", padx=(8, 0))

        self._status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self._status_label.pack(anchor="w", padx=24, pady=(0, 4))

        # Log box
        self._log_box = ctk.CTkTextbox(
            self, height=150, font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=20, pady=4)
        self._log_box._textbox.tag_configure("error",   foreground="#E74C3C")
        self._log_box._textbox.tag_configure("success", foreground="#2ECC71")

        # Bottom row: Build button
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=(4, 16))

        self._open_btn = ctk.CTkButton(
            bottom_frame, text="Open Output Folder", width=160,
            command=self._open_output, state="disabled",
        )
        self._open_btn.pack(side="left")

        self._build_btn = ctk.CTkButton(
            bottom_frame, text="Build ISO", width=120,
            command=self._start_build,
        )
        self._build_btn.pack(side="right")

    # ------------------------------------------------------------------
    # UI callbacks
    # ------------------------------------------------------------------

    def _browse_rsdk(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Data.rsdk",
            filetypes=[("RSDK Archive", "*.rsdk"), ("All files", "*.*")],
        )
        if path:
            self._rsdk_var.set(path)

    def _start_build(self) -> None:
        rsdk_path = self._rsdk_var.get().strip()
        if not rsdk_path:
            messagebox.showerror("Error", "Please select a Data.rsdk file first.")
            return

        # Reset UI
        self._build_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")
        self._progress_bar.set(0)
        self._pct_label.configure(text=" 0%")
        self._status_label.configure(text="Starting…")
        self._clear_log()

        for i, lbl in enumerate(self._step_labels):
            self._set_step_state_label(lbl, STATE_PENDING, _get_gui_label(i))

        self._step_states = [STATE_PENDING] * STEP_COUNT
        self._queue = Queue()

        self._pipeline = BuildPipeline(rsdk_path, self._queue, plus_enabled=self._plus_var.get())
        self._pipeline.start()
        self._poll_queue()

    def _open_output(self) -> None:
        output_dir = _external_base() / "Output"
        if sys.platform == "win32":
            os.startfile(str(output_dir))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(output_dir)])
        else:
            subprocess.run(["xdg-open", str(output_dir)])

    # ------------------------------------------------------------------
    # Queue polling
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                event = self._queue.get_nowait()
                self._handle_event(event)
        except Empty:
            pass

        # Keep polling while pipeline is running
        if self._pipeline is not None:
            self.after(50, self._poll_queue)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]

        if kind == "log":
            self._append_log(event[1])

        elif kind == "step_start":
            step = event[1]
            self._step_states[step] = STATE_ACTIVE
            self._update_step_ui(step, STATE_ACTIVE)
            self._status_label.configure(text=f"{STEP_NAMES[step]}…")

        elif kind == "step_done":
            step = event[1]
            self._step_states[step] = STATE_DONE
            self._update_step_ui(step, STATE_DONE)

        elif kind == "step_error":
            step = event[1]
            msg = event[2]
            self._step_states[step] = STATE_ERROR
            self._update_step_ui(step, STATE_ERROR)
            self._append_log(f"ERROR: {msg}")

        elif kind == "progress":
            pct = event[1]
            self._progress_bar.set(pct)
            self._pct_label.configure(text=f"{int(pct * 100):3d}%")

        elif kind == "done":
            output_dir = event[1]
            self._progress_bar.set(1.0)
            self._pct_label.configure(text="100%")
            self._status_label.configure(text=f"Done!  Output at: {output_dir}")
            self._append_log(f"\nBuild complete. Output at: {output_dir}")
            self._build_btn.configure(state="normal")
            self._open_btn.configure(state="normal")
            self._pipeline = None

        elif kind == "error":
            msg = event[1]
            self._status_label.configure(text=f"Error: {msg}")
            self._append_log(f"\nBuild failed: {msg}")
            self._build_btn.configure(state="normal")
            self._pipeline = None

    # ------------------------------------------------------------------
    # Step label helpers
    # ------------------------------------------------------------------

    def _update_step_ui(self, pipeline_step: int, state: str) -> None:
        """Map a pipeline step index to a GUI label index and update it."""
        gui_index = _pipeline_step_to_gui(pipeline_step)
        if gui_index is None:
            return
        lbl = self._step_labels[gui_index]
        self._set_step_state_label(lbl, state, _get_gui_label(gui_index))

    def _set_step_state_label(self, lbl: ctk.CTkLabel, state: str, text: str) -> None:
        icon = _ICONS[state]
        color = _COLORS[state]
        lbl.configure(text=f"{icon}  {text}", text_color=color)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _append_log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        stripped = msg.strip()
        is_error = (
            stripped.startswith("FAILED")
            or stripped.startswith("ERROR")
            or stripped.startswith("Build failed")
        )
        is_success = stripped.startswith("Build complete")
        tag = "error" if is_error else "success" if is_success else ""
        self._log_box.configure(state="normal")
        self._log_box._textbox.insert("end", line, tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Pipeline steps 6 (STEP_REPACK) and 7 (STEP_BUILD) both map to GUI row 6
_PIPELINE_TO_GUI = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 6,
}

_GUI_LABELS = [
    "Validate",
    "Extract RSDK",
    "Compress SFX",
    "Re-encode Videos",
    "Resize Images",
    "Apply Mods",
    "Repack & Build",
]


def _pipeline_step_to_gui(step: int) -> Optional[int]:
    return _PIPELINE_TO_GUI.get(step)


def _get_gui_label(gui_index: int) -> str:
    return _GUI_LABELS[gui_index]


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    app = BuilderApp()
    app.mainloop()
