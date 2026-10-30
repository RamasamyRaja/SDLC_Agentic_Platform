import { Component, input } from '@angular/core';

@Component({
  selector: 'app-loading-skeleton',
  template: `
    <div class="skeleton" [attr.aria-label]="label()" role="status">
      @for (row of rows(); track $index) {
        <div class="skeleton__row" [style.width]="row"></div>
      }
    </div>
  `,
  styleUrl: './loading-skeleton.component.scss',
})
export class LoadingSkeletonComponent {
  readonly rows = input<string[]>(['100%', '80%', '90%', '60%']);
  readonly label = input('Loading');
}
