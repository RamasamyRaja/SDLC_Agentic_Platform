import { Component, computed, input } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { RepositoryIndexStatus } from '../../../api/models/repository.model';

/**
 * Renders the repository's real onboarding / indexing state. Every figure comes from the backend; a progress bar is drawn
 * only when the backend reports both chunks_done and chunks_total for a running embedding phase.
 */
@Component({
  selector: 'app-index-health',
  imports: [KeyValuePipe],
  template: `
    @if (status(); as s) {
      <p class="ready" [class.ready--ok]="s.ready_for_retrieval">
        <strong>{{ s.ready_for_retrieval ? 'Ready for retrieval' : 'Not ready for retrieval' }}</strong>
        @if (s.stale) { <span class="chip chip--warn">stale index</span> }
        @if (s.indexing_interrupted || s.onboarding_interrupted) { <span class="chip chip--warn">interrupted</span> }
      </p>
      @for (r of s.reasons ?? []; track r) { <p class="reason">{{ r }}</p> }
      @if (s.onboarding_error) { <p class="error">Onboarding error: {{ s.onboarding_error }}</p> }
      @if (s.indexing_error) { <p class="error">Indexing error: {{ s.indexing_error }}</p> }
      @if (running()) {
        <p class="muted">Phase: <span class="mono">{{ s.phase }}</span></p>
        @if (hasCounters()) {
          <div class="progress"><span [style.width.%]="pct()"></span></div>
          <p class="muted">{{ s.chunks_done }} of {{ s.chunks_total }} chunks embedded in this run</p>
        }
      }
      <p class="muted">
        {{ s.indexed_chunks ?? 0 }} chunks indexed
        @if (s.documents_total !== undefined) { · {{ s.documents_total }} files tracked }
        @if (s.indexed_commit_sha) { · indexed at <span class="mono">{{ s.indexed_commit_sha.slice(0, 8) }}</span> }
        @if (s.commit_sha && s.indexed_commit_sha && s.commit_sha !== s.indexed_commit_sha) { · repository at <span class="mono">{{ s.commit_sha.slice(0, 8) }}</span> }
      </p>
      @if (s.documents_by_status) {
        <p class="muted">Files by analysis result:
          @for (e of s.documents_by_status | keyvalue; track e.key) { <span class="chip">{{ e.key }}: {{ e.value }}</span> }
        </p>
      }
      @if (s.documents_by_language) {
        <p class="muted">By language:
          @for (e of s.documents_by_language | keyvalue; track e.key) { <span class="chip">{{ e.key }}: {{ e.value }}</span> }
        </p>
      }
      @if (s.documents_pending_index) { <p class="muted">{{ s.documents_pending_index }} file(s) changed since last indexed.</p> }
    } @else { <p class="muted">Index state unavailable.</p> }
  `,
  styles: [`.chip{display:inline-block;margin:0 .25rem .25rem 0;padding:.05rem .5rem;border-radius:999px;border:1px solid currentColor;font-size:.8em}
    .chip--warn{color:#b45309}.error{color:#b91c1c}.reason{margin:.1rem 0}.ready--ok strong{color:#047857}.progress{height:7px;background:var(--color-bg-base);border-radius:99px;overflow:hidden}.progress span{display:block;height:100%;background:var(--color-accent)}.muted{color:var(--color-text-muted)}.mono{font-family:var(--font-family-mono)}`],
})
export class IndexHealthComponent {
  readonly status = input<RepositoryIndexStatus | null>(null);
  protected readonly running = computed(() => this.status()?.status === 'indexing' && !this.status()?.indexing_interrupted);
  protected readonly hasCounters = computed(() => {
    const s = this.status();
    return !!s && typeof s.chunks_total === 'number' && s.chunks_total > 0 && typeof s.chunks_done === 'number';
  });
  protected readonly pct = computed(() => {
    const s = this.status();
    return s && s.chunks_total ? Math.min(100, Math.round(((s.chunks_done ?? 0) / s.chunks_total) * 100)) : 0;
  });
}
