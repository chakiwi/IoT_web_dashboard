#pragma once
// Example pins only. Verify the exact ESP32-S3 CAM schematic before wiring PN532.
#define PN532_SCK  12
#define PN532_MISO 13
#define PN532_MOSI 11
#define PN532_SS   10
// 0: USB Serial -> simulator/serial_bridge.py; 1: Wi-Fi -> FastAPI HTTP.
#define USE_WIFI_TRANSPORT 0
#if USE_WIFI_TRANSPORT
#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define SERVER_URL "http://192.168.1.10:8000"
#define DEVICE_TOKEN "replace-with-same-DEVICE_TOKEN-from-env"
#endif
