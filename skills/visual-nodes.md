# Visual Nodes and Dashboards
description: Display rich HTML dashboards, charts, piecharts, flowcharts, and Notion-like boxes on the screen using floatable dashboard nodes.
when_to_use: User asks for a system overview, status report, complex comparisons, flowcharts, data visualization, or dashboards. Use nodes to represent your thoughts and display beautiful visual outputs.

## Instructions
You can create, edit, delete, and list floatable, interactive visual nodes on the user's screen. These nodes render HTML, CSS, and JS (via QtWebEngine).

### Guidelines for Node Design

1. **Self-Contained Vanilla CSS (Offline First)**:
   - **CRITICAL:** Do NOT use Tailwind CSS CDN or any other external framework scripts. CDNs are unstable, load slowly, and fail completely when offline. Write clean, self-contained Vanilla CSS instead.
   - Use CSS variables for colors, borders, and margins to keep your styles organized.

2. **High-Tech & Boxy HUD Aesthetics**:
   - Use transparent body backgrounds: `body { background: transparent; color: #f8fafc; font-family: 'Outfit', 'Segoe UI', sans-serif; margin: 0; padding: 12px; }`
   - Use boxy grid items with sharp, glowing borders: `border: 1px solid rgba(6, 182, 212, 0.25); box-shadow: 0 0 15px rgba(6, 182, 212, 0.1), inset 0 0 15px rgba(6, 182, 212, 0.05);`
   - Use vibrant neon theme highlights:
     - Cyan highlight: `#00f2ff` / `rgb(6, 182, 212)`
     - Magenta highlight: `#d946ef` / `rgb(217, 70, 239)`
     - Emerald Green: `#10b981` / `rgb(16, 185, 129)`
     - Amber Alert: `#f59e0b` / `rgb(245, 158, 11)`

3. **Typography**:
   - Use high-quality fonts. Include Google Fonts (`Outfit`, `Orbitron`, `Rajdhani`) via `<link>` but always specify system fallbacks like `system-ui`, `-apple-system`, `"Segoe UI"`, `sans-serif` so it loads offline.

4. **Animations & Interactive JS**:
   - Add hover micro-interactions: `transition: all 0.25s ease;` with subtle scale/translate transformations and border-color shifts.
   - Use vanilla JavaScript to handle interactive state changes like switching tabs or filtering lists.

---

## Code Templates

