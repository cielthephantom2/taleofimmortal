# Dịch bản Việt hóa qua Chat Completions

Công cụ Python chỉ dùng thư viện chuẩn, không cần pip. Cấu hình mặc định xử lý cả 7 JSON trong `Mods/Villain/patch_vh`. Với `LocalText` và `RoleLogLocal`, nguồn là `ch`, đích là `en`; các file có cấu trúc khác dùng trường nguồn gốc tương ứng (`name`, `text`, `desc`) và đích `en`/`descEN`. Không tạo lại `tc`, `kr`; không đổi `ch` hay cấu hình game.

## Chạy

### Rà soát trước lượt dịch chính thức (27/10/2026)

Chạy `run.cmd audit` để quét lại LocalText, đối chiếu nguồn ch với base, kiểm tra toàn bộ bản dịch dùng thẳng, và xuất `TranslationExports/TerminologyPreflight/audit.json`. Lệnh này không gọi API và không sửa file game. Mã thoát 2 cho biết có lỗi cấu trúc/nguồn/ràng buộc cần xử lý trước.

Lượt rà soát này đã đọc 55.205 dòng. Glossary hiện có 874 quy tắc; các bảng 6.228 mảnh tên, 3.265 tên vật phẩm và 5.033 tên kỹ năng/khí vận vẫn được nạp riêng. Danh sách nguồn bổ sung có biên tập nằm trong `game_terms_reviewed.tsv`; chỉ các cụm thực sự xuất hiện trong LocalText mới được nhập. Các mục bổ sung được lưu trong danh sách đồng bộ chính `TranslationExports/danh_sach_dong_bo.json`, rồi nhập vào glossary bằng `import_glossary.py`.

Tên đã duyệt được nhận diện trong mô tả/hội thoại: tên có trích dẫn được khóa khi bản dịch nguồn chỉ có một nghĩa; tên có thể là thành ngữ thông thường chỉ được đưa làm hướng dẫn theo ngữ cảnh. Mảnh ghép một chữ không được áp vào văn xuôi. Năm nguồn tên có nhiều bản dịch được ghi vào báo cáo, không tự gộp thành một bản dịch toàn cục. Danh sách chỉ thị đi kèm từng dòng dùng đúng các thuật ngữ tìm được trong nguồn, không gửi toàn bộ bảng tên trong mọi request.

`approved_format_exceptions.json` lưu 93 ngoại lệ đã đối chiếu theo file/key/nguồn/đích: số quyển/phần từ chữ Hán sang số Ả Rập và ba tên kỹ thuật chỉ khác khoảng trắng cạnh dấu số. Ngoại lệ chỉ chấp nhận đúng chuỗi đích đã duyệt; không nới kiểm tra biến, mã màu, số liệu ở các mục khác. File này cũng được liên kết trong danh sách đồng bộ.

Các thuật ngữ đa nghĩa được phân biệt `strict` và hướng dẫn theo ngữ cảnh; thuật ngữ ngắn không được ép thay bản tên đầy đủ chứa nó. Kiểm tra các mục được lấy thẳng từ danh sách trước khi gọi API giúp tránh dịch trả phí rồi mới phát hiện lỗi ở bản tên đã duyệt. Bộ dò Aho–Corasick giảm chi phí quét khi bảng thuật ngữ tăng.

Đây là rà soát nguồn, thuật ngữ và cấu trúc, không phải chứng nhận mọi câu tiếng Việt hiện tại đã đúng nghĩa. Báo cáo còn ghi các dòng en cũ có chữ Hán và khác biệt token/số để đối chiếu khi dịch mới. Không ghép lại bản phân loại cũ sau khi dịch file game.

Mở CMD trong thư mục này. `run.cmd` tự dùng Python có sẵn trên máy; máy khác có thể gọi `python translate.py ...`.

```bat
REM Xem khối lượng, hoàn toàn không gọi API và không sửa JSON.
run.cmd plan

REM Tùy chọn: ghi đè khóa trong credentials.local.json cho cửa sổ CMD hiện tại.
set "TRANSLATOR_API_KEY=DAN_KHOA_CUA_BAN_VAO_DAY"

REM Dịch 200 mục đầu để tự xem chất lượng. Lần chạy sau tiếp tục dùng tiến độ này.
run.cmd run 200

REM Dịch toàn bộ, hoặc tiếp tục sau khi ngắt/lỗi.
run.cmd run

REM Xem tiến độ / ghi lại kết quả đã lưu: không gọi API, không cần khóa.
run.cmd status
run.cmd apply
```

