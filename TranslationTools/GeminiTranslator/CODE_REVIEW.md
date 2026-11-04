# Kết quả rà soát bộ dịch

- Đã kiểm tra luồng gửi API, ghép đoạn, bảo vệ mã, lưu SQLite, sao lưu JSON, dừng và tiếp tục.
- 22 bài kiểm tra tự động đạt; không gọi API trong bộ kiểm tra.
- Quét 40,728 kết quả đã lưu theo nguồn/chính sách hiện tại: 0 lỗi cấu trúc, mã hoặc ràng buộc thuật ngữ.
- Rà 55,205 dòng LocalText: không khác nguồn gốc; 0 lỗi ở 15,438 mục lấy thẳng từ nguồn/bảng duyệt.
- Đọc tiến độ cho 25 mục: 129.8 ms trước, 1.5 ms sau. Đây là tốc độ truy vấn cục bộ, không phải tốc độ dịch toàn bộ.
- SQLite đóng kết nối sau mỗi giao dịch; tra cứu theo khóa nguồn/chính sách. Giảm dữ liệu thuật ngữ dư, chỉ ghi báo cáo đầy đủ mỗi 30 giây và khi dừng.
- Không trộn nhiều file game trong cùng lô. Các mục có mã phức tạp được cung cấp nguyên câu nguồn và chỉ dẫn ngữ pháp khi dịch theo đoạn.
- Thử API thật trên 5 mục từng lỗi: 5/5 hợp lệ, khoảng 8,7 giây. Đọc lại mẫu đã sửa lỗi địa danh bị hiểu như vật phẩm, quan hệ trong/ngoài và khoảng trắng. Kết quả thử chỉ lưu ở code_review_preview.json.
- Tên hiếm 琒 (NpcNameLast.json, ID 603) đang được bảng tên duyệt cho giữ nguyên. Công cụ giữ quyết định này và liệt kê riêng trong report.json; không tự đoán âm Hán–Việt.
- Kiểm tra cấu trúc không chứng minh mọi câu đúng nghĩa. Những bản dịch đã lưu không bị dịch lại chỉ vì sửa hiệu năng/prompt.

## Chạy lại trong CMD

Nếu đang dịch, nhấn Ctrl+C và chờ dừng hẳn, rồi nhập:

```bat
run.cmd run
```

Giữ nguyên thư mục state. Không ghi đè file game trong lần rà soát này.
