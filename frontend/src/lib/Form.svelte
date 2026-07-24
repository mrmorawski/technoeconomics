<script lang="ts">
  import type { ComponentSpec } from "./api-types";
  import Field from "./Field.svelte";

  // `values` and `enabled` are reactive `$state` proxies owned by the parent; binding to their
  // members here writes back through the same proxy, so the parent stays the single source.
  let {
    form,
    values,
    enabled,
  }: {
    form: ComponentSpec[];
    values: Record<string, number>;
    enabled: Record<string, boolean>;
  } = $props();
</script>

{#each form as component (component.id)}
  {@const inline = component.params.filter((p) => !p.advanced)}
  {@const advanced = component.params.filter((p) => p.advanced)}
  <fieldset>
    <legend>
      {#if component.color}
        <span class="dot" style="background:{component.color}"></span>
      {/if}
      {component.title}
      {#if !component.fixed}
        <input
          type="checkbox"
          role="switch"
          aria-label="Enable {component.title}"
          bind:checked={enabled[component.id]}
        />
      {/if}
    </legend>

    {#each inline as field (field.path)}
      <Field {field} bind:value={values[field.path]} disabled={!enabled[component.id]} />
    {/each}

    {#if advanced.length}
      <details>
        <summary>Advanced</summary>
        {#each advanced as field (field.path)}
          <Field {field} bind:value={values[field.path]} disabled={!enabled[component.id]} />
        {/each}
      </details>
    {/if}
  </fieldset>
{/each}

<style>
  legend {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: bold;
  }
  .dot {
    display: inline-block;
    width: 0.7em;
    height: 0.7em;
    border-radius: 50%;
  }
  legend input[type="checkbox"] {
    margin-left: auto;
    margin-bottom: 0;
  }
</style>
