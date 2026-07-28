"""
📊 EVALUATION RUNNER (Dành cho Role 5: Observability)

Chạy test cases qua CẢ HAI hệ thống (Chatbot Baseline + ReAct Agent), in ĐẦY ĐỦ
nội dung hội thoại, tự chấm rubric 0-2, và chạy kịch bản CHỨNG MINH AGENT CÓ MEMORY.

═══════════════════════════════════════════════════════════════════════════
 CÁCH DÙNG
═══════════════════════════════════════════════════════════════════════════
    python src/run_eval.py                        # 13 case + demo memory, in đầy đủ
    python src/run_eval.py --out docs/rubric.md   # ghi kết quả ra file Markdown
    python src/run_eval.py --memory-only          # CHỈ chạy demo memory (tiết kiệm quota)
    python src/run_eval.py --case 5               # chỉ chạy 1 case
    python src/run_eval.py --provider mock        # chạy offline không tốn quota
    python src/run_eval.py --max-chars 300        # cắt bớt output cho gọn (mặc định: không cắt)

═══════════════════════════════════════════════════════════════════════════
 CÁCH CHẤM RUBRIC (0-2 điểm mỗi tiêu chí)
═══════════════════════════════════════════════════════════════════════════
Script chấm TỰ ĐỘNG các tiêu chí đo được bằng máy và đánh dấu ⚠️ chỗ cần người xem.

  • Tool selection : so số tool call thực tế với `expected_tool_calls`
  • Termination    : dựa vào stop_reason
  • Grounding      : đối chiếu MỌI mã căn / mã BK / số tiền trong Final Answer
                     với nội dung các Observation. Bịa số nào không có -> 0 điểm.
  • Factual        : ⚠️ cần người đọc; máy chỉ chấm 0 khi phát hiện bịa rõ ràng
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import (run_baseline_chatbot, run_react_agent, load_test_cases,
                 build_conversation_context)
from providers import get_llm_provider
from prompts import MAX_ITERATIONS, MAX_REPEATED_ACTIONS

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
BK_RE = re.compile(r"\bBK\d{3,}\b")
MONEY_RE = re.compile(r"\b\d{1,3}(?:[.,]\d{3})+\b")

MAX_CHARS = 0   # 0 = in đầy đủ, không cắt


def cut(text, limit=None):
    """Cắt chuỗi theo MAX_CHARS. limit=0 hoặc None nghĩa là in đầy đủ."""
    text = str(text or "")
    lim = MAX_CHARS if limit is None else limit
    if not lim or len(text) <= lim:
        return text
    return text[:lim] + f"… [cắt bớt, tổng {len(text)} ký tự]"


def collect_uuids(result):
    """Lấy mọi mã căn UUID xuất hiện trong các Observation, giữ nguyên thứ tự."""
    out = []
    for s in result.get("steps", []):
        for u in UUID_RE.findall(str(s.get("observation") or "")):
            if u.lower() not in out:
                out.append(u.lower())
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 🏅 CHẤM RUBRIC
# ═══════════════════════════════════════════════════════════════════════════

def _expected_range(exp):
    if isinstance(exp, int):
        return exp, exp
    nums = [int(x) for x in re.findall(r"\d+", str(exp))]
    return (min(nums), max(nums)) if nums else (None, None)


def score_tool_selection(result, expected):
    lo, hi = _expected_range(expected)
    n = result.get("tool_calls", 0)
    if lo is None:
        return 1, "không có kỳ vọng rõ ràng"
    if lo <= n <= hi:
        return 2, f"gọi {n} tool, đúng kỳ vọng {expected}"
    if any(s.get("is_error") for s in result.get("steps", [])):
        return 1, f"gọi {n} tool (kỳ vọng {expected}) nhưng có tự phục hồi sau lỗi"
    if n == 0 and lo > 0:
        return 0, f"KHÔNG gọi tool nào dù cần {expected} — trả lời không có bằng chứng"
    return 0, f"gọi {n} tool, lệch kỳ vọng {expected}"


def score_termination(result):
    reason = result.get("stop_reason")
    if reason in ("empty_response", "eval_crash"):
        return 0, f"model không trả về nội dung dùng được ({reason})"
    if reason in ("final_answer", "single_llm_call"):
        steps = result.get("total_steps", 0)
        return (2, f"dừng đúng lúc ({reason}, {steps} bước)") if steps <= MAX_ITERATIONS \
            else (1, f"dừng nhưng thừa bước ({steps})")
    if reason in ("repeated_action", "max_iterations"):
        return 2, f"Guardrail ngắt an toàn ({reason})"
    if reason == "provider_error":
        return 0, "lỗi provider, không hoàn thành"
    return 1, f"stop_reason = {reason}"


def score_grounding(result, expected_tool_calls=None):
    """Đối chiếu dữ kiện trong Final Answer với các Observation.

    ⚠️ SỬA LỖI QUAN TRỌNG: bản trước cứ thấy `tool_calls == 0` là cho 2 điểm với
    lý do "câu hỏi kiến thức chung". Nhưng nếu Agent KHÔNG gọi tool mà VẪN nêu mã
    căn / giá / địa chỉ cụ thể thì đó chính là ẢO GIÁC — phải chấm 0.
    Đây đúng là tình huống đã xảy ra ở test case #5 khi chạy bằng LLM thật.
    """
    answer = str(result.get("final_answer") or "")
    obs_all = " ".join(str(s.get("observation") or "") for s in result.get("steps", []))
    facts = UUID_RE.findall(answer) + BK_RE.findall(answer) + MONEY_RE.findall(answer)
    n_tools = result.get("tool_calls", 0)

    if n_tools == 0:
        if facts:
            return 0, (f"🚨 ẢO GIÁC: gọi 0 tool nhưng vẫn nêu dữ liệu cụ thể "
                       f"{facts[:3]} — không có Observation nào làm bằng chứng")
        lo, _ = _expected_range(expected_tool_calls)
        if lo:
            return 1, f"không gọi tool (cần {expected_tool_calls}) nhưng cũng không bịa số liệu"
        return 2, "không cần bằng chứng (câu hỏi kiến thức chung)"

    if not facts:
        return 1, "có gọi tool nhưng Final Answer không trích dẫn dữ liệu cụ thể"

    bia = [f for f in facts if f not in obs_all]
    if bia:
        return 0, f"🚨 BỊA: {bia[:3]} không xuất hiện trong bất kỳ Observation nào"
    return 2, f"trích dẫn {len(facts)} dữ kiện, tất cả đều có trong Observation"


def score_factual(result, grounding_score):
    if grounding_score == 0:
        return 0, "🚨 phát hiện bịa dữ liệu"
    if result.get("stop_reason") == "provider_error":
        return 0, "không có câu trả lời"
    return 2, "⚠️ CẦN NGƯỜI XEM LẠI nội dung câu trả lời"


# ═══════════════════════════════════════════════════════════════════════════
# 🖨️ IN TRACE
# ═══════════════════════════════════════════════════════════════════════════

def print_trace(result, prefix="   "):
    """In ĐẦY ĐỦ chuỗi Thought -> Action -> Observation -> Final Answer."""
    for s in result.get("steps", []):
        print(f"{prefix}┌─ Step {s['step']}")
        if s.get("thought"):
            print(f"{prefix}│ 🧠 Thought: {cut(s['thought'])}")
        if s.get("action"):
            print(f"{prefix}│ 🛠️ Action: {cut(s['action'])}")
        if s.get("observation"):
            obs = cut(s["observation"]).replace("\n", f"\n{prefix}│              ")
            print(f"{prefix}│ 👁️ Observation: {obs}")
        if s.get("parse_error"):
            print(f"{prefix}│ ⚠️ PARSE ERROR — output không đúng định dạng ReAct")
        if s.get("final_answer"):
            fa = cut(s["final_answer"]).replace("\n", f"\n{prefix}│               ")
            print(f"{prefix}│ 🏁 Final Answer: {fa}")
        print(f"{prefix}└─")
    print(f"{prefix}📊 llm_calls={result.get('llm_calls')} tool_calls={result['tool_calls']} "
          f"steps={result['total_steps']} stop_reason={result['stop_reason']}")


# ═══════════════════════════════════════════════════════════════════════════
# 🧠 DEMO MEMORY — kịch bản hội thoại nhiều lượt
# ═══════════════════════════════════════════════════════════════════════════

CONVERSATION = [
    "Tìm giúp tôi căn hộ ở quận Cầu Giấy có giá thuê dưới 6 triệu mỗi tháng.",
    "Cho tôi xem chi tiết căn đầu tiên trong danh sách vừa rồi.",
    "Ngày mai căn đó còn khung giờ nào trống không?",
    "Đặt lịch giúp tôi khung giờ sớm nhất. Tôi tên Nguyễn Quang Vinh, số 0912345678.",
    "Kiểm tra lại giúp tôi lịch hẹn của số 0912345678.",
]


def run_conversation_demo(provider, turns=None):
    """Chạy hội thoại nhiều lượt để CHỨNG MINH Agent có Memory.

    Từ lượt 2 trở đi, khách KHÔNG hề nhắc tới mã căn UUID. Agent phải tự tra lại
    từ lịch sử hội thoại — đây là bằng chứng cho tiêu chí BONUS Memory (Cấp độ 4).
    """
    turns = turns or CONVERSATION
    print("\n" + "█" * 78)
    print("█ 🧠 KỊCH BẢN CHỨNG MINH AGENT CÓ MEMORY (hội thoại nhiều lượt)")
    print("█ Từ lượt 2, khách KHÔNG nhắc mã căn UUID — Agent phải tự tra từ lịch sử")
    print("█" * 78)

    history = []
    records = []

    for i, q in enumerate(turns, 1):
        print("\n" + "─" * 78)
        print(f"👤 LƯỢT {i} — Khách: {q}")
        print("─" * 78)

        # In khối ngữ cảnh mà app.py dựng từ lịch sử — ĐÂY LÀ BẰNG CHỨNG MEMORY
        ctx = build_conversation_context(history)
        if ctx:
            print("🗂️  NGỮ CẢNH ĐƯỢC NẠP TỪ LỊCH SỬ (build_conversation_context):")
            for line in ctx.strip().split("\n"):
                print(f"     {line}")
            print()
        else:
            print("🗂️  (Lượt đầu — chưa có lịch sử hội thoại)\n")

        result = run_react_agent(q, provider, history=history)
        print("🤖 AGENT:")
        print_trace(result)

        ids = collect_uuids(result)
        ids_from_ctx = [u for u in UUID_RE.findall(ctx or "")]
        used = UUID_RE.findall(" ".join(str(s.get("action") or "") for s in result["steps"]))

        # Chỉ ra rõ mã căn dùng ở lượt này lấy từ đâu
        if used:
            nguon = "LỊCH SỬ HỘI THOẠI ✅" if any(u.lower() in [x.lower() for x in ids_from_ctx]
                                                  for u in used) else "Observation trong chính lượt này"
            print(f"   🔑 Mã căn Agent dùng: {used[0]}")
            print(f"      → Nguồn: {nguon}")
            if not q_mentions_uuid(q):
                print(f"      → ⚠️ Khách KHÔNG hề nhắc mã này trong câu hỏi!")

        history = history + [
            {"role": "user", "content": q},
            {"role": "assistant", "content": (result["final_answer"] or "") +
             (f"\n[Các căn đã tra cứu: {', '.join(ids[:8])}]" if ids else "")},
        ]
        records.append({"turn": i, "question": q, "context": ctx,
                        "result": result, "uuids": ids, "used": used})

    return records


def q_mentions_uuid(q):
    return bool(UUID_RE.search(q))


# ═══════════════════════════════════════════════════════════════════════════
# 🧪 CHẠY TEST CASES
# ═══════════════════════════════════════════════════════════════════════════

def evaluate(tc, provider, verbose=True):
    q = tc["question"]
    if verbose:
        print("\n" + "█" * 78)
        print(f"█ CASE #{tc['id']} — {tc['category']}")
        print(f"█ {q}")
        print("█" * 78)

    base = run_baseline_chatbot(q, provider)
    agent = run_react_agent(q, provider)

    if verbose:
        print("\n💬 CHATBOT BASELINE (llm_calls=1, tool_calls=0):")
        print("   " + cut(base["final_answer"]).replace("\n", "\n   "))
        print("\n🤖 REACT AGENT:")
        print_trace(agent)

    ts, ts_n = score_tool_selection(agent, tc.get("expected_tool_calls"))
    tm, tm_n = score_termination(agent)
    gr, gr_n = score_grounding(agent, tc.get("expected_tool_calls"))
    fc, fc_n = score_factual(agent, gr)

    if verbose:
        print(f"\n   🏅 CHẤM ĐIỂM: Factual={fc} Grounding={gr} Tool={ts} Termination={tm} "
              f"→ {fc+gr+ts+tm}/8")
        for k, v in [("Tool", ts_n), ("Termination", tm_n), ("Grounding", gr_n), ("Factual", fc_n)]:
            print(f"      • {k}: {v}")

    b_tm, _ = score_termination(base)
    need_tool = _expected_range(tc.get("expected_tool_calls"))[0] or 0
    return {
        "tc": tc, "baseline": base, "agent": agent,
        "agent_scores": {"factual": fc, "grounding": gr, "tool": ts, "term": tm},
        "agent_notes": {"factual": fc_n, "grounding": gr_n, "tool": ts_n, "term": tm_n},
        "baseline_scores": {
            "factual": 2 if need_tool == 0 else 0,
            "grounding": 2 if need_tool == 0 else 0,
            "tool": 2 if need_tool == 0 else 0,
            "term": b_tm,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 📝 XUẤT MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════

def md_escape(t):
    return str(t or "").replace("|", "\\|").replace("\n", " ")


def conversation_markdown(records):
    L = ["\n---\n", "## 🧠 BẰNG CHỨNG AGENT CÓ MEMORY (hội thoại nhiều lượt)\n"]
    L.append("Mã căn là **UUID 36 ký tự** — khách hàng không bao giờ biết và không thể gõ ra. "
             "Từ lượt 2 trở đi khách chỉ nói *\"căn đầu tiên\"*, *\"căn đó\"*. "
             "Agent phải tự tra lại mã từ lịch sử hội thoại.\n")

    for r in records:
        L.append(f"\n### Lượt {r['turn']} — *\"{r['question']}\"*\n")
        if r["context"]:
            ctx_uuids = UUID_RE.findall(r["context"])
            L.append(f"**Ngữ cảnh nạp từ lịch sử**: {len(ctx_uuids)} mã căn từ các lượt trước\n")
            L.append("```text")
            L.append(r["context"].strip())
            L.append("```\n")
        L.append("```text")
        for s in r["result"]["steps"]:
            if s.get("thought"):
                L.append(f"Thought: {s['thought']}")
            if s.get("action"):
                L.append(f"Action: {s['action']}")
            if s.get("observation"):
                L.append(f"Observation: {s['observation']}")
            if s.get("final_answer"):
                L.append(f"Final Answer: {s['final_answer']}")
        ag = r["result"]
        L.append(f"\n[telemetry] llm_calls={ag.get('llm_calls')} tool_calls={ag['tool_calls']} "
                 f"stop_reason={ag['stop_reason']}")
        L.append("```\n")
        if r["used"] and not q_mentions_uuid(r["question"]):
            L.append(f"> 🔑 Agent dùng mã `{r['used'][0]}` — **khách không hề nhắc mã này**. "
                     f"Mã được lấy từ lịch sử hội thoại.\n")
    return "\n".join(L)


def to_markdown(results, provider, conv_records=None):
    model = getattr(provider, "model_name", "?")
    is_mock = "mock" in provider.__class__.__name__.lower()
    L = []
    L.append("## 📈 BẢNG CHẤM ĐIỂM RUBRIC 0–2 (tự sinh bởi `src/run_eval.py`)\n")
    L.append(f"- **Provider**: `{provider.__class__.__name__}` — model `{model}`")
    L.append(f"- **Thời điểm chạy**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- **Guardrails**: `MAX_ITERATIONS={MAX_ITERATIONS}`, "
             f"`MAX_REPEATED_ACTIONS={MAX_REPEATED_ACTIONS}`")
    if is_mock:
        L.append("\n> ⚠️ Chạy bằng MockProvider offline, KHÔNG gọi API thật.")

    if results:
        L.append("")
        L.append("| Case | Hệ thống | Factual | Grounding | Tool selection | Termination | Tổng |")
        L.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
        tot_a = tot_b = 0
        for r in results:
            i = r["tc"]["id"]
            a, b = r["agent_scores"], r["baseline_scores"]
            sa, sb = sum(a.values()), sum(b.values())
            tot_a += sa
            tot_b += sb
            L.append(f"| **#{i}** | Baseline Chatbot | {b['factual']} | {b['grounding']} | "
                     f"{b['tool']} | {b['term']} | **{sb}/8** |")
            L.append(f"| | ReAct Agent | {a['factual']} | {a['grounding']} | "
                     f"{a['tool']} | {a['term']} | **{sa}/8** |")
        n = len(results)
        L.append(f"| **TỔNG** | Baseline Chatbot | | | | | **{tot_b}/{n*8}** |")
        L.append(f"| | **ReAct Agent** | | | | | **{tot_a}/{n*8}** |")

        # Cảnh báo nổi bật các case bị phát hiện bịa
        flagged = [r for r in results if r["agent_scores"]["grounding"] == 0]
        if flagged:
            L.append("\n### 🚨 CÁC CASE PHÁT HIỆN ẢO GIÁC\n")
            for r in flagged:
                L.append(f"- **Case #{r['tc']['id']}**: {r['agent_notes']['grounding']}")

        L.append("\n### 📝 Ghi chú chấm điểm từng case\n")
        for r in results:
            nt = r["agent_notes"]
            L.append(f"- **Case #{r['tc']['id']}** ({r['tc']['category']}): "
                     f"Tool — {nt['tool']}; Termination — {nt['term']}; "
                     f"Grounding — {nt['grounding']}; Factual — {nt['factual']}")

        L.append("\n### 📊 Telemetry\n")
        L.append("| Case | Agent llm_calls | Agent tool_calls | stop_reason | Baseline tool_calls |")
        L.append("| :-: | :-: | :-: | :--- | :-: |")
        for r in results:
            ag = r["agent"]
            L.append(f"| #{r['tc']['id']} | {ag.get('llm_calls', '-')} | {ag['tool_calls']} | "
                     f"`{ag['stop_reason']}` | 0 |")

        L.append("\n### 💬 Toàn văn câu trả lời (Baseline vs Agent)\n")
        for r in results:
            L.append(f"\n<details><summary><b>Case #{r['tc']['id']}</b> — {md_escape(r['tc']['question'])}</summary>\n")
            L.append("**Chatbot Baseline:**\n")
            L.append("```text")
            L.append(str(r["baseline"]["final_answer"] or ""))
            L.append("```\n")
            L.append("**ReAct Agent — trace đầy đủ:**\n")
            L.append("```text")
            for s in r["agent"]["steps"]:
                if s.get("thought"):
                    L.append(f"Thought: {s['thought']}")
                if s.get("action"):
                    L.append(f"Action: {s['action']}")
                if s.get("observation"):
                    L.append(f"Observation: {s['observation']}")
                if s.get("final_answer"):
                    L.append(f"Final Answer: {s['final_answer']}")
            ag = r["agent"]
            L.append(f"\n[telemetry] llm_calls={ag.get('llm_calls')} tool_calls={ag['tool_calls']} "
                     f"stop_reason={ag['stop_reason']}")
            L.append("```\n")
            L.append("</details>\n")

    if conv_records:
        L.append(conversation_markdown(conv_records))

    return "\n".join(L)


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Chạy đánh giá test cases + demo Memory.")
    ap.add_argument("--provider", default=None, help="mock | custom | gemini | openai ...")
    ap.add_argument("--case", type=int, default=None, help="Chỉ chạy 1 case theo id")
    ap.add_argument("--out", default=None, help="Ghi báo cáo Markdown ra file")
    ap.add_argument("--quiet", action="store_true", help="Không in trace chi tiết")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="Cắt bớt mỗi đoạn text (0 = in đầy đủ, mặc định)")
    ap.add_argument("--no-memory", action="store_true", help="Bỏ qua demo Memory")
    ap.add_argument("--memory-only", action="store_true", help="CHỈ chạy demo Memory")
    args = ap.parse_args()

    MAX_CHARS = args.max_chars

    provider = get_llm_provider(args.provider)
    print("=" * 78)
    print("📊 EVALUATION RUNNER — Lab 03")
    print(f"   Provider: {provider.__class__.__name__} | "
          f"Model: {getattr(provider, 'model_name', '?')}")
    if "mock" in provider.__class__.__name__.lower():
        print("   ⚠️ ĐANG CHẠY MOCK OFFLINE — không gọi API thật!")
    print(f"   Guardrails: MAX_ITERATIONS={MAX_ITERATIONS}, "
          f"MAX_REPEATED_ACTIONS={MAX_REPEATED_ACTIONS}")
    print("=" * 78)

    results = []
    if not args.memory_only:
        cases = load_test_cases()
        if args.case:
            cases = [c for c in cases if c["id"] == args.case]
        # 🛡️ Bọc từng case: một case lỗi KHÔNG được làm mất trắng cả lần chạy
        # (đã từng mất case #12, #13 và toàn bộ báo cáo vì một TypeError).
        for tc in cases:
            try:
                results.append(evaluate(tc, provider, verbose=not args.quiet))
            except Exception as e:
                print(f"\n❌ CASE #{tc['id']} LỖI: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                empty = {"final_answer": f"[LỖI KHI CHẠY] {type(e).__name__}: {e}",
                         "steps": [], "total_steps": 0, "tool_calls": 0,
                         "llm_calls": 0, "stop_reason": "eval_crash"}
                results.append({
                    "tc": tc, "baseline": dict(empty), "agent": dict(empty),
                    "agent_scores": {"factual": 0, "grounding": 0, "tool": 0, "term": 0},
                    "agent_notes": {k: f"lỗi khi chạy: {e}" for k in
                                    ("factual", "grounding", "tool", "term")},
                    "baseline_scores": {"factual": 0, "grounding": 0, "tool": 0, "term": 0},
                })

    conv = None
    if not args.no_memory:
        try:
            conv = run_conversation_demo(provider)
        except Exception as e:
            print(f"\n❌ DEMO MEMORY LỖI: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    md = to_markdown(results, provider, conv)
    print("\n\n" + "=" * 78)
    print(md)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"\n✅ Đã ghi báo cáo ra: {args.out}")
