<script lang="ts">
  import { onMount } from "svelte";
  import {
    createShare,
    getPreset,
    getRun,
    listPresets,
    readShare,
    solve,
  } from "./lib/api";
  import {
    defaultEnabled,
    defaultValues,
    enabledDiff,
    overlayDiff,
  } from "./lib/paths";
  import {
    clientId,
    loadEdits,
    saveEdits,
    specHash,
    type StoredEdits,
  } from "./lib/store";
  import { streamRun } from "./lib/events";
  import Form from "./lib/Form.svelte";
  import Console from "./lib/Console.svelte";
  import Numbers from "./lib/Numbers.svelte";
  import Chart from "./lib/Chart.svelte";
  import type {
    Envelope,
    FieldError,
    PresetDetail,
    PresetSummary,
    RunResults,
  } from "./lib/api-types";

  // The opaque result payloads, cast at the render boundary (see backend results.py).
  interface NumberItem {
    label: string;
    value: number;
    unit: string;
  }
  interface ChartItem {
    id: string;
    option: unknown;
  }

  let presets = $state<PresetSummary[]>([]);
  let presetName = $state("");
  let detail = $state<PresetDetail | null>(null);
  // The working model: values keyed by spec path, enabled keyed by component id. `$state`
  // proxies, so <Form>'s bindings write straight back and the persistence effect tracks them.
  let values = $state<Record<string, number>>({});
  let enabled = $state<Record<string, boolean>>({});
  // Per-preset baselines (recomputed on load); the overlay is always the diff against these.
  let defaults = $state<Record<string, number>>({});
  let baseEnabled = $state<Record<string, boolean>>({});
  let hash = $state("");
  let error = $state<string | null>(null);
  let shareUrl = $state<string | null>(null);

  // Solve/run state.
  let running = $state(false);
  let consoleLines = $state<string[]>([]);
  let results = $state<RunResults | null>(null);
  let fieldErrors = $state<FieldError[]>([]);
  let solveMessage = $state<string | null>(null);
  let cancelStream: (() => void) | null = null;

  const numberItems = $derived((results?.numbers ?? []) as NumberItem[]);
  const chartItems = $derived((results?.charts ?? []) as ChartItem[]);

  function clearRun() {
    cancelStream?.();
    cancelStream = null;
    running = false;
    consoleLines = [];
    results = null;
    fieldErrors = [];
    solveMessage = null;
  }

  async function loadPreset(name: string, shared: StoredEdits | null = null) {
    detail = null;
    error = null;
    shareUrl = null;
    clearRun();
    try {
      const d = await getPreset(name);
      const defs = defaultValues(d.plant, d.form);
      const baseEn = defaultEnabled(d.form);
      const h = specHash(d.form);
      // A loaded share wins; otherwise restore localStorage edits if the spec still matches.
      const edits = shared ?? loadEdits(name, h) ?? { overlay: {}, enabled: {} };
      const nextValues = { ...defs };
      for (const [path, v] of Object.entries(edits.overlay)) {
        if (path in defs) nextValues[path] = v; // drop paths a schema bump removed
      }
      const nextEnabled = { ...baseEn };
      for (const [id, on] of Object.entries(edits.enabled)) {
        if (id in baseEn) nextEnabled[id] = on;
      }
      defaults = defs;
      baseEnabled = baseEn;
      hash = h;
      values = nextValues;
      enabled = nextEnabled;
      detail = d;
      void runSolve(); // auto-solve on load so a chart appears without the user clicking
    } catch {
      error = `Could not load preset "${name}".`;
    }
  }

  async function selectPreset(name: string) {
    presetName = name;
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("preset", name);
    history.replaceState(null, "", url);
    await loadPreset(name);
  }

  function reset() {
    values = { ...defaults };
    enabled = { ...baseEnabled };
    shareUrl = null;
    void runSolve(); // re-solve the defaults; charts update in place rather than vanishing
  }

  function envelope(): Envelope {
    return {
      preset: presetName,
      overlay: overlayDiff(values, defaults),
      enabled: enabledDiff(enabled, baseEnabled),
    };
  }

  async function runSolve() {
    fieldErrors = [];
    solveMessage = null;
    running = true; // disable controls at once; also closes the double-click window
    const outcome = await solve(envelope(), clientId());
    if (!outcome.ok) {
      running = false;
      if (outcome.kind === "invalid") fieldErrors = outcome.errors;
      else if (outcome.kind === "busy")
        solveMessage = `The server is busy${outcome.retryAfter ? ` — try again in ${outcome.retryAfter}s` : ""}.`;
      else solveMessage = outcome.message;
      return;
    }
    cancelStream?.();
    consoleLines = [];
    // Keep the current charts on screen while solving; when results arrive they update in
    // place (each chart is keyed by id), so a chart never blanks out between solves.
    const runId = outcome.runId;
    cancelStream = streamRun(runId, async (e) => {
      if (e.event === "progress") {
        consoleLines = [...consoleLines, e.data];
      } else if (e.event === "failed") {
        consoleLines = [...consoleLines, `Error: ${e.data}`];
        running = false;
      } else if (e.event === "cancelled") {
        // Another tab (same client) started a newer solve; this run was superseded.
        consoleLines = [...consoleLines, e.data];
        solveMessage = e.data;
        running = false;
      } else {
        consoleLines = [...consoleLines, "Done."];
        try {
          const snap = await getRun(runId);
          if (snap.results) results = snap.results; // update; never blank the charts
        } catch {
          solveMessage = "Could not fetch results.";
        }
        running = false;
      }
    });
  }

  async function share() {
    try {
      const token = await createShare(envelope());
      const url = new URL(location.href);
      url.search = "";
      url.searchParams.set("p", token);
      shareUrl = url.toString();
      if (navigator.clipboard) await navigator.clipboard.writeText(shareUrl).catch(() => {});
    } catch {
      error = "Could not create a share link.";
    }
  }

  // Persist the current edits (as diffs) whenever they change, tagged with the spec hash.
  $effect(() => {
    if (!detail) return;
    saveEdits(presetName, hash, {
      overlay: overlayDiff(values, defaults),
      enabled: enabledDiff(enabled, baseEnabled),
    });
  });

  onMount(async () => {
    try {
      presets = await listPresets();
    } catch {
      error = "Could not reach the server.";
      return;
    }
    const params = new URLSearchParams(location.search);
    const token = params.get("p");
    if (token) {
      try {
        const s = await readShare(token);
        presetName = s.preset;
        await loadPreset(s.preset, { overlay: s.overlay ?? {}, enabled: s.enabled ?? {} });
        return;
      } catch {
        error = "That share link is invalid or out of date — showing the preset defaults.";
      }
    }
    presetName = params.get("preset") ?? presets[0]?.name ?? "";
    if (presetName) await loadPreset(presetName);
  });
