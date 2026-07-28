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
    SAMPLE_APARTMENTS,
    search_apartments, 
    get_apartment_details, 
    book_viewing_schedule, 
    check_schedule_status
)
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS
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
        return json.load(f)


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


def run_baseline_chatbot(user_query: str, provider=None):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    """
    if provider is None:
        provider = get_llm_provider()
        
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    return {
        "mode": "baseline",
        "user_query": user_query,
        "final_answer": response,
        "steps": [],
        "total_steps": 0,
        "guardrail_triggered": False
    }


def run_react_agent(user_query: str, provider=None):
    """
    Dựng vòng lặp ReAct Agent (Thought -> Action -> Observation) có Guardrails và Trace Log.
    """
    if provider is None:
        provider = get_llm_provider()
        
    steps_log = []
    current_prompt = f"User Request: {user_query}"
    step = 0
    final_answer = None
    guardrail_triggered = False

    while step < MAX_ITERATIONS:
        step += 1
        llm_response = provider.generate(current_prompt, system_prompt=REACT_SYSTEM_PROMPT)
        
        thought, action_name, args, parsed_final = parse_action_call(llm_response)
        
        step_record = {
            "step": step,
            "raw_response": llm_response,
            "thought": thought,
            "action": f"{action_name}{args}" if action_name else None,
            "action_name": action_name,
            "args": args,
            "observation": None,
            "final_answer": parsed_final
        }
        
        if parsed_final:
            final_answer = parsed_final
            steps_log.append(step_record)
            break
            
        if action_name:
            observation = execute_tool(action_name, args)
            step_record["observation"] = observation
            steps_log.append(step_record)
            
            # Cập nhật prompt với Observation cho bước suy luận tiếp theo
            current_prompt += f"\n\nThought: {thought}\nAction: {action_name}{args}\nObservation: {observation}\nThought:"
        else:
            # Không parse được action hay final answer
            final_answer = llm_response
            step_record["final_answer"] = final_answer
            steps_log.append(step_record)
            break

    if step >= MAX_ITERATIONS and not final_answer:
        guardrail_triggered = True
        final_answer = (
            f"🛡️ PHANH AN TOÀN (GUARDRAIL TRIGGERED): Đã đạt giới hạn tối đa {MAX_ITERATIONS} bước suy luận. "
            f"Hệ thống tạm ngắt lặp để đảm bảo an toàn. Vui lòng làm rõ thông tin hoặc thử lại!"
        )

    return {
        "mode": "react",
        "user_query": user_query,
        "final_answer": final_answer,
        "steps": steps_log,
        "total_steps": len(steps_log),
        "guardrail_triggered": guardrail_triggered
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
    """Trả về danh sách phòng trọ mẫu cho UI preview"""
    return jsonify(SAMPLE_APARTMENTS)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """API endpoint xử lý tin nhắn từ giao diện chatbot"""
    data = request.json or {}
    user_query = data.get("query", "").strip()
    mode = data.get("mode", "react").lower()
    
    if not user_query:
        return jsonify({"error": "Nội dung câu hỏi không được để trống"}), 400
        
    provider = get_llm_provider()
    
    if mode == "baseline":
        res = run_baseline_chatbot(user_query, provider)
    else:
        res = run_react_agent(user_query, provider)
        
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


