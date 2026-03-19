"""
Gradio Chat Interface cho Mini Wren AI.

Giao diện chat qua lại giữa người dùng và FastAPI server.
Có phần settings để bật/tắt các tính năng và chọn số candidates.

Chạy:
    cd mini-wren-ai
    python gradio_app.py
"""

import json
import requests
import gradio as gr

API_BASE = "http://localhost:8000"


def format_response(data: dict) -> str:
    """Format API response thành message đẹp cho chatbot."""
    parts = []

    # ── Trạng thái ──
    if data.get("valid"):
        parts.append("✅ **Truy vấn thành công**")
    else:
        parts.append("❌ **Truy vấn thất bại**")

    # ── Intent ──
    if data.get("intent"):
        parts.append(f"\n🎯 **Intent:** {data['intent']}")

    # ── Explanation ──
    if data.get("explanation"):
        parts.append(f"\n💡 **Giải thích:** {data['explanation']}")

    # ── SQL ──
    if data.get("sql"):
        parts.append(f"\n📝 **SQL:**\n```sql\n{data['sql']}\n```")

    if data.get("original_sql") and data["original_sql"] != data.get("sql"):
        parts.append(f"\n🔄 **SQL gốc (trước rewrite):**\n```sql\n{data['original_sql']}\n```")

    # ── Data Table ──
    if data.get("columns") and data.get("rows"):
        row_count = data.get("row_count", len(data["rows"]))
        parts.append(f"\n📊 **Kết quả: {row_count} dòng**\n")

        # Markdown table
        cols = data["columns"]
        header = "| " + " | ".join(str(c) for c in cols) + " |"
        separator = "| " + " | ".join("---" for _ in cols) + " |"
        rows_md = []
        for row in data["rows"][:20]:  # Giới hạn 20 dòng hiển thị
            if isinstance(row, dict):
                row_vals = [str(row.get(c, "")) for c in cols]
            else:
                row_vals = [str(v) for v in row]
            rows_md.append("| " + " | ".join(row_vals) + " |")

        parts.append(header)
        parts.append(separator)
        parts.extend(rows_md)

        if row_count > 20:
            parts.append(f"\n*... và {row_count - 20} dòng nữa*")

    # ── Error ──
    if data.get("error"):
        parts.append(f"\n⚠️ **Lỗi:** {data['error']}")

    # ── Pipeline Info ──
    pipeline = data.get("pipeline_info", {})
    active = pipeline.get("active_features", [])
    if active:
        parts.append(f"\n🔧 **Tính năng đã dùng:** {', '.join(active)}")

    info_items = []
    if pipeline.get("reasoning_steps"):
        info_items.append(f"Reasoning steps: {len(pipeline['reasoning_steps'])}")
    if pipeline.get("schema_links"):
        info_items.append(f"Schema links: {len(pipeline['schema_links'])}")
    if pipeline.get("columns_pruned") is not None:
        info_items.append(f"Columns pruned: {pipeline['columns_pruned']}")
    if pipeline.get("candidates_generated"):
        info_items.append(f"Candidates: {pipeline['candidates_generated']}")
    if pipeline.get("voting_method"):
        info_items.append(f"Voting: {pipeline['voting_method']}")
    if pipeline.get("glossary_matches"):
        info_items.append(f"Glossary matches: {len(pipeline['glossary_matches'])}")
    if pipeline.get("similar_traces"):
        info_items.append(f"Memory traces: {len(pipeline['similar_traces'])}")

    if info_items:
        parts.append("\n<details><summary>📋 Chi tiết Pipeline</summary>\n")
        for item in info_items:
            parts.append(f"- {item}")
        parts.append("\n</details>")

    if data.get("retries"):
        parts.append(f"\n🔁 Retries: {data['retries']}")

    return "\n".join(parts)


