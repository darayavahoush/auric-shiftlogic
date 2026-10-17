// ShiftLogic Web UI Controller
let allItems = [];
let activeItem = null;
let currentFilter = 'all';

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const res = await fetch('data.json');
    allItems = await res.json();
    initApp();
  } catch (err) {
    console.error('Failed to load data.json:', err);
  }
});

function initApp() {
  setupTabs();
  setupFilters();
  setupSearch();
  renderItemList();
  if (allItems.length > 0) {
    selectItem(allItems[0]);
  }
}

function setupTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      
      tab.classList.add('active');
      const targetId = `tab-${tab.dataset.tab}`;
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add('active');
      
      if (tab.dataset.tab === 'knowledge-graph') {
        renderKnowledgeGraph(activeItem);
      }
    });
  });
}

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

  // Update header
  document.getElementById('active-item-id').textContent = item.id;
  const badge = document.getElementById('active-case-badge');
  badge.textContent = item.case;
  badge.className = `case-badge badge-${item.case}`;

  // Update Notes
  renderNotes(item);

  // Update Solver Stats
  renderSolverView(item);

  // Update Graph
  renderKnowledgeGraph(item);
}

function renderNotes(item) {
  const feed = document.getElementById('lines-feed');
  feed.innerHTML = '';

  const lines = item.text.split('\n')[1:].filter(l => l.trim());
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

function renderSolverView(item) {
  const validWorldsEl = document.getElementById('stat-valid-worlds');
  const worldsStatusEl = document.getElementById('stat-worlds-status');
  const displayEl = document.getElementById('solution-display');
  displayEl.innerHTML = '';

  if (item.case === 'unique') {
    validWorldsEl.textContent = '1';
    validWorldsEl.className = 'stat-number text-green';
    worldsStatusEl.textContent = 'Unique Schedule Derived';

    const assign = item.assignment || (item.assignments && item.assignments[0]) || {};
    displayEl.innerHTML = `
      <div class="schedule-card">
        <h4>Consistent Shift Roster</h4>
        <table class="schedule-table">
          <thead><tr><th>Staff</th><th>Time Block</th><th>Workstation</th></tr></thead>
          <tbody>
            ${Object.entries(assign).map(([p, info]) => `
              <tr>
                <td><strong>${p}</strong></td>
                <td><code>${info.block || '—'}</code></td>
                <td><span class="dot station-dot"></span> ${info.station || 'None'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  } else if (item.case === 'ambiguous') {
    const assigns = item.assignments || [];
    validWorldsEl.textContent = assigns.length.toString();
    validWorldsEl.className = 'stat-number text-amber';
    worldsStatusEl.textContent = `${assigns.length} Valid Assignments Found`;

    displayEl.innerHTML = `
      <div class="roster-grid">
        ${assigns.map((assign, i) => `
          <div class="schedule-card">
            <h4>Candidate Schedule #${i + 1}</h4>
            <table class="schedule-table">
              <thead><tr><th>Staff</th><th>Block</th><th>Station</th></tr></thead>
              <tbody>
                ${Object.entries(assign).map(([p, info]) => `
                  <tr>
                    <td><strong>${p}</strong></td>
                    <td><code>${info.block || '—'}</code></td>
                    <td>${info.station || '—'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `).join('')}
      </div>
    `;
  } else {
    validWorldsEl.textContent = '0';
    validWorldsEl.className = 'stat-number text-red';
    worldsStatusEl.textContent = 'Minimal Conflicting Core Detected';

    const conflictSets = item.conflict_line_sets || [];
    displayEl.innerHTML = `
      <div class="schedule-card" style="border-color: #ef4444;">
        <h4 style="color: #f87171;">Minimal Unsatisfiable Core (MUS) Citations</h4>
        <p style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 12px;">
          The following statements cannot all hold simultaneously. Dropping any single statement leaves a valid schedule.
        </p>
        ${conflictSets.map((set, i) => `
          <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.2); padding: 10px; border-radius: 6px; margin-bottom: 8px;">
            <strong style="font-size: 0.75rem; color: #f87171;">Contradiction Set #${i + 1} (${set.length} statements):</strong>
            <ul style="padding-left: 20px; font-size: 0.82rem; margin-top: 6px;">
              ${set.map(stmt => `<li style="margin-bottom: 4px;">"${stmt}"</li>`).join('')}
            </ul>
          </div>
        `).join('')}
      </div>
    `;
  }
}

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
  const height = 480;
  svg.innerHTML = '';

  // Positions
  const staffX = width * 0.2;
  const blockX = width * 0.55;
  const stationX = width * 0.85;

  const staffY = staff.map((_, i) => 80 + i * 75);
  const blockY = blocks.map((_, i) => 80 + i * 75);
  const stationY = stations.map((_, i) => 120 + i * 110);

  // Draw Edges first (if assignment exists)
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

  // Draw Staff Nodes
  staff.forEach((p, i) => {
    drawNode(svg, staffX, staffY[i], 24, '#0284c7', p, 'staff');
  });

  // Draw Block Nodes
  blocks.forEach((b, i) => {
    drawNode(svg, blockX, blockY[i], 22, '#7c3aed', b, 'block');
  });

  // Draw Station Nodes
  stations.forEach((st, i) => {
    drawNode(svg, stationX, stationY[i], 26, '#059669', st, 'station');
  });
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

async function runLiveInference() {
  if (!activeItem) return;

  const btn = document.getElementById('live-run-btn');
  const spinner = document.getElementById('btn-spinner');
  const btnText = document.getElementById('btn-text');

  btn.disabled = true;
  spinner.style.display = 'inline-block';
  btnText.textContent = ' Running Granite 8B...';

  try {
    const res = await fetch('/api/solve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: activeItem.id, budget: '1x' })
    });

    if (!res.ok) {
      throw new Error(`Inference error: ${res.statusText}`);
    }

    const data = await res.json();
    console.log('Live inference result:', data);

    // Switch to solver tab and update display with live result
    const solverTab = document.querySelector('.tab-btn[data-tab="solver-view"]');
    if (solverTab) solverTab.click();

    // Render result
    const displayEl = document.getElementById('solution-display');
    const validWorldsEl = document.getElementById('stat-valid-worlds');
    const worldsStatusEl = document.getElementById('stat-worlds-status');

    if (data.case === 'unique') {
      validWorldsEl.textContent = '1';
      validWorldsEl.className = 'stat-number text-green';
      worldsStatusEl.textContent = 'Live Granite 8B: Unique Schedule Derived';
      displayEl.innerHTML = `
        <div class="schedule-card" style="border-color: #10b981;">
          <h4 style="color: #34d399;">⚡ Live Inferred Shift Roster (Granite 4.2 8B)</h4>
          <table class="schedule-table">
            <thead><tr><th>Staff</th><th>Time Block</th><th>Workstation</th></tr></thead>
            <tbody>
              ${Object.entries(data.assignment || {}).map(([p, info]) => `
                <tr>
                  <td><strong>${p}</strong></td>
                  <td><code>${info.block || '—'}</code></td>
                  <td><span class="dot station-dot"></span> ${info.station || 'None'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else if (data.case === 'ambiguous') {
      const assigns = data.assignments || [];
      validWorldsEl.textContent = assigns.length.toString();
      validWorldsEl.className = 'stat-number text-amber';
      worldsStatusEl.textContent = `Live Granite 8B: ${assigns.length} Valid Assignments Found`;
      displayEl.innerHTML = `
        <div class="roster-grid">
          ${assigns.map((assign, i) => `
            <div class="schedule-card" style="border-color: #f59e0b;">
              <h4 style="color: #fbbf24;">Candidate Schedule #${i + 1}</h4>
              <table class="schedule-table">
                <thead><tr><th>Staff</th><th>Block</th><th>Station</th></tr></thead>
                <tbody>
                  ${Object.entries(assign).map(([p, info]) => `
                    <tr>
                      <td><strong>${p}</strong></td>
                      <td><code>${info.block || '—'}</code></td>
                      <td>${info.station || '—'}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      validWorldsEl.textContent = '0';
      validWorldsEl.className = 'stat-number text-red';
      worldsStatusEl.textContent = 'Live Granite 8B: Minimal Conflicting Core Detected';
      displayEl.innerHTML = `
        <div class="schedule-card" style="border-color: #ef4444;">
          <h4 style="color: #f87171;">⚡ Live Minimal Unsatisfiable Core Citations</h4>
          <p style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 12px;">
            The solver identified the following minimal contradictory statements:
          </p>
          <ul style="padding-left: 20px; font-size: 0.85rem; color: #fca5a5;">
            ${(data.conflicts || []).map(stmt => `<li style="margin-bottom: 6px;">"${stmt}"</li>`).join('')}
          </ul>
        </div>
      `;
    }

  } catch (err) {
    alert(`Live inference failed: ${err.message}. Make sure server.py is running.`);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    btnText.textContent = '⚡ Run Live Inference';
  }
}

