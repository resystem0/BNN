<script>
  import { showSoulOverlay, sessionId, enterVault } from '$lib/stores/session.js';

  let inputValue = '';
  let loading = false;
  let localError = '';

  async function handleSubmit() {
    if (!inputValue.trim() || loading) return;

    loading = true;
    localError = '';

    try {
      await enterVault(inputValue.trim());
      // enterVault closes the overlay on success by setting showSoulOverlay = false
      // and sets sessionId — if it failed it throws and we catch below
    } catch (err) {
      localError = err?.message ?? 'Failed to enter vault';
    } finally {
      // Only clear loading if overlay is still open (i.e. we didn't succeed)
      loading = false;
      if ($sessionId) {
        inputValue = '';
      }
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      showSoulOverlay.set(false);
    }
    if (e.key === 'Enter') {
      handleSubmit();
    }
  }

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) {
      showSoulOverlay.set(false);
    }
  }
</script>

{#if $showSoulOverlay}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="overlay-backdrop" on:click={handleBackdropClick}>
    <div class="overlay-card" role="dialog" aria-modal="true" aria-labelledby="vault-title">
      <div class="vault-header">
        <h2 class="vault-title" id="vault-title">ENTER THE VAULT</h2>
        <p class="vault-sub">Submit a query to begin axon-graph traversal</p>
      </div>

      <div class="vault-body">
        <div class="input-wrap">
          <!-- svelte-ignore a11y_autofocus -->
          <input
            type="text"
            class="soul-input"
            placeholder="your query or soul token..."
            bind:value={inputValue}
            on:keydown={handleKeydown}
            autofocus
            autocomplete="off"
            spellcheck="false"
            disabled={loading}
          />
        </div>

        {#if localError}
          <p class="inline-error" role="alert">{localError}</p>
        {/if}

        <button
          class="submit-btn"
          on:click={handleSubmit}
          disabled={!inputValue.trim() || loading}
        >
          {#if loading}
            <span class="spinner" aria-hidden="true"></span>
            ENTERING…
          {:else}
            ENTER GRAPH
          {/if}
        </button>
      </div>

      <button class="close-btn" on:click={() => showSoulOverlay.set(false)} aria-label="Close" disabled={loading}>
        ✕
      </button>
    </div>
  </div>
{/if}

<style>
  .overlay-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(6, 8, 16, 0.85);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade-in 0.2s ease;
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .overlay-card {
    position: relative;
    width: 420px;
    max-width: calc(100vw - 32px);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 2px;
    box-shadow:
      0 0 40px var(--accent-glow),
      0 24px 48px rgba(0, 0, 0, 0.6);
    padding: 32px;
    animation: slide-up 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  }

  @keyframes slide-up {
    from { transform: translateY(16px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .vault-header {
    margin-bottom: 24px;
  }

  .vault-title {
    font-family: var(--serif-dark);
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--gold);
    margin-bottom: 8px;
  }

  .vault-sub {
    font-family: var(--body-dark);
    font-size: 13px;
    font-style: italic;
    color: var(--text-dim);
    line-height: 1.5;
  }

  .vault-body {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .input-wrap {
    position: relative;
  }

  .soul-input {
    width: 100%;
    padding: 11px 14px;
    background: var(--void);
    border: 1px solid var(--border-strong);
    border-radius: 2px;
    color: var(--text);
    font-family: var(--mono-dark);
    font-size: 13px;
    font-weight: 400;
    letter-spacing: 0.04em;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }

  .soul-input:focus {
    border-color: var(--gold-dim);
    box-shadow: 0 0 12px rgba(232, 200, 122, 0.1);
  }

  .soul-input::placeholder {
    color: var(--text-dim);
    font-style: italic;
  }

  .soul-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .inline-error {
    font-family: var(--mono-dark);
    font-size: 11px;
    color: rgba(220, 100, 100, 0.9);
    letter-spacing: 0.03em;
    margin: 0;
    padding: 6px 10px;
    background: rgba(220, 80, 80, 0.08);
    border: 1px solid rgba(220, 80, 80, 0.25);
    border-radius: 2px;
  }

  .submit-btn {
    width: 100%;
    padding: 12px 20px;
    background: transparent;
    border: 1px solid var(--gold-dim);
    border-radius: 2px;
    color: var(--gold);
    font-family: var(--mono-dark);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.14em;
    cursor: pointer;
    transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .submit-btn:hover:not(:disabled) {
    background: rgba(232, 200, 122, 0.08);
    border-color: var(--gold);
    box-shadow: 0 0 16px rgba(232, 200, 122, 0.15);
  }

  .submit-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  /* Loading spinner */
  .spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 1.5px solid rgba(232, 200, 122, 0.3);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .close-btn {
    position: absolute;
    top: 12px;
    right: 14px;
    font-size: 14px;
    color: var(--text-dim);
    cursor: pointer;
    background: none;
    border: none;
    padding: 4px;
    line-height: 1;
    transition: color 0.2s ease;
  }

  .close-btn:hover:not(:disabled) {
    color: var(--text);
  }

  .close-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
</style>
