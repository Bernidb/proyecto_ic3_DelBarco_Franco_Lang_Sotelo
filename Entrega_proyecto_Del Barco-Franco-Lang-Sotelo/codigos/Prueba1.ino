#include <WiFi.h>
#include <PubSubClient.h>

// ---- CONFIGURACIÓN WIFI ----
const char* ssid = "---";
const char* password = "---";

// ---- CONFIGURACIÓN MQTT ----
const char* mqtt_server = "---";  // IP de tu Raspberry
const int mqtt_port = 1883;
const char* habitacion = "---";            // ID de cerradura/habitación
String token = "---";          // token que generaste en la web

WiFiClient espClient;
PubSubClient client(espClient);

// ---- PINES (ajustar según tu hardware) ----
const int ledVerde = 2;
const int ledRojo = 4;
const int relay = 5;

void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  Serial.print("MQTT mensaje en ");
  Serial.print(topic);
  Serial.print(": ");
  Serial.println(msg);

  if (msg == "aprobado") {
    digitalWrite(ledVerde, HIGH);
    digitalWrite(ledRojo, LOW);
    digitalWrite(relay, HIGH);   // activa la cerradura
    delay(5000);
    digitalWrite(relay, LOW);
    digitalWrite(ledVerde, LOW);
  } else if (msg == "rechazado") {
    digitalWrite(ledRojo, HIGH);
    delay(2000);
    digitalWrite(ledRojo, LOW);
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando MQTT...");
    //    String clientId = "ESP32Client-" + String(random(0xffff), HEX);
    //    if (client.connect(clientId.c_str())) {
    if (client.connect("ESP32_46")) {
      Serial.println("Conectado");
      String topicEstado = String("locknet/") + habitacion + "/estado";
      client.subscribe(topicEstado.c_str());
    } else {
      Serial.print("Error, rc=");
      Serial.print(client.state());
      Serial.println(" reintentando en 5s");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(ledVerde, OUTPUT);
  pinMode(ledRojo, OUTPUT);
  pinMode(relay, OUTPUT);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi conectado, IP: " + WiFi.localIP().toString());

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // ---- SIMULAR validación cada 15s ----
  static unsigned long last = 0;
  if (millis() - last > 15000) {
    last = millis();
    String topicValidacion = String("locknet/") + habitacion + "/validacion";
    client.publish(topicValidacion.c_str(), token.c_str());
    Serial.println("Enviado token: " + token);
  }
}