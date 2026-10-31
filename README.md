# Tale of Immortal — Vyyy Mod

DLL **1.7.53**. Toàn bộ `Mods/` và `ModExportData/` được chụp từ máy phát hành ngày 31/10/2026. `mods-files.json` (schema 2) ghi đường dẫn, kích thước và SHA-256 từng file.

## Chơi và tự cập nhật

Tải **PlayGame.bat**, đặt cạnh `guigubahuang.exe`, đóng game rồi chạy. `ChoiGame.bat` và `Update.bat` là các bản tương đương để giữ tên quen thuộc.

Cần tải lại batch mới này một lần để bật đồng bộ Vietnamese UI (launcher cũ chưa cho phép cập nhật file profile).

Launcher mới kiểm tra hash toàn bộ file trong `Mods`, `ModExportData` và file profile Vietnamese UI nêu dưới đây. File đúng hash được bỏ qua. Các file thiếu hoặc khác được tải từ cùng một commit GitHub; khi có trên 8 file thay đổi, tải một archive duy nhất rồi chỉ lấy các file nằm trong manifest. Kiểm tra SHA-256/kích thước trước khi cài.

File cũ được sao lưu theo đường dẫn gốc trong `ModBackups/FullUpdate-*`. Nếu cài lỗi giữa chừng, hoàn tác các file đã thay và không mở game. Mất mạng hoặc manifest/hash không hợp lệ cũng dừng mở game. Sau khi cập nhật thành công, game tự khởi động.

Đồng bộ thêm **`UserData/VietnameseUILayout/profiles.json`**: font mặc định, cỡ chữ, giãn chữ, màu sắc, vị trí/kích thước và các rule UI của máy phát hành. Profile UI cũ của máy nhận được sao lưu trước khi thay. Nếu chỉnh riêng profile trên máy B, lần chạy launcher tiếp theo sẽ đưa về bản đã đăng trên GitHub.

Giữ nguyên các cấu hình `UserData` khác, save và các file riêng không nằm trong manifest. File có cùng đường dẫn được repo quản lý (kể cả `Mods/Villain/config.ini`) sẽ được đồng bộ. Không tự xóa mod/file riêng ở máy nhận; hãy xử lý DLL mod cũ trùng chức năng nếu có.

Yêu cầu game, MelonLoader tương thích và Windows PowerShell 5.1. Launcher không cài MelonLoader hoặc cập nhật asset gốc của game.

## Cài thủ công

Code → Download ZIP, giải nén rồi chép `Mods/`, `ModExportData/` và `UserData/VietnameseUILayout/profiles.json` vào đúng đường dẫn trong thư mục game. Sao lưu bản đang dùng và đóng game trước khi thay file.

## Những thay đổi ngoài hai thư mục này

- `UserData/ImmortalModSuite/`: thiết lập mod riêng từng máy; không đăng.
- `UserData/VietnameseUILayout/profiles.json` đã được đăng và đồng bộ. Các file `.bak`, `selected-ui.json`, `building-name-labels.json`, `adjustments-latest.tsv` chỉ phục vụ backup/dò UI, không đồng bộ.
- `guigubahuang_Data/resources.assets`: máy phát hành từng sửa font/texture trực tiếp. File hiện khác bản sao lưu gốc; chưa phân phối trong repo và launcher không cập nhật file này.
- `ModSources`, `TranslationExports`, `TranslationTools`, `ModBackups`, `outputs`: source, công cụ, kết quả và backup phục vụ phát triển; không cần chép để chạy DLL.

`mod-manifest.json` schema 1 vẫn giữ để launcher cũ đọc được DLL chính; launcher mới dùng `mods-files.json` schema 2.
