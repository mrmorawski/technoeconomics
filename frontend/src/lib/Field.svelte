<script lang="ts">
  import type { FieldSpec } from "./api-types";

  let {
    field,
    value = $bindable(),
    disabled = false,
  }: { field: FieldSpec; value: number; disabled?: boolean } = $props();

  // HTML min/max give instant feedback; the server enforces the exact (inclusive/exclusive)
  // bound on POST, so these are advisory hints, not the authority.
  const min = $derived(field.min?.value);
  const max = $derived(field.max?.value);
</script>

<label>
  {field.label}{#if field.unit}&nbsp;<small class="unit">({field.unit})</small>{/if}
  <input
    type="number"
    bind:value
    {min}
    {max}
    step={field.step ?? "any"}
    {disabled}
  />
</label>

<style>
  .unit {
    color: var(--pico-muted-color);
  }
</style>
