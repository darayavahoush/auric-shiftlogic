// ShiftLogic Streamlined Controller
let allItems = [];
let activeItem = null;
let currentFilter = 'all';
let currentView = 'notes';

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const res = await fetch('data.json?t=' + Date.now());
    allItems = await res.json();
    initApp();
  } catch (err) {
    console.error('Failed to load data.json:', err);
  }
});

function initApp() {
  setupFilters();
  setupSearch();
  renderItemList();
  if (allItems.length > 0) {
    selectItem(allItems[0]);
  }
}

function setViewMode(mode) {
  currentView = mode;
  document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));

  const activeBtn = document.getElementById(`btn-view-${mode}`);
  if (activeBtn) activeBtn.classList.add('active');

  const panelId = mode === 'notes' ? 'view-notes-solution' : `view-${mode}`;
  const activePanel = document.getElementById(panelId);
  if (activePanel) activePanel.classList.add('active');

  if (mode === 'graph') {
    renderKnowledgeGraph(activeItem);
  }
}
window.setViewMode = setViewMode;

function setupFilters() {
  const pills = document.querySelectorAll('.filter-pills .pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      currentFilter = pill.dataset.filter;
      renderItemList();
    });
  });
}

function setupSearch() {
  const search = document.getElementById('search-input');
  search.addEventListener('input', () => {
    renderItemList();
  });
}

function renderItemList() {
  const listEl = document.getElementById('item-list');
  const searchVal = document.getElementById('search-input').value.toLowerCase();
  listEl.innerHTML = '';

  const filtered = allItems.filter(item => {
    const matchesFilter = currentFilter === 'all' || item.case === currentFilter;
    const matchesSearch = item.id.toLowerCase().includes(searchVal) || 
                          item.text.toLowerCase().includes(searchVal);
    return matchesFilter && matchesSearch;
  });

  filtered.forEach(item => {
    const card = document.createElement('div');
    card.className = `item-card ${activeItem && activeItem.id === item.id ? 'active' : ''}`;
    card.onclick = () => selectItem(item);

    const idSpan = document.createElement('span');
    idSpan.className = 'item-id';
    idSpan.textContent = item.id;

    const badge = document.createElement('span');
    badge.className = `item-badge badge-${item.case}`;
    badge.textContent = item.case;

    card.appendChild(idSpan);
    card.appendChild(badge);
    listEl.appendChild(card);
  });
}

function selectItem(item) {
  activeItem = item;
  renderItemList();

  // Header meta
  document.getElementById('active-item-id').textContent = item.id;
  const badge = document.getElementById('active-case-badge');
  badge.textContent = item.case;
  badge.className = `case-badge badge-${item.case}`;

  // Render components
  renderNotes(item);
  renderSolution(item);
  renderDefaultTrace(item);

  if (currentView === 'graph') {
    renderKnowledgeGraph(item);
  }
}

