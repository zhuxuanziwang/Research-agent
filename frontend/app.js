const healthBadge = document.getElementById("healthBadge");
const runBtn = document.getElementById("runBtn");
const ingestBtn = document.getElementById("ingestBtn");

const queryInput = document.getElementById("queryInput");
const dataPathInput = document.getElementById("dataPathInput");
const pdfDirInput = document.getElementById("pdfDirInput");
const ingestOutInput = document.getElementById("ingestOutInput");
const metadataCsvInput = document.getElementById("metadataCsvInput");

const answerBlock = document.getElementById("answerBlock");
const evidenceList = document.getElementById("evidenceList");
const riskList = document.getElementById("riskList");
const traceList = document.getElementById("traceList");
const ingestResult = document.getElementById("ingestResult");
const traceTemplate = document.getElementById("traceTemplate");
let activeRunId = "";
let pollTimer = null;

function setStatus(text) {
  healthBadge.textContent = text;
}

function formatTrace(entry) {
  const lines = [];
  const summary = entry.observation_summary || {};
  const topHits = summary.top_hits || [];
  const hitLabel = typeof summary.hit_count === "number" ? summary.hit_count : 0;
  lines.push(`Hits: ${hitLabel}`);
  if (topHits.length > 0) {
    const hitText = topHits
      .map(
        (hit) =>
          `[${hit.paper_id}] ${hit.title} (${hit.year}) · ${hit.section} · score=${hit.hybrid_score}`
      )
      .join("\n");
    lines.push(`Top Matches:\n${hitText}`);
  }
  const ambiguity = summary.ambiguity || {};
  if (Object.keys(ambiguity).length > 0) {
    lines.push(
      `Ambiguity: low_coverage=${Boolean(ambiguity.low_coverage)}, conflicting=${Boolean(ambiguity.conflicting_stances)}`
    );
  }
  const reflection = entry.reflection || {};
  lines.push(
    `Replan: ${Boolean(reflection.replan)} · new_steps=${reflection.new_steps_count || 0}`
  );
  if (reflection.reason) {
    lines.push(`Reason: ${reflection.reason}`);
  }
  return lines.join("\n\n");
}

function listRender(container, items, emptyText) {
  container.innerHTML = "";
  if (!items || items.length === 0) {
    const div = document.createElement("div");
    div.className = "list-item";
    div.textContent = emptyText;
    container.appendChild(div);
    return;
  }
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.textContent = item;
    container.appendChild(div);
  });
}

function resetRunButton() {
  runBtn.disabled = false;
  runBtn.textContent = "Run Workflow";
}

function renderTraceList(trace) {
  traceList.innerHTML = "";
  (trace || []).forEach((entry, idx) => {
    const node = traceTemplate.content.cloneNode(true);
    node.querySelector("h3").textContent = `Step ${idx + 1}: ${entry.sub_question || ""}`;
    node.querySelector(".pill").textContent = entry.tool || "unknown";
    node.querySelector("pre").textContent = formatTrace(entry);
    traceList.appendChild(node);
  });
}

function renderFinalResult(result, runId) {
  const header = `Run: ${runId} | Mode: ${result.mode || "unknown"} | Papers: ${result.paper_count ?? "?"} | Data: ${result.data_path || "?"}`;
  const answer = result.summary?.answer || "No summary returned.";
  answerBlock.textContent = `${header}\n\n${answer}`;
  listRender(evidenceList, result.summary?.evidence_points || [], "No evidence.");
  listRender(riskList, result.summary?.risks || [], "No risks.");
  renderTraceList(result.execution_trace || []);
}

function schedulePoll(runId) {
  pollTimer = setTimeout(() => {
    pollRun(runId);
  }, 1000);
}

async function pollRun(runId) {
  if (activeRunId !== runId) {
    return;
  }
  try {
    const response = await fetch(`/api/runs/${runId}`);
    const run = await response.json();
    if (!response.ok) {
      answerBlock.textContent = run.error || `Failed to fetch run status: ${runId}`;
      activeRunId = "";
      resetRunButton();
      return;
    }

    const progress = run.progress || {};
    const stepIndex = progress.step_index ?? 0;
    const totalSteps = progress.total_steps ?? 0;
    answerBlock.textContent = `Run: ${runId}\nStatus: ${run.status}\nStage: ${progress.stage || "unknown"}\nStep: ${stepIndex}/${totalSteps}\n${progress.message || ""}`;
    renderTraceList(run.execution_trace || []);

    if (run.status === "completed" && run.result) {
      renderFinalResult(run.result, runId);
      activeRunId = "";
      resetRunButton();
      return;
    }
    if (run.status === "failed") {
      answerBlock.textContent = `Run: ${runId}\nStatus: failed\n${run.error || "Unknown error."}`;
      activeRunId = "";
      resetRunButton();
      return;
    }
    schedulePoll(runId);
  } catch (err) {
    answerBlock.textContent = `Run status polling failed: ${err}`;
    activeRunId = "";
    resetRunButton();
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    setStatus(`Service OK (${data.mode || "unknown"}) · default data: ${data.default_data_path}`);
  } catch (err) {
    setStatus("Service unavailable");
  }
}

async function runAgent() {
  const query = queryInput.value.trim();
  if (!query) {
    answerBlock.textContent = "Please enter a query.";
    return;
  }
  runBtn.disabled = true;
  runBtn.textContent = "Running...";
  answerBlock.textContent = "Submitting run...";
  traceList.innerHTML = "";
  evidenceList.innerHTML = "";
  riskList.innerHTML = "";

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        data_path: dataPathInput.value.trim() || "data/real_papers.json",
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.run_id) {
      answerBlock.textContent = data.error || "Run failed.";
      resetRunButton();
      return;
    }
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    activeRunId = data.run_id;
    answerBlock.textContent = `Run submitted: ${data.run_id}\nWaiting for planner...`;
    schedulePoll(data.run_id);
  } catch (err) {
    answerBlock.textContent = `Run failed: ${err}`;
    resetRunButton();
  }
}

async function ingestPdfs() {
  const pdfDir = pdfDirInput.value.trim();
  if (!pdfDir) {
    ingestResult.textContent = "Please provide a PDF directory.";
    return;
  }
  ingestBtn.disabled = true;
  ingestBtn.textContent = "Building...";
  ingestResult.textContent = "Converting PDFs...";

  try {
    const response = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pdf_dir: pdfDir,
        output_path: ingestOutInput.value.trim() || "data/real_papers.json",
        metadata_csv: metadataCsvInput.value.trim(),
      }),
    });
    const data = await response.json();
    ingestResult.textContent = JSON.stringify(data, null, 2);
    if (response.ok) {
      dataPathInput.value = data.output || dataPathInput.value;
    }
  } catch (err) {
    ingestResult.textContent = `Ingest failed: ${err}`;
  } finally {
    ingestBtn.disabled = false;
    ingestBtn.textContent = "Build Real Dataset";
  }
}

runBtn.addEventListener("click", runAgent);
ingestBtn.addEventListener("click", ingestPdfs);
checkHealth();
