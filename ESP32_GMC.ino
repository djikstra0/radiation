#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include <vector>

#define LOG_PERIOD 60000  // Period merenja (60 sekundi)

// --- WiFi Podesavanja ---
const char* ssid = "";
const char* password = "";

// --- MQTT Podesavanja ---
const char* mqtt_server = ""; // IP adresa Windows PC
const int mqtt_port = 1883;
const char* mqtt_topic = "radijacija/srbija/nis";
const char* sensor_id = "ESP32_GMC_01"; // Jedinstveni ID ovog senzora

// --- NTP Podesavanja ---
const char* ntp_server = "pool.ntp.org";
const long gmt_offset_sec = 3600;      // UTC + 1 (Srbija zimi)
const int daylight_offset_sec = 3600;  // +1 sat tokom letnjeg racunanja vremena

// --- Struktura za Offline Buffering ---
struct Measurement {
  String timestamp;
  unsigned long value;
};

std::vector<Measurement> offlineBuffer;
const int size_limits_buffer = 100; // Maksimalan broj zapisa u memoriji da se ne prepuni RAM

WiFiClient espClient;
PubSubClient client(espClient);

const byte interruptPin = 5;
volatile unsigned long counts;
unsigned long cpm;
unsigned long previousMillis;

// --- MQTT Grace Period ---
unsigned long mqttConnectedAt = 0;
bool mqttGracePeriod = false;

const unsigned long MQTT_GRACE_PERIOD = 30000; // 30 sekundi

void IRAM_ATTR tubePulse() {
  counts++;
}

// Funkcija za dobijanje trenutnog vremena
String getFormattedTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Greska: Nemoguce preuzeti vreme!");
    return "N/A";
  }

  char timeStringBuff[30];

  // Format: YYYY-MM-DD HH:MM:SS
  strftime(timeStringBuff, sizeof(timeStringBuff), "%Y-%m-%d %H:%M:%S", &timeinfo);

  return String(timeStringBuff);
}

// Funkcija za povezivanje na WiFi i sinhronizaciju vremena
void setup_wifi() {
  delay(10);

  Serial.println();
  Serial.print("Povezivanje na ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi povezan!");
  Serial.print("IP adresa: ");
  Serial.println(WiFi.localIP());

  // Inicijalizacija i sinhronizacija vremena sa NTP serverom
  Serial.println("Sinhronizacija vremena sa NTP serverom...");
  configTime(gmt_offset_sec, daylight_offset_sec, ntp_server);

  // Cekamo dok se vreme uspesno ne preuzme
  struct tm timeinfo;

  while (!getLocalTime(&timeinfo)) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nVreme uspesno sinhronizovano!");
  Serial.print("Trenutno vreme: ");
  Serial.println(getFormattedTime());
}

// Funkcija za slanje nakupljenih offline podataka kada MQTT proradi
void flushOfflineBuffer() {
  if (offlineBuffer.empty()) return;

  Serial.printf(
    "Veza uspostavljena. Slanje nakupljenih podataka iz bafera (%d zapisa)...\n",
    offlineBuffer.size()
  );

  // Prolazimo kroz bafer od pocetka
  while (!offlineBuffer.empty() && client.connected()) {
    Measurement m = offlineBuffer.front();

    // Kreiranje JSON-a sa sacuvanim vremenom kada se merenje zaista desilo
    String payload =
      "{\"sensor_id\":\"" + String(sensor_id) +
      "\",\"value\":" + String(m.value) +
      ",\"timestamp\":\"" + m.timestamp + "\"}";

    if (client.publish(mqtt_topic, payload.c_str())) {

      Serial.print("Uspesno poslat offline podatak: ");
      Serial.println(payload);

      offlineBuffer.erase(offlineBuffer.begin());

    } else {

      Serial.println(
        "Prekid slanja bafera, MQTT konekcija ponovo pukla."
      );

      break;
    }

    delay(100); // Kratka pauza izmedju slanja podataka
  }
}

