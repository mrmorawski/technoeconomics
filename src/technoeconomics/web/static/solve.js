// SSE client for a solve run. connectStream() is called by _solving.jinja (swapped in
// after the form POST). It opens the stream and dispatches each event:
//   log     -> append a line to the run console
//   numbers -> replace the headline numbers (a pre-rendered HTML fragment)
//   chart   -> create/update an ECharts chart in place, keyed by id
//   done    -> close the stream; failed -> show the error and close

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
    const es = new EventSource("/industrial_heat/stream_solve");

    es.addEventListener("log", (e) => {
        term.textContent += e.data + "\n";
        term.scrollTop = term.scrollHeight;
    });
    es.addEventListener("numbers", (e) => {
        document.getElementById("numbers").innerHTML = e.data;
    });
    es.addEventListener("chart", (e) => {
        const {id, option} = JSON.parse(e.data);
        const chart = (charts[id] ??= echarts.init(chartDiv(id), picoTheme()));
        chart.setOption(option);
    });
    es.addEventListener("done", () => es.close());
    es.addEventListener("failed", (e) => {
        term.textContent += "ERROR: " + e.data + "\n";
        es.close();
    });
    // A transport error (not a "failed" message): close so EventSource does not silently
    // reconnect, which would restart the solve.
    es.onerror = () => es.close();
}

window.addEventListener("resize", () => {
    Object.values(charts).forEach((c) => c.resize());
});
