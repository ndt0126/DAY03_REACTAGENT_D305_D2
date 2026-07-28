"""
🔌 MULTI-PROVIDER LLM ADAPTER

Hỗ trợ chuyển đổi nhà cung cấp AI chỉ bằng cách đổi biến môi trường trong .env,
KHÔNG phải sửa một dòng code nào. Nhờ vậy mỗi thành viên trong nhóm dùng được
key/endpoint riêng của mình.

Cách dùng khuyến nghị (endpoint tương thích chuẩn OpenAI — NVIDIA NIM, Groq,
Together, DeepSeek, Ollama...):
    LLM_PROVIDER=custom
    LLM_BASE_URL=https://integrate.api.nvidia.com/v1
    LLM_API_KEY=nvapi-xxxxxxxx
    LLM_MODEL=meta/llama-3.3-70b-instruct

Chạy offline không cần key:
    LLM_PROVIDER=mock
"""

import os
import re
import sys

import requests
from dotenv import load_dotenv

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()


class BaseLLMProvider:
    """Interface cơ sở cho tất cả các LLM Provider.

    Tham số `stop` cực kỳ quan trọng với ReAct Agent: nó ép LLM DỪNG LẠI ngay sau
    khi sinh dòng `Action:`, để chính ứng dụng (không phải LLM) mới là bên chèn
    `Observation:` thật từ Tool. Thiếu phanh này, LLM sẽ tự bịa Observation và
    toàn bộ hệ thống chỉ còn là chatbot khoác định dạng ReAct.
    """
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        raise NotImplementedError


def _apply_stop(text: str, stop: list = None) -> str:
    """Cắt thủ công tại stop sequence đầu tiên.

    Đây là LỚP BẢO HIỂM THỨ HAI: một số provider không hỗ trợ stop natively
    (vd Gemini), và kể cả provider có hỗ trợ thì model vẫn có thể phớt lờ.
    """
    if not stop or not text:
        return text
    cut = len(text)
    for s in stop:
        idx = text.find(s)
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut].rstrip()


class CompatibleProvider(BaseLLMProvider):
    """🔧 Provider dùng chung cho mọi endpoint TƯƠNG THÍCH CHUẨN OpenAI.

    Bảng endpoint tham khảo (chỉ đổi LLM_BASE_URL + LLM_MODEL):
        NVIDIA NIM  -> https://integrate.api.nvidia.com/v1  | meta/llama-3.3-70b-instruct
        Groq        -> https://api.groq.com/openai/v1       | llama-3.3-70b-versatile
        Together AI -> https://api.together.xyz/v1          | meta-llama/Llama-3.3-70B-Instruct-Turbo
        DeepSeek    -> https://api.deepseek.com/v1          | deepseek-chat
        Ollama local-> http://localhost:11434/v1            | llama3.3  (key điền bừa cũng được)
    """
    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        # Ưu tiên biến chung LLM_*, vẫn chấp nhận NVIDIA_* để tương thích ngược
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("NVIDIA_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or self.DEFAULT_MODEL
        self.base_url = (base_url or os.getenv("LLM_BASE_URL")
                         or os.getenv("NVIDIA_BASE_URL") or self.DEFAULT_BASE_URL)

    # Các chuỗi placeholder — nếu key vẫn là một trong số này nghĩa là chưa điền.
    # Bắt sớm ở đây để báo lỗi rõ ràng, thay vì để API trả về 401 khó hiểu.
    _PLACEHOLDERS = ("your_", "dan_key", "xxxx", "<", "thay_bang", "api_key_here")

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        key = str(self.api_key or "")
        if not key or any(p in key.lower() for p in self._PLACEHOLDERS):
            return ("[LLM Error]: Bạn chưa dán API key thật vào biến LLM_API_KEY trong file .env!\n"
                    "  • Mở file .env, tìm dòng LLM_API_KEY= rồi dán key (bắt đầu bằng nvapi-).\n"
                    "  • Hoặc đổi LLM_PROVIDER=mock để chạy thử offline không cần key.")
        try:
            import openai
        except ImportError:
            return ("[LLM Error]: Chưa cài thư viện 'openai'. Chạy: pip install -r requirements.txt")
        try:
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.2,      # ReAct cần ổn định, không cần sáng tạo
                max_tokens=1024,
                stop=stop or None,
            )
            return _apply_stop(response.choices[0].message.content, stop)
        except Exception as e:
            return f"[LLM Exception @ {self.base_url}]: {str(e)}"


