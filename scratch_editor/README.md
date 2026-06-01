# Scratch Editor – Công cụ chỉnh sửa dự án Scratch (.sb3) cho giáo viên

Một phần mềm desktop bằng Python để giáo viên **chỉnh sửa, kiểm tra và đóng gói**
dự án Scratch 3 (.sb3) dùng cho thi/giảng dạy. Giao diện tiếng Việt, không cần
cài Scratch Desktop để chạy phần mềm này – file xuất ra sẽ mở được bằng
Scratch Desktop / scratch.mit.edu.

## Tính năng

- Mở file `.sb3` an toàn (file gốc **không bao giờ** bị sửa; toàn bộ thao tác
  diễn ra trong `workspace/temp/...`).
- Đọc và hiển thị: Stage, danh sách backdrop, sprite, biến, list, broadcast, asset.
- **Sân khấu trực quan 480×360**: hiển thị backdrop + sprite theo đúng toạ độ
  Scratch, kéo–thả sprite để chỉnh `x, y`.
- Thay ảnh nền / costume sprite bằng **ảnh chất lượng cao**: tự scale, đặt tâm
  xoay, dùng `bitmapResolution=2` để nét. Hỗ trợ PNG/JPG/WEBP/BMP/GIF và SVG
  (giữ nguyên).
- Chỉnh `x`, `y`, `size`, `direction`, `visible` của sprite qua form.
- Sửa **giá trị biến** và **nội dung list** (mỗi dòng = 1 phần tử).
- **Ngân hàng câu hỏi**: xem trước, **xuất/nhập CSV** (UTF-8 BOM, mở được bằng
  Excel) cho cả nhóm list trong cùng một sprite/stage. Có thể tạo list mới khi
  nhập nếu cột chưa tồn tại.
- Bộ **kiểm tra lỗi** trước khi xuất:
  - thiếu file asset (costume/sound),
  - sprite hoặc backdrop trùng tên,
  - biến/list trùng tên,
  - sprite nằm ngoài sân khấu,
  - broadcast bị block tham chiếu nhưng không khai báo (hoặc ngược lại),
  - **list lệch số dòng** trong cùng một nhóm câu hỏi (vd `cau_hoi`,
    `dap_an_a/b/c/d`),
  - file asset thừa.
- **Ẩn các biến Scratch thô** (tên bắt đầu bằng `_` hoặc `__`) trong bảng để
  giáo viên đỡ rối.
- Lệnh "Ẩn toàn bộ monitor biến" để tắt nhanh các biến hiển thị trên sân khấu.
- **Xuất `.sb3` mới** vào `workspace/output/`, kèm cơ chế **backup** tự động.
  Chỉ đóng gói các asset thực sự được tham chiếu (loại bỏ file rác).

## Tính năng AI (Gemini)

Tab **🤖 AI Assistant** cung cấp các hành động "AI đề xuất – giáo viên duyệt":

- **Chuẩn hoá list đang chọn / TẤT CẢ list**: sửa chính tả, NFC Unicode tiếng Việt,
  viết hoa đầu câu. Hiện diff cũ→mới, tick từng dòng rồi áp dụng.
- **Đồng văn phong đáp án A-D**: cho mapping ngân hàng câu hỏi đang chọn.
- **Sinh giải thích còn trống**: chỉ điền ô `giai_thich` chưa có nội dung.
- **Sinh câu hỏi mới từ chủ đề**: nhập chủ đề + khối + số câu → AI tạo đầy đủ
  4 đáp án + đáp án đúng + giải thích, append hoặc replace.
- **Đề xuất đổi tên** sprite / biến / list sang tiếng Việt rõ nghĩa
  (không động vào broadcast id, asset md5, block).
- **Review tổng thể dự án**: AI đọc cấu trúc + mẫu câu hỏi, đưa ra summary +
  suggestions + issues.

**API key**: Mở tab AI, dán `GEMINI_API_KEY` vào ô *API Key* khi sử dụng.
Nếu env có sẵn `GEMINI_API_KEY`, app sẽ gợi ý dán vào. Key không được lưu
xuống đĩa – chỉ tồn tại trong RAM phiên đang chạy.

**An toàn**: Mỗi lần áp dụng AI, `project.json` được snapshot vào
`workspace/backup/` với timestamp để rollback. AI tuyệt đối không sửa block,
broadcast id, hoặc md5 của asset.

