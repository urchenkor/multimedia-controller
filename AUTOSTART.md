# Automatic startup on Windows

Run `setup.bat` as Administrator from the folder where you will keep the project.
Use your normal Windows account (the account that should run the controller).
The installer installs dependencies and creates or updates `MediaControllerWake`
with both triggers:

- **Sign-in:** start the bridge 10 seconds after this user signs into Windows,
  including after shutdown or reboot.
- **Wake:** restart the bridge 10 seconds after Windows reports waking from sleep.

The bridge runs silently through `pythonw.exe` in your interactive session so it
can access your audio devices and send media keys. It does not run before sign-in.
Both triggers belong to the same task; a new trigger stops the previous scheduled
instance before launching its replacement. Battery power does not prevent startup,
and the task has no execution time limit.

If dependencies are already installed, you can install just the task with the
same Python interpreter you use for the bridge, from an elevated command prompt:

```cmd
python install_autostart.py
```

Keep `install_autostart.py`, `setup.bat`, and `controller_v2.py` together. If you
move the project or Python installation, run the installer again to update the
saved absolute paths. The task keeps its existing name for compatibility and is
updated without first deleting the previous registration.

## Check it on your PC

1. Close any manually launched copies of the bridge before testing. Task
   Scheduler can manage its own instances but cannot stop unrelated manual copies.
2. Open Task Scheduler and find `MediaControllerWake`. Confirm that both the
   sign-in and event triggers appear. You can select **Run** to test immediately.
3. Reboot and sign in. With the controller connected, wait about 10 seconds plus
   the board's two-second initialization time, then check the display and buttons.
4. Sleep and wake the PC; verify the controller works again and only one scheduled
   instance is running.

The bridge retries detection every two seconds if the controller is connected
later, and reconnects after serial errors. For boards with an unrecognized USB
description, a manual launch can specify `python controller_v2.py --port COM3`.

To remove automatic startup and wake recovery:

```cmd
schtasks /Delete /TN "MediaControllerWake" /F
```

## Validation

Run `python -m unittest discover -s tests -v` for all automated checks. The startup
tests validate both triggers, interactive user selection, command/path escaping,
replacement behavior, battery/runtime settings, registration, and failure handling.
Actual Windows task registration and reboot/wake behavior require a Windows PC.
