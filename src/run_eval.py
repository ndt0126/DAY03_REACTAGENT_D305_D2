"""
📊 EVALUATION RUNNER (Dành cho Role 5: Observability)

Chạy TOÀN BỘ test cases qua CẢ HAI hệ thống (Chatbot Baseline + ReAct Agent),
tự động chấm rubric 0-2 và xuất ra file Markdown dán thẳng vào trace_eval.md.

    python src/run_eval.py                  # chạy bằng provider trong .env
    python src/run_eval.py --provider mock  # chạy offline không tốn quota
    python src/run_eval.py --case 5         # chỉ chạy 1 case
    python src/run_eval.py --out docs/ket_qua.md

═══════════════════════════════════════════════════════════════════════════
 CÁCH CHẤM RUBRIC (0-2 điểm mỗi tiêu chí)
═══════════════════════════════════════════════════════════════════════════
Script chấm TỰ ĐỘNG các tiêu chí đo được bằng máy, và đánh dấu ⚠️ những chỗ
CẦN NGƯỜI XEM LẠI. Không nên tin 100% điểm máy chấm — mục đích là giảm việc
thủ công, không phải thay thế người đánh giá.

  • Tool selection : so số tool call thực tế với `expected_tool_calls` trong test_cases.json
  • Termination    : dựa vào stop_reason (final_answer / guardrail = tốt, crash = tệ)
  • Grounding      : kiểm tra Final Answer có trích dữ liệu XUẤT HIỆN trong Observation không
  • Factual        : ⚠️ cần người đọc — máy chỉ cảnh báo khi phát hiện dấu hiệu bịa
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

from app import run_baseline_chatbot, run_react_agent, load_test_cases
from providers import get_llm_provider
from prompts import MAX_ITERATIONS, MAX_REPEATED_ACTIONS

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_BK_RE = re.compile(r"\bBK\d{3,}\b")
_MONEY_RE = re.compile(r"\b\d{1,3}(?:[.,]\d{3})+\b")


def _expected_range(exp):
    """Chuyển `expected_tool_calls` (có thể là int hoặc chuỗi '1-3') thành (min, max)."""
    if isinstance(exp, int):
        return exp, exp
    nums = [int(x) for x in re.findall(r"\d+", str(exp))]
    if not nums:
        return None, None
    return min(nums), max(nums)


def score_tool_selection(result, expected):
    lo, hi = _expected_range(expected)
    n = result.get("tool_calls", 0)
    if lo is None:
        return 1, "không có kỳ vọng rõ ràng"
    if lo <= n <= hi:
        return 2, f"gọi {n} tool, đúng kỳ vọng {expected}"
    # Có tự sửa lỗi sau khi tool báo LỖI -> vẫn được 1 điểm
    had_error = any(s.get("is_error") for s in result.get("steps", []))
    if had_error:
        return 1, f"gọi {n} tool (kỳ vọng {expected}) nhưng có tự phục hồi sau lỗi"
    return 0, f"gọi {n} tool, lệch kỳ vọng {expected}"


def score_termination(result):
    reason = result.get("stop_reason")
    if reason in ("final_answer", "single_llm_call"):
        steps = result.get("total_steps", 0)
        if steps <= MAX_ITERATIONS:
            return 2, f"dừng đúng lúc ({reason}, {steps} bước)"
        return 1, f"dừng nhưng thừa bước ({steps})"
    if reason in ("repeated_action", "max_iterations"):
        return 2, f"Guardrail ngắt an toàn ({reason})"
    if reason == "provider_error":
        return 0, "lỗi provider, không hoàn thành"
    return 1, f"stop_reason = {reason}"


def score_grounding(result):
    """Final Answer có trích dữ liệu THẬT từ Observation không?"""
    answer = str(result.get("final_answer") or "")
    obs_all = " ".join(str(s.get("observation") or "") for s in result.get("steps", []))

    if result.get("tool_calls", 0) == 0:
        # Không gọi tool: chỉ đạt 2 nếu đây đúng là câu hỏi kiến thức chung
        return 2, "không cần bằng chứng (câu hỏi kiến thức chung)"

    facts = _UUID_RE.findall(answer) + _BK_RE.findall(answer) + _MONEY_RE.findall(answer)
    if not facts:
        return 1, "có gọi tool nhưng Final Answer không trích dẫn dữ liệu cụ thể"

    bia = [f for f in facts if f not in obs_all]
    if bia:
        return 0, f"⚠️ BỊA: {bia[:3]} không có trong bất kỳ Observation nào"
    return 2, f"trích dẫn {len(facts)} dữ kiện, tất cả đều có trong Observation"


def score_factual(result, grounding_score):
    """Máy không tự đánh giá được tính đúng đắn nội dung -> cần người xem."""
    if grounding_score == 0:
        return 0, "⚠️ có dấu hiệu bịa dữ liệu"
    if result.get("stop_reason") == "provider_error":
        return 0, "không có câu trả lời"
    return 2, "⚠️ CẦN NGƯỜI XEM LẠI nội dung câu trả lời"


def evaluate(tc, provider, verbose=True):
    q = tc["question"]
    if verbose:
        print("\n" + "█" * 74)
        print(f"█ CASE #{tc['id']} — {tc['category']}")
        print(f"█ {q}")
        print("█" * 74)

    base = run_baseline_chatbot(q, provider)
    agent = run_react_agent(q, provider)

    if verbose:
        print(f"\n💬 BASELINE  (llm=1, tool=0):\n   {str(base['final_answer'])[:220]}")
        print(f"\n🤖 REACT AGENT:")
        for s in agent["steps"]:
            if s.get("thought"):
                print(f"   🧠 {str(s['thought'])[:150]}")
            if s.get("action"):
                print(f"   🛠️ {str(s['action'])[:150]}")
            if s.get("observation"):
                print(f"   👁️ {str(s['observation'])[:200]}")
        print(f"   🏁 {str(agent['final_answer'])[:220]}")
        print(f"   📊 llm={agent.get('llm_calls')} tool={agent['tool_calls']} "
              f"stop={agent['stop_reason']}")

    ts, ts_note = score_tool_selection(agent, tc.get("expected_tool_calls"))
    tm, tm_note = score_termination(agent)
    gr, gr_note = score_grounding(agent)
    fc, fc_note = score_factual(agent, gr)

    b_gr, _ = score_grounding(base)
    b_tm, _ = score_termination(base)

    return {
        "tc": tc, "baseline": base, "agent": agent,
        "agent_scores": {"factual": fc, "grounding": gr, "tool": ts, "term": tm},
        "agent_notes": {"factual": fc_note, "grounding": gr_note,
                        "tool": ts_note, "term": tm_note},
        # Baseline không có tool nên Tool selection = 2 nếu case không cần tool, ngược lại 0
        "baseline_scores": {
            "factual": 2 if tc.get("expected_tool_calls") == 0 else 0,
            "grounding": 2 if tc.get("expected_tool_calls") == 0 else 0,
            "tool": 2 if tc.get("expected_tool_calls") == 0 else 0,
            "term": b_tm,
        },
    }


def to_markdown(results, provider) -> str:
    model = getattr(provider, "model_name", "?")
    is_mock = "mock" in provider.__class__.__name__.lower()
    L = []
    L.append("## 📈 BẢNG CHẤM ĐIỂM RUBRIC 0–2 (tự sinh bởi `src/run_eval.py`)\n")
    L.append(f"- **Provider**: `{provider.__class__.__name__}` — model `{model}`")
    L.append(f"- **Thời điểm chạy**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- **Guardrails**: `MAX_ITERATIONS={MAX_ITERATIONS}`, "
             f"`MAX_REPEATED_ACTIONS={MAX_REPEATED_ACTIONS}`")
    if is_mock:
        L.append("\n> ⚠️ **Kết quả này chạy bằng MockProvider offline, KHÔNG gọi API thật.** "
                 "Phải chạy lại bằng LLM thật trước khi nộp.")
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

    L.append("\n### 📝 Ghi chú chấm điểm từng case\n")
    for r in results:
        i = r["tc"]["id"]
        nt = r["agent_notes"]
        L.append(f"- **Case #{i}** ({r['tc']['category']}): "
                 f"Tool — {nt['tool']}; Termination — {nt['term']}; "
                 f"Grounding — {nt['grounding']}; Factual — {nt['factual']}")

    L.append("\n### 📊 Telemetry\n")
    L.append("| Case | Agent llm_calls | Agent tool_calls | stop_reason | Baseline tool_calls |")
    L.append("| :-: | :-: | :-: | :--- | :-: |")
    for r in results:
        ag = r["agent"]
        L.append(f"| #{r['tc']['id']} | {ag.get('llm_calls', '-')} | {ag['tool_calls']} | "
                 f"`{ag['stop_reason']}` | 0 |")

    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Chạy đánh giá toàn bộ test cases.")
    ap.add_argument("--provider", default=None, help="mock | custom | gemini | openai ...")
    ap.add_argument("--case", type=int, default=None, help="Chỉ chạy 1 case theo id")
    ap.add_argument("--out", default=None, help="Ghi báo cáo Markdown ra file")
    ap.add_argument("--quiet", action="store_true", help="Không in trace chi tiết")
    args = ap.parse_args()

    provider = get_llm_provider(args.provider)
    print("=" * 74)
    print("📊 EVALUATION RUNNER — Lab 03")
    print(f"   Provider: {provider.__class__.__name__} | "
          f"Model: {getattr(provider, 'model_name', '?')}")
    if "mock" in provider.__class__.__name__.lower():
        print("   ⚠️ ĐANG CHẠY MOCK OFFLINE — không gọi API thật!")
    print("=" * 74)

    cases = load_test_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]

    results = [evaluate(tc, provider, verbose=not args.quiet) for tc in cases]

    md = to_markdown(results, provider)
    print("\n\n" + "=" * 74)
    print(md)

    if args.out:
        path = args.out
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"\n✅ Đã ghi báo cáo ra: {path}")
