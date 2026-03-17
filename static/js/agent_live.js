/**
 * VaaniSeva — Agent Live View persona.
 */
const AgentLive = (() => {
    const STAGE_ORDER = [
        'GREETING', 'IDENTITY_VERIFICATION', 'PURPOSE',
        'NEGOTIATION', 'RESOLUTION', 'CLOSING'
    ];

    function init() {
        // Initial state
    }

    function onStateUpdate(state) {
        document.getElementById('live-call-id').textContent = state.callId || '—';
        document.getElementById('live-language').textContent = state.language || '—';
        document.getElementById('live-turn').textContent = state.turnCount || 0;

        const stageBadge = document.getElementById('live-stage');
        if (state.stage) {
            stageBadge.textContent = state.stage;
            stageBadge.classList.add('active');
        } else {
            stageBadge.textContent = '—';
            stageBadge.classList.remove('active');
        }

        // Update flow visualization
        updateFlowViz(state.stage);

        // Update context panel
        updateContext(state.contextUsed);
    }

    function onTranscriptUpdate(transcript) {
        const el = document.getElementById('live-transcript');
        el.innerHTML = '';
        transcript.forEach(t => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `msg ${t.speaker}`;
            msgDiv.innerHTML = `
                <div class="msg-label">${t.speaker === 'agent' ? 'VaaniSeva' : 'Customer'} [${t.stage || ''}]</div>
                <div class="msg-text">${t.text}</div>
            `;
            el.appendChild(msgDiv);
        });
        el.scrollTop = el.scrollHeight;
    }

    function updateFlowViz(currentStage) {
        const steps = document.querySelectorAll('#call-flow-viz .flow-step');
        const currentIdx = STAGE_ORDER.indexOf(currentStage);

        steps.forEach(step => {
            const stepStage = step.dataset.stage;
            const stepIdx = STAGE_ORDER.indexOf(stepStage);

            step.classList.remove('current', 'completed');
            if (stepIdx === currentIdx) {
                step.classList.add('current');
            } else if (stepIdx < currentIdx) {
                step.classList.add('completed');
            }
        });
    }

    function updateContext(contextUsed) {
        const el = document.getElementById('live-context');
        if (!contextUsed || !contextUsed.length) {
            el.innerHTML = '<p class="muted">No context retrieved yet.</p>';
            return;
        }

        el.innerHTML = contextUsed.map(c => `
            <div class="context-item">
                <div class="context-type">${c.type}</div>
                <div>${c.content}</div>
            </div>
        `).join('');
    }

    return { init, onStateUpdate, onTranscriptUpdate };
})();
