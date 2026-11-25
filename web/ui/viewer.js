"use strict";

const LANDMARK_RADIUS = 8;
const LANDMARK_SWITCH_MARGIN = 2;
const LANDMARK_OVERLAP_DISTANCE = 6;
const LANDMARK_CHOICE_TOLERANCE = 3;

function exportImageDimensions(shape, scale) {
  const [width, height] = shape.map((size, i) => size * scale[i]);
  const factor = Math.min(Math.max(1, 2048 / Math.max(width, height)),
    15500 / Math.max(width, height), Math.sqrt(40_000_000 / (width * height)));
  return [width, height].map((size) => Math.max(2, Math.floor(size * factor)));
}

function traceMarkupPath(ctx, screen, curved, firstSegment = 1, limit = screen.length) {
  ctx.beginPath();
  ctx.moveTo(...screen[firstSegment - 1]);
  for (let i = firstSegment; i < limit; i++) {
    const start = screen[i - 1], end = screen[i];
    if (curved && screen.length >= 3) {
      const before = screen[Math.max(0, i - 2)], after = screen[Math.min(screen.length - 1, i + 1)];
      ctx.bezierCurveTo(start[0] + (end[0] - before[0]) / 6, start[1] + (end[1] - before[1]) / 6,
        end[0] - (after[0] - start[0]) / 6, end[1] - (after[1] - start[1]) / 6, ...end);
    } else ctx.lineTo(...end);
  }
}

function drawMarks(ctx, marks, position, width, glyph, selected = null, continuation = null) {
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (const item of marks) {
    if (item.artwork) continue;
    const color = "rgb(" + item.color.join(",") + ")";
    const screen = item.points.map(position);
    if (item.kind !== "points" && screen.length >= 2) {
      const curved = item.kind === "curve" && item.curve_type !== 0;
      const path = curved && continuation?.role === item.role ? [...screen, continuation.point] : screen;
      traceMarkupPath(ctx, path, curved, 1, screen.length);
      ctx.lineWidth = width;
      ctx.strokeStyle = color;
      ctx.stroke();
    }
    if (!item.locked || item.kind === "points") {
      screen.forEach(([x, y], index) => {
        const targeted = selected?.role === item.role && selected.index === index;
        const radius = glyph * (targeted ? 1.45 : item.kind === "curve" ? .85 : 1);
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = glyph * .35;
        ctx.strokeStyle = "#0b1119";
        ctx.stroke();
        const label = item.labels[index];
        if (label) {
          ctx.font = `600 ${Math.max(11, glyph * 3.5)}px system-ui`;
          ctx.lineWidth = glyph * .65;
          ctx.strokeText(label, x + glyph * 2, y - glyph);
          ctx.fillText(label, x + glyph * 2, y - glyph);
        }
      });
    }
  }
}

