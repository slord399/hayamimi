"""hayamimi GUI Control Panel.

Provides a graphical control panel layout to download models, select audio input,
dynamically enumerate input (mic) and output (speaker) devices, toggle local server options,
launch/terminate the real-time transcription process, and display server URLs and live process logs.
"""

import os
import sys
import subprocess
import threading
import queue
import shutil
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    # PyInstaller extract directory
    ROOT_DIR = getattr(sys, '_MEIPASS', ROOT_DIR)

DOWNLOAD_SCRIPT = os.path.join(ROOT_DIR, "scripts", "download_models.py")
TRANSCRIBE_SCRIPT = os.path.join(ROOT_DIR, "scripts", "realtime_transcribe.py")


def get_python_cmd():
    """Get appropriate Python interpreter command when running from source or frozen executable."""
    if getattr(sys, 'frozen', False):
        py_path = shutil.which("python") or shutil.which("python3")
        if py_path:
            return py_path
    return sys.executable


def enumerate_audio_devices():
    """Dynamically enumerate available audio input (mic) and output (speaker) devices."""
    input_devices = ["(System Default Input)"]
    output_devices = ["(System Default Output)"]
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for dev in devices:
            name = dev.get("name", "").strip()
            if not name:
                continue
            if dev.get("max_input_channels", 0) > 0:
                if name not in input_devices:
                    input_devices.append(name)
            if dev.get("max_output_channels", 0) > 0:
                if name not in output_devices:
                    output_devices.append(name)
    except Exception:
        pass
    return input_devices, output_devices


class HayamimiGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("hayamimi (早耳) Control Panel")
        self.geometry("900x700")
        self.minsize(800, 550)

        self.transcribe_process = None
        self.download_process = None
        self.log_queue = queue.Queue()

        self._create_widgets()
        self._refresh_audio_devices()
        self._poll_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        # Top Container Frame
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(fill=tk.X, expand=False)

        # 1. Model Download Section
        dl_frame = ttk.LabelFrame(top_frame, text="Language Model Download", padding=10)
        dl_frame.pack(fill=tk.X, pady=(0, 10))

        self.minimal_var = tk.BooleanVar(value=True)
        self.minimal_check = ttk.Checkbutton(
            dl_frame,
            text="Minimal config (--minimal: ~1.1GB Japanese/English configuration)",
            variable=self.minimal_var,
        )
        self.minimal_check.pack(side=tk.LEFT, padx=(0, 15))

        self.dl_btn = ttk.Button(
            dl_frame,
            text="Download Models",
            command=self._start_download,
        )
        self.dl_btn.pack(side=tk.LEFT)

        # 2. Audio Input/Output Device & Execution Control Section
        audio_frame = ttk.LabelFrame(top_frame, text="Audio Input Source & Device Selector", padding=10)
        audio_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 0: Audio Mode Source
        ttk.Label(audio_frame, text="Input Source Mode:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.input_options = {
            "Microphone standard input": "mic",
            "PC internal speaker input (Windows)": "speaker",
            "Microphone + Speaker mix": "mix",
        }
        self.input_var = tk.StringVar(value="Microphone standard input")
        self.input_dropdown = ttk.Combobox(
            audio_frame,
            textvariable=self.input_var,
            values=list(self.input_options.keys()),
            state="readonly",
            width=32,
        )
        self.input_dropdown.grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=4)

        self.refresh_dev_btn = ttk.Button(
            audio_frame,
            text="Refresh Devices",
            command=self._refresh_audio_devices,
        )
        self.refresh_dev_btn.grid(row=0, column=2, sticky=tk.W, padx=(0, 15), pady=4)

        # Execution Control & Status
        self.start_stop_btn = ttk.Button(
            audio_frame,
            text="Start Transcription",
            command=self._toggle_transcription,
            width=20,
        )
        self.start_stop_btn.grid(row=0, column=3, sticky=tk.W, pady=4)

        self.status_var = tk.StringVar(value="Status: Stopped")
        self.status_label = ttk.Label(audio_frame, textvariable=self.status_var, font=("Helvetica", 10, "bold"))
        self.status_label.grid(row=0, column=4, sticky=tk.W, padx=(10, 0), pady=4)

        # Row 1: Microphone Input Device Selector
        ttk.Label(audio_frame, text="Microphone Device(s):").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.mic_var = tk.StringVar(value="(System Default Input)")
        self.mic_dropdown = ttk.Combobox(
            audio_frame,
            textvariable=self.mic_var,
            values=["(System Default Input)"],
            width=50,
        )
        self.mic_dropdown.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)
        ttk.Label(audio_frame, text="(Select or type device name/substring)").grid(row=1, column=3, columnspan=2, sticky=tk.W)

        # Row 2: Speaker Output Device Selector
        ttk.Label(audio_frame, text="Speaker Device:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=4)

        self.speaker_var = tk.StringVar(value="(System Default Output)")
        self.speaker_dropdown = ttk.Combobox(
            audio_frame,
            textvariable=self.speaker_var,
            values=["(System Default Output)"],
            state="readonly",
            width=50,
        )
        self.speaker_dropdown.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=4)

        # 3. Optional Local Server Settings
        server_frame = ttk.LabelFrame(top_frame, text="Optional Local Server Settings", padding=10)
        server_frame.pack(fill=tk.X, pady=(0, 10))

        # Left side: toggle
        toggle_subframe = ttk.Frame(server_frame)
        toggle_subframe.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 15))

        self.serve_var = tk.BooleanVar(value=True)
        self.serve_check = ttk.Checkbutton(
            toggle_subframe,
            text="Enable Local Server (--serve)",
            variable=self.serve_var,
        )
        self.serve_check.pack(anchor=tk.W, pady=(0, 5))

        # Right side: exact addresses & descriptions
        urls_subframe = ttk.Frame(server_frame)
        urls_subframe.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        addresses = [
            ("http://localhost:8833/dashboard", "Dashboard: Displays live speech text, finalized lines, translations, and polished transcript."),
            ("http://localhost:8833/", "OBS Overlay: Set as an OBS browser source URL to display subtitles on a streaming screen."),
            ("http://localhost:8833/transcript", "Transcript Page: Displays the polished transcript only."),
        ]

        for url, desc in addresses:
            row = ttk.Frame(urls_subframe)
            row.pack(fill=tk.X, pady=2)
            url_lbl = ttk.Label(row, text=url, font=("Courier", 9, "bold"), foreground="#0066cc", width=30)
            url_lbl.pack(side=tk.LEFT, anchor=tk.W)
            desc_lbl = ttk.Label(row, text=f"— {desc}", font=("Helvetica", 9))
            desc_lbl.pack(side=tk.LEFT, anchor=tk.W)

        # 4. Output Console / Log Area
        log_frame = ttk.LabelFrame(self, text="Console Output", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _refresh_audio_devices(self):
        input_devs, output_devs = enumerate_audio_devices()
        self.mic_dropdown["values"] = input_devs
        self.speaker_dropdown["values"] = output_devs
        if self.mic_var.get() not in input_devs:
            self.mic_var.set(input_devs[0])
        if self.speaker_var.get() not in output_devs:
            self.speaker_var.set(output_devs[0])

    def _log(self, message: str):
        self.log_queue.put(message)

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_text.insert(tk.END, msg)
            self.log_text.see(tk.END)
        self.after(100, self._poll_log_queue)

    def _run_subprocess(self, cmd: list[str], on_complete=None):
        def reader():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=ROOT_DIR,
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

    def _start_download(self):
        if self.download_process and self.download_process.poll() is None:
            messagebox.showinfo("In Progress", "Model download is already running.")
            return

        cmd = [get_python_cmd(), DOWNLOAD_SCRIPT]
        if self.minimal_var.get():
            cmd.append("--minimal")

        self.dl_btn.config(state=tk.DISABLED)
        self._log(f"\n>>> Starting Model Download: {' '.join(cmd)}\n")

        def complete():
            self.dl_btn.config(state=tk.NORMAL)
            self.download_process = None
            self._log("\n>>> Model Download Process Completed.\n")

        self._run_subprocess(cmd, on_complete=complete)

    def _toggle_transcription(self):
        if self.transcribe_process and self.transcribe_process.poll() is None:
            self._stop_transcription()
        else:
            self._start_transcription()

    def _start_transcription(self):
        input_key = self.input_var.get()
        input_flag = self.input_options.get(input_key, "mic")

        cmd = [get_python_cmd(), TRANSCRIBE_SCRIPT, "--input", input_flag]

        # Pass mic device if selected
        mic_dev = self.mic_var.get().strip()
        if mic_dev and mic_dev != "(System Default Input)":
            cmd.extend(["--mic-device", mic_dev])

        # Pass speaker device if selected
        speaker_dev = self.speaker_var.get().strip()
        if speaker_dev and speaker_dev != "(System Default Output)":
            cmd.extend(["--speaker-device", speaker_dev])

        if self.serve_var.get():
            cmd.append("--serve")

        self.start_stop_btn.config(text="Stop Transcription")
        self.status_var.set("Status: Running")
        self.status_label.config(foreground="green")
        self._log(f"\n>>> Launching Transcription: {' '.join(cmd)}\n")

        def complete():
            self.start_stop_btn.config(text="Start Transcription")
            self.status_var.set("Status: Stopped")
            self.status_label.config(foreground="black")
            self.transcribe_process = None
            self._log("\n>>> Transcription Process Terminated.\n")

        self._run_subprocess(cmd, on_complete=complete)

    def _stop_transcription(self):
        if self.transcribe_process and self.transcribe_process.poll() is None:
            self._log("\n>>> Terminating Transcription Process...\n")
            self.transcribe_process.terminate()

    def _on_close(self):
        if self.transcribe_process and self.transcribe_process.poll() is None:
            self.transcribe_process.terminate()
        if self.download_process and self.download_process.poll() is None:
            self.download_process.terminate()
        self.destroy()


def main():
    app = HayamimiGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
