<script lang="ts">
  import type { FieldSpec } from "./api-types";

  let {
    field,
    value = $bindable(),
    disabled = false,
    error = null,
  }: {
    field: FieldSpec;
    value: number;
    disabled?: boolean;
    error?: string | null;
  } = $props();

  // HTML min/max give the browser's spinner sensible limits, but cannot express a strict
  // bound — `validate.ts` applies the exclusivity, and the server is the authority on both.
  const min = $derived(field.min?.value);
  const max = $derived(field.max?.value);
</script>

<label>
  {field.label}{#if field.unit}&nbsp;<small class="unit">({field.unit})</small>{/if}
  {#if field.kind === "series"}
    <!-- A timeseries is surfaced so it is visible in the form, but is not editable yet. -->
    <input type="text" value="time series" readonly disabled />
  {:else}
    <input
      type="number"
      bind:value
      {min}
      {max}
      step={field.step ?? "any"}
      {disabled}
      aria-invalid={error ? "true" : undefined}
      aria-errormessage={error ? `${field.path}-error` : undefined}
    />
    {#if error}
      <small class="field-error" id="{field.path}-error">{error}</small>
    {/if}
  {/if}
</label>

<style>
  .unit {
    color: var(--pico-muted-color);
  }
  .field-error {
    color: var(--pico-del-color, #d9534f);
  }
</style>
