---
trigger: file_create
globs: ['**/tests/**', '**/test/**', '**/*.test.*', '**/*.spec.*']
---

# Test What Matters

Write tests for behavior, not implementation details.

## Test Focus Areas

1.  **Happy paths** - Normal successful operations
2.  **Error cases** - Expected failures
3.  **Edge cases** - Boundary conditions
4.  **Business rules** - Domain logic

## Good Test Names

```typescript
it('creates order when payment succeeds')
it('rejects order when inventory insufficient')
it('calculates discount for loyal customers')
it('sends notification after order completion')
```

## Test Structure (AAA)

```typescript
it('creates product with valid data', () => {
  // Arrange
  const productData = makeProduct()

  // Act
  const result = productService.create(productData)

  // Assert
  expect(result).toBeInstanceOf(Product)
  expect(result.name).toBe(productData.name)
})
```

## Avoid Testing

- Trivial getters/setters
- Framework internals
- Third-party library behavior
- Implementation details that may change

## Mock Judiciously

Mock external services, not internal collaborators.
