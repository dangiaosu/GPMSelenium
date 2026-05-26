const CONTENT_SCRIPT_FILE = "content.js";

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length || tabs[0].id === undefined) {
    throw new Error("No active tab is available.");
  }
  return tabs[0];
}

async function ensureRecorderInjected(tabId) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, { type: "ping" });
    if (response && response.ok === true) {
      return;
    }
  } catch (_error) {
    // The content script is not injected yet.
  }
  await chrome.scripting.executeScript({
    target: { tabId },
    files: [CONTENT_SCRIPT_FILE]
  });
}

async function sendToActiveRecorder(message) {
  const tab = await activeTab();
  await ensureRecorderInjected(tab.id);
  return await chrome.tabs.sendMessage(tab.id, message);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message.type !== "string") {
    sendResponse({ ok: false, error: "Invalid message." });
    return false;
  }

  if (!["start_recording", "stop_recording", "add_annotation", "dump_recording"].includes(message.type)) {
    sendResponse({ ok: false, error: `Unsupported message type: ${message.type}` });
    return false;
  }

  sendToActiveRecorder(message)
    .then((response) => sendResponse(response))
    .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
  return true;
});