### 1. Interactive High-Tech Dashboard Card (Vanilla CSS + Tabs)
Standard blueprint for capabilities, files list, systems logs, and general dashboards.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Orbitron:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: rgba(10, 15, 30, 0.9);
      --border-cyan: rgba(6, 182, 212, 0.3);
      --neon-cyan: #00f2ff;
      --neon-purple: #d946ef;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }
    body {
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: transparent;
      margin: 0;
      padding: 10px;
      color: var(--text-main);
      overflow-x: hidden;
    }
    .hud-box {
      background: var(--bg-dark);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-cyan);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 0 20px rgba(6, 182, 212, 0.15), inset 0 0 20px rgba(6, 182, 212, 0.05);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      border-bottom: 1px solid rgba(6, 182, 212, 0.2);
      padding-bottom: 16px;
    }
    .title-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .title {
      font-size: 20px;
      font-weight: 700;
      background: linear-gradient(to right, var(--neon-cyan), var(--neon-purple));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-shadow: 0 0 10px rgba(6, 182, 212, 0.4);
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .subtitle {
      font-size: 10px;
      color: rgba(6, 182, 212, 0.6);
      font-family: 'Orbitron', monospace;
      margin: 2px 0 0 0;
      letter-spacing: 2px;
      text-transform: uppercase;
    }
    .tabs {
      display: flex;
      gap: 8px;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid rgba(6, 182, 212, 0.2);
      color: var(--text-muted);
      padding: 6px 12px;
      font-size: 10px;
      font-family: 'Orbitron', sans-serif;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .tab-btn:hover {
      color: var(--text-main);
      border-color: rgba(6, 182, 212, 0.5);
    }
    .tab-btn.active {
      border-color: rgba(6, 182, 212, 0.8);
      background: rgba(6, 182, 212, 0.15);
      color: var(--neon-cyan);
      text-shadow: 0 0 8px rgba(6, 182, 212, 0.5);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .grid-item {
      display: flex;
      align-items: start;
      gap: 14px;
      background: rgba(30, 41, 59, 0.35);
      border: 1px solid rgba(6, 182, 212, 0.1);
      padding: 16px;
      border-radius: 12px;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .grid-item:hover {
      border-color: rgba(6, 182, 212, 0.55);
      transform: translateY(-2px);
      background: rgba(30, 41, 59, 0.55);
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.2);
    }
    .item-icon {
      font-size: 20px;
    }
    .item-title {
      font-weight: 700;
      font-size: 14px;
      margin: 0;
      color: var(--text-main);
    }
    .item-desc {
      font-size: 12px;
      color: var(--text-muted);
      margin: 4px 0 0 0;
      line-height: 1.4;
    }
    .hidden {
      display: none !important;
    }
  </style>
</head>
<body>
  <div class="hud-box">
    <!-- Header -->
    <div class="header">
      <div class="title-group">
        <span class="item-icon">⚡</span>
        <div>
          <h2 class="title" id="db-title">IRA Capabilities</h2>
          <p class="subtitle">System Core / v2.6.0</p>
        </div>
      </div>
      <!-- Tab Buttons -->
      <div class="tabs">
        <button onclick="switchTab('tab1')" id="btn-tab1" class="tab-btn active">Core</button>
        <button onclick="switchTab('tab2')" id="btn-tab2" class="tab-btn">Extra</button>
      </div>
    </div>

    <!-- Tab 1 Contents -->
    <div id="tab1-content">
      <div class="grid">
        <div class="grid-item">
          <span class="item-icon">👁️</span>
          <div>
            <h4 class="item-title">Screen Vision</h4>
            <p class="item-desc">Precise screen capture with dynamic coordinate mapping.</p>
          </div>
        </div>
        <div class="grid-item">
          <span class="item-icon">🌐</span>
          <div>
            <h4 class="item-title">Browser Control</h4>
            <p class="item-desc">DOM interaction via browser playwright wrapper.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2 Contents -->
    <div id="tab2-content" class="hidden">
      <div class="grid">
        <div class="grid-item">
          <span class="item-icon">🎤</span>
          <div>
            <h4 class="item-title">Live Voice</h4>
            <p class="item-desc">Sub-200ms end-to-end audio chat session.</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(tabId) {
      document.getElementById('tab1-content').classList.add('hidden');
      document.getElementById('tab2-content').classList.add('hidden');
      document.getElementById('btn-tab1').classList.remove('active');
      document.getElementById('btn-tab2').classList.remove('active');

      document.getElementById(tabId + '-content').classList.remove('hidden');
      document.getElementById('btn-' + tabId).classList.add('active');
    }
  </script>
</body>
</html>
```

### 2. High-Tech Chart.js Dashboard (Vanilla CSS)
Doughnut chart dashboard using self-contained layout.

```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Orbitron:wght@500;700&display=swap" rel="stylesheet">
  <style>
    body {
      background: transparent;
      color: #f1f5f9;
      font-family: 'Outfit', sans-serif;
      margin: 0;
      padding: 10px;
    }
    .hud-box {
      background: rgba(10, 15, 30, 0.9);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(6, 182, 212, 0.3);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 0 20px rgba(6, 182, 212, 0.15);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid rgba(6, 182, 212, 0.2);
      padding-bottom: 12px;
    }
    .title {
      font-size: 18px;
      font-family: 'Orbitron', sans-serif;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #00f2ff;
      margin: 0;
    }
    .badge {
      font-size: 10px;
      font-family: monospace;
      background: rgba(6, 182, 212, 0.1);
      color: #00f2ff;
      border: 1px solid rgba(6, 182, 212, 0.3);
      padding: 2px 8px;
      border-radius: 9999px;
    }
    .stats-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 16px;
      text-align: center;
    }
    .stat-card {
      background: rgba(30, 41, 59, 0.3);
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(6, 182, 212, 0.1);
    }
    .stat-label {
      font-size: 10px;
      color: #94a3b8;
      text-transform: uppercase;
      font-weight: 600;
    }
    .stat-val {
      font-size: 18px;
      font-weight: 700;
      font-family: monospace;
      margin-top: 4px;
    }
    .chart-wrapper {
      position: relative;
      height: 200px;
      width: 100%;
    }
  </style>
</head>
<body>
  <div class="hud-box">
    <div class="header">
      <h2 class="title">Resource Analysis</h2>
      <span class="badge">REALTIME</span>
    </div>
    
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">CPU</div>
        <div class="stat-val" style="color: #00f2ff;">35%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">RAM</div>
        <div class="stat-val" style="color: #d946ef;">48%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">GPU</div>
        <div class="stat-val" style="color: #10b981;">17%</div>
      </div>
    </div>

    <div class="chart-wrapper">
      <canvas id="chartCanvas"></canvas>
    </div>
  </div>

  <script>
    const ctx = document.getElementById('chartCanvas').getContext('2d');
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['CPU', 'RAM', 'GPU'],
        datasets: [{
          data: [35, 48, 17],
          backgroundColor: ['#00f2ff', '#d946ef', '#10b981'],
          borderColor: '#0a0f1e',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#94a3b8',
              font: { family: 'Outfit', size: 11 }
            }
          }
        }
      }
    });
  </script>
</body>
</html>
```

## Tooling Usage
- **node_create**: Create a new node. Provide a unique string `id` (e.g. `system-stats`), a title, and `content` (HTML).
- **node_edit**: Modify an existing node.
- **node_delete**: Remove the node when it is no longer needed.
- **node_list**: Check what nodes are active on the screen.
