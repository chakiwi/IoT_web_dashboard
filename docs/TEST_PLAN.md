# Kiểm thử và giới hạn

## Đã chạy trong môi trường phát triển

- FastAPI startup tự tạo SQLite và seed 12 sinh viên, 3 trạm, 24 sự kiện.
- Login và chặn truy cập không có token.
- POST thẻ đăng ký / không đăng ký, retry idempotent và xung đột event ID.
- Thêm/sửa/vô hiệu hóa sinh viên và liên kết thẻ.
- Heartbeat và thống kê thiết bị.
- WebSocket nhận sự kiện mới sau khi commit.

Lệnh: `python -m unittest discover -s tests -v` (dùng `.venv\\Scripts\\python.exe` trên Windows).

## Cần kiểm thử trực tiếp trên máy người dùng

- `setup.bat`: npm install / Vite build trong môi trường có Internet; chưa xác nhận build frontend trong môi trường bàn giao này vì không tải được npm packages.
- Trình duyệt Edge/Chrome xem giao diện, đăng nhập, tạo sinh viên, nhấn mô phỏng, kiểm tra phản hồi và dữ liệu lưu sau restart.
- Windows Firewall và các địa chỉ LAN thật.
- ESP32-S3 CAM: chân SPI trống/nguồn, USB CDC/COM, mode PN532, đầu đọc và tính tương thích của thẻ sinh viên thật.
- Không có đo lường độ ổn định 24/7; chưa test mất điện, ngoại tuyến dài ngày, nhiều trạm concurrent trong thực tế.

## Thử tay trên laptop

1. Đăng nhập, xem danh sách ban đầu.
2. Thêm sinh viên mới và UID hex chưa trùng.
3. Bấm `Mô phỏng lượt quét`, thấy bảng tăng; tải CSV kiểm tra dữ liệu.
4. Dùng `simulator/send_scan.py` gửi cùng `event_id` 2 lần, xác nhận chỉ lưu 1 hàng.
5. Gửi UID `DEADBEEF`, thấy `Thẻ chưa đăng ký`.
6. Tắt `start.bat`, mở lại để xác nhận dữ liệu SQLite vẫn còn.
7. Chuyển `dev.bat` để chỉnh React, kiểm tra Vite proxy và WebSocket tự kết nối lại.
8. Khi có phần cứng, làm bài test USB Serial trước, Wi-Fi sau.
