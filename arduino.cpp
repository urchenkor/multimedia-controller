// ============================================================
//  Media Controller — Arduino Nano
//  Энкодер: громкость + mute звука
//  Свитчи: трек вперёд/назад, пауза, mute микрофона
//  Встроенный светодиод D13: индикатор состояния микрофона
// ============================================================

// --- Энкодер ---
const int pinCLK = 2;
const int pinDT  = 3;
const int btnMute = 4;      // кнопка энкодера → mute ЗВУКА

// --- Свитчи ---
const int btnNext = 6;      // трек вперёд
const int btnPrev = 7;      // трек назад
const int btnPlay = 5;      // пауза/воспроизведение
const int btnMic  = 8;      // mute МИКРОФОНА

// --- Встроенный светодиод ---
const int ledPin = 13;

// --- Энкодер: переменные ---
volatile int lastEncoded = 0;
volatile long encoderValue = 0;
long lastEncoderValue = 0;
const int stepsPerClick = 4;

// --- Антидребезг ---
const unsigned long debounceDelay = 50;

// Для кнопки энкодера
bool muteBtnReading = HIGH;
bool muteBtnState   = HIGH;
unsigned long muteBtnDebounce = 0;

// Для свитчей (массивы)
const int switchPins[4] = {btnNext, btnPrev, btnPlay, btnMic};
const char* switchCmds[4] = {"TRACK_NEXT", "TRACK_PREV", "PLAY_PAUSE", "MIC_MUTE"};
bool switchReading[4] = {HIGH, HIGH, HIGH, HIGH};
bool switchState[4]   = {HIGH, HIGH, HIGH, HIGH};
unsigned long switchDebounce[4] = {0, 0, 0, 0};

// --- Состояние микрофона ---
bool micOn = true;

void setup() {
  Serial.begin(9600);

  // Энкодер
  pinMode(pinCLK, INPUT_PULLUP);
  pinMode(pinDT,  INPUT_PULLUP);
  pinMode(btnMute, INPUT_PULLUP);

  // Свитчи
  for (int i = 0; i < 4; i++) {
    pinMode(switchPins[i], INPUT_PULLUP);
  }

  // Светодиод
  pinMode(ledPin, OUTPUT);

  // Начальное состояние энкодера
  int MSB = digitalRead(pinCLK);
  int LSB = digitalRead(pinDT);
  lastEncoded = (MSB << 1) | LSB;

  attachInterrupt(digitalPinToInterrupt(pinCLK), updateEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(pinDT),  updateEncoder, CHANGE);

  // Микрофон по умолчанию включён
  digitalWrite(ledPin, HIGH);

  Serial.println("READY");
}

void updateEncoder() {
  int MSB = digitalRead(pinCLK);
  int LSB = digitalRead(pinDT);
  int encoded = (MSB << 1) | LSB;
  int sum = (lastEncoded << 2) | encoded;

  if (sum == 0b1101 || sum == 0b0100 || sum == 0b0010 || sum == 0b1011) {
    encoderValue++;
  }
  if (sum == 0b1110 || sum == 0b0111 || sum == 0b0001 || sum == 0b1000) {
    encoderValue--;
  }

  lastEncoded = encoded;
}

void loop() {
  // ============================================
  //  ЭНКОДЕР — вращение
  // ============================================
  long currentClicks = encoderValue / stepsPerClick;
  if (currentClicks != lastEncoderValue) {
    if (currentClicks > lastEncoderValue) {
      Serial.println("VOL_UP");
    } else {
      Serial.println("VOL_DOWN");
    }
    lastEncoderValue = currentClicks;
  }

  // ============================================
  //  КНОПКА ЭНКОДЕРА — mute звука
  // ============================================
  int muteReading = digitalRead(btnMute);

  if (muteReading != muteBtnReading) {
    muteBtnDebounce = millis();
    muteBtnReading = muteReading;
  }

  if ((millis() - muteBtnDebounce) > debounceDelay) {
    if (muteBtnReading != muteBtnState) {
      muteBtnState = muteBtnReading;
      if (muteBtnState == LOW) {
        Serial.println("SPEAKER_MUTE");
      }
    }
  }

  // ============================================
  //  СВИТЧИ
  // ============================================
  for (int i = 0; i < 4; i++) {
    int reading = digitalRead(switchPins[i]);

    if (reading != switchReading[i]) {
      switchDebounce[i] = millis();
      switchReading[i] = reading;
    }

    if ((millis() - switchDebounce[i]) > debounceDelay) {
      if (switchReading[i] != switchState[i]) {
        switchState[i] = switchReading[i];

        if (switchState[i] == LOW) {
          // Особый случай — mute микрофона переключает состояние и светодиод
          if (switchPins[i] == btnMic) {
            micOn = !micOn;
            digitalWrite(ledPin, micOn ? HIGH : LOW);
          }
          Serial.println(switchCmds[i]);
        }
      }
    }
  }
}