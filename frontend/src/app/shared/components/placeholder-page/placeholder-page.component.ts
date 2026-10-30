import { Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

interface PlaceholderPageData {
  title: string;
  description: string;
}

@Component({
  selector: 'app-placeholder-page',
  templateUrl: './placeholder-page.component.html',
  styleUrl: './placeholder-page.component.scss',
})
export class PlaceholderPageComponent {
  private readonly route = inject(ActivatedRoute);

  protected readonly pageData = toSignal(
    this.route.data.pipe(
      map(
        (data): PlaceholderPageData => ({
          title: (data['title'] as string | undefined) ?? 'Page',
          description: (data['description'] as string | undefined) ?? '',
        }),
      ),
    ),
    { initialValue: { title: 'Page', description: '' } },
  );
}
