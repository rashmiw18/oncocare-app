/* ==========================================================================
   OncoCare AI — Report page logic
   ========================================================================== */

(function () {
  const startInput = document.getElementById("startDate");
  const endInput = document.getElementById("endDate");
  const form = document.getElementById("reportForm");
  const patientSelect = document.getElementById("patientSelect");
  const downloadBtn = document.getElementById("downloadReportBtn");

  function toISODate(d) { return d.toISOString().slice(0, 10); }

  function setRange(days) {
    const end = new Date();
    let start;
    if (days === "all") {
      start = new Date(2020, 0, 1);
    } else {
      start = new Date();
      start.setDate(start.getDate() - parseInt(days, 10));
    }
    startInput.value = toISODate(start);
    endInput.value = toISODate(end);
  }

  document.querySelectorAll(".report-range-chips .chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".report-range-chips .chip").forEach(c => c.classList.remove("chip-active"));
      chip.classList.add("chip-active");
      setRange(chip.dataset.range);
    });
  });

  // Default: last 30 days
  setRange(30);
  document.querySelector('.chip[data-range="30"]')?.classList.add("chip-active");

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const params = new URLSearchParams();
    if (startInput.value) params.set("start", startInput.value);
    if (endInput.value) params.set("end", endInput.value);
    if (patientSelect && patientSelect.value) params.set("patient_id", patientSelect.value);

    downloadBtn.disabled = true;
    const label = downloadBtn.querySelector("span");
    const originalText = label.textContent;
    label.textContent = "Preparing PDF…";

    window.location.href = "/report/download?" + params.toString();

    setTimeout(() => {
      downloadBtn.disabled = false;
      label.textContent = originalText;
    }, 1800);
  });
})();
