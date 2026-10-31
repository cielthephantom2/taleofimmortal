# Tale of Immortal — Vyyy Mod

Phiên bản DLL hiện tại: **1.7.53**. Repo chứa toàn bộ thư mục `Mods` được chụp từ máy phát hành ngày 31/10/2026, gồm DLL, font và bộ dữ liệu/Việt hóa Villain. Danh sách file, kích thước và SHA-256 nằm trong `mods-files.json`.

## Cài bộ Mods đầy đủ

Tải repo bằng Code → Download ZIP, giải nén rồi chép thư mục `Mods` vào thư mục game cạnh `guigubahuang.exe`. Đóng game trước khi thay file. Sao lưu thư mục Mods đang dùng; không giữ song song các DLL mod độc lập cũ có chức năng trùng DLL tổng hợp.

Cần có game và MelonLoader tương thích cài sẵn. Không chép đè UserData hoặc save của máy nhận.

## Script cập nhật DLL

Đặt `ChoiGame.bat` cạnh `guigubahuang.exe`. Script kiểm tra phiên bản theo commit, SHA-256, sao lưu DLL cũ rồi khởi động game.

**Script hiện chỉ cập nhật `Mods/ImmortalModSuite.dll`, chưa đồng bộ toàn bộ thư mục Mods.** Lần cài đủ font và Việt hóa hãy chép thư mục Mods từ repo. `mod-manifest.json` vẫn dùng schema 1 để tương thích script hiện có.

## Những phần máy phát hành đã chỉnh ngoài Mods

- `ModExportData/Mod_nYOYTQ/`: dữ liệu mod xuất từ ModProject, có các thay đổi bảng dữ liệu riêng. Chưa có trong repo này.
- `UserData/ImmortalModSuite/` và `UserData/VietnameseUILayout/`: thiết lập từng máy, font và bố cục UI. Không đăng để giữ thiết lập riêng của máy nhận. DLL có cấu hình mặc định nhúng sẵn.
- `guigubahuang_Data/resources.assets`: từng có công việc chỉnh font/asset trực tiếp, có bản sao lưu DirectFont. Repo này không phân phối asset game đó; chép Mods không tái tạo thay đổi asset ngoài Mods.
- Các script ở thư mục game (`Update.bat` trên máy phát hành, `ChoiGame.bat` trong repo).
- `ModSources`, `TranslationExports`, `TranslationTools`, `ModBackups`, `outputs`: source, công cụ, kết quả và backup phục vụ phát triển; không phải các file phải chép để chạy DLL.

Repo này là bản chụp đầy đủ **Mods**, không phải toàn bộ bản game đã chỉnh sửa hoặc bộ cài MelonLoader.
