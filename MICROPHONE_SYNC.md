# Microphone synchronization (issue #1)

The active v2 system consists of `controller_v2.cpp` (Arduino Nano firmware),
`controller_v2.py` (Windows bridge), and `setup.bat` (dependencies and wake task).
The original `controller.cpp` / `controller.py` pair predates the OLED protocol.
The board sends newline-delimited button/encoder commands at 9600 baud; Python
uses pycaw for Windows audio and keyboard for media keys. Python also sends
volume, speaker mute and heartbeat messages to the board.

Previously the board initialized its microphone indicator to ON and toggled it
locally. The bridge only toggled the Windows microphone; it never reported the
actual microphone state. A board reset after sleep could therefore show ON while
Windows remained muted.

The bridge now reads the default Windows microphone at startup, after a microphone
button action, and periodically (0.5-second polling interval). It reacquires the
endpoint each time so it does not retain a stale microphone interface across
sleep or default-device changes. Reads and toggles run on the main thread.
Failed microphone operations are logged and periodic synchronization retries.
Unchanged state is resent too, allowing a reset board to recover without a change
in Windows mute state. All serial writers share a lock to keep messages intact.

New host-to-board messages:

| Message | Windows state | OLED / D13 LED |
| --- | --- | --- |
| `DISP:MIC:ON` | Unmuted | ON / HIGH |
| `DISP:MIC:OFF` | Muted | OFF / LOW |

The board updates its indicator only from these messages; a button press sends
`MIC_MUTE` and waits for confirmation. A microphone update received while the
sleep screen is active is saved and displayed when the next PING wakes it.
This reflects the default Windows capture endpoint's mute state, not an
application's independent mute control.

## Install and verify

1. Stop the running Python bridge.
2. Copy `controller_v2.cpp` into an Arduino sketch named
   `controller_v2/controller_v2.ino`, retaining the existing SSD1306/GFX libraries,
   and upload it to the Nano. Both firmware and Python must be updated together.
3. Run the updated `controller_v2.py` on Windows. The existing `setup.bat` wake
   task can continue to launch this script from its installed location.
4. Mute the microphone, sleep Windows, then wake it. Check that MIC returns to
   OFF and D13 is LOW without manually restarting the bridge or board.
5. Repeat with the microphone unmuted. Change endpoint mute outside the bridge
   and verify that both indicators follow it. Reset the board while muted and
   verify it returns to OFF after serial communication resumes.
6. Press the microphone button and verify Windows, OLED and LED agree. Repeat
   while turning the volume encoder.

Synchronization requires a functioning serial connection. This change does not
add USB port reconnection if Windows removes the port; the existing wake task
and serial connection behavior are unchanged.

## Automated checks

Run from the repository root:

```sh
python -m unittest discover -s tests -v
```

Tests exercise the actual Python bridge with mocked Windows and serial APIs,
including startup/idle polling, encoder input, unchanged-state resend, external
changes, endpoint replacement, read/write failures, and toggle result readback.
They run without third-party dependencies. They do not replace compiling the
Arduino sketch or checking real Windows sleep/wake and physical indicators.
