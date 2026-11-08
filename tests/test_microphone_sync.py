"""Run with python -m unittest discover -s tests -v (no hardware required)."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call, patch


# Replace Windows-only and hardware dependencies before importing the real bridge.
dependencies = {name: Mock() for name in (
    "serial", "serial.tools", "serial.tools.list_ports", "pycaw", "pycaw.pycaw",
    "comtypes", "keyboard",
)}
dependencies["serial"].SerialException = type("SerialException", (OSError,), {})
spec = importlib.util.spec_from_file_location(
    "controller_v2", Path(__file__).resolve().parents[1] / "controller_v2.py"
)
controller = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, dependencies):
    spec.loader.exec_module(controller)


class MicrophoneSyncTests(unittest.TestCase):
    def setUp(self):
        self.serial = Mock(is_open=True)
        self.mic = Mock()
        self.mic.GetMute.return_value = True
        self.patches = [
            patch.object(controller, "ser", self.serial),
            patch.object(controller, "get_mic_interface", return_value=self.mic),
            patch("builtins.print"),
        ]
        for replacement in self.patches:
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_muted_startup_sends_off(self):
        controller.sync_mic_from_system()
        self.serial.write.assert_called_once_with(b"DISP:MIC:OFF\n")
        self.mic.SetMute.assert_not_called()

    def test_external_unmute_sends_on(self):
        controller.sync_mic_from_system()
        self.mic.GetMute.return_value = False
        controller.sync_mic_from_system()
        self.assertEqual(self.serial.write.call_args_list,
                         [call(b"DISP:MIC:OFF\n"), call(b"DISP:MIC:ON\n")])

    def test_unchanged_mute_is_resent_after_board_reset(self):
        controller.sync_mic_from_system()
        controller.sync_mic_from_system()
        self.assertEqual(self.serial.write.call_args_list,
                         [call(b"DISP:MIC:OFF\n")] * 2)

    def test_default_microphone_is_reacquired(self):
        new_mic = Mock()
        new_mic.GetMute.return_value = False
        controller.get_mic_interface.side_effect = [self.mic, new_mic]
        controller.sync_mic_from_system()
        controller.sync_mic_from_system()
        self.serial.write.assert_called_with(b"DISP:MIC:ON\n")

    def test_missing_endpoint_recovers_on_next_poll(self):
        controller.get_mic_interface.side_effect = [OSError("resuming"), self.mic]
        controller.sync_mic_from_system()
        self.serial.write.assert_not_called()
        controller.sync_mic_from_system()
        self.serial.write.assert_called_once_with(b"DISP:MIC:OFF\n")

    def test_failed_read_does_not_send_guessed_state(self):
        self.mic.GetMute.side_effect = OSError("device invalidated")
        controller.sync_mic_from_system()
        self.serial.write.assert_not_called()

    def test_serial_failure_retries_unchanged_state(self):
        self.serial.write.side_effect = [controller.serial.SerialException("USB unavailable"), None]
        with self.assertRaises(controller.serial.SerialException):
            controller.sync_mic_from_system()
        controller.sync_mic_from_system()
        self.assertEqual(self.serial.write.call_args_list,
                         [call(b"DISP:MIC:OFF\n")] * 2)

    def test_toggle_reads_back_actual_result(self):
        # A device can retain its old state even when a mute change is requested.
        controller.toggle_mic_mute()
        self.mic.SetMute.assert_called_once_with(False, None)
        self.serial.write.assert_called_once_with(b"DISP:MIC:OFF\n")

    def test_successful_toggle_reports_new_state(self):
        self.mic.GetMute.side_effect = [True, False]
        controller.toggle_mic_mute()
        self.serial.write.assert_called_once_with(b"DISP:MIC:ON\n")

    def test_failed_toggle_does_not_claim_success(self):
        self.mic.SetMute.side_effect = OSError("endpoint lost")
        controller.toggle_mic_mute()
        self.serial.write.assert_not_called()

    def test_loop_syncs_at_startup_and_during_idle_and_encoder_input(self):
        self.serial.readline.side_effect = [b"", b"VOL_UP\n", KeyboardInterrupt]
        speaker = Mock()
        speaker.GetMasterVolumeLevelScalar.return_value = 0.5
        with patch.object(controller, "get_speaker_interface", return_value=speaker), \
             patch.object(controller.time, "monotonic", side_effect=[0, 1, 2]), \
             patch.object(controller, "change_volume_adaptive") as change_volume:
            with self.assertRaises(KeyboardInterrupt):
                controller.run_connected()
        mic_messages = [c for c in self.serial.write.call_args_list
                        if c.args[0].startswith(b"DISP:MIC:")]
        self.assertEqual(mic_messages, [call(b"DISP:MIC:OFF\n")] * 3)
        change_volume.assert_called_once_with(speaker, 1)


if __name__ == "__main__":
    unittest.main()
