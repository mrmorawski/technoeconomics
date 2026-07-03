// SSE client for solve runs. connectStream() is called once when the page loads and the
// stream stays open across runs; each Solve POST pushes a fresh run onto it. Events:
//   start    -> a run began: clear the console (charts update in place, so keep them)
//   progress -> append a progress line to the run console
//   numbers  -> render the headline numbers from data
//   chart    -> create/update an ECharts chart in place, keyed by id
//   done     -> mark the run complete; failed -> show the error (the stream stays open)

// ECharts instances kept across reruns, so setOption updates in place (no redraw flicker).
const charts = {};
let themeRegistered = false;

// A theme so chart text/axes follow the page colours (else dark-on-dark).
function picoTheme() {
    if (themeRegistered) return "pico";
    const text = getComputedStyle(document.body).color;
    const line = getComputedStyle(document.documentElement)
        .getPropertyValue("--pico-muted-border-color").trim() || "#888";
    const axis = {
        axisLine: {lineStyle: {color: line}},
        axisLabel: {color: text},
        splitLine: {lineStyle: {color: line, opacity: 0.4}},
    };
    echarts.registerTheme("pico", {
        textStyle: {color: text},
        title: {textStyle: {color: text}},
        legend: {textStyle: {color: text}},
        timeAxis: axis,
        valueAxis: axis,
    });
    themeRegistered = true;
    return "pico";
}

// The <div> for a chart id, created under #charts on first sighting.
function chartDiv(id) {
    let el = document.getElementById("chart-" + id);
    if (!el) {
        el = document.createElement("div");
        el.id = "chart-" + id;
        el.className = "result-plot";
        document.getElementById("charts").appendChild(el);
    }
    return el;
}

function connectStream() {
    const term = document.getElementById("console");
    const es = new EventSource("/industrial_heat/events");

    es.addEventListener("start", () => {
        term.textContent = "";  // a new run: clear the console for fresh progress lines
    });
    es.addEventListener("progress", (e) => {
        term.textContent += e.data + "\n";
        term.scrollTop = term.scrollHeight;
    });
    es.addEventListener("numbers", (e) => {
        // {label, value, unit} per headline number, rendered client-side (like the charts).
        const html = JSON.parse(e.data).map((n) =>
            `<article><small>${n.label}</small>` +
            `<strong>${n.value.toLocaleString(undefined, {maximumFractionDigits: 0})} ${n.unit}</strong>` +
            `</article>`
        ).join("");
        document.getElementById("numbers").innerHTML = html;
    });
    es.addEventListener("chart", (e) => {
        const {id, option} = JSON.parse(e.data);
        const chart = (charts[id] ??= echarts.init(chartDiv(id), picoTheme()));
        chart.setOption(option);
        chart.resize();  // re-measure in case the div was mid-layout when it was init'd
    });
    es.addEventListener("done", () => {
        term.textContent += "Done.\n";
    });
    es.addEventListener("failed", (e) => {
        term.textContent += "Error: " + e.data + "\n";
    });
    // The stream stays open across runs; a dropped connection auto-reconnects harmlessly,
    // since a run is launched by the Solve POST, not by opening this stream.
}

// Empty the results area and dispose the chart instances. Called from the Reset button so a
// fresh solve starts from a clean slate: disposing drops each ECharts instance (and its
// entry in `charts`), so the next solve re-inits into a new div instead of an orphaned one.
function clearResults() {
    Object.values(charts).forEach((c) => c.dispose());
    Object.keys(charts).forEach((id) => delete charts[id]);
    document.getElementById("charts").innerHTML = "";
    document.getElementById("numbers").innerHTML = "";
    document.getElementById("console").textContent = "";
}

window.addEventListener("resize", () => {
    Object.values(charts).forEach((c) => c.resize());
});
