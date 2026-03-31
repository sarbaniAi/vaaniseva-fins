/**
 * VaaniSeva — WhatsApp Collections Flow UI
 */
const WhatsApp = (() => {
    let phoneInput, messageInput, simInput;
    let conversationEl, statusEl;

    function init() {
        phoneInput = document.getElementById('wa-phone');
        messageInput = document.getElementById('wa-message');
        simInput = document.getElementById('wa-sim-msg');
        conversationEl = document.getElementById('wa-conversation');
        statusEl = document.getElementById('wa-send-status');

        document.getElementById('btn-wa-start-flow')?.addEventListener('click', startFlow);
        document.getElementById('btn-wa-send')?.addEventListener('click', sendMessage);
        document.getElementById('btn-wa-simulate')?.addEventListener('click', simulateIncoming);
        document.getElementById('btn-wa-refresh')?.addEventListener('click', refreshConversation);

        // Enter key on sim input
        simInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') simulateIncoming();
        });
    }

    async function startFlow() {
        const phone = phoneInput?.value?.trim();
        if (!phone) { setStatus('Enter a phone number'); return; }

        try {
            setStatus('Starting flow...');
            const resp = await App.api('/api/whatsapp/start-flow', {
                method: 'POST',
                body: JSON.stringify({ to: phone }),
            });
            if (resp.error) {
                setStatus('Error: ' + resp.error);
            } else {
                const mode = resp.mode === 'twilio' ? 'Sent via WhatsApp' : 'Local mode';
                setStatus(`Flow started! (${mode}) ${resp.note || ''}`);
                refreshConversation();
            }
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function sendMessage() {
        const phone = phoneInput?.value?.trim();
        const message = messageInput?.value?.trim();
        if (!phone || !message) { setStatus('Enter phone and message'); return; }

        try {
            setStatus('Sending...');
            const resp = await App.api('/api/whatsapp/send', {
                method: 'POST',
                body: JSON.stringify({ to: phone, message }),
            });
            if (resp.error) {
                setStatus('Error: ' + resp.error);
            } else {
                const mode = resp.mode === 'twilio' ? 'via WhatsApp' : 'local';
                setStatus(`Sent (${mode})! ${resp.note || ''}`);
                messageInput.value = '';
                refreshConversation();
            }
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function simulateIncoming() {
        const phone = phoneInput?.value?.trim();
        const message = simInput?.value?.trim();
        if (!phone || !message) { setStatus('Enter phone and message to simulate'); return; }

        try {
            setStatus('Processing...');
            const resp = await App.api('/api/whatsapp/simulate', {
                method: 'POST',
                body: JSON.stringify({ from: phone, message }),
            });
            if (resp.error) {
                setStatus('Error: ' + resp.error);
            } else {
                setStatus('Reply generated');
                simInput.value = '';
                refreshConversation();
            }
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function refreshConversation() {
        const phone = phoneInput?.value?.trim();
        if (!phone) return;

        try {
            const resp = await App.api('/api/whatsapp/conversations/' + encodeURIComponent(phone));
            renderConversation(resp.messages || []);
        } catch (e) {
            // May not exist yet
            conversationEl.innerHTML = '<p class="muted">No messages yet. Start a flow or simulate a message.</p>';
        }
    }

    function renderConversation(messages) {
        if (!messages.length) {
            conversationEl.innerHTML = '<p class="muted">No messages yet.</p>';
            return;
        }

        conversationEl.innerHTML = messages.map(m => {
            const isUser = m.role === 'user';
            const bgColor = isUser ? '#e8f5e9' : '#e3f2fd';
            const label = isUser ? 'Customer' : 'VaaniSeva';
            const align = isUser ? 'flex-end' : 'flex-start';
            // Escape HTML
            const safeText = m.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const formatted = safeText.replace(/\n/g, '<br>').replace(/\*(.*?)\*/g, '<strong>$1</strong>');

            return `<div style="display:flex;justify-content:${align};margin:4px 0">
                <div style="background:${bgColor};padding:8px 12px;border-radius:12px;max-width:80%;font-size:13px">
                    <div style="font-size:10px;color:#888;margin-bottom:2px">${label} ${m.time || ''}</div>
                    ${formatted}
                </div>
            </div>`;
        }).join('');

        // Scroll to bottom
        conversationEl.scrollTop = conversationEl.scrollHeight;
    }

    function setStatus(msg) {
        if (statusEl) statusEl.textContent = msg;
    }

    return { init };
})();
