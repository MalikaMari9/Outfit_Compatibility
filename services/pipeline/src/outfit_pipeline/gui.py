from __future__ import annotations

import json
import queue
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from PIL import Image, ImageDraw, ImageTk

from .engine import OutfitCompatibilityPipeline
from .scoring import label_from_score


class PipelineGui(tk.Tk):
    def __init__(self, pipeline: OutfitCompatibilityPipeline) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.title("Outfit Compatibility - Mock Test GUI")
        self.geometry("1180x760")

        self._preview_refs = {}
        self._rank_rows = []
        self._busy = False
        self._interactive_controls: list[tk.Widget] = []
        self._wheel_canvas: Optional[tk.Canvas] = None

        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind_all("<Button-4>", self._on_linux_scroll_up, add="+")
        self.bind_all("<Button-5>", self._on_linux_scroll_down, add="+")

        self._build_layout()

    def _build_layout(self) -> None:
        top_bar = ttk.Frame(self, padding=10)
        top_bar.pack(fill=tk.X)
        ttk.Label(
            top_bar,
            text=f"Device: {self.pipeline.device} | Data: {self.pipeline.data_root}",
        ).pack(anchor=tk.W)

        method_row = ttk.Frame(top_bar)
        method_row.pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(method_row, text="Foreground method").pack(side=tk.LEFT)
        self.bg_method_var = tk.StringVar(value=self.pipeline.foreground_method)
        self.bg_method_combo = ttk.Combobox(
            method_row,
            textvariable=self.bg_method_var,
            values=list(self.pipeline.available_foreground_methods()),
            width=14,
            state="readonly",
        )
        self.bg_method_combo.pack(side=tk.LEFT, padx=(8, 8))
        self.apply_method_btn = ttk.Button(method_row, text="Apply", command=self._apply_bg_method)
        self.apply_method_btn.pack(side=tk.LEFT)
        self._interactive_controls.extend([self.bg_method_combo, self.apply_method_btn])

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(top_bar, textvariable=self.status_var).pack(anchor=tk.W, pady=(4, 0))
        self.progress = ttk.Progressbar(top_bar, mode="indeterminate", length=360)
        self.progress.pack(anchor=tk.W, pady=(4, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._pair_tab = self._create_scrollable_tab(nb, "Pair Score")
        self._rank_tab = self._create_scrollable_tab(nb, "Top-K Retrieval")

        self._build_pair_tab(self._pair_tab)
        self._build_rank_tab(self._rank_tab)

    def _create_scrollable_tab(self, notebook: ttk.Notebook, title: str) -> ttk.Frame:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text=title)

        canvas = tk.Canvas(tab, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        body = ttk.Frame(canvas, padding=10)
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def on_body_config(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_config(event=None):
            if event is not None:
                canvas.itemconfigure(body_window, width=event.width)

        def enter_canvas(_event=None):
            self._wheel_canvas = canvas

        body.bind("<Configure>", on_body_config)
        canvas.bind("<Configure>", on_canvas_config)
        canvas.bind("<Enter>", enter_canvas)
        body.bind("<Enter>", enter_canvas)
        return body

    def _on_mousewheel(self, event) -> None:
        if self._wheel_canvas is None:
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta != 0:
            self._wheel_canvas.yview_scroll(delta, "units")

    def _on_linux_scroll_up(self, _event) -> None:
        if self._wheel_canvas is not None:
            self._wheel_canvas.yview_scroll(-1, "units")

    def _on_linux_scroll_down(self, _event) -> None:
        if self._wheel_canvas is not None:
            self._wheel_canvas.yview_scroll(1, "units")

    def _build_pair_tab(self, root: ttk.Frame) -> None:
        self.top_path_var = tk.StringVar()
        self.bottom_path_var = tk.StringVar()

        form = ttk.Frame(root)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Top image").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(form, textvariable=self.top_path_var, width=95).grid(row=0, column=1, sticky=tk.EW, pady=4)
        self.top_browse_btn = ttk.Button(form, text="Browse", command=lambda: self._browse_into(self.top_path_var))
        self.top_browse_btn.grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(form, text="Bottom image").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(form, textvariable=self.bottom_path_var, width=95).grid(row=1, column=1, sticky=tk.EW, pady=4)
        self.bottom_browse_btn = ttk.Button(form, text="Browse", command=lambda: self._browse_into(self.bottom_path_var))
        self.bottom_browse_btn.grid(row=1, column=2, padx=(8, 0), pady=4)

        form.columnconfigure(1, weight=1)

        self.run_pair_btn = ttk.Button(root, text="Run Pair Compatibility", command=self._run_pair)
        self.run_pair_btn.pack(anchor=tk.W, pady=(8, 8))
        self._interactive_controls.extend([self.top_browse_btn, self.bottom_browse_btn, self.run_pair_btn])

        preview_row = ttk.Frame(root)
        preview_row.pack(fill=tk.X)
        left_col = ttk.Frame(preview_row)
        left_col.pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(left_col, text="Top Original").pack(anchor=tk.W)
        self.pair_top_preview = ttk.Label(left_col, text="", anchor=tk.CENTER)
        self.pair_top_preview.pack()
        ttk.Label(left_col, text="Top BG Erased").pack(anchor=tk.W, pady=(8, 0))
        self.pair_top_fg_preview = ttk.Label(left_col, text="", anchor=tk.CENTER)
        self.pair_top_fg_preview.pack()

        right_col = ttk.Frame(preview_row)
        right_col.pack(side=tk.LEFT)
        ttk.Label(right_col, text="Bottom Original").pack(anchor=tk.W)
        self.pair_bottom_preview = ttk.Label(right_col, text="", anchor=tk.CENTER)
        self.pair_bottom_preview.pack()
        ttk.Label(right_col, text="Bottom BG Erased").pack(anchor=tk.W, pady=(8, 0))
        self.pair_bottom_fg_preview = ttk.Label(right_col, text="", anchor=tk.CENTER)
        self.pair_bottom_fg_preview.pack()

        ttk.Label(root, text="Result").pack(anchor=tk.W, pady=(12, 4))
        pair_text_box = ttk.Frame(root)
        pair_text_box.pack(fill=tk.BOTH, expand=True)
        self.pair_text = tk.Text(pair_text_box, wrap=tk.WORD, height=20)
        pair_text_scroll = ttk.Scrollbar(pair_text_box, orient=tk.VERTICAL, command=self.pair_text.yview)
        self.pair_text.configure(yscrollcommand=pair_text_scroll.set)
        self.pair_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pair_text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_rank_tab(self, root: ttk.Frame) -> None:
        self.rank_query_var = tk.StringVar()
        self.rank_mode_var = tk.StringVar(value="top2bottom")
        self.rank_topk_var = tk.IntVar(value=5)
        self.rank_shortlist_var = tk.IntVar(value=self.pipeline.cfg.retrieval.shortlist_k)

        form = ttk.Frame(root)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Mode").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.mode_box = ttk.Combobox(form, textvariable=self.rank_mode_var, values=["top2bottom", "bottom2top"], width=14, state="readonly")
        self.mode_box.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(form, text="Query image").grid(row=0, column=2, sticky=tk.W, padx=(16, 8), pady=4)
        ttk.Entry(form, textvariable=self.rank_query_var, width=68).grid(row=0, column=3, sticky=tk.EW, pady=4)
        self.rank_browse_btn = ttk.Button(form, text="Browse", command=lambda: self._browse_into(self.rank_query_var))
        self.rank_browse_btn.grid(row=0, column=4, padx=(8, 0), pady=4)

        ttk.Label(form, text="Top-K").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.rank_topk_spin = ttk.Spinbox(form, from_=1, to=50, textvariable=self.rank_topk_var, width=8)
        self.rank_topk_spin.grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(form, text="Shortlist-K").grid(row=1, column=2, sticky=tk.W, padx=(16, 8), pady=4)
        self.rank_shortlist_spin = ttk.Spinbox(
            form,
            from_=5,
            to=5000,
            increment=5,
            textvariable=self.rank_shortlist_var,
            width=10,
        )
        self.rank_shortlist_spin.grid(row=1, column=3, sticky=tk.W, pady=4)

        self.run_rank_btn = ttk.Button(form, text="Run Retrieval", command=self._run_rank)
        self.run_rank_btn.grid(row=1, column=4, padx=(8, 0), pady=4)
        self._interactive_controls.extend(
            [
                self.mode_box,
                self.rank_browse_btn,
                self.rank_topk_spin,
                self.rank_shortlist_spin,
                self.run_rank_btn,
            ]
        )
        form.columnconfigure(3, weight=1)

        row = ttk.Frame(root)
        row.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        left = ttk.Frame(row)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("rank", "item_id", "category", "score", "label", "image_path")
        table_box = ttk.Frame(left)
        table_box.pack(fill=tk.BOTH, expand=True)

        self.rank_table = ttk.Treeview(table_box, columns=cols, show="headings", height=18)
        self.rank_table.heading("rank", text="Rank")
        self.rank_table.heading("item_id", text="Item ID")
        self.rank_table.heading("category", text="Category")
        self.rank_table.heading("score", text="Final Score")
        self.rank_table.heading("label", text="Label")
        self.rank_table.heading("image_path", text="Image Path")
        self.rank_table.column("rank", width=60, anchor=tk.CENTER)
        self.rank_table.column("item_id", width=110)
        self.rank_table.column("category", width=180)
        self.rank_table.column("score", width=90, anchor=tk.CENTER)
        self.rank_table.column("label", width=160)
        self.rank_table.column("image_path", width=320)
        rank_table_vscroll = ttk.Scrollbar(table_box, orient=tk.VERTICAL, command=self.rank_table.yview)
        rank_table_hscroll = ttk.Scrollbar(table_box, orient=tk.HORIZONTAL, command=self.rank_table.xview)
        self.rank_table.configure(yscrollcommand=rank_table_vscroll.set, xscrollcommand=rank_table_hscroll.set)
        self.rank_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rank_table_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        rank_table_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.rank_table.bind("<<TreeviewSelect>>", self._on_rank_select)

        right = ttk.Frame(row)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        ttk.Label(right, text="Query Preview").pack(anchor=tk.W)
        self.rank_query_preview = ttk.Label(right, text="", anchor=tk.CENTER)
        self.rank_query_preview.pack(pady=(0, 8))
        ttk.Label(right, text="Query BG Erased").pack(anchor=tk.W)
        self.rank_query_fg_preview = ttk.Label(right, text="", anchor=tk.CENTER)
        self.rank_query_fg_preview.pack(pady=(0, 8))

        ttk.Label(right, text="Selected Candidate").pack(anchor=tk.W)
        self.rank_candidate_preview = ttk.Label(right, text="", anchor=tk.CENTER)
        self.rank_candidate_preview.pack(pady=(0, 8))
        ttk.Label(right, text="Candidate BG Erased").pack(anchor=tk.W)
        self.rank_candidate_fg_preview = ttk.Label(right, text="", anchor=tk.CENTER)
        self.rank_candidate_fg_preview.pack(pady=(0, 8))

        ttk.Label(right, text="Selected Details").pack(anchor=tk.W)
        rank_details_box = ttk.Frame(right)
        rank_details_box.pack(fill=tk.BOTH, expand=True)
        self.rank_details = tk.Text(rank_details_box, wrap=tk.WORD, height=18, width=44)
        rank_details_scroll = ttk.Scrollbar(rank_details_box, orient=tk.VERTICAL, command=self.rank_details.yview)
        self.rank_details.configure(yscrollcommand=rank_details_scroll.set)
        self.rank_details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rank_details_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _browse_into(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            var.set(path)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self._busy = busy
        for ctl in self._interactive_controls:
            try:
                if isinstance(ctl, ttk.Combobox):
                    ctl.configure(state="disabled" if busy else "readonly")
                else:
                    ctl.configure(state=tk.DISABLED if busy else tk.NORMAL)
            except tk.TclError:
                pass

        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        if status is not None:
            self._set_status(status)
        else:
            self.update_idletasks()

    def _run_async(
        self,
        start_message: str,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
    ) -> None:
        if self._busy:
            self._set_status("A task is already running. Please wait.")
            return

        self._set_busy(True, status=start_message)
        q: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                q.put(("ok", task()))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", exc))

        threading.Thread(target=worker, daemon=True).start()
        self.after(90, lambda: self._poll_async_result(q, on_success))

    def _poll_async_result(self, q: queue.Queue[tuple[str, Any]], on_success: Callable[[Any], None]) -> None:
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            self.after(90, lambda: self._poll_async_result(q, on_success))
            return

        self._set_busy(False)
        if kind == "err":
            self._set_status("Failed.")
            messagebox.showerror("Error", str(payload))
            return
        on_success(payload)

    def _apply_bg_method(self) -> None:
        method = self.bg_method_var.get().strip()
        try:
            self.pipeline.set_foreground_method(method)
        except Exception as exc:
            messagebox.showerror("Method Error", str(exc))
            return
        self._set_status(f"Foreground method set to: {self.pipeline.foreground_method}")

    def _preview(self, label: ttk.Label, path: str | Path, key: str, size: int = 220) -> None:
        p = Path(path)
        if not p.exists():
            label.configure(text="(image missing)", image="")
            return
        img = Image.open(p).convert("RGB")
        img.thumbnail((size, size))
        tk_img = ImageTk.PhotoImage(img)
        self._preview_refs[key] = tk_img
        label.configure(image=tk_img, text="")

    def _parse_crop_box(self, autocrop_info: object) -> Optional[tuple[int, int, int, int]]:
        if not isinstance(autocrop_info, dict):
            return None
        box = autocrop_info.get("crop_box")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            return None
        try:
            x1, y1, x2, y2 = [int(v) for v in box]
        except Exception:
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2)

    def _processed_path_from_autocrop(self, original_path: str | Path, autocrop_info: object) -> str:
        if isinstance(autocrop_info, dict):
            p = str(autocrop_info.get("processed_path") or "").strip()
            if p and Path(p).exists():
                return p
        return str(original_path)

    def _preview_with_autocrop_box(
        self,
        label: ttk.Label,
        path: str | Path,
        key: str,
        autocrop_info: object,
        size: int = 220,
        tag: str = "",
    ) -> None:
        p = Path(path)
        if not p.exists():
            label.configure(text="(image missing)", image="")
            return
        img = Image.open(p).convert("RGB")

        box = self._parse_crop_box(autocrop_info)
        if box is not None:
            draw = ImageDraw.Draw(img)
            applied = bool(autocrop_info.get("applied")) if isinstance(autocrop_info, dict) else False
            color = (32, 172, 92) if applied else (220, 180, 40)
            line_w = max(2, int(round(max(img.size) / 180)))
            draw.rectangle(box, outline=color, width=line_w)

            if isinstance(autocrop_info, dict):
                reason = str(autocrop_info.get("reason") or "").strip()
                conf = float(autocrop_info.get("confidence") or 0.0)
            else:
                reason = ""
                conf = 0.0
            short_reason = reason if len(reason) <= 22 else f"{reason[:22]}..."
            txt = f"{tag} {short_reason} {conf:.2f}".strip()
            tx = max(3, box[0] + 3)
            ty = max(3, box[1] - 14)
            tw = max(60, int(len(txt) * 6.2))
            draw.rectangle((tx - 2, ty - 2, tx + tw, ty + 10), fill=(0, 0, 0))
            draw.text((tx, ty), txt, fill=color)

        img.thumbnail((size, size))
        tk_img = ImageTk.PhotoImage(img)
        self._preview_refs[key] = tk_img
        label.configure(image=tk_img, text="")

    def _preview_foreground(self, label: ttk.Label, path: str | Path, key: str, size: int = 220) -> None:
        p = Path(path)
        if not p.exists():
            label.configure(text="(image missing)", image="")
            return
        try:
            fg = self.pipeline.get_foreground_preview(p, background="checkerboard")
        except Exception:
            label.configure(text="(bg erase failed)", image="")
            return
        fg.thumbnail((size, size))
        tk_img = ImageTk.PhotoImage(fg)
        self._preview_refs[key] = tk_img
        label.configure(image=tk_img, text="")

    def _run_pair(self) -> None:
        top = self.top_path_var.get().strip()
        bottom = self.bottom_path_var.get().strip()
        if not top or not bottom:
            messagebox.showerror("Missing input", "Please select both top and bottom images.")
            return

        self._run_async(
            start_message=f"Running pair compatibility... (bg={self.pipeline.foreground_method})",
            task=lambda: self.pipeline.score_pair(top_image=top, bottom_image=bottom),
            on_success=lambda out: self._finish_pair(out, top=top, bottom=bottom),
        )

    def _finish_pair(self, out, top: str, bottom: str) -> None:
        top_auto = out.details.get("top_autocrop") if isinstance(out.details, dict) else None
        bottom_auto = out.details.get("bottom_autocrop") if isinstance(out.details, dict) else None
        self._preview_with_autocrop_box(self.pair_top_preview, top, "pair_top", top_auto, tag="TOP")
        self._preview_with_autocrop_box(self.pair_bottom_preview, bottom, "pair_bottom", bottom_auto, tag="BOTTOM")
        top_fg_path = self._processed_path_from_autocrop(top, top_auto)
        bottom_fg_path = self._processed_path_from_autocrop(bottom, bottom_auto)
        self._preview_foreground(self.pair_top_fg_preview, top_fg_path, "pair_top_fg")
        self._preview_foreground(self.pair_bottom_fg_preview, bottom_fg_path, "pair_bottom_fg")

        self.pair_text.delete("1.0", tk.END)
        self.pair_text.insert(tk.END, json.dumps(out.to_dict(), indent=2))
        self._set_status(f"Pair complete. Final score={out.score.final:.4f} ({out.label})")

    def _run_rank(self) -> None:
        mode = self.rank_mode_var.get().strip()
        query = self.rank_query_var.get().strip()
        top_k = int(self.rank_topk_var.get())
        shortlist_k = int(self.rank_shortlist_var.get())

        if not query:
            messagebox.showerror("Missing input", "Please select a query image.")
            return

        self._run_async(
            start_message=(
                f"Running retrieval... (bg={self.pipeline.foreground_method}) "
                "first run can take time while embedding cache is built."
            ),
            task=lambda: self.pipeline.rank(
                mode=mode,  # type: ignore[arg-type]
                query_image=query,
                top_k=top_k,
                shortlist_k=shortlist_k,
            ),
            on_success=lambda rows: self._finish_rank(rows, query=query),
        )

    def _finish_rank(self, rows, query: str) -> None:
        query_auto = None
        if rows:
            first_details = rows[0].details if hasattr(rows[0], "details") else {}
            if isinstance(first_details, dict):
                query_auto = first_details.get("query_autocrop")
        self._preview_with_autocrop_box(self.rank_query_preview, query, "rank_query", query_auto, tag="QUERY")
        query_fg_path = self._processed_path_from_autocrop(query, query_auto)
        self._preview_foreground(self.rank_query_fg_preview, query_fg_path, "rank_query_fg")

        self._rank_rows = rows
        for iid in self.rank_table.get_children():
            self.rank_table.delete(iid)
        self.rank_details.delete("1.0", tk.END)
        self.rank_candidate_preview.configure(image="", text="")
        self.rank_candidate_fg_preview.configure(image="", text="")

        for r in rows:
            label = label_from_score(
                r.score.final,
                threshold=self.pipeline.cfg.model.threshold,
                borderline_threshold=self.pipeline.cfg.model.borderline_threshold,
                weak_threshold=self.pipeline.cfg.model.weak_threshold,
                excellent_threshold=self.pipeline.cfg.model.excellent_threshold,
            )
            self.rank_table.insert(
                "",
                tk.END,
                values=(
                    r.rank,
                    r.item_id,
                    str(r.details.get("candidate_category_name") or r.details.get("candidate_category") or ""),
                    f"{r.score.final:.4f}",
                    label,
                    r.image_path,
                ),
            )

        self._set_status(f"Retrieval complete. Showing {len(rows)} result(s).")

    def _on_rank_select(self, _event=None) -> None:
        selected = self.rank_table.selection()
        if not selected:
            return
        item = self.rank_table.item(selected[0])
        vals = item.get("values", [])
        if not vals:
            return
        rank = int(vals[0])
        if rank < 1 or rank > len(self._rank_rows):
            return
        row = self._rank_rows[rank - 1]
        self._preview(self.rank_candidate_preview, row.image_path, "rank_candidate")
        self._preview_foreground(self.rank_candidate_fg_preview, row.image_path, "rank_candidate_fg")
        self.rank_details.delete("1.0", tk.END)
        self.rank_details.insert(tk.END, json.dumps(row.to_dict(), indent=2))


def launch_gui(config_path: str | Path) -> None:
    pipeline = OutfitCompatibilityPipeline(config_path=config_path)
    app = PipelineGui(pipeline=pipeline)
    app.mainloop()
