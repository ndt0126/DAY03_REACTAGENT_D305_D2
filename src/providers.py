"""
🔌 MULTI-PROVIDER LLM ADAPTER (OpenAI, Gemini, Anthropic, OpenRouter & Offline Mock)
Hỗ trợ chuyển đổi linh hoạt giữa các nhà cung cấp AI chỉ bằng cách đổi biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
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
    """
    Interface cơ sở cho tất cả các LLM Provider.

    Tham số `stop` rất quan trọng với ReAct Agent: nó ép LLM DỪNG LẠI ngay sau khi
    sinh ra dòng `Action:`, để chính ứng dụng (không phải LLM) mới là bên chèn
    `Observation:` thật từ tool. Nếu thiếu phanh này, LLM sẽ tự bịa Observation.
    """
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        raise NotImplementedError


def _apply_stop(text: str, stop: list = None) -> str:
    """
    Cắt thủ công tại stop sequence đầu tiên tìm thấy.
    Dùng làm lớp bảo hiểm cho các provider không hỗ trợ stop natively (vd: Gemini),
    hoặc khi model phớt lờ stop sequence.
    """
    if not stop or not text:
        return text
    cut = len(text)
    for s in stop:
        idx = text.find(s)
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut].rstrip()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env!"
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents
            )
            return _apply_stop(response.text, stop)
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (GPT-4o, GPT-3.5-turbo, etc.)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env!"
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stop=stop or None,
            )
            return _apply_stop(response.choices[0].message.content, stop)
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider (Claude 3.5 Sonnet, Claude 3 Haiku)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-haiku-20240307"
        
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or self.api_key == "your_anthropic_api_key_here":
            return "[Anthropic Error]: Chưa cấu hình ANTHROPIC_API_KEY trong file .env!"
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            kwargs = {
                "model": self.model_name,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
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
    """OpenRouter Provider (Hỗ trợ gọi mọi model qua OpenRouter API)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or self.api_key == "your_openrouter_api_key_here":
            return "[OpenRouter Error]: Chưa cấu hình OPENROUTER_API_KEY trong file .env!"
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages
            }
            if stop:
                payload["stop"] = stop
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return _apply_stop(data["choices"][0]["message"]["content"], stop)
            else:
                return f"[OpenRouter API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[OpenRouter Exception]: {str(e)}"


class CompatibleProvider(BaseLLMProvider):
    """
    🔧 PROVIDER DÙNG CHUNG CHO CẢ NHÓM — endpoint cấu hình được hoàn toàn qua .env

    Hầu hết nhà cung cấp LLM hiện nay (NVIDIA NIM, Groq, Together, DeepSeek, vLLM
    tự host, LM Studio, Ollama...) đều expose endpoint TƯƠNG THÍCH CHUẨN OpenAI.
    Nghĩa là chỉ cần đổi `base_url` + `model` là chạy được, không cần SDK riêng.

    Nhờ vậy mỗi thành viên trong nhóm có thể dùng key/endpoint riêng của mình mà
    KHÔNG phải sửa một dòng code nào — chỉ sửa file .env của máy mình.

    Cấu hình trong .env:
        LLM_PROVIDER=custom
        LLM_BASE_URL=https://integrate.api.nvidia.com/v1
        LLM_API_KEY=nvapi-xxxxxxxx
        LLM_MODEL=meta/llama-3.3-70b-instruct

    Ví dụ endpoint khác cùng dùng được lớp này:
        Groq        -> https://api.groq.com/openai/v1
        Together    -> https://api.together.xyz/v1
        DeepSeek    -> https://api.deepseek.com/v1
        Ollama local-> http://localhost:11434/v1        (LLM_API_KEY điền bừa cũng được)
    """
    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        # Ưu tiên biến chung LLM_*, nhưng vẫn chấp nhận NVIDIA_* để tương thích ngược
        self.api_key = (api_key or os.getenv("LLM_API_KEY")
                        or os.getenv("NVIDIA_API_KEY"))
        self.model_name = model or os.getenv("LLM_MODEL") or self.DEFAULT_MODEL
        self.base_url = (base_url or os.getenv("LLM_BASE_URL")
                         or os.getenv("NVIDIA_BASE_URL") or self.DEFAULT_BASE_URL)

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        if not self.api_key or "your_" in str(self.api_key):
            return ("[LLM Error]: Chưa cấu hình LLM_API_KEY trong file .env! "
                    "Mẹo: đặt LLM_PROVIDER=mock để chạy thử offline không cần key.")
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.2,      # ReAct cần tính ổn định, không cần sáng tạo
                max_tokens=1024,
                stop=stop or None,
            )
            return _apply_stop(response.choices[0].message.content, stop)
        except Exception as e:
            return f"[LLM Exception @ {self.base_url}]: {str(e)}"


