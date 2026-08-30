---
trigger: file_edit
---

# Guard Clauses First

Use guard clauses to handle edge cases early and reduce nesting.

## Pattern

```typescript
// Good - Guard clauses first
function processOrder(order: Order): void {
  if (order.isCancelled) {
    throw new OrderCancelledException()
  }

  if (!order.items.length) {
    throw new EmptyOrderException()
  }

  if (!order.customer.canAfford(order.total)) {
    throw new InsufficientFundsException()
  }

  // Main logic here (not nested)
  fulfillOrder(order)
}

// Bad - Deeply nested
function processOrder(order: Order): void {
  if (!order.isCancelled) {
    if (order.items.length) {
      if (order.customer.canAfford(order.total)) {
        fulfillOrder(order)
      }
    }
  }
}
```

## Benefits

- Reduces cognitive load
- Makes requirements explicit
- Easier to test edge cases
- Cleaner main logic path
