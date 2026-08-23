# STANDARDS.md — Code Quality Standards (GREEN benchmark)

> Loaded by tdd-green via persistent_facts. The agent must follow these standards
> in its FIRST PASS. There is no REFACTOR phase — ugly code that violates these
> standards is a GREEN failure.

## SOLID Principles

### S — Single Responsibility
- One class/function = one reason to change.
- Red flag: >7 public methods handling different concerns.

### O — Open/Closed
- Open for extension, closed for modification.
- Red flag: adding a new behavior requires editing an existing if-chain.

### L — Liskov Substitution
- Subclasses substitutable for base classes.
- Red flag: narrowed return types, strengthened preconditions.

### I — Interface Segregation
- No client forced to depend on methods it doesn't use.
- Red flag: fat interfaces with empty implementations.

### D — Dependency Inversion
- Depend on abstractions, not concretions.
- Red flag: direct instantiation of concrete classes in domain code.

## Design Principles

### DRY — Don't Repeat Yourself
- Duplicate code blocks ≥6 lines across files → extract.

### KISS — Keep It Simple
- Cyclomatic complexity ≤10 per function.
- Nesting depth ≤4.
- Parameters ≤5.

### YAGNI — You Aren't Gonna Need It
- No unused imports.
- No dead code.

### LoD — Law of Demeter
- Attribute chains ≤3 (a.b.c is ok, a.b.c.d is not).

### CoI — Composition Over Inheritance
- Inheritance depth ≤2.

## Antipatterns to Avoid (HQG Tier A)

| ID | Name | Threshold |
|----|------|-----------|
| AP01 | God Class | >500 LOC or >20 public methods |
| AP05 | Magic Numbers | Hardcoded literals without named constants |
| AP06 | Long Method | >100 lines |
| AP08 | Long Parameter List | >5 parameters |
| AP18 | Switch Statements | >5 case branches |
| AP20 | Deep Nesting | >5 levels |
| AP22 | Dead Code | Unreachable code |
| AP23 | Duplicate Code | Identical 6+ line blocks |

## GREEN-Specific Rules

- NO `except Exception` (use specific exception types).
- NO `# pragma: no mutate` without written justification.
- NO `ABC`/`Protocol`/metaclass unless the contract requires polymorphism.
- Named constants for magic numbers (THRESHOLD_DEFAULT, DEFAULT_TIMEOUT).
- Guard clauses over nested ifs.
- Functions should do ONE thing.
