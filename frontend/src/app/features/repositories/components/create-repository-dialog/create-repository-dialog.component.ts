import { Component, ElementRef, inject, output, signal, viewChild } from '@angular/core';
import { RepositoryCreateRequest } from '../../../../api/models/repository.model';
import { RepositoryFacade } from '../../repository.facade';

@Component({
  selector: 'app-create-repository-dialog',
  templateUrl: './create-repository-dialog.component.html',
  styleUrl: './create-repository-dialog.component.scss',
})
export class CreateRepositoryDialogComponent {
  private readonly facade = inject(RepositoryFacade);

  readonly created = output<string>();

  protected readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  protected readonly name = signal('');
  protected readonly url = signal('');
  protected readonly branch = signal('main');
  protected readonly provider = signal('github');
  protected readonly formError = signal<string | null>(null);

  protected readonly isSubmitting = signal(false);

  open(): void {
    this.resetForm();
    this.dialogRef().nativeElement.showModal();
  }

  close(): void {
    this.dialogRef().nativeElement.close();
  }

  onNameInput(event: Event): void {
    this.name.set((event.target as HTMLInputElement).value);
    this.formError.set(null);
  }

  onUrlInput(event: Event): void {
    this.url.set((event.target as HTMLInputElement).value);
    this.formError.set(null);
  }

  onBranchInput(event: Event): void {
    this.branch.set((event.target as HTMLInputElement).value);
  }

  onProviderChange(event: Event): void {
    this.provider.set((event.target as HTMLSelectElement).value);
  }

  onBackdropClick(event: MouseEvent): void {
    if (event.target === this.dialogRef().nativeElement) {
      this.close();
    }
  }

  async onSubmit(event: Event): Promise<void> {
    event.preventDefault();

    const name = this.name().trim();
    const url = this.url().trim();

    if (!name) {
      this.formError.set('Repository name is required.');
      return;
    }
    if (!url) {
      this.formError.set('Repository URL is required.');
      return;
    }

    this.isSubmitting.set(true);
    this.formError.set(null);

    const req: RepositoryCreateRequest = {
      name,
      url,
      branch: this.branch().trim() || 'main',
      provider: this.provider(),
    };

    const repo = await this.facade.create(req);
    this.isSubmitting.set(false);

    if (repo) {
      this.close();
      this.created.emit(repo.id);
    } else {
      this.formError.set(this.facade.actionError() ?? 'Failed to create repository.');
    }
  }

  private resetForm(): void {
    this.name.set('');
    this.url.set('');
    this.branch.set('main');
    this.provider.set('github');
    this.formError.set(null);
    this.isSubmitting.set(false);
  }
}
