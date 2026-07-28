"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer / Integrator)

File chính ghép nối: Tools (Role 2) + Prompts (Role 3) + Test Cases (Role 1)
+ Multi-Provider Adapter, rồi chạy hai hệ thống để so sánh:

    • run_baseline_chatbot()  — Cấp độ 2: ĐÚNG 1 lần gọi LLM, 0 tool call
    • run_react_agent()       — Cấp độ 3: vòng lặp Thought -> Action -> Observation

═══════════════════════════════════════════════════════════════════════════
 KIẾN TRÚC VÒNG LẶP REACT (đọc kỹ phần này trước khi sửa code)
═══════════════════════════════════════════════════════════════════════════
Mỗi vòng lặp gồm 4 bước tách bạch:

  [1] CALL LLM   — gửi toàn bộ transcript, yêu cầu sinh bước tiếp theo.
                   Dùng stop sequence để LLM PHẢI dừng sau dòng Action.
  [2] PARSE      — regex bóc `Action: ten_tool[args]` hoặc `Final Answer:`.
  [3] EXECUTE    — tra tool trong AVAILABLE_TOOLS và gọi hàm Python THẬT.
  [4] APPEND     — chèn `Observation: <kết quả thật>` vào transcript, quay lại [1].

👉 Điểm mấu chốt: Observation do ỨNG DỤNG chèn, KHÔNG phải do LLM sinh ra.
   Nếu để LLM tự viết Observation thì toàn bộ bài lab trở thành ảo giác có
   định dạng đẹp — đây chính là lỗi mà CODELAB cảnh báo.

Cách chạy:
    python src/app.py              # chạy toàn bộ 5 test case
    python src/app.py 4            # chỉ chạy test case số 4
    python src/app.py --chat       # chế độ hỏi đáp tương tác
"""

import json
import os
import re
import sys
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from tools import AVAILABLE_TOOLS
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════
# 📥 NẠP TEST CASES (Role 1)
# ═══════════════════════════════════════════════════════════════════════════
def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1.

    Chấp nhận cả 2 định dạng để Role 1 tự do đổi cấu trúc file mà không làm gãy app:
      • Dạng cũ : [ {...}, {...} ]                      (list thuần)
      • Dạng mới: { "_meta": {...}, "test_cases": [...] } (có khối metadata)
    """
    config_path = os.path.join(BASE_DIR, "config", "test_cases.json")
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"] if isinstance(data, dict) else data


# ═══════════════════════════════════════════════════════════════════════════
# 🔍 BƯỚC [2]: PARSER — bóc Action / Final Answer ra khỏi text của LLM
# ═══════════════════════════════════════════════════════════════════════════

# Chấp nhận cả ngoặc vuông và ngoặc tròn vì LLM hay dùng lẫn lộn:
#   search_listings["Cầu Giấy", "5000000"]   /   search_listings('Cầu Giấy', 5000000)
_ACTION_RE = re.compile(
    r"Action\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*[\[\(](.*?)[\]\)]\s*$",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)
_THOUGHT_RE = re.compile(r"Thought\s*:\s*(.+?)(?=\n\s*(?:Action|Final\s*Answer)\s*:|$)",
                         re.IGNORECASE | re.DOTALL)


def parse_arguments(raw_args: str):
    """Tách chuỗi tham số thô thành list, tôn trọng dấu ngoặc kép.

    Ví dụ: '"Cầu Giấy", "5000000"'  ->  ['Cầu Giấy', '5000000']
           'APT001'                 ->  ['APT001']
           '"2026-07-29 09:00"'     ->  ['2026-07-29 09:00']

    Không dùng split(',') thô vì tham số có thể chứa dấu phẩy bên trong ngoặc kép.
    """
    if not raw_args or not raw_args.strip():
        return []

    args, current, in_quotes, quote_char = [], [], False, None
    for ch in raw_args:
        if ch in ("'", '"'):
            if not in_quotes:
                in_quotes, quote_char = True, ch
            elif ch == quote_char:
                in_quotes, quote_char = False, None
            else:
                current.append(ch)
        elif ch == "," and not in_quotes:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    args.append("".join(current).strip())

    # Bỏ ngoặc kép còn sót và loại bỏ phần tử rỗng ở cuối
    return [a.strip().strip("'\"").strip() for a in args if a.strip()]


def parse_llm_output(text: str) -> dict:
    """Phân loại output của LLM thành 1 trong 3 dạng: final / action / unparseable."""
    text = (text or "").strip()

    thought_m = _THOUGHT_RE.search(text)
    thought = thought_m.group(1).strip() if thought_m else ""

    # Ưu tiên kiểm tra Final Answer trước: nếu LLM đã chốt thì không cần gọi tool nữa
    final_m = _FINAL_RE.search(text)
    if final_m:
        return {"type": "final", "thought": thought, "answer": final_m.group(1).strip()}

    action_m = _ACTION_RE.search(text)
    if action_m:
        return {
            "type": "action",
            "thought": thought,
            "tool": action_m.group(1).strip(),
            "args": parse_arguments(action_m.group(2)),
            "raw_action": action_m.group(0).strip(),
        }

    return {"type": "unparseable", "thought": thought, "raw": text}


