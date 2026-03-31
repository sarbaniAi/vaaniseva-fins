/**
 * VaaniSeva — Tab routing and shared state.
 */
const App = (() => {
    // Shared call state (accessible by all persona modules)
    const state = {
        callId: null,
        customerId: null,
        customerName: null,
        stage: null,
        language: null,
        turnCount: 0,
        isActive: false,
        transcript: [],
        contextUsed: [],
    };

    function init() {
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(tab)?.classList.add('active');
            });
        });

        // Initialize persona modules
        CustomerSim.init();
        AgentLive.init();
        QualityAudit.init();
        if (typeof WhatsApp !== 'undefined') WhatsApp.init();
    }

    // API helper
    async function api(path, options = {}) {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!resp.ok) {
            const err = await resp.text();
            throw new Error(`API error ${resp.status}: ${err}`);
        }
        return resp.json();
    }

    // Update shared state and notify live view
    function updateCallState(updates) {
        Object.assign(state, updates);
        AgentLive.onStateUpdate(state);
    }

    function addTranscriptEntry(speaker, text, stage) {
        state.transcript.push({ speaker, text, stage });
        AgentLive.onTranscriptUpdate(state.transcript);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { state, api, updateCallState, addTranscriptEntry };
})();
