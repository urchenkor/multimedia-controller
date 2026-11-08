import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import keyboard
import time
import argparse

# --- Настройки ---
BAUD_RATE = 9600
MIC_SYNC_INTERVAL = 0.5

# --- Адаптивный шаг ---
ACCEL_TIMEOUT = 0.3
SPEED_TABLE = [
    (0.015, 10),
    (0.030, 5),
    (0.060, 3),
    (0.120, 2),
    (999.0, 1),
]

# --- Глобальные переменные ---
ser = None
current_volume = 50          # 0..100 (совпадает с Windows)
last_click_time = 0.0


# All serial and Windows audio access stays on the main thread.
def send_command(message):
    if ser is not None and ser.is_open:
        ser.write((message + "\n").encode("ascii"))


def send_to_display(volume_percent):
    send_command(f"DISP:VOL:{volume_percent}")


def send_mute_state(muted):
    send_command("DISP:MUTE:" + ("ON" if muted else "OFF"))


def send_mic_state(muted):
    """DISP:MIC describes whether the microphone is ON, not whether it is muted."""
    send_command("DISP:MIC:" + ("OFF" if muted else "ON"))


def sync_mic_from_system():
    """Reacquire the default endpoint after sleep/device changes and retry on failure."""
    try:
        mic = get_mic_interface()
        # Send even unchanged state: the board may have reset while Windows slept.
        send_mic_state(mic.GetMute())
    except serial.SerialException:
        raise
    except Exception as e:
        print(f"Microphone sync error: {e}")


def sync_speaker_from_system():
    """Reacquire the endpoint and resend state, including after a board reset."""
    try:
        speaker = get_speaker_interface()
        sync_volume_from_system(speaker)
        send_to_display(current_volume)
        send_mute_state(speaker.GetMute())
    except serial.SerialException:
        raise
    except Exception as e:
        print(f"Speaker sync error: {e}")


# --- Поиск Arduino ---
def find_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(k in port.description for k in ["CH340", "Arduino", "USB Serial", "USB-SERIAL"]):
            return port.device
    return None

# --- Интерфейс динамиков ---
def get_speaker_interface():
    devices = AudioUtilities.GetSpeakers()
    return devices.EndpointVolume.QueryInterface(IAudioEndpointVolume)

# --- Интерфейс микрофона ---
def get_mic_interface():
    devices = AudioUtilities.GetMicrophone()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))

# --- Синхронизация при старте ---
def sync_volume_from_system(volume):
    global current_volume
    real_linear = volume.GetMasterVolumeLevelScalar()
    current_volume = int(round(real_linear * 100))


# --- Адаптивный шаг ---
def get_step_multiplier(interval):
    for threshold, multiplier in SPEED_TABLE:
        if interval <= threshold:
            return multiplier
    return 1

def change_volume_adaptive(volume, direction):
    """direction: +1 (вверх) или -1 (вниз). Шаг зависит от скорости вращения."""
    global current_volume, last_click_time

    now = time.monotonic()
    interval = now - last_click_time

    # Read the selected device even during a fast turn or after a device switch.
    current_volume = int(round(volume.GetMasterVolumeLevelScalar() * 100))
    multiplier = 1 if last_click_time == 0 or interval > ACCEL_TIMEOUT else get_step_multiplier(interval)
    last_click_time = now

    # Меняем громкость в процентах, напрямую
    current_volume = max(0, min(100, current_volume + direction * multiplier))

    # Отправляем в Windows
    volume.SetMasterVolumeLevelScalar(current_volume / 100.0, None)

    # Отправляем на дисплей
    send_to_display(current_volume)

    print(f"Громкость: {current_volume}% (шаг {multiplier})")


# --- Mute динамиков ---
def toggle_speaker_mute(volume):
    muted = volume.GetMute()
    volume.SetMute(not muted, None)
    new_state = volume.GetMute()
    print("🔊 Звук ВЫКЛ" if new_state else "🔊 Звук ВКЛ")
    send_mute_state(new_state)


# --- Mute микрофона ---
def toggle_mic_mute():
    try:
        mic = get_mic_interface()
        mic.SetMute(not mic.GetMute(), None)
        # Report the actual result, rather than assuming SetMute succeeded.
        send_mic_state(mic.GetMute())
    except serial.SerialException:
        raise
    except Exception as e:
        print(f"Microphone toggle error: {e}")

def handle_command(line):
    try:
        if line == "VOL_UP":
            change_volume_adaptive(get_speaker_interface(), +1)
        elif line == "VOL_DOWN":
            change_volume_adaptive(get_speaker_interface(), -1)
        elif line == "SPEAKER_MUTE":
            toggle_speaker_mute(get_speaker_interface())
        elif line == "TRACK_NEXT":
            keyboard.send("next track")
        elif line == "TRACK_PREV":
            keyboard.send("previous track")
        elif line == "PLAY_PAUSE":
            keyboard.send("play/pause media")
        elif line == "MIC_MUTE":
            toggle_mic_mute()
    except serial.SerialException:
        raise
    except Exception as e:
        # Audio endpoints can disappear temporarily while Windows resumes.
        print(f"Command error: {e}")


def run_connected():
    next_sync = 0.0
    next_ping = 0.0
    while True:
        now = time.monotonic()
        if now >= next_ping:
            send_command("PING")
            next_ping = now + 1.0
        if now >= next_sync:
            sync_speaker_from_system()
            sync_mic_from_system()
            next_sync = now + MIC_SYNC_INTERVAL
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            handle_command(line)


def main(port=None):
    global ser, last_click_time
    try:
        while True:
            try:
                device = port or find_arduino()
                if device:
                    print(f"Connecting to {device}...")
                    ser = serial.Serial(device, BAUD_RATE, timeout=MIC_SYNC_INTERVAL,
                                        write_timeout=1)
                    time.sleep(2)  # Opening serial resets the Nano.
                    ser.reset_input_buffer()
                    last_click_time = 0.0
                    run_connected()
                else:
                    print("Controller not found; retrying in 2 seconds.")
            except (serial.SerialException, OSError) as e:
                print(f"Serial connection lost: {e}; retrying in 2 seconds.")
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except (serial.SerialException, OSError):
                        pass
                    ser = None
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nExit.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Windows bridge for the media controller")
    parser.add_argument("--port", help="Explicit COM port for a board not detected automatically")
    main(parser.parse_args().port)
