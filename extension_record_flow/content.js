(function initializeRecordFlow() {
  if (window.gpmRecorderInitialized === true) {
    return;
  }

  window.gpmRecorderInitialized = true;

  const recorderState = {
    recording: false,
    recordedSteps: [],
    networkEvents: [],
    listenerOptions: { capture: true, passive: true },
    lastEventKey: "",
    lastEventAt: 0
  };

  patchFetch(recorderState);
  patchXhr(recorderState);

  chrome.runtime.onMessage.addListener(handleMessage);

  function handleMessage(message, _sender, sendResponse) {
    try {
      if (!message || typeof message.type !== "string") {
        sendResponse({ ok: false, error: "Invalid recorder message." });
        return false;
      }
      if (message.type === "ping") {
        sendResponse({ ok: true });
        return false;
      }
      if (message.type === "start_recording") {
        startRecording(recorderState);
        sendResponse({ ok: true, stepCount: recorderState.recordedSteps.length });
        return false;
      }
      if (message.type === "stop_recording") {
        stopRecording(recorderState);
        sendResponse({ ok: true, stepCount: recorderState.recordedSteps.length });
        return false;
      }
      if (message.type === "add_annotation") {
        addAnnotation(recorderState, message.text || "");
        sendResponse({ ok: true, stepCount: recorderState.recordedSteps.length });
        return false;
      }
      if (message.type === "dump_recording") {
        sendResponse(buildDump(recorderState));
        return false;
      }
      sendResponse({ ok: false, error: `Unsupported recorder message: ${message.type}` });
      return false;
    } catch (error) {
      sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
      return false;
    }
  }

  function startRecording(state) {
    cleanupListeners(state);
    state.recordedSteps = [];
    state.networkEvents = [];
    state.recording = true;
    state.lastEventKey = "";
    state.lastEventAt = 0;
    addListeners(state);
  }

  function stopRecording(state) {
    cleanupListeners(state);
    state.recording = false;
  }

  function addListeners(state) {
    document.addEventListener("click", onClick, state.listenerOptions);
    document.addEventListener("input", onInput, state.listenerOptions);
    document.addEventListener("change", onChange, state.listenerOptions);
  }

  function cleanupListeners(state) {
    document.removeEventListener("click", onClick, state.listenerOptions);
    document.removeEventListener("input", onInput, state.listenerOptions);
    document.removeEventListener("change", onChange, state.listenerOptions);
  }

  function onClick(event) {
    recordElementEvent(recorderState, "click", event);
  }

  function onInput(event) {
    recordElementEvent(recorderState, "input", event);
  }

  function onChange(event) {
    recordElementEvent(recorderState, "change", event);
  }

  function recordElementEvent(state, eventType, event) {
    if (!state.recording || !(event.target instanceof Element)) {
      return;
    }
    const target = event.target;
    const selector = buildBestSelector(target);
    const eventKey = `${eventType}:${selector.value}`;
    const now = Date.now();
    if (eventKey === state.lastEventKey && now - state.lastEventAt < 250) {
      return;
    }
    state.lastEventKey = eventKey;
    state.lastEventAt = now;
    state.recordedSteps.push({
      type: eventType,
      selector: selector.value,
      selectorStrategy: selector.strategy,
      tagName: target.tagName.toLowerCase(),
      text: normalizedText(target).slice(0, 160),
      value: safeElementValue(target),
      attributes: safeAttributes(target),
      url: window.location.href,
      timestamp: new Date().toISOString()
    });
  }

  function addAnnotation(state, text) {
    const note = String(text || "").trim();
    if (!note) {
      throw new Error("Annotation text is empty.");
    }
    state.recordedSteps.push({
      type: "annotation",
      text: note,
      url: window.location.href,
      timestamp: new Date().toISOString()
    });
  }

  function buildDump(state) {
    return {
      ok: true,
      currentUrl: window.location.href,
      recordedSteps: state.recordedSteps.slice(),
      unrolledDOM: unrollDocument(),
      networkSnapshot: collectNetworkSnapshot(state)
    };
  }

  function buildBestSelector(element) {
    const dataTestId = element.getAttribute("data-testid");
    if (dataTestId) {
      return selectorResult(`[data-testid="${cssEscape(dataTestId)}"]`, "data-testid");
    }
    const dataCy = element.getAttribute("data-cy");
    if (dataCy) {
      return selectorResult(`[data-cy="${cssEscape(dataCy)}"]`, "data-cy");
    }
    if (element.id && isStableToken(element.id)) {
      return selectorResult(`#${cssEscape(element.id)}`, "id");
    }
    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) {
      return selectorResult(`${tagName(element)}[aria-label="${cssEscape(ariaLabel)}"]`, "aria-label");
    }
    const name = element.getAttribute("name");
    if (name) {
      return selectorResult(`${tagName(element)}[name="${cssEscape(name)}"]`, "name");
    }
    const text = normalizedText(element);
    if (text.length > 0 && text.length <= 80) {
      return selectorResult(textXPath(element, text), "text-xpath");
    }
    const chain = chainSelector(element);
    if (chain) {
      return selectorResult(chain, "chain");
    }
    return selectorResult(positionalXPath(element), "positional-xpath");
  }

  function selectorResult(value, strategy) {
    return { value, strategy };
  }

  function tagName(element) {
    return element.tagName.toLowerCase();
  }

  function normalizedText(element) {
    return String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
  }

  function textXPath(element, text) {
    const escapedText = xpathLiteral(text);
    return `//${tagName(element)}[normalize-space(.)=${escapedText}]`;
  }

  function chainSelector(element) {
    const parts = [];
    let current = element;
    for (let depth = 0; depth < 4 && current && current.nodeType === Node.ELEMENT_NODE; depth += 1) {
      parts.unshift(simpleSelectorPart(current));
      if (current.id && isStableToken(current.id)) {
        break;
      }
      current = current.parentElement;
    }
    return parts.length > 0 ? parts.join(" > ") : "";
  }

  function simpleSelectorPart(element) {
    if (element.id && isStableToken(element.id)) {
      return `#${cssEscape(element.id)}`;
    }
    const classes = Array.from(element.classList || [])
      .filter(isStableToken)
      .slice(0, 2)
      .map((className) => `.${cssEscape(className)}`)
      .join("");
    const index = siblingIndex(element);
    return `${tagName(element)}${classes}:nth-of-type(${index})`;
  }

  function siblingIndex(element) {
    if (!element.parentElement) {
      return 1;
    }
    const siblings = Array.from(element.parentElement.children).filter((child) => child.tagName === element.tagName);
    return siblings.indexOf(element) + 1;
  }

  function positionalXPath(element) {
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      parts.unshift(`${tagName(current)}[${siblingIndex(current)}]`);
      current = current.parentElement;
    }
    return `/${parts.join("/")}`;
  }

  function isStableToken(value) {
    const token = String(value || "");
    if (token.length < 2 || token.length > 80) {
      return false;
    }
    if (/^[a-f0-9]{8,}$/i.test(token)) {
      return false;
    }
    if (/\d{5,}/.test(token)) {
      return false;
    }
    return true;
  }

  function safeElementValue(element) {
    if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)) {
      return "";
    }
    const type = String(element.getAttribute("type") || "").toLowerCase();
    const name = String(element.getAttribute("name") || "").toLowerCase();
    const id = String(element.getAttribute("id") || "").toLowerCase();
    const sensitive = ["password", "token", "seed", "secret", "private", "mnemonic"];
    if (type === "password" || sensitive.some((marker) => name.includes(marker) || id.includes(marker))) {
      return "[MASKED]";
    }
    return String(element.value || "").slice(0, 500);
  }

  function safeAttributes(element) {
    const names = ["id", "class", "name", "type", "role", "aria-label", "data-testid", "data-cy", "placeholder"];
    const result = {};
    for (const name of names) {
      const value = element.getAttribute(name);
      if (value !== null) {
        result[name] = String(value).slice(0, 300);
      }
    }
    return result;
  }

  function unrollDocument() {
    const visited = new WeakSet();
    return `<!doctype html>\n${serializeNodeWithShadow(document.documentElement, visited)}`;
  }

  function serializeNodeWithShadow(sourceNode, visited) {
    if (!sourceNode || visited.has(sourceNode)) {
      return "";
    }
    if (sourceNode.nodeType !== Node.ELEMENT_NODE) {
      return serializePlainNode(sourceNode);
    }
    visited.add(sourceNode);
    const clone = sourceNode.cloneNode(false);
    const lightDomHtml = Array.from(sourceNode.childNodes || [])
      .map((child) => serializeNodeWithShadow(child, visited))
      .join("");
    const shadowHtml = sourceNode.shadowRoot ? serializeShadowRoot(sourceNode.shadowRoot, visited) : "";
    clone.innerHTML = `${lightDomHtml}${shadowHtml}`;
    return outerHtmlForNode(clone);
  }

  function serializeShadowRoot(shadowRoot, visited) {
    const shadowContent = Array.from(shadowRoot.childNodes || [])
      .map((child) => serializeNodeWithShadow(child, visited))
      .join("");
    return `<template data-gpm-shadow-root="open">${shadowContent}</template>`;
  }

  function serializePlainNode(sourceNode) {
    return outerHtmlForNode(sourceNode.cloneNode(true));
  }

  function outerHtmlForNode(node) {
    const container = document.createElement("div");
    container.appendChild(node);
    return container.innerHTML;
  }

  function collectNetworkSnapshot(state) {
    const resources = performance.getEntriesByType("resource").slice(-250).map((entry) => ({
      type: "resource",
      name: entry.name,
      initiatorType: entry.initiatorType,
      startTime: Math.round(entry.startTime),
      duration: Math.round(entry.duration)
    }));
    return [...resources, ...state.networkEvents.slice(-250)];
  }

  function patchFetch(state) {
    if (window.__gpmFetchPatched === true || typeof window.fetch !== "function") {
      return;
    }
    window.__gpmFetchPatched = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async function patchedFetch(input, init) {
      const method = init && init.method ? String(init.method).toUpperCase() : "GET";
      const url = typeof input === "string" ? input : input && input.url ? input.url : "";
      const startedAt = new Date().toISOString();
      try {
        const response = await originalFetch(input, init);
        state.networkEvents.push({ type: "fetch", method, url, status: response.status, startedAt, finishedAt: new Date().toISOString() });
        return response;
      } catch (error) {
        state.networkEvents.push({ type: "fetch", method, url, status: 0, error: String(error), startedAt, finishedAt: new Date().toISOString() });
        throw error;
      }
    };
  }

  function patchXhr(state) {
    if (window.__gpmXhrPatched === true) {
      return;
    }
    window.__gpmXhrPatched = true;
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function patchedOpen(method, url) {
      this.__gpmRecorder = { method: String(method || "GET").toUpperCase(), url: String(url || ""), startedAt: "" };
      return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function patchedSend() {
      if (this.__gpmRecorder) {
        this.__gpmRecorder.startedAt = new Date().toISOString();
        this.addEventListener("loadend", () => {
          state.networkEvents.push({
            type: "xhr",
            method: this.__gpmRecorder.method,
            url: this.__gpmRecorder.url,
            status: this.status,
            startedAt: this.__gpmRecorder.startedAt,
            finishedAt: new Date().toISOString()
          });
        });
      }
      return originalSend.apply(this, arguments);
    };
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function xpathLiteral(value) {
    if (!value.includes("'")) {
      return `'${value}'`;
    }
    if (!value.includes('"')) {
      return `"${value}"`;
    }
    return `concat('${value.replace(/'/g, "',\"'\",'")}')`;
  }
})();
