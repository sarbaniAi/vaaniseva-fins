/**
 * VaaniSeva — Quality Auditor persona.
 */
const QualityAudit = (() => {
    function init() {
        document.getElementById('btn-run-audit')?.addEventListener('click', runAudit);
        loadDashboard();
        loadScores();
    }

    async function loadDashboard() {
        try {
            const stats = await App.api('/api/dashboard/stats');
            document.getElementById('stat-total-calls').textContent = stats.total_calls;
            document.getElementById('stat-avg-score').textContent = stats.avg_quality_score || '—';
            document.getElementById('stat-resolution-rate').textContent = `${stats.resolution_rate || 0}%`;
        } catch (e) {
            console.error('Failed to load dashboard:', e);
        }
    }

    async function loadScores() {
        const tbody = document.getElementById('audit-table-body');
        try {
            const scores = await App.api('/api/audit/scores');
            if (!scores.length) {
                tbody.innerHTML = '<tr><td colspan="10" class="muted">No scored calls yet.</td></tr>';
                return;
            }
            tbody.innerHTML = scores.map(s => `
                <tr onclick="QualityAudit.showDetail('${s.call_id}')">
                    <td>${s.call_id}</td>
                    <td>${s.customer_name || '—'}</td>
                    <td>${s.language || '—'}</td>
                    <td>${s.outcome || '—'}</td>
                    <td><strong>${scoreColor(s.overall_score)}</strong></td>
                    <td>${scoreColor(s.compliance_score)}</td>
                    <td>${scoreColor(s.script_adherence_score)}</td>
                    <td>${scoreColor(s.empathy_score)}</td>
                    <td>${scoreColor(s.resolution_score)}</td>
                    <td>${scoreColor(s.language_quality_score)}</td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="10" class="muted">Error: ${e.message}</td></tr>`;
        }
    }

    async function runAudit() {
        const btn = document.getElementById('btn-run-audit');
        btn.textContent = 'Running...';
        btn.disabled = true;
        try {
            const result = await App.api('/api/audit/run', {
                method: 'POST',
                body: JSON.stringify({}),
            });
            alert(`Audit complete: ${result.scored} call(s) scored`);
            await loadDashboard();
            await loadScores();
        } catch (e) {
            alert(`Audit failed: ${e.message}`);
        } finally {
            btn.textContent = 'Run Audit (All Unscored)';
            btn.disabled = false;
        }
    }

    async function showDetail(callId) {
        try {
            const score = await App.api(`/api/audit/scores/${callId}`);
            const panel = document.getElementById('score-detail');
            document.getElementById('detail-call-id').textContent = callId;

            // Score bars
            const bars = document.getElementById('score-bars');
            const categories = [
                { label: 'Compliance', score: score.compliance_score, weight: '30%' },
                { label: 'Script', score: score.script_adherence_score, weight: '20%' },
                { label: 'Empathy', score: score.empathy_score, weight: '20%' },
                { label: 'Resolution', score: score.resolution_score, weight: '20%' },
                { label: 'Language', score: score.language_quality_score, weight: '10%' },
            ];
            bars.innerHTML = categories.map(c => `
                <div class="score-bar-row">
                    <span class="score-bar-label">${c.label} (${c.weight})</span>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width:${c.score}%;background:${barColor(c.score)}"></div>
                    </div>
                    <span class="score-bar-value">${c.score}</span>
                </div>
            `).join('');

            // Findings
            const findingsEl = document.getElementById('detail-findings');
            const findings = Array.isArray(score.findings) ? score.findings : JSON.parse(score.findings || '[]');
            findingsEl.innerHTML = findings.map(f => `<li>${f}</li>`).join('') || '<li class="muted">None</li>';

            // Recommendations
            const recsEl = document.getElementById('detail-recommendations');
            const recs = Array.isArray(score.recommendations) ? score.recommendations : JSON.parse(score.recommendations || '[]');
            recsEl.innerHTML = recs.map(r => `<li>${r}</li>`).join('') || '<li class="muted">None</li>';

            panel.classList.remove('hidden');
            panel.scrollIntoView({ behavior: 'smooth' });
        } catch (e) {
            console.error('Failed to load score detail:', e);
        }
    }

    function scoreColor(score) {
        if (score >= 90) return `<span style="color:#28A745">${score}</span>`;
        if (score >= 70) return `<span style="color:#17a2b8">${score}</span>`;
        if (score >= 50) return `<span style="color:#FFC107">${score}</span>`;
        return `<span style="color:#DC3545">${score}</span>`;
    }

    function barColor(score) {
        if (score >= 90) return '#28A745';
        if (score >= 70) return '#17a2b8';
        if (score >= 50) return '#FFC107';
        return '#DC3545';
    }

    return { init, showDetail };
})();