# Alias để tài liệu/code cũ không gãy
NvidiaProvider = CompatibleProvider


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (SDK riêng)."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or "your_" in str(self.api_key):
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env!"
        try:
            from google import genai
        except ImportError:
            return ("[Gemini Error]: Chưa cài thư viện 'google-genai'. Chạy: pip install google-genai\n"
                    "  (Gói này là TUỲ CHỌN, chỉ cần khi LLM_PROVIDER=gemini.)")
        try:
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return _apply_stop(response.text, stop)
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (GPT-4o, GPT-4o-mini...)."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or "your_" in str(self.api_key):
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env!"
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=self.model_name, messages=messages,
                temperature=0.2, stop=stop or None,
            )
            return _apply_stop(response.choices[0].message.content, stop)
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-haiku-20240307"

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or "your_" in str(self.api_key):
            return "[Anthropic Error]: Chưa cấu hình ANTHROPIC_API_KEY trong file .env!"
        try:
            import anthropic
        except ImportError:
            return ("[Anthropic Error]: Chưa cài thư viện 'anthropic'. Chạy: pip install anthropic\n"
                    "  (Gói này là TUỲ CHỌN, chỉ cần khi LLM_PROVIDER=anthropic.)")
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            kwargs = {
                "model": self.model_name,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            if stop:
                kwargs["stop_sequences"] = stop
            response = client.messages.create(**kwargs)
            return _apply_stop(response.content[0].text, stop)
        except Exception as e:
            return f"[Anthropic Exception]: {str(e)}"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Provider."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or "your_" in str(self.api_key):
            return "[OpenRouter Error]: Chưa cấu hình OPENROUTER_API_KEY trong file .env!"
        try:
            headers = {"Authorization": f"Bearer {self.api_key}",
                       "Content-Type": "application/json"}
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = {"model": self.model_name, "messages": messages, "temperature": 0.2}
            if stop:
                payload["stop"] = stop
            res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                return _apply_stop(res.json()["choices"][0]["message"]["content"], stop)
            return f"[OpenRouter API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[OpenRouter Exception]: {str(e)}"


class MockProvider(BaseLLMProvider):
    """🧪 Offline Mock Provider — KHÔNG cần API key.

    ⚠️ ĐÂY KHÔNG PHẢI BẢN IN CỨNG CÂU TRẢ LỜI.

    Mock này thực sự ĐỌC transcript ReAct được truyền vào, đếm số Observation đã
    có, và trích dữ liệu THẬT (mã căn UUID, khung giờ) ra khỏi Observation để
    dựng Action tiếp theo. Nhờ vậy vòng lặp ReAct thật trong app.py được chạy
    đầy đủ: parser, executor, guardrail, ghi file.

    👉 Mọi mã căn và khung giờ mock dùng đều LẤY TỪ Observation của Tool thật,
       không có bất kỳ mã bịa nào. Nếu mock bịa mã, trace log dùng làm báo cáo
       sẽ vô giá trị vì không tái lập được bằng code.
    """
    model_name = "offline-mock-v3"

    # UUID xuất hiện trong Observation của search_listings
    _UUID_RE = re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    # Khung giờ trống trong Observation của check_viewing_slots
    _SLOT_RE = re.compile(r"\b(0[89]|1[0-7]):00\b")
    _DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

    # ⚠️ Cố tình KHÔNG đưa "căn hộ", "phòng", "thuê", "triệu" vào đây. Chúng xuất hiện
    # cả trong câu hỏi tư vấn chung ("khi thuê căn hộ nên lưu ý gì trong hợp đồng")
    # nên sẽ khiến Agent gọi tool một cách vô ích.
    _LOOKUP_VERBS = ["tìm", "tra cứu", "đặt lịch", "book", "xem nhà", "còn trống",
                     "trống không", "khung giờ", "giờ nào", "lịch hẹn", "lịch xem",
                     "atlantis", "sao hỏa"]
    _DISTRICTS = ["cầu giấy", "thanh xuân", "tây hồ", "hoàn kiếm", "hà đông", "đống đa",
                  "long biên", "hoàng mai", "ba đình", "hai bà trưng", "từ liêm", "quận"]

    _DISTRICT_NAMES = ["Thanh Xuân", "Tây Hồ", "Hoàn Kiếm", "Hà Đông", "Đống Đa",
                       "Long Biên", "Hoàng Mai", "Ba Đình", "Hai Bà Trưng",
                       "Nam Từ Liêm", "Bắc Từ Liêm", "Cầu Giấy"]

    def _extract_params(self, cur: str):
        """Trích quận / khoảng giá / khoảng diện tích từ câu hỏi của khách.

        Mock trước đây luôn truyền cứng '8000000' bất kể khách nói gì — khách hỏi
        10 triệu thì nó vẫn tìm 8 triệu. Hàm này mô phỏng việc LLM thật bóc tham số.
        Vẫn chỉ là heuristic đơn giản: LLM thật làm việc này tốt hơn nhiều.
        """
        quan = next((q for q in self._DISTRICT_NAMES if q.lower() in cur), "Cầu Giấy")

        # Các con số kèm đơn vị "triệu" -> giá
        trieu = [float(x.replace(",", ".")) for x in
                 re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr\b)", cur)]
        # Số VNĐ viết đầy đủ (>= 6 chữ số)
        raw = [int(x.replace(".", "").replace(",", "")) for x in
               re.findall(r"\b(\d[\d.,]{5,})\b", cur)]
        gia = sorted([int(t * 1_000_000) for t in trieu] + raw)

        gmin = gmax = ""
        if len(gia) >= 2:                       # "từ 9 triệu tới 11 triệu"
            gmin, gmax = gia[0], gia[-1]
        elif len(gia) == 1:
            if any(k in cur for k in ["trên", "từ", "hơn", "lớn hơn"]):
                gmin = gia[0]
            else:                               # "dưới X", "tầm X", "khoảng X"
                gmax = gia[0]

        # Diện tích
        amin = amax = ""
        for num in re.findall(r"(?:trên|từ|hơn|lớn hơn|rộng)\s*(\d+)\s*(?:m2|mét vuông|m²)", cur):
            amin = int(num)
        for num in re.findall(r"(?:dưới|tối đa|nhỏ hơn|không quá)\s*(\d+)\s*(?:m2|mét vuông|m²)", cur):
            amax = int(num)

        return quan, gmax, gmin, amin, amax

    def _needs_lookup(self, text: str) -> bool:
        """Câu hỏi này có cần TRA CỨU DỮ LIỆU THẬT không?

        Là 'cần' nếu có động từ tra cứu/đặt lịch, HOẶC nhắc tên quận, HOẶC chứa
        sẵn một mã căn UUID. Câu hỏi tư vấn chung thì không thoả điều kiện nào.
        """
        if self._UUID_RE.search(text):
            return True
        return (any(k in text for k in self._LOOKUP_VERBS)
                or any(d in text for d in self._DISTRICTS))

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        is_react = "Thought:" in (system_prompt or "") or "ReAct" in (system_prompt or "")
        low = prompt.lower()

        # ---------- Chế độ Chatbot Baseline (1 lần gọi, KHÔNG tool) ----------
        if not is_react:
            if self._needs_lookup(low):
                return ("Tôi rất muốn giúp bạn, nhưng tôi là chatbot thuần và không có "
                        "công cụ tra cứu cơ sở dữ liệu phòng trọ. Tôi không thể biết căn nào "
                        "còn trống, giá bao nhiêu, hay đặt lịch xem nhà giúp bạn được. "
                        "Bạn nên liên hệ trực tiếp môi giới để có thông tin chính xác.")
            return ("Đây là câu trả lời dựa trên kiến thức chung: khi thuê nhà bạn nên đọc kỹ "
                    "điều khoản tiền cọc, thời hạn hợp đồng, quy định tăng giá, và đơn giá "
                    "điện nước. Loại câu hỏi này không cần tra cứu dữ liệu thời gian thực.")

        # ---------- Chế độ ReAct ----------
        n_obs = prompt.count("Observation:")
        last_obs = prompt.rsplit("Observation:", 1)[-1] if n_obs else ""
        # Dòng "Question:" là câu hỏi của lượt hiện tại (phần trước đó là lịch sử)
        user_line = prompt.rsplit("Question:", 1)[-1].split("\n")[0] if "Question:" in prompt else prompt

        # Câu hỏi lý thuyết -> trả lời ngay, KHÔNG tiêu tốn tool.
        # Cũng xét trên CÂU HỎI HIỆN TẠI, không xét cả lịch sử.
        if not self._needs_lookup(user_line.lower()) and n_obs == 0:
            return ("Thought: Câu hỏi này chỉ cần kiến thức chung, không tool nào tra cứu được "
                    "và cũng không cần thiết.\n"
                    "Final Answer: Bạn nên kiểm tra kỹ điều khoản tiền cọc, thời hạn hợp đồng "
                    "và đơn giá điện nước trước khi ký. (Trả lời từ kiến thức chung, không cần Tool.)")

        # 🔴 Bẫy: quận không tồn tại. Mock cố tình đóng vai LLM "cứng đầu" thử lại y hệt
        # để ép guardrail MAX_REPEATED_ACTIONS lộ diện.
        if "atlantis" in low:
            return ("Thought: Khách muốn tìm phòng ở quận Atlantis, tôi thử tra cứu.\n"
                    "Action: search_listings[\"Atlantis\", \"5000000\"]")

        # ✅ Đã đặt lịch xong -> CHỐT NGAY, không gọi lại tool có side effect lần nữa.
        # (Gọi book_viewing hai lần là lỗi nghiêm trọng: tạo lịch trùng cho khách.)
        if "ĐẶT LỊCH THÀNH CÔNG" in prompt:
            ma = re.search(r"Mã xác nhận:\s*(BK\d+)", prompt)
            code = ma.group(1) if ma else "(xem Observation)"
            return (f"Thought: Observation của book_viewing đã xác nhận thành công, "
                    f"tôi không được gọi lại tool này nữa.\n"
                    f"Final Answer: Đã đặt lịch xem nhà thành công cho bạn, mã xác nhận {code}. "
                    f"Toàn bộ thông tin lấy nguyên văn từ Observation của Tool.")

        # Tool báo lỗi -> thừa nhận, KHÔNG bịa tiếp
        if "LỖI" in last_obs:
            return ("Thought: Tool báo lỗi, tôi không có bằng chứng hợp lệ nào để trả lời.\n"
                    "Final Answer: Xin lỗi, tôi chưa lấy được dữ liệu hợp lệ cho yêu cầu này. "
                    "Bạn vui lòng kiểm tra lại khu vực, khoảng giá và định dạng ngày giờ (YYYY-MM-DD, giờ tròn 08:00-17:00).")

        # ⚠️ BÀI HỌC TỪ MỘT BUG THẬT: trước đây hai biến này đọc `low` (TOÀN BỘ prompt,
        # kể cả lịch sử hội thoại). Chính câu trả lời của Agent ở lượt trước có chứa
        # cụm "mã đặt lịch", khiến lượt SAU tự kích hoạt đặt lịch dù khách chỉ hỏi
        # tìm nhà. Agent tự đầu độc ngữ cảnh của chính mình.
        # => Ý ĐỊNH phải đọc từ CÂU HỎI HIỆN TẠI, không phải từ cả transcript.
        cur = user_line.lower()

        # Bắt câu PHỦ ĐỊNH. Khớp chuỗi thô sẽ hiểu nhầm "tôi có bảo bạn đặt lịch gì đâu?"
        # thành yêu cầu đặt lịch. Đây là hạn chế cố hữu của keyword matching —
        # LLM thật hiểu được phủ định, mock thì phải chặn thủ công.
        phu_dinh = any(k in cur for k in [
            "gì đâu", "đâu?", "có bảo", "không đặt", "đừng đặt", "chưa đặt",
            "không phải đặt", "ai bảo", "sao lại đặt", "huỷ", "hủy"])

        muon_dat_lich = (not phu_dinh) and any(
            k in cur for k in ["đặt lịch", "đặt hẹn", "book", "hẹn xem"])
        muon_xem_gio = muon_dat_lich or ((not phu_dinh) and any(
            k in cur for k in ["khung giờ", "xem nhà", "khi nào", "còn trống", "giờ nào", "lịch trống"]))
        muon_chi_tiet = any(k in cur for k in ["chi tiết", "thông tin", "cụ thể", "như nào", "thế nào"])

        # Mã căn có thể đến từ 2 nguồn: Observation trong lượt này, HOẶC khối
        # "CÁC CĂN ĐÃ ĐỀ CẬP TRONG HỘI THOẠI" mà app.py chèn từ lịch sử chat.
        uuids = self._UUID_RE.findall(prompt)
        co_lich_su = "ĐÃ ĐỀ CẬP TRONG HỘI THOẠI" in prompt

        # --- Bước 1 ---
        if n_obs == 0:
            # Nếu lịch sử hội thoại đã có sẵn mã căn và khách muốn xem giờ/đặt lịch
            # thì KHÔNG cần tìm lại — dùng thẳng mã từ lịch sử. Đây chính là kịch bản
            # "khách nói 'đặt lịch căn đầu tiên' mà không biết UUID".
            co_ma_can = uuids and (co_lich_su or self._UUID_RE.search(user_line))

            if co_ma_can and muon_xem_gio:
                nguon = "lịch sử hội thoại" if co_lich_su else "chính câu hỏi của khách"
                return (f"Thought: Đã có mã căn {uuids[0]} từ {nguon}, "
                        f"không cần tìm lại và cũng không được hỏi khách mã căn.\n"
                        f"Action: check_viewing_slots[\"{uuids[0]}\"]")

            # Khách hỏi chi tiết căn đã nhắc tới -> xem chi tiết, TUYỆT ĐỐI không đặt lịch
            if co_ma_can and muon_chi_tiet:
                return (f"Thought: Khách hỏi chi tiết căn đã nhắc ở lượt trước. Lấy mã "
                        f"{uuids[0]} từ lịch sử. Khách KHÔNG yêu cầu đặt lịch nên tôi "
                        f"không được gọi book_viewing.\n"
                        f"Action: get_listing_details[\"{uuids[0]}\"]")

            quan, gmax, gmin, amin, amax = self._extract_params(cur)
            mo_ta = f"quận {quan}" + (f", giá <= {gmax}" if gmax else "") + \
                    (f", giá >= {gmin}" if gmin else "") + \
                    (f", >= {amin}m2" if amin else "") + (f", <= {amax}m2" if amax else "")
            return (f"Thought: Khách chưa cung cấp mã căn (khách không thể biết UUID), "
                    f"nên tôi phải tìm danh sách căn theo tiêu chí: {mo_ta}.\n"
                    f"Action: search_listings[\"{quan}\", \"{gmax}\", \"{amin}\", \"{amax}\", \"\", \"{gmin}\"]")

        # --- Từ bước 2: LẤY MÃ CĂN THẬT, không bịa ---
        if not uuids:
            return ("Thought: Chưa có mã căn nào trong Observation, tôi không thể đi tiếp.\n"
                    "Final Answer: Tôi chưa tìm được căn phù hợp để tra cứu lịch xem nhà.")
        ma_can = uuids[0]

        # Nếu đã dùng mã từ lịch sử thì Observation đầu tiên chính là khung giờ trống
        # -> đi thẳng sang bước đặt lịch.
        if co_lich_su and n_obs == 1 and muon_dat_lich:
            slots = self._SLOT_RE.findall(last_obs)
            dates = self._DATE_RE.findall(last_obs)
            if slots and dates:
                return (f"Thought: Observation cho thấy còn khung {slots[0]}:00 ngày {dates[-1]}. "
                        f"Tôi tiến hành đặt lịch cho khách.\n"
                        f"Action: book_viewing[\"{ma_can}\", \"{dates[-1]}\", \"{slots[0]}:00\", "
                        f"\"Nguyễn Quang Vinh\", \"0912345678\"]")
            return ("Thought: Căn này đã kín lịch, không còn khung giờ nào.\n"
                    "Final Answer: Căn bạn chọn đã kín lịch ngày đó. Bạn muốn đổi sang ngày khác không?")

        if n_obs == 1 and muon_xem_gio:
            return (f"Thought: Đã có mã căn {ma_can} từ Observation bước trước. "
                    f"Giờ tôi kiểm tra khung giờ trống của căn này.\n"
                    f"Action: check_viewing_slots[\"{ma_can}\"]")

        if n_obs == 2 and muon_dat_lich:
            slots = self._SLOT_RE.findall(last_obs)
            dates = self._DATE_RE.findall(last_obs)
            if not slots or not dates:
                return ("Thought: Căn này đã kín lịch, không còn khung giờ nào.\n"
                        "Final Answer: Căn bạn chọn đã kín lịch ngày đó. Bạn muốn đổi sang ngày khác không?")
            gio = f"{slots[0]}:00"
            ngay = dates[-1]
            return (f"Thought: Observation cho thấy còn khung {gio} ngày {ngay}. Khách đã cung cấp "
                    f"tên và số điện thoại nên tôi tiến hành đặt lịch.\n"
                    f"Action: book_viewing[\"{ma_can}\", \"{ngay}\", \"{gio}\", \"Nguyễn Quang Vinh\", \"0912345678\"]")

        return ("Thought: Tôi đã có đủ bằng chứng từ các Observation phía trên để trả lời.\n"
                "Final Answer: Đã xử lý xong yêu cầu của bạn. Mọi mã căn, khung giờ và mã đặt lịch "
                "nêu trên đều lấy nguyên văn từ Observation của Tool, không phải tôi suy đoán.")


def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    """Factory tự chọn Provider từ biến môi trường LLM_PROVIDER."""
    name = (provider_name or os.getenv("LLM_PROVIDER") or "mock").lower().strip()

    if name == "gemini":
        return GeminiProvider()
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name in ("custom", "compatible", "nvidia", "nim", "nvidia_nim",
                "groq", "together", "deepseek", "ollama", "vllm"):
        return CompatibleProvider()
    return MockProvider()


if __name__ == "__main__":
    print("=== TEST MULTI-PROVIDER LLM ADAPTER ===")
    provider = get_llm_provider()
    print(f"✅ Provider: {provider.__class__.__name__}")
    print(f"   Model   : {getattr(provider, 'model_name', '?')}")
    print(f"   Base URL: {getattr(provider, 'base_url', '(SDK riêng)')}")
    print(f"\n💬 Thử gọi: {provider.generate('Xin chào')[:200]}")