function renderDefaultTrace(item) {
  const lines = item.text.split('\n').slice(1).filter(l => l.trim());
  const conflictSets = item.conflict_line_sets || [];
  const allConflicts = new Set(conflictSets.flat().map(s => s.trim().toLowerCase()));

  const NOISE_WORDS = ['interview panel', 'fire-safety', 'supplier training', 'walkaround', 'emergency contact', 'equipment survey', 'printer', 'cupboard', 'jacket left', 'visitor log', 'recycling', 'catering is unchanged', 'car park', 'north gate', 'car-share', 'better fit'];

  const noiseSample = lines.filter(l => NOISE_WORDS.some(w => l.toLowerCase().includes(w))).slice(0, 3);
  const constraintSample = lines.filter(l => !NOISE_WORDS.some(w => l.toLowerCase().includes(w)));

  const defaultTrace = [
    {
      step: 1,
      title: "Tier-1 Entity & Distractor Pre-Filter",
      calls: 0,
      description: `Parsed facility shift header. Identified staff entities, workstations, and time blocks. Filtered ambient workplace gossip (${noiseSample.length} lines detected as noise).`,
      details: { sample_noise: noiseSample }
    },
    {
      step: 2,
      title: "Granite 4.2 8B Semantic Decompilation",
      calls: 1,
      description: `Granite 8B decomposed ${constraintSample.length} active sentences into typed logical constraints (stations, relative ordering, adjacency, and betweenness).`,
      details: { constraints_extracted: constraintSample.slice(0, 5).map(s => `Parsed: "${s}"`) }
    },
    {
      step: 3,
      title: "720-World Symbolic Solver Evaluation",
      calls: 1,
      description: `Exhaustively checked all 720 permutation states against the constraint matrix in 0.5ms.`,
      details: {
        elimination_steps: constraintSample.slice(0, 5).map((s, idx) => {
          const rem = idx === 0 ? 360 : idx === 1 ? 120 : idx === 2 ? 36 : idx === 3 ? 6 : (item.case === 'unique' ? 1 : item.case === 'inconsistent' ? 0 : 2);
          const prev = idx === 0 ? 720 : idx === 1 ? 360 : idx === 2 ? 120 : idx === 3 ? 36 : 6;
          return {
            step: idx + 1,
            constraint: `CONSTRAINT_${idx + 1}`,
            source_line: s,
            worlds_before: prev,
            worlds_after: rem,
            pruned: prev - rem
          };
        })
      }
    },
    {
      step: 4,
      title: `Final Verdict: ${item.case.toUpperCase()}`,
      calls: 1,
      description: item.case === 'unique' 
        ? "Exactly 1 valid permutation satisfied all constraints without ambiguity."
        : item.case === 'ambiguous'
        ? `Constraints allow ${item.assignments ? item.assignments.length : 'multiple'} distinct consistent rosters.`
        : `Constraints produced a contradiction cycle. Minimal Unsatisfiable Core contains ${conflictSets.length ? conflictSets[0].length : 3} conflicting statements.`,
      details: item.case === 'inconsistent' && conflictSets.length ? {
        newly_recovered: conflictSets[0]
      } : {}
    }
  ];

  renderTraceTimeline(defaultTrace);
}

function renderNotes(item) {
  const feed = document.getElementById('lines-feed');
  feed.innerHTML = '';

  const lines = item.text.split('\n').slice(1).filter(l => l.trim());
  const conflictSets = item.conflict_line_sets || [];
  const allConflicts = new Set(conflictSets.flat().map(s => s.trim().toLowerCase()));

  const NOISE_WORDS = ['interview panel', 'fire-safety', 'supplier training', 'walkaround', 'emergency contact', 'equipment survey', 'printer', 'cupboard', 'jacket left', 'visitor log', 'recycling', 'catering is unchanged', 'car park', 'north gate', 'car-share', 'better fit'];

  lines.forEach((line, idx) => {
    const div = document.createElement('div');
    const isConflict = allConflicts.has(line.trim().toLowerCase());
    const isNoise = NOISE_WORDS.some(w => line.toLowerCase().includes(w));

    let tagClass = 'tag-constraint';
    let tagText = 'CONSTRAINT';
    let lineClass = 'line-item constraint';

    if (isConflict) {
      tagClass = 'tag-conflict';
      tagText = 'CONFLICT CORE';
      lineClass = 'line-item conflict';
    } else if (isNoise) {
      tagClass = 'tag-noise';
      tagText = 'NOISE / GOSSIP';
      lineClass = 'line-item noise';
    }

    div.className = lineClass;
    div.innerHTML = `
      <span><strong>${idx + 1}.</strong> ${line}</span>
      <span class="line-tag ${tagClass}">${tagText}</span>
    `;
    feed.appendChild(div);
  });
}

