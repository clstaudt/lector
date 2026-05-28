
# Agentic Testing Guide

You have `deal` and `hypothesis` available. Use them when they make tests clearer or more thorough than handwritten assertions.

**`deal`** lets you attach preconditions (`@deal.pre`), postconditions (`@deal.post`, `@deal.ensure`), and class invariants (`@deal.inv`) as decorators. These are executable specs — they run at call time and during testing. `deal.cases(fn)` auto-generates a full test from a function's contracts and type hints.

**`hypothesis`** generates test inputs from strategies (`st.integers()`, `st.text()`, `st.lists(...)`, etc.) via `@given`. It also offers `RuleBasedStateMachine` for testing stateful objects across random method-call sequences. It shrinks failing cases to minimal reproductions.

They compose: `deal.cases` uses hypothesis under the hood. You can also use hypothesis directly with `@given` when you need custom strategies or stateful testing.

## Preferences

Favor **properties over examples**. Instead of five parametrized cases with hardcoded expected values, ask: what must always be true about the output? Sorted? Same length? Round-trips? Total preserved? A single property checked across hundreds of generated inputs is usually stronger and more readable than a table of examples.

Favor **contracts on the function over assertions in a test file**. A `@deal.ensure` lives next to the code it specifies, serves as documentation, runs in production if you want it to, and is automatically tested by `deal.cases`. A pytest assertion in a separate file does only one of those things.

Keep **preconditions weak** (reject only what genuinely can't be handled) and **postconditions focused** (check essential properties, don't reimplement the function).

When example-based tests are clearer — especially for edge cases, regression bugs, or exact numerical results — use them. This is a style preference, not a rule.

## Keep Definitions Clean

When a function accumulates more than two or three decorators, combine them into a named contract using `deal.chain`:

```python
valid_discount = deal.chain(
    deal.pre(lambda _: _.price >= 0),
    deal.pre(lambda _: 0 <= _.percent <= 100),
    deal.ensure(lambda _: 0 <= _.result <= _.price),
)

@valid_discount
def apply_discount(price: float, percent: float) -> float:
    ...
```

This keeps the function signature readable, gives the contract a name that communicates intent, and allows reuse across functions that share the same behavioral envelope. Prefer this over stacking five or six anonymous decorators on a definition.

## Modifying Contracts

You can write, strengthen, or weaken contracts. Just be explicit about why. The one thing to avoid: silently weakening a contract to make a failing implementation pass.
