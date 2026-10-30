import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-error-state',
  template: `
    <div class="error" role="alert">
      <p class="error__title">{{ title() }}</p>
      @if (message()) {
        <p class="error__message">{{ message() }}</p>
      }
      @if (retryLabel()) {
        <button type="button" class="error__retry" (click)="retryClicked.emit()">{{ retryLabel() }}</button>
      }
    </div>
  `,
  styleUrl: './error-state.component.scss',
})
export class ErrorStateComponent {
  readonly title = input('Something went wrong');
  readonly message = input<string>();
  readonly retryLabel = input('Retry');
  readonly retryClicked = output<void>();
}
