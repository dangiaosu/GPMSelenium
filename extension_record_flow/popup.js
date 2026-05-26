const SERVER_DUMP_URL = "http://localhost:9999/dump";

const taskNameInput = document.getElementById("taskName");
const taskDescriptionInput = document.getElementById("taskDescription");
const requiredColumnsInput = document.getElementById("requiredColumns");
const checkpointNoteInput = document.getElementById("checkpointNote");
const statusBox = document.getElementById("status");

document.getElementById("startButton").addEventListener("click", () => runPopupAction(startRecording));
document.getElementById("stopButton").addEventListener("click", () => runPopupAction(stopRecording));
document.getElementById("addNoteButton").addEventListener("click", () => runPopupAction(addCheckpoint));
document.getElementById("dumpButton").addEventListener("click", () => runPopupAction(dumpAndSend));

async function runPopupAction(action) {
  try {
    await action();
  } catch (error) {
    setStatus(`Error: ${error && error.message ? error.message : String(error)}`);
  }
}

async function startRecording() {
  const response = await chrome.runtime.sendMessage({ type: "start_recording" });
  assertOk(response);
  setStatus(`Recording started. Steps reset: ${response.stepCount}`);
}

async function stopRecording() {
  const response = await chrome.runtime.sendMessage({ type: "stop_recording" });
  assertOk(response);
  setStatus(`Recording stopped. Steps: ${response.stepCount}`);
}

async function addCheckpoint() {
  const text = checkpointNoteInput.value.trim();
  if (!text) {
    throw new Error("Checkpoint note is empty.");
  }
  const response = await chrome.runtime.sendMessage({ type: "add_annotation", text });
  assertOk(response);
  checkpointNoteInput.value = "";
  setStatus(`Checkpoint added. Steps: ${response.stepCount}`);
}

async function dumpAndSend() {
  const response = await chrome.runtime.sendMessage({ type: "dump_recording" });
  assertOk(response);
  const payload = {
    metadata: buildMetadata(response),
    recordedSteps: response.recordedSteps || [],
    unrolledDOM: response.unrolledDOM || "",
    networkSnapshot: response.networkSnapshot || []
  };
  const serverResponse = await fetch(SERVER_DUMP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const serverBody = await serverResponse.json().catch(() => ({}));
  if (!serverResponse.ok || serverBody.ok !== true) {
    throw new Error(serverBody.error || `Dump server failed with status ${serverResponse.status}.`);
  }
  setStatus(`Saved: ${serverBody.path}`);
}

function buildMetadata(response) {
  return {
    taskName: safeTaskName(taskNameInput.value),
    taskDescription: taskDescriptionInput.value.trim(),
    requiredColumns: parseRequiredColumns(requiredColumnsInput.value),
    sourceUrl: response.currentUrl || "",
    dumpedAt: new Date().toISOString(),
    recorderVersion: "1.0.0",
    scoutMode: "chrome_extension_recorder_fallback"
  };
}

function parseRequiredColumns(rawValue) {
  return rawValue
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function safeTaskName(rawValue) {
  const cleaned = rawValue.trim().replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
  return cleaned || "recorded_task";
}

function assertOk(response) {
  if (!response || response.ok !== true) {
    throw new Error(response && response.error ? response.error : "Recorder command failed.");
  }
}

function setStatus(message) {
  statusBox.textContent = message;
}