# ═══════════════════════════════════════════════════════════════════════════
# ⚙️ BƯỚC [3]: EXECUTOR — gọi hàm Python thật, không bao giờ để crash
# ═══════════════════════════════════════════════════════════════════════════
def execute_tool(tool_name: str, args: list) -> str:
    """Tra tool trong registry rồi thực thi. Mọi lỗi đều trở thành Observation."""
    fn = AVAILABLE_TOOLS.get(tool_name)

    # Failure Mode 1: Unknown Tool — trả lỗi kèm danh sách hợp lệ để Agent tự sửa
    if fn is None:
        return (f"LỖI: Không tồn tại tool tên '{tool_name}'. "
                f"Các tool hợp lệ: {', '.join(AVAILABLE_TOOLS.keys())}.")

    # Failure Mode 2: Malformed Args — sai số lượng tham số
    try:
        import inspect
        sig = inspect.signature(fn)
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        if len(args) < len(required):
            return (f"LỖI: Tool '{tool_name}' cần ít nhất {len(required)} tham số "
                    f"({', '.join(p.name for p in required)}), nhưng chỉ nhận được {len(args)}. "
                    f"Cú pháp đúng: {tool_name}[{', '.join(sig.parameters.keys())}]")
        if len(args) > len(sig.parameters):
            args = args[:len(sig.parameters)]  # cắt bớt tham số thừa thay vì báo lỗi
        return fn(*args)
    except Exception as e:
        # Lưới an toàn cuối cùng: kể cả tool viết ẩu cũng không được làm sập app
        return f"LỖI: Thực thi '{tool_name}' thất bại ({type(e).__name__}: {e})."


# ═══════════════════════════════════════════════════════════════════════════
# 💬 HỆ THỐNG 1 — CHATBOT BASELINE (Cấp độ 2)
# ═══════════════════════════════════════════════════════════════════════════
def run_baseline_chatbot(user_query: str, provider, verbose: bool = True) -> dict:
    """ĐÚNG 1 lần gọi LLM, KHÔNG tool, KHÔNG nhúng dữ liệu — để so sánh công bằng."""
    if verbose:
        print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")

    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)

    if verbose:
        print(f"🤖 Trả lời:\n{response}")
        print("📊 Telemetry: llm_calls=1 | tool_calls=0 | grounded=False")

    return {"answer": response, "llm_calls": 1, "tool_calls": 0, "trace": []}


