---
updated: 2026-04-10
---

# Superforms + Zod v4 Form Validation

## Setup

**Packages**: `sveltekit-superforms` ^2.30.0, `zod` ^4.3.6

**Vite alias** (`vite.config.js`): The zod4 adapter is aliased to avoid pulling in unnecessary adapter dependencies (valibot, arktype) that break the build:
```javascript
'superforms-zod4-adapter': resolve(__dirname, 'node_modules/sveltekit-superforms/dist/adapters/zod4.js')
```

**Re-export** (`src/lib/superforms.ts`): All components import from here, not directly from sveltekit-superforms:
```typescript
export { superForm, defaults } from 'sveltekit-superforms';
export { zod, zodClient } from 'superforms-zod4-adapter';
```

## Schemas

All validation schemas live in `src/lib/schemas/`:

| File | Schema | Used By |
|------|--------|---------|
| `agent.ts` | `agentSchema` | AgentEditSheet |
| `connector.ts` | `connectorFormSchema` | ConnectorEditModal |
| `dev-server.ts` | `devServerSchema` | DevServerSetupModal |
| `mcp-server.ts` | `mcpServerSchema` | McpServerEditModal |
| `project-location.ts` | `projectLocationSchema` | Project creation |

## Standard Form Pattern

Every form component follows this exact pattern (SPA mode, no server-side form actions):

```typescript
import { superForm, defaults, zod, zodClient } from '$lib/superforms';
import { mySchema } from '$lib/schemas/my-schema';

const { form, errors, enhance, reset } = superForm(
  defaults({ /* default values */ }, zod(mySchema)),
  {
    SPA: true,
    validators: zodClient(mySchema),
    onUpdate({ form: f }) {
      if (f.valid) {
        saveData(f.data);
      }
    }
  }
);
```

**Key options**:
- `SPA: true` — always used; no SvelteKit form actions in this project
- `validators: zodClient(schema)` — real-time client-side validation as user types
- `onUpdate` — fires on submit; check `f.valid` before saving

**Template binding**:
```svelte
<form use:enhance>
  <Input bind:value={$form.fieldName} />
  {#if $errors.fieldName}
    <span class="text-destructive text-sm">{$errors.fieldName}</span>
  {/if}
</form>
```

## UI Components

There are formsnap-based wrappers in `src/lib/components/ui/form/` (`form-field.svelte`, `form-field-errors.svelte`, etc.), but the existing modal/sheet forms do NOT use them. They use direct `Input`/`Label`/`Textarea` components from the shadcn-svelte UI library instead.

## Settings Page

The settings page (`src/routes/(protected)/settings/+page.svelte`) currently does NOT use Superforms — it uses manual fetch/state management with no schema validation. New settings forms should adopt the Superforms pattern above for consistency.