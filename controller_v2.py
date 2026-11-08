import serial
import serial.tools.list_ports
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import keyboard
import time
import threading

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
serial_write_lock = threading.Lock()
current_volume = 50          # 0..100 (совпадает с Windows)
last_click_time = 0.0
last_encoder_change = 0.0


# --- Heartbeat ---
def heartbeat():
    """Раз в секунду шлёт PING на Arduino, чтобы она знала, что ПК жив."""
    global ser
    while True:
        if ser is not None and ser.is_open:
            try:
                with serial_write_lock:
                    ser.write(b"PING\n")
            except serial.SerialException:
                pass
        time.sleep(1)

# --- Отправка на дисплей ---
def send_to_display(volume_percent):
    global ser
    if ser is not None and ser.is_open:
        try:
            msg = f"DISP:VOL:{volume_percent}\n"
            with serial_write_lock:
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
            with serial_write_lock:
                ser.write(msg.encode())
            print(f"→ {msg.strip()}")
        except serial.SerialException as e:
            print(f"Ошибка отправки: {e}")

# --- Синхронизация микрофона ---
def send_mic_state(muted):
    """DISP:MIC describes whether the microphone is ON, not whether it is muted."""
    if ser is not None and ser.is_open:
        state = "OFF" if muted else "ON"
        with serial_write_lock:
            ser.write(f"DISP:MIC:{state}\n".encode())


def sync_mic_from_system():
    """Reacquire the default endpoint after sleep/device changes and retry on failure."""
    try:
        mic = get_mic_interface()
        # Send even unchanged state: the board may have reset while Windows slept.
        send_mic_state(mic.GetMute())
    except Exception as e:
        print(f"Microphone sync error: {e}")


# --- Опрос громкости и mute ---
def volume_watcher(volume):
    """Раз в 0.5 сек проверяет системную громкость и обновляет дисплей."""
    global current_volume, last_encoder_change
    last_sent_vol = -1
    last_sent_mute = None

    while True:
        try:
            if time.time() - last_encoder_change < 1.0:
                time.sleep(0.1)
                continue

            real_linear = volume.GetMasterVolumeLevelScalar()
            display_percent = int(round(real_linear * 100))

            if display_percent != last_sent_vol:
                last_sent_vol = display_percent
                current_volume = display_percent
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

# --- Синхронизация при старте ---
def sync_volume_from_system(volume):
    global current_volume
    real_linear = volume.GetMasterVolumeLevelScalar()
    current_volume = int(round(real_linear * 100))
    print(f"Текущая громкость Windows: {current_volume}%")


# --- Адаптивный шаг ---
def get_step_multiplier(interval):
    for threshold, multiplier in SPEED_TABLE:
        if interval <= threshold:
            return multiplier
    return 1

def change_volume_adaptive(volume, direction):
    """direction: +1 (вверх) или -1 (вниз). Шаг зависит от скорости вращения."""
    global current_volume, last_click_time, last_encoder_change

    now = time.time()
    interval = now - last_click_time

    if interval > ACCEL_TIMEOUT:
        # После паузы — синхронизация с реальной громкостью Windows
        real_linear = volume.GetMasterVolumeLevelScalar()
        current_volume = int(round(real_linear * 100))
        multiplier = 1
    else:
        multiplier = get_step_multiplier(interval)

    last_click_time = now
    last_encoder_change = now

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
    new_state = not muted
    print("🔊 Звук ВЫКЛ" if new_state else "🔊 Звук ВКЛ")
    send_mute_state(new_state)


# --- Mute микрофона ---
def toggle_mic_mute():
    try:
        mic = get_mic_interface()
        mic.SetMute(not mic.GetMute(), None)
        # Report the actual result, rather than assuming SetMute succeeded.
        send_mic_state(mic.GetMute())
    except Exception as e:
        print(f"Microphone toggle error: {e}")

# --- Основной цикл ---
def main():
    global ser, current_volume

    port = find_arduino()
    if not port:
        print("Arduino не найдена. Проверь подключение.")
        return

    print(f"Подключаюсь к {port}...")
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=MIC_SYNC_INTERVAL)
        time.sleep(2)
        ser.reset_input_buffer()
    except serial.SerialException as e:
        print(f"Ошибка открытия порта: {e}")
        return

    speaker = get_speaker_interface()
    sync_volume_from_system(speaker)

    send_to_display(current_volume)
    send_mute_state(speaker.GetMute())

    sync_mic_from_system()
    next_mic_sync = time.monotonic() + MIC_SYNC_INTERVAL
    watcher = threading.Thread(target=volume_watcher, args=(speaker,), daemon=True)
    watcher.start()
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()

    print("Готово. Управляй!")

    try:
        while True:
            # Keep COM access on the main thread, independent of encoder activity.
            if time.monotonic() >= next_mic_sync:
                sync_mic_from_system()
                next_mic_sync = time.monotonic() + MIC_SYNC_INTERVAL
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
                toggle_mic_mute()

    except KeyboardInterrupt:
        print("\nВыход.")
    finally:
        if ser and ser.is_open:
            ser.close()


if __name__ == "__main__":
    main()