URL và model đã lấy từ `D:\test.py`; khóa được lưu riêng trong `credentials.local.json` (đã thêm vào `.gitignore`). Biến `TRANSLATOR_API_KEY` được ưu tiên nếu đã đặt. Không đưa khóa vào nhật ký hoặc commit file khóa. Chỉ lệnh `run` gọi API có tính phí. Công cụ không tự mở game. Nên đóng game khi dịch hàng loạt để tránh cơ chế hot reload cập nhật liên tục khi file đang được thay đổi.

Lệnh `run` ghi bản dịch trực tiếp vào các JSON game trong cấu hình; không cần chạy `apply` sau mỗi batch. `apply` chỉ dùng khi muốn áp lại kết quả đã có trong tiến độ mà không gọi API. `run.cmd run 200` chọn 200 trường đầu trong phạm vi đang cấu hình, không bảo đảm có 200 mục gọi API: tên đã duyệt được lấy thẳng từ danh sách đồng bộ. Chạy lại cùng giới hạn không chọn 200 mục tiếp theo; bỏ giới hạn để tiếp tục toàn bộ.

Để chỉ dịch LocalText, giữ riêng phần tử có path `Mods/Villain/patch_vh/LocalText.json` trong mảng `files`. Để thử hội thoại, thêm `"include_key_globs": ["drama_dialogue*"]` vào phần tử đó rồi chạy `run 200`; bỏ bộ lọc sau khi duyệt. Có thể sao lưu config trước khi đổi phạm vi. Đổi phạm vi/batch/số luồng vẫn dùng chung tiến độ, không cần xóa state.

Các file `TranslationExports/LocalText_PhanLoai` hiện là bản xuất riêng: công cụ không tự cập nhật chúng sau khi dịch file game. Không ghép đè bản phân loại cũ lên LocalText mới; cần xuất lại hoặc đối chiếu các chỉnh sửa thủ công trước.

## Config

| Trường | Tác dụng |
|---|---|
| `base_url` | URL gốc API gồm `/v1`, lấy từ `test.py`; công cụ nối thêm `/chat/completions`. Cập nhật nếu địa chỉ tunnel thay đổi. |
| `model` | ID model lấy từ `test.py`: `ag/gemini-3.8-flash-low(low)`. |
| `api_key_env` / `api_key_file` | Ưu tiên biến `TRANSLATOR_API_KEY`, sau đó đọc trường `api_key` trong `credentials.local.json`. |
| `batch_size` | Từ **1 đến 1000 mục** mỗi request; hiện đặt 25 để giảm thời gian phản hồi qua gateway. Một mục là một trường nguồn/đích, không phải một dòng vật lý trong JSON. |
| `max_source_characters_per_batch` | Giới hạn thêm theo tổng độ dài; hiện đặt 6000 ký tự. |
| `parallel_requests` | Số request chạy song song; hiện đặt 2. |
| `requests_per_minute` | Giới hạn tổng số lần gọi/phút, bao gồm retry; mặc định 10. `0` tắt giới hạn này. Cần chỉnh theo quota thực tế. |
| `max_output_tokens` | Trần đầu ra một request; mặc định 32768. |
| `http_retries` | Retry lỗi mạng, 408, 429 và một số 5xx; có backoff dùng chung giữa các luồng. |
| `validation_retries` | Gửi lại riêng key thiếu/sai định dạng; tự chia batch lỗi nhỏ hơn. |
| `preserve_target_edge_whitespace` | Giữ khoảng trắng đầu/cuối của bản Việt hiện tại, gồm khoảng trắng sửa tên trấn, cảnh giới. |
| `deduplicate_within_context` | Tái dùng văn bản giống hệt trong cùng nhóm key và metadata ngữ cảnh. Không gộp chỉ vì giống chữ giữa những ngữ cảnh khác nhau. |
| `generation_overrides` | Tham số bổ sung ở cấp payload Chat Completions (ví dụ `top_p`); không dùng tên tham số Gemini cũ. `model`, `messages`, `stream` do công cụ quản lý. Schema JSON được gửi qua prompt và kiểm tra tại máy. |
| `files` | Danh sách file và mapping nguồn → đích; bỏ bớt file ở đây để chỉ dịch `LocalText`. |

