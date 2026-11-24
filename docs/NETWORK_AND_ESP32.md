# Thiết lập vận hành: Laptop — ESP32 — PN532

## Phương án 1: USB Serial, không dùng Wi-Fi

- ESP32 cắm USB vào laptop; có cổng COM (ví dụ COM5).
- Firmware đọc thẻ qua PN532 SPI, tạo JSON với `event_id`, `station_id`, `card_uid`, in thành **một dòng Serial**.
- Python `simulator/serial_bridge.py --port COM5` giữ cổng COM, đọc từng dòng. Nếu JSON có `type=scan` thì gửi HTTP POST **trên localhost** đến `http://127.0.0.1:8000/api/v1/scans` kèm `X-Device-Token` lấy từ `.env`.
- FastAPI kiểm tra token và mã trạm, tra `nfc_cards`, ghi `scan_events` trong SQLite, trả kết quả.
- Bridge gửi `ACK <event_id>` về ESP32 chỉ khi server đã chấp nhận.
- FastAPI phát WebSocket, React gọi GET cập nhật danh sách.

**Không cần Internet, router hay Wi-Fi.** Dây USB vừa dùng cấp nguồn (nếu đáp ứng nguồn) vừa truyền dữ liệu. Trên board S3-CAM, cấu hình USB CDC/UART phải tương ứng với cổng USB thực tế.

## Phương án 2: Wi-Fi LAN, không cần Internet

| Thành phần | Ví dụ | Nhiệm vụ |
|---|---|---|
| Router | 192.168.1.1 | Cấp IP nội bộ, chuyển lưu lượng LAN |
| Laptop | 192.168.1.10 | Chạy FastAPI `0.0.0.0:8000`, SQLite, React build |
| ESP32 | 192.168.1.20 | Gửi POST đến địa chỉ laptop |
| Điện thoại khác | 192.168.1.30 | Mở Dashboard nếu cùng LAN và đăng nhập |

IP chỉ minh họa. Chạy `ipconfig` để xác định IP laptop thực; có thể dùng DHCP reservation trên router để cố định IP server.

### Từng bước

1. Trên laptop, kết nối Wi-Fi/router cục bộ, hoặc dùng hotspot nếu mạng cho phép ESP32 và laptop liên hệ. Router không cần có Internet.
2. Sửa `.env`: thay mọi credential demo và `APP_SECRET`. **Không bật start-lan nếu chưa sửa**.
3. Chạy `start-lan.bat`. Kiểm tra trên laptop `http://127.0.0.1:8000/api/v1/health` trả `status:ok`.
4. Cho phép Windows Firewall truy cập port TCP 8000 từ mạng **Private**. Đảm bảo router không bật Client/AP Isolation.
5. Trên ESP32 `USE_WIFI_TRANSPORT=1`, điền `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_URL` trỏ tới **IP laptop**, không phải `localhost`, và `DEVICE_TOKEN` giống `.env`.
6. Khi ESP32 khởi động, nó kết nối Wi-Fi. Mỗi lần PN532 đọc thẻ, firmware gửi HTTP POST `...:8000/api/v1/scans` và nhận JSON xác nhận. Firmware gửi heartbeat định kỳ để tab Thiết bị hiện Online.
7. Bất kỳ trình duyệt nào cùng mạng mở `http://IP_LAPTOP:8000` và đăng nhập bằng mật khẩu trong `.env`.

**Không** bật Port Forwarding, DDNS hay public IP. HTTP chưa mã hóa phù hợp chỉ với LAN lab được kiểm soát; nếu triển khai thực tế nên dùng TLS, quản lý thiết bị và kiểm toán truy cập.

## Payload chung

```json
{
  "event_id": "STATION_A-1234567-1",
  "station_id": "STATION_A",
  "card_uid": "A1B200000001"
}
```

Headers với Wi-Fi: `Content-Type: application/json`, `X-Device-Token: <secret>`.

Thẻ có thể trả UID 4, 7, 10 byte tùy công nghệ. UID chỉ là mã quan sát; không mặc nhiên là thông tin danh tính đáng tin cậy. Thẻ ngân hàng/contactless có thể không cho mã ổn định.

## Phần cứng quan trọng

- PN532 đỏ V3 cần được cấu hình **SPI mode** (thường bằng switch trên module, phải đối chiếu đúng phiên bản người bán).
- Các chân SCK/MISO/MOSI/SS ở `firmware/include/config.h` **là chân ví dụ**. Board ESP32-S3 CAM OV3660 có thể chiếm GPIO khác nhau; chờ sơ đồ pin xác nhận rồi mới đấu.
- Nguồn cấp PN532 theo chính xác datasheet của board; logic ESP32-S3 3,3 V, tránh đưa tín hiệu 5 V trực tiếp vào GPIO.
- Nếu USB Serial bridge sử dụng COM5, tắt Arduino Monitor/ứng dụng khác đang chiếm COM5.
- Mỗi trạm có `station_id` và thiết bị token riêng. Thêm trạm vào dashboard chưa đủ: bổ sung token trên laptop và firmware.

## Cách phân biệt lỗi

| Dấu hiệu | Kiểm tra |
|---|---|
| Browser localhost:8000 không vào được | `start.bat` còn chạy? port 8000 bị chiếm? |
| Laptop vào được, ESP32 Wi-Fi không gửi được | IP laptop đúng? firewall Private? chung mạng, không bật isolation? |
| HTTP 401 | Kiểm tra `DEVICE_TOKEN_STATION_A` và `X-Device-Token` |
| HTTP 400 | UID sai định dạng hoặc trạm chưa được bật |
| HTTP 409 | `event_id` tái sử dụng với UID/trạm khác |
| COM5 không mở được | Đúng COM? Dùng cáp dữ liệu? Arduino Monitor đang chiếm COM? |
| Dashboard không cập nhật | Kiểm tra API, Network tab, WS `/ws/events`, Reload, token login |
| Thẻ không nhận | Kiểm tra loại thẻ ISO14443-A, SPI mode, dây PN532 và nguồn |
