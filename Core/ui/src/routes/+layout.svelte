<script>
  import '../app.css';
  import { page } from '$app/stores';
</script>

<slot />

<!-- Global nav dots -->
<nav class="nav-dots" aria-label="Navigation">
  <a
    href="/"
    class="dot"
    class:active={$page.url.pathname === '/'}
    title="Game"
    aria-label="Game view"
    style="--dot-color: #4f7bff"
  ></a>
  <a
    href="/treasury"
    class="dot"
    class:active={$page.url.pathname === '/treasury'}
    title="Treasury"
    aria-label="Treasury dashboard"
    style="--dot-color: #1a7a6e"
  ></a>
  <a
    href="/intelligence"
    class="dot"
    class:active={$page.url.pathname === '/intelligence'}
    title="Intelligence"
    aria-label="Node intelligence"
    style="--dot-color: #e8c87a"
  ></a>
  <a
    href="/dossier"
    class="dot"
    class:active={$page.url.pathname === '/dossier'}
    title="Dossier"
    aria-label="Miner dossier"
    style="--dot-color: #9c6fe4"
  ></a>
</nav>

<style>
  .nav-dots {
    position: fixed;
    bottom: 20px;
    right: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 900;
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--dot-color);
    opacity: 0.3;
    transition: opacity 0.2s ease, transform 0.2s ease;
    display: block;
  }

  .dot:hover {
    opacity: 0.7;
    transform: scale(1.2);
  }

  .dot.active {
    opacity: 1;
    box-shadow: 0 0 8px var(--dot-color);
  }
</style>