Trong từng phần tử `files`, có thể thêm `include_key_globs` hoặc `exclude_key_globs`. Ví dụ `"include_key_globs": ["player_*", "drama_dialogue610*"]` để duyệt thử chỉ số và một nhóm hội thoại; `"exclude_key_globs": ["startGameTipDesc*"]` để chưa dịch lịch sử cập nhật. Bỏ bộ lọc khi muốn dịch toàn bộ; các mục đã xong vẫn được tái sử dụng.

Batch cuối, batch bị giới hạn ký tự và batch retry có thể ít hơn 100 mục. Chuỗi đơn dài hơn trần ký tự sẽ đi riêng, không bị cắt mất nội dung; nếu vẫn vượt đầu ra của model, nó được đưa vào báo cáo lỗi để xử lý riêng.

## Chống lạc dòng và hỏng định dạng

- Mỗi mục gửi cả định danh duy nhất `[file, id, game_key, target_field]` và key gốc để model hiểu ngữ cảnh. Ghép kết quả bằng định danh, không dựa vào thứ tự trả về.
- Bảo vệ biến `{0}`, macro `&...&`, `|...|`, thẻ rich text, số liệu, xuống dòng và các escape. Bản dịch làm mất, thêm hoặc đảo token sẽ không được ghi.
- Yêu cầu JSON theo schema trong prompt và kiểm tra khi nhận phản hồi; phát hiện key thiếu, trùng hoặc không tồn tại. Các mục hợp lệ được giữ, chỉ mục lỗi cần dịch lại.
- Không gửi bản Việt cũ vào prompt để tránh nó dẫn dắt model theo bản dịch kém. Giữ văn phong qua `style.txt` và thuật ngữ đã duyệt.
- Bản dịch còn chữ Hán sẽ bị từ chối mặc định. Khi cần giữ nguyên một thuật ngữ chữ Hán có chủ đích, cần sửa quy tắc bảo vệ hoặc chính sách cho phù hợp.
- Những kiểm tra này bảo vệ cấu trúc, **không chứng minh bản dịch đúng nghĩa**. Người dùng vẫn cần duyệt chất lượng.

## Lưu tiến độ và tiết kiệm token

`state/progress.sqlite3` lưu kết quả theo **key + hash nguồn + chính sách dịch**. Bản dịch được lưu ngay khi phản hồi được xác thực; mỗi batch hoàn tất sẽ cập nhật JSON game bằng file tạm rồi thay thế file gốc. Các batch lỗi không làm mất kết quả đã dịch được.

`state/journal` lưu nguyên phản hồi API trước bước xử lý. Nếu ứng dụng bị ngắt sau khi nhận và lưu phản hồi nhưng chưa cập nhật SQLite, lần chạy sau khôi phục từ đây. Cơ sở dữ liệu dùng WAL và một khóa phiên để tránh hai chương trình sửa cùng tiến độ.

`state/backups/<phiên>/` giữ file trước lần ghi đầu tiên của phiên. `state/report.json` liệt kê key chưa dịch, lỗi, xung đột chỉnh sửa và usage token API đã ghi nhận. Không xóa `state` khi muốn tiếp tục. Sau lần chạy đầu, đổi thứ tự file hoặc batch không làm dịch lại các key đã xong.

Thay đổi nguồn, model hoặc văn phong sẽ tạo bản dịch mới cho những mục liên quan. Đổi batch hoặc số luồng không xóa cache. Sửa một thuật ngữ chỉ làm mất hiệu lực những mục có áp dụng thuật ngữ đó. Thuật ngữ khớp toàn bộ nguồn dùng thẳng bản đã duyệt, không tốn API.

Giữ nguyên cả thư mục `state` khi sao lưu/di chuyển. Nếu mất điện đúng lúc máy chủ đã xử lý nhưng máy chưa nhận/lưu phản hồi, không thể bảo đảm tránh một lần gọi lại có thể tính phí: endpoint này không cung cấp cơ chế chống tính phí lặp theo checkpoint cục bộ.

Trong khi chạy, nếu bạn sửa `en` bằng tay, công cụ sẽ không đè lên phần thay đổi phát hiện được; nó ghi xung đột. Nếu `ch` thay đổi, kết quả nguồn cũ không được áp vào nguồn mới. Hãy xem báo cáo; công cụ không tự giải quyết thay người dùng các xung đột đó.

