# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)

*Dành cho Role 5: Observability & Reviewer*

**Chủ đề nhóm**: 🏠 Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê (Đề tài #10)
**Provider**: NVIDIA NIM (`meta/llama-3.3-70b-instruct`) — có thể chạy đối chứng offline bằng `LLM_PROVIDER=mock`
**Lệnh tái lập**: `python src/app.py`

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `5/5` | Chuỗi bắt buộc 3 bước: tìm phòng ➔ tra khung giờ ➔ đặt lịch. Không thể rút gọn thành 1 truy vấn. |
| 🛠️ **Tool Interaction** | `5/5` | Toàn bộ dữ liệu (mã căn, giá, địa chỉ, khung giờ) nằm trong hệ thống, LLM không thể biết từ tham số huấn luyện. `book_viewing` còn tạo side effect ghi dữ liệu thật. |
| 🔀 **Dynamic Decision** | `5/5` | Tham số bước sau **chỉ tồn tại trong Observation bước trước**: mã `APT001` sinh ra từ `search_listings`, khung giờ `2026-07-29 09:00` sinh ra từ `check_viewing_slots`. Không chạy bước trước thì không thể viết đúng bước sau. |
| ⏳ **Long Horizon** | `3/5` | Quy trình 3–4 bước, kết thúc trong một phiên. Chưa cần bộ nhớ dài hạn qua nhiều ngày. |
| **TỔNG ĐIỂM FIT** | **18/20** | **KẾT LUẬN: BÀI TOÁN RẤT PHÙ HỢP VỚI REACT AGENT** |

> ⚠️ **Nhưng không phải mọi câu hỏi đều đáng dùng Agent.** Test case #1 và #2 (kiến thức chung về hợp đồng, đặt cọc) có điểm fit gần như 0 — Chatbot trả lời bằng 1 lần gọi LLM là đủ, còn Agent phải tốn thêm vòng lặp mà kết quả không tốt hơn. Đây chính là lý do nhóm thiết kế **Hybrid Flowchart** ở mục 6.

---

## 📋 2. BẢNG TỔNG KẾT 5 TEST CASES

| # | Loại | Tool calls kỳ vọng | Agent thực tế | Chatbot tool calls | Lý do dừng (`stop_reason`) | Đạt? |
| :-: | :--- | :-: | :-: | :-: | :--- | :-: |
| 1 | 🟢 Đơn giản | 0 | **0** | 0 | `final_answer` | ✅ |
| 2 | 🟢 Đơn giản | 0 | **0** | 0 | `final_answer` | ✅ |
| 3 | 🟡 1 Tool | 1 | **1** | 0 | `final_answer` | ✅ |
| 4 | 🟡 3 Tools nối chuỗi | 3 | **3** | 0 | `final_answer` | ✅ |
| 5 | 🔴 Bẫy Guardrail | 1–3 (đều lỗi) | **2** | 0 | `repeated_action` 🛡️ | ✅ |

**Quan sát cốt lõi**: Chatbot Baseline có `tool_calls = 0` ở **mọi** test case — đó không phải lỗi cấu hình mà là **giới hạn kiến trúc của Cấp độ 2**. Nó không có đường dẫn code nào để chạm tới dữ liệu.

**Quan sát thứ hai (quan trọng khi phản biện)**: Agent gọi **0 tool** ở case #1 và #2. Một agent tốt phải biết **khi nào KHÔNG cần dùng tool**. Gọi tool thừa cũng là một dạng lỗi — tốn chi phí orchestration mà không thêm bằng chứng.

---

## 🔍 3. SO SÁNH PHẢN HỒI — TEST CASE #4 (Trace đầy đủ)

**Câu hỏi**: *"Tìm phòng dưới 5 triệu ở Cầu Giấy, xem căn rẻ nhất còn khung giờ nào trống rồi đặt lịch xem nhà giúp tôi."*

### 🤖 Chatbot Baseline (Cấp độ 2)

```text
💬 [CHATBOT BASELINE]
🤖 Trả lời:
Tôi rất muốn giúp bạn, nhưng tôi là chatbot thuần và không có công cụ tra cứu
dữ liệu phòng trọ thời gian thực. Tôi không thể biết phòng nào còn trống,
giá bao nhiêu, hay đặt lịch xem nhà giúp bạn được.
📊 Telemetry: llm_calls=1 | tool_calls=0 | grounded=False
```

**Phân loại output**: `safe fallback` (an toàn, không ảo giác) — nhưng **không giải quyết được nhu cầu**. Người dùng vẫn chưa có phòng và chưa có lịch hẹn.

> 💡 **Lưu ý khi chấm chéo**: đây là kết quả với prompt đã ép "không được bịa". Nếu bỏ ràng buộc đó, chatbot rất dễ rơi vào `hallucinated` — bịa ra mã căn hộ và số điện thoại môi giới nghe cực kỳ thuyết phục nhưng hoàn toàn không tồn tại. Đó mới là kịch bản nguy hiểm trong thực tế.

### 🧠 ReAct Agent (Cấp độ 3)

```text
--- 🔄 Vòng lặp ReAct (Step 1/5) ---
🧠 Thought: Tôi cần tra cứu danh sách phòng thực tế trước, chưa thể biết mã căn nào.
🛠️ Action: search_listings['Cầu Giấy', '5000000']
👁️ Observation: Tìm thấy 1 căn tại Cầu Giấy (giá <= 5,000,000 VNĐ):
- [APT001] Studio full nội thất, ban công | 4,500,000 VNĐ/tháng | 28m2 | 1PN | Còn trống

--- 🔄 Vòng lặp ReAct (Step 2/5) ---
🧠 Thought: Đã có mã căn APT001 từ Observation. Giờ tôi kiểm tra khung giờ xem nhà.
🛠️ Action: check_viewing_slots['APT001']
👁️ Observation: Căn [APT001] còn 3 khung giờ xem nhà: 2026-07-29 09:00; 2026-07-29 15:00; 2026-07-30 10:00

--- 🔄 Vòng lặp ReAct (Step 3/5) ---
🧠 Thought: Đã có khung giờ trống từ Observation. Người dùng yêu cầu đặt lịch nên tôi tiến hành đặt khung giờ sớm nhất.
🛠️ Action: book_viewing['APT001', '2026-07-29 09:00']
👁️ Observation: Đặt lịch thành công! Mã xác nhận: BK001. Bạn sẽ xem căn [APT001] — Số 12, ngõ 165 Xuân Thủy, Cầu Giấy, Hà Nội vào lúc 2026-07-29 09:00.

--- 🔄 Vòng lặp ReAct (Step 4/5) ---
🧠 Thought: Tôi đã có đủ bằng chứng từ các Observation để trả lời.
🏁 Final Answer: Căn APT001 (Studio full nội thất, 4.500.000 VNĐ/tháng, 28m2) tại Cầu Giấy
   phù hợp ngân sách của bạn. Mọi thông tin trên đều lấy nguyên văn từ Observation của tool.

📊 Telemetry: llm_calls=4 | tool_calls=3 | steps=4 | stop_reason=final_answer
```

**Phân loại output**: `correct` + `grounded`.

**Bằng chứng chuỗi phụ thuộc (Dynamic Decision)** — đây là điểm mạnh nhất khi bảo vệ bài:

| Bước | Tham số dùng | Nguồn gốc tham số |
| :-: | :--- | :--- |
| 2 | `APT001` | ❗ Chỉ xuất hiện lần đầu trong **Observation của bước 1** |
| 3 | `2026-07-29 09:00` | ❗ Chỉ xuất hiện lần đầu trong **Observation của bước 2** |

Nếu bỏ vòng lặp ReAct, LLM **không có cách nào** biết được hai giá trị này. Đây là bằng chứng định lượng cho thấy Agent không phải là "chatbot có thêm màu mè".

---

## 🛡️ 4. FAILED TRACE & PHÂN TÍCH NGUYÊN NHÂN GỐC (RCA) — TEST CASE #5

**Câu hỏi bẫy**: *"Tìm phòng ở quận Atlantis và đặt lịch xem nhà vào ngày 32/13/2026."*

Cả hai tham số đều vô lý: quận không tồn tại **và** ngày không có thật.

### Trace thực tế (Agent V1 — chưa có phanh Repeated Action)

```text
--- Step 1/5 ---
🧠 Thought: Người dùng muốn tìm phòng ở quận Atlantis, tôi thử tra cứu.
🛠️ Action: search_listings['Atlantis', '5000000']
👁️ Observation: LỖI: Không tìm thấy quận 'Atlantis' trong khu vực phục vụ.
   Các quận hợp lệ: Cầu Giấy, Thanh Xuân, Tây Hồ, Đống Đa, Hai Bà Trưng.

--- Step 2/5 ---
🧠 Thought: Người dùng muốn tìm phòng ở quận Atlantis, tôi thử tra cứu.
🛠️ Action: search_listings['Atlantis', '5000000']     ← ❌ LẶP LẠI Y HỆT
👁️ Observation: LỖI: Không tìm thấy quận 'Atlantis' ... (giống hệt bước 1)

--- Step 3/5 ---
🛠️ Action: search_listings['Atlantis', '5000000']     ← ❌ LẶP LẦN 3
🛡️ GUARDRAIL: Action 'search_listings(Atlantis, 5000000)' đã lặp lại 2 lần. Ngắt vòng lặp an toàn!

📊 Telemetry: llm_calls=3 | tool_calls=2 | steps=3 | stop_reason=repeated_action
```

### 🔬 Root Cause Analysis

| Hạng mục | Nội dung |
| :--- | :--- |
| **Triệu chứng** | Agent gọi đi gọi lại đúng một Action với đúng một bộ tham số, đốt token mà không tiến triển. |
| **Nguyên nhân trực tiếp** | Observation báo lỗi được đưa lại vào transcript, nhưng LLM không rút ra được rằng *lặp lại y hệt sẽ cho kết quả y hệt*. |
| **Nguyên nhân gốc (Root Cause)** | Agent **không có trạng thái nhận biết chính nó đang bị kẹt**. Vòng lặp ReAct thuần không so sánh Action hiện tại với lịch sử Action. Ngoài ra system prompt V1 chưa có quy tắc xử lý khi gặp `LỖI:`. |
| **Vì sao `MAX_ITERATIONS` là chưa đủ** | Nó chỉ giới hạn *thiệt hại* (dừng sau 5 bước), không *phát hiện* được vòng lặp. Agent vẫn lãng phí trọn 5 bước rồi mới chết. |

### ✅ Cách khắc phục ở Agent V2

| Lớp phòng thủ | Vị trí | Cơ chế |
| :--- | :--- | :--- |
| **1. Prompt** | `prompts.py` — Quy tắc 5 & 6 | Ép LLM đọc kỹ thông báo lỗi, đổi tham số, và tự dừng sau 2 lần thất bại. |
| **2. Phát hiện lặp** | `app.py` — `action_history` | Chuẩn hóa Action thành chữ ký `tên_tool(tham_số)`; lặp quá `MAX_REPEATED_ACTIONS = 2` là cắt ngay. |
| **3. Trần cứng** | `app.py` — `MAX_ITERATIONS = 5` | Lưới an toàn cuối: chi phí luôn có trần dù LLM hành xử thế nào. |
| **4. Lỗi giàu thông tin** | `tools.py` | Không chỉ báo "lỗi" mà kèm luôn **danh sách giá trị hợp lệ**, giúp Agent tự sửa thay vì đoán mò. |
| **5. Fallback lịch sự** | `prompts.py` — `FALLBACK_MESSAGE` | Khi chạm phanh: xin lỗi, nêu rõ định dạng đúng, **không bịa** kết quả. |

### So sánh Before / After

| | Agent V1 | Agent V2 |
| :--- | :--- | :--- |
| Hành vi khi gặp tham số vô lý | Lặp vô hạn tới khi hết `MAX_ITERATIONS` | Cắt tại lần lặp thứ 3 (`stop_reason=repeated_action`) |
| Số lần gọi LLM lãng phí | 5 | 3 |
| Câu trả lời cuối | Cụt / không có | `FALLBACK_MESSAGE` lịch sự, chỉ rõ cách sửa |
| Có bịa dữ liệu không? | Rủi ro cao | ❌ Không — quy tắc 4 chặn |
| Chương trình có crash không? | ❌ Không (tool trả chuỗi `LỖI:`) | ❌ Không |

---

## 🧪 5. KIỂM THỬ TẦNG TOOL ĐỘC LẬP (chạy `python src/tools.py`)

Codelab yêu cầu test tool **trước** khi gắn vào Agent, để khi Agent chạy sai ta loại trừ được một nguồn lỗi.

```text
KẾT QUẢ: 12/12 test trả về chuỗi an toàn, 0 crash.
```

Bao gồm các tình huống lỗi: quận không hợp lệ · giá sai định dạng (`"năm triệu"`) · thiếu tham số · mã căn không tồn tại · **ngày vô lý 32/13** · khung giờ ngoài lịch · đặt trùng khung giờ. Không trường hợp nào ném Exception ra ngoài.

---

## 🔀 6. HYBRID DECISION — KHI NÀO DÙNG CHATBOT, KHI NÀO DÙNG AGENT

Sơ đồ đầy đủ: [`docs/hybrid_flowchart.mermaid`](./hybrid_flowchart.mermaid)

| Tín hiệu định tuyến | Đi đường | Lý do |
| :--- | :--- | :--- |
| Hỏi kiến thức chung, quy định, lời khuyên | 🟢 Chatbot | 1 lần gọi LLM, rẻ và nhanh hơn. Case #1, #2. |
| Cần dữ liệu tồn tại trong hệ thống (phòng, giá, khung giờ) | 🧠 Agent | Chatbot không có đường dẫn code tới dữ liệu. Case #3. |
| Cần thực hiện hành động có side effect (đặt lịch) | 🧠 Agent | Chỉ tool mới ghi được dữ liệu. Case #4. |
| Yêu cầu chứa tham số nghi ngờ vô lý | 🧠 Agent + Guardrail | Cần tool xác thực rồi fallback an toàn. Case #5. |

**Chi phí đo được**: câu hỏi đơn giản đi đường Chatbot tốn **1** lần gọi LLM; nếu ép đi đường Agent sẽ tốn **2+** lần. Trên quy mô lớn, định tuyến sai làm chi phí tăng gấp đôi mà chất lượng không đổi.

---

## 🎁 7. BONUS — AUTONOMOUS AGENT (Cấp độ 4)

Hàm `run_autonomous_agent()` trong `src/app.py` minh họa 2 năng lực mà Cấp độ 3 không có:

* **Planning**: gọi LLM tự chia mục tiêu lớn thành tối đa 3 nhiệm vụ con tuần tự, trước khi hành động.
* **Memory**: kết quả nhiệm vụ con `i` được nhét vào ngữ cảnh của nhiệm vụ con `i+1`. Cấp độ 3 chỉ có bộ nhớ trong phạm vi một câu hỏi; Cấp độ 4 mang bộ nhớ xuyên suốt nhiều nhiệm vụ.

Khác biệt cốt lõi: **Cấp 3 phản ứng, Cấp 4 lập kế hoạch trước rồi mới phản ứng.**

---

## 📌 8. KẾT LUẬN

1. **Agent không phải luôn thắng.** Ở case #1 và #2, Chatbot cho chất lượng tương đương với chi phí bằng một nửa. Agent chỉ đáng giá khi câu hỏi cần *bằng chứng* hoặc *hành động*.
2. **Đừng đánh giá Agent bằng câu trả lời cuối cùng.** Case #5 có câu trả lời cuối "xấu" (xin lỗi, không giúp được) nhưng đó lại là hành vi **đúng** — thà thừa nhận không biết còn hơn bịa ra một căn hộ không tồn tại.
3. **Guardrail phải có nhiều lớp.** `MAX_ITERATIONS` một mình chỉ giới hạn thiệt hại; phát hiện Repeated Action mới thực sự nhận ra vấn đề sớm.
4. **Thông báo lỗi là một phần của prompt engineering.** Tool trả về kèm danh sách giá trị hợp lệ giúp Agent tự phục hồi — lỗi nghèo thông tin thì Agent chỉ còn cách đoán mò.
