"use strict";

const table = document.getElementById("results");
const body = table.tBodies[0];
const headers = Array.from(table.tHead.rows[0].cells);
const toggles = Array.from(document.querySelectorAll("button.toggle"));
const metric = document.getElementById("metric");
const rows = () => Array.from(body.rows);
let sorted = { index: null, descending: false };

function highlight() {
  for (const row of rows()) {
    const candidates = Array.from(row.cells).filter(cell => {
      cell.classList.remove("best");
      return cell.dataset.status === "successful" && !cell.hidden;
    });
    // The fully observable MDP is an over-approximation of the POMDP,
    // even when its own result is exact. Compare its value with discretisation.
    // Display choices affect sorting, but not which POMDP bound is best.
    for (const families of [["cutoff"], ["discretisation", "MDP"]]) {
      const group = candidates.filter(cell => families.includes(cell.dataset.family)
        && cell.dataset.quality !== "" && Number.isFinite(Number(cell.dataset.quality)));
      const under = families[0] === "cutoff";
      const maximise = (row.dataset.direction === "max") === under;
      const values = group.map(cell => Number(cell.dataset.quality));
      const best = maximise ? Math.max(...values) : Math.min(...values);
      const tightest = group.filter(cell => Number(cell.dataset.quality) === best);
      const timed = tightest.filter(cell => cell.dataset.runtime !== ""
        && Number.isFinite(Number(cell.dataset.runtime)));
      const fastest = Math.min(...timed.map(cell => Number(cell.dataset.runtime)));
      for (const cell of timed.length ? timed : tightest) {
        if (!timed.length || Number(cell.dataset.runtime) === fastest) cell.classList.add("best");
      }
    }
  }
}

function setColumn(button, visible) {
  button.classList.toggle("on", visible);
  button.setAttribute("aria-pressed", String(visible));
  for (const cell of table.querySelectorAll("[data-col]")) {
    if (cell.dataset.col === button.dataset.col) cell.hidden = !visible;
  }
}

function sortTable(index, descending) {
  const header = headers[index];
  const numeric = header.dataset.kind !== "text";
  const value = cell => {
    if (header.dataset.kind === "run") {
      if (cell.dataset.status !== "successful") return null;
      const raw = metric.value === "bound" ? cell.dataset.bound : cell.dataset.runtime;
      return raw !== "" && Number.isFinite(Number(raw)) ? Number(raw) : null;
    }
    if (!numeric) return cell.dataset.sort;
    const raw = cell.dataset.sort;
    return raw !== "" && Number.isFinite(Number(raw)) ? Number(raw) : null;
  };
  rows().sort((a, b) => {
    const x = value(a.cells[index]), y = value(b.cells[index]);
    // Failures and missing data stay after successful runs in both directions.
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    const comparison = numeric ? x - y : x.localeCompare(y);
    return descending ? -comparison : comparison;
  }).forEach(row => body.appendChild(row));
  for (const cell of headers) cell.removeAttribute("aria-sort");
  header.setAttribute("aria-sort", descending ? "descending" : "ascending");
  sorted = { index, descending };
}

headers.forEach((header, index) => header.querySelector("button").addEventListener("click", () => {
  sortTable(index, sorted.index === index ? !sorted.descending : false);
}));
for (const button of toggles) button.addEventListener("click", () => {
  setColumn(button, button.getAttribute("aria-pressed") !== "true");
  highlight();
});
for (const button of document.querySelectorAll("[data-all]")) button.addEventListener("click", () => {
  for (const toggle of toggles) setColumn(toggle, button.dataset.all === "true");
  highlight();
});
metric.addEventListener("change", () => {
  document.body.dataset.metric = metric.value;
  if (sorted.index !== null) sortTable(sorted.index, sorted.descending);
  highlight();
});
const filter = document.getElementById("filter");
function filterRows() {
  const query = filter.value.toLowerCase().trim();
  for (const row of rows()) row.hidden = !row.dataset.search.includes(query);
  document.getElementById("row-count").textContent = `${rows().filter(row => !row.hidden).length} / ${rows().length} benchmarks`;
}
filter.addEventListener("input", filterRows);
document.body.dataset.metric = metric.value;
filterRows();
highlight();