# Giữ tên cũ làm alias để code/tài liệu cũ không gãy
NvidiaProvider = CompatibleProvider


class MockProvider(BaseLLMProvider):
    """
    🧪 Offline Mock Provider — KHÔNG cần API key.

    Đây KHÔNG phải là bản in cứng kết quả. Mock này thực sự đọc transcript ReAct
    được truyền vào và sinh ra bước `Thought/Action` tiếp theo dựa trên số lượng
    `Observation:` đã có. Nhờ vậy vòng lặp ReAct thật trong app.py được chạy
    đầy đủ (parser, executor, guardrail) ngay cả khi offline.

    Mock cũng cố ý mô phỏng 2 loại lỗi để test khả năng phục hồi của Agent:
      - Gọi tool không tồn tại (Unknown Tool)
      - Lặp lại đúng một Action (Repeated Action -> chạm MAX_ITERATIONS)
    """
    model_name = "offline-mock-v2"

    # Từ khóa cho thấy người dùng cần TRA CỨU DỮ LIỆU THẬT (phải đi đường Agent).
    # Lưu ý: cố tình KHÔNG đưa "thuê"/"phòng trọ" vào đây, vì "thuê nhà cần lưu ý
    # gì" là câu hỏi kiến thức chung, không cần tool.
    _LOOKUP_KEYWORDS = ["tìm", "đặt lịch", "còn trống", "quận", "atlantis",
                        "khung giờ", "xem nhà", "apt0"]

    def _needs_lookup(self, text: str) -> bool:
        return any(k in text for k in self._LOOKUP_KEYWORDS)

    def generate(self, prompt: str, system_prompt: str = "", stop: list = None) -> str:
        is_react = "Thought:" in (system_prompt or "") or "ReAct" in (system_prompt or "")
        text = prompt.lower()

        # ---------- Chế độ Chatbot Baseline (1 lần gọi, không tool) ----------
        if not is_react:
            if self._needs_lookup(text):
                # Hành vi AN TOÀN: thừa nhận không có dữ liệu thay vì bịa
                return ("Tôi rất muốn giúp bạn, nhưng tôi là chatbot thuần và không có "
                        "công cụ tra cứu dữ liệu phòng trọ thời gian thực. Tôi không thể "
                        "biết phòng nào còn trống, giá bao nhiêu, hay đặt lịch xem nhà "
                        "giúp bạn được.")
            return ("🤖 [Mock Chatbot]: Đây là câu trả lời tổng quát dựa trên kiến thức "
                    "chung (ví dụ: đọc kỹ điều khoản đặt cọc, thời hạn hợp đồng, chi phí "
                    "điện nước). Loại câu hỏi này KHÔNG cần tra cứu dữ liệu thời gian thực.")

        # ---------- Chế độ ReAct ----------
        n_obs = prompt.count("Observation:")
        last_obs = prompt.rsplit("Observation:", 1)[-1] if n_obs else ""

        # Câu hỏi lý thuyết -> trả lời ngay, KHÔNG tiêu tốn tool.
        # Đây là hành vi đúng: agent thông minh biết khi nào KHÔNG cần dùng tool.
        if not self._needs_lookup(text) and n_obs == 0:
            return ("Thought: Câu hỏi này chỉ cần kiến thức chung, không có tool nào tra cứu "
                    "được và cũng không cần thiết.\n"
                    "Final Answer: Đây là câu trả lời trực tiếp từ kiến thức có sẵn "
                    "(không cần bằng chứng từ tool).")

        # 🔴 Test case bẫy: quận không tồn tại. Mock cố tình đóng vai một LLM "cứng
        # đầu" — thất bại rồi vẫn thử lại y hệt. Mục đích: ép guardrail
        # MAX_REPEATED_ACTIONS lộ diện, chứng minh phanh an toàn thật sự hoạt động.
        if "atlantis" in text:
            return ("Thought: Người dùng muốn tìm phòng ở quận Atlantis, tôi thử tra cứu.\n"
                    "Action: search_listings[\"Atlantis\", \"5000000\"]")

        # Nếu observation trước báo lỗi -> Agent thừa nhận, KHÔNG bịa tiếp
        if "LỖI" in last_obs:
            return ("Thought: Tool báo lỗi và tôi không có bằng chứng hợp lệ nào.\n"
                    "Final Answer: Xin lỗi, tôi không tìm thấy dữ liệu hợp lệ cho yêu cầu này. "
                    "Bạn vui lòng kiểm tra lại tên khu vực và định dạng ngày (YYYY-MM-DD) nhé.")

        # Chuỗi tool phụ thuộc nhau: search -> check slots -> (book nếu được yêu cầu)
        wants_booking = "đặt lịch" in text
        # Chỉ tra khung giờ khi người dùng thực sự hỏi về lịch xem nhà.
        # Nếu họ chỉ hỏi "có phòng nào không" thì dừng sau 1 tool là ĐÚNG —
        # gọi thừa tool cũng là một dạng lỗi (lãng phí chi phí orchestration).
        wants_slots = wants_booking or any(k in text for k in ["khung giờ", "xem nhà", "khi nào"])

        if n_obs == 0:
            return ("Thought: Tôi cần tra cứu danh sách phòng thực tế trước, chưa thể biết mã căn nào.\n"
                    "Action: search_listings[\"Cầu Giấy\", \"5000000\"]")
        if n_obs == 1 and wants_slots:
            return ("Thought: Đã có mã căn APT001 từ Observation. Giờ tôi kiểm tra khung giờ xem nhà.\n"
                    "Action: check_viewing_slots[\"APT001\"]")
        if n_obs == 2 and wants_booking:
            return ("Thought: Đã có khung giờ trống từ Observation. Người dùng yêu cầu đặt lịch "
                    "nên tôi tiến hành đặt khung giờ sớm nhất.\n"
                    "Action: book_viewing[\"APT001\", \"2026-07-29 09:00\"]")

        return ("Thought: Tôi đã có đủ bằng chứng từ các Observation để trả lời.\n"
                "Final Answer: Căn APT001 (Studio full nội thất, 4.500.000 VNĐ/tháng, 28m2) tại "
                "Cầu Giấy phù hợp ngân sách của bạn. Mọi thông tin trên đều lấy nguyên văn từ "
                "Observation của tool, không phải do tôi suy đoán.")


def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    """Factory function tự chọn Provider từ biến môi trường LLM_PROVIDER"""
    name = (provider_name or os.getenv("LLM_PROVIDER") or "mock").lower().strip()

    if name == "gemini":
        return GeminiProvider()
    elif name == "openai":
        return OpenAIProvider()
    elif name == "anthropic":
        return AnthropicProvider()
    elif name == "openrouter":
        return OpenRouterProvider()
    elif name in ("custom", "compatible", "nvidia", "nim", "nvidia_nim",
                  "groq", "together", "deepseek", "ollama", "vllm"):
        # Mọi endpoint tương thích chuẩn OpenAI đều đi chung một lớp này
        return CompatibleProvider()
    else:
        return MockProvider()


if __name__ == "__main__":
    print("=== TEST MULTI-PROVIDER LLM ADAPTER ===")
    provider = get_llm_provider()
    print(f"✅ Provider đang dùng: {provider.__class__.__name__}")
    print(f"🤖 User Query: Hello")
    print(f"💬 Response  : {provider.generate('Hello')}")
