import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '@core/auth/auth.service';

@Component({
  selector: 'app-register-page',
  imports: [RouterLink],
  templateUrl: './register-page.component.html',
  styleUrl: './register-page.component.scss',
})
export class RegisterPageComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly fullName = signal('');
  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly confirmPassword = signal('');
  protected readonly showPassword = signal(false);
  protected readonly showConfirmPassword = signal(false);
  protected readonly isLoading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly passwordMismatch = computed(
    () => this.confirmPassword().length > 0 && this.password() !== this.confirmPassword(),
  );
  protected readonly passwordInputType = computed(() =>
    this.showPassword() ? 'text' : 'password',
  );
  protected readonly confirmPasswordInputType = computed(() =>
    this.showConfirmPassword() ? 'text' : 'password',
  );

  onInput(signalRef: typeof this.fullName, event: Event): void {
    signalRef.set((event.target as HTMLInputElement).value);
    this.errorMessage.set(null);
  }

  togglePasswordVisibility(): void {
    this.showPassword.update((visible) => !visible);
  }

  toggleConfirmPasswordVisibility(): void {
    this.showConfirmPassword.update((visible) => !visible);
  }

  async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    this.errorMessage.set(null);

    if (!this.fullName().trim() || !this.email().trim() || !this.password().trim()) {
      this.errorMessage.set('Please complete all required fields.');
      return;
    }

    if (this.password().length < 8) {
      this.errorMessage.set('Password must be at least 8 characters.');
      return;
    }

    if (this.password() !== this.confirmPassword()) {
      this.errorMessage.set('Passwords do not match.');
      return;
    }

    this.isLoading.set(true);

    try {
      const success = await this.authService.register(
        this.email(),
        this.password(),
        this.fullName(),
      );

      if (!success) {
        this.errorMessage.set(
          'Unable to create the account. The email may already be registered, or the backend is unavailable.',
        );
        return;
      }

      await this.router.navigate(['/app/dashboard']);
    } catch {
      this.errorMessage.set('Something went wrong. Please try again.');
    } finally {
      this.isLoading.set(false);
    }
  }
}
