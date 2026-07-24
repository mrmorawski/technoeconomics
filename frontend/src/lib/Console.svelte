<script lang="ts">
  let { lines }: { lines: string[] } = $props();

  let el = $state<HTMLPreElement | null>(null);

  // Keep the newest line in view as progress streams in.
  $effect(() => {
    lines.length;
    if (el) el.scrollTop = el.scrollHeight;
  });
</script>

<pre class="console" bind:this={el}>{lines.join("\n")}</pre>
