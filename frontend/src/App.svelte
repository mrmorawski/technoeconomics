<script lang="ts">
  // The preset is chosen by the ?preset= query param (reflected for linkable state); it
  // defaults to the first preset. Step 3 turns this shell into the real form/solve/results UI.
  const preset = new URLSearchParams(location.search).get("preset") ?? "industrial_heat";
</script>

<nav class="container">
  <ul>
    <li><strong><a href="/">technoeconomics.app</a></strong></li>
  </ul>
  <ul>
    <li><a href="/app.html?preset=industrial_heat">Industrial heat</a></li>
    <li><a href="/about.html">About</a></li>
  </ul>
</nav>

<main class="container">
  <hgroup>
    <h1>Model</h1>
    <p>Preset: <code>{preset}</code></p>
  </hgroup>
  <p>
    The interactive form, solve console, and results arrive in the next step. The scaffold is
    live: this is a Svelte 5 island mounted from <code>app.html</code>, styled with Pico, and
    talking to the FastAPI backend over <code>/api</code>.
  </p>
</main>
