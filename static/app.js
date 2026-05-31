document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('model-select');
    const modeSelect = document.getElementById('mode-select');
    const statusArea = document.getElementById('status-area');
    const chatArea = document.getElementById('chat-area');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const debugOutput = document.getElementById('debug-output');
    const evidenceOutput = document.getElementById('evidence-output');
    const debugPanel = document.querySelector('.debug-panel');
    const debugResizer = document.getElementById('debug-resizer');
    const container = document.querySelector('.container');
    const corpusSidebar = document.getElementById('corpus-sidebar');
    const corpusOverlay = document.getElementById('corpus-overlay');
    const openCorpusBtn = document.getElementById('open-corpus-btn');
    const closeCorpusBtn = document.getElementById('close-corpus-btn');
    const pinCorpusBtn = document.getElementById('pin-corpus-btn');

    const pdfFileInput = document.getElementById('pdf-file-input');
    const browsePdfBtn = document.getElementById('browse-pdf-btn');
    const selectedFilesContainer = document.getElementById('selected-files-container');
    const ingestPdfBtn = document.getElementById('ingest-pdf-btn');
    const ingestStatusArea = document.getElementById('ingest-status-area');
    const batchResultsArea = document.getElementById('batch-results-area');

    const corpusList = document.getElementById('corpus-list');
    const refreshCorpusBtn = document.getElementById('refresh-corpus-btn');
    const selectAllBtn = document.getElementById('select-all-btn');
    const clearSelectionBtn = document.getElementById('clear-selection-btn');
    const removeSelectedBtn = document.getElementById('remove-selected-btn');
    const retrievalScopeText = document.getElementById('retrieval-scope-text');

    const statDocs = document.getElementById('stat-docs');
    const statChunks = document.getElementById('stat-chunks');
    const statSelected = document.getElementById('stat-selected');
    const statLastIngest = document.getElementById('stat-last-ingest');

    const clearConfirmCheck = document.getElementById('clear-confirm-check');
    const clearCorpusBtn = document.getElementById('clear-corpus-btn');

    const groundingDisplay = document.getElementById('grounding-display');

    const chatGroundingInfo = document.getElementById('chat-grounding-info');
    const chatDocName = document.getElementById('chat-doc-name');
    const clearChatDocBtn = document.getElementById('clear-chat-doc-btn');

    const resetSessionBtn = document.getElementById('reset-session-btn');
    const tokenMode = document.getElementById('token-mode');
    const tokenTurnTotal = document.getElementById('token-turn-total');
    const tokenTurnPrompt = document.getElementById('token-turn-prompt');
    const tokenTurnResponse = document.getElementById('token-turn-response');
    const tokenSessionTotal = document.getElementById('token-session-total');
    const tokenSessionTurns = document.getElementById('token-session-turns');

    let allDocuments = [];
    let selectedDocumentIds = new Set();
    let chatDocumentId = null;
    let corpusPinned = false;

    function setCorpusPinned(pinned) {
        corpusPinned = pinned;
        document.body.classList.toggle('corpus-pinned', pinned);
        document.body.classList.toggle('corpus-open', pinned || document.body.classList.contains('corpus-open'));
        if (pinCorpusBtn) {
            pinCorpusBtn.classList.toggle('is-pinned', pinned);
            pinCorpusBtn.textContent = pinned ? 'Unpin' : 'Pin';
        }
    }

    // Tyrone should start with the library visible so document navigation is always ready.
    setCorpusPinned(true);

    function openCorpusSidebar() {
        if (!corpusSidebar) return;
        document.body.classList.add('corpus-open');
    }

    function closeCorpusSidebar() {
        if (!corpusSidebar || corpusPinned) return;
        document.body.classList.remove('corpus-open');
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeRegExp(value) {
        return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function renderInlineMarkdown(text) {
        let html = escapeHtml(text || '');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        return html;
    }

    function parseMarkdownTable(lines, startIndex) {
        if (startIndex + 1 >= lines.length) return null;

        const headerLine = lines[startIndex];
        const separatorLine = lines[startIndex + 1];
        if (!headerLine.includes('|') || !separatorLine.includes('|')) return null;

        const separatorCells = separatorLine.split('|').map(cell => cell.trim()).filter(Boolean);
        const isSeparator = separatorCells.length > 0 && separatorCells.every(cell => /^:?-{3,}:?$/.test(cell));
        if (!isSeparator) return null;

        const extractCells = line => line.split('|').map(cell => cell.trim()).filter((_, idx, arr) => !(idx === 0 && arr[idx] === '') && !(idx === arr.length - 1 && arr[idx] === ''));

        const headers = extractCells(headerLine);
        if (headers.length === 0) return null;

        const rows = [];
        let index = startIndex + 2;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim() !== '') {
            const rowCells = extractCells(lines[index]);
            if (rowCells.length === headers.length) {
                rows.push(rowCells);
                index += 1;
            } else {
                break;
            }
        }

        if (rows.length === 0) return null;

        let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
        headers.forEach(cell => {
            html += `<th>${renderInlineMarkdown(cell)}</th>`;
        });
        html += '</tr></thead><tbody>';
        rows.forEach(row => {
            html += '<tr>';
            row.forEach(cell => {
                html += `<td>${renderInlineMarkdown(cell)}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';

        return { html, nextIndex: index };
    }

    function renderMarkdown(text) {
        const normalized = String(text || '').replace(/\r\n/g, '\n');
        const lines = normalized.split('\n');
        const blocks = [];
        let paragraphLines = [];
        let inUl = false;
        let inOl = false;

        const flushParagraph = () => {
            if (paragraphLines.length > 0) {
                blocks.push(`<p>${paragraphLines.map(renderInlineMarkdown).join('<br>')}</p>`);
                paragraphLines = [];
            }
        };

        const closeLists = () => {
            if (inUl) {
                blocks.push('</ul>');
                inUl = false;
            }
            if (inOl) {
                blocks.push('</ol>');
                inOl = false;
            }
        };

        for (let i = 0; i < lines.length; i += 1) {
            const line = lines[i];
            const trimmed = line.trim();

            if (trimmed === '') {
                flushParagraph();
                closeLists();
                continue;
            }

            const table = parseMarkdownTable(lines, i);
            if (table) {
                flushParagraph();
                closeLists();
                blocks.push(table.html);
                i = table.nextIndex - 1;
                continue;
            }

            const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
            if (headingMatch) {
                flushParagraph();
                closeLists();
                const level = Math.min(6, headingMatch[1].length);
                blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
                continue;
            }

            const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
            if (ulMatch) {
                flushParagraph();
                if (inOl) {
                    blocks.push('</ol>');
                    inOl = false;
                }
                if (!inUl) {
                    blocks.push('<ul>');
                    inUl = true;
                }
                blocks.push(`<li>${renderInlineMarkdown(ulMatch[1])}</li>`);
                continue;
            }

            const olMatch = trimmed.match(/^\d+\.\s+(.*)$/);
            if (olMatch) {
                flushParagraph();
                if (inUl) {
                    blocks.push('</ul>');
                    inUl = false;
                }
                if (!inOl) {
                    blocks.push('<ol>');
                    inOl = true;
                }
                blocks.push(`<li>${renderInlineMarkdown(olMatch[1])}</li>`);
                continue;
            }

            closeLists();
            paragraphLines.push(trimmed);
        }

        flushParagraph();
        closeLists();

        return blocks.join('');
    }

    function buildHighlightTerms(query) {
        if (!query) return [];

        const tokens = query
            .toLowerCase()
            .split(/[^a-z0-9]+/i)
            .map(token => token.trim())
            .filter(token => token.length >= 3);

        const stopWords = new Set([
            'the', 'and', 'for', 'with', 'this', 'that', 'does', 'have',
            'from', 'what', 'when', 'where', 'which', 'into', 'about',
            'your', 'please', 'there', 'they', 'them', 'their', 'would',
            'could', 'should', 'just', 'more', 'than', 'into'
        ]);

        return [...new Set(tokens.filter(token => !stopWords.has(token)))];
    }

    function highlightText(text, query) {
        const escapedText = escapeHtml(text || '');
        const terms = buildHighlightTerms(query);

        if (terms.length === 0) {
            return escapedText;
        }

        const pattern = terms
            .sort((a, b) => b.length - a.length)
            .map(escapeRegExp)
            .join('|');

        return escapedText.replace(
            new RegExp(`\\b(${pattern})\\b`, 'gi'),
            '<mark class="evidence-highlight">$1</mark>'
        );
    }

    async function loadModels() {
        try {
            const response = await fetch('/api/models');
            const data = await response.json();

            modelSelect.innerHTML = '';

            // Fetch grounding for default model
            const gResp = await fetch('/api/grounding');
            const grounding = await gResp.json();
            const defaultModel = (grounding && grounding.selected_model) ? grounding.selected_model : 'granite4:3b';

            if (data.error) {
                statusArea.textContent = data.error;
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No models available';
                modelSelect.appendChild(option);
                sendBtn.disabled = true;
            } else if (data.models && data.models.length > 0) {
                statusArea.textContent = '';
                let defaultFound = false;
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    if (model === defaultModel) {
                        option.selected = true;
                        defaultFound = true;
                    }
                    modelSelect.appendChild(option);
                });

                if (!defaultFound && defaultModel) {
                    const warning = document.createElement('div');
                    warning.style.color = 'red';
                    warning.style.fontSize = '0.8em';
                    warning.style.marginTop = '4px';
                    warning.textContent = `Default model ${defaultModel} not available.`;
                    statusArea.appendChild(warning);
                }

                sendBtn.disabled = false;
            } else {
                statusArea.textContent = 'No local models found. Pull a model via ollama.';
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'Empty';
                modelSelect.appendChild(option);
                sendBtn.disabled = true;
            }
        } catch (error) {
            statusArea.textContent = 'Failed to communicate with backend.';
            sendBtn.disabled = true;
        }
    }

    function appendMessage(role, text, options = {}) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        if (role === 'assistant') {
            msgDiv.innerHTML = renderMarkdown(text);
            if (options.mode === 'document' && options.confidence) {
                const metaDiv = document.createElement('div');
                metaDiv.className = 'message-meta';
                const score = typeof options.confidence.score === 'number'
                    ? ` (${options.confidence.score.toFixed(2)})`
                    : '';
                metaDiv.textContent = `Confidence: ${String(options.confidence.label || 'low').replace(/^./, c => c.toUpperCase())}${score}`;
                msgDiv.appendChild(metaDiv);

                if (options.confidence.coverage_truncated) {
                    const noteDiv = document.createElement('div');
                    noteDiv.className = 'message-note';
                    noteDiv.textContent = 'Answer may be partial; based on retrieved evidence subset.';
                    msgDiv.appendChild(noteDiv);
                }
            }
        } else {
            msgDiv.textContent = text;
        }
        chatArea.appendChild(msgDiv);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function renderEvidence(chunks, query = '') {
        evidenceOutput.innerHTML = '';
        if (!chunks || chunks.length === 0) {
            evidenceOutput.innerHTML = '<div class="empty-evidence-msg">No evidence used.</div>';
            return;
        }

        chunks.forEach(chunk => {
            const chunkDiv = document.createElement('div');
            chunkDiv.className = 'evidence-chunk';

            const header = document.createElement('div');
            header.className = 'evidence-chunk-header';

            const titleSpan = document.createElement('span');
            titleSpan.textContent = `[Doc: ${chunk.document_name} | Chunk ${chunk.chunk_index}]`;

            const expandBtn = document.createElement('button');
            expandBtn.className = 'expand-btn';
            expandBtn.textContent = 'Expand';

            header.appendChild(titleSpan);
            header.appendChild(expandBtn);

            const textDiv = document.createElement('div');
            textDiv.className = 'evidence-chunk-text collapsed';
            textDiv.innerHTML = highlightText(chunk.text || '', query);

            expandBtn.addEventListener('click', () => {
                if (textDiv.classList.contains('collapsed')) {
                    textDiv.classList.remove('collapsed');
                    expandBtn.textContent = 'Collapse';
                } else {
                    textDiv.classList.add('collapsed');
                    expandBtn.textContent = 'Expand';
                }
            });

            chunkDiv.appendChild(header);
            chunkDiv.appendChild(textDiv);
            evidenceOutput.appendChild(chunkDiv);
        });
    }

    function renderGrounding(context) {
        if (!context) {
            groundingDisplay.textContent = 'No grounding context available.';
            return;
        }

        let html = '<div class="grounding-info">';
        html += `<div><strong>datetime:</strong> ${escapeHtml(context.current_datetime)}</div>`;
        html += `<div><strong>timezone:</strong> ${escapeHtml(context.timezone)}</div>`;
        html += `<div><strong>location:</strong> ${escapeHtml(context.location)}</div>`;
        html += `<div><strong>purpose:</strong> ${escapeHtml(context.agent_purpose)}</div>`;
        html += `<div><strong>default mode:</strong> ${escapeHtml(context.default_mode)}</div>`;

        let modelStr = escapeHtml(context.selected_model);
        if (!context.model_available) {
            modelStr += ' <span style="color: red; font-weight: bold;">(Not available)</span>';
        }
        html += `<div><strong>model:</strong> ${modelStr}</div>`;
        html += '</div>';

        groundingDisplay.innerHTML = html;
    }

    async function loadGrounding() {
        try {
            const response = await fetch('/api/grounding');
            const data = await response.json();
            renderGrounding(data);
        } catch (error) {
            groundingDisplay.textContent = 'Failed to load grounding.';
        }
    }

    function updateTokenDisplay(usage) {
        if (!usage) return;
        tokenMode.textContent = usage.mode || 'chat';
        tokenTurnTotal.textContent = usage.turn_total_tokens_est.toLocaleString();
        tokenTurnPrompt.textContent = usage.prompt_tokens_est.toLocaleString();
        tokenTurnResponse.textContent = usage.response_tokens_est.toLocaleString();
        tokenSessionTotal.textContent = usage.session_total_tokens_est.toLocaleString();
        tokenSessionTurns.textContent = usage.session_turn_count.toLocaleString();
    }

    function resetTokenDisplay() {
        tokenTurnTotal.textContent = '0';
        tokenTurnPrompt.textContent = '0';
        tokenTurnResponse.textContent = '0';
        tokenSessionTotal.textContent = '0';
        tokenSessionTurns.textContent = '0';
    }

    function formatChatDebug(payload) {
        if (!payload) return 'No debug payload.';

        let output = '[CHAT REQUEST]\n';
        output += `User message:\n${payload.user_message || 'N/A'}\n\n`;
        output += `Model:\n${payload.selected_model || 'N/A'}\n`;
        output += `Mode:\n${payload.mode || 'chat'}\n\n`;

        if (payload.mode === 'personal') {
            output += '[PERSONAL MODE]\n';
            output += `Input persisted: ${payload.personal_input_persisted ? 'yes' : 'no'}\n`;
            output += `Retrieved records: ${payload.personal_records_retrieved_count || 0}\n`;
            output += `General knowledge fallback: ${payload.personal_general_knowledge_fallback || 'disabled'}\n`;
            output += `Status: ${payload.personal_status || 'N/A'}\n`;

            const pc = payload.personal_context || {};
            const entities = pc.resolved_entities || [];
            output += `Resolved entities count: ${entities.length}\n`;
            entities.forEach(ent => {
                output += `- ${ent.canonical_name} (${ent.entity_type})\n`;
            });

            const memories = pc.memories || [];
            output += `Personal records retrieved: ${memories.length}\n`;
            memories.forEach((mem, i) => {
                output += `[${i+1}] ${mem.raw_user_input.substring(0, 100)}${mem.raw_user_input.length > 100 ? '...' : ''}\n`;
            });
            output += '\n';
        }

        output += '[RAG]\n';
        output += `RAG enabled:\n${payload.rag_enabled ? 'true' : 'false'}\n`;
        output += `Scope: ${payload.retrieval_scope || 'full_corpus'}\n`;
        output += `Selected docs count: ${payload.selected_documents_count || 0}\n`;
        if (payload.selected_documents_names && payload.selected_documents_names.length > 0) {
            output += `Selected docs: ${payload.selected_documents_names.join(', ')}\n`;
        }
        output += '\n';

        if (payload.rag_enabled && payload.mode === 'document') {
            output += `Retrieval query:\n${payload.retrieval_query || 'N/A'}\n\n`;
            output += '[RESPONSE FORMAT]\n';
            output += `Detected: ${payload.response_format_detected || 'default'}\n`;
            output += `Rules applied: ${payload.response_format_rules_applied ? 'true' : 'false'}\n`;
            output += `Reason: ${payload.response_format_reason || 'N/A'}\n\n`;
            output += '[COVERAGE]\n';
            output += `Mode: ${payload.coverage_mode || 'narrow_lookup'}\n`;
            output += `Coverage required: ${payload.coverage_required ? 'true' : 'false'}\n`;
            output += `Top-k requested: ${payload.retrieval_top_k_requested ?? 'N/A'}\n`;
            output += `Verified chunks: ${payload.retrieval_verified_chunks_count ?? 'N/A'}\n`;
            output += `Chunks used for prompt: ${payload.retrieval_chunks_used_for_prompt ?? 'N/A'}\n`;
            output += `Coverage truncated: ${payload.coverage_truncated ? 'true' : 'false'}\n`;
            output += `Coverage reason: ${payload.coverage_reason || 'N/A'}\n`;
            if (payload.confidence_reason_codes && payload.confidence_reason_codes.length > 0) {
                output += `Confidence reasons: ${payload.confidence_reason_codes.join(', ')}\n`;
            }
            output += '\n';

            if (payload.retrieval_metrics) {
                const metrics = payload.retrieval_metrics;
                output += '[RETRIEVAL METRICS]\n';
                output += `Eligible docs: ${metrics.eligible_docs}\n`;
                output += `Total candidate chunks: ${metrics.candidate_count}\n`;
                output += `Pool size for reranking: ${metrics.pool_size}\n\n`;
            }

            const chunks = payload.retrieval_chunks || [];
            output += `Retrieved chunks count:\n${chunks.length}\n\n`;
            output += 'Retrieved chunks (ranked):\n';

            if (chunks.length === 0) {
                output += '0 results\n';
            } else {
                chunks.forEach((chunk, index) => {
                    const text = chunk.text || '';
                    const truncatedChunk = text.length > 500 ? `${text.substring(0, 500)}...` : text;
                    output += `\n[${index + 1}] score=${chunk.score.toFixed(4)} | v=${chunk.vector_score.toFixed(4)} | l=${chunk.lexical_score.toFixed(4)}\n`;
                    output += `Doc: ${chunk.document_name} (index: ${chunk.chunk_index})\n`;
                    output += `Text length: ${text.length}\n`;
                    output += `${truncatedChunk}\n`;
                });
            }
            output += '\n';
        }

        output += '[WATCHER]\n';
        if (payload.watcher_enabled === false) {
            output += 'enabled: false\nstatus: skipped\n\n';
        } else {
            output += 'enabled: true\n';
            output += `allowed: ${payload.watcher_allowed !== undefined ? payload.watcher_allowed : 'N/A'}\n`;
            output += `modified: ${payload.watcher_modified !== undefined ? payload.watcher_modified : 'N/A'}\n`;

            const notes = payload.watcher_notes || [];
            if (notes.length > 0) {
                output += 'notes:\n';
                notes.forEach(note => {
                    output += `- ${note}\n`;
                });
            } else {
                output += 'notes: none\n';
            }
            output += `error: ${payload.watcher_error || 'none'}\n\n`;

            const ruleResults = payload.watcher_rule_results || [];
            if (ruleResults.length > 0) {
                const summary = { error: 0, warning: 0, info: 0 };
                output += '[WATCHER RULES]\n';

                ruleResults.forEach(result => {
                    if (!result.passed) {
                        summary[result.severity]++;
                    }
                });

                output += 'Summary:\n';
                output += `  errors: ${summary.error}\n`;
                output += `  warnings: ${summary.warning}\n`;
                output += `  info: ${summary.info}\n\n`;

                ruleResults.forEach(result => {
                    output += `${result.rule_id}: ${result.passed ? 'passed' : 'FAILED'}\n`;
                    output += `  severity: ${result.severity}\n`;
                    output += `  passed: ${result.passed}\n`;
                    if (!result.passed && result.details) {
                        output += `  details: ${result.details}\n`;
                    }
                    output += '\n';
                });
            }
        }

        let promptToDisplay = payload.final_prompt || 'N/A';
        if (promptToDisplay.length > 8000) {
            promptToDisplay = `${promptToDisplay.substring(0, 8000)}\n\n[...prompt truncated for display...]`;
        }

        output += `[FINAL PROMPT]\nFinal prompt sent to model:\n${promptToDisplay}\n\n`;
        output += `[MODEL RESPONSE PREVIEW]\nModel response preview:\n${payload.response_preview || 'N/A'}\n\n`;
        output += '[ERRORS]\nErrors:\n';
        output += `retrieval: ${payload.retrieval_error || 'none'}\n`;
        output += `ollama: ${payload.ollama_error || 'none'}\n`;

        return output;
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        const model = modelSelect.value;
        const mode = modeSelect.value;

        if (!message) return;
        if (!model) {
            statusArea.textContent = 'Please select a model.';
            return;
        }

        statusArea.textContent = '';
        appendMessage('user', message);
        messageInput.value = '';

        sendBtn.disabled = true;
        messageInput.disabled = true;

        try {
            const requestBody = {
                model,
                message,
                mode,
                document_ids: selectedDocumentIds.size > 0 ? Array.from(selectedDocumentIds) : null,
                chat_document_id: (mode === 'chat' && chatDocumentId) ? chatDocumentId : null
            };

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();

            if (data.debug && data.debug.error) {
                appendMessage('assistant', `System Error: ${data.debug.error}`);
            } else if (data.reply) {
                appendMessage('assistant', data.reply, { mode, confidence: data.confidence });
            } else {
                appendMessage('assistant', 'Empty response.');
            }

            renderEvidence(data.evidence, message);
            debugOutput.textContent = formatChatDebug(data.debug);
            updateTokenDisplay(data.token_usage);
        } catch (error) {
            statusArea.textContent = `Error sending request: ${error.message}`;
        } finally {
            sendBtn.disabled = false;
            messageInput.disabled = false;
            messageInput.focus();
        }
    }

    async function callRpaEndpoint(endpoint, body) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ mode: 'personal', ...body })
        });
        return response.json();
    }

    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', event => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    browsePdfBtn.addEventListener('click', () => {
        pdfFileInput.click();
    });

    pdfFileInput.addEventListener('change', () => {
        if (pdfFileInput.files && pdfFileInput.files.length > 0) {
            const files = Array.from(pdfFileInput.files);
            const count = files.length;

            selectedFilesContainer.innerHTML = '';
            const title = document.createElement('div');
            title.textContent = `Selected files (${count}):`;
            title.style.fontWeight = 'bold';
            selectedFilesContainer.appendChild(title);

            const list = document.createElement('ul');
            list.style.margin = '5px 0';
            list.style.paddingLeft = '20px';
            list.style.fontSize = '0.9em';

            const displayLimit = 5;
            files.slice(0, displayLimit).forEach(file => {
                const li = document.createElement('li');
                li.textContent = file.name;
                list.appendChild(li);
            });

            if (count > displayLimit) {
                const li = document.createElement('li');
                li.textContent = `... and ${count - displayLimit} more`;
                list.appendChild(li);
            }

            selectedFilesContainer.appendChild(list);
            ingestPdfBtn.disabled = false;
        } else {
            selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No files selected.</span>';
            ingestPdfBtn.disabled = true;
        }
    });

    function updateScopeStatus() {
        if (selectedDocumentIds.size === 0) {
            retrievalScopeText.textContent = 'Full corpus';
            removeSelectedBtn.disabled = true;
        } else {
            retrievalScopeText.textContent = `Working set (${selectedDocumentIds.size} documents)`;
            removeSelectedBtn.disabled = false;
            openCorpusSidebar();

        }
        statSelected.textContent = selectedDocumentIds.size;
    }

    function updateChatGroundingDisplay() {
        if (chatDocumentId) {
            const doc = allDocuments.find(d => d.document_id === chatDocumentId);
            if (doc) {
                chatDocName.textContent = doc.document_name;
                chatGroundingInfo.style.display = 'flex';
            } else {
                chatDocumentId = null;
                chatGroundingInfo.style.display = 'none';
            }
        } else {
            chatGroundingInfo.style.display = 'none';
        }
    }

    function toggleDocumentSelection(docId) {
        const mode = modeSelect.value;

        if (mode === 'chat') {
            if (chatDocumentId === docId) {
                chatDocumentId = null;
            } else {
                chatDocumentId = docId;
            }
            updateChatGroundingDisplay();
            renderDocumentCards();
        } else {
            if (selectedDocumentIds.has(docId)) {
                selectedDocumentIds.delete(docId);
            } else {
                selectedDocumentIds.add(docId);
            }
            renderDocumentCards();
            updateScopeStatus();
        }
    }

    clearChatDocBtn.addEventListener('click', () => {
        chatDocumentId = null;
        updateChatGroundingDisplay();
        renderDocumentCards();
    });

    modeSelect.addEventListener('change', () => {
        if (modeSelect.value === 'chat') {
            updateChatGroundingDisplay();
        } else {
            chatGroundingInfo.style.display = 'none';
        }
        renderDocumentCards();
        updatePersonalToolsVisibility();
    });

    function createBadge(text, bg, color) {
        const badge = document.createElement('span');
        badge.textContent = text;
        badge.style.fontSize = '0.72rem';
        badge.style.backgroundColor = bg;
        badge.style.padding = '2px 6px';
        badge.style.borderRadius = '999px';
        badge.style.color = color;
        badge.style.fontWeight = '600';
        return badge;
    }

    function renderDocumentCards() {
        corpusList.innerHTML = '';
        if (allDocuments.length === 0) {
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-corpus-msg';
            emptyMsg.textContent = 'No indexed documents.';
            corpusList.appendChild(emptyMsg);
            return;
        }

        const mode = modeSelect.value;

        allDocuments.forEach(doc => {
            const card = document.createElement('div');
            const isSelected = (mode === 'chat')
                ? (chatDocumentId === doc.document_id)
                : selectedDocumentIds.has(doc.document_id);

            card.className = `doc-card ${isSelected ? 'selected' : ''}`;

            const name = document.createElement('div');
            name.className = 'doc-name';
            name.append(document.createTextNode(doc.document_name));
            name.appendChild(createBadge((doc.file_type || 'pdf').toUpperCase(), '#e3f2fd', '#1976d2'));
            if (doc.ocr_used) {
                name.appendChild(createBadge('OCR', '#eef0f3', '#5b6572'));
            }

            const meta = document.createElement('div');
            meta.className = 'doc-meta';
            const date = new Date(doc.ingested_at).toLocaleString();
            const sizeKB = (doc.file_size_bytes / 1024).toFixed(1);
            const ocrMeta = doc.ocr_used ? ` | OCR: ${doc.ocr_char_count} chars, ${doc.ocr_page_count} pages` : '';
            meta.innerHTML = `
                <span style="font-family: monospace; font-size: 0.7rem; color: #8a94a3;">ID: ${escapeHtml(doc.document_id)}</span><br>
                Path: ${escapeHtml(doc.source_path || 'N/A')}<br>
                Ingested: ${escapeHtml(date)}<br>
                Chunks: ${doc.chunk_count} | Size: ${sizeKB} KB${escapeHtml(ocrMeta)}
            `;

            card.appendChild(name);
            card.appendChild(meta);
            card.addEventListener('click', () => toggleDocumentSelection(doc.document_id));
            corpusList.appendChild(card);
        });
    }

    async function loadStats() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();
            if (data.ok) {
                statDocs.textContent = data.stats.total_documents;
                statChunks.textContent = data.stats.total_chunks;
                statLastIngest.textContent = data.stats.last_ingestion_at
                    ? new Date(data.stats.last_ingestion_at).toLocaleString()
                    : 'N/A';
            }
        } catch (error) {
            console.error('Failed to load stats', error);
        }
    }

    async function loadIndexedDocs() {
        try {
            const response = await fetch('/api/docs');
            if (response.ok) {
                const data = await response.json();
                if (data.ok) {
                    allDocuments = data.documents || [];
                    const validIds = new Set(allDocuments.map(doc => doc.document_id));
                    selectedDocumentIds = new Set(
                        Array.from(selectedDocumentIds).filter(id => validIds.has(id))
                    );
                    renderDocumentCards();
                    updateScopeStatus();
                    loadStats();
                }
            }
        } catch (error) {
            console.error('Failed to load indexed docs', error);
        }
    }

    refreshCorpusBtn.addEventListener('click', () => {
        openCorpusSidebar();
        loadIndexedDocs();
    });

    selectAllBtn.addEventListener('click', () => {
        openCorpusSidebar();
        allDocuments.forEach(doc => selectedDocumentIds.add(doc.document_id));
        renderDocumentCards();
        updateScopeStatus();
    });

    clearSelectionBtn.addEventListener('click', () => {
        selectedDocumentIds.clear();
        renderDocumentCards();
        updateScopeStatus();
    });

    removeSelectedBtn.addEventListener('click', async () => {
        if (selectedDocumentIds.size === 0) return;

        const count = selectedDocumentIds.size;
        const confirmMsg = count === 1
            ? 'Are you sure you want to remove the selected document?'
            : `Are you sure you want to remove the ${count} selected documents?`;

        if (!confirm(confirmMsg)) return;

        removeSelectedBtn.disabled = true;
        const idsToRemove = Array.from(selectedDocumentIds);

        for (const docId of idsToRemove) {
            try {
                const response = await fetch(`/api/docs/${docId}`, { method: 'DELETE' });
                const result = await response.json();
                if (result.ok) {
                    selectedDocumentIds.delete(docId);
                } else {
                    console.error(`Failed to delete doc ${docId}: ${result.error}`);
                }
            } catch (error) {
                console.error(`Error deleting doc ${docId}`, error);
            }
        }

        await loadIndexedDocs();
    });

    clearConfirmCheck.addEventListener('change', () => {
        clearCorpusBtn.disabled = !clearConfirmCheck.checked;
    });

    clearCorpusBtn.addEventListener('click', async () => {
        if (!clearConfirmCheck.checked) return;
        if (!confirm('PERMANENTLY CLEAR ENTIRE CORPUS? This cannot be undone.')) return;

        clearCorpusBtn.disabled = true;
        try {
            const response = await fetch('/api/docs/clear', { method: 'POST' });
            const result = await response.json();
            if (result.ok) {
                selectedDocumentIds.clear();
                clearConfirmCheck.checked = false;
                clearCorpusBtn.disabled = true;
                await loadIndexedDocs();
            } else {
                alert(`Failed to clear corpus: ${result.error}`);
                clearCorpusBtn.disabled = false;
            }
        } catch (error) {
            console.error('Error clearing corpus', error);
            clearCorpusBtn.disabled = false;
        }
    });

    if (openCorpusBtn) {
        openCorpusBtn.addEventListener('click', openCorpusSidebar);
    }

    if (closeCorpusBtn) {
        closeCorpusBtn.addEventListener('click', closeCorpusSidebar);
    }

    if (corpusOverlay) {
        corpusOverlay.addEventListener('click', closeCorpusSidebar);
    }

    if (pinCorpusBtn) {
        pinCorpusBtn.addEventListener('click', () => {
            setCorpusPinned(!corpusPinned);
            if (!corpusPinned) {
                document.body.classList.remove('corpus-open');
            } else {
                document.body.classList.add('corpus-open');
            }
        });
    }

    resetSessionBtn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to reset the current session? This will clear session token counters and reset the session ID.')) return;

        try {
            const response = await fetch('/api/session/reset', { method: 'POST' });
            if (response.ok) {
                chatArea.innerHTML = '';
                evidenceOutput.innerHTML = '<div class="empty-evidence-msg">No evidence yet.</div>';
                debugOutput.textContent = 'Session reset.';
                resetTokenDisplay();
                await loadGrounding();
            }
        } catch (error) {
            console.error('Failed to reset session', error);
        }
    });

    ingestPdfBtn.addEventListener('click', async () => {
        if (!pdfFileInput.files || pdfFileInput.files.length === 0) {
            ingestStatusArea.textContent = 'No files selected.';
            return;
        }

        const files = Array.from(pdfFileInput.files);
        const total = files.length;

        ingestStatusArea.textContent = `Batch processing: 0/${total}...`;
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = true;
        batchResultsArea.innerHTML = '<h3>Batch ingestion results:</h3>';
        batchResultsArea.style.display = 'block';

        let batchDebugStr = `\n[INGEST BATCH]\nfiles_selected: ${total}\n`;

        for (let index = 0; index < total; index++) {
            const file = files[index];
            ingestStatusArea.textContent = `Batch processing: ${index + 1}/${total} (${file.name})...`;

            const formData = new FormData();
            formData.append('file', file);

            let result;
            try {
                const response = await fetch('/api/ingest', {
                    method: 'POST',
                    body: formData
                });
                result = await response.json();
            } catch (error) {
                result = {
                    ok: false,
                    path: file.name,
                    document_name: file.name,
                    status: 'failed',
                    error: 'Failed to communicate with server.'
                };
            }

            const resultItem = document.createElement('div');
            resultItem.style.marginBottom = '6px';

            const statusIcon = document.createElement('span');
            let statusText = '';

            if (result.status === 'success') {
                statusIcon.textContent = '✓ ';
                statusIcon.style.color = 'green';
                const ocrInfo = result.ocr_used
                    ? ` (OCR used: ${result.ocr_char_count} chars, ${result.ocr_page_count} pages)`
                    : '';
                statusText = `${result.document_name} - ${result.chunks_indexed} chunks${ocrInfo}`;
            } else if (result.status === 'skipped') {
                statusIcon.textContent = 'i ';
                statusIcon.style.color = 'orange';
                statusText = `${result.document_name} - Skipped (duplicate)`;
            } else {
                statusIcon.textContent = 'x ';
                statusIcon.style.color = 'red';
                statusText = `${result.document_name} - Failed: ${result.error || 'Unknown error'}`;
            }

            resultItem.appendChild(statusIcon);
            resultItem.appendChild(document.createTextNode(statusText));
            batchResultsArea.appendChild(resultItem);

            batchDebugStr += `\n[${index + 1}] ${file.name}\nstatus: ${result.status}\n`;
            if (result.status === 'success' || result.status === 'skipped') {
                batchDebugStr += `chunks: ${result.chunks_indexed}\n`;
                if (result.status === 'success') {
                    batchDebugStr += `ingestion_method: ${result.ingestion_method}\n`;
                    if (result.ocr_used) {
                        batchDebugStr += `ocr_char_count: ${result.ocr_char_count}\n`;
                        batchDebugStr += `ocr_page_count: ${result.ocr_page_count}\n`;
                    }
                }
                if (result.status === 'skipped') {
                    batchDebugStr += 'reason: duplicate\n';
                }
            } else {
                batchDebugStr += `error: ${result.error || 'unknown'}\n`;
            }
        }

        debugOutput.textContent = batchDebugStr + '\n' + debugOutput.textContent;
        ingestStatusArea.textContent = 'Batch ingestion complete.';

        openCorpusSidebar();
        await loadIndexedDocs();

        pdfFileInput.value = '';
        selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No files selected.</span>';
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = false;
    });

    if (debugResizer && debugPanel && container) {
        let resizing = false;

        const stopResize = () => {
            resizing = false;
            debugResizer.classList.remove('dragging');
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
        };

        debugResizer.addEventListener('mousedown', () => {
            resizing = true;
            debugResizer.classList.add('dragging');
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
        });

        window.addEventListener('mousemove', event => {
            if (!resizing || window.innerWidth <= 1120) return;

            const bounds = container.getBoundingClientRect();
            const minWidth = 320;
            const maxWidth = Math.min(900, bounds.width - 420);
            const desiredWidth = bounds.right - event.clientX;
            const clampedWidth = Math.max(minWidth, Math.min(maxWidth, desiredWidth));

            debugPanel.style.width = `${clampedWidth}px`;
            debugPanel.style.flexBasis = `${clampedWidth}px`;
        });

        window.addEventListener('mouseup', stopResize);
        window.addEventListener('mouseleave', stopResize);
    }

    loadGrounding();
    loadModels();
    loadIndexedDocs();
    updatePersonalToolsVisibility();
});