class RadiographViewer {
  constructor(canvas, callbacks) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", {alpha: false});
    this.callbacks = callbacks;
    this.zoom = 1;
    this.x = 0;
    this.y = 0;
    this.shape = null;
    this.scale = [1, 1];
    this.bitmap = null;
    this.implants = new Map();
    this.marks = [];
    this.landmarkFocus = null;
    this.active = null;
    this.gesture = null;
    this.pointPreview = null;
    this.pendingPreview = null;
    this.previewInFlight = false;
    this.windowPreview = null;
    this.pendingWindowPreview = null;
    this.windowPreviewInFlight = false;
    this.windowPreviewSerial = 0;
    this.updateSerial = 0;
    this.window = null;
    this.current = null;
    this.fitted = true;
    this.space = false;
    this.modifiedPointer = false;
    this.panMode = false;
    this.allowContextFinish = false;
    new ResizeObserver(() => this.resize()).observe(canvas);
    canvas.addEventListener("wheel", (event) => {
      if (!this.bitmap) return;
      event.preventDefault();
      const at = this.location(event);
      this.zoomAt(Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * .004), at);
    }, {passive: false});
    canvas.addEventListener("pointerdown", (event) => this.down(event));
    canvas.addEventListener("pointermove", (event) => this.move(event));
    canvas.addEventListener("pointerup", (event) => this.up(event));
    canvas.addEventListener("pointercancel", (event) => this.cancelGesture(event.pointerId));
    canvas.addEventListener("lostpointercapture", (event) => this.cancelGesture(event.pointerId));
    canvas.addEventListener("pointerleave", () => {
      if (!this.gesture) { this.current = null; this.draw(); }
    });
    canvas.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      // macOS can turn a Ctrl-click into a secondary click. Only a plain
      // secondary press can finish a placement.
      const finish = this.allowContextFinish && !event.ctrlKey && !this.space && !this.panMode && !this.gesture?.pan;
      this.allowContextFinish = false;
      if (finish) this.callbacks.finish();
    });
    const updateKeys = (event) => {
      const wasSpace = this.space;
      if (event.code === "Space") {
        if (event.type === "keyup") this.space = false;
        else if (document.activeElement === canvas) {
          event.preventDefault();
          this.space = true;
        }
      }
      const modified = event.ctrlKey || event.shiftKey;
      if (this.space !== wasSpace || modified !== this.modifiedPointer) {
        this.modifiedPointer = modified;
        this.draw();
      }
    };
    document.addEventListener("keydown", updateKeys);
    document.addEventListener("keyup", updateKeys);
    window.addEventListener("blur", () => {
      this.space = false;
      this.modifiedPointer = false;
      this.current = null;
      this.landmarkFocus = null;
      this.allowContextFinish = false;
      this.cancelGesture();
      this.draw();
    });
  }

  setPanMode(enabled) {
    this.panMode = enabled;
    this.callbacks.panModeChanged(enabled);
    this.draw();
  }

  location(event) {
    const rect = this.canvas.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  position([i, j]) {
    return [this.x + i * this.zoom * this.scale[0], this.y + j * this.zoom * this.scale[1]];
  }

  imagePoint([x, y]) {
    return [(x - this.x) / (this.scale[0] * this.zoom), (y - this.y) / (this.scale[1] * this.zoom)];
  }

  drawFragmentPixels(ctx, bitmap, plans, x, y, width, height) {
    if (!plans?.length) return;
    // Filling and clipping an unmoved patch twice darkens the antialiased edge.
    const identity = [[1, 0, 0], [0, 1, 0]];
    const moved = plans.some(({matrix}) =>
      matrix.some((row, i) => row.some((value, j) => Math.abs(value - identity[i][j]) > 1e-9)));
    if (!moved) return;
    ctx.save();
    try {
      ctx.translate(x, y);
      ctx.scale(width / bitmap.width, height / bitmap.height);
      ctx.beginPath();
      ctx.rect(0, 0, bitmap.width, bitmap.height);
      ctx.clip();
      ctx.translate(.5, .5);
      const polygon = (points) => {
        ctx.beginPath();
        points.forEach(([px, py], i) => i ? ctx.lineTo(px, py) : ctx.moveTo(px, py));
        ctx.closePath();
      };
      ctx.fillStyle = "#000";
      for (const plan of plans) { polygon(plan.polygon); ctx.fill(); }
      for (const plan of plans) {
        ctx.save();
        const [[a, c, e], [b, d, f]] = plan.matrix;
        ctx.transform(a, b, c, d, e, f);
        polygon(plan.polygon);
        ctx.clip();
        ctx.drawImage(bitmap, -.5, -.5);
        ctx.restore();
      }
    } finally { ctx.restore(); }
  }

  async loadImplants(marks) {
    const visible = new Set(marks.map(m => m.artwork).filter(Boolean));
    for (const [id, entry] of this.implants) {
      if (!visible.has(id)) {
        this.implants.delete(id);
        entry.bitmap?.close();
      }
    }
    await Promise.all([...visible].map(id => {
      if (this.implants.has(id)) return this.implants.get(id).ready;
      const entry = {};
      this.implants.set(id, entry);
      entry.ready = this.callbacks.artwork(id)
        .then(({files, grid}) => {
          entry.hit = files.hit;
          entry.grid = grid;
          return createImageBitmap(new Blob([files.png], {type: "image/png"}));
        })
        .then(bitmap => {
          if (this.implants.get(id) === entry) entry.bitmap = bitmap;
          else bitmap.close();
        }).catch(error => {
          if (this.implants.get(id) !== entry) return;
          this.implants.delete(id);
          throw error;
        });
      return entry.ready;
    }));
  }

  drawImplants(ctx, marks, position) {
    for (const mark of marks) {
      const bitmap = this.implants.get(mark.artwork)?.bitmap;
      if (!bitmap) continue;
      const [a, b, , d] = mark.points.map(position);
      ctx.save();
      ctx.transform((b[0]-a[0])/bitmap.width, (b[1]-a[1])/bitmap.width,
        (d[0]-a[0])/bitmap.height, (d[1]-a[1])/bitmap.height, ...a);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(bitmap, 0, 0);
      ctx.restore();
    }
  }

  async update(snapshot, reset) {
    if (reset || this.activeSide !== snapshot.state.pelvic_active_side) this.selectedPlanRole = null;
    this.activeSide = snapshot.state.pelvic_active_side;
    this.handles = snapshot.rotation_handles || {};
    this.cutKind = snapshot.state.pelvic_fragment_cut || "straight";
    this.fragments = snapshot.fragments || [];
    const serial = ++this.updateSerial;
    this.pointPreview = null;
    this.window = snapshot.image;
    if (reset || snapshot.active_role !== this.active) this.landmarkFocus = null;
    if (this.panMode && (reset || (snapshot.active_role && snapshot.active_role !== this.active))) {
      this.panMode = false;
      this.callbacks.panModeChanged(false);
    }
    this.active = snapshot.active_role;
    this.marks = snapshot.markups;
    await this.loadImplants(this.marks);
    if (serial !== this.updateSerial) return;
    if (!snapshot.loaded) {
      this.bitmap?.close();
      this.bitmap = null;
      this.shape = null;
      this.current = null;
      this.draw();
      return;
    }
    const [sx, sy] = snapshot.image.spacing;
    const base = Math.min(sx, sy);
    this.scale = [sx / base, sy / base];
    this.shape = snapshot.image.dimensions;
    if (snapshot.preview) {
      const next = await createImageBitmap(new Blob([snapshot.preview], {type: "image/png"}));
      if (serial !== this.updateSerial) { next.close(); return; }
      this.bitmap?.close();
      this.bitmap = next;
    }
    if (reset) this.fit();
    else this.draw();
  }

  resize() {
    const size = this.canvas.getBoundingClientRect();
    if (!size.width || !size.height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 3);
    this.width = size.width;
    this.height = size.height;
    this.ratio = ratio;
    this.canvas.width = Math.round(size.width * ratio);
    this.canvas.height = Math.round(size.height * ratio);
    if (this.fitted) this.fit();
    else this.draw();
  }

  fit() {
    if (!this.shape || !this.width) { this.draw(); return; }
    const [w, h] = this.shape.map((size, i) => size * this.scale[i]);
    this.zoom = Math.min(Math.max(1, this.width - 18) / w, Math.max(1, this.height - 18) / h);
    this.x = (this.width - w * this.zoom) / 2 + this.zoom * this.scale[0] / 2;
    this.y = (this.height - h * this.zoom) / 2 + this.zoom * this.scale[1] / 2;
    this.fitted = true;
    this.landmarkFocus = null;
    this.draw();
  }

  zoomAt(factor, at = [this.width / 2, this.height / 2]) {
    if (!this.shape) return;
    const image = this.imagePoint(at);
    this.zoom = Math.min(12, Math.max(0.005, this.zoom * factor));
    this.x = at[0] - image[0] * this.scale[0] * this.zoom;
    this.y = at[1] - image[1] * this.scale[1] * this.zoom;
    this.fitted = false;
    this.landmarkFocus = null;
    this.draw();
  }

  updateLandmarkFocus(cycle = false) {
    const at = this.current;
    const priorFocus = this.landmarkFocus;
    this.landmarkFocus = null;
    if (!at || this.active || this.panMode || this.space || this.modifiedPointer || this.callbacks.busy()) return null;
    if (at[0] < 0 || at[1] < 0 || at[0] >= this.width || at[1] >= this.height) return null;

    const nearby = [];
    let nearest = null, previous = null;
    for (const mark of this.marks) {
      if (mark.locked) continue;
      mark.points.forEach((point, index) => {
        const screen = this.position(point);
        const dx = at[0] - screen[0], dy = at[1] - screen[1];
        if (dx * dx + dy * dy > LANDMARK_RADIUS ** 2) return;
        const hit = {role: mark.role, index, screen, distance: Math.hypot(dx, dy)};
        nearby.push(hit);
        if (!nearest || hit.distance < nearest.distance) nearest = hit;
        if (priorFocus?.target.role === mark.role && priorFocus.target.index === index) previous = hit;
      });
    }
    if (!nearest) return null;

    // Keep a deliberate choice through small pointer movements before the drag.
    let choiceOrigin = previous ? priorFocus.choiceOrigin : null;
    if (choiceOrigin && Math.hypot(at[0] - choiceOrigin[0], at[1] - choiceOrigin[1]) > LANDMARK_CHOICE_TOLERANCE) {
      choiceOrigin = null;
    }
    let chosen = nearest;
    if (previous && (choiceOrigin || previous.distance <= nearest.distance + LANDMARK_SWITCH_MARGIN)) {
      chosen = previous;
    }
    const choices = nearby.filter((hit) => hit === chosen ||
      Math.hypot(hit.screen[0] - nearest.screen[0], hit.screen[1] - nearest.screen[1]) <= LANDMARK_OVERLAP_DISTANCE);
    if (cycle && choices.length > 1) {
      chosen = choices[(choices.indexOf(chosen) + 1) % choices.length];
      choiceOrigin = at;
    }
    const {role, index, screen} = chosen;
    this.landmarkFocus = {target: {role, index}, screen, multiple: choices.length > 1, choiceOrigin};
    return this.landmarkFocus;
  }

  rotationHandle(role, handles = this.handles) {
    const ray = handles?.[role];
    if (!ray || !role.startsWith(this.activeSide + "_")) return null;
    const a = this.position(ray[0]), b = this.position(ray[1]);
    const dx = b[0]-a[0], dy=b[1]-a[1], length=Math.hypot(dx,dy);
    if (!length) return null;
    return [a, [a[0]+48*dx/length, a[1]+48*dy/length]];
  }

  planHit(at) {
    if (this.active) return null;
    const handle = this.rotationHandle(this.selectedPlanRole);
    if (handle && Math.hypot(at[0]-handle[1][0],at[1]-handle[1][1]) <= 10)
      return {target:{role:this.selectedPlanRole+"Rotation",index:0},screen:handle[1]};
    return null;
  }

  bodyHit(at) {
    if (this.active) return null;
    const ctx = this.ctx;
    const contains = (points, edge) => {
      const p = new Path2D();
      points.forEach((v,i)=>i ? p.lineTo(...v) : p.moveTo(...v)); p.closePath();
      ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.lineWidth=10;
      const hit = ctx.isPointInPath(p,...at) || (edge && ctx.isPointInStroke(p,...at));
      ctx.restore(); return hit;
    };
    for (const m of this.marks) {
      if (!m.role.startsWith(this.activeSide+"_planning") || !m.role.endsWith("AnchorOutline")) continue;
      const role=m.role.slice(0,-7);
      const corners = m.points.map(p=>this.position(p));
      if (!this.handles[role] || !contains(corners, true)) continue;
      if (m.artwork) {
        const entry = this.implants.get(m.artwork);
        if (!entry?.hit) continue;
        const [a, b, , d] = corners;
        const u = [b[0]-a[0], b[1]-a[1]], v = [d[0]-a[0], d[1]-a[1]];
        const det = u[0]*v[1]-u[1]*v[0], x = at[0]-a[0], y = at[1]-a[1];
        const [rows, cols] = entry.grid;
        const i = Math.floor((x*v[1]-y*v[0])/det*cols), j = Math.floor((u[0]*y-u[1]*x)/det*rows);
        if (i<0 || i>=cols || j<0 || j>=rows || !entry.hit[j*cols+i]) continue;
      }
      return {target:{role,index:0},screen:this.position(this.handles[role][0])};
    }
    for (const f of this.fragments) {
      if (f.side !== this.activeSide) continue;
      const [[a,c,e],[b,d,h]]=f.matrix;
      const xy=f.polygon.map(([x,y])=>this.position([a*x+c*y+e,b*x+d*y+h]));
      if (!contains(xy,false)) continue;
      const role=f.side+"_fragmentTarget", anchor=this.marks.find(m=>m.role===role);
      if (anchor?.points.length) return {target:{role,index:0},screen:this.position(anchor.points[0])};
    }
    return null;
  }

  dragPoint(gesture, at) {
    const [dx, dy] = gesture.grabOffset;
    return this.imagePoint([at[0] + dx, at[1] + dy]);
  }

  down(event) {
    this.allowContextFinish = false;
    if (!this.bitmap || this.gesture || this.callbacks.busy()) return;
    const panRequested = this.space || this.panMode || event.ctrlKey || event.button === 1;
    const windowRequested = event.shiftKey && event.button === 0 && !panRequested;
    if (event.button === 2 && !panRequested) {
      this.allowContextFinish = true;
      return;
    }
    if (event.button !== 0 && event.button !== 1 && !(event.button === 2 && event.ctrlKey)) return;
    event.preventDefault();
    this.canvas.focus({preventScroll: true});
    if (this.callbacks.busy()) return;
    const at = this.current = this.location(event);
    this.modifiedPointer = event.ctrlKey || event.shiftKey;
    // In an active placement tool a click always adds the next point. This
    // avoids grabbing nearby anatomy when placing another role deliberately.
    const focus = panRequested || windowRequested ? null : (this.planHit(at) || this.updateLandmarkFocus() || this.bodyHit(at));
    if (focus && this.handles[focus.target.role]) this.selectedPlanRole = focus.target.role;
    const target = focus?.target ?? null;
    if (!target) this.landmarkFocus = null;
    const grabOffset = focus ? [focus.screen[0] - at[0], focus.screen[1] - at[1]] : null;
    const pan = panRequested || (!windowRequested && !this.active && !target);
    const window = windowRequested ? {low: this.window.low, high: this.window.high, invert: this.window.invert} : null;
    this.gesture = {at, pan, target, grabOffset, window, moved: false, x: this.x, y: this.y, pointerId: event.pointerId};
    this.canvas.setPointerCapture(event.pointerId);
    this.draw();
  }

  move(event) {
    const at = this.location(event);
    const g = this.gesture;
    if (g && g.pointerId !== event.pointerId) return;
    this.current = at;
    this.modifiedPointer = event.ctrlKey || event.shiftKey;
    if (g) {
      const dx = at[0] - g.at[0], dy = at[1] - g.at[1];
      g.moved ||= Math.hypot(dx, dy) > 2;
      if (g.window && g.moved) {
        this.queueWindowPreview(g, this.windowAt(g, at));
      } else if (g.pan && g.moved) {
        this.x = g.x + dx;
        this.y = g.y + dy;
        this.fitted = false;
      } else if (g.target && g.moved) {
        this.queuePointPreview(g, this.dragPoint(g, at));
      }
    }
    this.draw();
  }

  up(event) {
    const g = this.gesture;
    if (!g || g.pointerId !== event.pointerId) return;
    this.current = this.location(event);
    this.modifiedPointer = event.ctrlKey || event.shiftKey;
    if (g.target) g.moved ||= Math.hypot(this.current[0] - g.at[0], this.current[1] - g.at[1]) > 2;
    const committing = Boolean(g.target && g.moved);
    const window = g.window && g.moved ? this.windowAt(g, this.current) : null;
    this.endGesture(committing || !!window);
    if (window) {
      this.callbacks.window(window).finally(() => { this.clearWindowPreview(); this.draw(); });
    } else if (committing) {
      const [x, y] = this.dragPoint(g, this.current);
      this.callbacks.move({...g.target, x, y}).finally(() => {
        this.clearPointPreview();
        this.draw();
      });
    } else if (g.target) {
      this.updateLandmarkFocus(true);
    } else if (!g.pan && !g.window && !g.moved && this.active) {
      const [x, y] = this.imagePoint(this.current);
      this.callbacks.place({x, y});
    }
    this.draw();
  }

  clearPointPreview() {
    if (!this.pointPreview) return;
    this.pointPreview = null;
    this.callbacks.previewResults(null);
  }

  endGesture(keepPreview = false) {
    const {pointerId} = this.gesture;
    this.gesture = null;
    this.pendingPreview = null;
    this.pendingWindowPreview = null;
    ++this.windowPreviewSerial;
    if (!keepPreview) this.clearPointPreview();
    if (!keepPreview) this.clearWindowPreview();
    if (this.canvas.hasPointerCapture(pointerId)) this.canvas.releasePointerCapture(pointerId);
  }

  cancelGesture(pointerId = this.gesture?.pointerId) {
    if (!this.gesture || this.gesture.pointerId !== pointerId) return;
    this.endGesture();
    this.draw();
  }

  async queuePointPreview(gesture, [x, y]) {
    // Keep at most one calculation in flight and one latest position queued.
    this.pendingPreview = {gesture, point: {...gesture.target, x, y}};
    if (this.previewInFlight) return;
    this.previewInFlight = true;
    try {
      while (this.pendingPreview) {
        const next = this.pendingPreview;
        this.pendingPreview = null;
        const preview = await this.callbacks.previewMove(next.point).catch(() => null);
        if (this.gesture === next.gesture && preview?.edited) {
          this.pointPreview = preview;
          this.callbacks.previewResults(preview.state);
          this.draw();
        }
      }
    } finally {
      this.previewInFlight = false;
    }
  }

  windowAt(gesture, at) {
    const {low, high, invert} = gesture.window;
    const shift = (at[1] - gesture.at[1]) * (high - low) / Math.max(1, this.height);
    return {low: low + shift, high: high + shift, invert};
  }

  clearWindowPreview() {
    this.windowPreview?.close();
    this.windowPreview = null;
    this.callbacks.previewWindowValues(null);
  }

  async queueWindowPreview(gesture, window) {
    this.pendingWindowPreview = {gesture, window, serial: ++this.windowPreviewSerial};
    this.callbacks.previewWindowValues(window);
    if (this.windowPreviewInFlight) return;
    this.windowPreviewInFlight = true;
    try {
      while (this.pendingWindowPreview) {
        const next = this.pendingWindowPreview;
        this.pendingWindowPreview = null;
        const response = await this.callbacks.previewWindow(next.window).catch(() => null);
        if (!response?.preview || this.gesture !== next.gesture) continue;
        const bitmap = await createImageBitmap(new Blob([response.preview], {type: "image/png"}));
        if (this.gesture !== next.gesture || this.windowPreviewSerial !== next.serial) {
          bitmap.close();
          continue;
        }
        this.windowPreview?.close();
        this.windowPreview = bitmap;
        this.draw();
      }
    } finally {
      this.windowPreviewInFlight = false;
    }
  }

  placementContinuation() {
    if (!this.active || !this.current || this.panMode || this.space || this.gesture?.pan || this.gesture?.window) return;
    let mark = this.marks.find((item) => item.role === this.active);
    const fragment = this.active.endsWith("_fragmentBoundary");
    if (fragment && !mark?.points.length) {
      const cut = this.marks.find(item => item.role === this.activeSide + (this.cutKind === "stepped" ? "_resectionStepped" : "_resectionStraight"));
      if (cut?.points.length) mark={role:this.active,kind:"curve",curve_type:0,color:[238,208,95],points:[cut.points.at(-1)]};
    }
    if (!mark?.points.length) return;
    const [i, j] = this.imagePoint(this.current);
    if (!fragment && (i < 0 || j < 0 || i > this.shape[0] - 1 || j > this.shape[1] - 1)) return;
    const start = this.position(mark.points.at(-1));
    if (Math.hypot(start[0] - this.current[0], start[1] - this.current[1]) < 2) return;
    return {role: mark.role, point: this.current, mark};
  }

  drawPlacementGuide(ctx, continuation = this.placementContinuation()) {
    if (!continuation) return;
    const {mark, point} = continuation;
    const curved = mark.kind === "curve" && mark.curve_type !== 0;
    const screen = [...mark.points.map((p) => this.position(p)), point];
    ctx.save();
    traceMarkupPath(ctx, screen, curved, screen.length - 1);
    ctx.strokeStyle = `rgba(${mark.color.join(",")},0.86)`;
    ctx.lineWidth = 1.7;
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.restore();
  }

  drawLandmarkFocus(ctx, marks, target, showChoice) {
    const mark = marks.find((item) => item.role === target.role);
    const point = mark?.points[target.index];
    if (!point) return;
    const [x, y] = this.position(point);
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#0b1119";
    ctx.stroke();
    ctx.lineWidth = 1.25;
    ctx.strokeStyle = "#f3f7fc";
    ctx.stroke();
    if (showChoice && this.width > 28 && this.height > 32) {
      const name = mark.name?.replace(/^Hip Measurements - /, "") || "Landmark";
      const label = `${name} · Point ${target.index + 1} · Click to switch`;
      ctx.font = "600 12px system-ui";
      ctx.textBaseline = "middle";
      const width = Math.min(this.width - 10, Math.ceil(ctx.measureText(label).width) + 14);
      const left = Math.max(5, Math.min(x + 11, this.width - width - 5));
      const top = Math.max(5, y + 32 <= this.height ? y + 7 : y - 30);
      ctx.fillStyle = "#121d27";
      ctx.fillRect(left, top, width, 22);
      ctx.fillStyle = "#f3f7fc";
      ctx.fillText(label, left + 7, top + 11, width - 14);
    }
    ctx.restore();
  }

  draw() {
    if (!this.width) return;
    const ctx = this.ctx;
    const g = this.gesture;
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    ctx.fillStyle = "#090b0d";
    ctx.fillRect(0, 0, this.width, this.height);
    this.canvas.style.cursor = g?.pan && g.moved ? "grabbing" : "default";
    if (!this.bitmap) return;
    const pos = (p) => this.position(p);
    const [x, y] = pos([-.5, -.5]);
    const [rx, ry] = pos([this.shape[0] - .5, this.shape[1] - .5]);
    // Show individual source pixels when magnified. Keep filtering when a view
    // is fitted or lightly zoomed and pixels have less room on the display.
    ctx.imageSmoothingEnabled = this.zoom * Math.min(...this.scale) * this.ratio < 2;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(this.windowPreview || this.bitmap, x, y, rx - x, ry - y);
    this.drawFragmentPixels(ctx, this.windowPreview || this.bitmap, this.pointPreview?.fragments ?? this.fragments, x, y, rx - x, ry - y);
    const dragPoint = g?.target && g.moved ? this.dragPoint(g, this.current) : null;
    const marks = this.pointPreview?.markups ?? (g?.target && g.moved ? this.marks.map((m) => m.role !== g.target.role ? m : {
      ...m, points: m.points.map((p, i) => i === g.target.index ? dragPoint : p),
    }) : this.marks);
    const continuation = this.placementContinuation();
    this.drawImplants(ctx, marks, pos);
    drawMarks(ctx, marks, pos, 1.65, 3.05, g?.target, continuation);
    this.drawPlacementGuide(ctx, continuation);
    const hp = !this.active && this.rotationHandle(this.selectedPlanRole, this.pointPreview?.rotation_handles ?? this.handles);
    if (hp) {
      ctx.save(); ctx.beginPath(); ctx.strokeStyle="#f3f9fd"; ctx.lineWidth=1.5;
      ctx.moveTo(...hp[0]); ctx.lineTo(...hp[1]); ctx.stroke();
      ctx.beginPath(); ctx.arc(...hp[1],6,0,2*Math.PI); ctx.fillStyle="#19576a"; ctx.fill(); ctx.stroke(); ctx.restore();
    }
    const focus = g ? null : this.updateLandmarkFocus();
    const target = g?.target ?? focus?.target;
    if (target && !target.role.endsWith("Rotation")) this.drawLandmarkFocus(ctx, marks, target, focus?.multiple);
    this.callbacks.zoom(this.zoom);
  }

  async exportPNG(snapshot, summary, annotator, includeValues) {
    if (!this.bitmap) throw new Error("Open a radiograph before exporting.");
    const output = document.createElement("canvas");
    [output.width, output.height] = exportImageDimensions(this.shape, this.scale);
    const ctx = output.getContext("2d", {alpha: false});
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    const w = output.width, h = output.height;
    ctx.drawImage(this.bitmap, 0, 0, w, h);
    this.drawFragmentPixels(ctx, this.bitmap, snapshot.fragments, 0, 0, w, h);
    const position = ([i, j]) => [(i + .5) * w / this.shape[0], (j + .5) * h / this.shape[1]];
    const glyph = Math.max(1.3, Math.min(6.0, Math.min(w, h) * .0029));
    const lines = [`Annotator: ${annotator}`, ...(includeValues ? summary : [])];
    if (includeValues && summary.some((line) => /\bsu\b/.test(line))) lines.push("su = scene units");
    const minSide = Math.min(w, h);
    const font = Math.max(5, Math.min(26, Math.floor(minSide * .013)));
    const pad = Math.round(font * .62), lineHeight = Math.round(font * 1.42);
    ctx.font = `600 ${font}px system-ui`;
    const maxLines = Math.max(5, Math.floor((h - 4 * pad) / lineHeight));
    const groups = Array.from({length: Math.ceil(lines.length / maxLines)}, (_, i) => lines.slice(i * maxLines, (i + 1) * maxLines));
    const blockWidths = groups.map((chunk) => Math.min(w - pad * 2, Math.max(...chunk.map((line) => ctx.measureText(line).width)) + 2 * pad));
    const totalWidth = blockWidths.reduce((sum, value) => sum + value, 0) + pad * (groups.length - 1);
    let left = Math.max(pad, (w - totalWidth) / 2);
    const top = Math.max(pad, h - Math.min(lines.length, maxLines) * lineHeight - pad * 3);
    const panels = groups.map((chunk, i) => {
      const boxWidth = Math.min(blockWidths[i], w - left);
      const panel = {left, boxWidth, chunk};
      left += boxWidth + pad;
      return panel;
    });
    // The panel darkens only the radiograph. Annotations retain their colours
    // even inside the panel, and a thin outline keeps result text readable.
    ctx.fillStyle = "rgba(8, 12, 16, 0.4)";
    for (const panel of panels) ctx.fillRect(panel.left, top, panel.boxWidth, panel.chunk.length * lineHeight + 2 * pad);
    ctx.save();
    await this.loadImplants(snapshot.markups);
    this.drawImplants(ctx, snapshot.markups, position);
    drawMarks(ctx, snapshot.markups, position, Math.max(1.25, glyph * .70), glyph);
    ctx.restore();
    ctx.fillStyle = "#f3f7fc";
    ctx.strokeStyle = "#080c10";
    ctx.lineWidth = Math.max(1, font * .14);
    panels.forEach(({left: panelLeft, boxWidth, chunk}) => {
      chunk.forEach((line, j) => {
        const x = panelLeft + pad;
        const y = top + pad + font + j * lineHeight;
        const maxWidth = Math.max(1, boxWidth - 2 * pad);
        ctx.strokeText(line, x, y, maxWidth);
        ctx.fillText(line, x, y, maxWidth);
      });
    });
    return new Promise((resolve, reject) => output.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error("The annotated image could not be saved.")), "image/png"));
  }
}
