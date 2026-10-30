import { Component, input } from '@angular/core';

@Component({
  selector: 'app-section-header',
  template: `
    <div class="section-header">
      <h2 class="section-header__title">{{ title() }}</h2>
      @if (subtitle()) {
        <p class="section-header__subtitle text-muted">{{ subtitle() }}</p>
      }
      <ng-content select="[actions]" />
    </div>
  `,
  styleUrl: './section-header.component.scss',
})
export class SectionHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>();
}
