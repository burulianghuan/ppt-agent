let jobId = null;
let pollTimer = null;
let slides = [];
let pageIndex = 0;

const $ = (id) => document.getElementById(id);

function setStatus(s) {
  $("st-status").textContent = s.status || "—";
  $("st-progress").textContent = s.progress || "—";
  $("st-job").textContent = s.id || jobId || "—";
  if (s.error) {
    $("st-error").hidden = false;
    $("st-error").textContent = s.error;
  } else {
    $("st-error").hidden = true;
  }
}

function showOutline(outline) {
  $("outline-box").hidden = false;
  $("outline-json").value = JSON.stringify(outline || {}, null, 2);
}

function hideOutline() {
  $("outline-box").hidden = true;
}

function renderSlides(list) {
  slides = list || [];
  const thumbs = $("thumbs");
  thumbs.innerHTML = "";
  if (!slides.length) {
    $("prev").disabled = true;
    $("next").disabled = true;
    $("download-row").hidden = true;
    return;
  }
  $("download-row").hidden = false;
  $("btn-download").href = `/api/jobs/${jobId}/download.zip`;
  $("pptx-hint").hidden = false;

  slides.forEach((s, i) => {
    const div = document.createElement("div");
    div.className = "thumb" + (i === pageIndex ? " active" : "");
    div.innerHTML = `
      <img alt="" src="/api/jobs/${jobId}/pages/${i}.svg" />
      <div class="cap">${i + 1}. ${escapeHtml(s.page_title || s.page_key || "")}</div>
    `;
    div.onclick = () => {
      pageIndex = i;
      showPage();
    };
    thumbs.appendChild(div);
  });
  showPage();
}

function showPage() {
  if (!slides.length) return;
  pageIndex = Math.max(0, Math.min(pageIndex, slides.length - 1));
  $("page-label").textContent = `${pageIndex + 1} / ${slides.length} · ${slides[pageIndex].page_title || ""}`;
  $("prev").disabled = pageIndex <= 0;
  $("next").disabled = pageIndex >= slides.length - 1;
  $("preview").innerHTML = `<object data="/api/jobs/${jobId}/pages/${pageIndex}.svg" type="image/svg+xml"></object>`;
  [...$("thumbs").children].forEach((el, i) => {
    el.classList.toggle("active", i === pageIndex);
  });
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function poll() {
  if (!jobId) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const data = await res.json();
    setStatus(data);

    if (data.status === "waiting_outline_confirm") {
      showOutline(data.outline);
    }

    if (data.slides && data.slides.length) {
      // 设计进行中也可能逐步有页；当前实现是结束才写 slides
      if (!slides.length || slides.length !== data.slides.length) {
        pageIndex = 0;
      }
      renderSlides(data.slides);
    }

    if (data.status === "done" || data.status === "error") {
      clearInterval(pollTimer);
      pollTimer = null;
      $("btn-start").disabled = false;
      if (data.status === "done") hideOutline();
    }
  } catch (e) {
    console.error(e);
  }
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    topic: fd.get("topic"),
    audience: fd.get("audience"),
    purpose: fd.get("purpose"),
    pages: fd.get("pages"),
    style: fd.get("style"),
    extra: fd.get("extra") || "",
    auto_confirm_outline: fd.get("auto_confirm_outline") === "on",
  };

  $("btn-start").disabled = true;
  hideOutline();
  slides = [];
  $("thumbs").innerHTML = "";
  $("preview").innerHTML = `<div class="empty"><h2>生成中…</h2><p>调研与大纲通常需要几十秒，设计阶段更久。</p></div>`;
  $("download-row").hidden = true;

  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    setStatus({ status: "error", progress: "创建失败", error: data.detail || JSON.stringify(data), id: "—" });
    $("btn-start").disabled = false;
    return;
  }
  jobId = data.id;
  setStatus(data);
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 1500);
  poll();
});

$("btn-confirm").onclick = async () => {
  let outline;
  try {
    outline = JSON.parse($("outline-json").value);
  } catch {
    alert("大纲 JSON 格式不正确");
    return;
  }
  $("btn-confirm").disabled = true;
  const res = await fetch(`/api/jobs/${jobId}/confirm-outline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "edit", outline }),
  });
  const data = await res.json();
  $("btn-confirm").disabled = false;
  if (!res.ok) {
    alert(data.detail || "确认失败");
    return;
  }
  setStatus(data);
  hideOutline();
  if (!pollTimer) pollTimer = setInterval(poll, 1500);
};

$("btn-cancel").onclick = async () => {
  await fetch(`/api/jobs/${jobId}/confirm-outline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "cancel" }),
  });
  hideOutline();
};

$("prev").onclick = () => {
  pageIndex -= 1;
  showPage();
};
$("next").onclick = () => {
  pageIndex += 1;
  showPage();
};

$("btn-pptx").onclick = async () => {
  const btn = $("btn-pptx");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "生成中…（逐页渲染，请稍候）";
  try {
    const res = await fetch(`/api/jobs/${jobId}/download.pptx`);
    if (!res.ok) {
      let msg = "PPTX 生成失败";
      try {
        const j = await res.json();
        msg = j.detail || msg;
      } catch {}
      alert(msg);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ppt-${jobId}.pptx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("PPTX 下载出错：" + e);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
};
