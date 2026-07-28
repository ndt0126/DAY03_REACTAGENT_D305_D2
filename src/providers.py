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
    """Interface cơ sở cho tất cả các LLM Provider"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
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
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (GPT-4o, GPT-3.5-turbo, etc.)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
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
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider (Claude 3.5 Sonnet, Claude 3 Haiku)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-haiku-20240307"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
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
                
            response = client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            return f"[Anthropic Exception]: {str(e)}"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Provider (Hỗ trợ gọi mọi model qua OpenRouter API)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
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
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[OpenRouter API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[OpenRouter Exception]: {str(e)}"


class MockProvider(BaseLLMProvider):
    """Offline Mock Provider (Cho bài test không cần kết nối API)"""
    def __init__(self):
        self.model_name = "Offline Mock Engine"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        text = prompt.lower()
        
        # Checking if prompt contains previous observation
        if "observation:" in text:
            if "ap-102" in text and "đã xác nhận" not in text:
                if "chi tiết căn hộ" in text:
                    return (
                        "Thought: Đã xem chi tiết căn AP-102, tiến hành đặt lịch xem nhà cho khách hàng.\n"
                        "Action: book_viewing_schedule['AP-102', 'Nguyễn Văn A', '0912345678', '30/07/2026', '09:30']"
                    )
                return (
                    "Thought: Đã tìm thấy căn AP-102 phù hợp, tiếp theo xem chi tiết căn này.\n"
                    "Action: get_apartment_details['AP-102']"
                )
            elif "đặt lịch xem nhà thành công" in text or "bk-" in text:
                return (
                    "Thought: Tôi đã có đủ thông tin thực tế từ công cụ để hoàn tất trả lời.\n"
                    "Final Answer: Đã tìm thấy căn hộ Studio Bình Thạnh (AP-102) giá 7.2 tr/tháng. Đã đặt lịch xem nhà thành công với Mã hẹn BK-8821 vào lúc 09:30 ngày 30/07/2026 cho anh Nguyễn Văn A!"
                )
            elif "tìm thấy" in text and "cầu giấy" in text:
                return (
                    "Thought: Tôi đã có đủ thông tin các phòng trọ ở Cầu Giấy dưới 5 triệu.\n"
                    "Final Answer: Đã tìm thấy phòng trọ khép kín mã AP-101 tại Cầu Giấy giá 4.5 triệu/tháng đầy đủ nội thất (điều hòa, nóng lạnh, ban công)."
                )
            elif "lỗi" in text or "không tìm thấy" in text:
                return (
                    "Thought: Tool báo lỗi không tìm thấy địa điểm/mã căn hộ phù hợp.\n"
                    "Final Answer: Rất tiếc, hệ thống không tìm thấy căn hộ hợp lệ theo yêu cầu của bạn. Vui lòng kiểm tra lại thông tin mã phòng hoặc khu vực."
                )

        # Initial prompt handling
        if "cầu giấy" in text and "5 triệu" in text:
            return (
                "Thought: Cần tìm kiếm phòng trọ ở Cầu Giấy giá dưới 5 triệu.\n"
                "Action: search_apartments['Cầu Giấy', '5000000']"
            )
        elif "bình thạnh" in text or "1pn" in text or "đặt lịch" in text:
            return (
                "Thought: Cần tìm căn hộ 1PN / Studio ở Bình Thạnh giá dưới 8 triệu trước.\n"
                "Action: search_apartments['Bình Thạnh', '8000000', '1PN']"
            )
        elif "ap-99999" in text or "sao hỏa" in text:
            return (
                "Thought: Cần tra cứu chi tiết căn hộ AP-99999.\n"
                "Action: get_apartment_details['AP-99999']"
            )
        elif "kinh nghiệm" in text or "tân sinh viên" in text:
            return (
                "Ba kinh nghiệm quan trọng nhất khi thuê phòng trọ lần đầu:\n"
                "1. Kiểm tra kỹ hợp đồng thuê nhà: Tiền cọc, điều khoản tăng giá và thời hạn báo trước khi chuyển đi.\n"
                "2. Xác minh chi phí dịch vụ: Đơn giá điện, nước, internet, phí vệ sinh và gửi xe.\n"
                "3. Khảo sát trực tiếp phòng: An ninh khu vực, ngập nước khi mưa, khóa cổng và ánh sáng thông thoáng."
            )
        elif "hợp đồng" in text or "phí" in text:
            return (
                "Các khoản phí dịch vụ phổ biến trong hợp đồng thuê nhà:\n"
                "1. Tiền phòng cố định hàng tháng.\n"
                "2. Tiền điện (theo số kWh công tơ riêng) & Tiền nước (theo m3 hoặc đầu người).\n"
                "3. Phí dịch vụ chung: Wifi, vệ sinh hành lang, thang máy, phí gửi xe."
            )
            
        return (
            "Thought: Cần tìm kiếm phòng trọ theo yêu cầu người dùng.\n"
            "Action: search_apartments['Cầu Giấy', '5000000']"
        )



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
    else:
        return MockProvider()


if __name__ == "__main__":
    print("=== TEST MULTI-PROVIDER LLM ADAPTER ===")
    provider = get_llm_provider()
    print(f"✅ Provider đang dùng: {provider.__class__.__name__}")
    print(f"🤖 User Query: Hello")
    print(f"💬 Response  : {provider.generate('Hello')}")
