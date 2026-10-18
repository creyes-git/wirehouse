/* Wirehouse viewer.
 * Data: window.WIREHOUSE (archmap.json). Rendering: Three.js r149 (global THREE).
 *
 * The map is a tree of rooms. The main floor shows top-level blocks; walking
 * into a block opens a room with its children. Edges are stored at file
 * level and rolled up to whatever is visible: pipes between blocks in the
 * room, and wall ports for connections that leave the room.
 */
(function () {
  'use strict';

  const D = window.WIREHOUSE;
  const ROOT = '';

  // ── small utilities ──────────────────────────────────────────────────────
  const $ = (s) => document.querySelector(s);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('wirehouse:' + k); return v == null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('wirehouse:' + k, v); } catch (e) { /* storage blocked: fine */ } },
  };
  const motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  let reduceMotion = !!(motionQuery && motionQuery.matches);
  if (motionQuery && motionQuery.addEventListener) motionQuery.addEventListener('change', (e) => { reduceMotion = e.matches; });

  // ── model ────────────────────────────────────────────────────────────────
  const N = new Map();
  D.nodes.forEach((n) => N.set(n.id, n));
  const KIDS = new Map();
  D.nodes.forEach((n) => {
    const p = n.parent || ROOT;
    if (!KIDS.has(p)) KIDS.set(p, []);
    KIDS.get(p).push(n.id);
  });
  const kidsOf = (id) => KIDS.get(id || ROOT) || [];
  const enterable = (id) => kidsOf(id).length > 0;
  const parentOf = (id) => (N.get(id) && N.get(id).parent) || ROOT;
  function chain(id) { // leaf -> top
    const out = [];
    let c = id;
    while (c) { out.push(c); c = N.get(c) ? N.get(c).parent : null; }
    return out;
  }
  const EDGES = D.edges
    .filter((e) => N.has(e.source) && N.has(e.target))
    .map((e, i) => Object.assign({ i, sc: chain(e.source), tc: chain(e.target) }, e));

  function childOf(ch, R) {
    for (const x of ch) if (parentOf(x) === R) return x;
    return null;
  }
  function outsideRep(ch, rset) {
    for (let k = ch.length - 1; k >= 0; k--) if (!rset.has(ch[k])) return ch[k];
    return null;
  }

  /** Roll every edge up to the children of room R. */
  function roomLinks(R) {
    const inner = new Map();
    const ports = new Map();
    const rset = new Set(R ? chain(R) : []);
    const add = (map, key, base, e) => {
      let L = map.get(key);
      if (!L) { L = Object.assign({ kinds: new Set(), count: 0, edges: [], ids: new Set() }, base); map.set(key, L); }
      L.kinds.add(e.kind);
      L.ids.add(e.i);   // every edge, uncapped: traces light pipes by edge
      L.count += e.count || 1;
      if (L.edges.length < 300) L.edges.push(e);
      return L;
    };
    for (const e of EDGES) {
      const a = childOf(e.sc, R);
      const b = childOf(e.tc, R);
      if (a && b) {
        if (a !== b) add(inner, a + '>' + b, { a, b }, e);
      } else if (R && (a || b || e.sc.includes(R) || e.tc.includes(R))) {
        const insideIsSource = !!a || e.sc.includes(R);
        const outer = insideIsSource ? e.tc : e.sc;
        if (outer.includes(R)) continue; // both ends live inside this room
        const rep = outsideRep(outer, rset);
        if (!rep) continue;
        const dir = insideIsSource ? 'out' : 'in';
        const P = add(ports, rep + '|' + dir, { rep, dir, inners: new Map() }, e);
        const innerId = insideIsSource ? a : b;
        if (innerId) add(P.inners, innerId, { id: innerId }, e);
      }
    }
    return { inner: [...inner.values()], ports: [...ports.values()] };
  }

  // ── vocabulary ───────────────────────────────────────────────────────────
  const KIND_LABEL = {
    user: 'People and clients', frontend: 'Web frontend', mobile: 'Mobile app', desktop: 'Desktop app',
    gateway: 'Gateway', auth: 'Authentication', service: 'Backend service', worker: 'Worker or job',
    function: 'Serverless function', library: 'Shared library', database: 'Database', cache: 'Cache',
    queue: 'Queue', storage: 'File storage', search: 'Search index', external: 'Third-party API',
    ai: 'AI provider', infra: 'Infrastructure', ci: 'CI/CD', observability: 'Observability', tests: 'Tests',
    module: 'Folder', file: 'File', table: 'Table', resource: 'Infrastructure item',
  };
  const EDGE_LABEL = {
    imports: 'imports code', calls: 'calls', data: 'reads and writes', auth: 'signs in with',
    publishes: 'sends messages', depends_on: 'starts after', provisions: 'provisions', uses: 'uses', references: 'references',
  };
  const LANG = { typescript: 'TypeScript', javascript: 'JavaScript', python: 'Python', csharp: 'C#', go: 'Go', sql: 'SQL', prisma: 'Prisma' };

  // ── themes ───────────────────────────────────────────────────────────────
  const THEMES = {
    night: {
      name: 'Night shift', bg: 0x070b16, fogNear: 45, fogFar: 190,
      floor: 0x0a1020, floorAlt: 0x0d1529, paint: 0x2a4170, wall: 0x0c1426, wallLine: 0x2b4a80, beam: 0x16213b,
      hemi: [0x5f7ab8, 0x05070d, 0.85], key: [0xffc888, 0.45], glow: true, shadows: false,
      label: { bg: 'rgba(7,11,22,0.86)', ink: '#eef2f8', sub: '#93a0b8', edge: 'rgba(150,170,210,0.35)' },
      paintText: 'rgba(110,140,200,0.16)', particle: 1.0,
      kind: {
        user: 0xd7dde8, frontend: 0x39c0f5, mobile: 0x39c0f5, desktop: 0x39c0f5, gateway: 0xa78bfa, auth: 0xf472b6,
        service: 0x2dd4bf, worker: 0x4ade80, function: 0xa3e635, library: 0x94a3b8, tests: 0x7c8aa5,
        database: 0xfbbf24, cache: 0xfb923c, queue: 0xf87171, storage: 0xe0a96d, search: 0xfacc15,
        external: 0x818cf8, ai: 0xe879f9, infra: 0x9fb39a, ci: 0x9fb39a, observability: 0x9fb39a,
        module: 0x8fa8d8, file: 0xa9b8d6, table: 0xfcd34d, resource: 0x9fb39a,
      },
      edge: { imports: 0x7d8aa6, calls: 0x39c0f5, data: 0xfbbf24, auth: 0xf472b6, publishes: 0xf87171, depends_on: 0x56637d, provisions: 0x9fb39a, uses: 0xa78bfa, references: 0xd6b98c },
      trace: { down: 0x34d399, up: 0xc4b5fd, route: 0xffb23f },
    },
    day: {
      name: 'Day shift', bg: 0xdfe2e4, fogNear: 80, fogFar: 260,
      floor: 0xa9a59c, floorAlt: 0xa19d94, paint: 0xe8b81e, wall: 0xc9ccce, wallLine: 0x6f7984, beam: 0x6d7780,
      hemi: [0xf4f6f8, 0x6f6a60, 0.62], key: [0xfff6e8, 0.62], glow: false, shadows: true,
      label: { bg: 'rgba(250,249,245,0.95)', ink: '#1b2330', sub: '#5a6474', edge: 'rgba(27,35,48,0.25)' },
      paintText: 'rgba(60,64,72,0.10)', particle: 0.8,
      kind: {
        user: 0x5b6474, frontend: 0x2f80c0, mobile: 0x2f80c0, desktop: 0x2f80c0, gateway: 0x6d5bd0, auth: 0xc2417f,
        service: 0x1f8c80, worker: 0x3c8d4e, function: 0x6f9a1f, library: 0x6b7686, tests: 0x7a8494,
        database: 0xd08f12, cache: 0xd06a1f, queue: 0xc2453c, storage: 0xa77446, search: 0xb89410,
        external: 0x4f5bd5, ai: 0xa63db8, infra: 0x5f7a5a, ci: 0x5f7a5a, observability: 0x5f7a5a,
        module: 0xb98a55, file: 0xd9c9a8, table: 0xe0b44a, resource: 0x7f9a7a,
      },
      edge: { imports: 0x7c8594, calls: 0x2f80c0, data: 0xd08f12, auth: 0xc2417f, publishes: 0xc2453c, depends_on: 0x9aa2ad, provisions: 0x5f7a5a, uses: 0x6d5bd0, references: 0x8a6a3f },
      trace: { down: 0x13865c, up: 0x6d4fd6, route: 0xd9822b },
    },
  };
  let themeId = store.get('theme', window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'day' : 'night');
  if (!THEMES[themeId]) themeId = 'night';
  let T = THEMES[themeId];
  const kindHex = (k) => T.kind[k] != null ? T.kind[k] : T.kind.library;
  const edgeHex = (k) => T.edge[k] != null ? T.edge[k] : T.edge.uses;
  const css = (hex) => '#' + hex.toString(16).padStart(6, '0');

  // ── layout ───────────────────────────────────────────────────────────────
  const SHAPE = {
    user: 'people', frontend: 'kiosk', mobile: 'kiosk', desktop: 'kiosk', gateway: 'arch', auth: 'gate',
    service: 'container', worker: 'machine', function: 'container', library: 'stack', tests: 'container',
    database: 'silo', search: 'silo', cache: 'pucks', queue: 'conveyor', storage: 'pallet',
    external: 'dock', ai: 'dock', infra: 'cabinet', ci: 'cabinet', observability: 'cabinet',
    module: 'crate', file: 'slot', table: 'slot', resource: 'slot',
  };

  function blockSize(n) {
    const files = (n.stats && n.stats.files) || 0;
    const shape = SHAPE[n.kind] || 'container';
    if (shape === 'crate') {
      const s = clamp(2.6 + Math.sqrt(files) * 0.3, 2.6, 5.6);
      return { w: s, d: s, h: s * 0.78 };
    }
    if (shape === 'container' || shape === 'machine' || shape === 'stack') {
      const s = clamp(4.2 + Math.sqrt(files) * 0.34, 4.6, 10);
      return { w: s * 1.3, d: s * 0.72, h: 3.4 };
    }
    if (shape === 'kiosk') {
      const s = clamp(4.2 + Math.sqrt(files) * 0.3, 4.6, 9);
      return { w: s, d: s * 0.55, h: 4.4 };
    }
    if (shape === 'silo') {
      const t = (n.stats && n.stats.children) || 0;
      const s = clamp(3.8 + Math.sqrt(t) * 0.45, 3.8, 6.4);
      return { w: s, d: s, h: 5.6 };
    }
    return {
      pucks: { w: 3.6, d: 3.6, h: 2.6 }, conveyor: { w: 6.4, d: 2.4, h: 1.7 }, pallet: { w: 3.8, d: 3.8, h: 2.9 },
      dock: { w: 5.4, d: 2.9, h: 2.9 }, arch: { w: 5.2, d: 1.8, h: 4.4 }, gate: { w: 5.2, d: 1.8, h: 4.4 },
      cabinet: { w: enterable(n.id) ? 3.4 : 2.6, d: 1.8, h: 4.2 }, people: { w: 3.4, d: 2.6, h: 1.9 },
    }[shape] || { w: 4, d: 3, h: 3 };
  }

  const ZONES = [
    { id: 'clients', name: 'Clients', hint: 'Who starts a request' },
    { id: 'edge', name: 'Gateway and auth', hint: 'How requests get in and who is allowed' },
    { id: 'services', name: 'Services', hint: 'Your running code' },
    { id: 'data', name: 'Data', hint: 'Where things are stored' },
    { id: 'external', name: 'Loading dock', hint: 'Third-party providers' },
  ];
  const KIND_ORDER = ['user', 'frontend', 'mobile', 'desktop', 'gateway', 'auth', 'service', 'function', 'worker', 'library', 'tests',
    'database', 'search', 'cache', 'queue', 'storage', 'ai', 'external', 'infra', 'ci', 'observability'];

  function layoutRoot() {
    const tops = kidsOf(ROOT).map((id) => N.get(id));
    const byZone = {};
    const ops = [];
    for (const n of tops) {
      const z = n.layer === 'ops' ? 'ops' : (ZONES.some((Z) => Z.id === n.layer) ? n.layer : 'services');
      if (z === 'ops') ops.push(n); else (byZone[z] = byZone[z] || []).push(n);
    }
    const sortFn = (a, b) => (KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)) || a.name.localeCompare(b.name);
    const GAP = 4.5;
    const rows = [];
    for (const Z of ZONES) {
      const list = (byZone[Z.id] || []).sort(sortFn);
      if (!list.length && Z.id !== 'edge' && Z.id !== 'clients') continue;
      const sizes = list.map(blockSize);
      const width = sizes.reduce((s, b) => s + b.w, 0) + GAP * Math.max(0, list.length - 1);
      const depth = Math.max(5, ...sizes.map((b) => b.d)) + 9;
      rows.push({ Z, list, sizes, width, depth });
    }
    ops.sort(sortFn);
    const opsSizes = ops.map(blockSize);
    const opsW = ops.length ? Math.max(...opsSizes.map((s) => s.w)) + 7 : 0;
    const mainW = Math.max(40, ...rows.map((r) => r.width + 14));
    const W = mainW + opsW;
    const ENTRY = 9;
    const rowsDepth = rows.reduce((s, r) => s + r.depth, 0);
    const opsDepth = opsSizes.reduce((s, b) => s + b.d + 4, 0) + 6;
    const Dp = Math.max(rowsDepth + ENTRY + 4, opsDepth + ENTRY, 40);
    const items = [];
    const zones = [];
    const x0 = -W / 2 + opsW;
    const cx = x0 + mainW / 2;
    let z = Dp / 2 - ENTRY;
    for (const r of rows) {
      const zc = z - r.depth / 2;
      zones.push({ id: r.Z.id, name: r.Z.name, hint: r.Z.hint, x0, x1: W / 2, z0: z - r.depth, z1: z, empty: !r.list.length });
      let x = cx - r.width / 2;
      r.list.forEach((n, i) => {
        const s = r.sizes[i];
        items.push({ id: n.id, x: x + s.w / 2, z: zc, w: s.w, d: s.d, h: s.h, shape: SHAPE[n.kind] || 'container' });
        x += s.w + GAP;
      });
      z -= r.depth;
    }
    if (ops.length) {
      zones.push({ id: 'ops', name: 'Ops', hint: 'Build, deploy and watch', x0: -W / 2, x1: x0, z0: -Dp / 2, z1: Dp / 2 - ENTRY, empty: false, side: true });
      let oz = Dp / 2 - ENTRY - 4;
      ops.forEach((n, i) => {
        const s = opsSizes[i];
        items.push({ id: n.id, x: -W / 2 + opsW / 2, z: oz - s.d / 2, w: s.w, d: s.d, h: s.h, shape: SHAPE[n.kind] || 'cabinet' });
        oz -= s.d + 4;
      });
    }
    return { R: ROOT, W, D: Dp, items, zones, racks: [], ports: [], wallH: 11 };
  }

  const SLOT_W = 1.45, SLOT_COLS = 4, SLOT_LEVELS = 3, PER_RACK = SLOT_COLS * SLOT_LEVELS;

  function layoutRoom(R) {
    const kids = kidsOf(R).map((id) => N.get(id));
    const crates = kids.filter((n) => enterable(n.id) || !['file', 'table', 'resource'].includes(n.kind)).sort((a, b) => a.name.localeCompare(b.name));
    const leaves = kids.filter((n) => !crates.includes(n)).sort((a, b) => (a.test ? 1 : 0) - (b.test ? 1 : 0) || a.name.localeCompare(b.name));
    const items = [];
    const racks = [];
    const sizes = crates.map(blockSize);
    const cell = crates.length ? Math.max(...sizes.map((s) => Math.max(s.w, s.d))) + 3.6 : 0;
    const cols = crates.length ? Math.max(1, Math.min(8, Math.ceil(Math.sqrt(crates.length * 1.8)))) : 0;
    const crateRows = cols ? Math.ceil(crates.length / cols) : 0;
    const nRacks = Math.ceil(leaves.length / PER_RACK);
    const rackW = SLOT_COLS * SLOT_W + 0.5;
    const rackCols = nRacks ? Math.max(1, Math.min(6, Math.ceil(Math.sqrt(nRacks * 2.2)))) : 0;
    const rackRows = rackCols ? Math.ceil(nRacks / rackCols) : 0;
    const RX = rackW + 2.6, RZ = 5.2;
    const W = Math.max(28, cols * cell + 10, rackCols * RX + 10);
    const ENTRY = 9;
    const Dp = Math.max(24, ENTRY + crateRows * cell + (rackRows ? rackRows * RZ + 4 : 0) + 7);
    let z = Dp / 2 - ENTRY;
    crates.forEach((n, i) => {
      const r = Math.floor(i / cols), c = i % cols;
      const inRow = Math.min(cols, crates.length - r * cols);
      const s = sizes[i];
      items.push({ id: n.id, x: (c - (inRow - 1) / 2) * cell, z: z - r * cell - cell / 2, w: s.w, d: s.d, h: s.h, shape: SHAPE[n.kind] || 'crate' });
    });
    z -= crateRows * cell + (crateRows ? 2 : 0);
    for (let k = 0; k < nRacks; k++) {
      const r = Math.floor(k / rackCols), c = k % rackCols;
      const inRow = Math.min(rackCols, nRacks - r * rackCols);
      racks.push({ x: (c - (inRow - 1) / 2) * RX, z: z - r * RZ - RZ / 2, w: rackW, d: 1.5, h: SLOT_LEVELS * 1.2 + 0.4 });
    }
    leaves.forEach((n, i) => {
      const rk = racks[Math.floor(i / PER_RACK)];
      (rk.names = rk.names || []).push(n.name);
      const j = i % PER_RACK;
      const level = Math.floor(j / SLOT_COLS), col = j % SLOT_COLS;
      items.push({ id: n.id, x: rk.x - rackW / 2 + 0.25 + SLOT_W * (col + 0.5), z: rk.z, y: 0.32 + level * 1.2, w: SLOT_W - 0.25, d: 1.1, h: 0.82, shape: 'slot', rack: rk });
    });
    return { R, W, D: Dp, items, zones: [], racks, ports: [], wallH: 8 };
  }

  function placePorts(L, ports) {
    // Spread ports along the back wall, then down both side walls.
    const out = [];
    const backN = Math.min(ports.length, Math.max(1, Math.floor((L.W - 6) / 4.5)));
    const sideN = ports.length - backN;
    ports.forEach((p, i) => {
      let x, z, ry;
      if (i < backN) {
        x = -L.W / 2 + 3 + (L.W - 6) * ((i + 0.5) / backN); z = -L.D / 2 + 0.25; ry = 0;
      } else {
        const k = i - backN, side = k % 2 ? 1 : -1, idx = Math.floor(k / 2), per = Math.ceil(sideN / 2);
        x = side * (L.W / 2 - 0.25); z = -L.D / 2 + 4 + (L.D - 14) * ((idx + 0.5) / per); ry = -side * Math.PI / 2;
      }
      out.push(Object.assign({ x, z, y: 4.2, ry }, p));
    });
    return out;
  }

  // ── renderer / scene ─────────────────────────────────────────────────────
  const stage = $('#stage');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch (e) {
    stage.innerHTML = '<p style="padding:90px 24px;max-width:60ch">This browser could not start WebGL, so the 3D warehouse cannot be shown. The floor plan still works: press P or choose Floor plan.</p>';
  }
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 700);
  const world = new THREE.Group();
  scene.add(world);
  // GPU budget: most of a frame is pixel fill, so the resolution is capped and steps down on slow
  // devices (integrated GPUs on hi-dpi screens). Shadows are drawn once per room, not every frame.
  const MAX_DPR = 1.5, LOW_DPR = 1;
  const dprCap = () => Math.min(window.devicePixelRatio || 1, MAX_DPR);
  const GOV = { ratio: 1, frames: [], over: 0, under: 0 };
  if (renderer) {
    GOV.ratio = dprCap();
    renderer.setPixelRatio(GOV.ratio);
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.shadowMap.autoUpdate = false;
    stage.appendChild(renderer.domElement);
    renderer.domElement.tabIndex = 0;
  }
  function refreshShadows() { if (renderer) renderer.shadowMap.needsUpdate = true; }
  // Frame-time governor: when the 75th percentile of the last 2 s of frames stays over 18 ms for 2 s,
  // drop to 1x; when it stays under 12 ms for 2 s, step back up towards the cap.
  function governFrame(ms, now) {
    if (!renderer) return;
    const F = GOV.frames;
    F.push([now, ms]);
    while (F.length && F[0][0] < now - 2000) F.shift();
    if (F.length < 20) return;
    const sorted = F.map((f) => f[1]).sort((a, b) => a - b);
    const p75 = sorted[Math.floor(sorted.length * 0.75)];
    GOV.over = p75 > 18 ? (GOV.over || now) : 0;
    GOV.under = p75 < 12 ? (GOV.under || now) : 0;
    let next = GOV.ratio;
    if (GOV.over && now - GOV.over >= 2000) next = LOW_DPR;
    else if (GOV.under && now - GOV.under >= 2000) next = Math.min(dprCap(), GOV.ratio + 0.25);
    if (next !== GOV.ratio) {
      GOV.ratio = next;
      GOV.over = GOV.under = 0;
      F.length = 0;   // judge the new resolution on its own frames
      renderer.setPixelRatio(next);
      renderer.setSize(window.innerWidth, window.innerHeight);
    }
  }

  // material + geometry caches (cleared on theme change / room rebuild)
  let MATS = new Map();
  let GEOS = [];
  function mat(hex, o) {
    o = o || {};
    const key = hex + '|' + JSON.stringify(o);
    if (MATS.has(key)) return MATS.get(key);
    let m;
    if (o.basic) {
      m = new THREE.MeshBasicMaterial({ color: hex, transparent: !!o.opacity, opacity: o.opacity == null ? 1 : o.opacity, side: o.double ? THREE.DoubleSide : THREE.FrontSide, depthWrite: o.opacity == null });
    } else if (T.glow) {
      const c = new THREE.Color(hex);
      m = new THREE.MeshStandardMaterial({
        color: c.clone().multiplyScalar(o.bright ? 0.55 : 0.22), emissive: c, emissiveIntensity: o.emissive != null ? o.emissive : 0.12,
        roughness: 0.55, metalness: 0.25, transparent: !!o.opacity, opacity: o.opacity == null ? 1 : o.opacity,
        side: o.double ? THREE.DoubleSide : THREE.FrontSide,
      });
    } else {
      m = new THREE.MeshStandardMaterial({
        color: hex, roughness: o.rough != null ? o.rough : 0.72, metalness: o.metal != null ? o.metal : 0.08,
        emissive: o.emissive ? hex : 0x000000, emissiveIntensity: o.emissive || 0,
        transparent: !!o.opacity, opacity: o.opacity == null ? 1 : o.opacity, side: o.double ? THREE.DoubleSide : THREE.FrontSide,
      });
    }
    MATS.set(key, m);
    return m;
  }
  function geo(g) { GEOS.push(g); return g; }
  const lineMats = new Map();
  function lineMat(hex, opacity) {
    const key = hex + '|' + opacity;
    if (!lineMats.has(key)) lineMats.set(key, new THREE.LineBasicMaterial({ color: hex, transparent: opacity < 1, opacity }));
    return lineMats.get(key);
  }

  function mesh(g, m, x, y, z, parent) {
    const me = new THREE.Mesh(geo(g), m);
    me.position.set(x || 0, y || 0, z || 0);
    if (T.shadows) { me.castShadow = true; me.receiveShadow = true; }
    if (parent) parent.add(me);
    return me;
  }
  // Animated parts would go stale in the static shadow map, so they cast none.
  function noCast(obj) { obj.traverse((o) => { o.castShadow = false; }); return obj; }
  function box(w, h, d, hex, x, y, z, parent, o) {
    const m = mesh(new THREE.BoxGeometry(w, h, d), mat(hex, o), x, y + h / 2, z, parent);
    if (T.glow && !(o && o.noEdges)) {
      const edges = new THREE.LineSegments(geo(new THREE.EdgesGeometry(m.geometry)), lineMat(hex, o && o.edgeOpacity != null ? o.edgeOpacity : 0.9));
      m.add(edges);
    }
    return m;
  }

  // Repeated decorative parts (container ribs, rack frames, cabinet lights) are drawn as one
  // InstancedMesh per material instead of one mesh each. They are never picked, so nothing is lost,
  // and a busy floor drops from hundreds of draw calls to a few.
  let INST = new Map();
  const ORIGIN = new THREE.Vector3();
  function instBox(w, h, d, m, x, y, z, parent, o) {   // y is the bottom, like box()
    o = o || {};
    const key = m.uuid + (o.cast ? '|cast' : '');
    let b = INST.get(key);
    if (!b) { b = { m, cast: !!o.cast, mats: [], colors: [], phase: [] }; INST.set(key, b); }
    const at = parent ? parent.position : ORIGIN;
    b.mats.push(new THREE.Matrix4().compose(new THREE.Vector3(at.x + x, at.y + y + h / 2, at.z + z), new THREE.Quaternion(), new THREE.Vector3(w, h, d)));
    if (o.color != null) { b.colors.push(new THREE.Color(o.color)); b.phase.push(o.phase || 0); }
  }
  function flushInstances() {
    if (!INST.size) return;
    const unit = geo(new THREE.BoxGeometry(1, 1, 1));
    INST.forEach((b) => {
      const im = new THREE.InstancedMesh(unit, b.m, b.mats.length);
      b.mats.forEach((M, i) => im.setMatrixAt(i, M));
      b.colors.forEach((c, i) => im.setColorAt(i, c));
      im.frustumCulled = false;   // the bounding sphere is the unit box's, not the instances'
      im.castShadow = T.shadows && b.cast;
      im.receiveShadow = !!T.shadows;
      world.add(im);
      if (b.phase.length) {
        // cabinet lights blink by dimming their instance colour, not by hiding meshes
        const dim = new THREE.Color();
        ANIM.push((t) => {
          b.colors.forEach((c, i) => im.setColorAt(i, Math.sin(t * 3 + b.phase[i] * 1.7) > -0.6 ? c : dim.copy(c).multiplyScalar(0.15)));
          im.instanceColor.needsUpdate = true;
        });
      }
    });
    INST = new Map();
  }

  // text → canvas textures
  // Cached by text so walking back into a room is instant, but only for the last few rooms:
  // each texture can be a 1400px canvas on the GPU, and a big repo has many rooms.
  const TEX = new Map();
  const TEX_ROOMS = 3;
  let texRoom = 0;
  function textCanvas(lines, o) {
    o = o || {};
    const big = o.big || 46;
    const pad = o.pad == null ? 16 : o.pad;
    const c = document.createElement('canvas');
    const ctx = c.getContext('2d');
    const fonts = lines.map((l, i) => `${i === 0 ? (o.weight || 600) : 500} ${i === 0 ? big : Math.round(big * 0.62)}px ${i === 0 ? '"Barlow Condensed"' : '"Barlow"'}, "Arial Narrow", sans-serif`);
    let w = 0;
    lines.forEach((l, i) => { ctx.font = fonts[i]; w = Math.max(w, ctx.measureText(l).width); });
    const lh = lines.map((l, i) => (i === 0 ? big * 1.12 : big * 0.8));
    c.width = Math.ceil(Math.min(w, 1400) + pad * 2);
    c.height = Math.ceil(lh.reduce((a, b) => a + b, 0) + pad * 1.4);
    if (o.bg !== false) {
      ctx.fillStyle = o.bg || T.label.bg;
      const r = 10;
      ctx.beginPath();
      ctx.moveTo(r, 0); ctx.arcTo(c.width, 0, c.width, c.height, r); ctx.arcTo(c.width, c.height, 0, c.height, r);
      ctx.arcTo(0, c.height, 0, 0, r); ctx.arcTo(0, 0, c.width, 0, r); ctx.closePath(); ctx.fill();
      if (o.stripe) { ctx.fillStyle = o.stripe; ctx.fillRect(0, 0, 7, c.height); }
      ctx.strokeStyle = T.label.edge; ctx.lineWidth = 2; ctx.stroke();
    }
    let y = pad * 0.7;
    lines.forEach((l, i) => {
      ctx.font = fonts[i];
      ctx.fillStyle = i === 0 ? (o.ink || T.label.ink) : (o.sub || T.label.sub);
      ctx.textBaseline = 'top';
      ctx.textAlign = o.align === 'left' ? 'left' : 'center';
      const tx = o.align === 'left' ? pad + (o.stripe ? 6 : 0) : c.width / 2;
      ctx.fillText(l, tx, y + (i === 0 ? big * 0.06 : 0));
      y += lh[i];
    });
    return c;
  }
  function textTexture(lines, o) {
    const key = JSON.stringify([lines, o, themeId]);
    if (TEX.has(key)) { const hit = TEX.get(key); hit.userData.used = texRoom; return hit; }
    const c = textCanvas(lines, o);
    const t = new THREE.CanvasTexture(c);
    t.encoding = THREE.sRGBEncoding;
    t.anisotropy = 4;
    t.userData = { aspect: c.width / c.height, used: texRoom };
    TEX.set(key, t);
    return t;
  }
  function label(lines, height, o) {
    const t = textTexture(lines, o);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false }));
    sp.scale.set(height * t.userData.aspect, height, 1);
    sp.center.set(0.5, 0);
    sp.renderOrder = 5;
    return sp;
  }
  function decal(lines, width, o) {
    const t = textTexture(lines, o);
    const h = width / t.userData.aspect;
    const m = new THREE.Mesh(geo(new THREE.PlaneGeometry(width, h)), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
    return m;
  }
  function shortName(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }

  // ── blocks ───────────────────────────────────────────────────────────────
  // 24 units: from where the camera starts in a room (17 behind the worker) the first rack is about 23 away
  const SLOT_LABEL_FAR = 24, SLOT_LABELS_SHOWN = 24;
  const ANIM = [];   // per-frame animations for the current room
  let PICK = [];     // meshes that can be clicked
  let SPRITES = [];  // labels that fade with distance

  function tagPick(obj, info) { obj.traverse((o) => { if (o.isMesh) { o.userData.pick = info; PICK.push(o); } }); }

  function makeBlock(it) {
    const n = N.get(it.id);
    const g = new THREE.Group();
    g.position.set(it.x, 0, it.z);
    const col = kindHex(n.kind);
    const { w, d, h } = it;
    const S = it.shape;
    if (S === 'container' || S === 'dock' || S === 'machine' || S === 'stack') {
      if (S === 'stack') {
        const bw = w / 2 - 0.15, bd = d / 2 - 0.1;
        [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz], i) => box(bw, h * (i % 2 ? 0.45 : 0.5), bd, col, sx * (bw / 2 + 0.07), 0, sz * (bd / 2 + 0.05), g));
        box(bw, h * 0.42, bd, col, -bw / 2, h * 0.5, -bd / 2, g);
      } else {
        box(w, h, d, col, 0, 0, 0, g, { bright: S === 'dock' });
        const ribs = Math.max(4, Math.floor(w / 0.9));
        const ribM = mat(col, { noEdges: true, emissive: 0.25, bright: true });
        for (let i = 1; i < ribs; i++) {
          const rx = -w / 2 + (w * i) / ribs;
          instBox(0.08, h * 0.86, 0.06, ribM, rx, h * 0.07, d / 2 + 0.03, g);
          instBox(0.08, h * 0.86, 0.06, ribM, rx, h * 0.07, -d / 2 - 0.03, g);
        }
        box(0.06, h * 0.9, d * 0.46, 0x1a1f28, w / 2 + 0.03, h * 0.05, -d * 0.24, g, { noEdges: true });
        box(0.06, h * 0.9, d * 0.46, 0x1a1f28, w / 2 + 0.03, h * 0.05, d * 0.24, g, { noEdges: true });
        const sign = decal([shortName(n.name, 22)], Math.min(w * 0.7, 6), { bg: false, ink: T.glow ? css(col) : '#ffffff', weight: 700, big: 64 });
        sign.position.set(0, h * 0.55, d / 2 + 0.07);
        g.add(sign);
        if (S === 'machine') {
          const gear = new THREE.Group();
          mesh(new THREE.TorusGeometry(0.75, 0.22, 8, 18), mat(col, { bright: true, emissive: 0.4 }), 0, 0, 0, gear);
          for (let k = 0; k < 8; k++) {
            const tooth = mesh(new THREE.BoxGeometry(0.28, 0.42, 0.3), mat(col, { bright: true, emissive: 0.4 }), Math.cos(k * Math.PI / 4) * 1.0, Math.sin(k * Math.PI / 4) * 1.0, 0, gear);
            tooth.rotation.z = k * Math.PI / 4;
          }
          gear.position.set(w * 0.25, h + 1.1, 0);
          g.add(noCast(gear));
          ANIM.push((t) => { gear.rotation.z = t * 0.9; });
        }
        if (n.kind === 'ai') {
          const orb = noCast(mesh(new THREE.IcosahedronGeometry(0.7, 0), mat(col, { bright: true, emissive: 0.9 }), 0, h + 1.3, 0, g));
          ANIM.push((t) => { orb.rotation.y = t * 0.8; orb.position.y = h + 1.3 + Math.sin(t * 2) * 0.15; });
        }
      }
    } else if (S === 'kiosk') {
      box(w, h * 0.22, d, col, 0, 0, 0, g);
      box(w * 0.08, h * 0.35, 0.3, 0x2a2f3a, 0, h * 0.22, 0, g, { noEdges: true });
      const scr = box(w * 0.96, h * 0.52, 0.28, col, 0, h * 0.46, 0, g);
      const face = decal([shortName(n.name, 20), (n.tech || [])[0] || KIND_LABEL[n.kind]], w * 0.58, {
        bg: T.glow ? 'rgba(10,30,50,0.9)' : 'rgba(240,248,255,0.95)', ink: T.glow ? '#bfefff' : '#1b2330', big: 60,
      });
      face.position.set(0, h * 0.72, 0.16);
      g.add(face);
      scr.material = mat(col, { bright: true });
    } else if (S === 'silo') {
      const r = Math.min(w, d) / 2 * 0.92;
      mesh(new THREE.CylinderGeometry(r, r, h * 0.82, 28), mat(col), 0, h * 0.41, 0, g);
      mesh(new THREE.SphereGeometry(r, 28, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat(col), 0, h * 0.82, 0, g);
      for (let k = 1; k <= 3; k++) {
        const ring = mesh(new THREE.TorusGeometry(r + 0.04, 0.07, 6, 36), mat(col, { bright: true, emissive: 0.5 }), 0, (h * 0.82 * k) / 4, 0, g);
        ring.rotation.x = Math.PI / 2;
      }
      const sign = decal([shortName(n.name, 20)], Math.min(r * 1.7, 4.6), { bg: T.glow ? 'rgba(7,11,22,0.75)' : 'rgba(255,255,255,0.9)', big: 58 });
      sign.position.set(0, h * 0.5, r + 0.06);
      g.add(sign);
    } else if (S === 'pucks') {
      for (let k = 0; k < 3; k++) mesh(new THREE.CylinderGeometry(w / 2 - k * 0.15, w / 2 - k * 0.15, 0.7, 24), mat(col, { bright: k % 2 === 1 }), 0, 0.4 + k * 0.85, 0, g);
    } else if (S === 'conveyor') {
      box(w, 0.25, d, 0x3a3f48, 0, 0.9, 0, g, { noEdges: true });
      box(w, 0.9, 0.12, col, 0, 0, d / 2 - 0.06, g);
      box(w, 0.9, 0.12, col, 0, 0, -d / 2 + 0.06, g);
      const parcels = [];
      for (let k = 0; k < 4; k++) parcels.push(noCast(box(0.8, 0.6, 0.9, col, 0, 1.15, 0, g, { bright: true })));
      ANIM.push((t) => parcels.forEach((p, k) => { p.position.x = ((t * 0.8 + k / 4) % 1) * w - w / 2; }));
    } else if (S === 'pallet') {
      box(w, 0.3, d, 0x8a6a45, 0, 0, 0, g, { noEdges: true });
      const pts = [[-0.9, -0.9, 1.4], [0.8, -0.8, 1.1], [-0.8, 0.9, 1.2], [0.9, 0.9, 1.6], [0, 0, 1.0]];
      pts.forEach(([px, pz, s], i) => box(s, s * 0.8, s, col, px * (w / 4), 0.3 + (i === 4 ? 1.3 : 0), pz * (d / 4), g, { bright: i % 2 === 0 }));
    } else if (S === 'arch' || S === 'gate') {
      box(0.6, h, d, col, -w / 2 + 0.3, 0, 0, g);
      box(0.6, h, d, col, w / 2 - 0.3, 0, 0, g);
      box(w, 0.6, d, col, 0, h - 0.6, 0, g, { bright: true });
      const bar = noCast(box(w - 1.4, 0.14, 0.14, 0xf2c230, 0, 1.1, 0, g, { emissive: 0.4 }));
      if (S === 'gate') {
        const lock = new THREE.Group();
        mesh(new THREE.BoxGeometry(1.0, 0.85, 0.4), mat(col, { bright: true, emissive: 0.45 }), 0, 0, 0, lock);
        mesh(new THREE.TorusGeometry(0.33, 0.09, 8, 16, Math.PI), mat(col, { bright: true, emissive: 0.45 }), 0, 0.42, 0, lock);
        lock.position.set(0, h + 0.7, 0);
        g.add(noCast(lock));
        ANIM.push((t) => { lock.rotation.y = Math.sin(t * 1.2) * 0.5; });
      }
      ANIM.push((t) => { bar.rotation.z = Math.max(0, Math.sin(t * 0.6)) * 0.9; });
    } else if (S === 'cabinet') {
      box(w, h, d, col, 0, 0, 0, g);
      const ledM = mat(0xffffff, { basic: true });
      for (let r = 0; r < 6; r++) for (let c = 0; c < 3; c++) {
        instBox(0.16, 0.08, 0.04, ledM, -w / 4 + c * (w / 4), h * 0.2 + r * (h * 0.11) - 0.04, d / 2 + 0.03, g, { color: (r + c) % 3 ? 0x4ade80 : 0xfbbf24, phase: r * 3 + c });
      }
      const sign = decal([shortName(n.name, 16)], w * 0.86, { bg: false, ink: T.glow ? css(col) : '#ffffff', big: 60 });
      sign.position.set(0, h * 0.9, d / 2 + 0.05);
      g.add(sign);
    } else if (S === 'people') {
      box(w, 0.2, d, col, 0, 0, 0, g, { noEdges: true });
      [[-0.9, 0.2, 1], [0.15, -0.35, 1.1], [1.0, 0.35, 0.95]].forEach(([px, pz, s]) => {
        mesh(new THREE.CapsuleGeometry(0.28 * s, 0.7 * s, 4, 10), mat(col, { bright: true }), px, 0.2 + 0.63 * s, pz, g);
        mesh(new THREE.SphereGeometry(0.24 * s, 14, 10), mat(col, { bright: true }), px, 0.2 + 1.38 * s, pz, g);
      });
    } else if (S === 'crate') {
      const wood = T.glow ? col : 0xb98a55;
      box(w, h, d, wood, 0, 0, 0, g);
      if (!T.glow) {
        for (let k = 1; k < 4; k++) box(w + 0.04, 0.06, d + 0.04, 0x8f6a3f, 0, (h * k) / 4, 0, g, { noEdges: true });
        box(0.12, h, 0.12, 0x8f6a3f, -w / 2, 0, d / 2, g, { noEdges: true });
        box(0.12, h, 0.12, 0x8f6a3f, w / 2, 0, d / 2, g, { noEdges: true });
      }
      const st = decal([shortName(n.name, 18)], w * 0.84, { bg: false, ink: T.glow ? '#cfe0ff' : '#2b2117', weight: 700, big: 70 });
      st.position.set(0, h * 0.55, d / 2 + 0.03);
      g.add(st);
    } else {
      box(w, h, d, col, 0, 0, 0, g);
    }
    if (enterable(n.id) && S !== 'slot') {
      const door = noCast(box(Math.min(1.6, w * 0.4), Math.min(2.3, h * 0.75), 0.06, T.glow ? 0xffb23f : 0xf2c230, 0, 0, d / 2 + 0.06, g, { basic: true, opacity: 0.85, noEdges: true }));
      ANIM.push((t) => { door.material.opacity = 0.55 + Math.sin(t * 2.4) * 0.25; });
    }
    tagPick(g, { type: 'node', id: n.id });
    world.add(g);
    // floating label
    const sub = n.kind === 'module' ? `${(n.stats && n.stats.files) || 0} files` : (KIND_LABEL[n.kind] || n.kind);
    const lb = label([shortName(n.name, 28), sub], S === 'crate' ? 0.95 : 1.25, { stripe: css(col), align: 'left' });
    lb.position.set(it.x, h + (S === 'machine' || n.kind === 'ai' || S === 'gate' ? 2.3 : 0.6), it.z);
    world.add(lb);
    // on the main floor a far block's name never shrinks below about 14 px of text
    SPRITES.push({ sp: lb, far: 70, h: lb.scale.y, minPx: room && !room.R ? 30 : 0 });
    return g;
  }

  function makeRack(rk) {
    const g = new THREE.Group();
    g.position.set(rk.x, 0, rk.z);
    const steel = T.glow ? 0x3b5b94 : 0x2f6db5;
    const beam = T.glow ? 0xffb23f : 0xf28c28;
    const steelM = mat(steel, { noEdges: true, emissive: 0.4 }), beamM = mat(beam, { noEdges: true, emissive: 0.4 });
    const shelfM = mat(T.glow ? 0x121b30 : 0x9aa1a8, { noEdges: true });
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz]) => instBox(0.1, rk.h, 0.1, steelM, sx * (rk.w / 2), 0, sz * (rk.d / 2), g, { cast: true }));
    for (let l = 0; l < SLOT_LEVELS; l++) {
      instBox(rk.w, 0.07, rk.d, shelfM, 0, 0.25 + l * 1.2, 0, g, { cast: true });
      instBox(rk.w, 0.1, 0.08, beamM, 0, 0.25 + l * 1.2, rk.d / 2, g);
    }
    // An aisle sign, like a library shelf: readable from the door, where the file labels are too small.
    const names = rk.names || [];
    if (names.length) {
      const span = names.length > 1 ? `${shortName(names[0], 18)}  to  ${shortName(names[names.length - 1], 18)}` : shortName(names[0], 30);
      const sign = decal([span, `${names.length} file${names.length > 1 ? 's' : ''}`], Math.min(rk.w, 6), {
        bg: T.glow ? 'rgba(10,16,32,0.92)' : 'rgba(255,255,255,0.96)', stripe: T.glow ? '#ffb23f' : '#f28c28', align: 'left', big: 56,
      });
      sign.position.set(rk.x, rk.h + 0.15 + sign.geometry.parameters.height / 2, rk.z + rk.d / 2);
      sign.userData.rackSign = span;
      world.add(sign);
    }
  }

  function makeSlot(it) {
    const n = N.get(it.id);
    const g = new THREE.Group();
    g.position.set(it.x, it.y, it.z);
    let col = kindHex(n.kind);
    if (n.kind === 'file' && n.test) col = T.kind.tests;
    if (n.kind === 'file' && !T.glow) col = n.test ? 0xbfc4ca : 0xc9a46e;
    if (n.kind === 'table' && n.subkind === 'view') col = T.glow ? 0xfde68a : 0xe9cf86;
    if (n.kind === 'resource') col = kindHex(n.subkind && T.kind[n.subkind] != null ? n.subkind : 'resource');
    const h = n.kind === 'file' ? clamp(0.35 + Math.log2((n.lines || 10) + 1) * 0.06, 0.4, 0.9) : 0.75;
    box(it.w, h, it.d, col, 0, 0, 0, g, { edgeOpacity: 0.7 });
    if (n.endpoints && n.endpoints.length) noCast(box(it.w * 0.9, 0.08, 0.04, T.glow ? 0x39c0f5 : 0x2f80c0, 0, h * 0.7, it.d / 2 + 0.03, g, { basic: true, noEdges: true }));
    tagPick(g, { type: 'node', id: n.id });
    world.add(g);
    const lb = label([shortName(n.name, 26)], 0.34, { big: 40, pad: 10 });
    lb.position.set(it.x, it.y + h + 0.05, it.z + 0.45);
    world.add(lb);
    SPRITES.push({ sp: lb, far: SLOT_LABEL_FAR, h: lb.scale.y, slot: true });
    it.h = h;
  }

  // Labels fade in and out instead of popping. Only the nearest file labels show, so a room of racks
  // stays readable; far block names on the main floor keep a minimum size on screen.
  function updateLabels(dt, full) {
    const cp = camera.position;
    if (full) {
      const slots = [];
      SPRITES.forEach((s) => {
        s.dist = s.sp.position.distanceTo(cp);
        s.want = s.dist < s.far ? 1 : 0;
        if (s.slot && s.want) slots.push(s);
      });
      if (slots.length > SLOT_LABELS_SHOWN) slots.sort((a, b) => a.dist - b.dist).slice(SLOT_LABELS_SHOWN).forEach((s) => { s.want = 0; });
      const pxPerUnit = window.innerHeight / (2 * Math.tan((camera.fov * Math.PI) / 360));
      SPRITES.forEach((s) => {
        if (!s.minPx) return;
        const k = Math.max(1, s.minPx / ((s.h * pxPerUnit) / Math.max(s.dist, 0.1)));
        s.sp.scale.set((s.sp.scale.x / s.sp.scale.y) * s.h * k, s.h * k, 1);
      });
    }
    const a = reduceMotion ? 1 : Math.min(1, dt * 8);
    SPRITES.forEach((s) => {
      const m = s.sp.material, want = s.want == null ? 1 : s.want;
      m.opacity += (want - m.opacity) * a;
      if (Math.abs(want - m.opacity) < 0.01) m.opacity = want;
      s.sp.visible = m.opacity > 0.01;
    });
  }

  // Contact shadows: a soft dark blob under every block and rack, in one draw call. They ground the
  // blocks at night (no shadow map) and soften the hard shadow-map edge by day.
  function makeContactShadows(L) {
    const feet = L.items.filter((it) => it.shape !== 'slot').map((it) => [it.x, it.z, it.w * 1.35 + 0.8, it.d * 1.35 + 0.8])
      .concat(L.racks.map((r) => [r.x, r.z, r.w * 1.15 + 0.6, r.d * 1.8 + 0.6]));
    if (!feet.length) return;
    const g = geo(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2));
    const m = new THREE.MeshBasicMaterial({ map: blobTexture(), color: 0x000000, transparent: true, opacity: T.glow ? 0.6 : 0.32,
      depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
    const im = new THREE.InstancedMesh(g, m, feet.length);
    feet.forEach(([x, z, w, d], i) => im.setMatrixAt(i, tmpM.compose(tmpV.set(x, 0.012, z), tmpQ.identity(), tmpS.set(w, 1, d))));
    im.frustumCulled = false;
    im.renderOrder = 1;
    im.userData.contact = true;
    world.add(im);
  }

  // ── room shell: floor, walls, zones, signage, lights ────────────────────
  const SHELL = { walls: [], ceiling: [] };
  function updateShell() {
    const c = camera.position;
    SHELL.walls.forEach((w) => {
      const inside = (c.x - w.px) * w.nx + (c.z - w.pz) * w.nz > 0.3;
      w.objs.forEach((o) => { o.visible = inside; });
    });
    const below = c.y < room.wallH - 0.6;
    SHELL.ceiling.forEach((o) => { o.visible = below; });
  }
  function makeShell(L) {
    const { W, D: Dp } = L;
    const H = L.wallH;
    scene.background = new THREE.Color(T.bg);
    scene.fog = new THREE.Fog(T.bg, T.fogNear + Math.max(W, Dp) * 0.3, T.fogFar + Math.max(W, Dp));
    // floor
    const floor = mesh(new THREE.PlaneGeometry(W, Dp), mat(T.floor, { rough: 0.95 }), 0, 0, 0, world);
    floor.rotation.x = -Math.PI / 2;
    floor.castShadow = false;   // flat things only receive: each caster costs a draw call in the shadow pass
    floor.receiveShadow = true;
    floor.userData.floor = true;
    // the yard outside, so stepping the camera out never shows a void
    const yard = mesh(new THREE.PlaneGeometry(W + 260, Dp + 260), mat(T.glow ? 0x05080f : 0x8c887f, { rough: 1 }), 0, -0.03, 0, world);
    yard.rotation.x = -Math.PI / 2;
    yard.castShadow = false;
    if (T.glow) {
      const grid = new THREE.GridHelper(Math.max(W, Dp), Math.round(Math.max(W, Dp) / 3), 0x14203d, 0x0e1730);
      grid.position.y = 0.01;
      grid.scale.set(W / Math.max(W, Dp), 1, Dp / Math.max(W, Dp));
      world.add(grid);
    }
    // zones
    L.zones.forEach((Z, i) => {
      const zw = Z.x1 - Z.x0, zd = Z.z1 - Z.z0;
      const pl = mesh(new THREE.PlaneGeometry(zw - 1, zd - 1), mat(i % 2 ? T.floorAlt : T.floor, { rough: 0.95 }), (Z.x0 + Z.x1) / 2, 0.005, (Z.z0 + Z.z1) / 2, world);
      pl.rotation.x = -Math.PI / 2;
      pl.castShadow = false;
      pl.receiveShadow = true;
      // painted boundary lines
      const lineCol = T.paint;
      [[zw - 1, 0.18, (Z.x0 + Z.x1) / 2, Z.z1 - 0.5], [zw - 1, 0.18, (Z.x0 + Z.x1) / 2, Z.z0 + 0.5]].forEach(([lw, lt, lx, lz]) => {
        const s = mesh(new THREE.PlaneGeometry(lw, lt), mat(lineCol, { basic: true }), lx, 0.02, lz, world);
        s.rotation.x = -Math.PI / 2;
        s.castShadow = false;
      });
      // floor lettering
      const txt = Z.empty ? (Z.id === 'edge' ? 'No gateway or auth found' : 'Nothing here yet') : Z.name;
      const floorText = decal([txt], Math.min(zw * 0.45, Z.side ? zw * 0.8 : 22), { bg: false, ink: T.paintText, weight: 700, big: 90 });
      floorText.rotation.x = -Math.PI / 2;
      if (Z.side) { floorText.rotation.z = Math.PI / 2; floorText.position.set((Z.x0 + Z.x1) / 2, 0.03, Z.z1 - 8); }
      else floorText.position.set(Z.x0 + Math.min(zw * 0.45, 22) / 2 + 2, 0.03, Z.z1 - 2.2);
      world.add(floorText);
      // hanging sign
      if (!Z.side) {
        const sign = decal([Z.name, Z.empty && Z.id === 'edge' ? 'Requests reach the services directly' : Z.hint], 8, {
          bg: T.glow ? 'rgba(10,16,32,0.92)' : 'rgba(255,255,255,0.96)', stripe: T.glow ? '#ffb23f' : '#f2c230', align: 'left', big: 64,
        });
        sign.position.set(Z.x1 - 7, H - 2.2, (Z.z0 + Z.z1) / 2);
        world.add(sign);
        [-3, 3].forEach((dx) => box(0.03, 2.2 - (sign.geometry.parameters.height / 2), 0.03, T.beam, Z.x1 - 7 + dx, H - 2.2 + sign.geometry.parameters.height / 2, (Z.z0 + Z.z1) / 2, world, { noEdges: true }));
      }
    });
    // walls (front wall has a doorway)
    const wallM = mat(T.wall, { rough: 0.9, opacity: T.glow ? 0.92 : null });
    const t = 0.4, gap = 4.4;
    const walls = [
      [W, H, t, 0, -Dp / 2], [t, H, Dp, -W / 2, 0], [t, H, Dp, W / 2, 0],
      [(W - gap) / 2, H, t, -(W + gap) / 4, Dp / 2], [(W - gap) / 2, H, t, (W + gap) / 4, Dp / 2],
    ];
    // Each wall remembers which side is "inside" so the camera can see through
    // the walls it is standing behind.
    SHELL.walls = [
      { nx: 0, nz: 1, px: 0, pz: -Dp / 2, objs: [] }, { nx: 1, nz: 0, px: -W / 2, pz: 0, objs: [] },
      { nx: -1, nz: 0, px: W / 2, pz: 0, objs: [] }, { nx: 0, nz: -1, px: 0, pz: Dp / 2, objs: [] },
    ];
    walls.forEach(([ww, wh, wd, wx, wz], i) => {
      const side = SHELL.walls[Math.min(i, 3)];
      const m = mesh(new THREE.BoxGeometry(ww, wh, wd), wallM, wx, wh / 2, wz, world);
      m.castShadow = false;
      side.objs.push(m);
      const trim = T.glow
        ? mesh(new THREE.BoxGeometry(ww, 0.08, wd + 0.02), mat(T.wallLine, { basic: true }), wx, wh, wz, world)
        : mesh(new THREE.BoxGeometry(ww + 0.02, 0.5, wd + 0.02), mat(0x3a3f47), wx, 0.25, wz, world);
      trim.castShadow = false;
      side.objs.push(trim);
    });
    const lintel = box(gap + 0.6, 0.5, t + 0.1, T.glow ? 0xffb23f : 0xf2c230, 0, 3.6, Dp / 2, world, { emissive: 0.5 });
    lintel.castShadow = false;
    SHELL.walls[3].objs.push(lintel);
    // door sign
    const parentName = L.R ? (parentOf(L.R) ? N.get(parentOf(L.R)).name : 'the main floor') : null;
    const dsign = decal([L.R ? `Exit to ${parentName}` : `${D.project.name}`, L.R ? 'Walk through or press Q' : 'Wirehouse'], 6, {
      bg: T.glow ? 'rgba(10,16,32,0.95)' : 'rgba(255,255,255,0.97)', stripe: T.glow ? '#ffb23f' : '#f2c230', align: 'left', big: 60,
    });
    dsign.position.set(0, 5.2, Dp / 2 - 0.25);
    dsign.rotation.y = Math.PI;
    world.add(dsign);
    SHELL.walls[3].objs.push(dsign);
    SHELL.ceiling = [];
    // ceiling beams
    for (let z = -Dp / 2 + 4; z < Dp / 2; z += 9) {
      const b = box(W, 0.45, 0.35, T.beam, 0, H - 0.2, z, world, { noEdges: true });
      b.castShadow = false;
      SHELL.ceiling.push(b);
      if (!T.glow) {
        for (let x = -W / 2 + 8; x < W / 2 - 4; x += 14) {
          const lamp = mesh(new THREE.CylinderGeometry(0.7, 0.9, 0.25, 16), mat(0xfff8e6, { basic: true }), x, H - 0.75, z, world);
          lamp.castShadow = false;
          SHELL.ceiling.push(lamp);
        }
      } else {
        const strip = mesh(new THREE.BoxGeometry(W * 0.9, 0.05, 0.12), mat(0xffc888, { basic: true }), 0, H - 0.45, z, world);
        strip.castShadow = false;
        SHELL.ceiling.push(strip);
      }
    }
    // lights
    const hemi = new THREE.HemisphereLight(T.hemi[0], T.hemi[1], T.hemi[2]);
    world.add(hemi);
    const key = new THREE.DirectionalLight(T.key[0], T.key[1]);
    key.position.set(W * 0.25, 40, Dp * 0.35);
    if (T.shadows) {
      key.castShadow = true;
      key.shadow.mapSize.set(2048, 2048);
      const s = Math.max(W, Dp) * 0.6;
      Object.assign(key.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 1, far: 140 });
      key.shadow.bias = -0.0005;
    }
    world.add(key);
    world.add(key.target);
  }

  // ── pipes and particles ──────────────────────────────────────────────────
  let LINKS = [];
  let particles = null;
  const PART = [];
  const tmpM = new THREE.Matrix4();
  const tmpV = new THREE.Vector3();
  const tmpQ = new THREE.Quaternion();
  const tmpS = new THREE.Vector3();
  const tmpDir = new THREE.Vector3();
  const tmpQs = new THREE.Quaternion();
  const UP = new THREE.Vector3(0, 1, 0);

  function anchorOf(it) {
    if (!it) return null;
    if (it.shape === 'slot') return new THREE.Vector3(it.x, it.y + it.h + 0.05, it.z);
    return new THREE.Vector3(it.x, it.h * (it.shape === 'silo' ? 0.95 : 0.85), it.z);
  }

  function pipeCurve(A, B, lift) {
    const dist = A.distanceTo(B);
    const top = Math.max(A.y, B.y) + 2.2 + Math.min(dist * 0.14, 7) + (lift || 0);
    return new THREE.CubicBezierCurve3(A, new THREE.Vector3(A.x, top, A.z), new THREE.Vector3(B.x, top, B.z), B);
  }

  function linkKind(kinds) {
    const order = ['auth', 'data', 'publishes', 'calls', 'provisions', 'uses', 'imports', 'references', 'depends_on'];
    for (const k of order) if (kinds.has(k)) return k;
    return [...kinds][0] || 'uses';
  }

  function makePipe(A, B, info, lift) {
    const curve = pipeCurve(A, B, lift);
    const k = linkKind(info.kinds);
    const radius = clamp(0.05 + Math.log2(info.count + 1) * 0.025, 0.05, 0.2) * (k === 'imports' ? 0.75 : 1);
    const m = new THREE.MeshBasicMaterial({ color: edgeHex(k), transparent: true, opacity: 0.6, depthWrite: false });
    const tube = new THREE.Mesh(geo(new THREE.TubeGeometry(curve, 40, radius, 6, false)), m);
    tube.renderOrder = 2;
    tube.userData.pick = Object.assign({ type: 'link' }, info);
    PICK.push(tube);
    world.add(tube);
    const samples = curve.getSpacedPoints(64);
    const link = { tube, mat: m, kind: k, samples, len: curve.getLength(), info, active: true };
    LINKS.push(link);
    const nParticles = clamp(Math.round(1 + Math.log2(info.count + 1) * 1.2), 1, 6);
    for (let p = 0; p < nParticles; p++) PART.push({ link, t0: p / nParticles, speed: k === 'imports' ? 2.2 : 4.5 });
    return link;
  }

  function buildParticles() {
    if (!PART.length) return;
    // A short streak, wide at the head: it shows which way the connection runs at a glance.
    const g = geo(new THREE.CylinderGeometry(0.1, 0.025, 0.8, 6));
    const m = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95 * T.particle, depthWrite: false,
      blending: T.glow ? THREE.AdditiveBlending : THREE.NormalBlending });
    particles = new THREE.InstancedMesh(g, m, PART.length);
    particles.frustumCulled = false;
    particles.renderOrder = 3;
    const c = new THREE.Color();
    PART.forEach((p, i) => {
      c.setHex(edgeHex(p.link.kind));
      if (T.glow) c.lerp(new THREE.Color(0xffffff), 0.35);
      particles.setColorAt(i, c);
    });
    world.add(particles);
  }

  function updateParticles(time) {
    if (!particles) return;
    PART.forEach((p, i) => {
      const L = p.link;
      if (!L.active) {
        tmpS.set(0, 0, 0);
      } else {
        const f = (((p.t0 + (time * p.speed) / Math.max(L.len, 1)) % 1) + 1) % 1;
        const x = f * 64, k = Math.floor(x), r = x - k;
        const a = L.samples[k], b = L.samples[Math.min(k + 1, 64)];
        tmpV.set(a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r, a.z + (b.z - a.z) * r);
        tmpDir.subVectors(b, a);
        if (tmpDir.lengthSq() > 1e-10) tmpQs.setFromUnitVectors(UP, tmpDir.normalize());
        const s = L.focus ? 1.5 : 1;
        tmpS.set(s, s, s);
      }
      tmpM.compose(tmpV, tmpQs, tmpS);
      particles.setMatrixAt(i, tmpM);
    });
    particles.instanceMatrix.needsUpdate = true;
  }

  function makePortMesh(p) {
    const rep = N.get(p.rep);
    const g = new THREE.Group();
    g.position.set(p.x, p.y, p.z);
    g.rotation.y = p.ry;
    const col = kindHex(rep.kind);
    box(2.6, 1.7, 0.25, T.glow ? 0x121b30 : 0x4a525d, 0, -0.85, 0, g, { noEdges: true });
    box(2.6, 0.14, 0.3, col, 0, 0.78, 0, g, { emissive: 0.6, noEdges: true });
    const plate = decal([shortName(rep.name, 18), p.dir === 'out' ? 'Goes out to' : 'Comes in from'], 2.4, {
      bg: T.glow ? 'rgba(8,12,24,0.95)' : 'rgba(255,255,255,0.96)', stripe: css(col), align: 'left', big: 56,
    });
    plate.position.set(0, -0.15, 0.14);
    g.add(plate);
    const hatch = mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.3, 18), mat(col, { bright: true, emissive: 0.5 }), 0, -1.1, 0.2, g);
    hatch.rotation.x = Math.PI / 2;
    tagPick(g, { type: 'port', id: p.rep, port: p });
    world.add(g);
    // pipe anchor = hatch centre in world space
    const v = new THREE.Vector3(0, -1.1, 0.35);
    g.updateMatrixWorld();
    return g.localToWorld(v);
  }

  // ── avatar: worker in a hard hat ─────────────────────────────────────────
  let worker = null;
  const W8 = { pos: new THREE.Vector3(), vel: new THREE.Vector3(), vy: 0, yaw: 0, phase: 0, moving: 0 };

  // A soft round shadow, shared by every blob: drawn once on a 64 px canvas.
  let BLOB = null;
  function blobTexture() {
    if (BLOB) return BLOB;
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.55, 'rgba(255,255,255,0.45)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 64, 64);
    BLOB = new THREE.CanvasTexture(c);
    return BLOB;
  }

  function disposeTree(root) {
    root.traverse((o) => {
      if (o.geometry && !o.isSprite) o.geometry.dispose();   // sprites share one geometry inside three.js
      if (o.material) o.material.dispose();
    });
  }
  function buildWorker() {
    if (worker) { scene.remove(worker.root); disposeTree(worker.root); }
    const root = new THREE.Group();
    const skin = new THREE.MeshStandardMaterial({ color: 0xd9a77e, roughness: 0.8 });
    const pants = new THREE.MeshStandardMaterial({ color: 0x2c3e66, roughness: 0.85 });
    const shirt = new THREE.MeshStandardMaterial({ color: 0x5a6a80, roughness: 0.85 });
    const vest = new THREE.MeshStandardMaterial({ color: 0xff7a1a, roughness: 0.6, emissive: 0xff7a1a, emissiveIntensity: T.glow ? 0.35 : 0.05 });
    const reflect = new THREE.MeshStandardMaterial({ color: 0xe8edf2, emissive: 0xe8edf2, emissiveIntensity: T.glow ? 0.9 : 0.15 });
    const hat = new THREE.MeshStandardMaterial({ color: 0xffc400, roughness: 0.4, emissive: 0xffc400, emissiveIntensity: T.glow ? 0.25 : 0 });
    const boot = new THREE.MeshStandardMaterial({ color: 0x3b2a1e, roughness: 0.9 });
    // The worker moves every frame, so it casts no real shadow (that would redraw the shadow map
    // each frame); a soft blob on the floor grounds it instead.
    const part = (g, m, x, y, z, p) => { const me = new THREE.Mesh(g, m); me.position.set(x, y, z); p.add(me); return me; };
    const body = new THREE.Group();
    root.add(body);
    const legs = [-1, 1].map((s) => {
      const hip = new THREE.Group();
      hip.position.set(s * 0.15, 0.92, 0);
      part(new THREE.BoxGeometry(0.22, 0.78, 0.24), pants, 0, -0.4, 0, hip);
      part(new THREE.BoxGeometry(0.24, 0.16, 0.36), boot, 0, -0.84, 0.05, hip);
      body.add(hip);
      return hip;
    });
    part(new THREE.BoxGeometry(0.56, 0.62, 0.3), shirt, 0, 1.24, 0, body);
    part(new THREE.BoxGeometry(0.6, 0.5, 0.34), vest, 0, 1.27, 0, body);
    part(new THREE.BoxGeometry(0.61, 0.06, 0.35), reflect, 0, 1.18, 0, body);
    part(new THREE.BoxGeometry(0.61, 0.06, 0.35), reflect, 0, 1.36, 0, body);
    const arms = [-1, 1].map((s) => {
      const sh = new THREE.Group();
      sh.position.set(s * 0.38, 1.5, 0);
      part(new THREE.BoxGeometry(0.16, 0.56, 0.18), shirt, 0, -0.27, 0, sh);
      part(new THREE.SphereGeometry(0.09, 10, 8), skin, 0, -0.6, 0, sh);
      body.add(sh);
      return sh;
    });
    // clipboard in the left hand: this worker is taking inventory
    part(new THREE.BoxGeometry(0.03, 0.34, 0.26), new THREE.MeshStandardMaterial({ color: 0x8a6a45 }), 0.07, -0.62, 0.1, arms[0]);
    part(new THREE.BoxGeometry(0.035, 0.28, 0.2), new THREE.MeshStandardMaterial({ color: 0xf4f4f0 }), 0.08, -0.6, 0.1, arms[0]);
    part(new THREE.CylinderGeometry(0.08, 0.09, 0.1, 10), skin, 0, 1.6, 0, body);
    const head = part(new THREE.SphereGeometry(0.2, 18, 14), skin, 0, 1.82, 0, body);
    part(new THREE.SphereGeometry(0.235, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), hat, 0, 1.86, 0, body);
    part(new THREE.CylinderGeometry(0.32, 0.32, 0.03, 20), hat, 0, 1.86, 0.03, body);
    part(new THREE.BoxGeometry(0.07, 0.04, 0.05), new THREE.MeshStandardMaterial({ color: 0x222222 }), -0.07, 1.84, 0.18, body);
    part(new THREE.BoxGeometry(0.07, 0.04, 0.05), new THREE.MeshStandardMaterial({ color: 0x222222 }), 0.07, 1.84, 0.18, body);
    // a soft spot of light that follows the worker on the night shift
    let lamp = null;
    if (T.glow) {
      lamp = new THREE.PointLight(0xffd9a0, 0.9, 14, 2);
      lamp.position.set(0, 3.2, 0.4);
      root.add(lamp);
    }
    scene.add(root);
    const blob = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.MeshBasicMaterial({ map: blobTexture(), color: 0x000000, transparent: true, opacity: T.glow ? 0.55 : 0.4, depthWrite: false }));
    blob.rotation.x = -Math.PI / 2;
    blob.renderOrder = 1;
    root.add(blob);
    worker = { root, body, legs, arms, head, blob };
  }

  function animateWorker(dt, time) {
    const w = worker;
    const speed = Math.hypot(W8.vel.x, W8.vel.z);
    W8.moving += ((speed > 0.3 ? 1 : 0) - W8.moving) * Math.min(1, dt * 10);
    W8.phase += dt * (speed * 1.45);
    const swing = Math.sin(W8.phase) * 0.75 * W8.moving;
    w.legs[0].rotation.x = swing;
    w.legs[1].rotation.x = -swing;
    w.arms[0].rotation.x = -swing * 0.8 - 0.25 * (1 - W8.moving);
    w.arms[1].rotation.x = swing * 0.8;
    w.body.position.y = Math.abs(Math.sin(W8.phase)) * 0.06 * W8.moving + (1 - W8.moving) * Math.sin(time * 1.8) * 0.01;
    w.root.position.copy(W8.pos);
    // the blob stays on the floor and shrinks as the worker jumps
    w.blob.position.y = 0.04 - W8.pos.y;
    w.blob.scale.setScalar(Math.max(0.4, 1 - W8.pos.y * 0.25));
    let dy = W8.yaw - w.root.rotation.y;
    dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    w.root.rotation.y += dy * Math.min(1, dt * 12);
  }

  // ── room state ───────────────────────────────────────────────────────────
  let room = null;          // current layout
  let itemsById = new Map();
  let OBST = [];
  let selected = null;      // {type, id} or link info
  let hovered = null;
  let selBox = null, hovBox = null;

  function clearWorld() {
    const shared = new Set([...MATS.values(), ...lineMats.values()]);
    world.traverse((o) => {
      // Textures are cached by text (see TEX), so only the per-object materials go here.
      if ((o.isSprite || o.isMesh || o.isLine) && o.material && !shared.has(o.material)) o.material.dispose();
      if (o.isLine && o.geometry) o.geometry.dispose();          // grid and selection boxes
      if (o.isLight && o.dispose) o.dispose();                   // frees the 2048px shadow map
      if (o.isInstancedMesh && o !== particles) o.dispose();     // frees the per-instance buffers
    });
    texRoom++;
    TEX.forEach((t, k) => { if (t.userData.used < texRoom - TEX_ROOMS) { t.dispose(); TEX.delete(k); } });
    GEOS.forEach((g) => g.dispose());
    GEOS = [];
    markObjs.forEach((o) => o.geometry && o.geometry.dispose());   // trace rings own their geometry
    markObjs = [];
    while (world.children.length) world.remove(world.children[0]);
    ANIM.length = 0;
    PICK = [];
    SPRITES = [];
    LINKS = [];
    PART.length = 0;
    if (particles) { particles.dispose && particles.dispose(); particles = null; }
    selBox = hovBox = null;
  }

  function buildRoom(R) {
    clearWorld();
    room = R ? layoutRoom(R) : layoutRoot();
    itemsById = new Map(room.items.map((it) => [it.id, it]));
    makeShell(room);
    room.racks.forEach(makeRack);
    room.items.forEach((it) => (it.shape === 'slot' ? makeSlot(it) : makeBlock(it)));
    flushInstances();
    makeContactShadows(room);
    OBST = room.items.filter((it) => it.shape !== 'slot').map((it) => ({ x0: it.x - it.w / 2, x1: it.x + it.w / 2, z0: it.z - it.d / 2, z1: it.z + it.d / 2 }))
      .concat(room.racks.map((r) => ({ x0: r.x - r.w / 2, x1: r.x + r.w / 2, z0: r.z - r.d / 2, z1: r.z + r.d / 2 })));
    const { inner, ports } = roomLinks(R);
    room.links = inner;
    const pairCount = new Map();
    inner.forEach((Lk) => {
      const A = anchorOf(itemsById.get(Lk.a)), B = anchorOf(itemsById.get(Lk.b));
      if (!A || !B) return;
      const pk = [Lk.a, Lk.b].sort().join('|');
      const n = pairCount.get(pk) || 0;
      pairCount.set(pk, n + 1);
      makePipe(A, B, Lk, n * 1.1);
    });
    room.ports = placePorts(room, ports.sort((a, b) => b.count - a.count).slice(0, 40));
    room.ports.forEach((p) => {
      const P = makePortMesh(p);
      p.inners.forEach((info) => {
        const it = itemsById.get(info.id);
        const B = anchorOf(it);
        if (!B) return;
        const A = p.dir === 'out' ? B : P;
        const Bv = p.dir === 'out' ? P : B;
        makePipe(A, Bv, Object.assign({ a: p.dir === 'out' ? info.id : p.rep, b: p.dir === 'out' ? p.rep : info.id, port: p }, info), 0.6);
      });
    });
    buildParticles();
    if (renderer) renderer.shadowMap.enabled = !!T.shadows;
    refreshShadows();   // the scene is static apart from small animated parts that cast no shadow
    BUILD_HOOKS.forEach((f) => f());
    applyFocus();
    drawCrumbs();
    if (planOn) drawPlan();
  }
  const BUILD_HOOKS = [];   // later sections: () => void after a room is built
  const FILTER_HOOKS = [];  // later sections: () => void when the pipe filter changes

  // ── focus and highlight ──────────────────────────────────────────────────
  function focusNodeId() {
    const h = hovered && hovered.type !== 'link' ? hovered.id : null;
    const s = selected && selected.type !== 'link' ? selected.id : null;
    return h || s;
  }
  function boundsOf(id) {
    const it = itemsById.get(id);
    if (it) {
      const y0 = it.shape === 'slot' ? it.y : 0;
      return new THREE.Box3(new THREE.Vector3(it.x - it.w / 2 - 0.15, y0 - 0.05, it.z - it.d / 2 - 0.15), new THREE.Vector3(it.x + it.w / 2 + 0.15, y0 + it.h + 0.15, it.z + it.d / 2 + 0.15));
    }
    const p = room && room.ports.find((q) => q.rep === id);
    if (p) return new THREE.Box3().setFromCenterAndSize(new THREE.Vector3(p.x, p.y - 0.4, p.z), new THREE.Vector3(Math.abs(Math.cos(p.ry)) * 2.8 + 0.4, 2.2, Math.abs(Math.sin(p.ry)) * 2.8 + 0.4));
    return null;
  }
  function setBox(which, id, color) {
    const old = which === 'sel' ? selBox : hovBox;
    if (old) { world.remove(old); old.geometry.dispose(); old.material.dispose(); }
    let b = null;
    const bounds = id ? boundsOf(id) : null;
    if (bounds) {
      b = new THREE.Box3Helper(bounds, color);
      b.material.depthTest = false;
      b.renderOrder = 9;
      world.add(b);
    }
    if (which === 'sel') selBox = b; else hovBox = b;
  }
  function applyFocus() {
    const lit = litLinks();   // a trace, route or tour step lights its own pipes; hovering still peeks
    const f = lit ? (hovered && hovered.type !== 'link' ? hovered.id : null) : focusNodeId();
    const visible = f && (itemsById.has(f) || (room && room.ports.some((p) => p.rep === f)));
    const selLink = selected && selected.type === 'link' ? selected.info : null;
    // Busy rooms start quieter; selecting something brings its pipes forward.
    const base = (T.glow ? 0.55 : 0.72) * clamp(40 / Math.max(LINKS.length, 1), 0.35, 1);
    LINKS.forEach((L) => {
      let on = true, strong = false;
      if (selLink) { on = L.info === selLink; strong = on; }
      else if (visible) { on = L.info.a === f || L.info.b === f; strong = on; }
      else if (lit) { on = lit(L.info); strong = on; }
      const shown = shownKinds(L.info.kinds);
      L.tube.visible = shown;
      L.active = on && shown;
      L.focus = strong && shown;
      L.mat.opacity = strong ? 0.98 : on ? base : 0.06;
    });
    setBox('sel', selected && selected.type !== 'link' ? selected.id : null, T.glow ? 0xffb23f : 0x1f6fd1);
    setBox('hov', hovered && hovered.type !== 'link' && (!selected || hovered.id !== selected.id) ? hovered.id : null, T.glow ? 0x9fb3d9 : 0x5a6474);
    if (planOn) planFocus();
  }

  // ── camera, input, movement ──────────────────────────────────────────────
  const cam = { yaw: 0, pitch: 0.5, dist: 17, target: new THREE.Vector3(), follow: false };
  const keys = new Set();
  const canvas = renderer ? renderer.domElement : null;
  const ptr = { x: 0, y: 0, down: false, sx: 0, sy: 0, drag: false, moved: false, inside: false };
  const touches = new Map();   // pointerId -> {x, y} for pinch zoom
  let pinch = 0;
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

  function pickAt(cx, cy) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const hits = raycaster.intersectObjects(PICK, false);
    for (const h of hits) {
      const info = h.object.userData.pick;
      if (!info) continue;
      if (info.type === 'link') {
        const L = LINKS.find((x) => x.tube === h.object);
        if (L && !L.active) continue;
      }
      return { info, point: h.point };
    }
    const p = new THREE.Vector3();
    return raycaster.ray.intersectPlane(floorPlane, p) ? { info: null, point: p } : null;
  }

  if (canvas) {
    const spread = () => { const [a, b] = [...touches.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
    canvas.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'touch') {
        touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touches.size === 2) { pinch = spread(); ptr.drag = true; return; }   // a pinch is never a click
      }
      ptr.down = true; ptr.drag = false; ptr.sx = e.clientX; ptr.sy = e.clientY; ptr.x = e.clientX; ptr.y = e.clientY;
      canvas.setPointerCapture(e.pointerId);
      canvas.focus({ preventScroll: true });
    });
    canvas.addEventListener('pointermove', (e) => {
      if (touches.has(e.pointerId)) {
        touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touches.size === 2) {
          const d = spread();
          if (pinch > 0 && d > 0) cam.dist = clamp(cam.dist * (pinch / d), 3.2, 70);
          pinch = d;
          return;
        }
      }
      const dx = e.clientX - ptr.x, dy = e.clientY - ptr.y;
      ptr.x = e.clientX; ptr.y = e.clientY; ptr.moved = true; ptr.inside = true;
      if (!ptr.down) return;
      if (!ptr.drag && Math.hypot(e.clientX - ptr.sx, e.clientY - ptr.sy) > 5) { ptr.drag = true; canvas.classList.add('dragging'); }
      if (ptr.drag) {
        cam.yaw -= dx * 0.0055;
        cam.pitch = clamp(cam.pitch + dy * 0.004, 0.05, 1.35);
        cam.follow = false;
      }
    });
    const release = (e, click) => {
      canvas.classList.remove('dragging');
      if (click && ptr.down && !ptr.drag && touches.size < 2) onClick(e.clientX, e.clientY);
      touches.delete(e.pointerId);
      if (touches.size < 2) pinch = 0;
      if (touches.size === 1) { const t = touches.values().next().value; ptr.x = t.x; ptr.y = t.y; }   // the finger left keeps turning, without a jump
      if (!touches.size) ptr.down = false;
    };
    canvas.addEventListener('pointerup', (e) => release(e, true));
    canvas.addEventListener('pointercancel', (e) => release(e, false));
    canvas.addEventListener('pointerleave', () => { ptr.inside = false; if (hovered) { hovered = null; applyFocus(); } $('#tooltip').hidden = true; });
    canvas.addEventListener('dblclick', (e) => {
      const hit = pickAt(e.clientX, e.clientY);
      if (hit && hit.info && hit.info.type === 'node' && enterable(hit.info.id)) enterBlock(hit.info.id);
      else if (hit && hit.info && hit.info.type === 'port') focusNode(hit.info.id);
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      cam.dist = clamp(cam.dist * (1 + e.deltaY * 0.0011), 3.2, 70);
    }, { passive: false });
  }

  function onClick(cx, cy) {
    const hit = pickAt(cx, cy);
    if (!hit) return;
    if (hit.info) {
      if (hit.info.type === 'link') selectLink(hit.info);
      else if (hit.info.type === 'port') select(hit.info.id, { port: hit.info.port });
      else if (selected && selected.id === hit.info.id) travelTo(hit.info.id);
      else select(hit.info.id);
    } else {
      travelToPoint(hit.point.x, hit.point.z);
    }
  }

  function typing(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable); }
  // Focus on a button, link or focusable plan block: Space, Enter, arrows and Backspace
  // keep their normal meaning there instead of driving the worker.
  function onControl(e) {
    const t = e.target;
    return !!(t && t !== canvas && t.closest && t.closest('button, a, select, [role="button"], [role="option"], [tabindex]'));
  }

  // Escape peels back one layer at a time, most recent kind of thing first.
  const ESC = [];
  function onEscape(prio, active, close) { ESC.push({ prio, active, close }); ESC.sort((a, b) => a.prio - b.prio); }
  function escapeOnce() {
    for (const L of ESC) if (L.active()) { L.close(); return true; }
    return false;
  }
  onEscape(10, () => !$('#welcome').hidden, () => closeWelcome());
  onEscape(35, () => !!W8.path, () => { W8.path = null; arrival = null; });
  onEscape(45, () => !panel.hidden, () => closePanel());

  window.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    const findKey = k === 'k' && (e.ctrlKey || e.metaKey);
    if (typing(e) || e.altKey || ((e.ctrlKey || e.metaKey) && !findKey)) return;
    if (!$('#welcome').hidden) {
      if (k === 'escape' || (k === 'enter' && !onControl(e))) { e.preventDefault(); closeWelcome(); }
      else if (k === 'tab') {   // keep focus inside the card, moving through its buttons
        e.preventDefault();
        const f = [...$('#welcome').querySelectorAll('button, a[href]')].filter((b) => !b.hidden);
        const i = f.indexOf(document.activeElement);
        (f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length] || $('#welcomeGo')).focus();
      }
      return;
    }
    if (k === 'escape') { if (escapeOnce()) e.preventDefault(); return; }
    if (!$('#erd').hidden) return;   // the schema diagram is modal: nothing behind it moves
    const ctl = onControl(e);
    if (ctl && [' ', 'enter', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'backspace', 'home', 'end'].includes(k)) return;
    if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift'].includes(k)) {
      if (planOn) return;
      keys.add(k);
      if (k.startsWith('arrow')) e.preventDefault();
      return;
    }
    if (k === ' ') { e.preventDefault(); if (keySpace()) return; if (W8.pos.y <= 0.001) W8.vy = 6.5; return; }
    if (k === '/' || findKey) { e.preventDefault(); $('#search').focus(); $('#search').select(); return; }
    if (k === 'p') { setPlan(!planOn); return; }
    if (k === 'e' || k === 'enter') { if (!planOn) interact(); return; }   // the worker is hidden on the floor plan
    if (k === 'q' || k === 'backspace') { e.preventDefault(); exitRoom(); return; }
    if (k === 't') { setTheme(themeId === 'night' ? 'day' : 'night'); return; }
    if (k === 'h' || k === '?') { openWelcome(); return; }
    if (k === 'f' && selected && selected.type !== 'link') { travelTo(selected.id); return; }
    if (KEYS[k]) { e.preventDefault(); KEYS[k](); }
  });
  // Single-letter shortcuts added by later sections (trace, tours, export).
  const KEYS = {};
  let keySpace = () => false;
  window.addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
  window.addEventListener('blur', () => keys.clear());

  function collide(p) {
    const r = 0.42;
    for (let pass = 0; pass < 2; pass++) for (const o of OBST) {
      const cx = clamp(p.x, o.x0, o.x1), cz = clamp(p.z, o.z0, o.z1);
      const dx = p.x - cx, dz = p.z - cz, d2 = dx * dx + dz * dz;
      if (d2 >= r * r) continue;
      if (d2 > 1e-8) { const d = Math.sqrt(d2); p.x = cx + (dx / d) * r; p.z = cz + (dz / d) * r; }
      else {
        const opts = [[p.x - o.x0 + r, -1, 0], [o.x1 - p.x + r, 1, 0], [p.z - o.z0 + r, 0, -1], [o.z1 - p.z + r, 0, 1]].sort((a, b) => a[0] - b[0]);
        p.x += opts[0][1] * opts[0][0]; p.z += opts[0][2] * opts[0][0];
      }
    }
    const hw = room.W / 2 - 0.65, hd = room.D / 2 - 0.65;
    p.x = clamp(p.x, -hw, hw);
    const inDoor = Math.abs(p.x) < 1.7;
    p.z = clamp(p.z, -hd, inDoor && room.R ? room.D / 2 + 0.6 : hd);
  }

  function updateMovement(dt) {
    const f = (keys.has('w') || keys.has('arrowup') ? 1 : 0) - (keys.has('s') || keys.has('arrowdown') ? 1 : 0);
    const s = (keys.has('d') || keys.has('arrowright') ? 1 : 0) - (keys.has('a') || keys.has('arrowleft') ? 1 : 0);
    const run = keys.has('shift');
    let dx = 0, dz = 0, speed = run ? 11 : 6;
    if (f || s) {
      W8.path = null;
      const fx = -Math.sin(cam.yaw), fz = -Math.cos(cam.yaw);
      const rx = Math.cos(cam.yaw), rz = -Math.sin(cam.yaw);
      dx = fx * f + rx * s; dz = fz * f + rz * s;
      const l = Math.hypot(dx, dz); dx /= l; dz /= l;
    } else if (W8.path && W8.path.length) {
      const wp = W8.path[0];
      const vx = wp.x - W8.pos.x, vz = wp.z - W8.pos.z, l = Math.hypot(vx, vz);
      if (l < 0.35) { W8.path.shift(); if (!W8.path.length) arrive(); }
      else { dx = vx / l; dz = vz / l; speed = l > 6 ? 10 : 7; }
      cam.follow = true;
    }
    const tvx = dx * speed, tvz = dz * speed;
    const a = Math.min(1, dt * 12);
    W8.vel.x += (tvx - W8.vel.x) * a;
    W8.vel.z += (tvz - W8.vel.z) * a;
    W8.pos.x += W8.vel.x * dt;
    W8.pos.z += W8.vel.z * dt;
    W8.vy -= 22 * dt;
    W8.pos.y = Math.max(0, W8.pos.y + W8.vy * dt);
    if (W8.pos.y === 0) W8.vy = Math.max(0, W8.vy);
    collide(W8.pos);
    if (Math.hypot(W8.vel.x, W8.vel.z) > 0.4) W8.yaw = Math.atan2(W8.vel.x, W8.vel.z);
    if (room.R && W8.pos.z > room.D / 2 - 0.1 && !transitioning) exitRoom();
  }

  function updateCamera(dt) {
    if (cam.follow && W8.path) {
      let d = (W8.yaw + Math.PI) - cam.yaw;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      cam.yaw += d * Math.min(1, dt * 1.6);
    }
    const tgt = tmpV.set(W8.pos.x, W8.pos.y + 1.55, W8.pos.z);
    cam.target.lerp(tgt, Math.min(1, dt * 10));
    const cp = Math.cos(cam.pitch);
    let x = cam.target.x + Math.sin(cam.yaw) * cp * cam.dist;
    let y = cam.target.y + Math.sin(cam.pitch) * cam.dist;
    let z = cam.target.z + Math.cos(cam.yaw) * cp * cam.dist;
    const out = 30; // the camera may step outside; walls behind it get hidden
    x = clamp(x, -room.W / 2 - out, room.W / 2 + out);
    z = clamp(z, -room.D / 2 - out, room.D / 2 + out);
    y = clamp(y, 0.6, 60);
    camera.position.set(x, y, z);
    camera.lookAt(cam.target);
  }

  // ── pathfinding (A* on a coarse grid) ────────────────────────────────────
  function grid() {
    const cs = 0.5, pad = 0.5;
    const gw = Math.ceil(room.W / cs), gd = Math.ceil(room.D / cs);
    const blocked = new Uint8Array(gw * gd);
    const toI = (x, z) => [clamp(Math.floor((x + room.W / 2) / cs), 0, gw - 1), clamp(Math.floor((z + room.D / 2) / cs), 0, gd - 1)];
    for (let i = 0; i < gw; i++) for (let j = 0; j < gd; j++) {
      const x = -room.W / 2 + (i + 0.5) * cs, z = -room.D / 2 + (j + 0.5) * cs;
      if (Math.abs(x) > room.W / 2 - 0.7 || Math.abs(z) > room.D / 2 - 0.7) { blocked[j * gw + i] = 1; continue; }
      for (const o of OBST) if (x > o.x0 - pad && x < o.x1 + pad && z > o.z0 - pad && z < o.z1 + pad) { blocked[j * gw + i] = 1; break; }
    }
    return { cs, gw, gd, blocked, toI, toW: (i, j) => ({ x: -room.W / 2 + (i + 0.5) * cs, z: -room.D / 2 + (j + 0.5) * cs }) };
  }
  function nearestFree(G, i, j) {
    if (!G.blocked[j * G.gw + i]) return [i, j];
    for (let r = 1; r < 60; r++) for (let di = -r; di <= r; di++) for (let dj = -r; dj <= r; dj++) {
      if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
      const a = i + di, b = j + dj;
      if (a >= 0 && b >= 0 && a < G.gw && b < G.gd && !G.blocked[b * G.gw + a]) return [a, b];
    }
    return null;
  }
  function findPath(x0, z0, x1, z1) {
    const G = grid();
    const s = nearestFree(G, ...G.toI(x0, z0)), t = nearestFree(G, ...G.toI(x1, z1));
    if (!s || !t) return null;
    const idx = (i, j) => j * G.gw + i;
    const gS = new Float32Array(G.gw * G.gd).fill(Infinity);
    const from = new Int32Array(G.gw * G.gd).fill(-1);
    const closed = new Uint8Array(G.gw * G.gd);
    const heap = [];
    const push = (f, k) => { heap.push([f, k]); let c = heap.length - 1; while (c > 0) { const p = (c - 1) >> 1; if (heap[p][0] <= heap[c][0]) break; [heap[p], heap[c]] = [heap[c], heap[p]]; c = p; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let c = 0; for (;;) { const l = 2 * c + 1, r = l + 1; let m = c; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === c) break; [heap[m], heap[c]] = [heap[c], heap[m]]; c = m; } } return top; };
    const h = (i, j) => { const dx = Math.abs(i - t[0]), dy = Math.abs(j - t[1]); return Math.max(dx, dy) + 0.414 * Math.min(dx, dy); };
    gS[idx(...s)] = 0;
    push(h(...s), idx(...s));
    const goal = idx(...t);
    let found = false, guard = 0;
    while (heap.length && guard++ < 300000) {
      const [, k] = pop();
      if (closed[k]) continue;
      closed[k] = 1;
      if (k === goal) { found = true; break; }
      const i = k % G.gw, j = (k / G.gw) | 0;
      for (let di = -1; di <= 1; di++) for (let dj = -1; dj <= 1; dj++) {
        if (!di && !dj) continue;
        const a = i + di, b = j + dj;
        if (a < 0 || b < 0 || a >= G.gw || b >= G.gd) continue;
        const nk = idx(a, b);
        if (G.blocked[nk] || closed[nk]) continue;
        if (di && dj && (G.blocked[idx(i + di, j)] || G.blocked[idx(i, j + dj)])) continue;
        const g = gS[k] + (di && dj ? 1.414 : 1);
        if (g < gS[nk]) { gS[nk] = g; from[nk] = k; push(g + h(a, b), nk); }
      }
    }
    if (!found) return null;
    const cells = [];
    for (let k = goal; k !== -1; k = from[k]) cells.push(k);
    cells.reverse();
    const pts = cells.map((k) => G.toW(k % G.gw, (k / G.gw) | 0));
    // string-pull: keep only the corners we cannot see past
    const clear = (A, B) => {
      const n = Math.ceil(Math.hypot(B.x - A.x, B.z - A.z) / (G.cs * 0.5));
      for (let q = 1; q < n; q++) {
        const [i, j] = G.toI(A.x + ((B.x - A.x) * q) / n, A.z + ((B.z - A.z) * q) / n);
        if (G.blocked[idx(i, j)]) return false;
      }
      return true;
    };
    const out = [];
    let anchor = { x: x0, z: z0 };
    for (let q = 1; q < pts.length; q++) {
      if (!clear(anchor, pts[q])) { out.push(pts[q - 1]); anchor = pts[q - 1]; }
    }
    out.push(pts[pts.length - 1]);
    return out;
  }

  let arrival = null;
  function arrive() {
    W8.path = null;
    const a = arrival;
    arrival = null;
    if (a && a.face) W8.yaw = Math.atan2(a.face.x - W8.pos.x, a.face.z - W8.pos.z);
    if (a && a.then) a.then();
  }
  function travelToPoint(x, z, then, face) {
    const path = findPath(W8.pos.x, W8.pos.z, x, z);
    arrival = { then, face };
    if (!path) { W8.pos.set(x, 0, z); collide(W8.pos); arrive(); return; }
    W8.path = path;
  }
  function standPoint(id) {
    const it = itemsById.get(id);
    if (it) {
      const z = it.shape === 'slot' ? it.rack.z + it.rack.d / 2 + 1.3 : it.z + it.d / 2 + 1.6;
      return { x: it.x, z, face: { x: it.x, z: it.z } };
    }
    const p = room.ports.find((q) => q.rep === id);
    if (p) {
      const nx = Math.sin(p.ry), nz = Math.cos(p.ry);
      return { x: p.x + nx * 2.4, z: p.z + nz * 2.4, face: { x: p.x, z: p.z } };
    }
    return null;
  }
  function travelTo(id, then) {
    const sp = standPoint(id);
    if (!sp) { if (then) then(); return; }
    travelToPoint(sp.x, sp.z, then, sp.face);
  }

  // ── rooms and navigation ─────────────────────────────────────────────────
  let transitioning = false;
  function placeAvatar(from) {
    const sp = from ? standPoint(from) : null;
    if (sp) W8.pos.set(sp.x, 0, sp.z);
    else W8.pos.set(0, 0, room.D / 2 - (room.R ? 5 : 7));
    W8.yaw = Math.PI;
    collide(W8.pos);
    W8.vel.set(0, 0, 0);
    W8.path = null;
    arrival = null;
    cam.yaw = 0;
    cam.pitch = 0.5;
    cam.target.set(W8.pos.x, 1.55, W8.pos.z);
    if (worker) worker.root.rotation.y = W8.yaw;
  }
  // Room changes asked for during the fade run right after it, in order: each may carry a `then`
  // (applyHash unfreezes the address bar in one), so none may be dropped. All but the last run instantly.
  const pendingRooms = [];
  function goRoom(R, opts) {
    opts = opts || {};
    if (transitioning) { pendingRooms.push([R, opts]); return; }
    const doIt = () => {
      hovered = null;
      if (selected && selected.type === 'link') { selected = null; closePanel(true); }
      buildRoom(R);
      placeAvatar(opts.from);
      planView = null;
      if (planOn) drawPlan();
      if (opts.then) opts.then();
      syncHash();
    };
    if (!opts.instant && !reduceMotion && !planOn) {
      transitioning = true;
      $('#fade').classList.add('on');
      setTimeout(() => {
        doIt();
        $('#fade').classList.remove('on');
        setTimeout(() => {
          transitioning = false;
          while (pendingRooms.length > 1) { const [r, o] = pendingRooms.shift(); goRoom(r, Object.assign({}, o, { instant: true })); }
          if (pendingRooms.length) { const [r, o] = pendingRooms.shift(); goRoom(r, o); }
        }, 250);
      }, 260);
    } else doIt();
  }
  function enterBlock(id) { if (enterable(id)) goRoom(id); }
  function exitRoom() { if (room && room.R) goRoom(parentOf(room.R), { from: room.R }); }
  function interact() {
    const near = nearest();
    if (!near) return;
    if (enterable(near.id)) enterBlock(near.id); else select(near.id);
  }
  function focusNode(id, opts) {
    opts = opts || {};
    if (!N.has(id)) return;
    const R = parentOf(id);
    const go = () => { select(id); if (!planOn) travelTo(id, opts.enter ? () => enterBlock(id) : null); };
    if (room && room.R === R) go();
    else goRoom(R, { then: go });
  }
  // ── links into a view (URL hash) ─────────────────────────────────────────
  // #room=<id>&focus=<id>&reach=up|down&route=<from>~<to>&tour=<id>&stop=<n>&plan=1
  const encId = (id) => encodeURIComponent(id).replace(/~/g, '%7E');
  const HASH_PARTS = [];   // later sections add () => 'key=value' | null
  const HASH_APPLY = [];   // later sections add (state) => void, run once the room is ready
  let hashFrozen = false;
  function syncHash() {
    if (hashFrozen) return;
    const p = [];
    if (room && room.R) p.push('room=' + encId(room.R));
    if (selected && selected.type !== 'link') p.push('focus=' + encId(selected.id));
    HASH_PARTS.forEach((f) => { const s = f(); if (s) p.push(s); });
    if (planOn) p.push('plan=1');
    try { history.replaceState(null, '', p.length ? '#' + p.join('&') : location.pathname + location.search); } catch (e) { /* file:// may refuse */ }
  }
  function parseHash(h) {
    const out = {};
    const dec = (v) => { try { return decodeURIComponent(v); } catch (e) { return ''; } };
    String(h || '').replace(/^#/, '').split('&').forEach((kv) => {
      const i = kv.indexOf('=');
      if (i > 0) out[kv.slice(0, i)] = kv.slice(i + 1); else if (kv) out[kv] = '1';
    });
    for (const k of Object.keys(out)) out[k] = k === 'route' || k === 'trace' ? out[k].split('~').map(dec) : dec(out[k]);
    return out;
  }
  function applyHash(h) {
    const focus = h.focus && N.has(h.focus) ? h.focus : null;
    const R = h.room && N.has(h.room) && enterable(h.room) ? h.room : focus ? parentOf(focus) : ROOT;
    hashFrozen = true;
    if ((h.plan === '1') !== planOn) setPlan(h.plan === '1');
    goRoom(R, {
      instant: true,
      then: () => {
        if (focus) {
          const port = room.ports.find((p) => p.rep === focus);
          select(focus, port && !itemsById.has(focus) ? { port } : {});
        } else if (selected) closePanel();
        HASH_APPLY.forEach((f) => f(h));
        hashFrozen = false;
        syncHash();
      },
    });
  }
  window.addEventListener('hashchange', () => applyHash(parseHash(location.hash)));
  function copyLink() {
    syncHash();
    const url = location.href;
    const done = () => toast('Link copied: it opens this exact view');
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, () => toast(url));
    else toast(url);
  }

  function nearest() {
    if (!room) return null;
    let best = null, bd = 2.2;
    for (const it of room.items) {
      const z0 = it.shape === 'slot' ? it.rack.z - it.rack.d / 2 : it.z - it.d / 2;
      const z1 = it.shape === 'slot' ? it.rack.z + it.rack.d / 2 : it.z + it.d / 2;
      const dx = Math.max(it.x - it.w / 2 - W8.pos.x, 0, W8.pos.x - it.x - it.w / 2);
      const dz = Math.max(z0 - W8.pos.z, 0, W8.pos.z - z1);
      let d = Math.hypot(dx, dz);
      if (it.shape === 'slot') d += Math.abs(W8.pos.x - it.x) * 0.5;
      if (d < bd) { bd = d; best = it; }
    }
    return best;
  }
  function promptHtml() {
    if (planOn || transitioning || !$('#bar').hidden) return '';
    if (room.R && W8.pos.z > room.D / 2 - 3 && Math.abs(W8.pos.x) < 2.5) {
      return `Keep walking to go back to ${esc(parentOf(room.R) ? N.get(parentOf(room.R)).name : 'the main floor')}`;
    }
    const it = nearest();
    if (!it) return '';
    const n = N.get(it.id);
    return enterable(n.id) ? `<kbd>E</kbd> Walk into ${esc(n.name)}` : `<kbd>E</kbd> Inspect ${esc(n.name)}`;
  }
  let promptLast = null;
  function updatePrompt() {
    // runs several times a second, and rewriting the same text still restyles the page
    const el = $('#prompt'), h = promptHtml();
    if (h !== promptLast) { promptLast = h; if (h) el.innerHTML = h; }
    if (el.hidden !== !h) el.hidden = !h;
  }

  // ── info panel ───────────────────────────────────────────────────────────
  const panel = $('#panel'), body = $('#panelBody');
  function closePanel(silent) {
    panel.hidden = true;
    if (!silent) { selected = null; applyFocus(); syncHash(); }
  }
  $('#panelClose').addEventListener('click', () => closePanel());

  // Source links: the code host at the scanned commit (works for anyone the file is
  // shared with) and VS Code (works only on the machine that ran the scan).
  const REPO = D.repo || null;
  const DIRTY = new Set((REPO && REPO.dirty) || []);
  function vscodeLink(file, line) {
    const root = String(D.project.root || '').replace(/\\/g, '/');
    return 'vscode://file/' + encodeURI(root + '/' + file) + (line ? ':' + line : '');
  }
  function webLink(file, line) {
    if (!REPO || !REPO.web || !file) return null;
    const p = ((REPO.prefix ? REPO.prefix + '/' : '') + file).split('/').map(encodeURIComponent).join('/');
    const r = REPO.revision, base = REPO.web;
    const href = {
      github: `${base}/blob/${r}/${p}${line ? '#L' + line : ''}`,
      gitlab: `${base}/-/blob/${r}/${p}${line ? '#L' + line : ''}`,
      bitbucket: `${base}/src/${r}/${p}${line ? '#lines-' + line : ''}`,
      azure: `${base}?path=/${p}&version=GC${r}${line ? `&line=${line}&lineEnd=${line + 1}&lineStartColumn=1&lineEndColumn=1&lineStyle=plain&_a=contents` : ''}`,
    }[REPO.provider];
    if (!href) return null;
    let title = `View on ${REPO.host_name} at commit ${REPO.short}`, warn = false;
    if (DIRTY.has(file)) { title = `This file has local changes that are not in commit ${REPO.short}, so ${REPO.host_name} shows the older version`; warn = true; }
    else if (REPO.dirty_complete === false) { title = `Wirehouse could not list every file with local changes, so this file may differ from commit ${REPO.short}`; warn = true; }
    else if (REPO.pushed === false) { title = `Commit ${REPO.short} is not on ${REPO.host_name} yet, so this link may not open until it is pushed`; warn = true; }
    return { href, title, warn };
  }
  function srcLinks(file, line) {
    const w = webLink(file, line);
    return `<span class="links">${w ? `<a href="${esc(w.href)}" target="_blank" rel="noopener" title="${esc(w.title)}"${w.warn ? ' class="warn"' : ''}>${esc(REPO.host_name)}${w.warn ? ' *' : ''}</a>` : ''}` +
      (D.project.root ? `<a href="${esc(vscodeLink(file, line))}" title="Open in VS Code (only on the computer that ran the scan)">VS Code</a>` : '') + '</span>';
  }
  function toast(msg, ms) {
    const t = $('#toast');
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, ms || 1400);
  }
  function copy(text) {
    const done = () => toast('Copied ' + text);
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => toast(text));
    else toast(text);
  }

  function descendantsWhere(id, pred, cap) {
    const out = [], stack = [id];
    while (stack.length && out.length < cap) {
      const cur = stack.pop();
      const n = N.get(cur);
      if (n && pred(n)) out.push(n);
      for (const k of kidsOf(cur)) stack.push(k);
    }
    return out;
  }

  function connectionsOf(id) {
    const self = new Set(chain(id));
    const groups = new Map();
    for (const e of EDGES) {
      const sIn = e.sc.includes(id), tIn = e.tc.includes(id);
      if (sIn === tIn) continue;
      const other = sIn ? e.tc : e.sc;
      const rep = outsideRep(other, self);
      if (!rep) continue;
      const dir = sIn ? 'out' : 'in';
      const key = rep + '|' + dir;
      let g = groups.get(key);
      if (!g) { g = { rep, dir, kinds: new Set(), count: 0, notes: [], edges: [] }; groups.set(key, g); }
      g.kinds.add(e.kind);
      g.count += e.count || 1;
      if (e.description && g.notes.length < 2 && !g.notes.includes(e.description)) g.notes.push(e.description);
      if (g.edges.length < 40) g.edges.push(e);
    }
    return [...groups.values()].sort((a, b) => b.count - a.count);
  }

  function locRow(l) {
    const spot = l.file + (l.line ? ':' + l.line : '');
    return `<li><span class="main"><button class="link" data-copy="${esc(spot)}" title="Copy path">${esc(spot)}</button>${l.label ? `<span class="sub">${esc(l.label)}</span>` : ''}</span>${srcLinks(l.file, l.line)}</li>`;
  }
  function listWithMore(rows, show, id) {
    if (rows.length <= show) return rows.join('');
    return rows.slice(0, show).join('') + rows.slice(show).map((r) => r.replace('<li', `<li hidden data-rest="${id}"`)).join('');
  }
  function moreBtn(count, show, id) {
    return count > show ? `<button class="more" data-more="${id}">Show all ${count}</button>` : '';
  }

  function select(id, opts) {
    opts = opts || {};
    const n = N.get(id);
    if (!n) return;
    if (pick && pick.from !== id) { const from = pick.from; endPick(); startRoute(from, id); return; }
    selected = { type: 'node', id };
    applyFocus();
    const col = css(kindHex(n.kind));
    const inRoom = itemsById.has(id);
    const isOutside = !inRoom && !!opts.port;
    const chips = (n.tech || []).slice(0, 6).map((t) => `<span class="chip">${esc(t)}</span>`);
    if (n.test) chips.push('<span class="chip">Test code</span>');
    if (n.confidence === 'INFERRED') chips.push('<span class="chip warn">Inferred</span>');
    if (n.stale) chips.push('<span class="chip warn">Description may be out of date</span>');
    if (n.lang) chips.unshift(`<span class="chip">${esc(LANG[n.lang] || n.lang)}</span>`);
    const acts = [];
    if (isOutside) acts.push('<button class="go" data-act="goto">Take me there</button>');
    else if (enterable(id) && room.R !== id) acts.push('<button class="go" data-act="enter">Walk inside</button>');
    if (inRoom && !planOn) acts.push('<button data-act="walk">Walk to it</button>');
    else if (!inRoom && !isOutside) acts.push('<button data-act="goto">Take me there</button>');
    if (n.path && n.path !== '.') acts.push('<button data-act="copy">Copy path</button>');
    acts.push('<button data-act="link" title="Copy a link that opens the map on this">Copy link</button>');
    const st = n.stats || {};
    const kindTxt = n.kind === 'module' ? `Folder with ${st.files || 0} files` :
      n.kind === 'file' ? `File, ${n.lines || 0} lines` : (KIND_LABEL[n.kind] || n.kind);
    let h = `<div class="tag-head" style="--kind:${col}"><span class="hole"></span>
      <p class="kind">${esc(kindTxt)}${isOutside ? ', outside this room' : ''}</p>
      <h2>${esc(n.name)}</h2>${chips.length ? `<div class="chips">${chips.join('')}</div>` : ''}
      <div class="actions">${acts.join('')}</div>
      <div class="actions trace-acts"><span>Trace</span><button data-act="down" title="Everything this leads to, following recorded connections">Downstream</button><button data-act="up" title="Everything that leads here">Upstream</button><button data-act="route" title="Pick an end point and walk the path (R)">Route to…</button></div></div>`;
    if (n.description) h += `<section class="sec"><h3>What it is</h3><p>${esc(n.description)}</p></section>`;
    if (n.purpose) h += `<section class="sec"><h3>Why it's here</h3><p>${esc(n.purpose)}</p></section>`;
    if (n.doc && n.doc !== n.description) h += `<section class="sec"><h3>From the code</h3><p>${esc(n.doc)}</p></section>`;
    const locs = (n.locations || []).slice(0, 30).map(locRow);
    const syms = (n.symbols || []).map((s) => locRow({ file: n.path, line: s.line, label: `${s.kind} ${s.name}` }));
    if (locs.length || syms.length) {
      h += `<section class="sec"><h3>Where in the code</h3><ul class="rows">${listWithMore(locs.concat(syms), 8, 'loc')}</ul>${moreBtn(locs.length + syms.length, 8, 'loc')}</section>`;
    }
    const eps = [];
    const files = n.kind === 'file' ? [n] : descendantsWhere(id, (x) => x.kind === 'file' && x.endpoints, 500);
    files.forEach((f) => (f.endpoints || []).forEach((ep) => eps.push(ep)));
    if (eps.length) {
      eps.sort((a, b) => (a.method === 'PAGE') - (b.method === 'PAGE') || a.path.localeCompare(b.path));
      const rows = eps.map((ep) => `<li><span class="method">${esc(ep.method)}</span><span class="main"><button class="link" data-copy="${esc(ep.file + ':' + ep.line)}" title="${esc(ep.file + ':' + ep.line)}">${esc(ep.path)}</button></span>${srcLinks(ep.file, ep.line)}</li>`);
      const api = eps.filter((e) => e.method !== 'PAGE').length;
      h += `<section class="sec"><h3>Endpoints and pages</h3><p class="note">${api} API endpoints, ${eps.length - api} pages</p><ul class="rows">${listWithMore(rows, 10, 'ep')}</ul>${moreBtn(rows.length, 10, 'ep')}</section>`;
    }
    h += schemaSection(n);
    const conns = connectionsOf(id);
    if (conns.length) {
      const row = (g) => {
        const o = N.get(g.rep);
        const kinds = [...g.kinds].map((k) => EDGE_LABEL[k] || k).join(', ');
        const note = g.notes[0] ? `. ${g.notes[0]}` : '';
        return `<li><span class="swatch" style="background:${css(edgeHex(linkKind(g.kinds)))}"></span><span class="main"><button class="link" data-goto="${esc(g.rep)}">${esc(o.name)}</button><span class="sub">${esc(kinds)}${g.count > 1 ? ` (${g.count})` : ''}${esc(note)}</span></span><span class="side">${esc(KIND_LABEL[o.kind] || o.kind)}</span></li>`;
      };
      const out = conns.filter((g) => g.dir === 'out').map(row), inn = conns.filter((g) => g.dir === 'in').map(row);
      if (out.length) h += `<section class="sec"><h3>Reaches out to</h3><ul class="rows">${listWithMore(out, 10, 'co')}</ul>${moreBtn(out.length, 10, 'co')}</section>`;
      if (inn.length) h += `<section class="sec"><h3>Used by</h3><ul class="rows">${listWithMore(inn, 10, 'ci')}</ul>${moreBtn(inn.length, 10, 'ci')}</section>`;
    }
    const kids = kidsOf(id).map((k) => N.get(k));
    if (kids.length) {
      const counts = {};
      kids.forEach((k) => { const lbl = (KIND_LABEL[k.kind] || k.kind).toLowerCase(); counts[lbl] = (counts[lbl] || 0) + 1; });
      const summary = Object.entries(counts).map(([k, v]) => `${v} ${k}${v > 1 && !k.endsWith('s') ? 's' : ''}`).join(', ');
      const rows = kids.sort((a, b) => (enterable(b.id) - enterable(a.id)) || a.name.localeCompare(b.name))
        .map((k) => `<li><span class="swatch" style="background:${css(kindHex(k.kind))}"></span><span class="main"><button class="link" data-goto="${esc(k.id)}">${esc(k.name)}</button></span><span class="side">${k.stats && k.stats.files ? k.stats.files + ' files' : esc(KIND_LABEL[k.kind] || '')}</span></li>`);
      h += `<section class="sec"><h3>Inside</h3><p class="note">${esc(summary)}</p><ul class="rows">${listWithMore(rows, 10, 'in')}</ul>${moreBtn(rows.length, 10, 'in')}</section>`;
    }
    if (n.detected_via && n.detected_via.length) {
      h += `<section class="sec"><h3>How Wirehouse found it</h3><ul class="rows">${n.detected_via.map((v) => `<li><span class="main">${esc(v)}</span></li>`).join('')}</ul></section>`;
    }
    body.innerHTML = h;
    body.scrollTop = 0;
    panel.hidden = false;
    bindPanel(n);
    $('#announce').textContent = `${n.name}, ${kindTxt}${isOutside ? ', outside this room' : ''}`;
    SELECT_HOOKS.forEach((f) => f(id, opts));
    syncHash();
  }
  const SELECT_HOOKS = [];   // later sections: (id, opts) => void after a node is inspected

  function selectLink(info) {
    selected = { type: 'link', info };
    applyFocus();
    const a = N.get(info.a), b = N.get(info.b);
    const k = linkKind(info.kinds);
    const kinds = [...info.kinds].map((x) => `<span class="chip">${esc(EDGE_LABEL[x] || x)}</span>`).join('');
    const note = D.link_notes && D.link_notes[chain(info.a).slice(-1)[0] + '->' + chain(info.b).slice(-1)[0]];
    let h = `<div class="tag-head" style="--kind:${css(edgeHex(k))}"><span class="hole"></span>
      <p class="kind">Connection${info.count > 1 ? `, ${info.count} links` : ''}</p>
      <h2>${esc(a.name)} to ${esc(b.name)}</h2><div class="chips">${kinds}</div>
      <div class="actions"><button data-goto="${esc(info.a)}">Go to ${esc(shortName(a.name, 18))}</button><button data-goto="${esc(info.b)}">Go to ${esc(shortName(b.name, 18))}</button></div></div>`;
    if (note) h += `<section class="sec"><h3>What flows here</h3><p>${esc(note)}</p></section>`;
    const descs = [...new Set(info.edges.map((e) => e.description).filter(Boolean))].slice(0, 6);
    if (descs.length && !note) h += `<section class="sec"><h3>What flows here</h3>${descs.map((d) => `<p>${esc(d)}</p>`).join('')}</section>`;
    const rows = info.edges.map((e) => {
      const ev = (e.evidence || [])[0];
      const s = N.get(e.source), t = N.get(e.target);
      return `<li><span class="swatch" style="background:${css(edgeHex(e.kind))}"></span><span class="main">${esc(s.path || s.name)} <span class="sub">${esc(EDGE_LABEL[e.kind] || e.kind)} ${esc(t.path || t.name)}${e.confidence === 'INFERRED' ? ' (inferred)' : ''}${ev ? `<span class="where">${esc(ev.file + (ev.line ? ':' + ev.line : ''))}</span>` : ''}</span></span>${ev ? srcLinks(ev.file, ev.line) : ''}</li>`;
    });
    h += `<section class="sec"><h3>Evidence</h3><ul class="rows">${listWithMore(rows, 12, 'ev')}</ul>${moreBtn(rows.length, 12, 'ev')}</section>`;
    body.innerHTML = h;
    body.scrollTop = 0;
    panel.hidden = false;
    bindPanel(null);
  }

  const PANEL_ACTS = {};   // later sections: data-act name -> (node) => void
  function bindPanel(n) {
    body.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', () => copy(b.dataset.copy)));
    body.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => focusNode(b.dataset.goto)));
    body.querySelectorAll('[data-more]').forEach((b) => b.addEventListener('click', () => {
      body.querySelectorAll(`[data-rest="${b.dataset.more}"]`).forEach((r) => { r.hidden = false; });
      b.remove();
    }));
    if (!n) return;
    body.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => {
      const a = b.dataset.act;
      if (a === 'enter') { if (planOn) goRoom(n.id); else travelTo(n.id, () => enterBlock(n.id)); }
      if (a === 'walk') travelTo(n.id);
      if (a === 'goto') focusNode(n.id);
      if (a === 'copy') copy(n.path);
      if (a === 'link') copyLink();
      if (PANEL_ACTS[a]) PANEL_ACTS[a](n);
    }));
  }

  // ── hover tooltip ────────────────────────────────────────────────────────
  const lastPick = new THREE.Vector3(Infinity, 0, 0);
  function updateHover() {
    if (ptr.drag || !canvas) return;
    const camMoved = ptr.inside && lastPick.distanceToSquared(camera.position) > 1e-4;
    if (!ptr.moved && !(camMoved && frameNo % 3 === 0)) return;
    ptr.moved = false;
    lastPick.copy(camera.position);
    const hit = pickAt(ptr.x, ptr.y);
    const info = hit && hit.info;
    const tip = $('#tooltip');
    const same = (a, b) => (!a && !b) || (a && b && a.type === b.type && a.id === b.id && (a.type !== 'link' || a === b));
    if (!same(info, hovered)) { hovered = info; applyFocus(); }
    canvas.classList.toggle('pointing', !!info);
    if (!info) { tip.hidden = true; return; }
    if (info.type === 'link') {
      tip.innerHTML = `<b>${esc(N.get(info.a).name)} to ${esc(N.get(info.b).name)}</b><span>${esc([...info.kinds].map((k) => EDGE_LABEL[k] || k).join(', '))}${info.count > 1 ? `, ${info.count} links` : ''}</span>`;
    } else {
      const n = N.get(info.id);
      const extra = info.type === 'port' ? (info.port.dir === 'out' ? 'Outside this room. This room reaches it.' : 'Outside this room. It reaches in here.') : (n.kind === 'file' ? n.path : (KIND_LABEL[n.kind] || n.kind));
      tip.innerHTML = `<b>${esc(n.name)}</b><span>${esc(extra)}</span>`;
    }
    tip.style.left = Math.min(ptr.x + 16, window.innerWidth - 330) + 'px';
    tip.style.top = (ptr.y + 18) + 'px';
    tip.hidden = false;
  }

  // ── trace: reach, routes and journeys ────────────────────────────────────
  // Traces follow recorded connections only: what the scanner found plus what
  // enrichment added with evidence. That is the map's reach, not a promise about
  // runtime impact. A connection that points at a whole block (an env var naming a
  // service) reaches everything inside that block, because the map cannot say which
  // file answers it. Hops count block boundaries, so an import chain inside one
  // block does not make something look further away.
  // Start-up order (compose depends_on) and provisioning (Terraform, hosting) describe how things
  // are deployed, not what talks to what at runtime, so traces and routes do not follow them.
  const NOT_TRAFFIC = new Set(['depends_on', 'provisions']);
  const OUT_E = new Map(), IN_E = new Map();
  EDGES.forEach((e) => {
    if (!OUT_E.has(e.source)) OUT_E.set(e.source, []);
    OUT_E.get(e.source).push(e);
    if (!IN_E.has(e.target)) IN_E.set(e.target, []);
    IN_E.get(e.target).push(e);
  });
  const topOf = (id) => { const c = chain(id); return c[c.length - 1]; };
  const hops = (d) => `${d} hop${d === 1 ? '' : 's'}`;
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const where = (id) => { const n = N.get(id); return !n ? id : n.parent ? n.path || n.name : n.name; };
  // Change review (rendered with --against): what is new or changed, and the edges of new connections.
  const DELTA = D.delta || null;
  const DELTA_IDS = new Map(), DELTA_EDGES = new Set();
  let changesOn = false;
  if (DELTA) {
    DELTA.blocks.added.concat(DELTA.files.added).forEach((id) => { if (N.has(id)) DELTA_IDS.set(id, 'added'); });
    DELTA.blocks.changed.concat(DELTA.files.changed).forEach((id) => { if (N.has(id)) DELTA_IDS.set(id, 'changed'); });
    const fresh = new Set(DELTA.links.added);
    EDGES.forEach((e) => { if (fresh.has(topOf(e.source) + '->' + topOf(e.target))) DELTA_EDGES.add(e.i); });
  }

  /** Shortest-hop walk over recorded edges. dir 'down' follows edges forward, 'up' backward. */
  function walk(start, dir, opts) {
    opts = opts || {};
    const down = dir !== 'up';
    const dist = new Map(), via = new Map(), used = new Set(), ancDone = new Set(), buckets = [];
    const relax = (id, d, from, e) => {
      if (dist.has(id) && dist.get(id) <= d) return;
      dist.set(id, d);
      via.set(id, from == null ? null : { from, e });
      (buckets[d] = buckets[d] || []).push(id);
    };
    const step = (id, d, e, other) => {
      if (HIDE.has(e.kind) || NOT_TRAFFIC.has(e.kind) || !N.has(other)) return;
      used.add(e.i);
      relax(other, d + (topOf(other) === topOf(id) ? 0 : 1), id, e);
    };
    relax(start, 0, null, null);
    let found = null;
    for (let d = 0; d < buckets.length && d <= 40 && !found; d++) {
      const B = buckets[d] || [];
      for (let i = 0; i < B.length; i++) {
        const id = B[i];
        if (dist.get(id) !== d) continue;
        if (opts.stop && id !== start && opts.stop(id)) { found = id; break; }
        // A whole block reaches what is inside it. Upstream, only the start's own contents count:
        // reaching a block as the source of one edge says nothing about the other files in it.
        if (down || chain(id).includes(start)) for (const c of kidsOf(id)) relax(c, d, id, null);
        if (opts.loose) { const t = topOf(id); if (t !== id) relax(t, d, id, null); }
        if (down) (OUT_E.get(id) || []).forEach((e) => step(id, d, e, e.target));
        else {
          (IN_E.get(id) || []).forEach((e) => step(id, d, e, e.source));
          // a connection into a whole block may land on anything inside it
          for (const a of chain(id).slice(1)) {
            if (ancDone.has(a)) continue;
            ancDone.add(a);
            (IN_E.get(a) || []).forEach((e) => step(id, d, e, e.source));
          }
        }
      }
    }
    return { start, dir: down ? 'down' : 'up', dist, via, used, found };
  }
  function pathTo(res, end) {
    const out = [];
    for (let c = end; c != null;) { const v = res.via.get(c); out.push({ id: c, e: v ? v.e : null }); c = v ? v.from : null; }
    return out.reverse();
  }
  /** id -> what stands for it in room R: a child of R, a wall port, or null (R itself or above). */
  function projector(R) {
    const rset = new Set(R ? chain(R) : []);
    return (id) => {
      const ch = chain(id);
      if (!R) return ch[ch.length - 1];
      return ch.includes(R) ? childOf(ch, R) : outsideRep(ch, rset);
    };
  }
  function lcaRoom(a, b) {
    const B = new Set(chain(b));
    for (const x of chain(parentOf(a))) if (B.has(x) && x !== b) return x;
    return ROOT;
  }

  let trace = null;    // {mode:'down'|'up', id, res} or {mode:'route', a, b, path, loose, used, stops}
  let pick = null;     // choosing where a route ends: {from, res}
  let player = null;   // stepping through a route or tour: {kind, title, stops, i, playing}

  function startTrace(dir, id) {
    if (!N.has(id)) return;
    endPick(true); stopPlayer(true);
    trace = { mode: dir === 'up' ? 'up' : 'down', id, res: walk(id, dir) };
    refreshMarks(); drawBar(); syncHash();
  }
  function startPick(from) {
    if (!N.has(from)) return;
    stopPlayer(true);
    trace = null;
    pick = { from, res: walk(from, 'down') };
    refreshMarks(); drawBar(); syncHash();
  }
  function endPick(quiet) { if (!pick) return; pick = null; if (!quiet) { refreshMarks(); drawBar(); } }
  function startRoute(a, b) {
    if (!N.has(a) || !N.has(b) || a === b) return false;
    if (chain(a).includes(b) || chain(b).includes(a)) {
      // one holds the other: getting there takes no recorded connection, so there is no route to show
      toast(`${N.get(a).name} and ${N.get(b).name} are one inside the other: pick a place outside it`, 3200);
      return false;
    }
    endPick(true); stopPlayer(true);
    const reaches = (id) => chain(id).includes(b);
    let res = walk(a, 'down', { stop: reaches }), loose = false;
    if (!res.found) { res = walk(a, 'down', { stop: reaches, loose: true }); loose = !!res.found; }
    const path = res.found ? pathTo(res, res.found) : null;
    const used = new Set(path ? path.filter((p) => p.e).map((p) => p.e.i) : []);
    trace = { mode: 'route', a, b, path, loose, used, stops: path ? routeStops(path, a, b) : [] };
    refreshMarks(); drawBar(); syncHash();
    return true;
  }
  function routeStops(path, a, b) {
    const R0 = lcaRoom(a, b), rep = projector(R0), stops = [];
    path.forEach((p) => {
      const r = rep(p.id);
      p.stop = Math.max(0, stops.length - (r ? 0 : 1));   // which bar stop this step belongs to, for the floor badges
      if (!r) return;
      const last = stops[stops.length - 1];
      if (!last || last.id !== r) { p.stop = stops.length; stops.push({ id: r, room: R0, edge: p.e, inside: [] }); }
      else {
        p.stop = stops.length - 1;
        if (p.id !== r && p.e) last.inside.push(p.id);
      }
    });
    return stops;
  }
  function clearTrace() { trace = null; endPick(true); stopPlayer(true); refreshMarks(); drawBar(); syncHash(); }
  FILTER_HOOKS.push(() => {
    if (trace && trace.mode === 'route') startRoute(trace.a, trace.b);
    else if (trace) startTrace(trace.mode, trace.id);
    else if (pick) startPick(pick.from);
  });

  // marks: rings on the floor and badges for whatever is being traced
  function computeMarks() {
    MARK.lit = null; MARK.ids = null; MARK.hop = null; MARK.badges = new Map();
    if (!room) return;
    const rep = projector(room.R), TC = T.trace;
    const byHop = (res, color, startText) => {
      const best = new Map();
      res.dist.forEach((d, id) => { const r = rep(id); if (r && (!best.has(r) || best.get(r) > d)) best.set(r, d); });
      const s = rep(res.start);
      best.forEach((d, r) => MARK.badges.set(r, { text: r === s ? startText : hops(d), color, strong: r === s }));
      MARK.ids = new Set(best.keys());
      MARK.lit = (info) => { for (const i of info.ids) if (res.used.has(i)) return true; return false; };
      MARK.hop = best;
    };
    if (player) {
      const order = new Map();
      player.stops.forEach((st, k) => { const r = rep(st.id); if (r && !order.has(r)) order.set(r, k); });
      order.forEach((k, r) => MARK.badges.set(r, { text: String(k + 1), color: TC.route, strong: k === player.i }));
      MARK.ids = new Set(order.keys());
      if (player.used) MARK.lit = (info) => { for (const i of info.ids) if (player.used.has(i)) return true; return false; };
    } else if (pick) byHop(pick.res, TC.route, 'From');
    else if (trace && trace.mode === 'route') {
      if (!trace.path) return;
      // numbered like the bar's stops, so badge 2 and stop 2 are the same place in any room
      const order = new Map();
      trace.path.forEach((p) => { const r = rep(p.id); if (r && !order.has(r)) order.set(r, p.stop); });
      const end = rep(trace.b), first = order.keys().next().value;
      order.forEach((s, r) => MARK.badges.set(r, { text: r === first ? 'Start' : r === end ? 'End' : String(s + 1), color: TC.route, strong: r === first || r === end }));
      MARK.ids = new Set(order.keys());
      MARK.lit = (info) => { for (const i of info.ids) if (trace.used.has(i)) return true; return false; };
    } else if (trace) byHop(trace.res, TC[trace.mode], 'Start');
    else if (changesOn && DELTA) {
      // a block counts as new only when it is itself new; anything new or changed inside it marks it changed
      DELTA_IDS.forEach((how, id) => {
        const r = rep(id);
        if (!r) return;
        const text = r === id && how === 'added' ? 'New' : 'Changed';
        const prev = MARK.badges.get(r);
        if (!prev || prev.text === 'Changed') MARK.badges.set(r, { text, color: text === 'New' ? TC.down : TC.up, strong: text === 'New' });
      });
      MARK.ids = new Set(MARK.badges.keys());
      MARK.lit = (info) => { for (const i of info.ids) if (DELTA_EDGES.has(i)) return true; return false; };
    }
  }
  let markObjs = [];
  function drawMarks() {
    markObjs.forEach((o) => {
      world.remove(o);
      if (o.geometry && !o.isSprite) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
    markObjs = [];
    if (!room || !MARK.badges || !MARK.badges.size) return;
    MARK.badges.forEach((b, id) => {
      const it = itemsById.get(id);
      const port = !it && room.ports.find((p) => p.rep === id);
      if (!it && !port) return;
      if (it && it.shape !== 'slot') {
        const r = Math.max(it.w, it.d) / 2 + 0.7;
        const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + (b.strong ? 0.45 : 0.28), 48),
          new THREE.MeshBasicMaterial({ color: b.color, transparent: true, opacity: b.strong ? 0.95 : 0.7, depthWrite: false, side: THREE.DoubleSide }));
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(it.x, 0.05, it.z);
        ring.renderOrder = 4;
        world.add(ring);
        markObjs.push(ring);
      }
      const lb = label([b.text], b.strong ? 1.0 : 0.8, { bg: css(b.color), ink: T.glow ? '#0b0f17' : '#ffffff', big: 56, weight: 700, pad: 12 });
      if (it) {
        const tall = it.shape === 'machine' || it.shape === 'gate' || N.get(id).kind === 'ai';
        lb.position.set(it.x, it.shape === 'slot' ? it.y + it.h + 0.5 : it.h + (tall ? 3.9 : 2.2), it.z);
      } else lb.position.set(port.x + Math.sin(port.ry) * 0.7, port.y + 1.0, port.z + Math.cos(port.ry) * 0.7);
      world.add(lb);
      markObjs.push(lb);
    });
  }
  BUILD_HOOKS.push(() => { computeMarks(); drawMarks(); });
  function refreshMarks() {
    computeMarks();
    drawMarks();
    applyFocus();
    if (planOn) drawPlan();
  }

  // the trace bar: what is lit, why, and what you can do next
  const bar = $('#bar');
  function hiddenNote() {
    return HIDE.size ? ` Not following pipes that ${[...HIDE].map((k) => EDGE_LABEL[k]).join(', ')} (switched off in the pipe key).` : '';
  }
  function drawBar() {
    let h = '';
    const TC = T.trace;
    if (player) h = playerBar();
    else if (pick) {
      const n = Math.max(0, (MARK.ids ? MARK.ids.size : 1) - 1);
      h = `<div class="bar-head"><span class="bar-kind" style="--c:${css(TC.route)}">Route</span><span>From <b>${esc(N.get(pick.from).name)}</b>: pick where it ends</span></div>
        <p class="bar-note">Click a block or a wall port, or find it with <kbd>/</kbd>. Badges mark the ${plural(n, 'place')} in this room it can reach.${hiddenNote()}</p>
        <div class="bar-acts"><button data-b="cancel">Cancel</button></div>`;
    } else if (trace && trace.mode === 'route') {
      const a = N.get(trace.a), b = N.get(trace.b);
      if (!trace.path) {
        h = `<div class="bar-head"><span class="bar-kind" style="--c:${css(TC.route)}">Route</span><span><b>${esc(a.name)}</b> to <b>${esc(b.name)}</b></span></div>
          <p class="bar-note">The map has no recorded path in this direction.${hiddenNote()}</p>
          <div class="bar-acts"><button data-b="swap">Try ${esc(shortName(b.name, 18))} to ${esc(shortName(a.name, 18))}</button><button data-b="clear">Clear</button></div>`;
      } else {
        const steps = trace.stops.map((st, k) => `<button class="stop" data-goto="${esc(st.id)}"><span>${k + 1}</span>${esc(shortName(N.get(st.id).name, 26))}</button>`).join('<i aria-hidden="true">→</i>');
        h = `<div class="bar-head"><span class="bar-kind" style="--c:${css(TC.route)}">Route</span><span><b>${esc(a.name)}</b> to <b>${esc(b.name)}</b> · ${plural(trace.stops.length, 'stop')}</span></div>
          <div class="bar-steps">${steps}</div>
          <p class="bar-note">${trace.loose ? 'Loose route: the blocks connect, but not through the same files, so part of it is block to block.' : 'The shortest path through recorded connections.'}${hiddenNote()}</p>
          <div class="bar-acts"><button class="go" data-b="journey">Walk the route</button><button data-b="swap">Reverse</button><button data-b="link">Copy link</button><button data-b="clear">Clear</button></div>`;
      }
    } else if (trace) {
      const n = N.get(trace.id), down = trace.mode === 'down';
      const best = MARK.hop || new Map();
      const groups = new Map();
      const startRep = projector(room.R)(trace.id);
      best.forEach((d, id) => { if (id !== startRep) { if (!groups.has(d)) groups.set(d, []); groups.get(d).push(id); } });
      const reached = [...groups.values()].reduce((s, g) => s + g.length, 0);
      const max = reached ? Math.max(...groups.keys()) : 0;
      const list = [...groups.keys()].sort((x, y) => x - y).map((d) => `<div class="hop-row"><span class="hop">${d === 0 ? 'Same block' : hops(d)}</span>${groups.get(d)
        .sort((x, y) => N.get(x).name.localeCompare(N.get(y).name))
        .map((id) => `<button class="chip-btn" data-goto="${esc(id)}"><i style="background:${css(kindHex(N.get(id).kind))}"></i>${esc(shortName(N.get(id).name, 24))}</button>`).join('')}</div>`).join('');
      h = `<div class="bar-head"><span class="bar-kind" style="--c:${css(TC[trace.mode])}">${down ? 'Downstream' : 'Upstream'}</span>
        <span>${down ? 'Where' : 'What leads to'} <b>${esc(n.name)}</b>${down ? ' leads' : ''} · ${reached ? `${plural(reached, 'place')}, up to ${hops(max)} away` : 'nothing recorded'}</span></div>
        ${list ? `<div class="bar-list">${list}</div>` : ''}
        <p class="bar-note">Follows recorded connections that carry traffic (not start-up order or provisioning), so wiring the scan could not see is not included.${hiddenNote()}</p>
        <div class="bar-acts"><button data-b="flip">${down ? 'Upstream' : 'Downstream'} instead</button><button data-b="link">Copy link</button><button data-b="clear">Clear</button></div>`;
    }
    bar.hidden = !h;
    bar.innerHTML = h;
    bar.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => focusNode(b.dataset.goto)));
    bar.querySelectorAll('[data-b]').forEach((b) => b.addEventListener('click', () => BAR_ACTS[b.dataset.b]()));
    if (h) $('#prompt').hidden = true;
  }
  const BAR_ACTS = {
    cancel: () => { endPick(); syncHash(); },
    clear: () => clearTrace(),
    link: () => copyLink(),
    flip: () => startTrace(trace.mode === 'down' ? 'up' : 'down', trace.id),
    swap: () => startRoute(trace.b, trace.a),
    journey: () => startJourney(0, true),
    prev: () => goStop(player.i - 1),
    next: () => goStop(player.i + 1),
    play: () => setPlaying(!player.playing),
    stop: () => stopPlayer(),
  };

  // the player walks the worker from stop to stop (routes here, tours later)
  function startJourney(i, playing, extra) {
    if (!trace || trace.mode !== 'route' || !trace.path) return;
    const a = N.get(trace.a), b = N.get(trace.b);
    startPlayer(Object.assign({
      kind: 'route', title: `${a.name} to ${b.name}`, used: trace.used, playing,
      stops: trace.stops.map((st, k) => ({ id: st.id, room: st.room, html: routeStopHtml(st, k) })),
    }, extra || {}), i);
  }
  function routeStopHtml(st, k) {
    const n = N.get(st.id);
    let h = '';
    if (k === 0) h += `<p>Start at <b>${esc(n.name)}</b> (${esc((KIND_LABEL[n.kind] || n.kind).toLowerCase())}).</p>`;
    else if (st.edge) {
      const e = st.edge, ev = (e.evidence || [])[0];
      h += `<p><b>${esc(where(e.source))}</b> ${esc(EDGE_LABEL[e.kind] || e.kind)} <b>${esc(where(e.target))}</b>${e.description ? `: ${esc(e.description)}` : ''}${e.confidence === 'INFERRED' ? ' <span class="chip warn">inferred</span>' : ''}</p>`;
      if (ev) h += `<ul class="rows"><li><span class="main">${esc(ev.file + (ev.line ? ':' + ev.line : ''))}</span>${srcLinks(ev.file, ev.line)}</li></ul>`;
    } else h += `<p>Into <b>${esc(n.name)}</b>. The map links these blocks, but not through the same files (loose step).</p>`;
    if (st.inside.length) h += `<p class="bar-note">Inside ${esc(n.name)}: ${st.inside.slice(0, 4).map((x) => esc(where(x))).join(' → ')}${st.inside.length > 4 ? ' → …' : ''}</p>`;
    return h;
  }
  function startPlayer(p, i) {
    endPick(true);
    if (player) clearTimeout(player.timer);
    player = Object.assign({ i: -1, playing: false, timer: 0 }, p);
    goStop(i || 0);
  }
  function stopPlayer(quiet) {
    if (!player) return;
    clearTimeout(player.timer);
    const was = player;
    player = null;
    W8.path = null;
    arrival = null;
    PLAYER_HOOKS.forEach((f) => f(was));
    if (!quiet) { refreshMarks(); drawBar(); syncHash(); }
  }
  const PLAYER_HOOKS = [];   // later sections: (stoppedPlayer) => void
  function setPlaying(on) {
    if (!player) return;
    player.playing = on;
    clearTimeout(player.timer);
    if (!on) { W8.path = null; arrival = null; }
    else if (!player.arrived) { goStop(player.i); return; }
    else if (player.i < player.stops.length - 1) { goStop(player.i + 1); return; }
    else player.playing = false;
    drawBar();
  }
  function dwell(st) { return player.kind === 'route' ? 1700 : clamp(2600 + String(st.text || '').length * 35, 3000, 9000); }
  function goStop(i) {
    if (!player) return;
    clearTimeout(player.timer);
    i = clamp(i, 0, player.stops.length - 1);
    player.i = i;
    player.arrived = false;
    const st = player.stops[i];
    const R = st.room != null ? st.room : parentOf(st.id);
    const arrive = () => {
      if (!player || player.i !== i) return;
      player.arrived = true;
      STOP_HOOKS.forEach((f) => f(st, i));
      drawBar();
      if (player.playing) {
        player.timer = setTimeout(() => {
          if (!player || player.i !== i) return;
          if (i < player.stops.length - 1) goStop(i + 1); else { player.playing = false; drawBar(); }
        }, dwell(st));
      }
    };
    const here = () => {
      if (!player || player.i !== i) return;
      if (player.kind !== 'route') {
        const port = room.ports.find((p) => p.rep === st.id);
        select(st.id, port && !itemsById.has(st.id) ? { port, tour: true } : { tour: true });
      }
      refreshMarks();
      drawBar();
      if (planOn) { arrive(); return; }
      if (reduceMotion) {
        const sp = standPoint(st.id);
        if (sp) { W8.pos.set(sp.x, 0, sp.z); collide(W8.pos); W8.yaw = Math.atan2(sp.face.x - sp.x, sp.face.z - sp.z); }
        arrive();
      } else travelTo(st.id, arrive);
    };
    drawBar();
    syncHash();
    if ((room ? room.R : ROOT) !== R) goRoom(R, { then: here }); else here();
  }
  const STOP_HOOKS = [];   // later sections: (stop, index) => void on arrival
  function playerBar() {
    const st = player.stops[player.i], n = N.get(st.id), last = player.stops.length - 1;
    return `<div class="bar-head"><span class="bar-kind" style="--c:${css(T.trace.route)}">${player.kind === 'route' ? 'Route' : 'Tour'}</span>
        <span><b>${esc(player.title)}</b> · stop ${player.i + 1} of ${player.stops.length}${player.arrived ? '' : ', walking…'}</span></div>
      <div class="bar-step"><h4>${esc(st.title || n.name)}</h4>${st.html || ''}</div>
      <div class="bar-acts"><button data-b="prev" ${player.i === 0 ? 'disabled' : ''} aria-label="Previous stop">◀ Back</button>
        <button class="go" data-b="play" aria-pressed="${player.playing}">${player.playing ? 'Pause' : player.i === last && player.arrived ? 'At the end' : 'Play'}</button>
        <button data-b="next" ${player.i === last ? 'disabled' : ''} aria-label="Next stop">Next ▶</button>
        <button data-b="link">Copy link</button><button data-b="stop">Done</button></div>`;
  }

  PANEL_ACTS.down = (n) => startTrace('down', n.id);
  PANEL_ACTS.up = (n) => startTrace('up', n.id);
  PANEL_ACTS.route = (n) => startPick(n.id);
  KEYS.r = () => {
    if (selected && selected.type !== 'link') startPick(selected.id);
    else toast('Inspect a block first, then press R to pick where the route ends');
  };
  KEYS[','] = () => { if (player) goStop(player.i - 1); };
  KEYS['.'] = () => { if (player) goStop(player.i + 1); };
  keySpace = () => { if (!player) return false; setPlaying(!player.playing); return true; };
  onEscape(20, () => !!pick, () => { endPick(); syncHash(); });
  onEscape(30, () => !!(player && player.playing), () => setPlaying(false));
  onEscape(40, () => !!player, () => stopPlayer());
  onEscape(50, () => !!trace, () => clearTrace());

  HASH_PARTS.push(() => {
    if (pick || (player && player.tourId)) return null;   // tours write their own part
    if (trace && trace.mode === 'route') return 'route=' + encId(trace.a) + '~' + encId(trace.b) + (player && player.kind === 'route' ? '&stop=' + (player.i + 1) : '');
    if (trace) return 'trace=' + trace.mode + '~' + encId(trace.id);
    return null;
  });
  HASH_APPLY.push((h) => {
    if (h.route && h.route.length === 2 && N.has(h.route[0]) && N.has(h.route[1])) {
      if (!startRoute(h.route[0], h.route[1])) { clearTrace(); return; }
      if (h.stop && trace && trace.path) startJourney(clamp((+h.stop || 1) - 1, 0, trace.stops.length - 1), false);
    } else if (h.trace && h.trace.length === 2 && N.has(h.trace[1])) startTrace(h.trace[0], h.trace[1]);
    else if (trace || pick || (player && player.kind === 'route')) clearTrace();
  });

  // ── clipboard: tours and quests ──────────────────────────────────────────
  // Tours walk the worker through the system stop by stop; quests send the reader
  // looking for something and tick off when they inspect the answer. Progress
  // (quests found, tours walked, blocks inspected) lives in this browser only.
  const TOURS = D.tours || [];
  const QUESTS = D.quests || [];
  // Keyed by name and top-level blocks, so two projects that share a name do not share progress.
  const progSig = [...N.values()].filter((n) => !n.parent).map((n) => n.id).sort().join('|');
  let progHash = 0;
  for (let i = 0; i < progSig.length; i++) progHash = (progHash * 31 + progSig.charCodeAt(i)) | 0;
  const progKey = `progress:${D.project.name}:${(progHash >>> 0).toString(36)}`;
  const PROG = { found: [], walked: [], seen: [] };
  try {
    const saved = JSON.parse(store.get(progKey, '{}'));
    for (const k of Object.keys(PROG)) if (saved && Array.isArray(saved[k])) PROG[k] = saved[k].filter((x) => typeof x === 'string');
  } catch (e) { /* unreadable progress: start fresh */ }
  const saveProg = () => store.set(progKey, JSON.stringify(PROG));
  const clip = $('#clip'), clipBtn = $('#clipBtn');
  const hintsShown = new Set();
  let openQuest = null;

  function clipCount() {
    const found = QUESTS.filter((q) => PROG.found.includes(q.id)).length;
    clipBtn.innerHTML = `Clipboard${QUESTS.length ? ` <span class="count">${found}/${QUESTS.length}</span>` : ''}`;
  }
  function evRows(evs) {
    return (evs || []).length ? `<ul class="rows">${evs.map((ev) => `<li><span class="main">${esc(ev.file + (ev.line ? ':' + ev.line : ''))}</span>${srcLinks(ev.file, ev.line)}</li>`).join('')}</ul>` : '';
  }
  function drawClip() {
    clipCount();
    if (clip.hidden) return;
    const tops = kidsOf(ROOT);
    const seenTops = tops.filter((id) => PROG.seen.includes(id));
    const unseen = tops.filter((id) => !PROG.seen.includes(id));
    const foundN = QUESTS.filter((q) => PROG.found.includes(q.id)).length;
    let h = `<div class="clip-head"><h2>Clipboard</h2><button class="ghost round close" data-c="close" aria-label="Close clipboard">×</button></div>
      <p class="note">Tours walk you through the system. Quests send you looking for something. Progress stays in this browser.</p>`;
    if (TOURS.length) {
      h += `<section class="sec"><h3>Tours</h3><ul class="rows">${TOURS.map((t) => `<li><span class="main"><b>${esc(t.title)}</b>${PROG.walked.includes(t.id) ? ' <span class="chip">walked</span>' : ''}
        <span class="sub">${t.route ? 'A route, walked hop by hop' : plural(t.stops.length, 'stop')}${t.intro ? ` · ${esc(t.intro)}` : ''}</span></span>
        <button class="go small-btn" data-tour="${esc(t.id)}">Start</button></li>`).join('')}</ul></section>`;
    }
    if (QUESTS.length) {
      h += `<section class="sec"><h3>Quests <span class="note">${foundN} of ${QUESTS.length} found</span></h3><ul class="quests">${QUESTS.map((q) => {
        const found = PROG.found.includes(q.id), open = openQuest === q.id;
        let body = '';
        if (open && found) {
          body = `<div class="q-body">${q.explain ? `<p>${esc(q.explain)}</p>` : ''}${evRows(q.evidence)}
            <button class="link" data-goto="${esc(q.answer[0])}">Take me there</button></div>`;
        } else if (open) {
          body = `<div class="q-body">${hintsShown.has(q.id) ? `<p class="hint">${esc(q.hint || 'Try the search, or trace from a block you know.')}</p>` : `<button class="link" data-hint="${esc(q.id)}">Show a hint</button>`}
            <p class="note">Inspect the answer (click it) to tick this off.</p></div>`;
        }
        return `<li class="${found ? 'found' : ''}"><button class="q" data-q="${esc(q.id)}" aria-expanded="${open}"><span class="box" aria-hidden="true">${found ? '✓' : ''}</span>
          <span>${esc(q.question)}</span><span class="sr">${found ? ' (found)' : ' (not found yet)'}</span></button>${body}</li>`;
      }).join('')}</ul></section>`;
    }
    h += `<section class="sec"><h3>Inspected</h3><p class="note">You have looked at ${seenTops.length} of ${plural(tops.length, 'block')} on the main floor.</p>
      ${unseen.length ? `<div class="chips">${unseen.slice(0, 16).map((id) => `<button class="chip-btn" data-goto="${esc(id)}"><i style="background:${css(kindHex(N.get(id).kind))}"></i>${esc(shortName(N.get(id).name, 22))}</button>`).join('')}</div>` : '<p>Every block inspected. Nice inventory.</p>'}
      </section><div class="sec"><button class="link" data-c="reset">Start over (clear progress)</button></div>`;
    clip.innerHTML = h;
    clip.querySelectorAll('[data-tour]').forEach((b) => b.addEventListener('click', () => startTour(b.dataset.tour, 0, true)));
    clip.querySelectorAll('[data-q]').forEach((b) => b.addEventListener('click', () => {
      openQuest = openQuest === b.dataset.q ? null : b.dataset.q;
      drawClip();
      const again = clip.querySelector(`[data-q="${CSS.escape(b.dataset.q)}"]`);
      if (again) again.focus();
    }));
    clip.querySelectorAll('[data-hint]').forEach((b) => b.addEventListener('click', () => { hintsShown.add(b.dataset.hint); drawClip(); }));
    clip.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => focusNode(b.dataset.goto)));
    clip.querySelectorAll('[data-c]').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.c === 'close') toggleClip(false);
      if (b.dataset.c === 'reset') { PROG.found = []; PROG.walked = []; PROG.seen = []; hintsShown.clear(); saveProg(); drawClip(); }
    }));
  }
  function toggleClip(on) {
    clip.hidden = on == null ? !clip.hidden : !on;
    clipBtn.setAttribute('aria-expanded', String(!clip.hidden));
    drawClip();
    if (!clip.hidden) { const f = clip.querySelector('button[data-tour], button[data-q]'); if (f) f.focus(); }
  }
  clipBtn.addEventListener('click', () => toggleClip());

  function tourStopHtml(t, s, k) {
    return (k === 0 && t.intro ? `<p class="bar-note">${esc(t.intro)}</p>` : '') + (s.text ? `<p>${esc(s.text)}</p>` : '') + evRows(s.evidence);
  }
  function startTour(id, i, playing) {
    const t = TOURS.find((x) => x.id === id);
    if (!t) return;
    toggleClip(false);
    if (t.route) {
      if (!startRoute(t.route[0], t.route[1])) return;
      if (!trace || !trace.path) { toast('This tour has no recorded path to walk with the current pipe filter', 3000); return; }
      startJourney(i || 0, playing, { title: t.title, tourId: t.id });
      return;
    }
    clearTrace();
    startPlayer({
      kind: 'tour', tourId: t.id, title: t.title, playing,
      stops: t.stops.map((s, k) => ({ id: s.node, title: s.title || N.get(s.node).name, text: s.text, html: tourStopHtml(t, s, k) })),
    }, i || 0);
  }
  STOP_HOOKS.push((st, i) => {
    if (player && player.tourId && i === player.stops.length - 1 && !PROG.walked.includes(player.tourId)) {
      PROG.walked.push(player.tourId);
      saveProg();
      clipCount();
    }
  });
  SELECT_HOOKS.push((id, opts) => {
    const top = topOf(id);
    let changed = false;
    if (top && !PROG.seen.includes(top)) { PROG.seen.push(top); changed = true; }
    const ch = chain(id);
    if (!(opts && opts.tour)) QUESTS.forEach((q) => {
      if (PROG.found.includes(q.id) || !q.answer.some((a) => ch.includes(a))) return;
      PROG.found.push(q.id);
      changed = true;
      openQuest = q.id;
      toast(`Quest done: ${q.question}`, 3200);
    });
    if (changed) { saveProg(); drawClip(); }
  });

  KEYS.c = () => toggleClip();
  onEscape(25, () => !clip.hidden, () => { toggleClip(false); clipBtn.focus(); });
  HASH_PARTS.push(() => (player && player.tourId ? 'tour=' + encId(player.tourId) + '&stop=' + (player.i + 1) : null));
  HASH_APPLY.push((h) => {
    if (h.tour && TOURS.some((t) => t.id === h.tour)) startTour(h.tour, Math.max(0, (+h.stop || 1) - 1), false);
    else if (player && player.tourId) stopPlayer();
  });
  if (TOURS.length) {
    $('#welcomeTour').hidden = false;
    $('#welcomeTour').textContent = `Take the tour: ${TOURS[0].title}`;
    $('#welcomeTour').addEventListener('click', () => { closeWelcome(); startTour(TOURS[0].id, 0, true); });
  }
  clipCount();

  // ── schema: columns in the panel, a table diagram for each database ──────
  // Columns and foreign keys come from the code that defines the tables (SQL,
  // Prisma, SQLAlchemy, Django, Drizzle, TypeORM). Tables found some other way show
  // their name only.
  const tablesOf = (dbId) => kidsOf(dbId).map((k) => N.get(k)).filter((n) => n.kind === 'table');
  const fkTarget = (table, fk) => { const prefix = table.id.slice(0, table.id.lastIndexOf(':') + 1); const id = prefix + String(fk.table).toLowerCase(); return N.has(id) ? id : null; };
  function schemaSection(n) {
    if (n.kind === 'table') {
      const cols = n.columns || [];
      const rows = cols.map((c) => {
        const t = c.fk ? fkTarget(n, c.fk) : null;
        const keys = (c.pk ? '<span class="key pk" title="Primary key">PK</span>' : '') + (c.fk ? '<span class="key fk" title="Foreign key">FK</span>' : '');
        const ref = c.fk ? `<span class="sub">→ ${t ? `<button class="link" data-goto="${esc(t)}">${esc(N.get(t).name)}</button>` : esc(c.fk.table)}.${esc(c.fk.column)}</span>` : '';
        return `<li><span class="main"><b>${esc(c.name)}</b> ${keys}${ref}</span><span class="side">${esc(c.type || '')}${c.required ? ' · required' : ''}</span></li>`;
      });
      return `<section class="sec"><h3>Columns</h3>${cols.length ? `<ul class="rows">${listWithMore(rows, 12, 'col')}</ul>${moreBtn(rows.length, 12, 'col')}`
        : '<p class="note">The columns could not be read from the code that defines this table.</p>'}
        <div class="actions"><button data-act="erd">Open schema diagram</button></div></section>`;
    }
    const tables = tablesOf(n.id);
    if (!tables.length) return '';
    const fks = tables.reduce((s, t) => s + (t.columns || []).filter((c) => c.fk && fkTarget(t, c.fk)).length, 0);
    return `<section class="sec"><h3>Schema</h3><p class="note">${plural(tables.length, 'table')}, ${plural(fks, 'foreign key')} found in the code.</p>
      <div class="actions"><button class="go" data-act="erd">Open schema diagram</button></div></section>`;
  }
  PANEL_ACTS.erd = (n) => openErd(n.kind === 'table' ? n.parent : n.id, n.kind === 'table' ? n.id : null);

  const erd = $('#erd'), erdSvg = $('#erdSvg');
  let erdView = null, erdFocus = null;
  function openErd(dbId, focusTable) {
    const db = N.get(dbId);
    const tables = tablesOf(dbId);
    if (!db || !tables.length) return;
    erdFocus = focusTable;
    const BW = 240, HEAD = 30, ROW = 20, MAXROWS = 14, GAPX = 110, GAPY = 46;
    // most connected first, then walk the foreign keys so related tables land near each other
    const links = [];
    tables.forEach((t) => (t.columns || []).forEach((c, ci) => { const to = c.fk && fkTarget(t, c.fk); if (to && tables.some((x) => x.id === to)) links.push({ from: t.id, ci, to }); }));
    const deg = new Map(tables.map((t) => [t.id, 0]));
    links.forEach((l) => { deg.set(l.from, deg.get(l.from) + 1); deg.set(l.to, deg.get(l.to) + 1); });
    const order = [], seen = new Set();
    const byDeg = [...tables].sort((a, b) => deg.get(b.id) - deg.get(a.id) || a.name.localeCompare(b.name));
    byDeg.forEach((t) => {
      if (seen.has(t.id)) return;
      const q = [t.id];
      seen.add(t.id);
      while (q.length) {
        const id = q.shift();
        order.push(id);
        links.filter((l) => l.from === id || l.to === id).map((l) => (l.from === id ? l.to : l.from))
          .filter((x) => !seen.has(x)).forEach((x) => { seen.add(x); q.push(x); });
      }
    });
    const cols = clamp(Math.ceil(Math.sqrt(tables.length * 1.3)), 1, 6);
    const heights = new Array(cols).fill(20), box = new Map();
    order.forEach((id) => {
      const t = N.get(id), n = (t.columns || []).length;
      const rows = Math.min(n, MAXROWS) + (n > MAXROWS ? 1 : 0) || 1;
      const h = HEAD + rows * ROW + 8;
      let c = 0;
      for (let k = 1; k < cols; k++) if (heights[k] < heights[c] - 1) c = k;
      box.set(id, { x: 20 + c * (BW + GAPX), y: heights[c], w: BW, h, t });
      heights[c] += h + GAPY;
    });
    const W = 40 + cols * BW + (cols - 1) * GAPX, H = Math.max(...heights) + 20;
    const P = [`<defs><marker id="erdArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" class="erd-arrowhead"/></marker></defs>`];
    links.forEach((l) => {
      const a = box.get(l.from), b = box.get(l.to);
      const ri = Math.min(l.ci, MAXROWS);
      const ya = a.y + HEAD + ri * ROW + ROW / 2, yb = b.y + HEAD / 2;
      let d;
      if (l.from === l.to) d = `M${a.x + a.w},${ya} C${a.x + a.w + 50},${ya} ${a.x + a.w + 50},${yb} ${a.x + a.w},${yb}`;
      else if (Math.abs(a.x - b.x) < 1) d = `M${a.x + a.w},${ya} C${a.x + a.w + 60},${ya} ${b.x + b.w + 60},${yb} ${b.x + b.w},${yb}`;
      else {
        const right = b.x > a.x, xa = right ? a.x + a.w : a.x, xb = right ? b.x : b.x + b.w, k = (right ? 1 : -1) * Math.max(40, Math.abs(xb - xa) / 2);
        d = `M${xa},${ya} C${xa + k},${ya} ${xb - k},${yb} ${xb},${yb}`;
      }
      P.push(`<path class="erd-link" data-from="${esc(l.from)}" data-to="${esc(l.to)}" d="${d}" marker-end="url(#erdArrow)"/>`);
    });
    box.forEach((b, id) => {
      const t = b.t, cs = t.columns || [];
      P.push(`<g class="erd-table${id === focusTable ? ' focus' : ''}" data-id="${esc(id)}" tabindex="0" role="button" aria-label="${esc(t.name + ', ' + plural(cs.length, 'column'))}">` +
        `<rect class="erd-box" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="6"/>` +
        `<rect class="erd-head" x="${b.x}" y="${b.y}" width="${b.w}" height="${HEAD}" rx="6"/><rect class="erd-head" x="${b.x}" y="${b.y + HEAD - 6}" width="${b.w}" height="6"/>` +
        `<text class="erd-name" x="${b.x + 12}" y="${b.y + 20}">${esc(shortName(t.name, 26))}${t.subkind === 'view' ? ' (view)' : ''}</text>` +
        (cs.length ? cs.slice(0, MAXROWS).map((c, i) => {
          const y = b.y + HEAD + i * ROW + 14;
          return `<text class="erd-col${c.pk ? ' pk' : ''}" x="${b.x + 12}" y="${y}">${c.pk ? '<tspan class="erd-key">PK </tspan>' : c.fk ? '<tspan class="erd-key">FK </tspan>' : ''}${esc(shortName(c.name, 22))}</text>` +
            `<text class="erd-type" x="${b.x + b.w - 10}" y="${y}" text-anchor="end">${esc(shortName(c.type || '', 14))}</text>`;
        }).join('') + (cs.length > MAXROWS ? `<text class="erd-type" x="${b.x + 12}" y="${b.y + HEAD + MAXROWS * ROW + 14}">and ${cs.length - MAXROWS} more…</text>` : '')
          : `<text class="erd-type" x="${b.x + 12}" y="${b.y + HEAD + 14}">columns not read</text>`) + `</g>`);
    });
    erdSvg.innerHTML = P.join('');
    erdView = { x: 0, y: 0, w: W, h: H, W, H };
    fitErd();
    $('#erdTitle').textContent = `${db.name}: schema`;
    $('#erdNote').textContent = `${plural(tables.length, 'table')}, ${plural(links.length, 'foreign key')}. Arrows point from a foreign key to the table it references. Click a table to walk to it.`;
    erd.hidden = false;
    erdSvg.querySelectorAll('.erd-table').forEach((g) => {
      const go = () => { closeErd(); focusNode(g.dataset.id); };
      g.addEventListener('click', () => { if (!erdSvg._dragged) go(); });
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      g.addEventListener('mouseenter', () => erdHighlight(g.dataset.id));
      g.addEventListener('mouseleave', () => erdHighlight(erdFocus));
      g.addEventListener('focus', () => erdHighlight(g.dataset.id));
    });
    erdHighlight(focusTable);
    const first = erdSvg.querySelector('.erd-table.focus') || erdSvg.querySelector('.erd-table');
    if (first) first.focus({ preventScroll: true });
  }
  function erdHighlight(id) {
    erdSvg.querySelectorAll('.erd-link').forEach((p) => {
      const touches = p.dataset.from === id || p.dataset.to === id;
      p.classList.toggle('on', !!id && touches);
      p.classList.toggle('dim', !!id && !touches);
    });
  }
  function fitErd() {
    const r = erdSvg.getBoundingClientRect(), ar = (r.width || 800) / Math.max(1, r.height || 500);
    let w = erdView.W + 40, h = erdView.H + 40;
    if (w / h < ar) w = h * ar; else h = w / ar;
    Object.assign(erdView, { x: (erdView.W - w) / 2, y: (erdView.H - h) / 2, w, h });
    erdSvg.setAttribute('viewBox', `${erdView.x} ${erdView.y} ${erdView.w} ${erdView.h}`);
  }
  function closeErd() { erd.hidden = true; erdSvg.innerHTML = ''; }
  $('#erdClose').addEventListener('click', closeErd);
  erd.addEventListener('click', (e) => { if (e.target === erd) closeErd(); });
  (function erdPanZoom() {
    let down = null;
    const setVB = () => erdSvg.setAttribute('viewBox', `${erdView.x} ${erdView.y} ${erdView.w} ${erdView.h}`);
    erdSvg.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, vx: erdView.x, vy: erdView.y }; erdSvg._dragged = false; });
    erdSvg.addEventListener('pointermove', (e) => {
      if (!down) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!erdSvg._dragged && Math.hypot(dx, dy) > 4) erdSvg._dragged = true;
      if (!erdSvg._dragged) return;
      const k = erdView.w / erdSvg.clientWidth;
      erdView.x = down.vx - dx * k; erdView.y = down.vy - dy * k;
      setVB();
    });
    const up = () => { down = null; setTimeout(() => { erdSvg._dragged = false; }, 0); };
    erdSvg.addEventListener('pointerup', up);
    erdSvg.addEventListener('pointerleave', up);
    erdSvg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const f = Math.exp(e.deltaY * 0.0012), r = erdSvg.getBoundingClientRect();
      const mx = erdView.x + ((e.clientX - r.left) / r.width) * erdView.w, my = erdView.y + ((e.clientY - r.top) / r.height) * erdView.h;
      const nw = clamp(erdView.w * f, 120, 8000), k = nw / erdView.w;
      erdView.x = mx - (mx - erdView.x) * k; erdView.y = my - (my - erdView.y) * k; erdView.w = nw; erdView.h *= k;
      setVB();
    }, { passive: false });
  })();
  onEscape(12, () => !erd.hidden, () => closeErd());

  // ── export: pictures and share cards ─────────────────────────────────────
  // A picture is the view itself (3D or floor plan) without the panels around it.
  // A share card is 1200 x 630: the picture plus what is being shown (a route, a
  // trace, a tour stop or one block) and the commit it was drawn from.
  const exportBtn = $('#exportBtn'), exportMenu = $('#exportMenu');
  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'view';

  function canvasToBlob(c) { return new Promise((res) => c.toBlob((b) => res(b), 'image/png')); }
  function planStyles() {
    const cs = getComputedStyle(document.documentElement);
    const v = (k) => cs.getPropertyValue(k).trim();
    return `text{font-family:"Barlow Condensed","Arial Narrow",sans-serif;fill:${v('--ink')}}.zone-name{font-weight:700;fill:${v('--muted')};opacity:.5}` +
      `.dim{opacity:.18}.lnk{fill:none;stroke-linecap:round}.off{display:none}`;
  }
  /** The current view as a canvas: the 3D scene, or the floor plan drawn from its SVG. */
  async function viewCanvas(fit) {
    if (!planOn && renderer) {
      renderer.render(scene, camera);   // read right after drawing: no preserveDrawingBuffer needed
      const src = renderer.domElement, c = document.createElement('canvas');
      c.width = src.width; c.height = src.height;
      c.getContext('2d').drawImage(src, 0, 0);
      return c;
    }
    if (!planOn && !fit) {   // no WebGL and the plan is hidden: picture the floor plan at window size
      fit = { width: window.innerWidth, height: Math.max(1, window.innerHeight - 70) };
      drawPlan();
    }
    const r = fit || plan.getBoundingClientRect(), k = Math.min(2, window.devicePixelRatio || 1);
    const clone = plan.cloneNode(true);
    clone.removeAttribute('hidden');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', r.width);
    clone.setAttribute('height', r.height);
    if (fit) {   // frame the whole room for the card instead of the window's pan and zoom
      let w = room.W + 6, h = room.D + 8;
      if (w / h < r.width / r.height) w = h * r.width / r.height; else h = w * r.height / r.width;
      clone.setAttribute('viewBox', `${-w / 2} ${-h / 2 - 2} ${w} ${h}`);
      clone.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    }
    const st = document.createElementNS('http://www.w3.org/2000/svg', 'style');
    st.textContent = planStyles();
    clone.insertBefore(st, clone.firstChild);
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
    try {
      const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
      const c = document.createElement('canvas');
      c.width = Math.round(r.width * k); c.height = Math.round(r.height * k);
      const ctx = c.getContext('2d');
      ctx.fillStyle = css(T.bg); ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      return c;
    } finally { URL.revokeObjectURL(url); }
  }

  function cardFacts() {
    const name = (id) => (N.get(id) || { name: id }).name;
    const TC = T.trace;
    if (player) {
      const st = player.stops[player.i];
      return { kicker: player.kind === 'route' ? 'Route' : 'Tour', color: TC.route, title: player.title,
        sub: `Stop ${player.i + 1} of ${player.stops.length}: ${st.title || name(st.id)}`,
        lines: player.stops.slice(0, 7).map((s, k) => `${k + 1}. ${s.title || name(s.id)}`) };
    }
    if (trace && trace.mode === 'route') {
      if (!trace.path) return { kicker: 'Route', color: TC.route, title: `${name(trace.a)} to ${name(trace.b)}`, sub: 'No recorded path in this direction', lines: [] };
      return { kicker: 'Route', color: TC.route, title: `${name(trace.a)} to ${name(trace.b)}`,
        sub: `${plural(trace.stops.length, 'stop')}${trace.loose ? ', loose (block to block in places)' : ', through recorded connections'}`,
        lines: trace.stops.slice(0, 7).map((s, k) => `${k + 1}. ${name(s.id)}${k && s.edge ? `  (${EDGE_LABEL[s.edge.kind] || s.edge.kind})` : ''}`) };
    }
    if (trace) {
      const down = trace.mode === 'down', groups = new Map(), startRep = projector(room.R)(trace.id);
      (MARK.hop || new Map()).forEach((d, id) => { if (id !== startRep) { if (!groups.has(d)) groups.set(d, []); groups.get(d).push(name(id)); } });
      const reached = [...groups.values()].reduce((s, g) => s + g.length, 0);
      return { kicker: down ? 'Downstream' : 'Upstream', color: TC[trace.mode], title: down ? `Where ${name(trace.id)} leads` : `What leads to ${name(trace.id)}`,
        sub: reached ? `${plural(reached, 'place')}, up to ${hops(Math.max(...groups.keys()))} away` : 'Nothing recorded',
        lines: [...groups.keys()].sort((a, b) => a - b).slice(0, 6).map((d) => `${d ? hops(d) : 'Same block'}: ${groups.get(d).sort().join(', ')}`) };
    }
    if (selected && selected.type !== 'link') {
      const n = N.get(selected.id), conns = connectionsOf(selected.id);
      const outs = conns.filter((g) => g.dir === 'out').map((g) => name(g.rep)), ins = conns.filter((g) => g.dir === 'in').map((g) => name(g.rep));
      return { kicker: KIND_LABEL[n.kind] || n.kind, color: kindHex(n.kind), title: n.name,
        sub: String(n.purpose || n.description || '').split(/(?<=[.!?])\s/)[0],
        lines: [outs.length ? `Reaches out to: ${outs.slice(0, 6).join(', ')}` : '', ins.length ? `Used by: ${ins.slice(0, 6).join(', ')}` : ''].filter(Boolean) };
    }
    const tops = kidsOf(ROOT).map((id) => N.get(id));
    const zoneLine = (z, label) => { const xs = tops.filter((n) => n.layer === z).map((n) => n.name); return xs.length ? `${label}: ${xs.slice(0, 5).join(', ')}${xs.length > 5 ? ` +${xs.length - 5}` : ''}` : ''; };
    return { kicker: 'Architecture', color: T.trace.route, title: `${D.project.name} warehouse`,
      sub: `${plural(tops.length, 'block')} on the main floor, ${plural(roomLinks(ROOT).inner.length, 'pipe')} between them`,
      lines: [zoneLine('clients', 'Clients'), zoneLine('edge', 'Gateway and auth'), zoneLine('services', 'Services'), zoneLine('data', 'Data'), zoneLine('external', 'Loading dock')].filter(Boolean) };
  }
  function wrap(ctx, text, maxW, maxLines) {
    const words = String(text).split(/\s+/), out = [];
    let cur = '';
    for (const w of words) {
      const t = cur ? cur + ' ' + w : w;
      if (ctx.measureText(t).width > maxW && cur) { out.push(cur); cur = w; } else cur = t;
      if (out.length === maxLines) break;
    }
    if (out.length < maxLines && cur) out.push(cur);
    if (out.length === maxLines && words.join(' ').length > out.join(' ').length) out[maxLines - 1] = out[maxLines - 1].replace(/\s*\S*$/, '') + '…';
    return out;
  }
  async function shareCard() {
    const view = await viewCanvas(planOn ? { width: 730, height: 630 } : null);
    const W = 1200, H = 630, c = document.createElement('canvas');
    c.width = W; c.height = H;
    const ctx = c.getContext('2d'), f = cardFacts(), night = T.glow;
    ctx.fillStyle = css(T.bg); ctx.fillRect(0, 0, W, H);
    // the view, cover-fitted to the right of the text column
    const L = 470, vw = W - L, s = Math.max(vw / view.width, H / view.height);
    const sw = vw / s, sh = H / s;
    ctx.drawImage(view, (view.width - sw) / 2, (view.height - sh) / 2, sw, sh, L, 0, vw, H);
    const g = ctx.createLinearGradient(L - 2, 0, L + 90, 0);
    g.addColorStop(0, css(T.bg)); g.addColorStop(1, night ? 'rgba(7,11,22,0)' : 'rgba(223,226,228,0)');
    ctx.fillStyle = g; ctx.fillRect(L - 2, 0, 92, H);
    ctx.fillStyle = css(T.bg); ctx.fillRect(0, 0, L, H);
    // hazard stripe
    for (let x = -30; x < L + 30; x += 24) {
      ctx.fillStyle = night ? '#ffb23f' : '#f2c230';
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + 12, 0); ctx.lineTo(x + 2, 10); ctx.lineTo(x - 10, 10); ctx.closePath(); ctx.fill();
    }
    const ink = night ? '#eef2f8' : '#1b2330', muted = night ? '#93a0b8' : '#5a6474';
    let y = 54;
    ctx.fillStyle = muted; ctx.font = '600 20px "Barlow Condensed", "Arial Narrow", sans-serif';
    ctx.fillText(`WIREHOUSE · ${String(D.project.name).toUpperCase()}`, 40, y);
    y += 26;
    ctx.font = '700 17px "Barlow Condensed", "Arial Narrow", sans-serif';
    const kw = ctx.measureText(f.kicker.toUpperCase()).width + 18;
    ctx.fillStyle = css(f.color); ctx.fillRect(40, y, kw, 26);
    ctx.fillStyle = '#0b0f17'; ctx.fillText(f.kicker.toUpperCase(), 49, y + 19);
    y += 46;
    ctx.fillStyle = ink; ctx.font = '700 46px "Barlow Condensed", "Arial Narrow", sans-serif';
    wrap(ctx, f.title, L - 70, 3).forEach((t) => { y += 44; ctx.fillText(t, 40, y); });
    y += 34;
    ctx.fillStyle = muted; ctx.font = '500 20px "Barlow", "Segoe UI", sans-serif';
    wrap(ctx, f.sub, L - 70, 2).forEach((t) => { ctx.fillText(t, 40, y); y += 26; });
    y += 12;
    ctx.fillStyle = ink; ctx.font = '500 18px "Barlow", "Segoe UI", sans-serif';
    for (const line of f.lines) {
      const ls = wrap(ctx, line, L - 70, 2);
      if (y + ls.length * 24 > H - 60) break;
      ls.forEach((t) => { ctx.fillText(t, 40, y); y += 24; });
      y += 4;
    }
    ctx.fillStyle = muted; ctx.font = '500 15px "Barlow", "Segoe UI", sans-serif';
    const place = room && room.R ? chain(room.R).reverse().map((id) => N.get(id).name).join(' / ') : 'main floor';
    ctx.fillText(`Recorded connections only · ${place}${REPO && REPO.short ? ` · commit ${REPO.short}` : ''}`, 40, H - 30);
    return { canvas: c, name: `${slug(D.project.name)}-${slug(f.kicker + '-' + f.title)}.png` };
  }
  async function download(canvas, name) {
    const blob = await canvasToBlob(canvas);
    if (!blob) { toast('This view could not be turned into a picture', 2600); return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    EXPORTS.push({ name, width: canvas.width, height: canvas.height, bytes: blob.size });
    toast(`Saved ${name}`, 2000);
  }
  const EXPORTS = [];   // receipts, for the automated checks
  const EXPORT_ACTS = {
    png: async () => download(await viewCanvas(), `${slug(D.project.name)}-${planOn ? 'floor-plan' : 'warehouse'}.png`),
    card: async () => { const c = await shareCard(); download(c.canvas, c.name); },
    copy: () => {
      // ClipboardItem must be created inside the click; it takes a promise of the image
      if (!navigator.clipboard || !window.ClipboardItem) { toast('This browser cannot copy pictures; use Save instead', 2600); return; }
      const blob = viewCanvas().then(canvasToBlob);
      navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]).then(() => toast('Picture copied'), () => toast('Copying was blocked; use Save instead', 2600));
    },
  };
  function toggleExport(on) {
    exportMenu.hidden = on == null ? !exportMenu.hidden : !on;
    exportBtn.setAttribute('aria-expanded', String(!exportMenu.hidden));
    if (!exportMenu.hidden) {
      const what = cardFacts();
      $('#exportCardSub').textContent = `${what.kicker}: ${shortName(what.title, 40)}`;
      exportMenu.querySelector('button').focus();
    }
  }
  exportBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleExport(); });
  exportMenu.querySelectorAll('[data-x]').forEach((b) => b.addEventListener('click', () => { toggleExport(false); EXPORT_ACTS[b.dataset.x](); }));
  exportMenu.addEventListener('keydown', (e) => {
    const items = [...exportMenu.querySelectorAll('button')], i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length].focus(); }
  });
  document.addEventListener('click', (e) => { if (!exportMenu.hidden && !exportMenu.contains(e.target)) toggleExport(false); });
  KEYS.x = () => toggleExport();
  onEscape(11, () => !exportMenu.hidden, () => { toggleExport(false); exportBtn.focus(); });

  // ── changes: what moved since an earlier map ─────────────────────────────
  // Only present when the page was rendered with --against. Removed things are listed, never drawn:
  // they are no longer in the code.
  const changesBtn = $('#changesBtn'), changesMenu = $('#changesMenu');
  function drawChanges() {
    if (!DELTA) return;
    const b = DELTA.blocks, f = DELTA.files, L = DELTA.links;
    const go = (id) => `<button type="button" data-go="${esc(id)}">${esc(N.get(id) ? N.get(id).name : id)}</button>`;
    const list = (title, items) => items.length ? `<h3>${esc(title)}</h3><ul>${items.join('')}</ul>` : '';
    const since = DELTA.against && DELTA.against.commit ? `commit ${esc(DELTA.against.commit)}` : 'the earlier map';
    const pair = (k) => { const [a, c] = k.split('->'); return `${go(a)} → ${go(c)}`; };
    const more = (n, shown) => n > shown ? [`<li class="gone">…and ${n - shown} more</li>`] : [];
    changesMenu.innerHTML = `<p class="lead">Compared with ${since}. Blocks count as changed when the code inside them did.</p>` +
      list('Blocks', b.added.map((i) => `<li><span class="tag">new</span>${go(i)}</li>`)
        .concat(b.changed.map((i) => `<li><span class="tag">changed</span>${go(i)}</li>`))
        .concat(b.removed.map((r) => `<li class="gone"><span class="tag">removed</span>${esc(r.name)} (no longer in the code)</li>`))) +
      list('Connections', L.added.map((k) => `<li><span class="tag">new</span>${pair(k)}</li>`)
        .concat(L.changed.map((k) => `<li><span class="tag">changed</span>${pair(k)}</li>`))
        .concat(L.removed.map((r) => `<li class="gone"><span class="tag">removed</span>${esc(r.source_name)} → ${esc(r.target_name)}</li>`))) +
      list('Files', f.added.slice(0, 40).map((i) => `<li><span class="tag">new</span>${go(i)}</li>`).concat(more(f.counts.added, Math.min(40, f.added.length)))
        .concat(f.changed.slice(0, 40).map((i) => `<li><span class="tag">changed</span>${go(i)}</li>`)).concat(more(f.counts.changed, Math.min(40, f.changed.length)))
        .concat(f.removed.slice(0, 20).map((r) => `<li class="gone"><span class="tag">removed</span>${esc(r.path || r.name)}</li>`)).concat(more(f.counts.removed, Math.min(20, f.removed.length)))) +
      `<div class="acts"><button type="button" class="ghost small" data-floor>${changesOn ? 'Hide on the floor' : 'Show on the floor'}</button></div>`;
    changesMenu.querySelectorAll('[data-go]').forEach((el) => el.addEventListener('click', () => { toggleChanges(false); focusNode(el.dataset.go); }));
    // the redraw detaches the clicked button, so the outside-click check must not see this click
    changesMenu.querySelector('[data-floor]').addEventListener('click', (e) => { e.stopPropagation(); setChangesOn(!changesOn); });
  }
  function setChangesOn(on) {
    changesOn = !!(on && DELTA);
    refreshMarks(); drawChanges(); syncHash();
  }
  function toggleChanges(on) {
    changesMenu.hidden = on == null ? !changesMenu.hidden : !on;
    changesBtn.setAttribute('aria-expanded', String(!changesMenu.hidden));
  }
  if (DELTA) {
    const n = DELTA.blocks.counts.added + DELTA.blocks.counts.changed + DELTA.blocks.counts.removed +
      DELTA.links.added.length + DELTA.links.removed.length + DELTA.links.changed.length;
    $('#changesWrap').hidden = false;
    changesBtn.textContent = `Changes · ${n}`;
    drawChanges();
  }
  changesBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleChanges(); });
  document.addEventListener('click', (e) => { if (!changesMenu.hidden && !changesMenu.contains(e.target)) toggleChanges(false); });
  onEscape(14, () => !changesMenu.hidden, () => { toggleChanges(false); changesBtn.focus(); });
  KEYS.v = () => { if (DELTA) toggleChanges(); };
  HASH_PARTS.push(() => (changesOn ? 'changes=1' : null));
  HASH_APPLY.push((h) => { if ((h.changes === '1') !== changesOn) setChangesOn(h.changes === '1'); });

  // ── checks: what the render left out ─────────────────────────────────────
  // Every part the agent wrote was checked against the scan (node ids, files, lines, secrets). What
  // failed is listed here, so a reader knows the page is missing it rather than that it was never written.
  const DIAGS = D.diagnostics || [];
  const MAX_CHECKS = 60;
  const checksBtn = $('#checksBtn'), checksMenu = $('#checksMenu');
  if (DIAGS.length) {
    const errors = DIAGS.filter((d) => d.severity === 'error').length;
    $('#checksWrap').hidden = false;
    checksBtn.textContent = `Checks · ${DIAGS.length}`;
    checksBtn.classList.toggle('warn', errors > 0);
    checksMenu.innerHTML = `<p class="lead">Wirehouse checked every node id, file, line and secret in the agent's notes. ` +
      `${errors ? `${plural(errors, 'error')} left parts out of this page` : 'Nothing was left out'}` +
      `${DIAGS.length - errors ? `; ${plural(DIAGS.length - errors, 'warning')} worth a look` : ''}.</p><ol>` +
      DIAGS.slice(0, MAX_CHECKS).map((d) => `<li class="${d.severity === 'error' ? 'error' : 'warning'}"><b>${esc(d.code)}</b>` +
        `<span class="subj">${esc(d.subject)}</span><p>${esc(d.message)}</p><p class="fix">${esc(d.fix)}</p></li>`).join('') + '</ol>' +
      (DIAGS.length > MAX_CHECKS ? `<p class="lead">…and ${DIAGS.length - MAX_CHECKS} more in archmap.json.</p>` : '');
  }
  function toggleChecks(on) {
    checksMenu.hidden = on == null ? !checksMenu.hidden : !on;
    checksBtn.setAttribute('aria-expanded', String(!checksMenu.hidden));
  }
  checksBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleChecks(); });
  document.addEventListener('click', (e) => { if (!checksMenu.hidden && !checksMenu.contains(e.target)) toggleChecks(false); });
  onEscape(13, () => !checksMenu.hidden, () => { toggleChecks(false); checksBtn.focus(); });

  // ── breadcrumbs ──────────────────────────────────────────────────────────
  function drawCrumbs() {
    const nav = $('#crumbs');
    const parts = [{ id: ROOT, name: D.project.name }].concat(room.R ? chain(room.R).reverse().map((id) => ({ id, name: N.get(id).name })) : []);
    nav.innerHTML = parts.map((p, i) => (i ? '<span class="sep" aria-hidden="true">/</span>' : '') +
      `<button type="button" data-room="${esc(p.id)}" ${i === parts.length - 1 ? 'aria-current="location"' : ''} title="${esc(p.name)}">${esc(p.name)}</button>`).join('');
    nav.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      if (b.hasAttribute('aria-current')) return;
      const target = b.dataset.room;
      const from = room.R ? chain(room.R).find((x) => parentOf(x) === target) : null;
      goRoom(target, { from });
    }));
    nav.scrollLeft = nav.scrollWidth;
  }

  // ── search ───────────────────────────────────────────────────────────────
  const INDEX = D.nodes.map((n) => ({ n, name: n.name.toLowerCase(), path: String(n.path || '').toLowerCase() }));
  const sIn = $('#search'), sOut = $('#results');
  let sSel = 0, sHits = [];
  function runSearch() {
    const q = sIn.value.trim().toLowerCase();
    if (!q) { sOut.hidden = true; return; }
    const terms = q.split(/\s+/);
    sHits = INDEX.map((r) => {
      let s = 0;
      if (r.name === q) s += 100;
      else if (r.name.startsWith(q)) s += 60;
      else if (r.name.includes(q)) s += 40;
      if (terms.every((t) => r.name.includes(t) || r.path.includes(t))) s += 20; else if (!s) return null;
      if (!r.n.parent) s += 15;
      if (r.n.kind === 'module') s += 6;
      if (r.n.test) s -= 8;
      s -= r.name.length * 0.05;
      return s > 0 ? { r, s } : null;
    }).filter(Boolean).sort((a, b) => b.s - a.s).slice(0, 12);
    sSel = 0;
    sOut.innerHTML = sHits.length ? sHits.map((h, i) => {
      const n = h.r.n;
      const place = n.parent ? chain(n.parent).reverse().map((x) => N.get(x).name).join(' / ') : 'the main floor';
      return `<li role="option" data-i="${i}" aria-selected="${i === 0}"><span class="dot" style="background:${css(kindHex(n.kind))}"></span><span class="nm">${esc(n.name)}</span><span class="where">${esc(KIND_LABEL[n.kind] || n.kind)} in ${esc(place)}</span></li>`;
    }).join('') : `<li class="empty">Nothing matches "${esc(sIn.value)}". Try a folder, file or service name.</li>`;
    sOut.hidden = false;
    sOut.querySelectorAll('li[data-i]').forEach((li) => li.addEventListener('mousedown', (e) => { e.preventDefault(); pickResult(+li.dataset.i); }));
  }
  function pickResult(i) {
    const h = sHits[i];
    if (!h) return;
    sOut.hidden = true;
    sIn.value = '';
    sIn.blur();
    focusNode(h.r.n.id);
  }
  sIn.addEventListener('input', runSearch);
  sIn.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sSel = clamp(sSel + (e.key === 'ArrowDown' ? 1 : -1), 0, Math.max(0, sHits.length - 1));
      sOut.querySelectorAll('li[data-i]').forEach((li) => li.setAttribute('aria-selected', String(+li.dataset.i === sSel)));
    } else if (e.key === 'Enter') { e.preventDefault(); pickResult(sSel); }
    else if (e.key === 'Escape') { sIn.value = ''; sOut.hidden = true; sIn.blur(); }
  });
  sIn.addEventListener('blur', () => setTimeout(() => { sOut.hidden = true; }, 120));

  // ── minimap ──────────────────────────────────────────────────────────────
  const mm = $('#minimap');
  const mctx = mm.getContext('2d');
  let mmT = null;
  function drawMinimap() {
    const dpr = window.devicePixelRatio || 1;
    const cw = mm.clientWidth, ch = mm.clientHeight;
    const pw = Math.round(cw * dpr), ph = Math.round(ch * dpr);
    if (mm.width !== pw || mm.height !== ph) { mm.width = pw; mm.height = ph; }
    mctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    mctx.clearRect(0, 0, cw, ch);
    const pad = 8, s = Math.min((cw - pad * 2) / room.W, (ch - pad * 2) / room.D);
    const ox = cw / 2, oz = ch / 2;
    mmT = { s, ox, oz };
    const X = (x) => ox + x * s, Z = (z) => oz + z * s;
    mctx.fillStyle = css(T.floor); mctx.strokeStyle = css(T.wallLine); mctx.lineWidth = 1.5;
    mctx.fillRect(X(-room.W / 2), Z(-room.D / 2), room.W * s, room.D * s);
    mctx.strokeRect(X(-room.W / 2), Z(-room.D / 2), room.W * s, room.D * s);
    room.zones.forEach((Zn, i) => { mctx.fillStyle = i % 2 ? css(T.floorAlt) : css(T.floor); mctx.fillRect(X(Zn.x0) + 1, Z(Zn.z0) + 1, (Zn.x1 - Zn.x0) * s - 2, (Zn.z1 - Zn.z0) * s - 2); });
    mctx.globalAlpha = 0.5;
    room.racks.forEach((r) => { mctx.fillStyle = css(T.wallLine); mctx.fillRect(X(r.x - r.w / 2), Z(r.z - r.d / 2), r.w * s, r.d * s); });
    mctx.globalAlpha = 1;
    room.items.forEach((it) => {
      if (it.shape === 'slot') return;
      mctx.fillStyle = css(kindHex(N.get(it.id).kind));
      mctx.fillRect(X(it.x - it.w / 2), Z(it.z - it.d / 2), Math.max(2, it.w * s), Math.max(2, it.d * s));
    });
    room.ports.forEach((p) => { mctx.fillStyle = css(kindHex(N.get(p.rep).kind)); mctx.fillRect(X(p.x) - 2, Z(p.z) - 2, 4, 4); });
    if (selected && selected.type !== 'link' && itemsById.has(selected.id)) {
      const it = itemsById.get(selected.id);
      const z = it.shape === 'slot' ? it.rack.z : it.z, d = it.shape === 'slot' ? it.rack.d : it.d;
      mctx.strokeStyle = T.glow ? '#ffb23f' : '#1f6fd1'; mctx.lineWidth = 2;
      mctx.strokeRect(X(it.x - it.w / 2) - 2, Z(z - d / 2) - 2, it.w * s + 4, d * s + 4);
    }
    mctx.save();
    mctx.translate(X(W8.pos.x), Z(W8.pos.z));
    mctx.rotate(-W8.yaw + Math.PI);
    mctx.fillStyle = '#ff7a1a'; mctx.strokeStyle = '#fff'; mctx.lineWidth = 1.2;
    mctx.beginPath(); mctx.moveTo(0, -7); mctx.lineTo(5, 5); mctx.lineTo(-5, 5); mctx.closePath(); mctx.fill(); mctx.stroke();
    mctx.restore();
  }
  mm.addEventListener('click', (e) => {
    if (!mmT || planOn) return;
    const r = mm.getBoundingClientRect();
    travelToPoint((e.clientX - r.left - mmT.ox) / mmT.s, (e.clientY - r.top - mmT.oz) / mmT.s);
  });

  // The pipe key doubles as a filter: switch a kind of connection off to hide its
  // pipes (and leave it out of traces). A pipe carrying several kinds stays while
  // any of them is on.
  const HIDE = new Set();
  const shownKinds = (kinds) => { for (const k of kinds) if (!HIDE.has(k)) return true; return false; };
  function keyCounts() {
    const c = {};
    const add = (kinds) => kinds.forEach((k) => { c[k] = (c[k] || 0) + 1; });
    if (room) {
      (room.links || []).forEach((L) => add(L.kinds));
      room.ports.forEach((p) => p.inners.forEach((info) => add(info.kinds)));
    }
    return c;
  }
  function drawKey() {
    const c = keyCounts();
    const kinds = Object.keys(EDGE_LABEL).filter((k) => c[k] || HIDE.has(k));
    $('#key').innerHTML = (kinds.length ? kinds.map((k) => `<button type="button" data-k="${k}" aria-pressed="${!HIDE.has(k)}" title="${HIDE.has(k) ? 'Show' : 'Hide'} pipes that ${esc(EDGE_LABEL[k])}">` +
      `<i style="background:${css(edgeHex(k))}"></i><span>${esc(EDGE_LABEL[k][0].toUpperCase() + EDGE_LABEL[k].slice(1))}</span><b>${c[k] || 0}</b></button>`).join('')
      : '<p class="note">No pipes in this room.</p>') +
      (HIDE.size ? '<button type="button" class="all" data-k="*">Show every kind</button>' : '');
    $('#key').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      const k = b.dataset.k;
      if (k === '*') HIDE.clear(); else if (HIDE.has(k)) HIDE.delete(k); else HIDE.add(k);
      drawKey();
      applyFocus();
      FILTER_HOOKS.forEach((f) => f());
      const again = $(`#key button[data-k="${k}"]`);
      if (again) again.focus();
    }));
    $('#keyBtn').textContent = ($('#key').hidden ? 'Pipe key' : 'Hide pipe key') + (HIDE.size ? ` (${HIDE.size} off)` : '');
    $('#keyBtn').setAttribute('aria-expanded', String(!$('#key').hidden));
  }
  BUILD_HOOKS.push(drawKey);
  $('#keyBtn').addEventListener('click', () => { const k = $('#key'); k.hidden = !k.hidden; drawKey(); });

  // What a trace, route or tour has lit up in the current room (set by the trace section).
  const MARK = { lit: null, ids: null };
  function litLinks() { return MARK.lit; }
  function markedIds() { return MARK.ids; }

  // ── 2D floor plan ────────────────────────────────────────────────────────
  const plan = $('#plan');
  let planOn = false, planView = null;
  function fitPlan() {
    const W = room.W + 8, H = room.D + 8;
    const ar = window.innerWidth / Math.max(1, window.innerHeight - 70);
    let w = W, h = H;
    if (w / h < ar) w = h * ar; else h = w / ar;
    planView = { x: -w / 2, y: -h / 2 - 3, w, h };
  }
  function setViewBox() { plan.setAttribute('viewBox', `${planView.x} ${planView.y} ${planView.w} ${planView.h}`); }
  function drawPlan() {
    if (!planView) fitPlan();
    const P = [];
    const ink = css(T.wallLine);
    P.push(`<defs>${Object.keys(T.edge).map((k) => `<marker id="ar-${k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="${css(edgeHex(k))}"/></marker>`).join('')}</defs>`);
    P.push(`<rect x="${-room.W / 2}" y="${-room.D / 2}" width="${room.W}" height="${room.D}" fill="${css(T.floor)}" stroke="${ink}" stroke-width="0.3"/>`);
    P.push(`<rect x="-2.2" y="${room.D / 2 - 0.3}" width="4.4" height="0.6" fill="${css(T.bg)}"/>`);
    room.zones.forEach((Z, i) => {
      P.push(`<rect x="${Z.x0 + 0.4}" y="${Z.z0 + 0.4}" width="${Z.x1 - Z.x0 - 0.8}" height="${Z.z1 - Z.z0 - 0.8}" fill="${css(i % 2 ? T.floorAlt : T.floor)}" stroke="${css(T.paint)}" stroke-width="0.15" stroke-dasharray="1 0.6"/>`);
      const txt = Z.empty && Z.id === 'edge' ? 'Gateway and auth: none found' : Z.name;
      P.push(Z.side ? `<text class="zone-name" x="${(Z.x0 + Z.x1) / 2}" y="${Z.z1 - 3}" font-size="1.6" text-anchor="middle">${esc(txt)}</text>`
        : `<text class="zone-name" x="${Z.x0 + 1.5}" y="${Z.z1 - 1.3}" font-size="2">${esc(txt)}</text>`);
    });
    room.racks.forEach((r) => P.push(`<rect x="${r.x - r.w / 2}" y="${r.z - r.d / 2 - 0.7}" width="${r.w}" height="${r.d + 1.4}" fill="none" stroke="${ink}" stroke-width="0.12" rx="0.2"/>`));
    const pos = new Map();
    room.items.forEach((it) => {
      // racks are drawn flat: each shelf level becomes a row so every slot stays visible
      if (it.shape === 'slot') {
        const lvl = Math.round((it.y - 0.32) / 1.2);
        pos.set(it.id, { x: it.x, z: it.z - 0.7 + lvl * 0.7, w: it.w, d: 0.6 });
      } else pos.set(it.id, { x: it.x, z: it.z, w: it.w, d: it.d });
    });
    const linkSvg = (L, A, B, i) => {
      const k = linkKind(L.kinds);
      const mx = (A.x + B.x) / 2, mz = (A.z + B.z) / 2;
      const dx = B.x - A.x, dz = B.z - A.z, len = Math.hypot(dx, dz) || 1;
      const off = Math.min(len * 0.18, 6);
      const cx = mx - (dz / len) * off, cz = mz + (dx / len) * off;
      const w = clamp(0.1 + Math.log2(L.count + 1) * 0.06, 0.1, 0.45);
      return `<path class="lnk" data-l="${i}" d="M${A.x},${A.z} Q${cx},${cz} ${B.x},${B.z}" stroke="${css(edgeHex(k))}" stroke-width="${w}" marker-end="url(#ar-${esc(k)})" opacity="0.85"/>`;
    };
    const planLinks = [];
    (room.links || []).forEach((L) => { const A = pos.get(L.a), B = pos.get(L.b); if (A && B) { planLinks.push(L); P.push(linkSvg(L, A, B, planLinks.length - 1)); } });
    room.ports.forEach((p) => p.inners.forEach((info) => {
      const I = pos.get(info.id); if (!I) return;
      const pp = { x: p.x, z: p.z };
      const L = Object.assign({ a: p.dir === 'out' ? info.id : p.rep, b: p.dir === 'out' ? p.rep : info.id }, info);
      planLinks.push(L);
      P.push(p.dir === 'out' ? linkSvg(L, I, pp, planLinks.length - 1) : linkSvg(L, pp, I, planLinks.length - 1));
    }));
    room.items.forEach((it) => {
      const n = N.get(it.id), q = pos.get(it.id);
      const col = css(kindHex(n.kind));
      const slot = it.shape === 'slot';
      const fs = slot ? 0.36 : clamp(it.w / 4.2, 1.0, 1.7);
      P.push(`<g class="blk" data-id="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.name + ', ' + (KIND_LABEL[n.kind] || n.kind) + (enterable(n.id) ? ', can be walked into' : ''))}"><rect x="${q.x - q.w / 2}" y="${q.z - q.d / 2}" width="${q.w}" height="${q.d}" rx="${slot ? 0.08 : 0.35}" fill="${col}" fill-opacity="${slot ? 0.8 : 0.28}" stroke="${col}" stroke-width="${slot ? 0.05 : 0.18}"/>` +
        (it.shape === 'silo' ? `<circle cx="${q.x}" cy="${q.z}" r="${q.w / 2 - 0.4}" fill="none" stroke="${col}" stroke-width="0.12"/>` : '') +
        `<text x="${q.x}" y="${slot ? q.z + 0.12 : q.z + 0.25}" font-size="${fs}" text-anchor="middle" font-weight="600">${esc(shortName(n.name, slot ? 14 : 24))}</text>` +
        (!slot ? `<text x="${q.x}" y="${q.z + 0.25 + fs * 1.05}" font-size="${fs * 0.62}" text-anchor="middle" opacity="0.7">${esc(n.kind === 'module' ? (n.stats ? n.stats.files : 0) + ' files' : (KIND_LABEL[n.kind] || n.kind))}</text>` : '') + `</g>`);
    });
    room.ports.forEach((p) => {
      const n = N.get(p.rep), col = css(kindHex(n.kind));
      P.push(`<g class="blk" data-id="${esc(n.id)}" data-port="1" tabindex="0" role="button" aria-label="${esc(n.name + ', outside this room')}"><rect x="${p.x - 2}" y="${p.z - 0.7}" width="4" height="1.4" rx="0.25" fill="${css(T.bg)}" stroke="${col}" stroke-width="0.18"/><text x="${p.x}" y="${p.z + 0.25}" font-size="0.7" text-anchor="middle">${esc(shortName(n.name, 16))}</text></g>`);
    });
    if (MARK.badges) MARK.badges.forEach((b, id) => {
      const it = itemsById.get(id);
      if (it && it.shape === 'slot') return;   // racks are too tight for badges: the highlight says it
      const q = pos.get(id) || (() => { const p = room.ports.find((x) => x.rep === id); return p ? { x: p.x, z: p.z, d: 1.4 } : null; })();
      if (!q) return;
      const w = Math.max(1.6, b.text.length * 0.42 + 0.6), y = q.z - q.d / 2 - 1.05;
      P.push(`<g class="badge${b.strong ? ' strong' : ''}"><rect x="${q.x - w / 2}" y="${y - 0.55}" width="${w}" height="1.1" rx="0.55" fill="${css(b.color)}"/>` +
        `<text x="${q.x}" y="${y + 0.28}" font-size="0.75" text-anchor="middle" font-weight="700" fill="${T.glow ? '#0b0f17' : '#ffffff'}">${esc(b.text)}</text></g>`);
    });
    P.push(`<g id="planMe"><circle r="0.6" fill="#ff7a1a" stroke="#fff" stroke-width="0.15"/></g>`);
    plan.innerHTML = `<g id="vp">${P.join('')}</g>`;
    plan._links = planLinks;
    setViewBox();
    plan.querySelectorAll('.blk').forEach((g) => {
      g.addEventListener('click', (e) => { e.stopPropagation(); if (plan._dragged) return; select(g.dataset.id, g.dataset.port ? { port: room.ports.find((p) => p.rep === g.dataset.id) } : {}); });
      g.addEventListener('dblclick', (e) => { e.stopPropagation(); if (g.dataset.port) focusNode(g.dataset.id); else if (enterable(g.dataset.id)) goRoom(g.dataset.id); });
      g.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        e.stopPropagation();
        const id = g.dataset.id, again = selected && selected.id === id;
        if (again && g.dataset.port) focusNode(id);
        else if (again && enterable(id)) goRoom(id, { then: () => { const f = plan.querySelector('.blk'); if (f) f.focus(); } });
        else select(id, g.dataset.port ? { port: room.ports.find((p) => p.rep === id) } : {});
      });
      g.addEventListener('mouseenter', () => { hovered = { type: 'node', id: g.dataset.id }; planFocus(); });
      g.addEventListener('mouseleave', () => { hovered = null; planFocus(); });
    });
    plan.querySelectorAll('.lnk').forEach((pth) => pth.addEventListener('click', (e) => { e.stopPropagation(); selectLink(plan._links[+pth.dataset.l]); }));
    planFocus();
    const me = plan.querySelector('#planMe');
    if (me) me.setAttribute('transform', `translate(${W8.pos.x},${W8.pos.z})`);
  }
  function planFocus() {
    if (!planOn) return;
    const trace = litLinks();
    const hov = hovered && hovered.type !== 'link' && hovered.id;
    const f = trace ? hov : hov || (selected && selected.type !== 'link' && selected.id);
    const sl = !trace && selected && selected.type === 'link' ? selected.info : null;
    const links = plan._links || [];
    const related = new Set();
    const lit = !f ? trace : null;
    const marked = !f && trace ? markedIds() : null;
    plan.querySelectorAll('.lnk').forEach((p) => {
      const L = links[+p.dataset.l];
      const on = sl ? (L.a === sl.a && L.b === sl.b) : f ? L.a === f || L.b === f : lit ? lit(L) : true;
      p.classList.toggle('dim', !on);
      p.classList.toggle('off', !shownKinds(L.kinds));
      if (on && (f || sl)) { related.add(L.a); related.add(L.b); }
    });
    plan.querySelectorAll('.blk').forEach((g) => g.classList.toggle('dim',
      marked ? !marked.has(g.dataset.id) : !!(f || sl) && !related.has(g.dataset.id) && g.dataset.id !== f));
  }
  function setPlan(on) {
    on = on || !renderer;
    planOn = on;
    plan.toggleAttribute('hidden', !on); // SVG elements have no .hidden property
    stage.style.visibility = on ? 'hidden' : 'visible';
    $('#minimapWrap').hidden = on;
    $('#view3d').classList.toggle('on', !on);
    $('#view2d').classList.toggle('on', on);
    $('#prompt').hidden = true;
    $('#tooltip').hidden = true;
    keys.clear();
    if (on) { planView = null; if (room) drawPlan(); }   // before the first room, goRoom draws it
    else if (canvas) canvas.focus({ preventScroll: true });
    syncHash();
  }
  $('#view3d').addEventListener('click', () => setPlan(false));
  $('#view2d').addEventListener('click', () => setPlan(true));
  (function planPanZoom() {
    let down = null;
    plan.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, vx: planView.x, vy: planView.y }; plan._dragged = false; });
    plan.addEventListener('pointermove', (e) => {
      if (!down) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!plan._dragged && Math.hypot(dx, dy) > 4) { plan._dragged = true; plan.classList.add('dragging'); }
      if (!plan._dragged) return;
      const k = planView.w / plan.clientWidth;
      planView.x = down.vx - dx * k; planView.y = down.vy - dy * k;
      setViewBox();
    });
    const up = () => { down = null; plan.classList.remove('dragging'); setTimeout(() => { plan._dragged = false; }, 0); };
    plan.addEventListener('pointerup', up);
    plan.addEventListener('pointerleave', up);
    plan.addEventListener('wheel', (e) => {
      e.preventDefault();
      const f = Math.exp(e.deltaY * 0.0012);
      const r = plan.getBoundingClientRect();
      const mx = planView.x + ((e.clientX - r.left) / r.width) * planView.w;
      const my = planView.y + ((e.clientY - r.top) / r.height) * planView.h;
      const nw = clamp(planView.w * f, 6, 800), k = nw / planView.w;
      planView.x = mx - (mx - planView.x) * k; planView.y = my - (my - planView.y) * k;
      planView.w = nw; planView.h *= k;
      setViewBox();
    }, { passive: false });
  })();

  // ── theme ────────────────────────────────────────────────────────────────
  function setTheme(id) {
    themeId = id;
    T = THEMES[id];
    store.set('theme', id);
    document.documentElement.dataset.theme = id;
    $('#theme').textContent = id === 'night' ? 'Day shift' : 'Night shift';
    $('#theme').title = `Switch to ${id === 'night' ? 'day' : 'night'} shift lighting (T)`;
    clearWorld();
    MATS.forEach((m) => m.dispose());
    MATS = new Map();
    TEX.forEach((t) => t.dispose());
    TEX.clear();
    lineMats.forEach((m) => m.dispose());
    lineMats.clear();
    drawKey();
    if (!room) return;
    const keep = W8.pos.clone(), yaw = W8.yaw;
    buildWorker();
    buildRoom(room.R);
    W8.pos.copy(keep); W8.yaw = yaw;
    if (selected && selected.type !== 'link') {
      const port = room.ports.find((p) => p.rep === selected.id);
      select(selected.id, port && !itemsById.has(selected.id) ? { port } : {});
    } else if (selected) closePanel();
    drawBar();   // its kind colours come from the theme
  }
  $('#theme').addEventListener('click', () => setTheme(themeId === 'night' ? 'day' : 'night'));

  // ── welcome card ─────────────────────────────────────────────────────────
  function openWelcome() { $('#welcome').hidden = false; $('#welcomeGo').focus(); }
  function closeWelcome() { $('#welcome').hidden = true; store.set('welcomed', '1'); if (canvas) canvas.focus({ preventScroll: true }); }
  $('#welcomeGo').addEventListener('click', closeWelcome);
  $('#helpBtn').addEventListener('click', openWelcome);
  $('#welcome').addEventListener('click', (e) => { if (e.target.id === 'welcome') closeWelcome(); });

  // ── main loop ────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  let frameNo = 0;
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    if (renderer) {
      GOV.ratio = dprCap();
      GOV.frames.length = 0;
      renderer.setPixelRatio(GOV.ratio);
      renderer.setSize(w, h);
    }
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    if (planOn && room) { fitPlan(); setViewBox(); }
  }
  window.addEventListener('resize', resize);
  // Moving the window to a screen with another pixel density fires no resize event in every browser.
  (function watchDensity() {
    if (!window.matchMedia) return;
    const q = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    const on = () => { resize(); watchDensity(); };
    if (q.addEventListener) q.addEventListener('change', on, { once: true });
  })();

  // Idle: after 5 s without input, walking or a playing tour, draw every other frame.
  const IDLE_MS = 5000;
  let lastInput = performance.now();
  ['pointerdown', 'pointermove', 'wheel', 'keydown', 'touchstart'].forEach((ev) => window.addEventListener(ev, () => { lastInput = performance.now(); }, { passive: true }));
  function idle(now) {
    const busy = keys.size || W8.path || ptr.down || transitioning || W8.pos.y > 0 || (player && player.playing);
    if (busy) lastInput = now;
    return now - lastInput > IDLE_MS;
  }

  let lastFrame = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    now = now || performance.now();
    frameNo++;
    const lazy = idle(now);
    if (lazy && frameNo % 2) return;   // the skipped frame's time goes into the next one's dt
    const dt = Math.min(clock.getDelta(), 0.05);
    const time = clock.elapsedTime;
    if (lastFrame && !lazy && !document.hidden) governFrame(now - lastFrame, now);
    lastFrame = now;
    if (!room) return;
    if (planOn) {
      if (frameNo % 10 === 0) { const me = plan.querySelector('#planMe'); if (me) me.setAttribute('transform', `translate(${W8.pos.x},${W8.pos.z})`); }
      return;
    }
    if (!renderer || document.hidden) return;
    updateMovement(dt);
    animateWorker(dt, time);
    updateCamera(dt);
    updateShell();
    if (!reduceMotion) ANIM.forEach((f) => f(time));
    updateParticles(reduceMotion ? 0 : time);
    updateHover();
    updateLabels(dt, frameNo % 4 === 0);
    if (frameNo % 6 === 0) updatePrompt();
    if (frameNo % 3 === 0) drawMinimap();
    renderer.render(scene, camera);
  }

  // ── lost GPU context ─────────────────────────────────────────────────────
  // Drivers can drop the WebGL context (GPU reset, sleep, too many tabs), which
  // leaves a blank canvas. Say so, and rebuild the room once it comes back.
  if (canvas) {
    const glMsg = document.createElement('div');
    glMsg.id = 'glMsg';
    glMsg.hidden = true;
    stage.appendChild(glMsg);
    let lostTimer = 0;
    canvas.addEventListener('webglcontextlost', () => {
      glMsg.innerHTML = '<p>The graphics driver dropped the 3D view. Trying to bring it back…</p>';
      glMsg.hidden = false;
      clearTimeout(lostTimer);
      lostTimer = setTimeout(() => {
        glMsg.innerHTML = '<p>The 3D view could not be restored. Reload the page to try again. The floor plan still works: press P or choose Floor plan.</p><button type="button" class="primary">Reload</button>';
        glMsg.querySelector('button').addEventListener('click', () => location.reload());
      }, 4000);
    });
    canvas.addEventListener('webglcontextrestored', () => {
      clearTimeout(lostTimer);
      glMsg.hidden = true;
      setTheme(themeId); // recreates every material, texture and mesh
    });
  }

  // A small hook for automated checks (also handy in the devtools console).
  window.__wirehouse = {
    goRoom, focusNode, select, selectLink, setPlan, setTheme, exitRoom, enterBlock, travelTo,
    startTrace, startPick, startRoute, startJourney, clearTrace, goStop, setPlaying, startTour, toggleClip, setChangesOn,
    progress: () => JSON.parse(JSON.stringify(PROG)),
    openErd,
    exportReceipts: () => EXPORTS.slice(), shareCard: async () => { const c = await shareCard(); return { name: c.name, w: c.canvas.width, h: c.canvas.height, url: c.canvas.toDataURL('image/png') }; },
    trace: () => trace && (trace.mode === 'route'
      ? { mode: 'route', loose: trace.loose, stops: trace.stops.map((s) => s.id), path: trace.path && trace.path.map((p) => p.id) }
      : { mode: trace.mode, id: trace.id, marks: MARK.hop && Object.fromEntries(MARK.hop) }),
    player: () => player && { kind: player.kind, i: player.i, n: player.stops.length, playing: player.playing, arrived: player.arrived, stops: player.stops.map((s) => s.id) },
    // feeds the resolution governor `seconds` of frames that each took `ms`, as a slow or fast device would
    frames(ms, seconds) {
      const t0 = performance.now() + 1e6, reset = () => { GOV.frames.length = 0; GOV.over = GOV.under = 0; };
      reset();
      for (let t = 0; t < seconds * 1000; t += ms) governFrame(ms, t0 + t);
      reset();
      return renderer && renderer.getPixelRatio();
    },
    idle: () => idle(performance.now()),
    tick(n) { for (let i = 0; i < (n || 1); i++) { updateMovement(1 / 60); animateWorker(1 / 60, i / 60); updateCamera(1 / 60); } renderer && renderer.render(scene, camera); },
    state: () => ({ room: room && room.R, items: room && room.items.length, links: LINKS.length, ports: room && room.ports.length, selected, pos: W8.pos.toArray().map((v) => +v.toFixed(2)), walking: !!W8.path }),
    links: () => room && room.links,
    // how well the first moving particle lines up with its pipe (1 = along the flow)
    streak: () => {
      const i = PART.findIndex((p) => p.link.active);
      if (i < 0 || !particles) return null;
      particles.getMatrixAt(i, tmpM);
      tmpM.decompose(tmpV, tmpQ, tmpS);
      const axis = UP.clone().applyQuaternion(tmpQ);
      tmpQ.identity();
      const L = PART[i].link;
      let best = -1;
      for (let k = 0; k < 64; k++) best = Math.max(best, axis.dot(tmpDir.subVectors(L.samples[k + 1], L.samples[k]).normalize()));
      return { align: best, additive: particles.material.blending === THREE.AdditiveBlending };
    },
    contactShadows: () => { const o = world.children.find((c) => c.userData.contact); return o ? o.count : 0; },
    labels: () => ({
      slots: SPRITES.filter((s) => s.slot && s.sp.visible).length, blocks: SPRITES.filter((s) => !s.slot && s.sp.visible).length,
      racks: world.children.filter((o) => o.userData.rackSign).map((o) => o.userData.rackSign),
    }),
    marks: () => Object.fromEntries([...(MARK.badges || new Map())].map(([id, b]) => [id, b.text])),
    // What one frame costs the GPU, for the performance budget.
    gpu: () => {
      if (!renderer) return null;
      let casters = 0, meshes = 0, instanced = 0;
      scene.traverseVisible((o) => { if (o.isMesh) { meshes++; if (o.castShadow) casters++; if (o.isInstancedMesh) instanced++; } });
      // one frame drawn here with the counters kept across the shadow pass, which render() would reset
      const i = renderer.info;
      i.autoReset = false;
      i.reset();
      renderer.render(scene, camera);
      i.autoReset = true;
      return { calls: i.render.calls, triangles: i.render.triangles, textures: i.memory.textures, geometries: i.memory.geometries,
        programs: (i.programs || []).length, meshes, instanced, casters, shadows: renderer.shadowMap.enabled, pixelRatio: renderer.getPixelRatio() };
    },
  };

  async function start() {
    $('#theme').textContent = themeId === 'night' ? 'Day shift' : 'Night shift';
    document.documentElement.dataset.theme = themeId;
    try {
      await Promise.race([
        Promise.all([document.fonts.load('600 40px "Barlow Condensed"'), document.fonts.load('700 40px "Barlow Condensed"'), document.fonts.load('500 30px "Barlow"')]),
        new Promise((r) => setTimeout(r, 1500)),
      ]);
    } catch (e) { /* fall back to system fonts */ }
    resize();
    buildWorker();
    if (!renderer) { $('#view3d').disabled = true; $('#view3d').title = 'This browser could not start WebGL'; setPlan(true); }
    const startHash = location.hash;
    applyHash(parseHash(startHash));
    const tops = kidsOf(ROOT).length, links = roomLinks(ROOT).inner.length;
    $('#welcomeTitle').textContent = `${D.project.name} warehouse`;
    $('#welcomeLead').textContent = `${tops} blocks stand on the main floor with ${links} pipes between them. Each block is part of the system, and each pipe is a connection found in the code. Blocks with a glowing door can be walked into.`;
    if (store.get('welcomed', '0') !== '1' && !/nowelcome/.test(startHash)) openWelcome();
    frame();
  }
  start();
})();
