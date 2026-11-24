#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_PN532.h>
#include <esp_system.h>
#include "config.h"
#if USE_WIFI_TRANSPORT
#include <WiFi.h>
#include <HTTPClient.h>
#endif

Adafruit_PN532 nfc(PN532_SS, &SPI);
struct Pending { String eventId; String uid; String json; };
Pending queueItems[12];
int head=0, count=0;
uint32_t sequenceNo=0;
uint32_t bootId=0;
String lastUid="";
unsigned long lastScanAt=0, lastSendAt=0, lastHeartbeatAt=0;

String uidHex(const uint8_t* uid, uint8_t len) {
  String result="";
  const char* hex="0123456789ABCDEF";
  for (int i=0;i<len;i++) { result += hex[uid[i]>>4]; result += hex[uid[i]&15]; }
  return result;
}

void pushScan(const String &uid) {
  if (count==12) { Serial.println("QUEUE FULL (scan not saved)"); return; }
  String eventId=String(bootId,HEX)+"-"+String(++sequenceNo);
  String json="{\"type\":\"scan\",\"event_id\":\""+eventId+"\",\"card_uid\":\""+uid+"\"}";
  queueItems[(head+count)%12]={eventId,uid,json};
  count++;
}

#if USE_WIFI_TRANSPORT
bool postJson(String route, const String& json) {
  if (WiFi.status()!=WL_CONNECTED) return false;
  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client,String(SERVER_URL)+route))return false;
  http.addHeader("Content-Type","application/json");
  http.addHeader("X-Device-Token",DEVICE_TOKEN);
  http.setTimeout(3500);
  int code=http.POST(json);
  http.end();
  return code>=200 && code<300;
}
#endif

void processQueue() {
  if (count==0 || millis()-lastSendAt<1800)return;
  lastSendAt=millis();
  Pending &event=queueItems[head];
#if USE_WIFI_TRANSPORT
  if(postJson("/api/v1/scans",event.json)) { head=(head+1)%12;count--; }
#else
  // Serial bridge sends ACK only after FastAPI has saved this event.
  Serial.println(event.json);
#endif
}

void receiveAck() {
#if !USE_WIFI_TRANSPORT
  static String buffer="";
  while (Serial.available()) {
    char c=Serial.read();
    if (c=='\n') {
      buffer.trim();
      if (count>0 && buffer=="ACK "+queueItems[head].eventId) {
        head=(head+1)%12;count--;
      }
      buffer="";
    } else if (buffer.length()<120) buffer+=c;
  }
#endif
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  bootId=esp_random();
#if USE_WIFI_TRANSPORT
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  Serial.println("Connecting Wi-Fi...");
#endif
  SPI.begin(PN532_SCK,PN532_MISO,PN532_MOSI,PN532_SS);
  nfc.begin();
  uint32_t version=nfc.getFirmwareVersion();
  if (!version) { Serial.println("PN532 NOT FOUND. Check SPI mode, wiring, power."); }
  else { nfc.SAMConfig(); Serial.println("PN532 ready"); }
}

void loop() {
  receiveAck();
  // The PN532 returns UID only for supported cards; ISO 14443-A alone
  // does not guarantee an identifiable stable UID on a bank-linked card.
  uint8_t uid[10],uidLength=0;
  if(nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A,uid,&uidLength,150)) {
    String value=uidHex(uid,uidLength);
    if (value!=lastUid || millis()-lastScanAt>2500) {
      lastUid=value;lastScanAt=millis();pushScan(value);
    }
  }
  processQueue();

  delay(20);
}
