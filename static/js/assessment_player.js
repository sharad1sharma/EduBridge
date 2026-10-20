/**
 * EduBridge Assessment Player & Integrity Controller
 * Adheres strictly to CSP (script-src 'self')
 * Handles countdown timer, autosave sync, tab-switch integrity, and auto-submission
 */
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('assessmentForm');
    const timerEl = document.getElementById('assessmentTimer');
    const autosaveEl = document.getElementById('autosaveStatus');
    const counterEl = document.getElementById('answeredCounter');

    if (!form || !timerEl) return;

    const assessmentId = form.getAttribute('data-assessment-id');
    let remainingSeconds = parseInt(form.getAttribute('data-remaining-seconds') || '0', 10);
    let tabSwitches = 0;
    let isSubmitting = false;

    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        if (cookie) return cookie.split('=')[1];
        const input = form.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function formatTime(secs) {
        if (secs <= 0) return '00:00';
        const mins = Math.floor(secs / 60);
        const remSecs = secs % 60;
        return `${String(mins).padStart(2, '0')}:${String(remSecs).padStart(2, '0')}`;
    }

    function updateAnswerCounter() {
        const checkedRadios = form.querySelectorAll('input[type=radio]:checked');
        const filledCode = form.querySelectorAll('textarea[name^="code_"]');
        let codeCount = 0;
        filledCode.forEach(ta => { if (ta.value.trim().length > 0) codeCount++; });
        if (counterEl) {
            counterEl.textContent = `${checkedRadios.length + codeCount} answered`;
        }
    }

    function getAnswersPayload() {
        const answers = {};
        const checked = form.querySelectorAll('input[type=radio]:checked');
        checked.forEach(r => {
            const name = r.getAttribute('name'); // e.g. q_1
            if (name && name.startsWith('q_')) {
                answers[name.replace('q_', '')] = r.value;
            }
        });
        const codeAreas = form.querySelectorAll('textarea[name^="code_"]');
        codeAreas.forEach(ta => {
            const name = ta.getAttribute('name'); // e.g. code_1
            if (name && name.startsWith('code_')) {
                answers['coding_' + name.replace('code_', '')] = ta.value;
            }
        });
        return answers;
    }

    // Restore saved answers from previous session / refresh
    try {
        const rawSaved = form.getAttribute('data-saved-answers');
        if (rawSaved) {
            const savedAnswers = JSON.parse(rawSaved);
            Object.keys(savedAnswers).forEach(key => {
                const val = savedAnswers[key];
                if (key.startsWith('coding_')) {
                    const cid = key.replace('coding_', '');
                    const ta = form.querySelector(`textarea[name="code_${cid}"]`);
                    if (ta && val) ta.value = (typeof val === 'object' ? (val.code || '') : val);
                } else {
                    const radio = form.querySelector(`input[name="q_${key}"][value="${val}"]`);
                    if (radio) radio.checked = true;
                }
            });
        }
    } catch (err) {
        console.warn('EduBridge: Could not restore previous answers:', err);
    }

    async function sendAutosave(isTabSwitch = false) {
        if (isSubmitting) return;
        try {
            if (autosaveEl) autosaveEl.textContent = 'Saving...';
            const resp = await fetch(`/student/assessment/${assessmentId}/autosave/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    answers: getAnswersPayload(),
                    tab_switch: isTabSwitch
                })
            });

            if (resp.ok) {
                const data = await resp.json();
                if (data.status === 'auto_submitted' || data.status === 'time_expired') {
                    isSubmitting = true;
                    alert(data.reason || 'Assessment submitted automatically per institutional policy.');
                    window.location.href = data.redirect || '/student/results/';
                    return;
                }
                if (autosaveEl) autosaveEl.textContent = 'Answers saved';
            }
        } catch (err) {
            if (autosaveEl) autosaveEl.textContent = 'Offline (will retry)';
        }
    }

    // 1. Timer countdown interval
    timerEl.textContent = formatTime(remainingSeconds);
    const timerInterval = setInterval(function () {
        remainingSeconds -= 1;
        timerEl.textContent = formatTime(remainingSeconds);

        if (remainingSeconds <= 60 && remainingSeconds > 0) {
            timerEl.style.color = '#DC2626';
            timerEl.style.animation = 'pulse 1s infinite';
        }

        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            if (!isSubmitting) {
                isSubmitting = true;
                if (autosaveEl) autosaveEl.textContent = 'Time expired! Finalizing...';
                form.submit();
            }
        }
    }, 1000);

    // 2. Periodic Autosave every 20 seconds
    const autosaveInterval = setInterval(function () {
        if (!isSubmitting) sendAutosave(false);
    }, 20000);

    // 3. Radio button change listener
    form.addEventListener('change', function (e) {
        if (e.target.matches('input[type=radio]')) {
            updateAnswerCounter();
            sendAutosave(false);
        }
    });

    // 4. Tab visibility monitoring for anti-cheating policy
    document.addEventListener('visibilitychange', function () {
        if (document.hidden && !isSubmitting) {
            tabSwitches += 1;
            sendAutosave(true);
        }
    });

    // 5. Form submission handler
    form.addEventListener('submit', function (e) {
        if (!isSubmitting) {
            const ok = confirm('Are you sure you want to finalize and submit your assessment? You cannot change answers after submission.');
            if (!ok) {
                e.preventDefault();
                return false;
            }
        }
        isSubmitting = true;
        clearInterval(timerInterval);
        clearInterval(autosaveInterval);
    });

    updateAnswerCounter();
});
