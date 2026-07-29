/**
 * Standalone Local Test UI Workbench Client.
 *
 * Communicates directly with the TEEA Local REST API (`/analyze` and `/health`).
 */

const API_BASE = window.location.origin;

// Sample Tibetan Presets
const PRESETS = {
  sample1: "མངོན་སུམ",
  sample2: "བཀྲ་ཤིས་བདེ་ལེགས། ང་བོད་ཡིག་རྩོམ།",
  sample3: "ཤེས་རབ་ཀྱི་ཕ་རོལ་ཏུ་ཕྱིན་པའི་སྙིང་པོ།"
};

let currentSuggestions = [];

document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("tibetanInput");
  const charCount = document.getElementById("charCount");
  const wordCount = document.getElementById("wordCount");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const presetSelect = document.getElementById("samplePresets");

  // Check health on load
  checkHealth();

  // Update text stats
  textarea.addEventListener("input", () => {
    const text = textarea.value;
    charCount.textContent = text.length;
    wordCount.textContent = text.trim() ? text.trim().split(/\s+/).length : 0;
  });

  // Preset selector
  presetSelect.addEventListener("change", (e) => {
    const key = e.target.value;
    if (PRESETS[key]) {
      textarea.value = PRESETS[key];
      textarea.dispatchEvent(new Event("input"));
    }
  });

  // Analyze button click
  analyzeBtn.addEventListener("click", runAnalysis);
});

async function checkHealth() {
  const statusBadge = document.getElementById("serviceStatus");
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      statusBadge.classList.add("active");
      document.getElementById("metricVocab").textContent = data.vocabulary_size.toLocaleString();
    } else {
      statusBadge.classList.remove("active");
    }
  } catch (err) {
    statusBadge.classList.remove("active");
  }
}

async function runAnalysis() {
  const text = document.getElementById("tibetanInput").value;
  const analyzeBtn = document.getElementById("analyzeBtn");
  const suggestionsList = document.getElementById("suggestionsList");

  if (!text.trim()) {
    alert("Please enter or paste Tibetan text to analyze.");
    return;
  }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing...";

  try {
    const startTime = performance.now();
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });

    const elapsedMs = performance.now() - startTime;
    if (!res.ok) {
      throw new Error(`Service returned HTTP ${res.status}`);
    }

    const data = await res.json();
    currentSuggestions = data.suggestions || [];

    document.getElementById("metricLatency").textContent = `${data.latency_ms || elapsedMs.toFixed(1)} ms`;
    document.getElementById("metricCount").textContent = currentSuggestions.length;
    document.getElementById("suggestionsBadge").textContent = `${currentSuggestions.length} Suggestions`;

    renderSuggestions(currentSuggestions);
  } catch (err) {
    suggestionsList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <p style="color: var(--danger-fg);">Failed to connect to local service: ${err.message}</p>
      </div>
    `;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.innerHTML = '<span class="btn-icon">⚡</span> Analyze Text';
  }
}

function renderSuggestions(suggestions) {
  const suggestionsList = document.getElementById("suggestionsList");

  if (!suggestions || suggestions.length === 0) {
    suggestionsList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✨</div>
        <p>No suggestions found. The document reads clean!</p>
      </div>
    `;
    return;
  }

  suggestionsList.innerHTML = suggestions.map((s, idx) => {
    const origText = getOriginalText(s);
    return `
      <div class="suggestion-item" data-index="${idx}">
        <div class="suggestion-header">
          <span class="rule-source">${s.source}</span>
          <span class="badge tint">${s.priority}</span>
        </div>

        ${(s.context_before || s.context_after) ? `
          <div class="context-snippet">
            ...${s.context_before}<span class="context-target">[${origText}]</span>${s.context_after}...
          </div>
        ` : ''}

        <div class="diff-box">
          <span class="diff-orig">${origText}</span>
          <span class="diff-arrow">→</span>
          <span class="diff-repl">${s.replacement || "(Advisory notice)"}</span>
        </div>

        <div class="suggestion-footer">
          <span class="suggestion-msg">${s.message}</span>
          ${s.replacement ? `
            <button class="apply-btn" onclick="applySuggestion(${idx})">Apply Correction</button>
          ` : ''}
        </div>
      </div>
    `;
  }).join("");
}

function getOriginalText(suggestion) {
  const textarea = document.getElementById("tibetanInput");
  const fullText = textarea.value;
  return fullText.slice(suggestion.span.char_start, suggestion.span.char_end);
}

function applySuggestion(index) {
  const suggestion = currentSuggestions[index];
  if (!suggestion || !suggestion.replacement) return;

  const textarea = document.getElementById("tibetanInput");
  const fullText = textarea.value;
  const start = suggestion.span.char_start;
  const end = suggestion.span.char_end;

  const newText = fullText.slice(0, start) + suggestion.replacement + fullText.slice(end);
  textarea.value = newText;
  textarea.dispatchEvent(new Event("input"));

  // Re-run analysis on updated document
  runAnalysis();
}
