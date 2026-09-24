<script lang="ts">
  import { LANE_NAMES } from '../lib/copy';
  import type { Lane } from '../lib/types';

  let { lane, named = false, large = false }: { lane: Lane; named?: boolean; large?: boolean } = $props();
</script>

<span class="chip mono" class:large style:--lane="var(--lane-{lane})" title={LANE_NAMES[lane]}>
  <i></i>{lane}{#if named}<span class="name">{LANE_NAMES[lane]}</span>{/if}
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    line-height: 1;
    white-space: nowrap;
  }

  i {
    width: 8px;
    height: 8px;
    border-radius: 1.5px;
    background: var(--lane);
    flex: none;
  }

  .name {
    font-family: var(--font-sans);
    font-weight: 400;
    color: var(--ink-2);
    margin-left: 2px;
  }

  .large {
    font-size: 22px;
    gap: 10px;
    letter-spacing: -0.02em;
  }

  .large i {
    width: 16px;
    height: 16px;
    border-radius: 2px;
  }

  .large .name {
    font-size: 15px;
    letter-spacing: 0;
  }
</style>
