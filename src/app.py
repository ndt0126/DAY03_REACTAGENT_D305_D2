"""
🚀 CORE AGENT APP & WEB APPLICATION (Dành cho Role 4: Core Agent Developer / Integrator)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
Đồng thời khởi chạy WebApp Frontend "Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê".
"""

import json
import os
import sys
import re
import inspect
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import (
    AVAILABLE_TOOLS,
    get_sample_listings,
    get_all_bookings,
    search_listings,
    get_listing_details,
    check_viewing_slots,
    book_viewing,
    list_bookings,
)
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    MAX_REPEATED_ACTIONS,
    STOP_SEQUENCES,
    FALLBACK_MESSAGE,
)
from providers import get_llm_provider

load_dotenv()

# Đường dẫn thư mục Frontend (src/frontend)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(SRC_DIR, "frontend")

# Khởi tạo Flask App
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    config_path = os.path.join(BASE_DIR, "config", "test_cases.json")
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict) and "test_cases" in data:
            return data["test_cases"]
        return data



def parse_action_call(response_text: str):
    """
    Trích xuất Thought, Action (tên tool & tham số) hoặc Final Answer từ phản hồi của LLM.
    Hỗ trợ các định dạng:
    - Action: search_apartments['Cầu Giấy', '5000000']
    - Action: get_apartment_details['AP-101']
    - Action: book_viewing_schedule['AP-102', 'Nguyễn Văn A', '0912345678', '30/07/2026', '09:30']
    - Action: search_apartments(location='Cầu Giấy', max_price=5000000)
    """
    thought = ""
    action_name = None
    args = []
    final_answer = None

    # Tìm Thought
    thought_match = re.search(r'Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)', response_text, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()

    # Tìm Final Answer
    final_match = re.search(r'Final Answer:\s*(.*)', response_text, re.DOTALL)
    if final_match:
        final_answer = final_match.group(1).strip()
        return thought, None, [], final_answer

    # Tìm Action
    action_match = re.search(r'Action:\s*([a-zA-Z0-9_]+)[\(\[](.*?)[\)\]]', response_text, re.DOTALL)
    if action_match:
        action_name = action_match.group(1).strip()
        raw_args = action_match.group(2).strip()
        
        # Parse arguments
        if raw_args:
            # Tách tham số theo dấu phẩy, xử lý ngoặc kép/đơn
            parsed = re.findall(r'(?:[^\s,"\']|"(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\')+', raw_args)
            for item in parsed:
                clean_item = item.strip().strip("'\"")
                # Nếu dạng key=val -> lấy val
                if "=" in clean_item and not clean_item.startswith("http"):
                    parts = clean_item.split("=", 1)
                    clean_item = parts[1].strip().strip("'\"")
                args.append(clean_item)

    # Nếu không parse được theo cấu trúc ReAct nhưng có text trả về và không có Action
    if not action_name and not final_answer:
        # Nếu model trả về văn bản tự do không khớp pattern
        clean_text = re.sub(r'^Thought:\s*', '', response_text).strip()
        final_answer = clean_text

    return thought, action_name, args, final_answer


def execute_tool(action_name: str, args: list) -> str:
    """
    Thực thi Tool từ AVAILABLE_TOOLS một cách an toàn.
    """
    if action_name not in AVAILABLE_TOOLS:
        valid_tools = list(AVAILABLE_TOOLS.keys())
        return f"LỖI PHANH AN TOÀN: Công cụ '{action_name}' không tồn tại! Các công cụ hợp lệ gồm: {valid_tools}"

    tool_func = AVAILABLE_TOOLS[action_name]
    sig = inspect.signature(tool_func)
    param_names = list(sig.parameters.keys())

    try:
        if len(args) == 1 and len(param_names) >= 1:
            return tool_func(args[0])
        elif len(args) == 2 and len(param_names) >= 2:
            return tool_func(args[0], args[1])
        elif len(args) >= 3:
            # Map positional args to parameters
            kwargs = {}
            for i, p_name in enumerate(param_names):
                if i < len(args):
                    kwargs[p_name] = args[i]
            return tool_func(**kwargs)
        elif len(args) == 0 and len(param_names) == 0:
            return tool_func()
        else:
            return tool_func(*args)
    except Exception as e:
        return f"LỖI XỬ LÝ TOOL {action_name}: {str(e)}"


# =========================================================
# 🧠 BỘ NHỚ HỘI THOẠI — giải bài toán "khách không biết UUID"
# =========================================================

# UUID của căn hộ, dùng để moi lại mã căn đã xuất hiện ở các lượt chat trước
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

MAX_HISTORY_TURNS = 6        # số lượt chat gần nhất được đưa vào ngữ cảnh
MAX_CONTEXT_LISTINGS = 8     # số căn gần nhất được nhắc lại cho Agent


def build_conversation_context(history) -> str:
    """Dựng khối ngữ cảnh từ lịch sử chat để Agent tự tra ra mã căn.

    ═══ VÌ SAO CẦN HÀM NÀY? ═══
    Mã căn là UUID 36 ký tự. Khách hàng KHÔNG BAO GIỜ biết và không thể gõ ra.
    Trong thực tế khách chỉ nói "đặt lịch xem căn đầu tiên" hoặc "căn ở Xuân Thủy".

    Nếu mỗi lượt chat đều bắt đầu từ con số 0, Agent buộc phải hỏi khách mã căn
    (bất khả thi) hoặc tự bịa ra mã (ảo giác). Hàm này gom lại các căn đã xuất
    hiện ở những lượt trước, kèm mã UUID đầy đủ, để Agent đối chiếu.

    Args:
        history (list): [{"role": "user"|"assistant", "content": str}, ...]

    Returns:
        str: Khối ngữ cảnh chèn vào đầu transcript, hoặc "" nếu chưa có lịch sử.
    """
    if not history:
        return ""

    turns = [h for h in history if isinstance(h, dict) and h.get("content")]
    turns = turns[-MAX_HISTORY_TURNS * 2:]
    if not turns:
        return ""

    lines = ["=== LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ ==="]
    for h in turns:
        who = "Khách" if h.get("role") == "user" else "Trợ lý"
        content = str(h["content"]).strip().replace("\n", " ")
        if len(content) > 400:
            content = content[:400] + "..."
        lines.append(f"{who}: {content}")

    # Moi toàn bộ UUID đã từng xuất hiện, khử trùng lặp nhưng GIỮ THỨ TỰ
    # (thứ tự quan trọng: khách nói "căn đầu tiên" là căn nào)
    seen, uuids = set(), []
    for h in turns:
        for u in _UUID_RE.findall(str(h["content"])):
            ul = u.lower()
            if ul not in seen:
                seen.add(ul)
                uuids.append(ul)

    if uuids:
        lines.append("")
        lines.append("=== CÁC CĂN ĐÃ ĐỀ CẬP TRONG HỘI THOẠI (dùng mã này, ĐỪNG hỏi khách) ===")
        # Bổ sung địa chỉ + giá từ dữ liệu thật để Agent đối chiếu khi khách nói
        # "căn ở Xuân Thủy" hay "căn rẻ nhất"
        for i, u in enumerate(uuids[-MAX_CONTEXT_LISTINGS:], 1):
            info = get_listing_brief(u)
            lines.append(f"{i}. {u}" + (f" — {info}" if info else ""))

    lines.append("=== HẾT PHẦN LỊCH SỬ ===\n")
    return "\n".join(lines)


def get_listing_brief(ma_can: str) -> str:
    """Lấy mô tả ngắn của một căn để đính kèm vào ngữ cảnh hội thoại."""
    try:
        from tools import _load_listings
        item = _load_listings().get(ma_can)
        if not item:
            return ""
        return f"{item['dia_chi']}, {item['quan']} | {item['gia']:,} VNĐ/tháng | {item['dien_tich']}m2"
    except Exception:
        return ""


def run_baseline_chatbot(user_query: str, provider=None, history=None):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ: ĐÚNG 1 lần gọi LLM, 0 tool call.
    """
    if provider is None:
        provider = get_llm_provider()

    # Baseline cũng được cấp lịch sử hội thoại để so sánh CÔNG BẰNG với Agent.
    # Khác biệt duy nhất giữa hai hệ thống phải là CÓ/KHÔNG CÓ TOOL, không phải trí nhớ.
    prompt = user_query
    if history:
        turns = [h for h in history if isinstance(h, dict) and h.get("content")][-MAX_HISTORY_TURNS * 2:]
        if turns:
            hist = "\n".join(
                f"{'Khách' if h.get('role') == 'user' else 'Trợ lý'}: {str(h['content'])[:400]}"
                for h in turns)
            prompt = f"=== LỊCH SỬ HỘI THOẠI ===\n{hist}\n=== HẾT ===\n\nKhách hỏi: {user_query}"

    response = provider.generate(prompt, system_prompt=CHATBOT_BASELINE_PROMPT)
    return {
        "mode": "baseline",
        "user_query": user_query,
        "final_answer": response,
        "steps": [],
        "total_steps": 0,
        "tool_calls": 0,
        "guardrail_triggered": False,
        "stop_reason": "single_llm_call"
    }


def run_react_agent(user_query: str, provider=None, history=None):
    """Vòng lặp ReAct thật: LLM -> parse -> chạy Tool -> chèn Observation -> lặp.

    ═══ 4 BƯỚC MỖI VÒNG LẶP ═══
      [1] CALL LLM  — gửi transcript + stop sequence để LLM PHẢI dừng sau dòng Action
      [2] PARSE     — bóc `Action: ten_tool[args]` hoặc `Final Answer:`
      [3] EXECUTE   — tra AVAILABLE_TOOLS, gọi hàm Python THẬT
      [4] APPEND    — ỨNG DỤNG chèn `Observation: <kết quả thật>`, KHÔNG phải LLM

    ═══ 3 LỚP GUARDRAIL ═══
      • STOP_SEQUENCES       — chặn LLM tự bịa dòng Observation (phòng tuyến 1)
      • MAX_REPEATED_ACTIONS — phát hiện Agent kẹt lặp cùng một Action
      • MAX_ITERATIONS       — trần cứng, chi phí luôn có giới hạn

    Args:
        history (list): lịch sử chat [{"role","content"}], để Agent tự tra ra mã căn
                        UUID đã xuất hiện ở lượt trước mà không phải hỏi khách.
    """
    if provider is None:
        provider = get_llm_provider()

    steps_log = []
    tool_calls = 0
    llm_calls = 0
    action_history = []
    final_answer = None
    guardrail_triggered = False
    stop_reason = None

    # Transcript = BỘ NHỚ LÀM VIỆC của Agent. Mỗi vòng nó dài thêm một khối
    # Thought/Action/Observation và được gửi lại nguyên vẹn ở vòng sau.
    context_block = build_conversation_context(history)
    transcript = f"{context_block}Question: {user_query}\n"

    for step in range(1, MAX_ITERATIONS + 1):
        # ---------- [1] CALL LLM ----------
        llm_response = provider.generate(
            transcript,
            system_prompt=REACT_SYSTEM_PROMPT,
            stop=STOP_SEQUENCES,          # 🛡️ GUARDRAIL 1
        )
        llm_calls += 1

        # Provider lỗi (sai key, mất mạng...) -> dừng ngay, không đốt thêm vòng lặp
        if llm_response and llm_response.lstrip().startswith("[") and \
                any(t in llm_response[:40] for t in ("Error", "Exception")):
            stop_reason = "provider_error"
            final_answer = f"Không gọi được LLM. Chi tiết: {llm_response}"
            steps_log.append({"step": step, "raw_response": llm_response,
                              "thought": "", "action": None, "action_name": None,
                              "args": [], "observation": None,
                              "final_answer": final_answer, "error": True})
            break

        # ---------- [2] PARSE ----------
        thought, action_name, args, parsed_final = parse_action_call(llm_response)

        step_record = {
            "step": step,
            "raw_response": llm_response,
            "thought": thought,
            "action": f"{action_name}{args}" if action_name else None,
            "action_name": action_name,
            "args": args,
            "observation": None,
            "final_answer": None,
        }

        # ---------- [2a] LLM đã chốt câu trả lời ----------
        if parsed_final and action_name is None:
            final_answer = parsed_final
            stop_reason = "final_answer"
            step_record["final_answer"] = final_answer
            steps_log.append(step_record)
            break

        # ---------- [2b] Không parse được ----------
        # ⚠️ KHÔNG lấy text rác làm Final Answer (đó là đường để ảo giác lọt ra
        # thẳng cho người dùng). Thay vào đó dạy lại định dạng qua Observation.
        if action_name is None:
            hint = ("LỖI ĐỊNH DẠNG: Không tìm thấy dòng 'Action:' hoặc 'Final Answer:'. "
                    "Hãy xuất lại đúng mẫu: 'Action: ten_tool[\"tham_so\"]' "
                    "hoặc 'Final Answer: <câu trả lời>'.")
            step_record["observation"] = hint
            step_record["parse_error"] = True
            steps_log.append(step_record)
            transcript += f"{llm_response}\nObservation: {hint}\n"
            continue

        # ---------- 🛡️ GUARDRAIL 2: Repeated Action ----------
        signature = f"{action_name}({', '.join(map(str, args))})"
        if action_history.count(signature) >= MAX_REPEATED_ACTIONS:
            guardrail_triggered = True
            stop_reason = "repeated_action"
            final_answer = FALLBACK_MESSAGE
            step_record["observation"] = (
                f"🛡️ GUARDRAIL: Action '{signature}' đã lặp lại {MAX_REPEATED_ACTIONS} lần "
                f"mà không tiến triển. Ngắt vòng lặp an toàn.")
            step_record["final_answer"] = final_answer
            steps_log.append(step_record)
            break
        action_history.append(signature)

        # ---------- [3] EXECUTE — chạy hàm Python THẬT ----------
        observation = execute_tool(action_name, args)
        tool_calls += 1
        step_record["observation"] = observation
        step_record["is_error"] = str(observation).startswith("LỖI")
        steps_log.append(step_record)

        # ---------- [4] APPEND — ứng dụng chèn Observation ----------
        transcript += (f"Thought: {thought}\n"
                       f"Action: {action_name}[{', '.join(map(str, args))}]\n"
                       f"Observation: {observation}\n")

    # ---------- 🛡️ GUARDRAIL 3: hết ngân sách vòng lặp ----------
    if final_answer is None:
        guardrail_triggered = True
        stop_reason = "max_iterations"
        final_answer = (
            f"🛡️ PHANH AN TOÀN: Đã chạm giới hạn {MAX_ITERATIONS} bước suy luận mà chưa "
            f"có câu trả lời chắc chắn.\n\n{FALLBACK_MESSAGE}")

    return {
        "mode": "react",
        "user_query": user_query,
        "final_answer": final_answer,
        "steps": steps_log,
        "total_steps": len(steps_log),
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
        "guardrail_triggered": guardrail_triggered,
        "transcript": transcript,
    }


# =========================================================
# FLASK WEB SERVER ROUTES & APIS
# =========================================================

@app.route("/")
def serve_index():
    """Phục vụ trang giao diện webapp Chatbot từ src/frontend/index.html"""
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    """Phục vụ các file tĩnh trong src/frontend/"""
    return send_from_directory(FRONTEND_DIR, path)

@app.route("/api/test-cases", methods=["GET"])
def api_get_test_cases():
    """Trả về bộ test cases từ config/test_cases.json"""
    return jsonify(load_test_cases())

@app.route("/api/tools", methods=["GET"])
def api_get_tools():
    """Trả về danh sách các tool và mô tả spec"""
    tools_info = []
    for name, func in AVAILABLE_TOOLS.items():
        doc = inspect.getdoc(func) or "Không có mô tả"
        sig = str(inspect.signature(func))
        tools_info.append({
            "name": name,
            "signature": f"{name}{sig}",
            "description": doc
        })
    return jsonify(tools_info)

@app.route("/api/listings", methods=["GET"])
def api_get_listings():
    """Trả về vài căn đầu tiên từ listings.txt cho UI preview (không phải toàn bộ 10.000 căn)"""
    return jsonify(get_sample_listings(50))


@app.route("/api/bookings", methods=["GET"])
def api_get_bookings():
    """Trả về danh sách lịch hẹn xem nhà hiện có trong bookings.txt"""
    return jsonify(get_all_bookings())

@app.route("/api/providers", methods=["GET"])
def api_get_providers():
    """Trả về danh sách các LLM Provider hỗ trợ.

    ⚠️ BÀI HỌC TỪ MỘT BUG THẬT: trước đây danh sách này thiếu option "custom".
    Khi .env đặt LLM_PROVIDER=custom, không option nào được đánh dấu active,
    dropdown tự chọn option ĐẦU TIÊN (mock), rồi frontend gửi provider="mock"
    lên /api/chat — GHI ĐÈ hoàn toàn cấu hình .env. Kết quả: người dùng tưởng
    đang chạy NVIDIA NIM nhưng thực chất chạy MockProvider offline.
    => Danh sách phải luôn chứa provider đang cấu hình trong .env.
    """
    env_provider = (os.getenv("LLM_PROVIDER") or "mock").lower().strip()
    model = os.getenv("LLM_MODEL") or "mặc định"

    # Mọi endpoint tương thích OpenAI đều quy về một id chung là "custom"
    compatible = {"custom", "compatible", "nvidia", "nim", "nvidia_nim",
                  "groq", "together", "deepseek", "ollama", "vllm"}
    canonical = "custom" if env_provider in compatible else env_provider

    providers = [
        {"id": "custom", "name": f"⚙️ Endpoint theo .env ({model})"},
        {"id": "mock", "name": "🧪 Offline Mock (không cần API key)"},
        {"id": "gemini", "name": "Google Gemini"},
        {"id": "openai", "name": "OpenAI"},
        {"id": "anthropic", "name": "Anthropic Claude"},
        {"id": "openrouter", "name": "OpenRouter"},
    ]
    for p in providers:
        p["active"] = (p["id"] == canonical)

    # Lưới an toàn: luôn phải có đúng một option được chọn sẵn
    if not any(p["active"] for p in providers):
        providers[0]["active"] = True

    return jsonify({"providers": providers, "current": canonical, "model": model})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """API endpoint xử lý tin nhắn từ giao diện chatbot"""
    data = request.json or {}
    user_query = data.get("query", "").strip()
    mode = data.get("mode", "react").lower()
    provider_name = data.get("provider", None)
    # Lịch sử hội thoại do frontend gửi lên — nhờ nó Agent mới tra được mã căn UUID
    # từ các lượt chat trước thay vì phải hỏi khách (khách không thể biết UUID).
    history = data.get("history", []) or []

    if not user_query:
        return jsonify({"error": "Nội dung câu hỏi không được để trống"}), 400

    provider = get_llm_provider(provider_name)

    if mode == "baseline":
        res = run_baseline_chatbot(user_query, provider, history=history)
    else:
        res = run_react_agent(user_query, provider, history=history)
        
    res["provider"] = provider.__class__.__name__
    res["model"] = getattr(provider, "model_name", "Mock Model")
    return jsonify(res)



import socket

def find_available_port(default_port=5001):
    """
    Tự động tìm port còn trống nếu port 5000/5001 bị chiếm bởi macOS ControlCenter (AirPlay) 
    hoặc tiến trình cũ chưa giải phóng.
    """
    env_port = os.getenv("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
            
    port = default_port
    while port < default_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1
    return default_port


# =========================================================
# MAIN ENTRY POINT (CLI & WEB SERVER)
# =========================================================

if __name__ == "__main__":
    print("==========================================================================")
    print("🏫 VINUNI AI CODELAB - LAB 03: REACT AGENT TRỢ LÝ TÌM & ĐẶT LỊCH XEM NHÀ")
    print("==========================================================================")
    
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")
    
    # In thông tin chạy demo CLI
    print("--- 🚀 DEMO CHẠY TEST CASE #4 (MULTI-STEP AGENT) ---")
    sample_query = tests[3]["question"]
    print(f"❓ User Query: {sample_query}\n")
    
    react_res = run_react_agent(sample_query, provider)
    print(f"🏁 Final Answer: {react_res['final_answer']}")
    print(f"📊 Tổng số bước ReAct: {react_res['total_steps']}")
    for s in react_res['steps']:
        print(f"  [Step {s['step']}] Thought: {s['thought']}")
        if s['action']:
            print(f"  [Step {s['step']}] Action: {s['action']}")
        if s['observation']:
            print(f"  [Step {s['step']}] Observation:\n{s['observation']}\n")

    port = find_available_port(5001)
    print("\n==========================================================================")
    print(f"🌐 KHỞI CHẠY WEBAPP FRONTEND TẠI: http://127.0.0.1:{port}")
    print("==========================================================================")
    
    # Start Flask Server
    app.run(host="0.0.0.0", port=port, debug=False)