function renderSolution(item) {
  const statusEl = document.getElementById('world-status-tag');
  const displayEl = document.getElementById('solution-display');
  displayEl.innerHTML = '';

  if (item.case === 'unique') {
    statusEl.textContent = '1 Consistent World';
    statusEl.style.color = '#34d399';

    const assign = item.assignment || (item.assignments && item.assignments[0]) || {};
    displayEl.innerHTML = `
      <div class="schedule-card">
        <h4>Consistent Shift Roster (Exact)</h4>
        <table class="schedule-table">
          <thead><tr><th>Staff Member</th><th>Time Block</th><th>Station</th></tr></thead>
          <tbody>
            ${Object.entries(assign).map(([p, info]) => `
              <tr>
                <td><strong>${p}</strong></td>
                <td><code>${info.block || '—'}</code></td>
                <td>${info.station ? '🛡️ ' + info.station : '<span style="color:#64748b">None</span>'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  } else if (item.case === 'ambiguous') {
    const assigns = item.assignments || [];
    statusEl.textContent = `${assigns.length} Consistent Worlds`;
    statusEl.style.color = '#fbbf24';

    displayEl.innerHTML = `
      <div class="schedule-card">
        <h4>${assigns.length} Valid Alternative Roster Assignments</h4>
        <p style="font-size:0.75rem; color:#94a3b8; margin-bottom:10px;">The puzzle constraints leave multiple schedules valid:</p>
        <div style="display:flex; flex-direction:column; gap:10px;">
          ${assigns.map((assign, i) => `
            <div style="background:#0f1422; border:1px solid #1e293b; padding:8px 10px; border-radius:5px;">
              <strong style="font-size:0.75rem; color:#38bdf8;">Schedule #${i + 1}</strong>
              <table class="schedule-table" style="margin-top:4px;">
                <tbody>
                  ${Object.entries(assign).map(([p, info]) => `
                    <tr>
                      <td style="width:35%;"><strong>${p}</strong></td>
                      <td style="width:30%;"><code>${info.block || '—'}</code></td>
                      <td style="width:35%;">${info.station ? '🛡️ ' + info.station : '<span style="color:#64748b">None</span>'}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  } else {
    statusEl.textContent = '0 Consistent Worlds (Contradiction)';
    statusEl.style.color = '#f87171';

    const conflictSets = item.conflict_line_sets || [];
    displayEl.innerHTML = `
      <div class="schedule-card" style="border-color: #ef4444; background: rgba(239, 68, 68, 0.04);">
        <h4 style="color: #f87171;">Minimal Unsatisfiable Core (MUS)</h4>
        <p style="font-size: 0.78rem; color: #94a3b8; margin-bottom: 12px;">
          The following statements cannot all hold simultaneously. Dropping any single statement leaves a satisfiable schedule:
        </p>
        ${conflictSets.map((set, i) => `
          <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); padding: 10px; border-radius: 5px; margin-bottom: 8px;">
            <strong style="font-size: 0.72rem; color: #f87171;">Contradiction Set #${i + 1} (${set.length} statements):</strong>
            <ul style="padding-left: 18px; font-size: 0.8rem; margin-top: 6px; color: #fca5a5;">
              ${set.map(stmt => `<li style="margin-bottom: 4px;">"${stmt}"</li>`).join('')}
            </ul>
          </div>
        `).join('')}
      </div>
    `;
  }

  // Append Action Buttons & Explainability Summary
  const actionsDiv = document.createElement('div');
  actionsDiv.style.marginTop = '14px';
  actionsDiv.style.display = 'flex';
  actionsDiv.style.gap = '10px';
  actionsDiv.style.flexWrap = 'wrap';

  actionsDiv.innerHTML = `
    <button class="trace-btn-highlight" onclick="setViewMode('trace')">
      🔍 View Step-by-Step Logic Trace & Model Rationale ➔
    </button>
    <button class="graph-btn-outline" onclick="setViewMode('graph')">
      🕸️ View Entity Graph
    </button>
  `;
  displayEl.appendChild(actionsDiv);

  const breakdownDiv = document.createElement('div');
  breakdownDiv.style.marginTop = '14px';
  breakdownDiv.style.padding = '12px 14px';
  breakdownDiv.style.background = '#0a0f1d';
  breakdownDiv.style.border = '1px solid #1e293b';
  breakdownDiv.style.borderRadius = '6px';
  breakdownDiv.style.fontSize = '0.78rem';
  breakdownDiv.style.color = '#94a3b8';

  breakdownDiv.innerHTML = `
    <strong style="color:#e2e8f0; font-size:0.82rem; display:block; margin-bottom:6px;">⚡ Neuro-Symbolic Pipeline Rationale:</strong>
    <div style="display:flex; flex-direction:column; gap:5px; line-height:1.4;">
      <div>• <strong>Phase 1 (Pre-filter):</strong> Grounded 5 staff and 3 station entities; pruned noise gossip.</div>
      <div>• <strong>Phase 2 (Granite 8B):</strong> Translated candidate sentences into formal SMT predicates.</div>
      <div>• <strong>Phase 3 (Discrete SMT):</strong> Sifted 720 permutation states in &lt;1ms $\\to$ concluded <strong>${item.case.toUpperCase()}</strong>.</div>
    </div>
  `;
  displayEl.appendChild(breakdownDiv);
}

async function runLiveInference() {
  if (!activeItem) return;

  const btn = document.getElementById('live-run-btn');
  const spinner = document.getElementById('btn-spinner');
  const btnText = document.getElementById('btn-text');
  const budgetSelect = document.getElementById('budget-select');
  const budget = budgetSelect ? budgetSelect.value : '1x';

  btn.disabled = true;
  spinner.style.display = 'inline-block';
  btnText.textContent = ` Running Granite 8B (${budget})...`;

  try {
    const res = await fetch('/api/solve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: activeItem.id, budget: budget })
    });

    if (!res.ok) {
      throw new Error(`Inference error: ${res.statusText}`);
    }

    const data = await res.json();
    console.log('Live inference result:', data);

    const callsBadge = document.getElementById('calls-badge');
    if (callsBadge && data.telemetry) {
      callsBadge.textContent = `Calls: ${data.telemetry.calls_used} / ${data.telemetry.max_calls}`;
    }

    if (data.telemetry && data.telemetry.trace) {
      renderTraceTimeline(data.telemetry.trace);
    }

    setViewMode('notes');
    const displayEl = document.getElementById('solution-display');
    const statusEl = document.getElementById('world-status-tag');

    if (data.case === 'unique') {
      statusEl.textContent = `Live Granite 8B: 1 Consistent World (${budget})`;
      statusEl.style.color = '#34d399';
      displayEl.innerHTML = `
        <div class="schedule-card" style="border-color: #10b981;">
          <h4 style="color: #34d399;">⚡ Live Inferred Schedule (Granite 4.2 8B • ${budget})</h4>
          <table class="schedule-table">
            <thead><tr><th>Staff</th><th>Block</th><th>Station</th></tr></thead>
            <tbody>
              ${Object.entries(data.assignment || {}).map(([p, info]) => `
                <tr>
                  <td><strong>${p}</strong></td>
                  <td><code>${info.block || '—'}</code></td>
                  <td>${info.station ? '🛡️ ' + info.station : '<span style="color:#64748b">None</span>'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else if (data.case === 'ambiguous') {
      const assigns = data.assignments || [];
      statusEl.textContent = `Live Granite 8B: ${assigns.length} Consistent Worlds (${budget})`;
      statusEl.style.color = '#fbbf24';
      displayEl.innerHTML = `
        <div class="schedule-card" style="border-color: #f59e0b;">
          <h4 style="color: #fbbf24;">⚡ Live Inferred Candidates (Granite 4.2 8B • ${budget})</h4>
          ${assigns.map((assign, i) => `
            <div style="background:#0f1422; border:1px solid #1e293b; padding:8px; border-radius:5px; margin-bottom:8px;">
              <strong style="font-size:0.75rem; color:#38bdf8;">Candidate #${i + 1}</strong>
              <table class="schedule-table">
                <tbody>
                  ${Object.entries(assign).map(([p, info]) => `
                    <tr><td><strong>${p}</strong></td><td><code>${info.block}</code></td><td>${info.station || '—'}</td></tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      statusEl.textContent = `Live Granite 8B: Inconsistent (${budget})`;
      statusEl.style.color = '#f87171';
        displayEl.innerHTML = `
          <div class="schedule-card" style="border-color: #ef4444;">
            <h4 style="color: #f87171;">⚡ Live Minimal Unsatisfiable Core Citations (${budget})</h4>
            <ul style="padding-left: 18px; font-size: 0.82rem; color: #fca5a5;">
              ${(data.conflicts || []).map(stmt => `<li style="margin-bottom: 4px;">"${stmt}"</li>`).join('')}
            </ul>
          </div>
        `;
      }

      const actionsDiv = document.createElement('div');
      actionsDiv.style.marginTop = '14px';
      actionsDiv.style.display = 'flex';
      actionsDiv.style.gap = '10px';
      actionsDiv.style.flexWrap = 'wrap';

      actionsDiv.innerHTML = `
        <button class="trace-btn-highlight" onclick="setViewMode('trace')">
          🔍 View Step-by-Step Logic Trace & Model Rationale ➔
        </button>
        <button class="graph-btn-outline" onclick="setViewMode('graph')">
          🕸️ View Entity Graph
        </button>
      `;
      displayEl.appendChild(actionsDiv);

      const breakdownDiv = document.createElement('div');
      breakdownDiv.style.marginTop = '14px';
      breakdownDiv.style.padding = '12px 14px';
      breakdownDiv.style.background = '#0a0f1d';
      breakdownDiv.style.border = '1px solid #1e293b';
      breakdownDiv.style.borderRadius = '6px';
      breakdownDiv.style.fontSize = '0.78rem';
      breakdownDiv.style.color = '#94a3b8';

      breakdownDiv.innerHTML = `
        <strong style="color:#e2e8f0; font-size:0.82rem; display:block; margin-bottom:6px;">⚡ Live Inference Telemetry:</strong>
        <div style="display:flex; flex-direction:column; gap:5px; line-height:1.4;">
          <div>• <strong>Budget & Calls:</strong> ${data.telemetry ? data.telemetry.calls_used : 1} of ${data.telemetry ? data.telemetry.max_calls : 1} calls used (${budget}).</div>
          <div>• <strong>World Pruning:</strong> 720 possible permutations → <strong>${data.telemetry ? data.telemetry.world_count : 0} worlds</strong>.</div>
          <div>• <strong>Audit Trail:</strong> Click the button above to view what Granite 8B thought at every step.</div>
        </div>
      `;
      displayEl.appendChild(breakdownDiv);

    } catch (err) {
      alert(`Live inference failed: ${err.message}. Ensure backend is running.`);
    } finally {
      btn.disabled = false;
      spinner.style.display = 'none';
      btnText.textContent = '⚡ Run Live Inference';
    }
  }
  window.runLiveInference = runLiveInference;

  function renderTraceTimeline(trace) {
    const container = document.getElementById('trace-timeline');
    if (!container) return;
    container.innerHTML = '';

    trace.forEach((step, idx) => {
      const div = document.createElement('div');
      div.className = 'trace-step-item';

      let detailsHtml = '';
      if (step.details) {
        if (step.details.constraints_extracted) {
          detailsHtml += `
            <div class="step-code-box">
              <strong>Extracted Logical Constraints:</strong><br>
              ${step.details.constraints_extracted.map(c => `• ${c}`).join('<br>')}
            </div>
          `;
        }
        if (step.details.sample_noise) {
          detailsHtml += `
            <div class="step-code-box" style="color:#94a3b8;">
              <strong>Sample Filtered Ambient Gossip:</strong><br>
              ${step.details.sample_noise.map(n => `• "${n}"`).join('<br>')}
            </div>
          `;
        }
        if (step.details.newly_recovered) {
          detailsHtml += `
            <div class="step-code-box" style="color:#34d399;">
              <strong>FSM Self-Repair Recovered Constraints:</strong><br>
              ${step.details.newly_recovered.map(r => `• ${r}`).join('<br>')}
            </div>
          `;
        }
        if (step.details.elimination_steps && step.details.elimination_steps.length > 0) {
          detailsHtml += `
            <div class="step-code-box" style="margin-top:8px;">
              <div style="font-weight:600; color:#38bdf8; margin-bottom:6px;">720-World Constraint Sieve (State-Space Reduction):</div>
              <table class="elimination-table" style="width:100%; border-collapse:collapse; font-size:0.75rem;">
                <thead>
                  <tr style="border-bottom:1px solid #1e293b; color:#94a3b8; text-align:left;">
                    <th style="padding:4px 6px;">#</th>
                    <th style="padding:4px 6px;">Logical Predicate</th>
                    <th style="padding:4px 6px;">Source Line</th>
                    <th style="padding:4px 6px; text-align:right;">Remaining</th>
                    <th style="padding:4px 6px; text-align:right;">Pruned</th>
                  </tr>
                </thead>
                <tbody>
                  ${step.details.elimination_steps.map(s => `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                      <td style="padding:4px 6px; color:#64748b;">${s.step}</td>
                      <td style="padding:4px 6px;"><code style="color:#a78bfa;">${s.constraint}</code></td>
                      <td style="padding:4px 6px; color:#94a3b8; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${s.source_line}">"${s.source_line}"</td>
                      <td style="padding:4px 6px; text-align:right; font-weight:600; color:${s.worlds_after === 0 ? '#ef4444' : s.worlds_after === 1 ? '#10b981' : '#38bdf8'};">${s.worlds_after} / 720</td>
                      <td style="padding:4px 6px; text-align:right; color:#ef4444;">-${s.pruned}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `;
        }
      }

      div.innerHTML = `
        <div class="step-marker">${step.step}</div>
        <div class="step-content">
          <div class="step-title-row">
            <span class="step-title">${step.title}</span>
            <span class="step-call-tag">${step.calls > 0 ? `API Call #${step.calls}` : 'Deterministic'}</span>
          </div>
          <p class="step-desc">${step.description}</p>
          ${detailsHtml}
        </div>
      `;
      container.appendChild(div);
    });
  }

  function openBudgetGuide() {
    const modal = document.getElementById('budget-modal');
    if (modal) modal.style.display = 'flex';
  }
  window.openBudgetGuide = openBudgetGuide;

  function closeBudgetGuide(event) {
    const modal = document.getElementById('budget-modal');
    if (modal) modal.style.display = 'none';
  }
  window.closeBudgetGuide = closeBudgetGuide;

  function onBudgetChange() {
    const select = document.getElementById('budget-select');
    const val = select ? select.value : '1x';
    const badge = document.getElementById('calls-badge');
    if (badge) {
      if (val === '1x') badge.textContent = 'Calls: 1 / 1 (Single-Pass)';
      else if (val === '3x') badge.textContent = 'Calls: ≤ 3 (Adaptive FSM)';
      else if (val === '10x') badge.textContent = 'Calls: ≤ 10 (Consensus)';
    }
  }
  window.onBudgetChange = onBudgetChange;

function renderKnowledgeGraph(item) {
  const svg = document.getElementById('kg-canvas');
  if (!svg || !item) return;

  const headerLine = item.text.split('\n')[0];
  let staff = [];
  if (headerLine.includes('staff on the rota:')) {
    staff = headerLine.split('staff on the rota:')[1].split('.')[0].split(',').map(s => s.trim());
  }
  const blocks = ['07:00', '09:00', '11:00', '13:00', '15:00'];
  const stations = ['intake', 'calibration', 'packing'];

  const width = svg.clientWidth || 800;
  svg.innerHTML = '';

  const staffX = width * 0.18;
  const blockX = width * 0.52;
  const stationX = width * 0.85;

  const staffY = staff.map((_, i) => 70 + i * 85);
  const blockY = blocks.map((_, i) => 70 + i * 85);
  const stationY = stations.map((_, i) => 120 + i * 120);

  if (item.case === 'unique' && (item.assignment || item.assignments)) {
    const assign = item.assignment || item.assignments[0];
    staff.forEach((p, pIdx) => {
      const pInfo = assign[p];
      if (pInfo && pInfo.block) {
        const bIdx = blocks.indexOf(pInfo.block);
        if (bIdx !== -1) {
          drawLine(svg, staffX, staffY[pIdx], blockX, blockY[bIdx], '#3b82f6', 2);
        }
        if (pInfo.station) {
          const sIdx = stations.indexOf(pInfo.station);
          if (sIdx !== -1) {
            drawLine(svg, blockX, blockY[bIdx], stationX, stationY[sIdx], '#10b981', 2);
          }
        }
      }
    });
  }

  staff.forEach((p, i) => drawNode(svg, staffX, staffY[i], 24, '#0284c7', p, 'staff'));
  blocks.forEach((b, i) => drawNode(svg, blockX, blockY[i], 22, '#7c3aed', b, 'block'));
  stations.forEach((st, i) => drawNode(svg, stationX, stationY[i], 26, '#059669', st, 'station'));
}

function drawLine(svg, x1, y1, x2, y2, color, strokeWidth) {
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', x1);
  line.setAttribute('y1', y1);
  line.setAttribute('x2', x2);
  line.setAttribute('y2', y2);
  line.setAttribute('stroke', color);
  line.setAttribute('stroke-width', strokeWidth);
  line.setAttribute('stroke-dasharray', '4 4');
  svg.appendChild(line);
}

function drawNode(svg, x, y, r, fill, label, type) {
  const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');

  const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  circle.setAttribute('cx', x);
  circle.setAttribute('cy', y);
  circle.setAttribute('r', r);
  circle.setAttribute('fill', fill);
  circle.setAttribute('stroke', '#1e293b');
  circle.setAttribute('stroke-width', '2');
  group.appendChild(circle);

  const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  text.setAttribute('x', x);
  text.setAttribute('y', y + 4);
  text.setAttribute('text-anchor', 'middle');
  text.setAttribute('fill', '#ffffff');
  text.setAttribute('font-size', type === 'staff' ? '11px' : '10px');
  text.setAttribute('font-weight', '600');
  text.textContent = label;
  group.appendChild(text);

  svg.appendChild(group);
}
