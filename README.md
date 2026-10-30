# Tale of Immortal - Vyyy Mod

## Cài và tự cập nhật

Tải `ChoiGame.bat`, đặt cạnh `guigubahuang.exe`, rồi chạy file này để chơi.

Launcher kiểm tra manifest và DLL từ cùng một commit GitHub, so sánh SHA-256 và chỉ tải DLL khi khác bản đang cài. DLL được xác minh trước khi đặt vào `Mods/ImmortalModSuite.dll`. Bản cũ được sao lưu trong `ModBackups`. Sau đó game tự khởi động.

Khi mất mạng hoặc tải sai hash, giữ bản mod đang cài. Nếu chưa có mod thì dừng và báo lỗi. Hãy đóng game trước khi cập nhật.

Yêu cầu Windows PowerShell 5.1, game và MelonLoader tương thích đã được cài sẵn. Giữ nguyên `UserData` và save game.

## Cấu trúc repo tương ứng thư mục game

```
ChoiGame.bat
mod-manifest.json
Mods/
  ImmortalModSuite.dll
```

Phiên bản hiện tại: 1.7.44. Repo này cung cấp DLL mod tổng hợp; không chứa game, MelonLoader, bộ Việt hóa Villain hoặc ModExportData riêng.