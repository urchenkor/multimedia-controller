import unittest
from unittest.mock import Mock, call, patch

from test_microphone_sync import controller


class RecoveryTests(unittest.TestCase):
    def test_missing_board_is_retried_and_connected_board_is_closed(self):
        board = Mock()
        with patch.object(controller, 'ser', None), \
             patch.object(controller, 'find_arduino', side_effect=[None, 'COM4']), \
             patch.object(controller.serial, 'Serial', return_value=board), \
             patch.object(controller, 'run_connected', side_effect=KeyboardInterrupt) as run, \
             patch.object(controller.time, 'sleep'), patch('builtins.print'):
            controller.main()
        run.assert_called_once()
        board.close.assert_called_once()

    def test_disconnect_reopens_port(self):
        first, second = Mock(), Mock()
        with patch.object(controller, 'ser', None), \
             patch.object(controller.serial, 'Serial', side_effect=[first, second]) as connect, \
             patch.object(controller, 'run_connected', side_effect=[
                 controller.serial.SerialException('unplugged'), KeyboardInterrupt]), \
             patch.object(controller.time, 'sleep'), patch('builtins.print'):
            controller.main(port='COM7')
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(connect.call_args.kwargs['write_timeout'], 1)

    def test_failed_open_retries(self):
        board = Mock()
        with patch.object(controller, 'ser', None), \
             patch.object(controller.serial, 'Serial', side_effect=[
                 controller.serial.SerialException('busy'), board]) as connect, \
             patch.object(controller, 'run_connected', side_effect=KeyboardInterrupt), \
             patch.object(controller.time, 'sleep'), patch('builtins.print'):
            controller.main(port='COM7')
        self.assertEqual(connect.call_count, 2)
        board.close.assert_called_once()

    def test_unrelated_serial_port_is_not_opened(self):
        with patch.object(controller.serial.tools.list_ports, 'comports',
                          return_value=[Mock(description='Bluetooth', device='COM2')]):
            self.assertIsNone(controller.find_arduino())

    def test_speaker_state_is_resent_and_endpoint_reacquired(self):
        first, second = Mock(), Mock()
        first.GetMasterVolumeLevelScalar.return_value = 0.2
        second.GetMasterVolumeLevelScalar.return_value = 0.8
        first.GetMute.return_value = False
        second.GetMute.return_value = True
        board = Mock(is_open=True)
        with patch.object(controller, 'ser', board), \
             patch.object(controller, 'get_speaker_interface', side_effect=[first, second]):
            controller.sync_speaker_from_system()
            controller.sync_speaker_from_system()
        self.assertEqual(board.write.call_args_list, [call(b'DISP:VOL:20\n'),
                         call(b'DISP:MUTE:OFF\n'), call(b'DISP:VOL:80\n'),
                         call(b'DISP:MUTE:ON\n')])

    def test_audio_failure_does_not_stop_media_commands(self):
        with patch.object(controller, 'get_speaker_interface', side_effect=RuntimeError('resuming')), \
             patch.object(controller.keyboard, 'send') as send, patch('builtins.print'):
            controller.sync_speaker_from_system()
            controller.handle_command('VOL_UP')
            controller.handle_command('TRACK_NEXT')
        send.assert_called_once_with('next track')

    def test_serial_write_error_reaches_reconnect_loop(self):
        speaker = Mock()
        speaker.GetMasterVolumeLevelScalar.return_value = 0.5
        board = Mock(is_open=True)
        board.write.side_effect = controller.serial.SerialException('unplugged')
        with patch.object(controller, 'ser', board), \
             patch.object(controller, 'get_speaker_interface', return_value=speaker):
            with self.assertRaises(controller.serial.SerialException):
                controller.sync_speaker_from_system()

    def test_fast_turn_reads_actual_new_device_volume(self):
        speaker = Mock()
        speaker.GetMasterVolumeLevelScalar.return_value = 0.1
        with patch.object(controller, 'current_volume', 90), \
             patch.object(controller, 'last_click_time', 10.0), \
             patch.object(controller.time, 'monotonic', return_value=10.01), \
             patch.object(controller, 'send_to_display'), patch('builtins.print'):
            controller.change_volume_adaptive(speaker, 1)
        speaker.SetMasterVolumeLevelScalar.assert_called_once_with(0.2, None)


if __name__ == '__main__':
    unittest.main()
