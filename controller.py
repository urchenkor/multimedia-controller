import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import keyboard
import time

# --- Настройки ---
BAUD_RATE = 9600
VOLUME_STEP = 0.02   # шаг громкости (0.02 = 2%)

# --- Поиск Arduino ---
def find_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(k in port.description for k in ["CH340", "Arduino", "USB Serial", "USB-SERIAL"]):
            return port.device
    if ports:
        return ports[0].device
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

# --- Громкость ---
def change_volume(volume, delta):
    current = volume.GetMasterVolumeLevelScalar()
    new = max(0.0, min(1.0, current + delta))
    volume.SetMasterVolumeLevelScalar(new, None)
    print(f"Громкость: {int(new * 100)}%")

# --- Mute динамиков ---
def toggle_speaker_mute(volume):
    muted = volume.GetMute()
    volume.SetMute(not muted, None)
    print("🔊 Звук ВЫКЛ" if not muted else "🔊 Звук ВКЛ")

# --- Mute микрофона ---
def toggle_mic_mute(mic):
    muted = mic.GetMute()
    mic.SetMute(not muted, None)
    print("🎤 Микрофон ВЫКЛ" if not muted else "🎤 Микрофон ВКЛ")

# --- Основной цикл ---
def main():
    port = find_arduino()
    if not port:
        print("Arduino не найдена. Проверь подключение.")
        return

    print(f"Подключаюсь к {port}...")
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
    except serial.SerialException as e:
        print(f"Ошибка открытия порта: {e}")
        return

    speaker = get_speaker_interface()
    mic = get_mic_interface()
    print("Готово. Управляй!")

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            print(f"← {line}")

            if line == "VOL_UP":
                change_volume(speaker, +VOLUME_STEP)
            elif line == "VOL_DOWN":
                change_volume(speaker, -VOLUME_STEP)
            elif line == "SPEAKER_MUTE":
                toggle_speaker_mute(speaker)
            elif line == "TRACK_NEXT":
                keyboard.send("next track")
            elif line == "TRACK_PREV":
                keyboard.send("previous track")
            elif line == "PLAY_PAUSE":
                keyboard.send("play/pause media")
            elif line == "MIC_MUTE":
                toggle_mic_mute(mic)

    except KeyboardInterrupt:
        print("\nВыход.")
    finally:
        ser.close()

if __name__ == "__main__":
    main()