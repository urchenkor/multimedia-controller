// ============================================================
//  Media Controller — Arduino Nano
//  + OLED 128x64 SSD1306 (I2C)
//  Энкодер: громкость + mute звука
//  Свитчи: трек вперёд/назад, пауза, mute микрофона
//  Встроенный светодиод D13: индикатор состояния микрофона
// ============================================================

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --- Дисплей ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 32
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- Энкодер ---
const int pinCLK = 2;
const int pinDT  = 3;
const int btnMute = 4;      // кнопка энкодера → mute ЗВУКА

// --- Свитчи ---
const int btnNext = 6;      // трек вперёд
const int btnPrev = 7;      // трек назад
const int btnPlay = 5;      // пауза/воспроизведение
const int btnMic  = 8;      // mute МИКРОФОНА

// --- Светодиод ---
const int ledPin = 13;

// --- Энкодер: переменные ---
volatile int lastEncoded = 0;
volatile long encoderValue = 0;
long lastEncoderValue = 0;
const int stepsPerClick = 4;

// --- Антидребезг ---
const unsigned long debounceDelay = 50;

bool muteBtnReading = HIGH;
bool muteBtnState   = HIGH;
unsigned long muteBtnDebounce = 0;

const int switchPins[4] = {btnNext, btnPrev, btnPlay, btnMic};
const char* switchCmds[4] = {"TRACK_NEXT", "TRACK_PREV", "PLAY_PAUSE", "MIC_MUTE"};
bool switchReading[4] = {HIGH, HIGH, HIGH, HIGH};
bool switchState[4]   = {HIGH, HIGH, HIGH, HIGH};
unsigned long switchDebounce[4] = {0, 0, 0, 0};

// --- Состояние ---
bool micOn = true;
int currentVolume = 50;   // 0..100

// --- Буфер для входящих команд ---
String inputBuffer = "";

void setup() {
  Serial.begin(9600);

  // Дисплей
  if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println("SSD1306 не найден!");
    for (;;);
  }
  display.clearDisplay();
  display.display();

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

  digitalWrite(ledPin, micOn ? HIGH : LOW);

  drawScreen();
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

// ============================================================
//  Отрисовка экрана
// ============================================================
void drawScreen() {
  display.clearDisplay();

  // --- Строка 1: VOLUME и процент ---
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.print("VOLUME");

  // Процент справа (выравниваем по правому краю)
  char volStr[5];
  sprintf(volStr, "%3d%%", currentVolume);
  int16_t x1, y1;
  uint16_t w, h;
  display.getTextBounds(volStr, 0, 0, &x1, &y1, &w, &h);
  display.setCursor(SCREEN_WIDTH - w - 2, 0);
  display.print(volStr);

  // --- Строка 2: полоска громкости ---
  int barX = 0;
  int barY = 14;
  int barW = SCREEN_WIDTH - 2;
  int barH = 12;

  display.drawRect(barX, barY, barW, barH, SSD1306_WHITE);

  int fillW = (barW - 4) * currentVolume / 100;
  if (fillW > 0) {
    display.fillRect(barX + 2, barY + 2, fillW, barH - 4, SSD1306_WHITE);
  }

  // --- Строка 3: микрофон ---
  display.setTextSize(1);
  display.setCursor(0, 34);
  display.print("MIC:");

  // Индикатор (закрашенный или пустой кружок)
  int dotX = 32;
  int dotY = 38;
  if (micOn) {
    display.fillCircle(dotX, dotY, 4, SSD1306_WHITE);
  } else {
    display.drawCircle(dotX, dotY, 4, SSD1306_WHITE);
  }

  display.setCursor(42, 34);
  display.print(micOn ? "ON" : "OFF");

  display.display();
}

// ============================================================
//  Парсинг входящих команд от Python
// ============================================================
void handleIncoming(String cmd) {
  // Формат: DISP:VOL:75
  if (cmd.startsWith("DISP:VOL:")) {
    int val = cmd.substring(9).toInt();
    if (val >= 0 && val <= 100 && val != currentVolume) {
      currentVolume = val;
      drawScreen();
    }
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      inputBuffer.trim();
      if (inputBuffer.length() > 0) {
        handleIncoming(inputBuffer);
      }
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
      if (inputBuffer.length() > 64) inputBuffer = "";  // защита от переполнения
    }
  }
}

// ============================================================
//  Основной цикл
// ============================================================
void loop() {
  // --- Входящие команды от Python ---
  readSerial();

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
          if (switchPins[i] == btnMic) {
            micOn = !micOn;
            digitalWrite(ledPin, micOn ? HIGH : LOW);
            drawScreen();   // обновляем экран сразу
          }
          Serial.println(switchCmds[i]);
        }
      }
    }
  }
}