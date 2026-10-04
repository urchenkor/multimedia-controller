import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
import time

# --- Настройки ---
BAUD_RATE = 9600
VOLUME_STEP = 0.02   # шаг громкости (0.02 = 2%)

# --- Поиск Arduino ---
def find_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(keyword in port.description for keyword in ["CH340", "Arduino", "USB Serial", "USB-SERIAL"]):
            return port.device
    if ports:
        return ports[0].device
    return None

# --- Управление громкостью ---
def get_volume_interface():
    devices = AudioUtilities.GetSpeakers()
    return devices.EndpointVolume.QueryInterface(IAudioEndpointVolume)

def change_volume(volume, delta):
    current = volume.GetMasterVolumeLevelScalar()
    new = max(0.0, min(1.0, current + delta))
    volume.SetMasterVolumeLevelScalar(new, None)
    print(f"Громкость: {int(new * 100)}%")

def toggle_mute(volume):
    muted = volume.GetMute()
    volume.SetMute(not muted, None)
    print("Звук ВЫКЛ" if not muted else "Звук ВКЛ")

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

    volume = get_volume_interface()
    print("Готово. Крути ручку, жми кнопку!")

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            print(f"Получено: {line}")

            if line == "VOL_UP":
                change_volume(volume, +VOLUME_STEP)
            elif line == "VOL_DOWN":
                change_volume(volume, -VOLUME_STEP)
            elif line == "MIC_TOGGLE" or line == "MIC_ON" or line == "MIC_OFF":
                # Кнопка энкодера теперь управляет mute динамиков
                toggle_mute(volume)

    except KeyboardInterrupt:
        print("\nВыход.")
    finally:
        ser.close()

if __name__ == "__main__":
    main()