// Funkcija za rekonekciju na MQTT broker (samo ako ima WiFi-ja)
void reconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    return; // Nemoj blokirati kod ako nema uopste WiFi mreze
  }

  if (!client.connected()) {

    Serial.print("Pokusaj MQTT povezivanja...");

    if (client.connect("ESP32_Radiation_Client")) {

      Serial.println("povezan na MQTT Broker!");

      // Zapocinjemo grace period od 30 sekundi.
      // Offline podaci se ne salju odmah nakon povezivanja.
      mqttConnectedAt = millis();
      mqttGracePeriod = true;

      Serial.println(
        "Cekanje 30 sekundi pre slanja offline podataka."
      );

    } else {

      Serial.print("neuspesno, rc=");
      Serial.print(client.state());
      Serial.println(
        " pokusavam ponovo u sledecem krugu"
      );
    }
  }
}

void setup() {

  counts = 0;
  cpm = 0;

  pinMode(interruptPin, INPUT);

  attachInterrupt(
    digitalPinToInterrupt(interruptPin),
    tubePulse,
    FALLING
  );

  Serial.begin(9600);

  setup_wifi();

  client.setServer(mqtt_server, mqtt_port);
}

void loop() {

  // Odrzavanje WiFi veze
  if (WiFi.status() != WL_CONNECTED) {

    // Ako pukne WiFi, pokusavamo ponovno povezivanje
    // bez blokade glavne petlje
    WiFi.begin(ssid, password);

  } else {

    // Ako ima WiFi-ja, proveri i odrzavaj MQTT vezu
    if (!client.connected()) {
      reconnect();
    }

    client.loop();

    // MQTT grace period:
    // nakon uspostavljanja veze cekamo 30 sekundi pre slanja
    // podataka iz offline bafera
    if (mqttGracePeriod && client.connected()) {

      if (millis() - mqttConnectedAt >= MQTT_GRACE_PERIOD) {

        mqttGracePeriod = false;

        Serial.println(
          "Prosao grace period. Pokretanje slanja offline podataka."
        );

        flushOfflineBuffer();
      }
    }
  }

  unsigned long currentMillis = millis();

  if (currentMillis - previousMillis > LOG_PERIOD) {

    previousMillis = currentMillis;

    // Citanje i resetovanje impulsa (atomski)
    noInterrupts();

    cpm = counts / 8;
    counts = 0;

    interrupts();

    Serial.print("\n--- Novo merenje --- CPM: ");
    Serial.println(cpm);

    // Uzimanje tacnog vremena u trenutku merenja
    String current_time = getFormattedTime();

    // Provera da li imamo aktivnu konekciju za slanje
    // u realnom vremenu
    if (WiFi.status() == WL_CONNECTED && client.connected()) {

      // Ako imamo internet, saljemo odmah sa trenutnim vremenom
      String payload =
        "{\"sensor_id\":\"" + String(sensor_id) +
        "\",\"value\":" + String(cpm) +
        ",\"timestamp\":\"" + current_time + "\"}";

      Serial.print("Online rezim. Saljem: ");
      Serial.println(payload);

      if (!client.publish(mqtt_topic, payload.c_str())) {

        Serial.println(
          "Greska pri slanju! Smestam podatak u offline bafer."
        );

        if (offlineBuffer.size() < size_limits_buffer) {
          offlineBuffer.push_back({
            current_time,
            cpm
          });
        }
      }

    } else {

      // OFFLINE REZIM:
      // Internet ili MQTT nije dostupan, cuvamo podatak
      // lokalno u RAM-u
      Serial.println(
        "Offline rezim. Podatak se smesta u bafer."
      );

      if (offlineBuffer.size() < size_limits_buffer) {

        offlineBuffer.push_back({
          current_time,
          cpm
        });

        Serial.printf(
          "U baferu trenutno ima %d zapisa.\n",
          offlineBuffer.size()
        );

      } else {

        Serial.println(
          "Kriticno: Bafer je pun! Najstariji podatak ce biti odbacen."
        );

        offlineBuffer.erase(offlineBuffer.begin());

        offlineBuffer.push_back({
          current_time,
          cpm
        });
      }
    }
  }
}