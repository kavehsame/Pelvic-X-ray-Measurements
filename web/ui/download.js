"use strict";

class ComponentDownloadError extends Error {
  constructor(message, details, retryable = false) {
    super(message);
    this.name = "ComponentDownloadError";
    this.details = details;
    this.retryable = retryable;
  }
}

async function runtimeDigest(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (value) => value.toString(16).padStart(2, "0")).join("");
}

async function boundedRuntimeResponse(response, limit) {
  if (!response.ok || !response.body) throw new Error("Missing response body.");
  const reader = response.body.getReader(), blocks = [];
  let length = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new Error("The response exceeds the component size limit.");
      }
      blocks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const block of blocks) { result.set(block, offset); offset += block.byteLength; }
  return result;
}

async function verifiedComponent(content, record, settings) {
  const document = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(content));
  if (document.format !== "pelvic-runtime-component-v1" || document.encoding !== "base64" || document.compression !== "gzip"
      || document.payloadSha256 !== settings.payloadHash || document.index !== record.index
      || document.offset !== record.offset || document.bytes !== record.bytes
      || document.sha256 !== record.sha256 || typeof document.data !== "string"
      || document.data.length !== 4 * Math.ceil(record.bytes / 3)) {
    throw new Error("The component metadata does not match this build.");
  }
  const decoded = atob(document.data);
  if (decoded.length !== record.bytes) throw new Error("The component is incomplete.");
  const bytes = Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  if (await runtimeDigest(bytes) !== record.sha256) throw new Error("The component checksum differs.");
  return bytes;
}

async function fetchRuntimeComponent(url, record, settings, stop) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (stop.aborted) cancel();
  stop.addEventListener("abort", cancel, {once: true});
  const timeout = setTimeout(() => { timedOut = true; cancel(); }, settings.componentTimeoutMs);
  const details = {version: settings.version, component: url.href, stage: "download"};
  try {
    const response = await fetch(url, {
      method: "GET", cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer",
      redirect: "error", signal: controller.signal,
    });
    details.httpStatus = response.status;
    details.contentType = response.headers.get("Content-Type") || "not supplied";
    if (!response.ok) {
      throw new ComponentDownloadError(
        `App components could not be downloaded (HTTP ${response.status}). Some restricted networks, including hospitals, may block this app. Ask your IT team to check access to this website.`,
        details, response.status === 408 || response.status === 429 || response.status >= 500);
    }
    if (details.contentType.toLowerCase().includes("text/html")) {
      throw new ComponentDownloadError(
        "The network returned a web page instead of an app component. It may be a sign-in or filtering page. Ask your IT team to check access to this website.", details);
    }
    const content = await boundedRuntimeResponse(response, record.documentBytes + 4096);
    let bytes;
    try {
      details.stage = "verification";
      bytes = await verifiedComponent(content, record, settings);
    } catch (error) {
      throw new ComponentDownloadError(
        "An app component did not pass verification. Reload the page and try again. If this persists, ask your IT team whether the download is being filtered or replaced.",
        {...details, reason: error.message});
    }
    return {bytes, content};
  } catch (error) {
    if (stop.aborted || error instanceof ComponentDownloadError) throw error;
    throw new ComponentDownloadError(timedOut
      ? "The component download timed out. Try Start again; completed components can be reused."
      : "The browser could not download an app component. Check the connection. Some restricted networks, including hospitals, may prevent this app from starting.",
    {...details, reason: timedOut ? "timeout" : error.message}, true);
  } finally {
    clearTimeout(timeout);
    stop.removeEventListener("abort", cancel);
  }
}

async function loadRuntimePackage(settings, status, progress) {
  const cacheKey = new URL(settings.payload, location.href);
  cacheKey.searchParams.set("sha256", settings.payloadHash);
  let cache;
  try {
    cache = await globalThis.caches?.open("pelvic-xray-software");
    const stored = await cache?.match(cacheKey.href);
    if (stored) {
      const bytes = await boundedRuntimeResponse(stored, settings.payloadSize);
      if (bytes.byteLength === settings.payloadSize && await runtimeDigest(bytes) === settings.payloadHash) return bytes;
      await cache.delete(cacheKey.href);
    }
  } catch {
    await cache?.delete(cacheKey.href).catch(() => {});
  }
  if (!globalThis.DecompressionStream) throw new Error("Update Chrome or Edge to prepare this app in the browser.");
  const transport = new Uint8Array(settings.transportSize);
  const urls = settings.components.map((record) => new URL(record.path, location.href));
  if (urls.some((url) => url.origin !== location.origin)) throw new Error("App components must come from this website.");
  const stop = new AbortController();
  let next = 0, completed = 0, received = 0;
  progress.max = settings.transportSize;
  progress.value = 0;
  progress.hidden = false;
  status.textContent = "Downloading app components…";
  async function part(record, url) {
    try {
      const stored = await cache?.match(url.href);
      if (stored) return await verifiedComponent(await boundedRuntimeResponse(stored, record.documentBytes + 4096), record, settings);
    } catch { await cache?.delete(url.href).catch(() => {}); }
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const result = await fetchRuntimeComponent(url, record, settings, stop.signal);
        await cache?.put(url.href, new Response(result.content, {headers: {"Content-Type": "application/json"}})).catch(() => {});
        return result.bytes;
      } catch (error) {
        if (!error.retryable || stop.signal.aborted || attempt === 1) throw error;
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  }
  async function run() {
    while (!stop.signal.aborted && next < settings.components.length) {
      const index = next++, record = settings.components[index];
      const block = await part(record, urls[index]);
      if (stop.signal.aborted) return;
      transport.set(block, record.offset);
      completed++;
      received += block.byteLength;
      progress.value = received;
      status.textContent = `Downloading app components… ${completed}/${settings.components.length}`;
    }
  }
  const workers = Array.from({length: Math.min(3, settings.components.length)}, run);
  try { await Promise.all(workers); }
  catch (error) { stop.abort(); await Promise.allSettled(workers); throw error; }
  if (received !== settings.transportSize || await runtimeDigest(transport) !== settings.transportHash) {
    throw new ComponentDownloadError("The complete app package did not pass verification. Reload the page and try again.",
      {version: settings.version, stage: "package verification"});
  }
  status.textContent = "Verifying app components…";
  let bytes;
  try {
    const stream = new Blob([transport]).stream().pipeThrough(new DecompressionStream("gzip"));
    bytes = await boundedRuntimeResponse(new Response(stream), settings.payloadSize);
    if (bytes.byteLength !== settings.payloadSize || await runtimeDigest(bytes) !== settings.payloadHash) {
      throw new Error("The expanded package checksum differs.");
    }
  } catch (error) {
    throw new ComponentDownloadError("The app package could not be verified. Reload the page and try again.",
      {version: settings.version, stage: "package expansion", reason: error.message});
  }
  // Cache only verified software. No image picker is enabled before this returns.
  let saved = false;
  if (cache) {
    try {
      await cache.put(cacheKey.href, new Response(bytes, {headers: {"Content-Type": "application/octet-stream"}}));
      saved = true;
    } catch { /* Storage may be unavailable or full; the current session can continue. */ }
  }
  if (saved) await Promise.all(urls.map((url) => cache.delete(url.href).catch(() => {})));
  return bytes;
}
