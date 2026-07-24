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
  //
  // `replaceMerge: ["series"]` is load-bearing, not a tuning knob. ECharts' default merge keeps
  // series the new option does not mention, and matches the rest positionally — so a re-solve
  // with a component disabled leaves its series on the chart, bound by position to a different
  // component's data. Replacing the series array drops the departed ones (the backend gives
  // each a stable `id`, so the survivors are matched by identity), while everything outside
  // `series` still merges, which is what keeps the chart from flickering on every solve.
  $effect(() => {
    chart?.setOption(option as Parameters<EChartsType["setOption"]>[0], {
      replaceMerge: ["series"],
    });
  });
</script>

<div class="result-plot" bind:this={el}></div>
