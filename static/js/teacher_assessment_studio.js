/**
 * EduBridge Teacher Assessment Authoring Studio
 * Strictly adheres to institutional CSP (script-src 'self', no inline scripts/eval)
 * Powers Manual Builder, Bulk MCQ Parser, TeachMate AI Question Generator, and Form Submission
 */
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('assessmentAuthorForm');
    if (!form) return;

    const questionsJsonInput = document.getElementById('questions_json');
    const codingJsonInput = document.getElementById('coding_problems_json');
    const actionInput = document.getElementById('formSubmitAction');

    const paneManual = document.getElementById('paneManual');
    const paneBulk = document.getElementById('paneBulk');
    const paneAi = document.getElementById('paneAi');

    const tabBtnManual = document.getElementById('tabBtnManual');
    const tabBtnBulk = document.getElementById('tabBtnBulk');
    const tabBtnAi = document.getElementById('tabBtnAi');

    const mcqContainer = document.getElementById('mcqListContainer');
    const codingContainer = document.getElementById('codingListContainer');
    const counterSummary = document.getElementById('qCounterSummary');

    let questions = [];
    let codingProblems = [];

    // Helper: CSRF token retrieval
    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        if (cookie) return cookie.split('=')[1];
        const csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
        return csrfInput ? csrfInput.value : '';
    }

    // Helper: HTML string escaping
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // 1. Initialize Questions from hidden inputs or default starter set
    try {
        if (questionsJsonInput && questionsJsonInput.value.trim()) {
            const parsed = JSON.parse(questionsJsonInput.value);
            if (Array.isArray(parsed)) questions = parsed;
        }
    } catch (e) {
        questions = [];
    }

    try {
        if (codingJsonInput && codingJsonInput.value.trim()) {
            const parsed = JSON.parse(codingJsonInput.value);
            if (Array.isArray(parsed)) codingProblems = parsed;
        }
    } catch (e) {
        codingProblems = [];
    }

    // Starter questions if completely empty on new creation
    if (questions.length === 0 && codingProblems.length === 0) {
        const defaultTopic = (document.getElementById('topic') && document.getElementById('topic').value.trim()) || 'Engineering Coursework';
        questions = [
            {
                id: 1,
                question: `What is the worst-case asymptotic time complexity of searching in an AVL Tree for ${defaultTopic}?`,
                options: ["A) O(1)", "B) O(log n)", "C) O(n)", "D) O(n log n)"],
                correct: "B",
                marks: 4,
                explanation: "An AVL tree maintains a balance factor in {-1, 0, 1}, guaranteeing height O(log n)."
            },
            {
                id: 2,
                question: "Which algorithmic paradigm is employed by Dijkstra's shortest path algorithm?",
                options: ["A) Dynamic Programming", "B) Greedy Method", "C) Divide and Conquer", "D) Backtracking"],
                correct: "B",
                marks: 4,
                explanation: "Dijkstra greedily chooses the unvisited vertex with the minimum distance at each step."
            }
        ];
    }

    // 2. Tab Switching Logic
    function switchTab(activePane, activeBtn) {
        if (paneManual) paneManual.style.display = 'none';
        if (paneBulk) paneBulk.style.display = 'none';
        if (paneAi) paneAi.style.display = 'none';

        [tabBtnManual, tabBtnBulk, tabBtnAi].forEach(btn => {
            if (btn) {
                btn.style.background = '';
                btn.style.color = '';
                btn.style.border = '';
            }
        });

        if (activePane) activePane.style.display = 'block';
        if (activeBtn) {
            activeBtn.style.background = 'var(--brand-primary, #2563EB)';
            activeBtn.style.color = '#FFFFFF';
        }
    }

    if (tabBtnManual) tabBtnManual.addEventListener('click', () => switchTab(paneManual, tabBtnManual));
    if (tabBtnBulk) tabBtnBulk.addEventListener('click', () => switchTab(paneBulk, tabBtnBulk));
    if (tabBtnAi) tabBtnAi.addEventListener('click', () => switchTab(paneAi, tabBtnAi));

    // 3. Synchronize hidden form inputs
    function syncHiddenInputs() {
        if (questionsJsonInput) questionsJsonInput.value = JSON.stringify(questions);
        if (codingJsonInput) codingJsonInput.value = JSON.stringify(codingProblems);
        if (counterSummary) {
            counterSummary.textContent = `${questions.length} MCQs, ${codingProblems.length} Coding Challenges`;
        }
    }

    // 4. Render Questions into DOM with event-delegated hooks (CSP compliant)
    function renderQuestions() {
        syncHiddenInputs();

        if (mcqContainer) {
            if (questions.length === 0) {
                mcqContainer.innerHTML = `
                    <div style="padding: 1.5rem; text-align: center; background: #F8FAFC; border: 1px dashed var(--border-subtle); border-radius: 8px; color: var(--text-muted); font-size: 0.85rem;">
                        No MCQs added yet. Click <strong>+ Add MCQ</strong> above, paste via <strong>Bulk Paste</strong>, or generate with <strong>AI Generate</strong>.
                    </div>
                `;
            } else {
                mcqContainer.innerHTML = questions.map((q, idx) => {
                    const opts = Array.isArray(q.options) && q.options.length >= 2 ? q.options : ['A) Option A', 'B) Option B', 'C) Option C', 'D) Option D'];
                    const correctLetter = (q.correct || 'A').toUpperCase().trim();

                    return `
                        <div class="card" style="padding: 1.25rem; border-left: 4px solid var(--brand-primary, #2563EB); background: #FAFBFD; margin-bottom: 0.85rem;" data-mcq-card="${idx}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                                <span style="font-weight: 700; font-size: 0.9rem; color: var(--brand-primary, #2563EB);">MCQ Question ${idx + 1}</span>
                                <button type="button" class="btn small delete-mcq-btn" data-action="delete-mcq" data-idx="${idx}" style="color: #DC2626; border-color: #FECACA; background: #FEF2F2; cursor: pointer;">
                                    🗑️ Delete Question
                                </button>
                            </div>
                            <div style="margin-bottom: 0.75rem;">
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Question Statement:</label>
                                <input type="text" class="form-input mcq-statement-input" data-idx="${idx}" value="${escapeHtml(q.question)}" placeholder="Enter question text here..." required>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;">
                                ${opts.map((opt, oIdx) => {
                                    const optLetter = String.fromCharCode(65 + oIdx);
                                    const isCorrect = correctLetter === optLetter;
                                    return `
                                        <div class="mcq-option-row" style="display: flex; align-items: center; gap: 0.65rem; background: white; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--border-subtle); box-sizing: border-box;">
                                            <input type="radio" name="correct_mcq_${idx}" data-action="set-correct" data-idx="${idx}" value="${optLetter}" ${isCorrect ? 'checked' : ''} style="margin: 0; cursor: pointer; width: 18px; height: 18px; flex-shrink: 0; vertical-align: middle; accent-color: var(--brand-primary, #2563EB);">
                                            <span style="font-weight: 700; font-size: 0.85rem; color: var(--text-main); min-width: 16px; text-align: center; flex-shrink: 0; line-height: 1;">${optLetter}</span>
                                            <input type="text" class="form-input mcq-option-input" data-idx="${idx}" data-oidx="${oIdx}" style="padding: 0.35rem 0.5rem; font-size: 0.85rem; flex: 1; margin: 0; min-width: 0;" value="${escapeHtml(opt)}" placeholder="Option text">
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                            <div style="display: grid; grid-template-columns: 3fr 1fr; gap: 0.75rem;">
                                <div>
                                    <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Pedagogical Explanation:</label>
                                    <input type="text" class="form-input mcq-explanation-input" data-idx="${idx}" style="font-size: 0.85rem;" value="${escapeHtml(q.explanation || '')}" placeholder="Why is this the correct answer?">
                                </div>
                                <div>
                                    <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Marks:</label>
                                    <input type="number" step="0.5" class="form-input mcq-marks-input" data-idx="${idx}" style="font-size: 0.85rem;" value="${q.marks || 4}" min="1" max="50">
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        if (codingContainer) {
            if (codingProblems.length === 0) {
                codingContainer.innerHTML = '';
            } else {
                codingContainer.innerHTML = codingProblems.map((c, cIdx) => `
                    <div class="card" style="padding: 1.25rem; border-left: 4px solid #7C3AED; background: #FAF5FF; margin-bottom: 0.85rem;" data-coding-card="${cIdx}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                            <span style="font-weight: 700; font-size: 0.9rem; color: #7C3AED;">💻 Coding Challenge ${cIdx + 1}: ${escapeHtml(c.title || 'Challenge')}</span>
                            <button type="button" class="btn small delete-coding-btn" data-action="delete-coding" data-idx="${cIdx}" style="color: #DC2626; border-color: #FECACA; background: #FEF2F2; cursor: pointer;">
                                🗑️ Delete Challenge
                            </button>
                        </div>
                        <div style="display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;">
                            <div>
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Problem Title:</label>
                                <input type="text" class="form-input coding-field-input" data-idx="${cIdx}" data-field="title" value="${escapeHtml(c.title || '')}" placeholder="e.g. Invert a Binary Tree" required>
                            </div>
                            <div>
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Language:</label>
                                <select class="form-select coding-field-input" data-idx="${cIdx}" data-field="lang">
                                    <option value="python" ${(c.lang || 'python') === 'python' ? 'selected' : ''}>Python 3</option>
                                    <option value="cpp" ${c.lang === 'cpp' ? 'selected' : ''}>C++ 17</option>
                                    <option value="java" ${c.lang === 'java' ? 'selected' : ''}>Java 17</option>
                                </select>
                            </div>
                            <div>
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Marks:</label>
                                <input type="number" step="1" class="form-input coding-field-input" data-idx="${cIdx}" data-field="marks" value="${c.marks || 10}" min="1" max="100">
                            </div>
                        </div>
                        <div style="margin-bottom: 0.75rem;">
                            <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Problem Description & Constraints:</label>
                            <textarea class="form-input coding-field-input" data-idx="${cIdx}" data-field="description" rows="2" placeholder="Explain the problem statement and bounds...">${escapeHtml(c.description || '')}</textarea>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                            <div>
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Sample Input:</label>
                                <textarea class="form-input coding-field-input" data-idx="${cIdx}" data-field="sample_input" rows="2" style="font-family: monospace;" placeholder="Sample input data...">${escapeHtml(c.sample_input || '')}</textarea>
                            </div>
                            <div>
                                <label style="display: block; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem;">Sample Output:</label>
                                <textarea class="form-input coding-field-input" data-idx="${cIdx}" data-field="sample_output" rows="2" style="font-family: monospace;" placeholder="Expected output...">${escapeHtml(c.sample_output || '')}</textarea>
                            </div>
                        </div>
                    </div>
                `);
            }
        }
    }

    // 5. Event Delegation for MCQs container (No inline handlers)
    if (mcqContainer) {
        mcqContainer.addEventListener('click', function (e) {
            const delBtn = e.target.closest('[data-action="delete-mcq"]');
            if (delBtn) {
                const idx = parseInt(delBtn.getAttribute('data-idx'), 10);
                if (!isNaN(idx) && idx >= 0 && idx < questions.length) {
                    questions.splice(idx, 1);
                    renderQuestions();
                }
            }
        });

        mcqContainer.addEventListener('change', function (e) {
            const radio = e.target.closest('[data-action="set-correct"]');
            if (radio) {
                const idx = parseInt(radio.getAttribute('data-idx'), 10);
                if (!isNaN(idx) && questions[idx]) {
                    questions[idx].correct = radio.value;
                    syncHiddenInputs();
                }
            }
        });

        mcqContainer.addEventListener('input', function (e) {
            const target = e.target;
            const idx = parseInt(target.getAttribute('data-idx'), 10);
            if (isNaN(idx) || !questions[idx]) return;

            if (target.classList.contains('mcq-statement-input')) {
                questions[idx].question = target.value;
                syncHiddenInputs();
            } else if (target.classList.contains('mcq-option-input')) {
                const oIdx = parseInt(target.getAttribute('data-oidx'), 10);
                if (!isNaN(oIdx)) {
                    if (!Array.isArray(questions[idx].options)) questions[idx].options = [];
                    questions[idx].options[oIdx] = target.value;
                    syncHiddenInputs();
                }
            } else if (target.classList.contains('mcq-explanation-input')) {
                questions[idx].explanation = target.value;
                syncHiddenInputs();
            } else if (target.classList.contains('mcq-marks-input')) {
                questions[idx].marks = parseFloat(target.value) || 4;
                syncHiddenInputs();
            }
        });
    }

    // 6. Event Delegation for Coding container
    if (codingContainer) {
        codingContainer.addEventListener('click', function (e) {
            const delBtn = e.target.closest('[data-action="delete-coding"]');
            if (delBtn) {
                const idx = parseInt(delBtn.getAttribute('data-idx'), 10);
                if (!isNaN(idx) && idx >= 0 && idx < codingProblems.length) {
                    codingProblems.splice(idx, 1);
                    renderQuestions();
                }
            }
        });

        codingContainer.addEventListener('input', function (e) {
            const target = e.target;
            const idx = parseInt(target.getAttribute('data-idx'), 10);
            const field = target.getAttribute('data-field');
            if (!isNaN(idx) && field && codingProblems[idx]) {
                if (field === 'marks') {
                    codingProblems[idx][field] = parseFloat(target.value) || 10;
                } else {
                    codingProblems[idx][field] = target.value;
                }
                syncHiddenInputs();
            }
        });
    }

    // 7. Add MCQ and Add Coding Problem Button Listeners
    const addMcqBtn = document.getElementById('addMcqBtn');
    if (addMcqBtn) {
        addMcqBtn.addEventListener('click', function () {
            const nextId = questions.length + 1;
            questions.push({
                id: nextId,
                question: `Engineering Practice Problem #${nextId}`,
                options: ["A) Primary Option A", "B) Alternative Option B", "C) Option C", "D) Option D"],
                correct: "A",
                explanation: "",
                marks: 4
            });
            renderQuestions();
            // Scroll to the new question
            const lastCard = mcqContainer ? mcqContainer.lastElementChild : null;
            if (lastCard) lastCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    }

    const addCodingBtn = document.getElementById('addCodingBtn');
    if (addCodingBtn) {
        addCodingBtn.addEventListener('click', function () {
            const nextId = codingProblems.length + 1;
            codingProblems.push({
                id: nextId,
                title: `Programming Challenge #${nextId}`,
                description: "Implement the required function resolving computational constraints.",
                constraints: "1 <= N <= 10^5",
                sample_input: "5\n1 2 3 4 5",
                sample_output: "15",
                test_cases: [{"input": "5\n1 2 3 4 5", "output": "15", "hidden": false}],
                lang: "python",
                marks: 10
            });
            renderQuestions();
            const lastCard = codingContainer ? codingContainer.lastElementChild : null;
            if (lastCard) lastCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    }

    // 8. Bulk MCQ Parser
    const parseBulkBtn = document.getElementById('parseBulkBtn');
    const bulkPasteInput = document.getElementById('bulkPasteInput');
    if (parseBulkBtn && bulkPasteInput) {
        parseBulkBtn.addEventListener('click', function () {
            const text = bulkPasteInput.value.trim();
            if (!text) {
                alert("Please paste formatted MCQs before clicking Parse & Import.");
                bulkPasteInput.focus();
                return;
            }

            const blocks = text.split(/\n\s*\n|(?=Q\d+[\.:\)])/i);
            let importedCount = 0;

            blocks.forEach(block => {
                const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
                if (lines.length >= 2) {
                    const qLine = lines[0];
                    const qText = qLine.replace(/^(?:Q\d+[\.:\)]\s*|\d+[\.:\)]\s*)/i, '').trim();
                    const opts = [];
                    let correct = 'A';
                    let explanation = '';
                    let marks = 4;

                    lines.slice(1).forEach(l => {
                        const optMatch = l.match(/^([A-D])[\)\.:\-]\s*(.*)$/i);
                        if (optMatch) {
                            opts.push(`${optMatch[1].toUpperCase()}) ${optMatch[2]}`);
                        }
                        const ansMatch = l.match(/^(?:Answer|Ans|Correct)[\s:\-]*([A-D])/i);
                        if (ansMatch) {
                            correct = ansMatch[1].toUpperCase();
                        }
                        const expMatch = l.match(/^(?:Explanation|Exp)[\s:\-]*(.*)$/i);
                        if (expMatch) {
                            explanation = expMatch[1].trim();
                        }
                        const markMatch = l.match(/^(?:Marks|Mark)[\s:\-]*(\d+)/i);
                        if (markMatch) {
                            marks = parseFloat(markMatch[1]) || 4;
                        }
                    });

                    if (qText && opts.length >= 2) {
                        questions.push({
                            id: questions.length + 1,
                            question: qText,
                            options: opts,
                            correct: correct,
                            marks: marks,
                            explanation: explanation
                        });
                        importedCount++;
                    }
                }
            });

            if (importedCount > 0) {
                bulkPasteInput.value = '';
                alert(`Successfully imported ${importedCount} MCQs into your assessment!`);
                switchTab(paneManual, tabBtnManual);
                renderQuestions();
            } else {
                alert("Could not detect standard MCQ format. Please ensure question statements are followed by lines like 'A) ...', 'B) ...' and 'Answer: A'.");
            }
        });
    }

    // 9. TeachMate AI Question Generator
    const runAiGenBtn = document.getElementById('runAiGenBtn');
    if (runAiGenBtn) {
        runAiGenBtn.addEventListener('click', async function () {
            const topicInput = document.getElementById('aiGenTopic');
            const coreTopicInput = document.getElementById('topic');
            const topic = (topicInput && topicInput.value.trim()) || (coreTopicInput && coreTopicInput.value.trim()) || 'Engineering Core Concepts';

            const mcqCountEl = document.getElementById('aiGenMcqCount');
            const codingCountEl = document.getElementById('aiGenCodingCount');
            const diffEl = document.getElementById('difficulty');

            const mcqCount = mcqCountEl ? parseInt(mcqCountEl.value, 10) : 5;
            const codingCount = codingCountEl ? parseInt(codingCountEl.value, 10) : 1;
            const diff = diffEl ? diffEl.value : 'Medium';

            const btnText = document.getElementById('aiGenBtnText');
            const spinner = document.getElementById('aiGenSpinner');

            runAiGenBtn.disabled = true;
            if (btnText) btnText.style.display = 'none';
            if (spinner) spinner.style.display = 'inline';

            try {
                const resp = await fetch('/api/teacher/ai-generate-questions/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        topic: topic,
                        difficulty: diff,
                        mcq_count: mcqCount,
                        coding_count: codingCount,
                        type: 'mixed',
                        language: 'python'
                    })
                });

                if (resp.ok) {
                    const data = await resp.json();
                    let addedMcqs = 0;
                    let addedCoding = 0;

                    if (Array.isArray(data.mcqs) && data.mcqs.length > 0) {
                        data.mcqs.forEach(q => {
                            q.id = questions.length + 1;
                            questions.push(q);
                            addedMcqs++;
                        });
                    }

                    if (Array.isArray(data.coding_problems) && data.coding_problems.length > 0) {
                        data.coding_problems.forEach(c => {
                            c.id = codingProblems.length + 1;
                            codingProblems.push(c);
                            addedCoding++;
                        });
                    }

                    alert(`TeachMate AI successfully generated ${addedMcqs} MCQs and ${addedCoding} coding problems for '${topic}'! You can now review and customize them in the manual builder.`);
                    switchTab(paneManual, tabBtnManual);
                    renderQuestions();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    if (resp.status === 401) {
                        alert("Session expired or authentication required. Please ensure you are logged into your faculty or administrator account.");
                    } else if (resp.status === 403) {
                        alert("Authorization required: Only authorized faculty and administrators can generate curriculum assessments.");
                    } else {
                        alert("AI Question Generator Notice: " + (err.error || `Service returned status ${resp.status}`));
                    }
                }
            } catch (err) {
                alert("Network error while connecting to AI question service: " + err.message);
            } finally {
                runAiGenBtn.disabled = false;
                if (btnText) btnText.style.display = 'inline';
                if (spinner) spinner.style.display = 'none';
            }
        });
    }

    // 10. Form Submissions (Draft, Schedule, Publish)
    form.addEventListener('submit', function (e) {
        syncHiddenInputs();
        if (questions.length === 0 && codingProblems.length === 0) {
            const proceed = confirm("Your assessment does not contain any questions. Would you like EduBridge to auto-generate standard syllabus practice questions?");
            if (!proceed) {
                e.preventDefault();
                return false;
            }
        }
    });

    const btnDraft = document.getElementById('btnSubmitDraft');
    const btnSchedule = document.getElementById('btnSubmitSchedule');
    const btnPublish = document.getElementById('btnSubmitPublish');

    if (btnDraft) {
        btnDraft.addEventListener('click', function () {
            if (actionInput) actionInput.value = 'draft';
            syncHiddenInputs();
            form.submit();
        });
    }

    if (btnSchedule) {
        btnSchedule.addEventListener('click', function () {
            if (actionInput) actionInput.value = 'schedule';
            syncHiddenInputs();
            form.submit();
        });
    }

    if (btnPublish) {
        btnPublish.addEventListener('click', function () {
            if (actionInput) actionInput.value = 'publish';
            syncHiddenInputs();
            form.submit();
        });
    }

    // Initial render
    renderQuestions();
});
