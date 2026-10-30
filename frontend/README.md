# RadAiAgentFrontend

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 22.1.6.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.

## M7 backend integration

The frontend is configured to use the Milestone 7 FastAPI backend in development and production builds through the API abstraction layer.

- Frontend dev server: `http://localhost:4200`
- FastAPI backend: `http://localhost:8000`
- Angular proxy: `proxy.conf.json` forwards `/api` to the FastAPI server.
- Repository, onboarding, analysis, indexing, semantic search, tasks, task analysis, agent runs, tools, and task artifacts use the M7 API adapters.
- Reports, settings, and source-file content remain frontend/mock-backed where M7 does not expose corresponding endpoints.
- Execution history is locally persisted because M7 exposes execution lookup by known execution ID, but does not expose an execution-history list endpoint.

Run the backend first, then from this project directory run:

```bash
npm install
npm start
```

The current M7 backend uses a development user stand-in, so the frontend should be treated as a development integration until real authentication is added.

## RAD final integration

This frontend is configured for the FastAPI backend (`/api`). It uses real JWT authentication, the registration flow, real repository file retrieval, backend execution history, backend reports, and RBAC-aware controls.
