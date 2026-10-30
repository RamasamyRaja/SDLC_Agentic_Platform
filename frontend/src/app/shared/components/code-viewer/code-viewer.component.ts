import { Component, input } from '@angular/core';

@Component({
  selector: 'app-code-viewer',
  templateUrl: './code-viewer.component.html',
  styleUrl: './code-viewer.component.scss',
})
export class CodeViewerComponent {
  readonly content = input('');
  readonly language = input('text');
  readonly path = input('');
  readonly isMock = input(false);
  readonly lineNumbers = input(true);
}
