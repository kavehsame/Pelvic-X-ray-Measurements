"use strict";

// Pyodide sees an allowlist of embedded assets. Even its package loader
// cannot fall through to the browser's network fetch.
const virtualRoot = "https://pelvic-runtime.invalid/";
let embedded = new Map();
let python;
let dispatch;
let openjpeg;
let charls;
globalThis.fetch = async (request) => {
  const url = typeof request === "string" ? request : request.url ?? request.href;
  if (typeof url !== "string" || !url.startsWith(virtualRoot)) {
    throw new TypeError("Network access is disabled in the measurement worker.");
  }
  const filename = url.slice(virtualRoot.length);
  if (!embedded.has(filename)) throw new TypeError("This asset is not bundled with the app.");
  const type = filename.endsWith(".wasm") ? "application/wasm" : "application/octet-stream";
  return new Response(embedded.get(filename), {headers: {"content-type": type}});
};

function checkJPEGFrame(frame, width, height, bytesPerSample, sof) {
  if (frame[0] !== 0xff || frame[1] !== 0xd8) throw new Error("Invalid lossless JPEG frame.");
  for (let cursor = 2; cursor + 4 < frame.length;) {
    if (frame[cursor++] !== 0xff) throw new Error("Invalid lossless JPEG segment.");
    while (frame[cursor] === 0xff) cursor++;
    const marker = frame[cursor++];
    const length = frame[cursor] * 256 + frame[cursor + 1];
    if (length < 2 || length + cursor > frame.length) throw new Error("Truncated lossless JPEG segment.");
    if (marker === sof) {
      const precision = frame[cursor + 2];
      const rows = frame[cursor + 3] * 256 + frame[cursor + 4];
      const columns = frame[cursor + 5] * 256 + frame[cursor + 6];
      if (length < 11 || rows !== height || columns !== width || frame[cursor + 7] !== 1
          || precision < 2 || precision > bytesPerSample * 8) {
        throw new Error("DICOM metadata and the lossless JPEG frame differ.");
      }
      return;
    }
    if (marker === 0xda) break;
    cursor += length;
  }
  throw new Error("The compressed frame header was not found.");
}

function checkJ2KFrame(bytes, width, height, bytesPerSample) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  // A DICOM frame generally starts with the J2K codestream. Some exports wrap
  // it in a JP2 container. Read its boxes in memory without resolving references.
  while (offset + 8 < bytes.length && view.getUint16(offset) !== 0xff4f) {
    const length = view.getUint32(offset);
    if (length < 8 || length > bytes.length - offset) throw new Error("Invalid JPEG 2000 container.");
    if (view.getUint32(offset + 4) === 0x6a703263) { offset += 8; break; } // jp2c
    offset += length;
  }
  if (offset + 45 > bytes.length || view.getUint32(offset) !== 0xff4fff51
      || view.getUint32(offset + 8) - view.getUint32(offset + 16) !== width
      || view.getUint32(offset + 12) - view.getUint32(offset + 20) !== height
      || view.getUint16(offset + 40) !== 1 || (bytes[offset + 42] & 127) + 1 > bytesPerSample * 8
      || bytes[offset + 43] !== 1 || bytes[offset + 44] !== 1) {
    throw new Error("DICOM metadata and the JPEG 2000 frame differ.");
  }
}

