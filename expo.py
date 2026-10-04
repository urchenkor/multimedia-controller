import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import keyboard
import math
import time

# --- Настройки ---
BAUD_RATE = 9600
VOLUME_STEPS = 100
VOLUME_K = 3.0

# Текущая ступень громкости
current_step = 50

# --- Адаптивный шаг ---
last_click_time = 0.0          # время последнего щелчка
ACCEL_TIMEOUT = 0.3            # если пауза больше 0.3 сек — сбрасываем разгон

# Пороги интервала (сек) → множитель шага
# Чем меньше интервал, тем больше шаг
SPEED_TABLE = [
    (0.015, 10),   # 15 мс и меньше  → шаг 10 (очень быстро)
    (0.030, 7),    # 30 мс и меньше  → шаг 5
    (0.060, 5),    # 60 мс и меньше  → шаг 3
    (0.120, 3),    # 120 мс и меньше → шаг 2
    (999.0, 1),    # всё остальное   → шаг 1 (медленно)
]
def get_step_multiplier(interval):
    """Определяет множитель шага по интервалу между щелчками."""
    for threshold, multiplier in SPEED_TABLE:
        if interval <= threshold:
            return multiplier
    return 1

def change_volume_adaptive(volume, direction):
    """
    direction: +1 (вверх) или -1 (вниз).
    Шаг зависит от скорости вращения.
    """
    global current_step, last_click_time

    now = time.time()
    interval = now - last_click_time

    # Если пауза большая — сбрасываем разгон, начинаем с 1
    if interval > ACCEL_TIMEOUT:
        multiplier = 1
    else:
        multiplier = get_step_multiplier(interval)

    last_click_time = now

    # Пересинхронизация с реальной громкостью Windows
    real_linear = volume.GetMasterVolumeLevelScalar()
    current_step = linear_to_step(real_linear)

    # Применяем шаг с учётом направления
    current_step = max(0, min(VOLUME_STEPS, current_step + direction * multiplier))

    linear = step_to_linear(current_step)
    volume.SetMasterVolumeLevelScalar(linear, None)

    print(f"Громкость: ступень {current_step}/{VOLUME_STEPS} "
          f"(шаг {multiplier}, линейно {int(linear*100)}%)")

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


# --- Преобразования громкости ---
def step_to_linear(step):
    """Ступень (0..100) → линейное значение (0.0..1.0)"""
    step = max(0, min(VOLUME_STEPS, step))
    ratio = step / VOLUME_STEPS
    return (math.exp(VOLUME_K * ratio) - 1) / (math.exp(VOLUME_K) - 1)


def linear_to_step(linear):
    """Линейное значение (0.0..1.0) → ступень (0..100)"""
    linear = max(0.0, min(1.0, linear))
    if linear <= 0:
        return 0
    ratio = math.log(linear * (math.exp(VOLUME_K) - 1) + 1) / VOLUME_K
    return int(round(ratio * VOLUME_STEPS))


def sync_volume_from_system(volume):
    """Считывает текущую громкость Windows и выставляет current_step."""
    global current_step
    real_linear = volume.GetMasterVolumeLevelScalar()
    current_step = linear_to_step(real_linear)
    print(f"Текущая громкость Windows: {int(real_linear*100)}% "
          f"(ступень {current_step}/{VOLUME_STEPS})")

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
    sync_volume_from_system(speaker)

    mic = get_mic_interface()
    print("Готово. Управляй!")

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            print(f"← {line}")

            if line == "VOL_UP":
                change_volume_adaptive(speaker, +1)
            elif line == "VOL_DOWN":
                change_volume_adaptive(speaker, -1)
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