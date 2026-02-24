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

function setStatus(text) {
  healthBadge.textContent = text;
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

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    setStatus(`Service OK · default data: ${data.default_data_path}`);
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
  answerBlock.textContent = "Executing multi-step workflow...";
  traceList.innerHTML = "";

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        data_path: dataPathInput.value.trim() || "data/mock_papers.json",
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      answerBlock.textContent = data.error || "Run failed.";
      return;
    }

    answerBlock.textContent = data.summary?.answer || "No summary returned.";
    listRender(evidenceList, data.summary?.evidence_points || [], "No evidence.");
    listRender(riskList, data.summary?.risks || [], "No risks.");

    (data.execution_trace || []).forEach((entry, idx) => {
      const node = traceTemplate.content.cloneNode(true);
      node.querySelector("h3").textContent = `Step ${idx + 1}: ${entry.step?.sub_question || ""}`;
      node.querySelector(".pill").textContent = entry.step?.tool || "unknown";
      node.querySelector("pre").textContent = JSON.stringify(
        {
          observation: entry.observation,
          reflection: entry.reflection,
        },
        null,
        2
      );
      traceList.appendChild(node);
    });
  } catch (err) {
    answerBlock.textContent = `Run failed: ${err}`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run Workflow";
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

