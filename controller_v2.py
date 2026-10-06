import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import keyboard
import math
import time
import threading

# --- Настройки ---
BAUD_RATE = 9600
VOLUME_STEPS = 100
VOLUME_K = 3.0

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
current_step = 30
last_click_time = 0.0

# --- Отправка на дисплей ---
def send_to_display(volume_percent):
    global ser
    if ser is not None and ser.is_open:
        try:
            msg = f"DISP:VOL:{volume_percent}\n"
            ser.write(msg.encode())
            print(f"→ {msg.strip()}")
        except serial.SerialException as e:
            print(f"Ошибка отправки: {e}")

# +++ MUTE +++
def send_mute_state(muted):
    global ser
    if ser is not None and ser.is_open:
        try:
            state = "ON" if muted else "OFF"
            msg = f"DISP:MUTE:{state}\n"
            ser.write(msg.encode())
            print(f"→ {msg.strip()}")
        except serial.SerialException as e:
            print(f"Ошибка отправки: {e}")

# --- Опрос громкости и mute ---
def volume_watcher(volume):
    """Раз в 0.5 сек проверяет системную громкость и обновляет дисплей."""
    global current_step
    last_sent_vol = -1
    last_sent_mute = None

    while True:
        try:
            real_linear = volume.GetMasterVolumeLevelScalar()
            display_percent = int(real_linear * 100)

            if display_percent != last_sent_vol:
                last_sent_vol = display_percent
                send_to_display(display_percent)

            # +++ MUTE: следим за состоянием mute +++
            muted = volume.GetMute()
            if muted != last_sent_mute:
                last_sent_mute = muted
                send_mute_state(muted)

        except Exception as e:
            print(f"Watcher error: {e}")

        time.sleep(0.5)

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
    step = max(0, min(VOLUME_STEPS, step))
    ratio = step / VOLUME_STEPS
    return (math.exp(VOLUME_K * ratio) - 1) / (math.exp(VOLUME_K) - 1)

def linear_to_step(linear):
    linear = max(0.0, min(1.0, linear))
    if linear <= 0:
        return 0
    ratio = math.log(linear * (math.exp(VOLUME_K) - 1) + 1) / VOLUME_K
    return int(round(ratio * VOLUME_STEPS))

def sync_volume_from_system(volume):
    global current_step
    real_linear = volume.GetMasterVolumeLevelScalar()
    current_step = linear_to_step(real_linear)
    print(f"Текущая громкость Windows: {int(real_linear*100)}% "
          f"(ступень {current_step}/{VOLUME_STEPS})")

def get_step_multiplier(interval):
    for threshold, multiplier in SPEED_TABLE:
        if interval <= threshold:
            return multiplier
    return 1

def change_volume_adaptive(volume, direction):
    global current_step, last_click_time

    now = time.time()
    interval = now - last_click_time

    if interval > ACCEL_TIMEOUT:
        real_linear = volume.GetMasterVolumeLevelScalar()
        current_step = linear_to_step(real_linear)
        multiplier = 1
    else:
        multiplier = get_step_multiplier(interval)

    last_click_time = now

    current_step = max(0, min(VOLUME_STEPS, current_step + direction * multiplier))
    linear = step_to_linear(current_step)
    volume.SetMasterVolumeLevelScalar(linear, None)

    # Процент для дисплея (0..100) — переводим из ступеней
    display_percent = int(current_step * 100 / VOLUME_STEPS)
    send_to_display(display_percent)

    print(f"Громкость: {current_step}/{VOLUME_STEPS} "
          f"(шаг {multiplier}, {int(linear*100)}%)")

# --- Mute динамиков ---
def toggle_speaker_mute(volume):
    muted = volume.GetMute()
    volume.SetMute(not muted, None)
    new_state = not muted
    print("🔊 Звук ВЫКЛ" if new_state else "🔊 Звук ВКЛ")
    send_mute_state(new_state)   # +++ MUTE +++

# --- Mute микрофона ---
def toggle_mic_mute(mic):
    muted = mic.GetMute()
    mic.SetMute(not muted, None)
    print("🎤 Микрофон ВЫКЛ" if not muted else "🎤 Микрофон ВКЛ")

# --- Основной цикл ---
def main():
    global ser, current_step

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

    # Отправляем начальную громкость на дисплей
    display_percent = int(current_step * 100 / VOLUME_STEPS)
    send_to_display(display_percent)

    # +++ MUTE: начальное состояние +++
    send_mute_state(speaker.GetMute())

    mic = get_mic_interface()
    watcher = threading.Thread(target=volume_watcher, args=(speaker,), daemon=True)
    watcher.start()

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
        if ser and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()