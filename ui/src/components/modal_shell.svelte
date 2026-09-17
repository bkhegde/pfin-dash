<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    open = $bindable(false),
    title,
    width = "640px",
    closeOnBackdrop = false,
    children,
    footer,
  } = $props<{
    open: boolean;
    title: string;
    width?: string;
    closeOnBackdrop?: boolean;
    children: Snippet;
    footer?: Snippet;
  }>();

  function close() {
    open = false;
  }

  function onOverlayClick(event: MouseEvent) {
    if (closeOnBackdrop && event.target === event.currentTarget) {
      close();
    }
  }

  function onWindowKeydown(event: KeyboardEvent) {
    if (open && event.key === "Escape") {
      close();
    }
  }
</script>

<svelte:window onkeydown={onWindowKeydown} />

{#if open}
  <div class="app-modal-overlay" role="presentation" onclick={onOverlayClick}>
    <div
      class="app-modal"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={`--mf-modal-width: ${width};`}
    >
      <header class="app-modal-header">
        <h2>{title}</h2>
        <button class="app-button" onclick={close}>Close</button>
      </header>

      <div class="app-modal-body">
        {@render children()}
      </div>

      {#if footer}
        <footer class="app-modal-footer">
          {@render footer()}
        </footer>
      {/if}
    </div>
  </div>
{/if}
