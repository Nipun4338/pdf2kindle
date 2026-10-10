// Progress polling for a running Conversion, and a friendlier file picker.
(() => {
  const progress = document.getElementById("progress");
  if (progress) {
    const poll = async () => {
      try {
        const res = await fetch(progress.dataset.statusUrl, { cache: "no-store" });
        const s = await res.json();
        document.getElementById("status").textContent = s.status;
        document.getElementById("count").textContent = `${s.done} / ${s.total || "?"} pages`;
        const bar = document.getElementById("bar");
        bar.max = s.total || 1;
        bar.value = s.done;
        if (s.status === "ready" || s.status === "failed") return location.reload();
      } catch (_) { /* server restarting; try again */ }
      setTimeout(poll, 1000);
    };
    poll();
  }

  const file = document.getElementById("file");
  if (file) {
    const label = document.getElementById("file-label");
    file.addEventListener("change", () => {
      label.textContent = file.files[0] ? file.files[0].name : "Choose a PDF or drop it here";
    });
  }

  const build = document.getElementById("build");
  if (build) {
    build.form.addEventListener("submit", (e) => {
      if (e.submitter === build) {
        setTimeout(() => { build.disabled = true; build.textContent = "Building…"; });
      }
    });
  }
})();
