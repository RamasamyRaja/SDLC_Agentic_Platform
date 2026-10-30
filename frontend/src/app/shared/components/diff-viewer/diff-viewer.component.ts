import { Component, computed, input } from '@angular/core';
import { parseDiff } from '../../../features/tasks/task-detail.helpers';

@Component({
  selector: 'app-diff-viewer',
  template: `
    @if (lines().length === 0) {
      <p class="muted">No diff — no files were changed.</p>
    } @else {
      <pre class="diff" tabindex="0" aria-label="Unified diff">@for (l of lines(); track $index) {<span class="l l--{{ l.kind }}">{{ l.text }}
</span>}</pre>
    }
  `,
  styles: [`
    .diff{margin:0;max-height:520px;overflow:auto;background:var(--color-bg-base);border:1px solid var(--color-border-default);border-radius:6px;font-family:var(--font-family-mono);font-size:12px;line-height:1.5}
    .l{display:block;padding:0 10px;white-space:pre}
    .l--add{background:rgba(46,160,67,.18)} .l--del{background:rgba(248,81,73,.18)}
    .l--hunk{color:var(--color-accent)} .l--file{font-weight:600}
    .muted{color:var(--color-text-muted);font-size:12px}
  `],
})
export class DiffViewerComponent {
  readonly diff = input<string | null | undefined>('');
  protected readonly lines = computed(() => parseDiff(this.diff()));
}