Trước khi ghi, công cụ kiểm tra cả id, key và nguồn. Rà soát ngày 27/10/2026 đã bổ sung chặn trường hợp key bị đổi trong lúc dịch; chạy `plan` xác nhận cấu hình đọc được 85.724 trường/7 file, trong đó 14.251 mục thuộc bản duyệt hoặc không chứa chữ Hán. Chưa xác minh bằng request API thực tế trong đợt rà soát này.

`Ctrl+C` ngừng xếp request mới và chờ request đang chạy lưu kết quả. Có thể phải chờ đến timeout mạng. Chạy lại cùng lệnh để tiếp tục.

## Danh sách đồng bộ, đa nghĩa và ngữ cảnh

`skill_fate_names_file` trỏ đến `TranslationExports/skills_fates_review/approved_names.json`: 5.033 tên kỹ năng, công pháp, khí vận trong nhóm phân loại 03/04. Công cụ dùng tên đã duyệt theo key/ch, không gọi API dịch lại. Các trường “name” thực chất chứa cả đoạn mô tả được loại khỏi danh sách khóa tên. Báo cáo và danh sách loại riêng nằm trong cùng thư mục.

`item_names_file` trỏ đến `TranslationExports/item_names_review/approved_item_names.json`: **3.265 tên vật phẩm** đã rà và lưu theo key/nguồn Trung. Công cụ dùng trực tiếp tên đã duyệt, không gọi API để dịch lại. Nếu nguồn `ch` đổi thì dừng để rà tên mới. Danh sách này được liên kết từ `TranslationExports/danh_sach_dong_bo.json`. Chỉ khóa tên theo key, không thay mù một từ trong mọi hội thoại.

`name_fragments.json` khóa riêng **6.228 mảnh/tên** đã duyệt theo file/id/key: họ, tên, địa danh, tông môn và công pháp. Các mục này bắt buộc Hán–Việt, dùng thẳng bản duyệt và không gọi API. Nếu nguồn Trung của một mục đã khóa thay đổi, công cụ dừng để yêu cầu rà lại âm đọc. Khoảng trắng ghép tên được lấy từ trường tiếng Việt hiện tại. Không áp các âm đọc này bằng find/replace vào câu hội thoại. Có thêm bảng `HerdNPCNameFirst.json` cho tiền tố tên yêu thú.

`glossary.json` hiện có 874 quy tắc: 873 mục nhập từ `TranslationExports/danh_sach_dong_bo.json` và một quy tắc tùy chỉnh cho hệ Phong. Trong đó giữ đủ 321 mục đã duyệt ban đầu, bao gồm **Tiên thiên khí vận**. Đây là danh sách công cụ sử dụng. Khi cập nhật danh sách đồng bộ bên ngoài, chạy `python import_glossary.py` để nhập lại; các mục tùy chỉnh không có tiền tố `import:` được giữ.

Mỗi quy tắc có `source`, `vi`, `variants`, `note`. Thêm `files` và/hoặc `key_globs` để xác định nghĩa theo ngữ cảnh. Quy tắc chuyên biệt ghi đè quy tắc toàn cục của cùng nguồn. Hai quy tắc khớp toàn bộ nguồn nhưng cho hai đích khác nhau sẽ dừng trước khi tốn token. `strict: true` bắt buộc kết quả có nguyên tên tiếng Việt đã duyệt; 213 tên khí vận được bật mặc định. Nhãn thông thường không bật kiểm tra cứng này để tránh ép sai ngữ pháp của động từ trong câu.

Xem `glossary.examples.json` cho ví dụ **攻击 → Công kích** khi là nhãn chỉ số, **攻击 → tấn công** khi là động từ trong hội thoại. File ví dụ không tự nạp; chỉ thêm quy tắc muốn áp dụng vào `glossary.json`.

Thuật ngữ xuất hiện trong câu được đưa làm hướng dẫn cho model; không dùng find/replace mù để ép từ bất chấp ngữ pháp. Đừng thêm tự động mọi đề xuất của model vào glossary: cần duyệt nghĩa trước, nhất là các từ đa nghĩa và tên riêng.

## Nên tối ưu thêm

