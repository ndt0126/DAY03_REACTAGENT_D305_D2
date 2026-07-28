# 🎬 HƯỚNG DẪN CHẠY DEMO — LAB 03

---

## 1️⃣ CÀI ĐẶT (chỉ làm 1 lần)

Mở PowerShell tại thư mục dự án:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

> Nếu PowerShell chặn script: chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi thử lại.

---

## 2️⃣ CẤU HÌNH `.env`

Mở file `.env`, sửa 4 dòng đầu:

```env
LLM_PROVIDER=custom
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=nvapi-xxxxxxxxxxxxxxxx
LLM_MODEL=meta/llama-3.3-70b-instruct
```

**Chạy offline không cần key** (dùng khi hết quota hoặc mất mạng giữa buổi):

```env
LLM_PROVIDER=mock
```

---

## 3️⃣ SINH DỮ LIỆU

```powershell
python config\generate_listings.py --stats
python config\generate_bookings.py
```

- `listings.txt` — 10.000 căn hộ (chỉ cần sinh 1 lần, đã commit sẵn)
- `bookings.txt` — 132 lịch hẹn có sẵn

> ⚠️ **Nên chạy lại `generate_bookings.py` ngay trước buổi demo.** Lịch được sinh tương đối
> so với ngày chạy (từ ngày mai tới +14 ngày). Để quá 14 ngày là seed hết hạn.
>
> ⚠️ Chạy lại sẽ **ghi đè** mọi lịch khách đã đặt qua chat.

---

## 4️⃣ KIỂM TRA NHANH TRƯỚC KHI DEMO

```powershell
python src\tools.py       # phải ra: 20/20 test, 0 crash
python src\prompts.py     # xem prompt sinh ra, phải thấy 5 tool
python src\providers.py   # xác nhận provider + model đang dùng
```

---

## 5️⃣ CHẠY WEB APP

```powershell
python src\app.py
```

Mở trình duyệt tại địa chỉ terminal in ra (thường là `http://127.0.0.1:5001`).

---

# 🎤 KỊCH BẢN DEMO 5 PHÚT

## Màn 1 — Cho thấy giới hạn của Chatbot *(1 phút)*

Bấm nút **Chatbot Baseline**, gõ:

```
Tìm căn hộ ở quận Cầu Giấy dưới 6 triệu
```

👉 Chatbot thừa nhận không có dữ liệu. **Chỉ vào telemetry: `tool_calls = 0`.**

> **Câu nói chốt**: *"Nó không phải không muốn giúp — nó không có đường dẫn code nào
> chạm tới dữ liệu. Đây là giới hạn kiến trúc, không phải giới hạn cấu hình."*

---

## Màn 2 — ReAct Agent giải đúng bài đó *(1 phút)*

Chuyển sang **ReAct Agent**, gõ **y hệt câu trên**.

👉 Mở rộng phần trace, chỉ vào chuỗi `Thought → Action → Observation`.

> **Câu nói chốt**: *"Dòng Observation này do ứng dụng chèn sau khi chạy hàm Python thật,
> không phải LLM tự viết. Chúng em dùng stop sequence cắt output của model ngay trước
> khi nó kịp bịa."*

---

## Màn 3 — ⭐ ĐIỂM MẠNH NHẤT: khách không biết UUID *(2 phút)*

Gõ tiếp trong **cùng cửa sổ chat** (đừng bấm Clear):

```
Đặt lịch xem căn đầu tiên nhé, tôi tên Nguyễn Quang Vinh, sđt 0912345678
```

👉 Agent tự lấy mã UUID từ lượt chat trước, tra khung giờ trống, rồi đặt lịch.

> **Câu nói chốt**: *"Mã căn là UUID 36 ký tự. Khách hàng không bao giờ biết và không thể
> gõ ra. Khách chỉ nói 'căn đầu tiên'. Agent phải tự đối chiếu với lịch sử hội thoại —
> đây là thứ Chatbot một lượt không bao giờ làm được."*

