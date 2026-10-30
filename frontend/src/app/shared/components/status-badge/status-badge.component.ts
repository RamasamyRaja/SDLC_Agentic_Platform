import { Component, computed, input } from '@angular/core';
import { statusLabel, statusVariant, StatusKind } from '@shared/utils/format.utils';

@Component({
  selector: 'app-status-badge',
  template: `<span class="badge badge--{{ variant() }}">{{ label() }}</span>`,
  styleUrl: './status-badge.component.scss',
})
export class StatusBadgeComponent {
  readonly status = input.required<StatusKind>();
  protected readonly variant = computed(() => statusVariant(this.status()));
  protected readonly label = computed(() => statusLabel(this.status()));
}
