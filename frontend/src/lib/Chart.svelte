<script lang="ts">
  import { onMount } from "svelte";
  import type { EChartsType } from "echarts/core";

  // The option is an opaque ECharts config from the backend results catalog.
  let { option }: { option: unknown } = $props();

  let el: HTMLDivElement;
  let chart = $state<EChartsType | null>(null);

  onMount(() => {
    let disposed = false;
    const onResize = () => chart?.resize();
    // Dynamic import → ECharts is a lazy chunk, loaded only when a chart first renders.
    void (async () => {
      const mod = await import("./echarts");
      if (disposed) return;
      chart = mod.echarts.init(el, mod.picoTheme());
      window.addEventListener("resize", onResize);
    })();
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      chart?.dispose();
    };
  });

  // (Re)apply the option once the chart exists and whenever it changes; a re-solve updates the
  // same chart (keyed by id) in place rather than redrawing.
  $effect(() => {
    chart?.setOption(option as Parameters<EChartsType["setOption"]>[0]);
  });
</script>

<div class="result-plot" bind:this={el}></div>
