/**
 * VaaniSeva — Customer Simulator persona.
 */
const CustomerSim = (() => {
    let selectedCustomerId = null;

    function init() {
        loadCustomers();

        document.getElementById('btn-start-call')?.addEventListener('click', startCall);
        document.getElementById('btn-dial-call')?.addEventListener('click', dialCall);
        document.getElementById('btn-send-text')?.addEventListener('click', sendText);
        document.getElementById('btn-end-call')?.addEventListener('click', endCall);
        document.getElementById('btn-record')?.addEventListener('click', () => AudioManager.startRecording());
        document.getElementById('btn-stop-record')?.addEventListener('click', () => AudioManager.stopRecording());
        document.getElementById('btn-send-voice')?.addEventListener('click', sendVoice);

        // Enter key sends text
        document.getElementById('text-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendText();
        });
    }

    async function loadCustomers() {
        const listEl = document.getElementById('customer-list');
        try {
            const customers = await App.api('/api/customers');
            if (!customers.length) {
                listEl.innerHTML = '<p class="muted">No customers found. Run setup notebooks first.</p>';
                return;
            }
            listEl.innerHTML = customers.map(c => `
                <div class="customer-item" data-id="${c.id}" onclick="CustomerSim.selectCustomer(${c.id})">
                    <div>
                        <span class="name">${c.name}</span>
                        <span class="meta">${c.city} &bull; ${c.language_pref}</span>
                    </div>
                    <span class="meta">${c.phone}</span>
                </div>
            `).join('');
        } catch (e) {
            listEl.innerHTML = `<p class="muted">Could not load customers: ${e.message}</p>`;
        }
    }

    async function selectCustomer(id) {
        selectedCustomerId = id;

        // Highlight selected
        document.querySelectorAll('.customer-item').forEach(el => {
            el.classList.toggle('selected', parseInt(el.dataset.id) === id);
        });

        // Load details
        try {
            const data = await App.api(`/api/customers/${id}`);
            const c = data.customer;
            const detailEl = document.getElementById('customer-detail');

            document.getElementById('cust-name').textContent = c.name;
            document.getElementById('cust-city').textContent = c.city;
            document.getElementById('cust-lang').textContent = c.language_pref;
            document.getElementById('cust-phone').textContent = c.phone;

            const loansEl = document.getElementById('cust-loans');
            if (data.loans.length) {
                loansEl.innerHTML = data.loans.map(l => `
                    <div class="loan-card ${l.days_overdue > 0 ? 'overdue' : ''}">
                        <div><span class="loan-type">${l.loan_type}</span></div>
                        <div>EMI: ₹${Number(l.emi_amount).toLocaleString('en-IN')} &bull;
                             Overdue: <span class="loan-amount">₹${Number(l.overdue_amount).toLocaleString('en-IN')}</span> &bull;
                             ${l.days_overdue} days</div>
                    </div>
                `).join('');
            } else {
                loansEl.innerHTML = '<p class="muted">No loans found.</p>';
            }

            detailEl.classList.remove('hidden');

            // Show phone number in dial input and show it
            const dialInput = document.getElementById('dial-number');
            if (dialInput) {
                dialInput.value = c.phone;
                dialInput.style.display = 'block';
            }
        } catch (e) {
            console.error('Failed to load customer:', e);
        }
    }

    async function dialCall() {
        if (!selectedCustomerId) return;

        const toNumber = document.getElementById('dial-number')?.value;
        if (!toNumber) {
            alert('Enter the phone number to dial');
            return;
        }

        const callPurpose = document.getElementById('call-purpose')?.value || 'LOAN_RECOVERY';
        const transcriptEl = document.getElementById('call-transcript');
        transcriptEl.innerHTML = '<p class="loading">Dialing real call...</p>';

        try {
            const data = await App.api('/api/voice/dial', {
                method: 'POST',
                body: JSON.stringify({
                    customer_id: selectedCustomerId,
                    to_number: toNumber,
                    call_purpose: callPurpose,
                }),
            });

            if (data.error) {
                transcriptEl.innerHTML = `<p class="muted">Dial failed: ${data.error}</p>`;
                return;
            }

            transcriptEl.innerHTML = '';
            appendMessage('agent', `📞 Real call dialing to ${toNumber}... (Call SID: ${data.call_sid})`, 'DIALING');
            appendMessage('agent', 'Twilio is connecting the call. The agent will speak when customer picks up.', 'CONNECTING');

            // Show greeting
            if (data.greeting) {
                appendMessage('agent', data.greeting, 'GREETING');
                App.addTranscriptEntry('agent', data.greeting, 'GREETING');
            }

            App.updateCallState({
                callId: data.call_id,
                customerId: selectedCustomerId,
                customerName: data.customer_name,
                stage: 'GREETING',
                isActive: true,
                transcript: [],
            });

            // Show phone call controls
            document.getElementById('call-controls')?.classList.remove('hidden');
            document.getElementById('call-stage')?.classList.add('active');
            document.getElementById('call-stage').textContent = 'REAL CALL — GREETING';

            // Store that this is a phone call
            App.state.isPhoneCall = true;
            App.state.twilioSid = data.call_sid;

        } catch (e) {
            transcriptEl.innerHTML = `<p class="muted">Dial error: ${e.message}</p>`;
        }
    }

    async function startCall() {
        if (!selectedCustomerId) return;

        const transcriptEl = document.getElementById('call-transcript');
        transcriptEl.innerHTML = '<p class="loading">Starting call...</p>';

        try {
            const callPurpose = document.getElementById('call-purpose')?.value || 'LOAN_RECOVERY';
            const data = await App.api('/api/call/start', {
                method: 'POST',
                body: JSON.stringify({
                    customer_id: selectedCustomerId,
                    language: 'hi',
                    call_purpose: callPurpose,
                }),
            });

            // Update shared state
            App.updateCallState({
                callId: data.call_id,
                customerId: selectedCustomerId,
                customerName: data.customer_name,
                stage: data.stage,
                language: data.language,
                turnCount: 0,
                isActive: true,
                transcript: [],
                contextUsed: [],
            });

            // Show greeting
            transcriptEl.innerHTML = '';
            appendMessage('agent', data.greeting_text, data.stage);
            App.addTranscriptEntry('agent', data.greeting_text, data.stage);

            // Play greeting audio
            if (data.greeting_audio_b64) {
                AudioManager.playAudioB64(data.greeting_audio_b64, document.getElementById('agent-audio-container'));
            }

            // Show controls
            document.getElementById('call-controls')?.classList.remove('hidden');
            document.getElementById('call-stage').textContent = data.stage;
            document.getElementById('call-stage').classList.add('active');

        } catch (e) {
            transcriptEl.innerHTML = `<p class="muted">Failed to start call: ${e.message}</p>`;
        }
    }

    async function sendText() {
        const input = document.getElementById('text-input');
        const text = input.value.trim();
        if (!text || !App.state.callId) return;

        input.value = '';
        appendMessage('customer', text, App.state.stage);
        App.addTranscriptEntry('customer', text, App.state.stage);

        // Phone call: use telephony process-turn (agent speaks on phone)
        if (App.state.isPhoneCall) {
            await processPhoneTurn(text);
        } else {
            await processTurn({ text });
        }
    }

    async function processPhoneTurn(customerText) {
        try {
            const data = await App.api('/api/telephony/process-turn', {
                method: 'POST',
                body: JSON.stringify({
                    call_id: App.state.callId,
                    customer_text: customerText,
                }),
            });

            if (data.error) {
                appendMessage('agent', `Error: ${data.error}`, App.state.stage);
                return;
            }

            appendMessage('agent', `🔊 ${data.agent_text}`, data.stage);
            App.addTranscriptEntry('agent', data.agent_text, data.stage);

            App.updateCallState({
                stage: data.stage,
                turnCount: App.state.turnCount + 1,
            });
            document.getElementById('call-stage').textContent = `REAL CALL — ${data.stage}`;

            if (data.is_ended) {
                onCallEnded(data.outcome || 'COMPLETED');
                App.state.isPhoneCall = false;
            }
        } catch (e) {
            appendMessage('agent', `Error: ${e.message}`, App.state.stage);
        }
    }

    async function sendVoice() {
        const audio = AudioManager.getAudioB64();
        if (!audio || !App.state.callId) return;

        appendMessage('customer', '🎤 (voice message)', App.state.stage);
        await processTurn({ audio_b64: audio });
    }

    async function processTurn(payload) {
        try {
            const data = await App.api('/api/call/turn', {
                method: 'POST',
                body: JSON.stringify({
                    call_id: App.state.callId,
                    ...payload,
                }),
            });

            // If voice input, update with recognized text
            if (payload.audio_b64 && data.customer_text) {
                const msgs = document.querySelectorAll('#call-transcript .msg.customer');
                const lastMsg = msgs[msgs.length - 1];
                if (lastMsg) {
                    lastMsg.querySelector('.msg-text').textContent = data.customer_text;
                }
                App.addTranscriptEntry('customer', data.customer_text, data.stage);
            }

            // Show agent response
            appendMessage('agent', data.agent_text, data.stage);
            App.addTranscriptEntry('agent', data.agent_text, data.stage);

            // Play audio
            if (data.agent_audio_b64) {
                AudioManager.playAudioB64(data.agent_audio_b64, document.getElementById('agent-audio-container'));
            }

            // Update state
            App.updateCallState({
                stage: data.stage,
                turnCount: App.state.turnCount + 1,
                contextUsed: data.context_used || [],
            });

            document.getElementById('call-stage').textContent = data.stage;

            // Check if call ended
            if (data.is_ended) {
                onCallEnded(data.outcome);
            }
        } catch (e) {
            appendMessage('agent', `Error: ${e.message}`, App.state.stage);
        }
    }

    async function endCall() {
        if (!App.state.callId) return;

        try {
            await App.api('/api/call/end', {
                method: 'POST',
                body: JSON.stringify({ call_id: App.state.callId }),
            });
            onCallEnded('MANUAL_END');
        } catch (e) {
            console.error('Failed to end call:', e);
        }
    }

    function onCallEnded(outcome) {
        App.updateCallState({ isActive: false });
        document.getElementById('call-controls')?.classList.add('hidden');
        document.getElementById('call-stage').textContent = `ENDED — ${outcome || 'N/A'}`;
        document.getElementById('call-stage').classList.remove('active');
        appendMessage('agent', '--- Call Ended ---', 'CLOSED');
    }

    function appendMessage(speaker, text, stage) {
        const el = document.getElementById('call-transcript');
        const msgDiv = document.createElement('div');
        msgDiv.className = `msg ${speaker}`;
        msgDiv.innerHTML = `
            <div class="msg-label">${speaker === 'agent' ? 'VaaniSeva' : 'Customer'} [${stage}]</div>
            <div class="msg-text">${text}</div>
        `;
        el.appendChild(msgDiv);
        el.scrollTop = el.scrollHeight;
    }

    return { init, selectCustomer };
})();
