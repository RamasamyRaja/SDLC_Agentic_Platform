import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '@core/auth/auth.service';

@Component({
  selector: 'app-login-page',
  imports: [RouterLink],
  templateUrl: './login-page.component.html',
  styleUrl: './login-page.component.scss',
})
export class LoginPageComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly username = signal('');
  protected readonly password = signal('');
  protected readonly showPassword = signal(false);
  protected readonly isLoading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly usernameTouched = signal(false);

  protected readonly usernameError = computed(() => {
    if (!this.usernameTouched()) return null;
    return this.username().trim() ? null : 'Username is required.';
  });

  protected readonly passwordInputType = computed(() =>
    this.showPassword() ? 'text' : 'password',
  );

  onUsernameInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.username.set(value);
    this.errorMessage.set(null);
  }

  onUsernameBlur(): void {
    this.usernameTouched.set(true);
  }

  onPasswordInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.password.set(value);
    this.errorMessage.set(null);
  }

  togglePasswordVisibility(): void {
    this.showPassword.update((visible) => !visible);
  }

  async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    this.usernameTouched.set(true);

    if (!this.username().trim()) {
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    try {
      const success = await this.authService.login(this.username(), this.password());
      if (!success) {
        this.errorMessage.set('Unable to sign in. Check your credentials and try again.');
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
