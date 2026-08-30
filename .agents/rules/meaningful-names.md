---
trigger: file_edit
---

# Meaningful Variable Names

Use descriptive, intention-revealing names.

## Naming Conventions

### Booleans

Use `is`, `has`, `can`, `should` prefix:

```typescript
const isActive = true
const hasPermission = false
const canEdit = true
const shouldNotify = false
```

### Functions/Methods

Use verbs:

```typescript
getUserById(id)
calculateTotalPrice(items)
sendNotification(user)
validatePayment(payment)
```

### Collections

Use plural nouns:

```typescript
const users = []
const orderItems = []
const productCategories = []
```

## Anti-Patterns

```typescript
// Bad
const d = new Date()
const u = await getUser(id)
const temp = []
const data = []
const result = []

// Good
const createdAt = new Date()
const customer = await getUser(id)
const pendingOrders = []
const validatedInput = []
const processedProducts = []
```

## Exceptions

Single-letter variables OK in short loops: `for (let i = 0; ...)`
