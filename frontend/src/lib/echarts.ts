// ECharts, tree-shaken to only what the curated result charts use (a stacked-area line chart
// over a time axis with zoom). Chart.svelte imports this module *dynamically*, so ECharts lands
// in a lazy chunk kept out of the main app bundle. When a new plot type is added to the results
// catalog, register its chart type/component here (the one acceptable coupling to the backend
// catalog).

import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  DatasetComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  DatasetComponent,
  CanvasRenderer,
]);

let registered = false;

/** Register (once) a theme so chart text and axes follow Pico's colours, dark mode included. */
export function picoTheme(): string {
  if (registered) return "pico";
  const text = getComputedStyle(document.body).color;
  const line =
    getComputedStyle(document.documentElement)
      .getPropertyValue("--pico-muted-border-color")
      .trim() || "#888";
  const axis = {
    axisLine: { lineStyle: { color: line } },
    axisLabel: { color: text },
    splitLine: { lineStyle: { color: line, opacity: 0.4 } },
  };
  echarts.registerTheme("pico", {
    textStyle: { color: text },
    title: { textStyle: { color: text } },
    legend: { textStyle: { color: text } },
    timeAxis: axis,
    valueAxis: axis,
  });
  registered = true;
  return "pico";
}

export { echarts };
