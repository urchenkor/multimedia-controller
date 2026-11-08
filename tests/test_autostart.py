"""Validate the Windows task definition and installation without scheduling locally."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import install_autostart as installer


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.script = Path('/Users/Test & User/Media Controller/controller_v2.py')
        self.pythonw = Path('/Python Install/pythonw.exe')
        self.user = 'PC\\Test & User'
        self.root = ET.fromstring(installer.build_task_xml(self.pythonw, self.script, self.user))
        self.ns = {'t': installer.TASK_NS}

    def value(self, path):
        return self.root.find(path, self.ns).text

    def test_logon_runs_for_installing_user_after_delay(self):
        self.assertEqual(self.value('t:Triggers/t:LogonTrigger/t:UserId'), self.user)
        self.assertEqual(self.value('t:Triggers/t:LogonTrigger/t:Delay'), 'PT10S')
        self.assertEqual(self.value('t:Principals/t:Principal/t:UserId'), self.user)
        self.assertEqual(self.value('t:Principals/t:Principal/t:LogonType'), 'InteractiveToken')

    def test_wake_trigger_preserves_power_event(self):
        query = ET.fromstring(self.value('t:Triggers/t:EventTrigger/t:Subscription'))
        select = query.find('Query/Select')
        self.assertEqual(select.attrib['Path'], 'System')
        self.assertIn('Microsoft-Windows-Power-Troubleshooter', select.text)
        self.assertIn('EventID=1', select.text)
        self.assertEqual(self.value('t:Triggers/t:EventTrigger/t:Delay'), 'PT10S')
        self.assertEqual(len(self.root.find('t:Triggers', self.ns)), 2)

    def test_restart_prevents_duplicate_scheduled_instances(self):
        self.assertEqual(self.value('t:Settings/t:MultipleInstancesPolicy'), 'StopExisting')

    def test_background_controller_has_no_time_or_battery_limit(self):
        self.assertEqual(self.value('t:Settings/t:ExecutionTimeLimit'), 'PT0S')
        self.assertEqual(self.value('t:Settings/t:DisallowStartIfOnBatteries'), 'false')
        self.assertEqual(self.value('t:Settings/t:StopIfGoingOnBatteries'), 'false')

    def test_action_preserves_paths_with_spaces_and_xml_characters(self):
        self.assertEqual(self.value('t:Actions/t:Exec/t:Command'), str(self.pythonw))
        self.assertEqual(self.value('t:Actions/t:Exec/t:Arguments'), f'"{self.script}"')
        self.assertEqual(self.value('t:Actions/t:Exec/t:WorkingDirectory'), str(self.script.parent))

    def test_install_updates_existing_task_with_valid_xml(self):
        captured = []

        def run(args, **kwargs):
            self.assertTrue(kwargs['check'])
            if args == ['whoami']:
                return Mock(stdout=self.user + '\n')
            self.assertEqual(args[:4], ['schtasks', '/Create', '/TN', 'MediaControllerWake'])
            self.assertEqual(args[-1], '/F')
            xml_path = Path(args[args.index('/XML') + 1])
            self.assertTrue(xml_path.is_file())
            ET.fromstring(xml_path.read_bytes())
            captured.append(xml_path)
            return Mock(returncode=0)

        with patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.Path, 'is_file', return_value=True), \
             patch.object(installer.subprocess, 'run', side_effect=run) as runner, \
             patch('builtins.print'):
            installer.main()
        self.assertEqual(runner.call_count, 2)
        self.assertFalse(captured[0].exists())

    def test_failed_registration_is_not_reported_as_success(self):
        with patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.Path, 'is_file', return_value=True), \
             patch.object(installer.subprocess, 'run', side_effect=[
                 Mock(stdout=self.user), subprocess.CalledProcessError(1, 'schtasks')]), \
             patch('builtins.print') as output:
            with self.assertRaises(subprocess.CalledProcessError):
                installer.main()
            output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