# ═══════════════════════════════════════════════════════════════════════════
# 🧠 HỆ THỐNG 2 — REACT AGENT (Cấp độ 3) — TRÁI TIM CỦA BÀI LAB
# ═══════════════════════════════════════════════════════════════════════════
def run_react_agent(user_query: str, provider, verbose: bool = True) -> dict:
    """Vòng lặp ReAct thật: LLM -> parse -> execute tool -> chèn Observation -> lặp.

    Returns:
        dict: answer, số vòng lặp, số tool call, lý do dừng và trace đầy đủ
              (dùng cho báo cáo docs/trace_eval.md của Role 5).
    """
    if verbose:
        print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
        print(f"🛡️ Guardrails: MAX_ITERATIONS={MAX_ITERATIONS}, "
              f"MAX_REPEATED_ACTIONS={MAX_REPEATED_ACTIONS}")

    # Transcript là BỘ NHỚ LÀM VIỆC của agent. Mỗi vòng lặp nó dài thêm một khối
    # Thought/Action/Observation, và được gửi lại nguyên vẹn cho LLM ở vòng sau.
    # Đây chính là cơ chế "Observation quay lại prompt" mà CODELAB yêu cầu.
    transcript = f"Question: {user_query}\n"

    trace = []
    tool_calls = 0
    llm_calls = 0
    action_history = []      # để phát hiện Repeated Action
    stop_reason = None
    final_answer = None

    for step in range(1, MAX_ITERATIONS + 1):
        if verbose:
            print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        # ---------- [1] CALL LLM ----------
        raw = provider.generate(
            transcript,
            system_prompt=REACT_SYSTEM_PROMPT,
            stop=STOP_SEQUENCES,
        )
        llm_calls += 1

        if raw and raw.startswith("["):  # provider trả về lỗi kiểu [NVIDIA Error]: ...
            if any(tag in raw[:30] for tag in ["Error", "Exception"]):
                stop_reason = "provider_error"
                final_answer = f"Không gọi được LLM. Chi tiết: {raw}"
                trace.append({"step": step, "type": "provider_error", "raw": raw})
                if verbose:
                    print(f"❌ {raw}")
                break

        parsed = parse_llm_output(raw)

        if parsed.get("thought") and verbose:
            print(f"🧠 Thought: {parsed['thought']}")

        # ---------- [2a] LLM đã chốt câu trả lời ----------
        if parsed["type"] == "final":
            final_answer = parsed["answer"]
            stop_reason = "final_answer"
            transcript += f"Thought: {parsed['thought']}\nFinal Answer: {final_answer}\n"
            trace.append({"step": step, "type": "final",
                          "thought": parsed["thought"], "answer": final_answer})
            if verbose:
                print(f"🏁 Final Answer: {final_answer}")
            break

        # ---------- [2b] LLM xuất ra text không đúng định dạng ----------
        if parsed["type"] == "unparseable":
            # Không bỏ cuộc ngay: dạy lại định dạng cho LLM qua chính Observation.
            hint = ("LỖI ĐỊNH DẠNG: Không tìm thấy dòng 'Action:' hoặc 'Final Answer:'. "
                    "Hãy xuất lại theo đúng mẫu: 'Action: ten_tool[\"tham_so\"]' "
                    "hoặc 'Final Answer: ...'.")
            transcript += f"{raw}\nObservation: {hint}\n"
            trace.append({"step": step, "type": "parse_error", "raw": raw})
            if verbose:
                print(f"⚠️ Output không parse được:\n{raw}\n👁️ Observation: {hint}")
            continue

        # ---------- [2c] LLM yêu cầu gọi tool ----------
        tool_name, args = parsed["tool"], parsed["args"]
        signature = f"{tool_name}({', '.join(args)})"

        if verbose:
            print(f"🛠️ Action: {tool_name}{args}")

        # 🛡️ GUARDRAIL: Repeated Action — agent bị kẹt gọi đi gọi lại y hệt
        if action_history.count(signature) >= MAX_REPEATED_ACTIONS:
            stop_reason = "repeated_action"
            final_answer = FALLBACK_MESSAGE
            trace.append({"step": step, "type": "guardrail_repeated", "action": signature})
            if verbose:
                print(f"🛡️ GUARDRAIL: Action '{signature}' đã lặp lại "
                      f"{MAX_REPEATED_ACTIONS} lần. Ngắt vòng lặp an toàn!")
            break
        action_history.append(signature)

        # ---------- [3] EXECUTE — chạy hàm Python THẬT ----------
        observation = execute_tool(tool_name, args)
        tool_calls += 1

        if verbose:
            print(f"👁️ Observation: {observation}")

        # ---------- [4] APPEND — ứng dụng chèn Observation, KHÔNG phải LLM ----------
        transcript += (f"Thought: {parsed['thought']}\n"
                       f"Action: {tool_name}[{', '.join(args)}]\n"
                       f"Observation: {observation}\n")

        trace.append({
            "step": step, "type": "action",
            "thought": parsed["thought"], "tool": tool_name,
            "args": args, "observation": observation,
            "is_error": observation.startswith("LỖI"),
        })

    # 🛡️ GUARDRAIL: hết ngân sách vòng lặp mà chưa có Final Answer
    if final_answer is None:
        stop_reason = "max_iterations"
        final_answer = FALLBACK_MESSAGE
        if verbose:
            print(f"\n🛡️ GUARDRAIL TRIGGERED: Đã chạm giới hạn {MAX_ITERATIONS} bước "
                  f"mà chưa có Final Answer. Ngắt lặp an toàn!")
            print(f"🏁 Fallback:\n{final_answer}")

    if verbose:
        print(f"\n📊 Telemetry: llm_calls={llm_calls} | tool_calls={tool_calls} | "
              f"steps={len(trace)} | stop_reason={stop_reason}")

    return {
        "answer": final_answer,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "steps": len(trace),
        "stop_reason": stop_reason,
        "trace": trace,
        "transcript": transcript,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 🎁 BONUS (Cấp độ 4) — AUTONOMOUS: Planning + Memory
# ═══════════════════════════════════════════════════════════════════════════
def run_autonomous_agent(goal: str, provider, verbose: bool = True) -> dict:
    """Agent tự chia mục tiêu lớn thành các mục tiêu con, rồi giải từng cái bằng
    ReAct, MANG THEO bộ nhớ kết quả của các bước trước (đây là điểm khác Cấp 3).

    Cấp 3 chỉ phản ứng với câu hỏi hiện tại. Cấp 4 lập kế hoạch trước và tích luỹ
    bộ nhớ xuyên suốt nhiều nhiệm vụ con.
    """
    if verbose:
        print(f"\n🚀 [AUTONOMOUS AGENT] Mục tiêu: {goal}")

    plan_prompt = (
        "Hãy chia mục tiêu sau thành TỐI ĐA 3 nhiệm vụ con tuần tự, mỗi nhiệm vụ 1 dòng, "
        "đánh số 1. 2. 3. Không giải thích thêm.\n"
        f"Mục tiêu: {goal}"
    )
    plan_raw = provider.generate(plan_prompt, system_prompt="Bạn là chuyên gia lập kế hoạch.")
    subtasks = [re.sub(r"^\s*\d+[\.\)]\s*", "", ln).strip()
                for ln in (plan_raw or "").split("\n")
                if re.match(r"^\s*\d+[\.\)]", ln)][:3]

    if not subtasks:
        subtasks = [goal]  # fallback: không lập được kế hoạch thì làm thẳng

    if verbose:
        print("📋 Kế hoạch (Planning):")
        for i, t in enumerate(subtasks, 1):
            print(f"   {i}. {t}")

    memory = []  # 🧠 MEMORY: kết quả các nhiệm vụ con được mang sang bước sau
    for i, task in enumerate(subtasks, 1):
        if verbose:
            print(f"\n═══ Nhiệm vụ con {i}/{len(subtasks)}: {task} ═══")
        context = ""
        if memory:
            context = "Bối cảnh từ các bước đã hoàn thành:\n" + "\n".join(
                f"- {m['task']} => {m['result']}" for m in memory) + "\n\n"
        result = run_react_agent(context + task, provider, verbose=verbose)
        memory.append({"task": task, "result": result["answer"]})

    if verbose:
        print(f"\n🧠 Bộ nhớ tích luỹ sau {len(memory)} nhiệm vụ con:")
        for m in memory:
            print(f"   • {m['task']}\n     -> {m['result'][:120]}...")

    return {"goal": goal, "plan": subtasks, "memory": memory,
            "answer": memory[-1]["result"] if memory else ""}


# ═══════════════════════════════════════════════════════════════════════════
# 🏁 MAIN
# ═══════════════════════════════════════════════════════════════════════════
def print_header(provider):
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print("=" * 70)
    print("🏫 VINUNI — LAB 3: CHATBOT vs REACT AGENT")
    print("🏠 Chủ đề: Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê")
    print("=" * 70)
    print(f"🔌 Provider: {provider.__class__.__name__} (Model: {model_name})")
    print(f"🛠️ Tools nạp được: {len(AVAILABLE_TOOLS)} -> {', '.join(AVAILABLE_TOOLS.keys())}")


def run_interactive(provider):
    """Chế độ hỏi đáp tương tác — tiện cho phần demo và cross-audit ở Mốc 4."""
    print("\n💬 CHẾ ĐỘ TƯƠNG TÁC (gõ 'exit' để thoát)")
    while True:
        try:
            q = input("\n👤 Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("exit", "quit", "thoat"):
            break
        run_react_agent(q, provider)


if __name__ == "__main__":
    provider = get_llm_provider()
    print_header(provider)

    if "--chat" in sys.argv:
        run_interactive(provider)
        sys.exit(0)

    tests = load_test_cases()
    print(f"✅ Đã tải {len(tests)} test cases từ config/test_cases.json")

    # Cho phép chạy 1 test riêng lẻ: python src/app.py 4
    selected = [t for t in tests if str(t["id"]) in sys.argv] or tests

    summary = []
    for tc in selected:
        print("\n" + "█" * 70)
        print(f"█ TEST CASE #{tc['id']} — {tc['category']}")
        print(f"█ {tc['question']}")
        print("█" * 70)

        print("\n────────── HỆ THỐNG 1: CHATBOT BASELINE (Cấp 2) ──────────")
        base = run_baseline_chatbot(tc["question"], provider)

        print("\n────────── HỆ THỐNG 2: REACT AGENT (Cấp 3) ──────────")
        agent = run_react_agent(tc["question"], provider)

        summary.append({
            "id": tc["id"],
            "expected_tool_calls": tc.get("expected_tool_calls", "-"),
            "agent_tool_calls": agent["tool_calls"],
            "stop_reason": agent["stop_reason"],
        })

    print("\n" + "=" * 70)
    print("📊 BẢNG TỔNG KẾT (dán vào docs/trace_eval.md)")
    print("=" * 70)
    print(f"{'Case':<6}{'Tool calls kỳ vọng':<22}{'Agent thực tế':<16}{'Lý do dừng'}")
    print("-" * 70)
    for s in summary:
        print(f"#{s['id']:<5}{str(s['expected_tool_calls']):<22}"
              f"{s['agent_tool_calls']:<16}{s['stop_reason']}")
    print("=" * 70)
    print("💡 Chatbot Baseline luôn có tool_calls = 0 ở mọi case — đó chính là "
          "giới hạn cốt lõi của Cấp độ 2.")