**Chứng minh side effect là thật** — mở PowerShell thứ hai:

```powershell
Get-Content config\bookings.txt -Tail 1
```

👉 Dòng cuối chính là lịch vừa đặt. Rồi hỏi lại trong chat:

```
Kiểm tra lại lịch hẹn của tôi với số 0912345678
```

---

## Màn 4 — Guardrail chặn ảo giác *(1 phút)*

Bấm **Clear chat**, rồi gõ:

```
Tìm căn hộ 500 mét vuông ở quận Atlantis và đặt lịch xem nhà vào ngày 32/13/2026
```

👉 Agent lặp lại Action thất bại → bị `MAX_REPEATED_ACTIONS` cắt → trả fallback lịch sự.

> **Câu nói chốt**: *"`MAX_ITERATIONS` một mình chỉ giới hạn thiệt hại, phải đốt trọn 8 lượt
> gọi LLM rồi mới chết. Phát hiện Repeated Action cắt ngay ở bước 3 — tiết kiệm 5 lượt gọi."*

**Nếu còn thời gian**, thêm câu này (bẫy hay nhất):

```
Tìm căn hộ trên 15 triệu ở quận Hoàn Kiếm mà gần đó vẫn có chợ dân sinh
```

👉 Đáp án đúng là **13 căn**. Agent nào đoán mò sẽ nói "không có" vì chợ dân sinh là tiện ích
duy nhất có tỉ lệ **nghịch** với giá (78% ở nhóm rẻ → 32% ở nhóm đắt).

---

# 🛡️ XỬ LÝ SỰ CỐ TẠI CHỖ

| Tình huống | Cách chữa |
| :--- | :--- |
| Hết quota / mất mạng | Sửa `.env` thành `LLM_PROVIDER=mock`, khởi động lại app. Mock vẫn chạy đủ vòng lặp ReAct trên dữ liệu thật. |
| Port bị chiếm | `$env:PORT=5055; python src\app.py` |
| Model trả lời sai định dạng | Bình thường với model nhỏ. Chỉ vào bước `parse_error` trong trace — đó chính là bằng chứng cho phần Observability. |
| Lịch đã kín hết | `python config\generate_bookings.py` để reset. |
| Model chép thiếu UUID | Tool chấp nhận tiền tố ≥6 ký tự nên vẫn chạy. Đây là điểm cộng khi bị hỏi về robustness. |

---

# ❓ BA CÂU PHẢN BIỆN CHẮC CHẮN BỊ HỎI

**"Làm sao chứng minh Agent gọi tool thật chứ không phải LLM bịa?"**
> Mở `src/app.py`, chỉ vào `execute_tool()` — nó tra `AVAILABLE_TOOLS` và gọi hàm Python thật.
> Rồi chỉ vào dòng `transcript += ... Observation: {observation}` — chuỗi đó là **giá trị trả
> về của hàm**, không phải text của LLM. Bằng chứng thứ hai: `STOP_SEQUENCES` cắt output của
> model ngay trước khi nó kịp viết `Observation:`.

**"Sao không dùng Chatbot cho nhanh?"**
> Mở test case #5. Mã căn UUID ở bước 2 và khung giờ ở bước 3 **chỉ xuất hiện lần đầu trong
> Observation của bước trước**. Chatbot không có đường dẫn code nào tới hai giá trị đó.
> Ngược lại, ở case #1 và #2 nhóm em **cố tình cho Agent 0 tool call** vì ở đó Chatbot rẻ
> hơn mà chất lượng tương đương.

**"Hỏi câu vô lý thì Agent có sập không?"**
> Mời thầy/cô thử trực tiếp. Tool không bao giờ raise Exception — mọi lỗi thành chuỗi `LỖI:`
> kèm danh sách giá trị hợp lệ để Agent tự sửa. Có 5 lớp phòng thủ, chạm phanh thì trả
> `FALLBACK_MESSAGE` lịch sự chứ không bịa. Đã test 20/20 tình huống lỗi, 0 crash.
