// =========================================================
// RENTAGENT AI — FRONTEND INTERACTIVE LOGIC (src/frontend/script.js)
// =========================================================

document.addEventListener("DOMContentLoaded", () => {
    let currentMode = "react"; // 'react' hoặc 'baseline'
    let testCasesData = [];

    // DOM Elements
    const chatMessages = document.getElementById("chatMessages");
    const chatForm = document.getElementById("chatForm");
    const userInput = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    const clearChatBtn = document.getElementById("clearChatBtn");
    
    const modeReactBtn = document.getElementById("modeReactBtn");
    const modeBaselineBtn = document.getElementById("modeBaselineBtn");
    const currentModeTitle = document.getElementById("currentModeTitle");
    const currentModeDesc = document.getElementById("currentModeDesc");
    
    const providerSelect = document.getElementById("providerSelect");
    const testCasesList = document.getElementById("testCasesList");
    const featuredListings = document.getElementById("featuredListings");
    const toolsList = document.getElementById("toolsList");

    // ---------------------------------------------------------
    // 1. FETCH INITIAL DATA FROM BACKEND APIs
    // ---------------------------------------------------------
    async function init() {
        await Promise.all([
            fetchProviders(),
            fetchTestCases(),
            fetchListings(),
            fetchTools()
        ]);
    }

    async function fetchProviders() {
        try {
            const res = await fetch("/api/providers");
            const data = await res.json();
            if (data.providers && data.providers.length > 0) {
                providerSelect.innerHTML = "";
                data.providers.forEach((p) => {
                    const opt = document.createElement("option");
                    opt.value = p.id;
                    opt.textContent = p.name;
                    if (p.active) opt.selected = true;
                    providerSelect.appendChild(opt);
                });
            }
        } catch (err) {
            console.log("Could not load providers", err);
        }
    }


    async function fetchTestCases() {
        try {
            const res = await fetch("/api/test-cases");
            testCasesData = await res.json();
            renderTestCases(testCasesData);
        } catch (err) {
            testCasesList.innerHTML = `<div class="skeleton-loader">Không thể tải test cases</div>`;
        }
    }

    async function fetchListings() {
        try {
            const res = await fetch("/api/listings");
            const listings = await res.json();
            renderListings(listings);
        } catch (err) {
            featuredListings.innerHTML = `<div class="skeleton-loader">Không thể tải căn hộ mẫu</div>`;
        }
    }

    async function fetchTools() {
        try {
            const res = await fetch("/api/tools");
            const tools = await res.json();
            renderTools(tools);
        } catch (err) {
            toolsList.innerHTML = `<div class="skeleton-loader">Không thể tải công cụ</div>`;
        }
    }

    // ---------------------------------------------------------
    // 2. RENDER SIDEBAR COMPONENTS
    // ---------------------------------------------------------
    function renderTestCases(cases) {
        testCasesList.innerHTML = "";
        cases.forEach((tc) => {
            const btn = document.createElement("button");
            btn.className = "test-item-btn";
            btn.innerHTML = `
                <span class="test-badge">Case #${tc.id} • ${tc.category.split(" ")[0]}</span>
                <span class="test-question">${tc.question}</span>
            `;
            btn.addEventListener("click", () => {
                userInput.value = tc.question;
                userInput.focus();
            });
            testCasesList.appendChild(btn);
        });
    }

    function renderListings(listings) {
        featuredListings.innerHTML = "";
        listings.forEach((ap) => {
            const card = document.createElement("div");
            card.className = "listing-mini-card";
            card.innerHTML = `
                <div class="listing-title">[${ap.id}] ${ap.title}</div>
                <div class="listing-details">
                    <span>📍 ${ap.district}</span>
                    <span class="price-tag">${ap.price_display}</span>
                </div>
                <button class="quick-book-btn">Đặt xem căn này</button>
            `;
            const bookBtn = card.querySelector(".quick-book-btn");
            bookBtn.addEventListener("click", () => {
                userInput.value = `Xem chi tiết và đặt lịch xem căn hộ mã ${ap.id} lúc 10:00 sáng mai cho anh Nguyễn Văn A, SĐT 0912345678.`;
                userInput.focus();
            });
            featuredListings.appendChild(card);
        });
    }

    function renderTools(tools) {
        toolsList.innerHTML = "";
        tools.forEach((t) => {
            const chip = document.createElement("div");
            chip.className = "tool-chip";
            chip.innerHTML = `
                <div class="tool-chip-name">⚙️ ${t.name}</div>
                <div class="tool-chip-desc">${t.description.split("\n")[0]}</div>
            `;
            toolsList.appendChild(chip);
        });
    }

    // ---------------------------------------------------------
    // 3. MODE SWITCHING (ReAct Agent vs Chatbot Baseline)
    // ---------------------------------------------------------
    modeReactBtn.addEventListener("click", () => setMode("react"));
    modeBaselineBtn.addEventListener("click", () => setMode("baseline"));

    function setMode(mode) {
        currentMode = mode;
        if (mode === "react") {
            modeReactBtn.classList.add("active");
            modeBaselineBtn.classList.remove("active");
            currentModeTitle.innerHTML = `🤖 Chế độ: ReAct Agent (Suy Luận Thought ➔ Action ➔ Observation)`;
            currentModeDesc.innerHTML = `Agent có khả năng tự gọi công cụ tra cứu phòng trọ, xem thông tin và đặt lịch hẹn thực tế.`;
        } else {
            modeBaselineBtn.classList.add("active");
            modeReactBtn.classList.remove("active");
            currentModeTitle.innerHTML = `💬 Chế độ: Chatbot Baseline (Thuần LLM - Không có Tool)`;
            currentModeDesc.innerHTML = `Chatbot gốc chỉ dùng tri thức có sẵn, KHÔNG có dữ liệu phòng trọ thực tế.`;
        }
    }

    // Quick text insert
    window.sendQuickText = function(text) {
        userInput.value = text;
        userInput.focus();
    };

    // Enter to Submit, Shift+Enter to Newline
    userInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
        }
    });

    // ---------------------------------------------------------
    // 4. CHAT FORM SUBMISSION & MESSAGE RENDERING
    // ---------------------------------------------------------
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = userInput.value.trim();
        if (!query) return;

        // Render User Message
        appendUserMessage(query);
        userInput.value = "";
        userInput.style.height = "auto"; // Reset height
        sendBtn.disabled = true;


        // Render Loading Indicator
        const loadingId = appendLoadingMessage();

        try {
            const selectedProvider = providerSelect ? providerSelect.value : "mock";
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    query: query, 
                    mode: currentMode,
                    provider: selectedProvider
                })
            });
            const data = await response.json();

            // Remove loading and append Assistant Response
            removeMessage(loadingId);
            appendAssistantMessage(data);


        } catch (err) {
            removeMessage(loadingId);
            appendAssistantMessage({
                final_answer: "⚠️ Lỗi kết nối đến máy chủ AI Agent. Vui lòng kiểm tra lại dịch vụ backend!"
            });
        } finally {
            sendBtn.disabled = false;
        }
    });

    function appendUserMessage(text) {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const row = document.createElement("div");
        row.className = "message-row user-row";
        row.innerHTML = `
            <div class="avatar user-avatar">
                <i class="fa-solid fa-user"></i>
            </div>
            <div class="message-bubble user-bubble">
                <div class="bubble-header">
                    <span class="agent-name">Bạn</span>
                    <span class="time-stamp">${time}</span>
                </div>
                <div class="bubble-body">${escapeHtml(text)}</div>
            </div>
        `;
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function appendLoadingMessage() {
        const id = "loading-" + Date.now();
        const row = document.createElement("div");
        row.className = "message-row assistant-row";
        row.id = id;
        row.innerHTML = `
            <div class="avatar assistant-avatar">
                <i class="fa-solid fa-robot"></i>
            </div>
            <div class="message-bubble assistant-bubble">
                <div class="bubble-body">
                    <i class="fa-solid fa-circle-notch fa-spin"></i> RentAgent đang ${currentMode === 'react' ? 'suy luận và thực thi tools...' : 'sinh câu trả lời...'}
                </div>
            </div>
        `;
        chatMessages.appendChild(row);
        scrollToBottom();
        return id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function appendAssistantMessage(data) {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const row = document.createElement("div");
        row.className = "message-row assistant-row";

        let traceHtml = "";
        
        // Render ReAct Trace steps if available
        if (data.mode === "react" && data.steps && data.steps.length > 0) {
            traceHtml += `<div class="react-trace-box">`;
            data.steps.forEach((st) => {
                traceHtml += `
                    <div class="step-card">
                        <span class="step-tag"><i class="fa-solid fa-arrows-spin"></i> Step ${st.step}</span>
                        ${st.thought ? `<div class="thought-block">🧠 <strong>Thought:</strong> ${escapeHtml(st.thought)}</div>` : ''}
                        ${st.action ? `<div class="action-block">🛠️ <strong>Action:</strong> ${escapeHtml(st.action)}</div>` : ''}
                        ${st.observation ? `<div class="observation-block">👁️ <strong>Observation:</strong>\n${escapeHtml(st.observation)}</div>` : ''}
                    </div>
                `;
            });
            traceHtml += `</div>`;
        }

        // Guardrail alert
        let guardrailHtml = "";
        if (data.guardrail_triggered) {
            guardrailHtml = `<div class="guardrail-alert"><i class="fa-solid fa-shield-halved"></i> ${data.final_answer}</div>`;
        }

        const finalBody = data.final_answer ? formatMarkdown(data.final_answer) : "";

        row.innerHTML = `
            <div class="avatar assistant-avatar">
                <i class="fa-solid fa-robot"></i>
            </div>
            <div class="message-bubble assistant-bubble">
                <div class="bubble-header">
                    <span class="agent-name">RentAgent AI (${data.mode === 'react' ? 'ReAct Loop' : 'Baseline'})</span>
                    <span class="time-stamp">${time}</span>
                </div>
                <div class="bubble-body">
                    ${traceHtml}
                    ${guardrailHtml ? guardrailHtml : `<div>${finalBody}</div>`}
                </div>
            </div>
        `;

        chatMessages.appendChild(row);
        scrollToBottom();
    }

    // Helper functions
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(text) {
        if (!text) return "";
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function formatMarkdown(text) {
        if (!text) return "";
        let formatted = escapeHtml(text);
        // Bold
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Newlines
        formatted = formatted.replace(/\n/g, '<br>');
        return formatted;
    }

    // Clear Chat
    clearChatBtn.addEventListener("click", () => {
        chatMessages.innerHTML = `
            <div class="message-row assistant-row">
                <div class="avatar assistant-avatar">
                    <i class="fa-solid fa-robot"></i>
                </div>
                <div class="message-bubble assistant-bubble">
                    <div class="bubble-header">
                        <span class="agent-name">RentAgent AI</span>
                        <span class="time-stamp">Vừa xong</span>
                    </div>
                    <div class="bubble-body">
                        Lịch sử chat đã được xóa. Hãy nhập câu hỏi mới hoặc chọn Test Case bên trái!
                    </div>
                </div>
            </div>
        `;
    });

    // Start App
    init();
});