def ask_api(
    message: str,
    history: list,
    enable_schema_linking: bool,
    enable_column_pruning: bool,
    enable_cot_reasoning: bool,
    enable_voting: bool,
    enable_glossary: bool,
    enable_memory: bool,
    num_candidates: int,
):
    """Gửi câu hỏi tới FastAPI /v1/ask và trả response."""
    payload = {
        "question": message,
        "enable_schema_linking": enable_schema_linking,
        "enable_column_pruning": enable_column_pruning,
        "enable_cot_reasoning": enable_cot_reasoning,
        "enable_voting": enable_voting,
        "enable_glossary": enable_glossary,
        "enable_memory": enable_memory,
        "num_candidates": int(num_candidates),
    }

    try:
        resp = requests.post(f"{API_BASE}/v1/ask", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return format_response(data)
    except requests.exceptions.ConnectionError:
        return "❌ **Không kết nối được tới server!**\n\nHãy đảm bảo FastAPI server đang chạy tại `http://localhost:8000`.\n\n```\npython -m uvicorn src.server:app --reload --port 8000\n```"
    except requests.exceptions.Timeout:
        return "⏱️ **Timeout!** Server xử lý quá lâu. Thử lại hoặc đơn giản hóa câu hỏi."
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        return f"❌ **Lỗi từ server ({e.response.status_code}):**\n\n{error_detail}"
    except Exception as e:
        return f"❌ **Lỗi không xác định:**\n\n{str(e)}"


def check_server_status():
    """Kiểm tra trạng thái server."""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        data = resp.json()
        if data.get("deployed"):
            return "🟢 Server đang chạy & đã deploy"
        else:
            return "🟡 Server đang chạy nhưng chưa deploy"
    except Exception:
        return "🔴 Server không phản hồi"


# ── Build Gradio UI ──
with gr.Blocks(
    title="Mini Wren AI - Text to SQL",
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="slate",
        neutral_hue="slate",
    ),
    css="""
    .settings-panel { 
        border-left: 2px solid var(--border-color-primary); 
        padding-left: 16px; 
    }
    .status-badge {
        font-size: 0.85em;
        padding: 4px 12px;
        border-radius: 8px;
        background: var(--background-fill-secondary);
    }
    footer { display: none !important; }
    """,
) as demo:

    # ── Header ──
    gr.Markdown(
        """
        # 🧠 Mini Wren AI — Text to SQL
        *Chat với cơ sở dữ liệu bằng ngôn ngữ tự nhiên*
        """,
    )

    with gr.Row():
        # ══════════ MAIN CHAT AREA ══════════
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                label="💬 Chat",
                height=520,
                placeholder="Nhập câu hỏi bằng tiếng Việt hoặc tiếng Anh...",
            )

            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Ví dụ: Tổng doanh thu theo tháng...",
                    show_label=False,
                    scale=5,
                    container=False,
                )
                send_btn = gr.Button("Gửi 🚀", variant="primary", scale=1)

        # ══════════ SETTINGS SIDEBAR ══════════
        with gr.Column(scale=1, elem_classes="settings-panel"):
            server_status = gr.Markdown(
                value=check_server_status(),
                elem_classes="status-badge",
            )

            gr.Markdown("### ⚙️ Cài đặt Pipeline")

            with gr.Group():
                gr.Markdown("**Tính năng**")
                schema_linking = gr.Checkbox(
                    label="🔗 Schema Linking",
                    value=False,
                    info="Liên kết câu hỏi với schema DB",
                )
                column_pruning = gr.Checkbox(
                    label="✂️ Column Pruning",
                    value=False,
                    info="Loại bỏ cột không liên quan",
                )
                cot_reasoning = gr.Checkbox(
                    label="🧩 Chain-of-Thought",
                    value=False,
                    info="Suy luận từng bước",
                )
                voting = gr.Checkbox(
                    label="🗳️ Voting",
                    value=False,
                    info="Bình chọn giữa nhiều câu SQL",
                )
                glossary = gr.Checkbox(
                    label="📖 Glossary",
                    value=False,
                    info="Dùng bảng thuật ngữ",
                )
                memory = gr.Checkbox(
                    label="🧠 Memory",
                    value=False,
                    info="Dùng bộ nhớ ngữ nghĩa",
                )

            with gr.Group():
                gr.Markdown("**Số lượng Candidates**")
                num_candidates = gr.Slider(
                    minimum=1,
                    maximum=5,
                    value=3,
                    step=1,
                    label="Candidates",
                    info="Số SQL candidates tạo ra",
                )

            with gr.Accordion("📋 JSON Preview", open=False):
                json_preview = gr.JSON(
                    label="Request sẽ gửi",
                    value={
                        "question": "<câu hỏi của bạn>",
                        "enable_schema_linking": False,
                        "enable_column_pruning": False,
                        "enable_cot_reasoning": False,
                        "enable_voting": False,
                        "enable_glossary": False,
                        "enable_memory": False,
                        "num_candidates": 3,
                    },
                )

    # ── Update JSON preview khi thay đổi settings ──
    def update_preview(sl, cp, cot, vt, gl, mem, nc):
        return {
            "question": "<câu hỏi của bạn>",
            "enable_schema_linking": sl,
            "enable_column_pruning": cp,
            "enable_cot_reasoning": cot,
            "enable_voting": vt,
            "enable_glossary": gl,
            "enable_memory": mem,
            "num_candidates": int(nc),
        }

    all_settings = [
        schema_linking, column_pruning, cot_reasoning,
        voting, glossary, memory, num_candidates,
    ]

    for setting in all_settings:
        setting.change(
            fn=update_preview,
            inputs=all_settings,
            outputs=json_preview,
        )

    # ── Chat logic ──
    def _extract_text(content):
        """Extract plain text from Gradio 6.x multimodal content."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # [{'text': '...', 'type': 'text'}, ...]
            return " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def user_submit(message, history):
        """Thêm tin nhắn user vào history."""
        text = _extract_text(message) if not isinstance(message, str) else message
        if not text.strip():
            return "", history
        history = history + [{"role": "user", "content": text}]
        return "", history

    def bot_respond(history, sl, cp, cot, vt, gl, mem, nc):
        """Gọi API và thêm response của bot."""
        if not history or history[-1]["role"] != "user":
            return history

        user_msg = _extract_text(history[-1]["content"])
        bot_reply = ask_api(user_msg, history, sl, cp, cot, vt, gl, mem, nc)
        history = history + [{"role": "assistant", "content": bot_reply}]
        return history

    # Bind events
    submit_inputs = [msg_input, chatbot]
    bot_inputs = [chatbot] + all_settings

    msg_input.submit(
        fn=user_submit,
        inputs=submit_inputs,
        outputs=[msg_input, chatbot],
    ).then(
        fn=bot_respond,
        inputs=bot_inputs,
        outputs=chatbot,
    )

    send_btn.click(
        fn=user_submit,
        inputs=submit_inputs,
        outputs=[msg_input, chatbot],
    ).then(
        fn=bot_respond,
        inputs=bot_inputs,
        outputs=chatbot,
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
