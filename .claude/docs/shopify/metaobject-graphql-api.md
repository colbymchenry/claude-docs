---
updated: 2026-04-09
---

# Shopify Metaobject GraphQL API Patterns

Patterns for managing metaobject definitions and instances via the Admin GraphQL API (through MCP tools).

## Adding Fields to a Metaobject Definition

Use `metaobjectDefinitionUpdate` with `fieldDefinitions.create`:

```graphql
mutation {
  metaobjectDefinitionUpdate(
    id: "gid://shopify/MetaobjectDefinition/15351415073"
    definition: {
      fieldDefinitions: [
        {
          create: {
            key: "use_secondary_for_accent"
            name: "Use secondary for accent"
            description: "When enabled, PDP buttons use secondary color"
            type: "boolean"
          }
        }
      ]
    }
  ) {
    metaobjectDefinition { id }
    userErrors { field message }
  }
}
```

Field type strings: `"boolean"`, `"single_line_text_field"`, `"color"`, `"file_reference"`, `"metaobject_reference"`.

## Batch Updating Metaobject Instances

Use GraphQL aliases to update multiple metaobjects in one request:

```graphql
mutation {
  school1: metaobjectUpdate(
    id: "gid://shopify/Metaobject/177797103905"
    metaobject: { fields: [{ key: "use_secondary_for_accent", value: "true" }] }
  ) { metaobject { id displayName } userErrors { field message } }

  school2: metaobjectUpdate(
    id: "gid://shopify/Metaobject/177797071137"
    metaobject: { fields: [{ key: "use_secondary_for_accent", value: "true" }] }
  ) { metaobject { id displayName } userErrors { field message } }
}
```

**Boolean values are strings** — use `"true"` / `"false"`, not bare `true`/`false`.

## Querying Metaobjects

### Single field access
Use `field(key:)` for one field (NOT `fields(keys: [...])`— that argument doesn't exist):

```graphql
{ metaobjects(type: "school", first: 5) {
    nodes { id displayName field(key: "slug") { value } }
}}
```

### Search by display name
Use `display_name:` filter. Multi-word names need quoting or they get split:

```graphql
{ metaobjects(type: "school", first: 3, query: "display_name:\"Utah State\"") {
    nodes { id displayName }
}}
```

Without quotes, `display_name:Utah State` searches `display_name:Utah` AND default field `State`.

## Key Metaobject Definition IDs

| Type | Definition ID |
|------|--------------|
| School | `gid://shopify/MetaobjectDefinition/15351415073` |

## School Metaobject Stats

- **Total schools:** 162 (as of 2026-04-09)
- **`use_secondary_for_accent`:** Defaults to `false` for all schools. Set to `true` only for schools whose primary color is too dark for button/accent use.
- Pagination: `metaobjects_list` returns max 50 per page — need 4 pages to fetch all schools.

**Note:** Maine does not exist as a School metaobject yet.
