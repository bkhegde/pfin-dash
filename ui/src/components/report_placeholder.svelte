<script lang="ts">
  let {
    title,
    subtitle,
    description,
    primaryAction,
    dataPoints,
    notes = [],
  }: {
    title: string;
    subtitle: string;
    description: string;
    primaryAction: string;
    dataPoints: string[];
    notes?: string[];
  } = $props();
</script>

<section class="report-placeholder" aria-label={title}>
  <header class="report-placeholder__header">
    <div>
      <h2 class="report-placeholder__title">{title}</h2>
      <p class="report-placeholder__subtitle">{subtitle}</p>
    </div>

    <button class="mf-btn mf-btn-primary" type="button" disabled>
      {primaryAction}
    </button>
  </header>

  <div class="report-placeholder__body">
    <p class="report-placeholder__description">{description}</p>

    <div class="report-placeholder__panel">
      <h3 class="report-placeholder__panel-title">Planned report shape</h3>
      <ul class="report-placeholder__list">
        {#each dataPoints as dataPoint}
          <li>{dataPoint}</li>
        {/each}
      </ul>
    </div>

    {#if notes.length > 0}
      <div class="report-placeholder__panel report-placeholder__panel--muted">
        <h3 class="report-placeholder__panel-title">Notes</h3>
        <ul class="report-placeholder__list">
          {#each notes as note}
            <li>{note}</li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>
</section>