1. **Duyệt một mẫu phân tầng trước khi dịch cả game:** tên riêng, mô tả kỹ năng, hội thoại, hướng dẫn, nhật ký. 200 dòng đầu liên tiếp không đại diện cho cả game; có thể tạm chọn file/key để duyệt từng nhóm.
2. **Tách dịch và biên tập:** dùng model nhanh cho phần lặp và nhãn; model chất lượng cao cho cốt truyện/tên công pháp. Có thể tạo config khác, lọc file/nhóm mục trước khi chạy; bộ định tuyến model theo từng nhóm chưa được tự động hóa.
3. **Thêm ngân sách RPM/TPM và chi phí:** hiện đã có RPM, concurrency, usage và giới hạn ký tự; chưa có bộ giới hạn TPM hoặc trần tiền tự động. Cần giá đúng của model để tính tiền, không ước lượng theo số dòng.
4. **Bổ sung quan hệ nhân vật:** key giúp nhận diện loại câu, chưa đủ xác định ai nói với ai. Nên ghép dữ liệu DramaDialogue/NPC để cung cấp vai vế và chủ thể trước khi biên tập hội thoại khó.
5. **Kiểm tra độ dài giao diện và mảnh ghép tên:** bảo toàn khoảng trắng không tự bảo đảm vừa khung. Cần danh sách nhãn dài, viết tắt có duyệt và kiểm tra trực tiếp trong game.
6. **Dịch bất đồng bộ với Batch API** khi không cần có kết quả ngay: cần backend riêng để gửi job và lấy kết quả; công cụ hiện dùng request trực tiếp chạy song song, chưa tích hợp Batch API.

Tài liệu API đã đối chiếu khi viết công cụ:

- https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash

## Giảm lỗi phải dịch lại

Cấu hình hiện dùng lô tối đa 25 mục / 6000 ký tự nguồn và 2 yêu cầu đồng thời. Mục có nhiều mã bảo vệ hoặc đã lỗi định dạng được dịch theo mảng đoạn chữ; chương trình tự chèn lại mã giữ chỗ theo đúng thứ tự. Mọi kiểm tra mã game, số liệu, xuống dòng và thuật ngữ vẫn áp dụng. Không xóa state: các mục hợp lệ đã lưu tiếp tục được dùng lại. Đổi kích thước lô và cơ chế sửa định dạng không làm mất tiến độ.

## Kiểm tra và hiệu năng

Xem `CODE_REVIEW.md`, `code_review_metrics.json` và `code_review_preview.json` để đọc kết quả rà soát. Dùng `python -X utf8 -m unittest discover -s . -p test_translate.py -v` trong thư mục công cụ để chạy bộ kiểm tra không gọi API. Báo cáo chi tiết tiến độ được ghi mỗi 30 giây và khi dừng; bản dịch và phản hồi API vẫn được lưu sau từng lô. Trường `approved_names_with_chinese` liệt kê tên hiếm đang được bảng duyệt cho giữ nguyên chữ Hán.

## Chạy tiếp và hoãn lỗi (cấu hình hiện tại)

- `http_retries = 0`, `validation_retries = 0`: mỗi lô gọi API một lần; lỗi mạng hoặc kiểm tra bản dịch thất bại thì lưu lỗi và chuyển lô tiếp theo.
- `defer_failed_items = true`: `run.cmd run` không gửi lại các mục lỗi đã lưu. Các bản dịch hợp lệ vẫn được giữ; mục lỗi có thể được lấy từ bản tên duyệt/bộ nhớ hợp lệ mà không gọi API.
- Lỗi được lưu ngay vào SQLite; danh sách `state/failed_items.json` được cập nhật cùng báo cáo định kỳ và khi dừng. Danh sách chứa file, game_key, nguồn ch và lý do lỗi.
- Dùng `run.cmd retry` khi muốn xử lý riêng các mục lỗi; lệnh này không gửi những mục chưa từng thử. Mỗi mục vẫn chỉ thử một lần trong lượt chạy vì retry tự động đã tắt.
- Changelog, roadmap, khảo sát, credit/lời cảm ơn và thông báo cuộc thi MOD đã được loại qua `exclude_key_globs` của LocalText. Danh sách 588 mục, tương đương 175.016 ký tự nguồn, nằm trong `excluded_outside_game.json`. Đây là loại khỏi phạm vi dịch, không xóa dòng hay sửa nguồn game.
- Lỗi xác thực/quyền truy cập/model không hợp lệ vẫn dừng phiên để kiểm tra cấu hình.

```bat
run.cmd run
REM Xử lý phần lỗi khi bạn muốn:
run.cmd retry
```
