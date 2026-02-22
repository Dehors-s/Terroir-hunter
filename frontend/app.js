const statusText = document.getElementById("status-text");
const statusDot = document.getElementById("status-dot");
const ahpMap = document.getElementById("ahp-map");
const hybridMap = document.getElementById("hybrid-map");
const phenologyImg = document.getElementById("phenology-img");
const similarityTableBody = document.querySelector("#similarity-table tbody");

const outputUrls = {
  suitabilityMap: "/api/output/suitability_map.html",
  similarityMap: "/api/output/similar_regions_map.html",
  similarityCsv: "/api/output/similar_regions.csv",
  phenologyPng: "/api/output/phenology_matching_analysis.png",
};

function setStatus(type, message) {
  statusText.textContent = message;
  if (type === "running") {
    statusDot.style.background = "#f7d774";
    statusDot.style.boxShadow = "0 0 12px rgba(247, 215, 116, 0.8)";
  } else if (type === "error") {
    statusDot.style.background = "#ff6b6b";
    statusDot.style.boxShadow = "0 0 12px rgba(255, 107, 107, 0.8)";
  } else {
    statusDot.style.background = "#61d9ff";
    statusDot.style.boxShadow = "0 0 12px rgba(97, 217, 255, 0.8)";
  }
}

async function fetchStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) {
    throw new Error("无法获取状态");
  }
  return response.json();
}

function loadMap(iframe, url) {
  iframe.src = url + "?t=" + Date.now();
}

async function loadCsv() {
  const response = await fetch(outputUrls.similarityCsv);
  if (!response.ok) {
    return;
  }
  const text = await response.text();
  const rows = text.trim().split("\n").slice(1);
  similarityTableBody.innerHTML = "";
  rows.forEach((row) => {
    const cols = row.split(",");
    const tr = document.createElement("tr");
    cols.forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    });
    similarityTableBody.appendChild(tr);
  });
}

function loadPhenology() {
  phenologyImg.src = outputUrls.phenologyPng + "?t=" + Date.now();
}

async function refreshOutputs(status) {
  if (status.outputs.suitability_map) {
    loadMap(ahpMap, outputUrls.suitabilityMap);
  }
  if (status.outputs.similarity_map) {
    loadMap(hybridMap, outputUrls.similarityMap);
  }
  if (status.outputs.similarity_csv) {
    await loadCsv();
  }
  if (status.outputs.phenology_png) {
    loadPhenology();
  }
}

async function pollUntilComplete(taskKey) {
  setStatus("running", "任务执行中，请稍候...");
  let finished = false;
  while (!finished) {
    const status = await fetchStatus();
    const task = status.tasks[taskKey];
    if (task.status === "completed") {
      setStatus("idle", "任务完成，结果已更新。");
      await refreshOutputs(status);
      finished = true;
    } else if (task.status === "failed") {
      setStatus("error", task.error || "任务失败");
      finished = true;
    } else {
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }
}

async function runTask(endpoint, taskKey) {
  const response = await fetch(endpoint, { method: "POST" });
  if (response.status === 409) {
    setStatus("running", "任务正在运行中...");
    await pollUntilComplete(taskKey);
    return;
  }
  if (!response.ok) {
    setStatus("error", "启动任务失败");
    return;
  }
  await pollUntilComplete(taskKey);
}

async function refreshStatus() {
  try {
    const status = await fetchStatus();
    const anyRunning = Object.values(status.tasks).some((task) => task.status === "running");
    if (anyRunning) {
      setStatus("running", "任务执行中...");
    } else {
      setStatus("idle", "等待任务");
    }
    await refreshOutputs(status);
  } catch (err) {
    setStatus("error", "状态获取失败");
  }
}

document.getElementById("btn-run-ahp").addEventListener("click", () => {
  runTask("/api/run/ahp", "ahp");
});

document.getElementById("btn-run-hybrid").addEventListener("click", () => {
  runTask("/api/run/hybrid", "hybrid");
});

document.getElementById("btn-refresh").addEventListener("click", () => {
  refreshStatus();
});

document.getElementById("btn-open-dashboard").addEventListener("click", () => {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
});

refreshStatus();