</script>

<nav class="container">
  <ul>
    <li><strong><a href="/">technoeconomics.app</a></strong></li>
  </ul>
  <ul>
    <li><a href="/app.html?preset=industrial_heat">Industrial heat</a></li>
    <li><a href="/about.html">About</a></li>
    <li>
      <a href="https://mrmorawski.github.io/technoeconomics/getting-started/">Docs</a>
    </li>
  </ul>
</nav>

<main class="container">
  {#if error}
    <article class="error">{error}</article>
  {/if}

  {#if presets.length}
    <label>
      Preset
      <select value={presetName} onchange={(e) => selectPreset(e.currentTarget.value)}>
        {#each presets as preset (preset.name)}
          <option value={preset.name}>{preset.title}</option>
        {/each}
      </select>
    </label>
  {/if}

  {#if detail}
    <hgroup>
      <h1>{detail.title}</h1>
      <p>{detail.description}</p>
    </hgroup>

    {#if detail.schematic_svg}
      <!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted preset-authored SVG -->
      <div class="schematic">{@html detail.schematic_svg}</div>
    {/if}

    <Form form={detail.form} {values} {enabled} />

    <div class="actions">
      <button onclick={runSolve} disabled={running} aria-busy={running}>
        {running ? "Solving…" : "Solve"}
      </button>
      <button class="secondary" onclick={reset} disabled={running}>Reset</button>
      <button class="secondary outline" onclick={share}>Share link</button>
    </div>

    {#if shareUrl}
      <label>
        Share URL
        <input type="text" readonly value={shareUrl} onfocus={(e) => e.currentTarget.select()} />
      </label>
    {/if}

    {#if solveMessage}
      <article class="notice">{solveMessage}</article>
    {/if}

    {#if fieldErrors.length}
      <article class="error">
        <strong>Please fix these before solving:</strong>
        <ul>
          {#each fieldErrors as fe (fe.path)}
            <li><code>{fe.path}</code> — {fe.message}</li>
          {/each}
        </ul>
      </article>
    {/if}

    {#if consoleLines.length}
      <Console lines={consoleLines} />
    {/if}

    {#if results}
      <Numbers numbers={numberItems} />
      <div class="charts">
        {#each chartItems as chart (chart.id)}
          <Chart option={chart.option} />
        {/each}
      </div>
    {/if}
  {:else if !error}
    <p aria-busy="true">Loading…</p>
  {/if}
</main>

<style>
  .schematic {
    margin: 1.5rem 0;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .actions button {
    width: auto;
  }
  .error {
    background: var(--pico-del-color, #d9534f);
    color: white;
  }
  .notice {
    background: var(--pico-mark-background-color);
  }
</style>
