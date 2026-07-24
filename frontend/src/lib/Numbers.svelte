<script lang="ts">
  interface NumberItem {
    label: string;
    value: number;
    unit: string;
  }

  let { numbers }: { numbers: NumberItem[] } = $props();

  const format = (v: number) =>
    v.toLocaleString(undefined, { maximumFractionDigits: 0 });
</script>

<div class="numbers">
  {#each numbers as n (n.label)}
    <article>
      <small>{n.label}</small>
      <strong>{format(n.value)} {n.unit}</strong>
    </article>
  {/each}
</div>
