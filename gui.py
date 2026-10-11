# Credits & License
# Original Author: oboroge0 (Hayamimi - Real-time multilingual speech-to-text on CPU)
# Repository: https://github.com/oboroge0/hayamimi
# License: MIT License

"""hayamimi GUI Control Panel.

Provides a graphical control panel layout to download models, select audio input (including WebSocket),
dynamically enumerate input (mic) and output (speaker) devices, configure advanced CLI options,
toggle local server settings, switch GUI display language with multi-language i18n support,
and launch/terminate the real-time transcription process with live console logs.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    ROOT_DIR = getattr(sys, "_MEIPASS", ROOT_DIR)
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    scripts_dir = os.path.join(ROOT_DIR, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ROOT_DIR

LOCALES_DIR = os.path.join(ROOT_DIR, "locales")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".hayamimi_gui_config.json")

DOWNLOAD_SCRIPT = os.path.abspath(os.path.join(ROOT_DIR, "scripts", "download_models.py"))
if not os.path.exists(DOWNLOAD_SCRIPT) and getattr(sys, "frozen", False):
    alt_dl = os.path.abspath(os.path.join(ROOT_DIR, "download_models.py"))
    if os.path.exists(alt_dl):
        DOWNLOAD_SCRIPT = alt_dl

TRANSCRIBE_SCRIPT = os.path.abspath(os.path.join(ROOT_DIR, "scripts", "realtime_transcribe.py"))
if not os.path.exists(TRANSCRIBE_SCRIPT) and getattr(sys, "frozen", False):
    alt_tr = os.path.abspath(os.path.join(ROOT_DIR, "realtime_transcribe.py"))
    if os.path.exists(alt_tr):
        TRANSCRIBE_SCRIPT = alt_tr


def get_python_cmd():
    """Get appropriate Python interpreter command when running from source or frozen executable.

    Returns None when running from a frozen executable so that bundled modules run in-process.
    """
    if getattr(sys, "frozen", False):
        return None
    return sys.executable


def load_locale(lang_code: str) -> dict:
    """Load localization JSON dictionary for given language code."""
    filepath = os.path.join(LOCALES_DIR, f"{lang_code}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback to English if file missing or corrupt
    en_filepath = os.path.join(LOCALES_DIR, "en.json")
    if os.path.exists(en_filepath):
        with open(en_filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_saved_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def enumerate_audio_devices():
    """Dynamically enumerate available audio input (mic) and output (speaker) devices."""
    input_devices = []
    output_devices = []
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        for dev in devices:
            name = dev.get("name", "").strip()
            if not name:
                continue
            if dev.get("max_input_channels", 0) > 0 and name not in input_devices:
                input_devices.append(name)
            if dev.get("max_output_channels", 0) > 0 and name not in output_devices:
                output_devices.append(name)
    except Exception:
        pass
    return input_devices, output_devices


class HayamimiGUI(tk.Tk):
    LANG_MAP = {
        "Japanese": "ja",
        "English": "en",
        "Chinese": "zh",
        "Korean": "ko",
        "Cantonese": "yue",
    }
    REV_LANG_MAP = {v: k for k, v in LANG_MAP.items()}

    def __init__(self):
        super().__init__()

        saved_cfg = load_saved_config()
        self.ui_lang = saved_cfg.get("ui_lang", "ja")
        self.i18n = load_locale(self.ui_lang)

        self.geometry("980x780")
        self.minsize(860, 600)

        self.transcribe_process = None
        self.transcribe_stop_event = None
        self.download_process = None
        self.log_queue = queue.Queue()

        self._create_widgets()
        self._refresh_audio_devices()
        self._poll_log_queue()
        self._update_ui_strings()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def t(self, key_path: str, default: str = "") -> str:
        """Helper to retrieve nested translation key e.g. 'audio_settings.frame_title'."""
        keys = key_path.split(".")
        val = self.i18n
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default or key_path
        return str(val)

    def _create_widgets(self):
        # Header / UI Language Selector Frame
        header_frame = ttk.Frame(self, padding=(10, 5, 10, 5))
        header_frame.pack(fill=tk.X, expand=False)

        title_container = ttk.Frame(header_frame)
        title_container.pack(side=tk.LEFT)

        self.title_lbl = ttk.Label(title_container, text="", font=("Helvetica", 14, "bold"))
        self.title_lbl.pack(side=tk.TOP, anchor=tk.W)

        self.attr_lbl = ttk.Label(
            title_container,
            text="Hayamimi (MIT License) — Original Repository: https://github.com/oboroge0/hayamimi",
            font=("Helvetica", 8),
            foreground="#555555",
        )
        self.attr_lbl.pack(side=tk.TOP, anchor=tk.W, pady=(2, 0))

        self.lang_select_lbl = ttk.Label(header_frame, text="")
        self.lang_select_lbl.pack(side=tk.RIGHT, padx=(10, 5))

        self.ui_lang_var = tk.StringVar(value=self.REV_LANG_MAP.get(self.ui_lang, "Japanese"))
        self.ui_lang_dropdown = ttk.Combobox(
            header_frame,
            textvariable=self.ui_lang_var,
            values=list(self.LANG_MAP.keys()),
            state="readonly",
            width=12,
        )
        self.ui_lang_dropdown.pack(side=tk.RIGHT)
        self.ui_lang_dropdown.bind("<<ComboboxSelected>>", self._on_ui_language_changed)

        # Scrollable Canvas Container for controls
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas, padding=10)

        self.scroll_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_frame_id = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_frame_id, width=e.width)
        )

        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        top_frame = self.scroll_frame

        # 1. Model Download Section
        self.dl_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.dl_frame.pack(fill=tk.X, pady=(0, 10))

        self.minimal_var = tk.BooleanVar(value=True)
        self.minimal_check = ttk.Checkbutton(
            self.dl_frame,
            text="",
            variable=self.minimal_var,
        )
        self.minimal_check.pack(side=tk.LEFT, padx=(0, 15))

        self.dl_btn = ttk.Button(
            self.dl_frame,
            text="",
            command=self._start_download,
        )
        self.dl_btn.pack(side=tk.LEFT)

        status_subframe = ttk.Frame(self.dl_frame)
        status_subframe.pack(side=tk.LEFT, padx=(15, 0), fill=tk.Y)

        self.dl_total_status_var = tk.StringVar(value="Total Progress: Idle")
        self.dl_total_status_lbl = ttk.Label(
            status_subframe,
            textvariable=self.dl_total_status_var,
            font=("Helvetica", 9, "bold"),
            foreground="#111111",
        )
        self.dl_total_status_lbl.pack(anchor=tk.W)

        self.dl_file_status_var = tk.StringVar(value="Current File: Ready")
        self.dl_file_status_lbl = ttk.Label(
            status_subframe,
            textvariable=self.dl_file_status_var,
            font=("Helvetica", 8),
            foreground="#555555",
        )
        self.dl_file_status_lbl.pack(anchor=tk.W)

        # Legacy alias for compatibility
        self.dl_status_var = self.dl_total_status_var

        # 2. Audio Input Source & Device Selector
        self.audio_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.audio_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 0: Mode Selector & Refresh & Execution
        self.lbl_input_mode = ttk.Label(self.audio_frame, text="")
        self.lbl_input_mode.grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.input_var = tk.StringVar(value="mic")
        self.input_dropdown = ttk.Combobox(
            self.audio_frame,
            textvariable=self.input_var,
            state="readonly",
            width=28,
        )
        self.input_dropdown.grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=4)

        self.refresh_dev_btn = ttk.Button(
            self.audio_frame,
            text="",
            command=self._refresh_audio_devices,
        )
        self.refresh_dev_btn.grid(row=0, column=2, sticky=tk.W, padx=(0, 15), pady=4)

        self.start_stop_btn = ttk.Button(
            self.audio_frame,
            text="",
            command=self._toggle_transcription,
            width=20,
        )
        self.start_stop_btn.grid(row=0, column=3, sticky=tk.W, pady=4)

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.audio_frame, textvariable=self.status_var, font=("Helvetica", 10, "bold"))
        self.status_label.grid(row=0, column=4, sticky=tk.W, padx=(10, 0), pady=4)

        # Row 1: Mic Device
        self.lbl_mic_dev = ttk.Label(self.audio_frame, text="")
        self.lbl_mic_dev.grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.mic_var = tk.StringVar(value="")
        self.mic_dropdown = ttk.Combobox(self.audio_frame, textvariable=self.mic_var, width=45)
        self.mic_dropdown.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)

        self.lbl_dev_hint = ttk.Label(self.audio_frame, text="")
        self.lbl_dev_hint.grid(row=1, column=3, columnspan=2, sticky=tk.W)

        # Row 2: Speaker Device
        self.lbl_speaker_dev = ttk.Label(self.audio_frame, text="")
        self.lbl_speaker_dev.grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.speaker_var = tk.StringVar(value="")
        self.speaker_dropdown = ttk.Combobox(self.audio_frame, textvariable=self.speaker_var, state="readonly", width=45)
        self.speaker_dropdown.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)

        # Row 3: WebSocket Host & Port Configuration
        self.lbl_ws_host = ttk.Label(self.audio_frame, text="")
        self.lbl_ws_host.grid(row=3, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.ws_host_var = tk.StringVar(value="127.0.0.1")
        self.ws_host_entry = ttk.Entry(self.audio_frame, textvariable=self.ws_host_var, width=20)
        self.ws_host_entry.grid(row=3, column=1, sticky=tk.W, pady=4)

        self.lbl_ws_port = ttk.Label(self.audio_frame, text="")
        self.lbl_ws_port.grid(row=3, column=2, sticky=tk.E, padx=(10, 5), pady=4)

        self.ws_port_var = tk.StringVar(value="8766")
        self.ws_port_entry = ttk.Entry(self.audio_frame, textvariable=self.ws_port_var, width=10)
        self.ws_port_entry.grid(row=3, column=3, sticky=tk.W, pady=4)

        # 3. Fine-Tuning & Pipeline Parameters
        self.pipeline_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.pipeline_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 0: en_tier & punct_model
        self.lbl_en_tier = ttk.Label(self.pipeline_frame, text="")
        self.lbl_en_tier.grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.en_tier_var = tk.StringVar(value="v3")
        self.en_tier_dropdown = ttk.Combobox(self.pipeline_frame, textvariable=self.en_tier_var, values=["v3", "v2"], state="readonly", width=12)
        self.en_tier_dropdown.grid(row=0, column=1, sticky=tk.W, padx=(0, 20), pady=4)

        self.lbl_punct = ttk.Label(self.pipeline_frame, text="")
        self.lbl_punct.grid(row=0, column=2, sticky=tk.W, padx=(0, 5), pady=4)
        self.punct_var = tk.StringVar(value="bert")
        self.punct_dropdown = ttk.Combobox(self.pipeline_frame, textvariable=self.punct_var, values=["bert", "4class"], state="readonly", width=12)
        self.punct_dropdown.grid(row=0, column=3, sticky=tk.W, pady=4)

        # Row 1: threads & min_silence
        self.lbl_threads = ttk.Label(self.pipeline_frame, text="")
        self.lbl_threads.grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.threads_var = tk.StringVar(value="4")
        self.threads_entry = ttk.Entry(self.pipeline_frame, textvariable=self.threads_var, width=14)
        self.threads_entry.grid(row=1, column=1, sticky=tk.W, padx=(0, 20), pady=4)

        self.lbl_min_silence = ttk.Label(self.pipeline_frame, text="")
        self.lbl_min_silence.grid(row=1, column=2, sticky=tk.W, padx=(0, 5), pady=4)
        self.min_silence_var = tk.StringVar(value="0.35")
        self.min_silence_entry = ttk.Entry(self.pipeline_frame, textvariable=self.min_silence_var, width=14)
        self.min_silence_entry.grid(row=1, column=3, sticky=tk.W, pady=4)

        # Row 2: max_speech & max_resident
        self.lbl_max_speech = ttk.Label(self.pipeline_frame, text="")
        self.lbl_max_speech.grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.max_speech_var = tk.StringVar(value="12.0")
        self.max_speech_entry = ttk.Entry(self.pipeline_frame, textvariable=self.max_speech_var, width=14)
        self.max_speech_entry.grid(row=2, column=1, sticky=tk.W, padx=(0, 20), pady=4)

        self.lbl_max_resident = ttk.Label(self.pipeline_frame, text="")
        self.lbl_max_resident.grid(row=2, column=2, sticky=tk.W, padx=(0, 5), pady=4)
        self.max_resident_var = tk.StringVar(value="3")
        self.max_resident_entry = ttk.Entry(self.pipeline_frame, textvariable=self.max_resident_var, width=14)
        self.max_resident_entry.grid(row=2, column=3, sticky=tk.W, pady=4)

        # 4. Processing Toggles
        self.toggles_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.toggles_frame.pack(fill=tk.X, pady=(0, 10))

        self.no_partial_var = tk.BooleanVar(value=False)
        self.no_partial_check = ttk.Checkbutton(self.toggles_frame, text="", variable=self.no_partial_var)
        self.no_partial_check.pack(side=tk.LEFT, padx=(0, 20))

        self.no_refine_var = tk.BooleanVar(value=False)
        self.no_refine_check = ttk.Checkbutton(self.toggles_frame, text="", variable=self.no_refine_var)
        self.no_refine_check.pack(side=tk.LEFT, padx=(0, 20))

        self.speakers_var = tk.BooleanVar(value=False)
        self.speakers_check = ttk.Checkbutton(self.toggles_frame, text="", variable=self.speakers_var)
        self.speakers_check.pack(side=tk.LEFT)

        # 5. Dictionaries & Language Switching
        self.lang_sw_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.lang_sw_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 0: translate
        self.lbl_translate = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_translate.grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.translate_var = tk.StringVar(value="")
        self.translate_entry = ttk.Entry(self.lang_sw_frame, textvariable=self.translate_var, width=25)
        self.translate_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=4)
        self.lbl_translate_hint = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_translate_hint.grid(row=0, column=2, columnspan=2, sticky=tk.W)

        # Row 1: hotwords path
        self.lbl_hotwords = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_hotwords.grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.hotwords_var = tk.StringVar(value="")
        self.hotwords_entry = ttk.Entry(self.lang_sw_frame, textvariable=self.hotwords_var, width=40)
        self.hotwords_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)
        self.btn_browse_hotwords = ttk.Button(self.lang_sw_frame, text="", command=self._browse_hotwords)
        self.btn_browse_hotwords.grid(row=1, column=3, sticky=tk.W, pady=4)

        # Row 2: replace path
        self.lbl_replace = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_replace.grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.replace_var = tk.StringVar(value="")
        self.replace_entry = ttk.Entry(self.lang_sw_frame, textvariable=self.replace_var, width=40)
        self.replace_entry.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)
        self.btn_browse_replace = ttk.Button(self.lang_sw_frame, text="", command=self._browse_replace)
        self.btn_browse_replace.grid(row=2, column=3, sticky=tk.W, pady=4)

        # Row 3: mode, switch guard, lid confirm
        self.lbl_mode = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_mode.grid(row=3, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.mode_var = tk.StringVar(value="balanced")
        self.mode_dropdown = ttk.Combobox(self.lang_sw_frame, textvariable=self.mode_var, values=["balanced", "single", "fast"], state="readonly", width=12)
        self.mode_dropdown.grid(row=3, column=1, sticky=tk.W, padx=(0, 15), pady=4)

        self.lbl_lang_guard = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_lang_guard.grid(row=3, column=2, sticky=tk.E, padx=(5, 5), pady=4)
        self.lang_guard_var = tk.StringVar(value="2.0")
        self.lang_guard_entry = ttk.Entry(self.lang_sw_frame, textvariable=self.lang_guard_var, width=8)
        self.lang_guard_entry.grid(row=3, column=3, sticky=tk.W, pady=4)

        self.lbl_lid_confirm = ttk.Label(self.lang_sw_frame, text="")
        self.lbl_lid_confirm.grid(row=4, column=0, sticky=tk.W, padx=(0, 5), pady=4)
        self.lid_confirm_var = tk.StringVar(value="2")
        self.lid_confirm_entry = ttk.Entry(self.lang_sw_frame, textvariable=self.lid_confirm_var, width=8)
        self.lid_confirm_entry.grid(row=4, column=1, sticky=tk.W, pady=4)

        # 6. Optional Local Server Settings
        self.server_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.server_frame.pack(fill=tk.X, pady=(0, 10))

        toggle_subframe = ttk.Frame(self.server_frame)
        toggle_subframe.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 15))

        self.serve_var = tk.BooleanVar(value=True)
        self.serve_check = ttk.Checkbutton(
            toggle_subframe,
            text="",
            variable=self.serve_var,
        )
        self.serve_check.pack(anchor=tk.W, pady=(0, 5))

        self.urls_subframe = ttk.Frame(self.server_frame)
        self.urls_subframe.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.address_widgets = []
        addresses = [
            ("http://localhost:8833/dashboard", "server_settings.dashboard_desc"),
            ("http://localhost:8833/", "server_settings.overlay_desc"),
            ("http://localhost:8833/transcript", "server_settings.transcript_desc"),
        ]

        for url, desc_key in addresses:
            row = ttk.Frame(self.urls_subframe)
            row.pack(fill=tk.X, pady=2)
            url_lbl = ttk.Label(row, text=url, font=("Courier", 9, "bold"), foreground="#0066cc", width=30)
            url_lbl.pack(side=tk.LEFT, anchor=tk.W)
            desc_lbl = ttk.Label(row, text="", font=("Helvetica", 9))
            desc_lbl.pack(side=tk.LEFT, anchor=tk.W)
            self.address_widgets.append((desc_lbl, desc_key))

        # 7. Output Console / Log Area
        self.log_frame = ttk.LabelFrame(top_frame, text="", padding=10)
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, font=("Courier", 9), height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _update_ui_strings(self):
        """Update all text strings in the interface based on current locale."""
        self.title_lbl.config(text=self.t("app_title"))
        self.title(self.t("app_title"))
        self.lang_select_lbl.config(text=self.t("language_selector"))

        self.dl_frame.config(text=self.t("model_download.frame_title"))
        self.minimal_check.config(text=self.t("model_download.minimal_check"))
        self.dl_btn.config(text=self.t("model_download.download_btn"))

        self.audio_frame.config(text=self.t("audio_settings.frame_title"))
        self.lbl_input_mode.config(text=self.t("audio_settings.input_mode"))

        # Preserve current selection code
        mode_names = [
            self.t("audio_settings.mic_input"),
            self.t("audio_settings.speaker_input"),
            self.t("audio_settings.mix_input"),
            self.t("audio_settings.ws_input"),
        ]
        self.input_mode_map = {
            self.t("audio_settings.mic_input"): "mic",
            self.t("audio_settings.speaker_input"): "speaker",
            self.t("audio_settings.mix_input"): "mix",
            self.t("audio_settings.ws_input"): "ws",
        }
        self.input_dropdown["values"] = mode_names
        # Set dropdown string matching current code
        cur_code = self.input_var.get()
        matched_str = mode_names[0]
        for name, code in self.input_mode_map.items():
            if code == cur_code:
                matched_str = name
                break
        self.input_dropdown.set(matched_str)

        self.refresh_dev_btn.config(text=self.t("audio_settings.refresh_btn"))
        if self.transcribe_process and self.transcribe_process.poll() is None:
            self.start_stop_btn.config(text=self.t("audio_settings.stop_transcription"))
            self.status_var.set(self.t("audio_settings.status_running"))
        else:
            self.start_stop_btn.config(text=self.t("audio_settings.start_transcription"))
            self.status_var.set(self.t("audio_settings.status_stopped"))

        self.lbl_mic_dev.config(text=self.t("audio_settings.mic_device"))
        self.lbl_speaker_dev.config(text=self.t("audio_settings.speaker_device"))
        self.lbl_dev_hint.config(text=self.t("audio_settings.device_hint"))

        self.lbl_ws_host.config(text=self.t("audio_settings.ws_host"))
        self.lbl_ws_port.config(text=self.t("audio_settings.ws_port"))

        self.pipeline_frame.config(text=self.t("pipeline_settings.frame_title"))
        self.lbl_en_tier.config(text=self.t("pipeline_settings.en_tier"))
        self.lbl_punct.config(text=self.t("pipeline_settings.punct_model"))
        self.lbl_threads.config(text=self.t("pipeline_settings.threads"))
        self.lbl_min_silence.config(text=self.t("pipeline_settings.min_silence"))
        self.lbl_max_speech.config(text=self.t("pipeline_settings.max_speech"))
        self.lbl_max_resident.config(text=self.t("pipeline_settings.max_resident"))

        self.toggles_frame.config(text=self.t("toggles.frame_title"))
        self.no_partial_check.config(text=self.t("toggles.no_partial"))
        self.no_refine_check.config(text=self.t("toggles.no_refine"))
        self.speakers_check.config(text=self.t("toggles.speakers"))

        self.lang_sw_frame.config(text=self.t("lang_switching.frame_title"))
        self.lbl_translate.config(text=self.t("lang_switching.translate"))
        self.lbl_translate_hint.config(text=self.t("lang_switching.translate_hint"))
        self.lbl_hotwords.config(text=self.t("lang_switching.hotwords"))
        self.btn_browse_hotwords.config(text=self.t("lang_switching.browse"))
        self.lbl_replace.config(text=self.t("lang_switching.replace"))
        self.btn_browse_replace.config(text=self.t("lang_switching.browse"))
        self.lbl_mode.config(text=self.t("lang_switching.mode"))
        self.lbl_lang_guard.config(text=self.t("lang_switching.lang_guard"))
        self.lbl_lid_confirm.config(text=self.t("lang_switching.lid_confirm"))

        self.server_frame.config(text=self.t("server_settings.frame_title"))
        self.serve_check.config(text=self.t("server_settings.enable_server"))

        for desc_lbl, desc_key in self.address_widgets:
            desc_lbl.config(text=f"— {self.t(desc_key)}")

        self.log_frame.config(text=self.t("console.frame_title"))

    def _on_ui_language_changed(self, event=None):
        selected_name = self.ui_lang_var.get()
        code = self.LANG_MAP.get(selected_name, "ja")
        if code != self.ui_lang:
            self.ui_lang = code
            self.i18n = load_locale(code)
            self._update_ui_strings()

            cfg = load_saved_config()
            cfg["ui_lang"] = code
            save_config(cfg)

    def _browse_hotwords(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.hotwords_var.set(filename)

    def _browse_replace(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.replace_var.set(filename)

    def _refresh_audio_devices(self):
        default_in = self.t("audio_settings.system_default_input")
        default_out = self.t("audio_settings.system_default_output")

        input_devs, output_devs = enumerate_audio_devices()
        input_list = [default_in] + input_devs
        output_list = [default_out] + output_devs

        self.mic_dropdown["values"] = input_list
        self.speaker_dropdown["values"] = output_list

        if not self.mic_var.get() or self.mic_var.get() not in input_list:
            self.mic_var.set(default_in)
        if not self.speaker_var.get() or self.speaker_var.get() not in output_list:
            self.speaker_var.set(default_out)

    def _log(self, message: str):
        self.log_queue.put(message)

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_text.insert(tk.END, msg)
            self.log_text.see(tk.END)
        self.after(100, self._poll_log_queue)

    def _get_subprocess_env(self):
        env = os.environ.copy()
        base_path = getattr(sys, "_MEIPASS", ROOT_DIR)
        paths_to_add = [base_path, os.path.join(base_path, "scripts")]
        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            paths_to_add.append(pythonpath)
        env["PYTHONPATH"] = os.path.pathsep.join(paths_to_add)
        return env

    def _run_subprocess(self, cmd: list[str], on_complete=None):
        def reader():
            try:
                env = self._get_subprocess_env()

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=APP_DIR,
                    env=env,
                )
                if cmd[1] == DOWNLOAD_SCRIPT:
                    self.download_process = proc
                elif cmd[1] == TRANSCRIBE_SCRIPT:
                    self.transcribe_process = proc

                for line in proc.stdout:
                    self._log(line)

                proc.wait()
            except Exception as e:
                self._log(f"\n[GUI Error] Failed to execute process: {e}\n")
            finally:
                if on_complete:
                    self.after(0, on_complete)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

    def _parse_download_line(self, line: str, is_minimal: bool):
        if not hasattr(self, "_dl_model_count"):
            self._dl_model_count = 0
            self._dl_total_models = 4 if is_minimal else 10

        if line.startswith("[get ]") or line.startswith("[skip]"):
            self._dl_model_count += 1
            pct = min(100, int((self._dl_model_count / self._dl_total_models) * 100))
            label = line[6:].strip()
            self.dl_total_status_var.set(
                f"Total Progress: Model {self._dl_model_count}/{self._dl_total_models} - {label} ({pct}%)"
            )
            self.dl_file_status_var.set("Current File: Initializing...")
        elif "%" in line:
            self.dl_file_status_var.set(f"Current File: {line}")

    def _run_download_subprocess(self, cmd: list[str], on_complete=None):
        def reader():
            try:
                self._dl_model_count = 0
                self._dl_total_models = 4 if "--minimal" in cmd else 10
                env = self._get_subprocess_env()

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=APP_DIR,
                    env=env,
                )
                self.download_process = proc

                buffer = ""
                while True:
                    ch = proc.stdout.read(1)
                    if not ch:
                        break
                    if ch in ("\r", "\n"):
                        text = buffer.strip()
                        if text:
                            self.after(0, self._parse_download_line, text, "--minimal" in cmd)
                            self._log(text + "\n")
                        buffer = ""
                    else:
                        buffer += ch
                if buffer.strip():
                    text = buffer.strip()
                    self.after(0, self._parse_download_line, text, "--minimal" in cmd)
                    self._log(text + "\n")

                proc.wait()
                if proc.returncode != 0:
                    err_msg = f"Error (code {proc.returncode})"
                    self.after(0, self.dl_total_status_var.set, f"Total Progress: {err_msg}")
                    self.after(0, self.dl_file_status_var.set, err_msg)
                    self._log(f"\n[Model Download Process Error] Download subprocess exited with code {proc.returncode}\n")
            except Exception as e:
                err_msg = f"Error: {e}"
                self.after(0, self.dl_total_status_var.set, f"Total Progress: {err_msg}")
                self.after(0, self.dl_file_status_var.set, err_msg)
                self._log(f"\n[Model Download Exception] {e}\n")
            finally:
                if on_complete:
                    self.after(0, on_complete)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

    def _run_download_in_thread(self, minimal: bool, on_complete=None):
        def worker():
            import io
            import traceback

            class StatusWriter(io.TextIOBase):
                def __init__(self, gui_obj, is_minimal):
                    self.gui_obj = gui_obj
                    self.is_minimal = is_minimal
                    self.buffer = ""

                def write(self, s):
                    for ch in s:
                        if ch in ("\r", "\n"):
                            line = self.buffer.strip()
                            if line:
                                self.gui_obj.after(0, self.gui_obj._parse_download_line, line, self.is_minimal)
                                self.gui_obj._log(line + "\n")
                            self.buffer = ""
                        else:
                            self.buffer += ch
                    return len(s)

                def flush(self):
                    if self.buffer.strip():
                        line = self.buffer.strip()
                        self.gui_obj.after(0, self.gui_obj._parse_download_line, line, self.is_minimal)
                        self.gui_obj._log(line + "\n")
                        self.buffer = ""

            self._dl_model_count = 0
            self._dl_total_models = 4 if minimal else 10
            writer = StatusWriter(self, minimal)
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = writer
                sys.stderr = writer

                try:
                    import scripts.download_models as dl_mod
                except ImportError:
                    import download_models as dl_mod

                args_list = ["--minimal"] if minimal else []
                sys_argv_orig = sys.argv
                try:
                    sys.argv = [DOWNLOAD_SCRIPT] + args_list
                    dl_mod.main()
                finally:
                    sys.argv = sys_argv_orig
                writer.flush()
            except Exception as e:
                err_msg = f"Error: {e}"
                tb_str = traceback.format_exc()
                self.after(0, self.dl_total_status_var.set, f"Total Progress: {err_msg}")
                self.after(0, self.dl_file_status_var.set, err_msg)
                self._log(f"\n[Model Download Error] {err_msg}\n{tb_str}\n")
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                if on_complete:
                    self.after(0, on_complete)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _start_download(self):
        if self.download_process and self.download_process.poll() is None:
            messagebox.showinfo("In Progress", self.t("model_download.in_progress"))
            return

        py_cmd = get_python_cmd()

        self.dl_btn.config(state=tk.DISABLED)
        self.start_stop_btn.config(state=tk.DISABLED)
        self.dl_total_status_var.set("Total Progress: " + self.t("model_download.started"))
        self.dl_file_status_var.set("Current File: Starting...")

        def complete():
            self.dl_btn.config(state=tk.NORMAL)
            self.start_stop_btn.config(state=tk.NORMAL)
            self.download_process = None
            cur_status = self.dl_total_status_var.get()
            if not cur_status or ("Error" not in cur_status and "code" not in cur_status):
                self.dl_total_status_var.set("Total Progress: " + self.t("model_download.completed"))
                self.dl_file_status_var.set("Current File: Completed")

        if py_cmd is None or getattr(sys, "frozen", False):
            self._run_download_in_thread(self.minimal_var.get(), on_complete=complete)
        else:
            cmd = [py_cmd, DOWNLOAD_SCRIPT]
            if self.minimal_var.get():
                cmd.append("--minimal")
            self._run_download_subprocess(cmd, on_complete=complete)

    def _toggle_transcription(self):
        if self.transcribe_process and self.transcribe_process.poll() is None:
            self._stop_transcription()
        else:
            self._start_transcription()

    def _run_transcribe_in_thread(self, args_list: list[str], on_complete=None):
        def worker():
            import io
            import traceback

            class StatusWriter(io.TextIOBase):
                def __init__(self, gui_obj):
                    self.gui_obj = gui_obj
                    self.buffer = ""

                def write(self, s):
                    for ch in s:
                        if ch in ("\n", "\r"):
                            line = self.buffer.strip()
                            if line:
                                self.gui_obj._log(line + "\n")
                            self.buffer = ""
                        else:
                            self.buffer += ch
                    return len(s)

                def flush(self):
                    if self.buffer.strip():
                        self.gui_obj._log(self.buffer.strip() + "\n")
                        self.buffer = ""

            writer = StatusWriter(self)
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = writer
                sys.stderr = writer

                try:
                    import scripts.realtime_transcribe as tr_mod
                except ImportError:
                    import realtime_transcribe as tr_mod

                sys_argv_orig = sys.argv
                try:
                    sys.argv = [TRANSCRIBE_SCRIPT] + args_list
                    tr_mod.main(stop_event=self.transcribe_stop_event)
                finally:
                    sys.argv = sys_argv_orig
                writer.flush()
            except Exception as e:
                err_msg = f"Error: {e}"
                tb_str = traceback.format_exc()
                self._log(f"\n[Transcription Error] {err_msg}\n{tb_str}\n")
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                if on_complete:
                    self.after(0, on_complete)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _start_transcription(self):
        selected_mode_str = self.input_dropdown.get()
        input_flag = self.input_mode_map.get(selected_mode_str, "mic")

        py_cmd = get_python_cmd()
        cmd_args = ["--input", input_flag]

        # Devices
        mic_dev = self.mic_var.get().strip()
        default_in = self.t("audio_settings.system_default_input")
        if mic_dev and mic_dev != default_in and mic_dev != "(System Default Input)":
            cmd_args.extend(["--mic-device", mic_dev])

        speaker_dev = self.speaker_var.get().strip()
        default_out = self.t("audio_settings.system_default_output")
        if speaker_dev and speaker_dev != default_out and speaker_dev != "(System Default Output)":
            cmd_args.extend(["--speaker-device", speaker_dev])

        # WebSocket settings if input mode is ws
        if input_flag == "ws":
            ws_host = self.ws_host_var.get().strip()
            if ws_host:
                cmd_args.extend(["--ws-host", ws_host])
            ws_port = self.ws_port_var.get().strip()
            if ws_port:
                cmd_args.extend(["--ws-port", ws_port])

        # Pipeline Parameters
        en_tier = self.en_tier_var.get()
        if en_tier:
            cmd_args.extend(["--en-tier", en_tier])

        punct_model = self.punct_var.get()
        if punct_model:
            cmd_args.extend(["--punct-model", punct_model])

        threads = self.threads_var.get().strip()
        if threads:
            cmd_args.extend(["--threads", threads])

        min_silence = self.min_silence_var.get().strip()
        if min_silence:
            cmd_args.extend(["--min-silence", min_silence])

        max_speech = self.max_speech_var.get().strip()
        if max_speech:
            cmd_args.extend(["--max-speech", max_speech])

        max_resident = self.max_resident_var.get().strip()
        if max_resident:
            cmd_args.extend(["--max-resident", max_resident])

        # Processing Toggles
        if self.no_partial_var.get():
            cmd_args.append("--no-partial")
        if self.no_refine_var.get():
            cmd_args.append("--no-refine")
        if self.speakers_var.get():
            cmd_args.append("--speakers")

        # Dictionaries & Language Switching
        translate = self.translate_var.get().strip()
        if translate:
            cmd_args.extend(["--translate", translate])

        hotwords = self.hotwords_var.get().strip()
        if hotwords:
            cmd_args.extend(["--hotwords", hotwords])

        replace = self.replace_var.get().strip()
        if replace:
            cmd_args.extend(["--replace", replace])

        mode = self.mode_var.get()
        if mode:
            cmd_args.extend(["--mode", mode])

        lang_guard = self.lang_guard_var.get().strip()
        if lang_guard:
            cmd_args.extend(["--lang-switch-guard", lang_guard])

        lid_confirm = self.lid_confirm_var.get().strip()
        if lid_confirm:
            cmd_args.extend(["--lid-switch-confirm", lid_confirm])

        # Server
        if self.serve_var.get():
            cmd_args.append("--serve")

        self.start_stop_btn.config(text=self.t("audio_settings.stop_transcription"))
        self.status_var.set(self.t("audio_settings.status_running"))
        self.status_label.config(foreground="green")
        self.transcribe_stop_event = threading.Event()

        def complete():
            self.start_stop_btn.config(text=self.t("audio_settings.start_transcription"))
            self.status_var.set(self.t("audio_settings.status_stopped"))
            self.status_label.config(foreground="black")
            self.transcribe_process = None
            self.transcribe_stop_event = None
            self._log("\n>>> Transcription Process Terminated.\n")

        if py_cmd is None or getattr(sys, "frozen", False):
            self._log(f"\n>>> Launching Transcription (in-thread): {' '.join(cmd_args)}\n")
            self._run_transcribe_in_thread(cmd_args, on_complete=complete)
        else:
            full_cmd = [py_cmd, TRANSCRIBE_SCRIPT] + cmd_args
            self._log(f"\n>>> Launching Transcription: {' '.join(full_cmd)}\n")
            self._run_subprocess(full_cmd, on_complete=complete)

    def _stop_transcription(self):
        if self.transcribe_stop_event is not None:
            self._log("\n>>> Terminating Transcription Thread...\n")
            self.transcribe_stop_event.set()
        elif self.transcribe_process and self.transcribe_process.poll() is None:
            self._log("\n>>> Terminating Transcription Process...\n")
            self.transcribe_process.terminate()

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        elif event.delta:
            if sys.platform == "darwin":
                delta = -1 if event.delta > 0 else 1
            else:
                delta = int(-1 * (event.delta / 120))
                if delta == 0:
                    delta = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(delta, "units")

    def _on_close(self):
        if self.transcribe_stop_event is not None:
            self.transcribe_stop_event.set()
        elif self.transcribe_process and self.transcribe_process.poll() is None:
            self.transcribe_process.terminate()
        if self.download_process and self.download_process.poll() is None:
            self.download_process.terminate()
        self.destroy()


def main():
    app = HayamimiGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