## Cài đặt

Yêu cầu **Python 3.10+**.

```bash
pip install -r requirements.txt
python main.py
```

Thư viện chuẩn dùng: `tkinter`, `zipfile`, `json`, `hashlib`, `pathlib`,
`shutil`, `csv`. Thư viện ngoài duy nhất là **Pillow**.

> Trên Windows, `tkinter` đi kèm bộ cài Python chính thức. Nếu dùng Python
> trên Linux phải cài thêm `sudo apt install python3-tk`.

## Cấu trúc thư mục

```
scratch_editor/
├── main.py                 # entry-point, chạy `python main.py`
├── requirements.txt
├── README.md
├── core/                   # logic không phụ thuộc UI
│   ├── sb3_io.py           # mở/đóng gói .sb3
│   ├── project_model.py    # truy cập có ý nghĩa lên project.json
│   ├── assets.py           # xử lý ảnh nền/costume bằng Pillow
│   ├── linter.py           # kiểm tra lỗi dự án
│   └── qbank.py            # ngân hàng câu hỏi (CSV)
├── ui/                     # giao diện tkinter
│   ├── app.py              # cửa sổ chính
│   ├── stage_view.py       # canvas 480x360
│   └── dialogs.py          # dialog sửa list, biến
├── utils/
│   ├── paths.py            # workspace (temp/output/backup)
│   └── hashing.py          # MD5 cho asset
└── workspace/
    ├── temp/               # nơi giải nén .sb3 khi mở (tự dọn)
    ├── output/             # nơi lưu .sb3 đã xuất
    └── backup/             # bản sao lưu trước khi ghi đè
```

## Quy trình giáo viên sử dụng

1. **Mở** file `.sb3` đề thi gốc do trường giao.
2. Trên tab **Sprite**: chọn sprite, kéo trên Stage để đặt lại vị trí. Có thể
   nhập trực tiếp `x, y, size`.
3. Tab **Backdrop**: bấm *Thay ảnh nền* để đổi sang ảnh có sẵn (ví dụ ảnh logo
   trường, ảnh chủ đề). Chọn `Fit / Cover / Stretch`.
4. Tab **Ngân hàng câu hỏi**: bấm *Xuất CSV*, mở bằng Excel, sửa câu hỏi/đáp án
   thoải mái, lưu lại rồi *Nhập CSV*. Phần mềm sẽ ghi lại vào đúng các list
   trong Scratch.
5. Tab **Biến / List / Broadcast**: tinh chỉnh thêm.
6. Bấm **Kiểm tra lỗi** trước khi xuất. Sửa hết lỗi đỏ (❌) và xem xét cảnh báo
   (⚠️).
7. **Xuất .sb3** → file mới nằm trong `workspace/output/`. Mở bằng Scratch
   Desktop để kiểm tra cuối cùng trước khi nộp dự thi.

## Lưu ý kỹ thuật

- File `.sb3` thực chất là một file zip chứa `project.json` và các asset đặt
  tên theo MD5 (`<md5>.png`, `<md5>.svg`, `<md5>.wav`, ...). Khi thay asset,
  phần mềm tự tính MD5 mới và cập nhật `assetId` / `md5ext` trong
  `project.json`.
- Hệ toạ độ Scratch: gốc (0,0) ở giữa sân khấu, `x ∈ [-240, 240]`,
  `y ∈ [-180, 180]`. Stage view chuyển đổi qua lại giữa toạ độ này và pixel
  canvas.
- Tâm xoay (`rotationCenterX/Y`) được đặt giữa ảnh khi thay costume mới.
- `bitmapResolution=2` được dùng cho costume bitmap mới để giữ độ nét khi
  Scratch hiển thị.

## Giới hạn đã biết

- Stage view không render SVG (Tkinter không hỗ trợ). Sprite SVG hiển thị bằng
  ô placeholder, **không ảnh hưởng** đến file xuất ra – Scratch vẫn render
  đúng.
- Không sửa block code (kéo–thả block). Đây là editor *nội dung* (asset/biến/
  list/vị trí), không phải editor *logic*.
- Phần mềm yêu cầu `project.json` hợp lệ theo định dạng Scratch 3. File `.sb2`
  (Scratch 2 cũ) không được hỗ trợ.
