const int pinCLK = 2;
const int pinDT  = 3;
const int btnMute = 4;

volatile int lastEncoded = 0;
volatile long encoderValue = 0;
long lastEncoderValue = 0;

const int stepsPerClick = 4;

// --- Переменные для кнопки ---
bool lastButtonState = HIGH;
bool reading = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;

bool micOn = true;

void setup() {
  Serial.begin(9600);

  pinMode(pinCLK, INPUT_PULLUP);
  pinMode(pinDT,  INPUT_PULLUP);
  pinMode(btnMute, INPUT_PULLUP);

  int MSB = digitalRead(pinCLK);
  int LSB = digitalRead(pinDT);
  lastEncoded = (MSB << 1) | LSB;

  attachInterrupt(digitalPinToInterrupt(pinCLK), updateEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(pinDT),  updateEncoder, CHANGE);

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
  // --- Вращение ---
  long currentClicks = encoderValue / stepsPerClick;
  if (currentClicks != lastEncoderValue) {
    if (currentClicks > lastEncoderValue) {
      Serial.println("VOL_UP");
    } else {
      Serial.println("VOL_DOWN");
    }
    lastEncoderValue = currentClicks;
  }

  // --- Кнопка Mute ---
  int currentReading = digitalRead(btnMute);

  if (currentReading != reading) {
    lastDebounceTime = millis();
    reading = currentReading;
  }

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading != lastButtonState) {
      lastButtonState = reading;

     if (lastButtonState == LOW) {
             Serial.println("MIC_TOGGLE");   // было micOn ? "MIC_ON" : "MIC_OFF"
           }
    }
  }
}