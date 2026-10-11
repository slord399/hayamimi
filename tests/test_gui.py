"""Unit tests for hayamimi GUI control panel components, device enumeration, and command generation logic."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import gui


class TestHayamimiGUIUnit(unittest.TestCase):
    def test_gui_script_paths(self):
        self.assertTrue(os.path.exists(gui.DOWNLOAD_SCRIPT))
        self.assertTrue(os.path.exists(gui.TRANSCRIBE_SCRIPT))

    def test_input_options_mapping(self):
        expected_mappings = {
            "Microphone standard input": "mic",
            "PC internal speaker input (Windows)": "speaker",
            "Microphone + Speaker mix": "mix",
        }
        for label, code in expected_mappings.items():
            self.assertIn(label, expected_mappings)

    @patch("gui.enumerate_audio_devices")
    def test_enumerate_audio_devices_mock(self, mock_enum):
        mock_enum.return_value = (["(System Default Input)", "Mic 1"], ["(System Default Output)", "Speaker 1"])
        inputs, outputs = gui.enumerate_audio_devices()
        self.assertEqual(inputs, ["(System Default Input)", "Mic 1"])
        self.assertEqual(outputs, ["(System Default Output)", "Speaker 1"])

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    def test_transcribe_command_construction_with_devices(
        self, mock_refresh, mock_poll, mock_widgets
    ):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.input_options = {
            "Microphone standard input": "mic",
            "PC internal speaker input (Windows)": "speaker",
            "Microphone + Speaker mix": "mix",
        }
        app.input_var = MagicMock()
        app.mic_var = MagicMock()
        app.speaker_var = MagicMock()
        app.serve_var = MagicMock()
        app.start_stop_btn = MagicMock()
        app.status_var = MagicMock()
        app.status_label = MagicMock()
        app.transcribe_process = None
        app._log = MagicMock()
        app._run_subprocess = MagicMock()

        # Test 1: mic with custom mic device and serve
        app.input_var.get.return_value = "Microphone standard input"
        app.mic_var.get.return_value = "USB Microphone"
        app.speaker_var.get.return_value = "(System Default Output)"
        app.serve_var.get.return_value = True
        gui.HayamimiGUI._start_transcription(app)

        expected_cmd_1 = [
            sys.executable,
            gui.TRANSCRIBE_SCRIPT,
            "--input",
            "mic",
            "--mic-device",
            "USB Microphone",
            "--serve",
        ]
        app._run_subprocess.assert_called_once()
        actual_cmd_1 = app._run_subprocess.call_args[0][0]
        self.assertEqual(actual_cmd_1, expected_cmd_1)

        # Test 2: mix with custom mic and speaker devices, no serve
        app._run_subprocess.reset_mock()
        app.input_var.get.return_value = "Microphone + Speaker mix"
        app.mic_var.get.return_value = "Array Mic"
        app.speaker_var.get.return_value = "Realtek Speaker"
        app.serve_var.get.return_value = False
        gui.HayamimiGUI._start_transcription(app)

        expected_cmd_2 = [
            sys.executable,
            gui.TRANSCRIBE_SCRIPT,
            "--input",
            "mix",
            "--mic-device",
            "Array Mic",
            "--speaker-device",
            "Realtek Speaker",
        ]
        app._run_subprocess.assert_called_once()
        actual_cmd_2 = app._run_subprocess.call_args[0][0]
        self.assertEqual(actual_cmd_2, expected_cmd_2)

    @patch("gui.HayamimiGUI._create_widgets")
    @patch("gui.HayamimiGUI._poll_log_queue")
    @patch("gui.HayamimiGUI._refresh_audio_devices")
    def test_download_command_construction(self, mock_refresh, mock_poll, mock_widgets):
        app = gui.HayamimiGUI.__new__(gui.HayamimiGUI)
        app.minimal_var = MagicMock()
        app.dl_btn = MagicMock()
        app.download_process = None
        app._log = MagicMock()
        app._run_subprocess = MagicMock()

        # Minimal true
        app.minimal_var.get.return_value = True
        gui.HayamimiGUI._start_download(app)
        expected_cmd_1 = [sys.executable, gui.DOWNLOAD_SCRIPT, "--minimal"]
        actual_cmd_1 = app._run_subprocess.call_args[0][0]
        self.assertEqual(actual_cmd_1, expected_cmd_1)

        # Minimal false
        app._run_subprocess.reset_mock()
        app.minimal_var.get.return_value = False
        gui.HayamimiGUI._start_download(app)
        expected_cmd_2 = [sys.executable, gui.DOWNLOAD_SCRIPT]
        actual_cmd_2 = app._run_subprocess.call_args[0][0]
        self.assertEqual(actual_cmd_2, expected_cmd_2)


if __name__ == "__main__":
    unittest.main()
