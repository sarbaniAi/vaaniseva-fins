/**
 * VaaniSeva — Browser audio capture (MediaRecorder) + playback.
 */
const AudioManager = (() => {
    let recorder = null;
    let chunks = [];
    let recording = false;
    let timer = null;
    let seconds = 0;
    let audioB64 = null;

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recorder = new MediaRecorder(stream);
            chunks = [];
            audioB64 = null;

            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };

            recorder.onstop = () => {
                const blob = new Blob(chunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.onloadend = () => {
                    // Store full data URI, will strip prefix before sending
                    audioB64 = reader.result;
                };
                reader.readAsDataURL(blob);
                stream.getTracks().forEach(t => t.stop());
            };

            recorder.start();
            recording = true;
            seconds = 0;
            _updateTimerUI(true);
            timer = setInterval(() => {
                seconds++;
                const m = String(Math.floor(seconds / 60)).padStart(2, '0');
                const s = String(seconds % 60).padStart(2, '0');
                const el = document.getElementById('rec-time');
                if (el) el.textContent = `${m}:${s}`;
            }, 1000);
            return true;
        } catch (err) {
            console.error('Mic access denied:', err);
            return false;
        }
    }

    function stopRecording() {
        if (recorder && recorder.state !== 'inactive') {
            recorder.stop();
        }
        recording = false;
        clearInterval(timer);
        _updateTimerUI(false);
    }

    function getAudioB64() {
        if (!audioB64) return null;
        // Strip data URI prefix
        if (audioB64.includes('base64,')) {
            return audioB64.split('base64,')[1];
        }
        return audioB64;
    }

    function isRecording() {
        return recording;
    }

    function playAudioB64(b64, container) {
        if (!b64 || !container) return;
        container.innerHTML = `<audio controls autoplay style="width:100%" src="data:audio/wav;base64,${b64}"></audio>`;
    }

    function _updateTimerUI(show) {
        const timerEl = document.getElementById('rec-timer');
        const recBtn = document.getElementById('btn-record');
        const stopBtn = document.getElementById('btn-stop-record');
        const sendBtn = document.getElementById('btn-send-voice');

        if (show) {
            timerEl?.classList.remove('hidden');
            stopBtn?.classList.remove('hidden');
            recBtn?.classList.add('hidden');
        } else {
            timerEl?.classList.add('hidden');
            stopBtn?.classList.add('hidden');
            recBtn?.classList.remove('hidden');
            sendBtn?.classList.remove('hidden');
        }
    }

    return { startRecording, stopRecording, getAudioB64, isRecording, playAudioB64 };
})();
