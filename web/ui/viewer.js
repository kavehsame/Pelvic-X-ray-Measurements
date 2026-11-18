"use strict";

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
    this.marks = [];
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
    document.addEventListener("keydown", (event) => {
      if (event.code === "Space" && document.activeElement === canvas) {
        event.preventDefault();
        this.space = true;
        this.draw();
      }
    });
    document.addEventListener("keyup", (event) => {
      if (event.code !== "Space" || !this.space) return;
      this.space = false;
      this.draw();
    });
    window.addEventListener("blur", () => {
      this.space = false;
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

  async update(snapshot, reset) {
    const serial = ++this.updateSerial;
    this.pointPreview = null;
    this.window = snapshot.image;
    if (this.panMode && (reset || (snapshot.active_role && snapshot.active_role !== this.active))) {
      this.panMode = false;
      this.callbacks.panModeChanged(false);
    }
    this.active = snapshot.active_role;
    this.marks = snapshot.markups;
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
    this.draw();
  }

  zoomAt(factor, at = [this.width / 2, this.height / 2]) {
    if (!this.shape) return;
    const image = this.imagePoint(at);
    this.zoom = Math.min(12, Math.max(0.005, this.zoom * factor));
    this.x = at[0] - image[0] * this.scale[0] * this.zoom;
    this.y = at[1] - image[1] * this.scale[1] * this.zoom;
    this.fitted = false;
    this.draw();
  }

  findPoint(at) {
    let best = null;
    let min = 8;
    for (const m of this.marks) if (!m.locked) {
      m.points.forEach((p, index) => {
        const screen = this.position(p);
        const distance = Math.hypot(at[0] - screen[0], at[1] - screen[1]);
        if (distance < min) { min = distance; best = {role: m.role, index}; }
      });
    }
    return best;
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
    // In an active placement tool a click always adds the next point. This
    // avoids grabbing nearby anatomy when placing another role deliberately.
    const target = !panRequested && !windowRequested && !this.active ? this.findPoint(at) : null;
    const pan = panRequested || (!windowRequested && !this.active && !target);
    const window = windowRequested ? {low: this.window.low, high: this.window.high, invert: this.window.invert} : null;
    this.gesture = {at, pan, target, window, moved: false, x: this.x, y: this.y, pointerId: event.pointerId};
    this.canvas.setPointerCapture(event.pointerId);
    if (pan || window) this.draw();
  }

  move(event) {
    const at = this.location(event);
    const g = this.gesture;
    if (g && g.pointerId !== event.pointerId) return;
    this.current = at;
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
        this.queuePointPreview(g, this.imagePoint(at));
      }
    }
    this.draw();
  }

  up(event) {
    const g = this.gesture;
    if (!g || g.pointerId !== event.pointerId) return;
    this.current = this.location(event);
    const [x, y] = this.imagePoint(this.current);
    const committing = Boolean(g.target && g.moved);
    const window = g.window && g.moved ? this.windowAt(g, this.current) : null;
    this.endGesture(committing || !!window);
    if (window) {
      this.callbacks.window(window).finally(() => { this.clearWindowPreview(); this.draw(); });
    } else if (committing) {
      this.callbacks.move({...g.target, x, y}).finally(() => {
        this.clearPointPreview();
        this.draw();
      });
    } else if (!g.pan && !g.window && !g.moved && this.active) {
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
    const mark = this.marks.find((item) => item.role === this.active);
    if (!mark?.points.length) return;
    const [i, j] = this.imagePoint(this.current);
    if (i < 0 || j < 0 || i > this.shape[0] - 1 || j > this.shape[1] - 1) return;
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

  draw() {
    if (!this.width) return;
    const ctx = this.ctx;
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    ctx.fillStyle = "#090b0d";
    ctx.fillRect(0, 0, this.width, this.height);
    this.canvas.style.cursor = this.gesture?.window ? "ns-resize" : this.gesture?.pan ? "grabbing" :
      !this.bitmap ? "default" : this.panMode || this.space || !this.active ? "grab" : "crosshair";
    if (!this.bitmap) return;
    const pos = (p) => this.position(p);
    const [x, y] = pos([-.5, -.5]);
    const [rx, ry] = pos([this.shape[0] - .5, this.shape[1] - .5]);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(this.windowPreview || this.bitmap, x, y, rx - x, ry - y);
    const g = this.gesture;
    const marks = this.pointPreview?.markups ?? (g?.target && g.moved ? this.marks.map((m) => m.role !== g.target.role ? m : {
      ...m, points: m.points.map((p, i) => i === g.target.index ? this.imagePoint(this.current) : p),
    }) : this.marks);
    const continuation = this.placementContinuation();
    drawMarks(ctx, marks, pos, 1.65, 3.05, g?.target, continuation);
    this.drawPlacementGuide(ctx, continuation);
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