function decodeCompressed(frame, width, height, bytesPerSample, codec) {
  const view = frame instanceof Uint8Array ? null : frame.getBuffer("u8");
  try {
    const bytes = (view ? view.data : frame).slice();
    const expected = width * height * bytesPerSample;
    if (codec === "lossless") {
      checkJPEGFrame(bytes, width, height, bytesPerSample, 0xc3);
      const pixels = new globalThis.JPEGLossless.Decoder().decode(bytes.buffer, 0, bytes.length, bytesPerSample);
      if (pixels.byteLength < expected) throw new Error("The decoded DICOM frame is incomplete.");
      return new Uint8Array(pixels.buffer, pixels.byteOffset, expected).slice();
    }
    let decoder;
    if (codec === "j2k") {
      checkJ2KFrame(bytes, width, height, bytesPerSample);
      decoder = new openjpeg.J2KDecoder();
    } else if (codec === "jls") {
      checkJPEGFrame(bytes, width, height, bytesPerSample, 0xf7);
      decoder = new charls.JpegLSDecoder();
    } else {
      throw new Error("Unknown DICOM decoder.");
    }
    try {
      decoder.getEncodedBuffer(bytes.length).set(bytes);
      decoder.decode();
      const frameInfo = decoder.getFrameInfo();
      const pixels = decoder.getDecodedBuffer();
      if (frameInfo.width !== width || frameInfo.height !== height || frameInfo.componentCount !== 1) {
        throw new Error("The decoded DICOM dimensions do not match the header.");
      }
      if (bytesPerSample === 2 && pixels.length === width * height) {
        return new Uint8Array(Uint16Array.from(pixels).buffer);
      }
      if (pixels.length !== expected) throw new Error("The decoded DICOM frame size differs from its header.");
      return pixels.slice();
    } finally {
      decoder.delete();
    }
  } finally {
    view?.release();
  }
}

async function startWorker(files) {
  embedded = new Map(files);
  const moduleURL = URL.createObjectURL(new Blob([embedded.get("pyodide.asm.mjs")], {type: "text/javascript"}));
  const createPyodideModule = (await import(moduleURL)).default;
  try {
    python = await globalThis.loadPyodide({
      indexURL: virtualRoot,
      packageBaseUrl: virtualRoot,
      createPyodideModule,
      lockFileContents: JSON.parse(new TextDecoder().decode(embedded.get("pyodide-lock.json"))),
      packages: ["numpy", "pillow"],
      checkAPIVersion: true,
    });
    python.FS.mkdirTree("/transfer");
    python.FS.mkdirTree("/app");
    python.unpackArchive(embedded.get("core.zip"), "zip", {extractDir: "/app"});
    python.unpackArchive(embedded.get("pydicom-code.zip"), "zip", {extractDir: "/app"});
    [openjpeg, charls] = await Promise.all([
      OpenJPEGWASM({wasmBinary: embedded.get("openjpeg.wasm")}),
      CharLSWASM({wasmBinary: embedded.get("charls.wasm")}),
    ]);
    python.registerJsModule("worker_codecs", {decode_compressed: decodeCompressed});
    python.runPython("import sys\nsys.path.insert(0, '/app')\nfrom core.engine import dispatch");
    dispatch = python.globals.get("dispatch");
    embedded.clear();
  } finally {
    URL.revokeObjectURL(moduleURL);
  }
}

self.onmessage = async ({data: message}) => {
  const {id, action, args, inputs} = message;
  try {
    if (action === "init") await startWorker(message.files);
    if (inputs) for (const [name, buffer] of inputs) python.FS.writeFile("/transfer/" + name, new Uint8Array(buffer));
    const response = JSON.parse(dispatch(action === "init" ? "configure" : action, JSON.stringify(args || {})));
    if (response.error) {
      self.postMessage({id, ...response});
      return;
    }
    const buffers = [];
    const getBytes = (path) => {
      const bytes = python.FS.readFile(path);
      python.FS.unlink(path);
      buffers.push(bytes.buffer);
      return bytes;
    };
    if (response.preview) response.preview = getBytes(response.preview);
    if (response.files) {
      for (const [key, path] of Object.entries(response.files)) response.files[key] = getBytes(path);
    }
    self.postMessage({id, response}, buffers);
  } catch (error) {
    const detail = String(error.message || error);
    const safe = action === "init" ? "The browser could not start the measurement engine. Reload the page to retry."
      : "Chrome could not complete that operation. Check the file and try again.";
    self.postMessage({id, error: safe, detail});
  } finally {
    if (python && inputs) {
      for (const [name] of inputs) {
        const path = "/transfer/" + name;
        if (python.FS.analyzePath(path).exists) python.FS.unlink(path);
      }
    }
  }
};
