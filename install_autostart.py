"""Install the interactive Windows task used at sign-in and after sleep."""
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

TASK_NAME = "MediaControllerWake"  # Replace the existing wake-only task in place.
TASK_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", TASK_NS)


def build_task_xml(pythonw, script, user):
    def add(parent, name, value=None, **attributes):
        node = ET.SubElement(parent, f"{{{TASK_NS}}}{name}", attributes)
        node.text = value
        return node

    task = ET.Element(f"{{{TASK_NS}}}Task", {"version": "1.2"})
    registration = add(task, "RegistrationInfo")
    add(registration, "Description", "Start the media controller at sign-in and restart it after sleep.")
    triggers = add(task, "Triggers")
    logon = add(triggers, "LogonTrigger")
    add(logon, "Enabled", "true")
    add(logon, "UserId", user)
    add(logon, "Delay", "PT10S")
    wake = add(triggers, "EventTrigger")
    add(wake, "Enabled", "true")
    add(wake, "Subscription", '<QueryList><Query Id="0" Path="System"><Select Path="System">'
        '*[System[Provider[@Name="Microsoft-Windows-Power-Troubleshooter"] and (EventID=1)]]'
        '</Select></Query></QueryList>')
    add(wake, "Delay", "PT10S")
    principals = add(task, "Principals")
    principal = add(principals, "Principal", id="ControllerUser")
    add(principal, "UserId", user)
    add(principal, "LogonType", "InteractiveToken")
    add(principal, "RunLevel", "HighestAvailable")
    settings = add(task, "Settings")
    # A wake event replaces the old process instead of competing for its COM port.
    add(settings, "MultipleInstancesPolicy", "StopExisting")
    add(settings, "DisallowStartIfOnBatteries", "false")
    add(settings, "StopIfGoingOnBatteries", "false")
    add(settings, "StartWhenAvailable", "true")
    add(settings, "ExecutionTimeLimit", "PT0S")
    actions = add(task, "Actions", Context="ControllerUser")
    action = add(actions, "Exec")
    add(action, "Command", str(pythonw))
    add(action, "Arguments", f'"{script}"')
    add(action, "WorkingDirectory", str(script.parent))
    return ET.tostring(task, encoding="utf-8", xml_declaration=True)


def main():
    if sys.platform != "win32":
        raise SystemExit("Run this installer on Windows.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().with_name("controller_v2.py")
    for path in (pythonw, script):
        if not path.is_file():
            raise SystemExit(f"Required file not found: {path}")
    user = subprocess.run(["whoami"], check=True, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="media-controller-") as temporary:
        xml_path = Path(temporary) / "task.xml"
        xml_path.write_bytes(build_task_xml(pythonw, script, user))
        # /F updates the existing task without deleting it first.
        subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME,
                        "/XML", str(xml_path), "/F"], check=True)
    print("Controller will start 10 seconds after sign-in and restart after wake.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Task installation failed: {error}", file=sys.stderr)
        sys.exit(1)
