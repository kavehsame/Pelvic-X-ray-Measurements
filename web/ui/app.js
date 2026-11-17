"use strict";

const $ = (id) => document.getElementById(id);
const add = (parent, tag, text = "", cls = "") => {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (cls) node.className = cls;
  parent.append(node);
  return node;
};
const click = (id, handler) => $(id).addEventListener("click", handler);
const arrow = (title, path) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><title>${title}</title>${path}</svg>`;
const icons = {
  folder: arrow("Folder", '<path d="M3 7.5h6l2 2.5h9a1 1 0 0 1 1 1l-2 7H4L2 8.5a1 1 0 0 1 1-1Z"/><path d="M5 18l2-7.5h13"/>'),
  sparkle: arrow("Suggestions", '<path d="M11 2.5 13.1 8.9 19.5 11l-6.4 2.1L11 19.5l-2.1-6.4L2.5 11l6.4-2.1L11 2.5ZM19.5 15.5v5m-2.5-2.5h5"/>'),
  rotate: arrow("Rotate", '<path d="M4 11a8 8 0 1 1 2 6m-2-6V5m0 6h6"/>'),
  mirror: arrow("Mirror", '<path d="M12 3v18M3 17V7l6 10H3Zm18 0V7l-6 10h6Z"/>'),
  contrast: arrow("Window", '<circle cx="12" cy="12" r="8"/><path d="M12 4v16m0-3a5 5 0 0 0 0-10"/>'),
  image: arrow("Image", '<rect x="2.5" y="3.5" width="19" height="17" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 18 5-5 3 3 4.5-5 5.5 6"/>'),
};
for (const target of document.querySelectorAll("[data-icon]")) target.innerHTML = icons[target.dataset.icon] || "";

const tools = new Map(), valueBoxes = new Map();
const resultLabels = {
  calibration: "Calibration", reference: "Reference", lld: "LLD",
  head: "Head Dia.", ccd: "CCD Angle", tonnis: "AI (Tönnis)", sharp: "Sharp", lce: "LCE",
  acetabular_offset: "Acetab. Off.", femoral_offset: "Femoral Off.", global_offset: "Global Off.",
  extrusion: "Extr. Idx", ccr: "CCR", cti: "CTI", cfi: "CFI",
  implant_head: "Impl. Head Dia.", inclination: "Inclination (FH)", ellipse_inclination: "Inclination (E)",
  cup_version: "Cup Ant/Ret An.", implant_ccd: "Impl. Fem. CCD", stem_alignment: "Stem Align.",
  post_acetabular_offset: "Post Acetab. Off.", post_femoral_offset: "Post Femoral Off.", post_global_offset: "Post Global Off.",
};
const resultOrder = ["head", "ccd", "tonnis", "sharp", "lce", "acetabular_offset", "femoral_offset", "global_offset", "extrusion",
  "ccr", "cti", "cfi", "implant_head", "inclination", "ellipse_inclination", "cup_version", "implant_ccd", "stem_alignment",
  "post_acetabular_offset", "post_femoral_offset", "post_global_offset"];
const ioError = (error) => error?.name === "AbortError";

let worker, config, snap, inputHandle, outputHandle, activeSource;
let entries = [], allFiles = new Map(), caseIndex = -1, working = new Map();
let activeDirty = false, busy = false, startLocked = false;
let sequence = 0;
const pending = new Map();

function request(action, args = {}, buffers = []) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    worker.postMessage({id, action, args, inputs: buffers}, buffers.map(([, buffer]) => buffer));
  });
}

function attachWorker(instance) {
  worker = instance;
  worker.onmessage = ({data}) => {
    const handler = pending.get(data.id);
    if (data.detail) console.error(data.detail);
    if (handler) {
      pending.delete(data.id);
      if (data.error) handler.reject(new Error(data.error));
      else handler.resolve(data.response);
    }
  };
  worker.onerror = (event) => {
    console.error(event.message);
    for (const handler of pending.values()) handler.reject(new Error("The browser worker stopped. Reload the page to restart."));
    pending.clear();
  };
}

async function readVerifiedRuntime(response, progress = null) {
  if (!response.ok) throw new Error("The app components could not load. Check the site and try again.");
  const bytes = new Uint8Array(APP_CONFIG.payloadSize);
  const reader = response.body.getReader();
  if (progress) {
    progress.max = bytes.length;
    progress.value = 0;
    progress.hidden = false;
  }
  let offset = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    if (offset + value.byteLength > bytes.byteLength) {
      await reader.cancel();
      throw new Error("The downloaded app components did not pass verification.");
    }
    bytes.set(value, offset);
    offset += value.byteLength;
    if (progress) progress.value = offset;
  }
  if (offset !== bytes.byteLength) throw new Error("The download was incomplete. Try Start again.");
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (x) => x.toString(16).padStart(2, "0")).join("");
  if (digest !== APP_CONFIG.payloadHash) throw new Error("The app components did not match this version.");
  return bytes;
}

async function runtimeBytes() {
  const source = new URL(APP_CONFIG.payload, location.href);
  const cacheKey = new URL(source);
  cacheKey.searchParams.set("sha256", APP_CONFIG.payloadHash);
  let cache;
  try {
    cache = await globalThis.caches?.open("pelvic-xray-software");
    const stored = await cache?.match(cacheKey.href);
    if (stored) return await readVerifiedRuntime(stored);
  } catch {
    // A damaged or unavailable cache must not stop a normal download.
    await cache?.delete(cacheKey.href).catch(() => {});
  }
  $("start-status").textContent = "Downloading browser components…";
  const response = await fetch(source, {
    method: "GET", cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer", redirect: "error",
  });
  const bytes = await readVerifiedRuntime(response, $("start-progress"));
  // Only the verified software bundle enters the cache, before any image
  // picker is enabled. Storage can be disabled or decline the write.
  await cache?.put(cacheKey.href, new Response(bytes, {
    headers: {"Content-Type": "application/octet-stream"},
  })).catch(() => {});
  return bytes;
}

async function checkedRuntime() {
  if (!window.isSecureContext || !window.crypto?.subtle || !window.WebAssembly || !window.Worker) {
    throw new Error("Open this site in a supported browser through HTTPS or a localhost address.");
  }
  const bytes = await runtimeBytes();
  const view = new DataView(bytes.buffer);
  const length = view.getUint32(0, true);
  const encoding = new TextDecoder();
  const manifest = JSON.parse(encoding.decode(bytes.subarray(4, 4 + length)));
  const files = Object.entries(manifest).map(([name, [at, size]]) => [name, bytes.subarray(4 + length + at, 4 + length + at + size)]);
  const vendored = new Map(files);
  const workerScript = new Blob([
    vendored.get("pyodide.js"), "\n",
    "globalThis.JPEGLossless=(()=>{const module={exports:{}};", vendored.get("jpeg-lossless.cjs"), "\nreturn module.exports;})();\n",
    vendored.get("openjpeg.js"), "\n", vendored.get("charls.js"), "\n",
    vendored.get("worker.js"),
  ], {type: "text/javascript"});
  // Policies are additive. This second policy takes effect before the file
  // pickers are enabled and also applies to the blob worker.
  const lock = document.createElement("meta");
  lock.httpEquiv = "Content-Security-Policy";
  lock.content = "connect-src 'none'";
  document.head.append(lock);
  startLocked = true;
  const workerURL = URL.createObjectURL(workerScript);
  try {
    attachWorker(new Worker(workerURL, {name: "Pelvic local measurement engine"}));
    $("start-status").textContent = "Preparing the measurement tools…";
    const id = ++sequence;
    const initial = new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
    worker.postMessage({id, action: "init", files}, [bytes.buffer]);
    let timeout;
    const timer = new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error("The measurement engine took too long to start. Reload the page to retry.")), 90_000);
    });
    try { return await Promise.race([initial, timer]); }
    finally { clearTimeout(timeout); }
  } finally {
    URL.revokeObjectURL(workerURL);
  }
}

click("start", async () => {
  $("start").disabled = true;
  $("start-status").textContent = "Checking for cached app components…";
  try {
    config = await checkedRuntime();
    renderControls(config);
    $("workspace").hidden = false;
    $("welcome").hidden = true;
    $("close-scene").hidden = false;
    await refresh(config, true, true);
    $("browse-input").focus();
  } catch (error) {
    worker?.terminate();
    $("start-status").textContent = error.message;
    $("start").disabled = startLocked;
    $("start-progress").hidden = true;
  }
});

function setMessage(message, error = false) {
  $("instruction").textContent = message || "";
  $("instruction").parentElement.dataset.error = String(error);
}

async function run(label, fn) {
  if (busy || !config || viewer.gesture?.target || viewer.gesture?.window) return;
  busy = true;
  renderAvailability();
  if (label) setMessage(label);
  try {
    await fn();
  } catch (error) {
    if (!ioError(error)) setMessage(error.message || "That operation could not be completed.", true);
  } finally {
    busy = false;
    renderAvailability();
  }
}

async function command(action, args = {}, {dirty = false, reset = false, sync = false, files = []} = {}) {
  const next = await request(action, args, files);
  await refresh(next, reset, sync);
  if (dirty && next.edited !== false) activeDirty = true;
  return next;
}

function doAction(action, args, options) {
  return run("", () => command(action, args, options));
}

const viewer = new RadiographViewer($("radiograph"), {
  busy: () => busy,
  place: (point) => doAction("place", point, {dirty: true}),
  move: (point) => doAction("move", point, {dirty: true}),
  previewMove: (point) => request("preview_move", point),
  window: (window) => doAction("window", window, {dirty: true}),
  previewWindow: (window) => request("preview_window", window),
  previewWindowValues: (window) => {
    const value = window ?? snap?.image;
    if (!value) return;
    $("window-low").value = value.low;
    $("window-high").value = value.high;
  },
  previewResults: (state) => renderResults(state ?? snap.state),
  finish: () => { if (snap?.active_role) doAction("finish"); },
  panModeChanged: (enabled) => $("pan-button").setAttribute("aria-pressed", String(enabled)),
  zoom: (zoom) => {
    if (!snap?.image) return;
    const [w, h] = snap.image.dimensions;
    $("viewer-meta").textContent = `${snap.image.format} · ${w} × ${h} · ${Math.round(zoom * 100)}%`;
  },
});

function check(parent, id, name, change, help) {
  const label = add(parent, "label", "", "check");
  const input = add(label, "input");
  input.type = "checkbox";
  if (id) input.id = id;
  add(label, "span", name);
  input.addEventListener("change", () => change(input.checked));
  if (help) label.dataset.help = help;
  return input;
}

function makeTool(section, key, label, custom = false) {
  const group = add(section, "div", "", custom ? "tool-row numbered" : "tool-row");
  const toolButton = add(group, "button", label, "tool-button");
  group.dataset.help = key;
  toolButton.type = "button";
  toolButton.id = "tool-" + key;
  toolButton.dataset.key = key;
  const kind = custom ? key.slice(6) : null;
  toolButton.addEventListener("click", async () => {
    await doAction(custom ? "custom" : "tool", custom ? {kind} : {key}, {dirty: true});
    viewer.canvas.focus({preventScroll: true});
  });
  let count;
  if (custom) {
    count = add(group, "input", "", "tool-count");
    count.type = "number";
    count.id = "count-" + kind;
    count.min = "0";
    count.max = "0";
    count.value = "0";
    count.setAttribute("aria-label", label + " count");
    count.addEventListener("change", () => doAction("custom", {kind, count: count.value}, {dirty: true}));
  }
  const hide = check(group, "hide-" + key, "Hide", (hidden) => doAction("hide", {key, hidden}, {dirty: true}));
  hide.setAttribute("aria-label", "Hide " + label);
  const options = new Map();
  if (["neck_axis", "implant_neck"].includes(key)) {
    const row = add(group, "div", "", "tool-options");
    const axis = key === "neck_axis" ? "neck" : "implant_neck";
    for (const [option, title] of [["lock_to_center", "Lock to center"], ["use_single_guide", "Use single guide"]]) {
      const name = `pelvic_${axis}_${option}`;
      options.set(name, check(row, name, title, (checked) => doAction("axis", {kind: axis, option, checked}, {dirty: true}), key));
    }
  }
  if (custom && kind !== "point") {
    const row = add(group, "div", "", "tool-options");
    for (const [mode, title] of [["parallel", "Lock ∥ Ref"], ["perpendicular", "Lock ⟂ Ref"]]) {
      const name = `pelvic_other_${kind}_${mode}`;
      options.set(name, check(row, name, title, (checked) => doAction("lock", {kind, mode, checked}, {dirty: true}), key));
    }
  }
  tools.set(key, {group, button: toolButton, hide, count, custom, kind, options});
}

function renderControls(initial) {
  const list = $("measurement-tools");
  initial.sections.forEach((section, index) => {
    if (index === 3) {
      const custom = add(list, "section", "", "tool-section");
      add(custom, "h2", "4: Points & Lines & Angles");
      for (const name of ["Point", "Line", "Angle"]) makeTool(custom, "other_" + name.toLowerCase(), name, true);
    }
    const row = add(list, "section", "", "tool-section");
    add(row, "h2", section.label);
    section.tools.forEach(({key, label}) => makeTool(row, key, label));
  });
  function result(container, key, bilateral) {
    const row = add(container, "div", "", "result-row" + (bilateral ? "" : " global"));
    row.dataset.help = "result_" + key;
    row.tabIndex = 0;
    add(row, "span", resultLabels[key]);
    for (const side of (bilateral ? ["right", "left"] : [""])) {
      const name = "pelvic_result_" + (side ? side + "_" : "") + key;
      const box = add(row, "output", "—");
      box.id = name.replaceAll("_", "-");
      valueBoxes.set(name, box);
    }
  }
  ["calibration", "reference", "lld"].forEach((key) => result($("global-results"), key, false));
  resultOrder.forEach((key) => result($("bilateral-results"), key, true));
}

function renderAvailability() {
  const state = snap?.state || {};
  const loaded = !!snap?.loaded;
  for (const [key, tool] of tools) {
    const {button, hide, count, custom, kind, group, options} = tool;
    const enabled = custom ? state[`pelvic_other_${kind}_enabled`] : state[`pelvic_enabled_${key}`];
    const applied = custom ? state[`pelvic_other_${kind}_applied`] : state[`pelvic_applied_${key}`];
    button.disabled = busy || !enabled;
    button.dataset.active = String(state.pelvic_active_key === key);
    button.dataset.applied = String(!!applied);
    group.dataset.dependency = !enabled && !custom ? state[`pelvic_dependency_${key}`] || "" : "";
    group.tabIndex = !busy && !enabled && group.dataset.dependency ? 0 : -1;
    hide.checked = !!state[`pelvic_hide_${key}`];
    hide.disabled = busy || !loaded;
    if (count) {
      count.disabled = busy || !loaded;
      count.value = state[`pelvic_other_${kind}_count`] ?? 0;
      count.max = state[`pelvic_other_${kind}_max`] ?? 0;
    }
    for (const [name, option] of options) {
      option.disabled = busy || !loaded;
      option.checked = !!state[name];
    }
  }
  for (const id of ["fit", "zoom-in", "zoom-out", "pan-button", "show-window", "side-left", "side-right", "import-csv", "comments", "export-values", "close-scene"]) {
    $(id).disabled = busy || !loaded;
  }
  for (const id of ["rotate", "mirror"]) $(id).disabled = busy || !loaded || snap.annotated;
  for (const id of ["browse-input", "open-files", "open-empty", "browse-output", "ball"]) $(id).disabled = busy;
  $("auto-place").disabled = busy || !state.pelvic_auto_enabled;
  $("clear-input").disabled = busy || !entries.length;
  $("clear-output").disabled = busy || !outputHandle;
  $("case-prev").disabled = busy || caseIndex <= 0;
  $("case-next").disabled = busy || caseIndex + 1 >= entries.length;
  for (const button of document.querySelectorAll("[data-export]")) {
    button.disabled = busy || !loaded || (button.dataset.advance && (!outputHandle || caseIndex >= entries.length - 1));
    if (button.dataset.advance) button.title = !outputHandle ? "Choose an output folder to save and advance." : "";
  }
}

async function refresh(next, reset, sync) {
  snap = next;
  const state = next.state;
  $("empty-view").hidden = next.loaded;
  $("side-badge").hidden = !next.loaded;
  $("side-badge").dataset.side = state.pelvic_active_side;
  $("side-badge").textContent = "ACTIVE SIDE: " + state.pelvic_active_side.toUpperCase();
  for (const side of ["left", "right"]) $("side-" + side).setAttribute("aria-pressed", String(state.pelvic_active_side === side));
  $("active-tool").textContent = next.active_role ? state.pelvic_active_tool : "Ready";
  setMessage(state.pelvic_instruction);
  if (!next.loaded) $("viewer-meta").textContent = "";
  if (document.activeElement !== $("ball")) $("ball").value = state.pelvic_ball_diameter;
  if (sync) {
    $("annotator").value = state.pelvic_annotator_name;
    $("comments").value = state.pelvic_comments;
    $("export-values").checked = state.pelvic_export_measurements;
    annotatorError(false);
  }
  renderResults(state);
  await viewer.update(next, reset);
  renderAvailability();
}

function renderResults(state) {
  for (const [name, box] of valueBoxes) {
    const value = state[name] ?? "—";
    if (box.textContent !== value) {
      box.textContent = value;
      box.dataset.defined = String(value !== "—");
    }
  }
  const result = $("custom-results");
  const rows = state.pelvic_custom_results ?? [];
  const signature = JSON.stringify(rows);
  if (result.dataset.values === signature) return;
  result.dataset.values = signature;
  result.replaceChildren();
  for (const entry of rows) {
    const row = add(result, "div", "", "custom-result");
    row.dataset.help = "result_custom";
    add(row, "span", entry.label);
    add(row, "output", entry.value);
  }
  if (!result.children.length) result.textContent = "No custom measurements.";
}

function decision(title, text, actions) {
  const modal = $("decision-dialog");
  $("decision-title").textContent = title;
  $("decision-description").textContent = text;
  $("decision-actions").replaceChildren();
  return new Promise((resolve) => {
    modal.returnValue = "cancel";
    for (const action of actions) {
      const button = add($("decision-actions"), "button", action.label, action.primary ? "primary" : "quiet");
      button.type = "button";
      button.addEventListener("click", () => modal.close(action.value));
    }
    modal.addEventListener("close", () => resolve(modal.returnValue), {once: true});
    modal.showModal();
  });
}

const cancel = {label: "Cancel", value: "cancel"};
const dirty = () => activeDirty || [...working.values()].some((item) => item.dirty);
const discardQuery = () => dirty() ? decision("Discard unsaved changes?", "Export the working annotations first if you want to keep them.",
  [cancel, {label: "Discard changes", value: "discard", primary: true}]).then((value) => value === "discard") : Promise.resolve(true);

const maxInput = 200_000_000;
const caseStem = (name) => name.replace(/(\.nii\.gz|\.[^.]+)$/i, "");
function safeStem(name) {
  const stem = name.replace(/[^\p{L}\p{N}._ ()-]+/gu, "_").replace(/^[. ]+|[. ]+$/g, "").slice(0, 110);
  return !stem || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(stem) ? "Case_" + stem : stem;
}

async function fileBytes(file, limit = maxInput) {
  if (file.size > limit) throw new Error("This file exceeds the browser size limit.");
  return file.arrayBuffer();
}

function updateCaseLabel() {
  const entry = entries[caseIndex];
  $("case-name").textContent = entry?.file.name || "No image loaded";
  $("case-name").title = entry?.file.name || "";
  $("case-count").textContent = entry ? `${caseIndex + 1} of ${entries.length}`
    : entries.length ? `${entries.length} available` : "";
  renderAvailability();
}

async function selectedEntries(files, folderName, handle = null) {
  const candidates = [];
  const map = new Map();
  for (const file of files) {
    const relative = file.webkitRelativePath ? file.webkitRelativePath.split("/").slice(1).join("/") : file.name;
    map.set(relative.toLowerCase(), file);
    // Match the desktop's immediate folder scan. Explicit file selection can
    // still include a detached pixel file alongside its header.
    if (relative.includes("/")) continue;
    const lower = file.name.toLowerCase();
    if (config.file_suffixes.some((suffix) => lower.endsWith(suffix))) candidates.push(file);
    else if (!file.name.includes(".") && file.size > 132) {
      const mark = new TextDecoder().decode(await file.slice(128, 132).arrayBuffer());
      if (mark === "DICM") candidates.push(file);
    }
  }
  candidates.sort((a, b) => a.name.localeCompare(b.name, undefined, {numeric: true, sensitivity: "base"}));
  if (!candidates.length) throw new Error("The selection contains no supported radiographs or Slicer scenes.");
  const seen = new Map();
  const next = candidates.map((file) => {
    const stem = safeStem(caseStem(file.name));
    let unique = stem;
    let serial = 1;
    while (seen.has(unique.toLowerCase())) unique = `${stem} (${++serial})`;
    seen.set(unique.toLowerCase(), file);
    return {file, stem: unique, legacyStem: caseStem(file.name)};
  });
  const previous = {entries, allFiles, caseIndex, working, inputHandle};
  const previousPath = $("input-path").value;
  entries = next;
  allFiles = map;
  working = new Map();
  caseIndex = -1;
  inputHandle = handle;
  $("input-path").value = folderName || (files.length === 1 ? files[0].name : "Selected files");
  try {
    await loadCase(0, {keepCurrent: false});
  } catch (error) {
    // Keep the new list when nothing was open so a different case can still
    // be tried. If a case was open, leave that scene and its list intact.
    if (previous.caseIndex >= 0) {
      ({entries, allFiles, caseIndex, working, inputHandle} = previous);
      $("input-path").value = previousPath;
    }
    updateCaseLabel();
    throw error;
  }
}

async function childDirectory(parent, child, create = false) {
  try { return await parent.getDirectoryHandle(child, {create}); }
  catch (error) { if (error.name === "NotFoundError") return null; throw error; }
}

async function findSaved(entry) {
  if (!outputHandle) return null;
  const dirs = [await childDirectory(outputHandle, entry.stem), outputHandle].filter(Boolean);
  if (entry.legacyStem !== entry.stem && !/[\\/]/.test(entry.legacyStem) && ![".", "..", ""].includes(entry.legacyStem)) {
    const legacy = await childDirectory(outputHandle, entry.legacyStem);
    if (legacy) dirs.push(legacy);
  }
  const prefixes = [entry.stem + "_web_", entry.legacyStem + "_browser_"];
  const matching = (name) => /\.(mrb|csv)$/i.test(name) && (prefixes.some((p) => name.startsWith(p))
      || name.replace(/\.(mrb|csv)$/i, "") === entry.legacyStem);
  const saves = [];
  for (const directory of dirs) {
    for await (const [name, handle] of directory.entries()) {
      if (handle.kind === "file" && matching(name)) {
        const file = await handle.getFile();
        saves.push({file, base: name.replace(/\.(mrb|csv)$/i, "")});
      }
    }
  }
  saves.sort((a, b) => b.file.lastModified - a.file.lastModified || b.file.name.localeCompare(a.file.name));
  const latest = saves[0];
  if (!latest) return null;
  // A CSV-only Replace can update an existing group without replacing its MRB.
  // Respect modification time within the group as well as between versions.
  const group = saves.filter((value) => value.base === latest.base);
  const scene = group.find((value) => /\.mrb$/i.test(value.file.name))?.file;
  const csv = group.find((value) => /\.csv$/i.test(value.file.name))?.file;
  return {scene: scene && (!csv || scene.lastModified >= csv.lastModified) ? scene : undefined, csv};
}

async function notes() {
  if (!snap?.loaded) return;
  await request("notes", {annotator: $("annotator").value, comments: $("comments").value, values: $("export-values").checked});
}

async function saveWorking() {
  if (caseIndex < 0 || !snap?.loaded) return;
  await notes();
  const {saved} = await request("serialize");
  working.set(caseIndex, {saved, source: activeSource, dirty: activeDirty});
}

async function loadCase(index, {keepCurrent = true, reload = false} = {}) {
  if (!(index >= 0 && index < entries.length) || (!reload && index === caseIndex)) return;
  if (keepCurrent && index !== caseIndex) await saveWorking();
  const entry = entries[index];
  const cached = !reload && working.get(index);
  const saved = cached ? null : await findSaved(entry);
  let source = cached?.source || saved?.scene || entry.file;
  async function open(selected, csv) {
    let related = null;
    if (/\.(nhdr|mhd)$/i.test(selected.name)) {
      const text = await selected.slice(0, 65536).text();
      const name = (text.match(/^(?:data\s*file\s*:|ElementDataFile\s*=)[ \t]*([^\r\n]+)/im)?.[1] ?? "").trim();
      if (name && name.toUpperCase() !== "LOCAL") {
        if (name.includes("/") || name.includes("\\") || name === "..") throw new Error("Place the detached image data beside its header and select both files.");
        related = allFiles.get(name.toLowerCase());
      }
    }
    const files = [["image", await fileBytes(selected)]];
    if (related) files.push(["companion", await fileBytes(related)]);
    if (csv) files.push(["annotations", await fileBytes(csv, 12_000_000)]);
    await command("load", {
      filename: selected.name, case_name: entry.file.name, cached: cached?.saved,
      companion: !!related, saved_csv: !!csv, annotator: $("annotator").value.trim(),
    }, {reset: true, sync: true, files});
  }
  setMessage("Reading the radiograph on this device…");
  try {
    await open(source, saved?.scene ? null : saved?.csv);
  } catch (error) {
    if (!saved?.scene || !saved.csv) throw error;
    source = entry.file;
    await open(source, saved.csv);
    setMessage("The saved scene could not open. Its CSV coordinates and comments were restored on the original radiograph.");
  }
  caseIndex = index;
  activeSource = source;
  activeDirty = !!cached?.dirty;
  if (reload) working.delete(index);
  updateCaseLabel();
}

click("browse-input", () => run("", async () => {
  if (!await discardQuery()) return;
  if (!window.showDirectoryPicker) { $("directory-input").click(); return; }
  const directory = await window.showDirectoryPicker({id: "pelvic-input", mode: "read"});
  if (outputHandle && await directory.isSameEntry(outputHandle)) throw new Error("Choose a different folder for the source radiographs.");
  const files = [];
  for await (const handle of directory.values()) if (handle.kind === "file") files.push(await handle.getFile());
  await selectedEntries(files, directory.name, directory);
}));
click("open-files", () => $("file-input").click());
click("open-empty", () => $("file-input").click());
for (const id of ["file-input", "directory-input"]) $(id).addEventListener("change", (event) => {
  const files = [...event.target.files];
  event.target.value = "";
  if (!files.length) return;
  const name = id === "directory-input" ? files[0].webkitRelativePath.split("/")[0] : "";
  run("", async () => { if (await discardQuery()) await selectedEntries(files, name); });
});

click("browse-output", () => run("", async () => {
  if (!window.showDirectoryPicker) throw new Error("Folder writing is unavailable here. Export to a Chrome download instead.");
  const directory = await window.showDirectoryPicker({id: "pelvic-output", mode: "readwrite"});
  if (inputHandle && await directory.isSameEntry(inputHandle)) throw new Error("Choose an output folder separate from the input folder.");
  outputHandle = directory;
  $("output-path").value = directory.name;
  if (caseIndex >= 0 && !activeDirty && !snap.annotated && !$("comments").value.trim() && await findSaved(entries[caseIndex])) {
    await loadCase(caseIndex, {keepCurrent: false, reload: true});
  }
}));
click("clear-output", () => { outputHandle = null; $("output-path").value = ""; renderAvailability(); });
click("case-prev", () => run("", () => loadCase(caseIndex - 1)));
click("case-next", () => run("", () => loadCase(caseIndex + 1)));

async function clearScene(clearInput) {
  if (!await discardQuery()) return;
  await command("close", {annotator: $("annotator").value.trim()}, {sync: true, reset: true});
  working.clear();
  activeSource = null;
  activeDirty = false;
  caseIndex = -1;
  if (clearInput) { entries = []; allFiles.clear(); inputHandle = null; $("input-path").value = ""; }
  updateCaseLabel();
}
click("close-scene", () => run("", () => clearScene(false)));
click("clear-input", () => run("", () => clearScene(true)));

click("import-csv", () => $("csv-input").click());
$("csv-input").addEventListener("change", (event) => {
  const [file] = event.target.files;
  event.target.value = "";
  if (!file) return;
  run("", async () => {
    if ((snap.annotated || activeDirty) && await decision("Open saved coordinates?",
      "This replaces the annotations in the current workspace.", [cancel, {label: "Open CSV", value: "open", primary: true}]) !== "open") return;
    await notes();
    const files = [["annotations", await fileBytes(file, 12_000_000)]];
    await command("restore_csv", {}, {files, sync: true, reset: true, dirty: true});
  });
});

const stage = $("view-stage");
stage.addEventListener("dragover", (event) => { event.preventDefault(); stage.classList.add("drop"); });
stage.addEventListener("dragleave", (event) => { if (!stage.contains(event.relatedTarget)) stage.classList.remove("drop"); });
stage.addEventListener("drop", (event) => {
  event.preventDefault();
  stage.classList.remove("drop");
  const files = [...event.dataTransfer.files];
  if (files.length) run("", async () => { if (await discardQuery()) await selectedEntries(files); });
});

for (const side of ["left", "right"]) click("side-" + side, () => doAction("side", {side}, {dirty: !!snap.annotated}));
$("ball").addEventListener("change", async (event) => {
  const value = event.target.valueAsNumber;
  if (!Number.isFinite(value) || value <= 0 || value >= 1000) {
    $("ball").value = snap.state.pelvic_ball_diameter;
    setMessage("Enter a positive calibration-ball diameter below 1,000 mm.", true);
    return;
  }
  await doAction("ball", {value}, {dirty: !!snap?.loaded});
});
click("fit", () => viewer.fit());
click("pan-button", () => viewer.setPanMode(!viewer.panMode));
click("zoom-in", () => viewer.zoomAt(1.25));
click("zoom-out", () => viewer.zoomAt(.8));
click("rotate", () => doAction("orient", {operation: "rotate"}, {reset: true, dirty: true}));
click("mirror", () => doAction("orient", {operation: "mirror"}, {reset: true, dirty: true}));
click("show-window", () => {
  $("window-low").value = snap.image.low;
  $("window-high").value = snap.image.high;
  $("invert").checked = snap.image.invert;
  $("window-dialog").showModal();
});
$("window-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const lo = $("window-low").valueAsNumber, hi = $("window-high").valueAsNumber;
  if (hi <= lo) {
    $("window-high").setCustomValidity("Window maximum must be greater than the minimum.");
    $("window-high").reportValidity();
    return;
  }
  $("window-dialog").close();
  doAction("window", {low: lo, high: hi, invert: $("invert").checked}, {dirty: true});
});
for (const id of ["window-low", "window-high"]) $(id).addEventListener("input", () => $("window-high").setCustomValidity(""));

click("auto-place", () => run("", async () => {
  const {suggestions} = await request("auto_open");
  $("auto-context").textContent = `${suggestions.mode === "pre" ? "Pre-operative" : "Post-operative"} suggestions for the ${suggestions.side} side`;
  $("auto-features").replaceChildren();
  for (const feature of suggestions.features) {
    const box = check($("auto-features"), "suggest-" + feature.key, feature.label, () => {});
    box.value = feature.key;
    box.checked = feature.available;
    box.disabled = !feature.available;
  }
  $("auto-dialog").showModal();
}));
$("auto-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const selected = [...$("auto-features").querySelectorAll("input:checked")].map((input) => input.value);
  $("auto-dialog").close();
  if (selected.length) doAction("auto_place", {selected}, {dirty: true});
  else setMessage("No features selected.");
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || document.querySelector("dialog[open]")) return;
  if (viewer.gesture?.pan || viewer.panMode) {
    event.preventDefault();
    viewer.cancelGesture();
    viewer.setPanMode(false);
  } else if (viewer.gesture?.target || viewer.gesture?.window) {
    event.preventDefault();
    viewer.cancelGesture();
  } else if (snap?.active_role) {
    event.preventDefault();
    viewer.callbacks.finish();
  }
});

function annotatorError(invalid) {
  $("annotator").setAttribute("aria-invalid", String(invalid));
  $("annotator-error").hidden = !invalid;
  if (invalid) { $("annotator").scrollIntoView({block: "center"}); $("annotator").focus({preventScroll: true}); }
}
$("annotator").addEventListener("input", () => annotatorError(false));
$("comments").addEventListener("input", () => { activeDirty = true; });
$("export-values").addEventListener("change", () => { activeDirty = true; });

function summarize(state) {
  const lines = [];
  for (const key of ["calibration", "reference", "lld"]) {
    const value = state["pelvic_result_" + key];
    if (value && value !== "—") lines.push(`${resultLabels[key]}: ${value}`);
  }
  for (const key of resultOrder) {
    const left = state[`pelvic_result_left_${key}`], right = state[`pelvic_result_right_${key}`];
    const values = [[right, "R"], [left, "L"]].filter(([value]) => value && value !== "—")
      .map(([value, side]) => `${side} ${value}`);
    if (values.length) lines.push(`${resultLabels[key]}  ${values.join("  ")}`);
  }
  for (const row of state.pelvic_custom_results) if (row.defined) lines.push(`${row.label}  ${row.value}`);
  return lines;
}

async function existingGroups(directory, stem) {
  const groups = new Map();
  for await (const [name, handle] of directory.entries()) {
    if (handle.kind !== "file" || !name.startsWith(stem + "_web_") || !/\.(csv|mrb|png)$/i.test(name)) continue;
    const key = name.replace(/\.(csv|mrb|png)$/i, "");
    if (!groups.has(key)) groups.set(key, new Map());
    groups.get(key).set(name, handle);
  }
  return groups;
}

async function writeFile(handle, data) {
  const writer = await handle.createWritable();
  try {
    await writer.write(data);
    await writer.close();
  } catch (error) {
    await writer.abort().catch(() => {});
    throw error;
  }
}

async function writeGroup(directory, base, files, group) {
  const changes = [];
  try {
    for (const [ext, blob] of Object.entries(files)) {
      const name = base + "." + ext;
      const previous = group?.get(name);
      const backup = previous ? await (await previous.getFile()).arrayBuffer() : null;
      // When saving a new version, guard against a name that appeared after
      // the directory was initially read, such as a concurrent export.
      if (!previous) {
        try { await directory.getFileHandle(name); throw new Error("An export with this name already exists. Try saving a new version."); }
        catch (error) { if (error.name !== "NotFoundError") throw error; }
      }
      const handle = previous || await directory.getFileHandle(name, {create: true});
      changes.push({name, handle, backup});
      await writeFile(handle, blob);
    }
  } catch (error) {
    let restored = true;
    for (const {name, handle, backup} of changes.reverse()) {
      try {
        if (backup) await writeFile(handle, backup);
        else await directory.removeEntry(name);
      } catch (_) { restored = false; }
    }
    if (!restored) throw new Error("The export stopped and could not restore every file. Check the output folder before retrying.");
    throw error;
  }
}

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = add(document.body, "a");
  a.href = url;
  a.download = name;
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

async function exportCase(kind, advance) {
  const annotator = $("annotator").value.trim();
  if (!annotator) { annotatorError(true); return; }
  const entry = entries[caseIndex];
  if (!entry) return;
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "");
  let base = entry.stem + "_web_" + stamp;
  let directory, group;
  if (outputHandle) {
    directory = await childDirectory(outputHandle, entry.stem, false);
    const groups = directory ? await existingGroups(directory, entry.stem) : new Map();
    const latest = [...groups.keys()].sort().at(-1);
    if (latest) {
      const choice = await decision("Export already exists", "Replace the previous export files of this type or save a new version.",
        [cancel, {label: "Replace", value: "replace"}, {label: "Save new version", value: "new", primary: true}]);
      if (choice === "cancel") return;
      if (choice === "replace") { base = latest; group = groups.get(latest); }
    }
  }
  if (snap.active_role) await command("finish");
  // Shaft contours step on Finish. Stop placement as a separate action before
  // writing any result so a half-finished trace cannot be mistaken for complete.
  if (snap.active_role) throw new Error("Finish the four shaft contours before exporting.");
  setMessage("Preparing the export on this device…");
  await notes();
  const response = await request("export", {kind});
  await refresh(response);
  const blobs = Object.fromEntries(Object.entries(response.files).map(([ext, bytes]) =>
    [ext, new Blob([bytes], {type: ext === "csv" ? "text/csv;charset=utf-8" : "application/zip"})]));
  if (kind === "all" || kind === "image") {
    blobs.png = await viewer.exportPNG(response, summarize(response.state), annotator, $("export-values").checked);
  }
  if (outputHandle) {
    directory ||= await childDirectory(outputHandle, entry.stem, true);
    await writeGroup(directory, base, blobs, group);
    setMessage(`Saved to ${outputHandle.name} / ${entry.stem}.`);
    if (kind === "all" || kind === "scene" || kind === "csv") {
      activeDirty = false;
      working.delete(caseIndex);
    }
  } else if (kind === "all") {
    const files = await Promise.all(Object.entries(blobs).map(async ([ext, blob]) => [ext, await blob.arrayBuffer()]));
    const {files: zipped} = await request("zip", {entries: files.map(([ext]) => [base + "." + ext, ext])}, files);
    download(new Blob([zipped.zip], {type: "application/zip"}), base + ".zip");
    setMessage("Export ready in Chrome downloads.");
    activeDirty = false;
    working.delete(caseIndex);
  } else {
    const [ext, blob] = Object.entries(blobs)[0];
    download(blob, base + "." + ext);
    setMessage("Export ready in Chrome downloads.");
    if (kind !== "image") { activeDirty = false; working.delete(caseIndex); }
  }
  if (advance && caseIndex + 1 < entries.length) await loadCase(caseIndex + 1);
}
for (const button of document.querySelectorAll("[data-export]")) {
  button.addEventListener("click", () => run("", () => exportCase(button.dataset.export, button.dataset.advance === "true")));
}

click("manual-button", () => $("manual").showModal());
for (const btn of document.querySelectorAll("[data-close]")) btn.addEventListener("click", () => btn.closest("dialog").close());
for (const btn of document.querySelectorAll("[data-jump]")) btn.addEventListener("click", () => $(btn.dataset.jump).scrollIntoView({block: "start"}));

const help = $("hover-help");
let tooltipTimer, helpTarget;
function hideHelp() {
  clearTimeout(tooltipTimer);
  help.hidden = true;
  helpTarget = null;
}
function queueHelp(target) {
  if (!target || target === helpTarget || !APP_CONFIG.help[target.dataset.help]) return;
  hideHelp();
  helpTarget = target;
  tooltipTimer = setTimeout(() => {
    const entry = APP_CONFIG.help[target.dataset.help];
    help.replaceChildren();
    add(help, "strong", entry[0]);
    add(help, "div", [entry[1], target.dataset.dependency].filter(Boolean).join(" "));
    if (["morphology", "result_ccr", "result_cti", "result_cfi"].includes(target.dataset.help)) {
      const img = add(help, "img");
      img.src = APP_CONFIG.schematic;
      img.alt = "Femoral shaft indices schematic";
    }
    help.hidden = false;
    const {left, bottom, top} = target.getBoundingClientRect();
    help.style.left = Math.max(8, Math.min(left, innerWidth - help.offsetWidth - 8)) + "px";
    help.style.top = Math.max(7, bottom + help.offsetHeight < innerHeight - 7 ? bottom + 6 : top - help.offsetHeight - 6) + "px";
  }, 2500);
}
document.addEventListener("pointerover", (event) => queueHelp(event.target.closest("[data-help]")));
document.addEventListener("pointerout", (event) => { if (helpTarget && !helpTarget.contains(event.relatedTarget)) hideHelp(); });
document.addEventListener("focusin", (event) => queueHelp(event.target.closest("[data-help]")));
document.addEventListener("focusout", hideHelp);
document.addEventListener("scroll", hideHelp, true);
window.addEventListener("beforeunload", (event) => {
  if (dirty()) { event.preventDefault(); event.returnValue = ""; }
});
