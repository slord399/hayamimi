"""Unit tests for hayamimi GUI control panel components, i18n localization, and CLI flag generation logic."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import gui


class TestHayamimiGUIUnit(unittest.TestCase):
    def test_gui_script_paths(self):
        self.assertTrue(os.path.exists(gui.DOWNLOAD_SCRIPT))
        self.assertTrue(os.path.exists(gui.TRANSCRIBE_SCRIPT))

    def test_load_locale(self):
        ja_locale = gui.load_locale("ja")
        self.assertIn("app_title", ja_locale)
        self.assertEqual(ja_locale["app_title"], "hayamimi (早耳) コントロールパネル")

        en_locale = gui.load_locale("en")
        self.assertIn("app_title", en_locale)
        self.assertEqual(en_locale["app_title"], "hayamimi (早耳) Control Panel")

        zh_locale = gui.load_locale("zh")
        self.assertIn("app_title", zh_locale)

        ko_locale = gui.load_locale("ko")
        self.assertIn("app_title", ko_locale)

        yue_locale = gui.load_locale("yue")
        self.assertIn("app_title", yue_locale)

    def test_get_python_cmd_unfrozen(self):
        with patch.object(sys, "frozen", False, create=True):
            cmd = gui.get_python_cmd()
            self.assertEqual(cmd, sys.executable)

    def test_get_python_cmd_frozen(self):
        with patch.object(sys, "frozen", True, create=True):
            cmd = gui.get_python_cmd()
            self.assertIsNone(cmd)

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    @patch("gui.HayamimiGUI._update_ui_strings")
    def test_start_download_status_update(
        self, mock_update_ui, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.download_process = None
        app.minimal_var = MagicMock()
        app.minimal_var.get.return_value = True
        app.dl_btn = MagicMock()
        app.start_stop_btn = MagicMock()
        app.dl_total_status_var = MagicMock()
        app.dl_file_status_var = MagicMock()
        app._run_download_subprocess = MagicMock()
        app.t = MagicMock(return_value="Starting Model Download")

        with patch("gui.get_python_cmd", return_value="/usr/bin/python3"):
            gui.HayamimiGUI._start_download(app)

        app.dl_btn.config.assert_called_with(state=gui.tk.DISABLED)
        app.start_stop_btn.config.assert_called_with(state=gui.tk.DISABLED)
        app.dl_total_status_var.set.assert_called_with("Total Progress: Starting Model Download")
        app._run_download_subprocess.assert_called_once()

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    @patch("gui.HayamimiGUI._update_ui_strings")
    def test_start_download_in_thread_when_frozen(
        self, mock_update_ui, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.download_process = None
        app.minimal_var = MagicMock()
        app.minimal_var.get.return_value = True
        app.dl_btn = MagicMock()
        app.start_stop_btn = MagicMock()
        app.dl_total_status_var = MagicMock()
        app.dl_file_status_var = MagicMock()
        app._run_download_in_thread = MagicMock()
        app.t = MagicMock(return_value="Starting Model Download")

        with patch("gui.get_python_cmd", return_value=None):
            gui.HayamimiGUI._start_download(app)

        app.dl_btn.config.assert_called_with(state=gui.tk.DISABLED)
        app.start_stop_btn.config.assert_called_with(state=gui.tk.DISABLED)
        app.dl_total_status_var.set.assert_called_with("Total Progress: Starting Model Download")
        app._run_download_in_thread.assert_called_once()

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    @patch("gui.HayamimiGUI._update_ui_strings")
    def test_mousewheel_scrolling(
        self, mock_update_ui, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.canvas = MagicMock()

        event_num4 = MagicMock(num=4, delta=0)
        gui.HayamimiGUI._on_mousewheel(app, event_num4)
        app.canvas.yview_scroll.assert_called_with(-1, "units")

        event_num5 = MagicMock(num=5, delta=0)
        gui.HayamimiGUI._on_mousewheel(app, event_num5)
        app.canvas.yview_scroll.assert_called_with(1, "units")

        event_delta = MagicMock(num=0, delta=-120)
        gui.HayamimiGUI._on_mousewheel(app, event_delta)
        app.canvas.yview_scroll.assert_called_with(1, "units")

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    @patch("gui.HayamimiGUI._update_ui_strings")
    def test_full_cli_command_construction(
        self, mock_update_ui, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.input_mode_map = {
            "WebSocket audio network input": "ws",
            "Microphone standard input": "mic",
        }
        app.input_dropdown = MagicMock()
        app.input_dropdown.get.return_value = "WebSocket audio network input"

        app.mic_var = MagicMock()
        app.mic_var.get.return_value = "(System Default Input)"
        app.speaker_var = MagicMock()
        app.speaker_var.get.return_value = "(System Default Output)"

        app.ws_host_var = MagicMock()
        app.ws_host_var.get.return_value = "0.0.0.0"
        app.ws_port_var = MagicMock()
        app.ws_port_var.get.return_value = "8766"

        app.en_tier_var = MagicMock()
        app.en_tier_var.get.return_value = "v2"
        app.punct_var = MagicMock()
        app.punct_var.get.return_value = "4class"
        app.threads_var = MagicMock()
        app.threads_var.get.return_value = "8"
        app.min_silence_var = MagicMock()
        app.min_silence_var.get.return_value = "0.4"
        app.max_speech_var = MagicMock()
        app.max_speech_var.get.return_value = "10.0"
        app.max_resident_var = MagicMock()
        app.max_resident_var.get.return_value = "2"

        app.no_partial_var = MagicMock()
        app.no_partial_var.get.return_value = True
        app.no_refine_var = MagicMock()
        app.no_refine_var.get.return_value = True
        app.speakers_var = MagicMock()
        app.speakers_var.get.return_value = True

        app.translate_var = MagicMock()
        app.translate_var.get.return_value = "en,zh"
        app.hotwords_var = MagicMock()
        app.hotwords_var.get.return_value = "/path/to/hotwords.txt"
        app.replace_var = MagicMock()
        app.replace_var.get.return_value = "/path/to/replace.txt"
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = "single"
        app.lang_guard_var = MagicMock()
        app.lang_guard_var.get.return_value = "1.5"
        app.lid_confirm_var = MagicMock()
        app.lid_confirm_var.get.return_value = "3"

        app.serve_var = MagicMock()
        app.serve_var.get.return_value = True

        app.start_stop_btn = MagicMock()
        app.status_var = MagicMock()
        app.status_label = MagicMock()
        app.transcribe_process = None
        app._log = MagicMock()
        app._run_subprocess = MagicMock()
        app.t = MagicMock(return_value="text")

        expected_cmd = [
            "/usr/bin/python3",
            gui.TRANSCRIBE_SCRIPT,
            "--input",
            "ws",
            "--ws-host",
            "0.0.0.0",
            "--ws-port",
            "8766",
            "--en-tier",
            "v2",
            "--punct-model",
            "4class",
            "--threads",
            "8",
            "--min-silence",
            "0.4",
            "--max-speech",
            "10.0",
            "--max-resident",
            "2",
            "--no-partial",
            "--no-refine",
            "--speakers",
            "--translate",
            "en,zh",
            "--hotwords",
            "/path/to/hotwords.txt",
            "--replace",
            "/path/to/replace.txt",
            "--mode",
            "single",
            "--lang-switch-guard",
            "1.5",
            "--lid-switch-confirm",
            "3",
            "--serve",
        ]

        with patch("gui.get_python_cmd", return_value="/usr/bin/python3"):
            gui.HayamimiGUI._start_transcription(app)

        app._run_subprocess.assert_called_once()
        actual_cmd = app._run_subprocess.call_args[0][0]
        self.assertEqual(actual_cmd, expected_cmd)

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    @patch("gui.HayamimiGUI._update_ui_strings")
    def test_transcription_in_thread_when_frozen(
        self, mock_update_ui, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.input_mode_map = {"Microphone standard input": "mic"}
        app.input_dropdown = MagicMock()
        app.input_dropdown.get.return_value = "Microphone standard input"

        app.mic_var = MagicMock()
        app.mic_var.get.return_value = "(System Default Input)"
        app.speaker_var = MagicMock()
        app.speaker_var.get.return_value = "(System Default Output)"

        app.en_tier_var = MagicMock()
        app.en_tier_var.get.return_value = "v3"
        app.punct_var = MagicMock()
        app.punct_var.get.return_value = "bert"
        app.threads_var = MagicMock()
        app.threads_var.get.return_value = "4"
        app.min_silence_var = MagicMock()
        app.min_silence_var.get.return_value = "0.35"
        app.max_speech_var = MagicMock()
        app.max_speech_var.get.return_value = "12.0"
        app.max_resident_var = MagicMock()
        app.max_resident_var.get.return_value = "3"

        app.no_partial_var = MagicMock()
        app.no_partial_var.get.return_value = False
        app.no_refine_var = MagicMock()
        app.no_refine_var.get.return_value = False
        app.speakers_var = MagicMock()
        app.speakers_var.get.return_value = False

        app.translate_var = MagicMock()
        app.translate_var.get.return_value = ""
        app.hotwords_var = MagicMock()
        app.hotwords_var.get.return_value = ""
        app.replace_var = MagicMock()
        app.replace_var.get.return_value = ""
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = "balanced"
        app.lang_guard_var = MagicMock()
        app.lang_guard_var.get.return_value = "2.0"
        app.lid_confirm_var = MagicMock()
        app.lid_confirm_var.get.return_value = "2"

        app.serve_var = MagicMock()
        app.serve_var.get.return_value = True

        app.start_stop_btn = MagicMock()
        app.status_var = MagicMock()
        app.status_label = MagicMock()
        app.transcribe_process = None
        app._log = MagicMock()
        app._run_transcribe_in_thread = MagicMock()
        app.t = MagicMock(return_value="text")

        with patch("gui.get_python_cmd", return_value=None):
            gui.HayamimiGUI._start_transcription(app)

        app._run_transcribe_in_thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
