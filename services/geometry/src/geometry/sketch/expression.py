"""Safe arithmetic evaluation of sketch **dimension expressions**.

A dimension's value may be a literal or a math EXPRESSION over other
dimensions' names (``height="width/2"``). This module is the real mini-parser
plus evaluator that resolves those expressions — a hand-written
recursive-descent parser, **not** :func:`eval` (no attribute access, no calls,
no names beyond the dimension namespace; the grammar below is the whole
language, so a malformed or hostile string can only ever be a clean error).

Grammar (EBNF)::

    expr    := term   (('+' | '-') term)*
    term    := factor (('*' | '/') factor)*
    factor  := ('+' | '-') factor | primary
    primary := NUMBER | IDENT | '(' expr ')'

    NUMBER  := digits ['.' digits] | '.' digits   (decimal, non-negative; a
               leading '-' is the unary-minus OPERATOR, not part of the number)
    IDENT   := [A-Za-z_][A-Za-z0-9_]*

Standard precedence (``*`` / ``/`` bind tighter than ``+`` / ``-``), unary
``+`` / ``-``, and parentheses. Identifiers resolve to other DRIVING
dimensions' values; the resolver builds the dependency graph implicitly and
detects cycles.

Every failure is a :class:`SketchExpressionError` — a subclass of
:class:`~geometry.sketch.solver.SketchDefinitionError`, so the feature
evaluator maps it to the ``sketch_invalid`` per-feature error (never a 500):
syntax errors, unknown or driven references, reference cycles, and division by
zero.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from py_kit.schemas.sketch import (
    AngleConstraint,
    DiameterConstraint,
    DimensionConstraint,
    DistanceConstraint,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchEntity,
    SketchLine,
)

from geometry.sketch.angles import AngleFrame, measured_angle_deg
from geometry.sketch.solver import SketchDefinitionError

#: Resolves a referenced dimension name to its evaluated value, in that
#: dimension's own unit (mm for a length, degrees for an angle).
Resolver = Callable[[str], float]

#: Maximum nesting/recursion depth the parser and evaluator will descend before
#: failing with a clean :class:`SketchExpressionError` instead of running into
#: Python's ``RecursionError`` (an uncaught crash → 500). Depth here counts
#: grammar nesting: one level per parenthesis, per unary operator, and per
#: left-deep binary chain step. The request-boundary ``max_length=256`` cap on
#: ``DimensionConstraint.expression`` already bounds any real input's depth well
#: below this (a 256-char string reaches at most ~128 paren levels / ~128 flat
#: terms); this guard is DEFENSE IN DEPTH — even if that cap is ever raised or a
#: caller bypasses schema validation, the parser/evaluator still fail cleanly.
#: 150 is comfortably above any genuine formula's nesting yet far under the
#: default recursion limit (1000): ~150 paren levels cost only a few hundred
#: stack frames, so the guard always trips before the interpreter does.
_MAX_DEPTH = 150


class SketchExpressionError(SketchDefinitionError):
    """A dimension expression is malformed, references an unknown/driven
    dimension, forms a reference cycle, or divides by zero.

    A subclass of :class:`SketchDefinitionError` so the existing
    ``except SketchDefinitionError`` in the feature evaluator maps it to the
    ``sketch_invalid`` error envelope with no new plumbing.
    """


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \s*                                   # skip leading whitespace
    (?:
        (?P<num>\d+\.\d*|\.\d+|\d+)       # 3, 3.5, 3., .5
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*) # width, height_2, _x
      | (?P<op>[-+*/()])                   # operators + parens
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Token:
    kind: str  # "num" | "ident" | "op"
    value: str


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    length = len(text)
    while pos < length:
        match = _TOKEN_RE.match(text, pos)
        if match is None or match.end() == pos:
            # No token matched at a non-whitespace character.
            stripped = text[pos:].lstrip()
            if not stripped:  # only trailing whitespace remained
                break
            raise SketchExpressionError(
                f"invalid character {stripped[0]!r} in expression {text!r}"
            )
        pos = match.end()
        kind = match.lastgroup
        assert kind is not None  # one alternative always captures
        tokens.append(_Token(kind=kind, value=match.group(kind)))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


def _guard_eval_depth(depth: int) -> None:
    """Fail cleanly past :data:`_MAX_DEPTH` so a deep (left-deep binary or
    unary) AST can never blow ``_Node.evaluate`` into a ``RecursionError``.

    A flat expression like ``1 + 1 + ... + 1`` parses ITERATIVELY (no parser
    recursion) but builds a left-deep :class:`_Binary` chain whose evaluation
    recurses once per term — so the request-boundary length cap and the
    parser's depth guard alone do not bound it; this eval-side guard does.
    """
    if depth > _MAX_DEPTH:
        raise SketchExpressionError(
            f"dimension expression nests deeper than {_MAX_DEPTH}; simplify it"
        )


@dataclass(frozen=True)
class _Num:
    value: float

    def references(self) -> set[str]:
        return set()

    def evaluate(self, resolve: Resolver, _depth: int = 0) -> float:
        return self.value


@dataclass(frozen=True)
class _Ref:
    name: str

    def references(self) -> set[str]:
        return {self.name}

    def evaluate(self, resolve: Resolver, _depth: int = 0) -> float:
        return resolve(self.name)


@dataclass(frozen=True)
class _Unary:
    op: str
    operand: _Node

    def references(self) -> set[str]:
        return self.operand.references()

    def evaluate(self, resolve: Resolver, _depth: int = 0) -> float:
        _guard_eval_depth(_depth)
        value = self.operand.evaluate(resolve, _depth + 1)
        return -value if self.op == "-" else value


@dataclass(frozen=True)
class _Binary:
    op: str
    left: _Node
    right: _Node

    def references(self) -> set[str]:
        return self.left.references() | self.right.references()

    def evaluate(self, resolve: Resolver, _depth: int = 0) -> float:
        _guard_eval_depth(_depth)
        left = self.left.evaluate(resolve, _depth + 1)
        right = self.right.evaluate(resolve, _depth + 1)
        if self.op == "+":
            return left + right
        if self.op == "-":
            return left - right
        if self.op == "*":
            return left * right
        if right == 0.0:
            raise SketchExpressionError("division by zero in dimension expression")
        return left / right


#: One node of a parsed dimension expression.
_Node = _Num | _Ref | _Unary | _Binary


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], text: str) -> None:
        self._tokens = tokens
        self._text = text
        self._pos = 0
        self._depth = 0

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def parse(self) -> _Node:
        node = self._parse_expr()
        remaining = self._peek()
        if remaining is not None:
            raise SketchExpressionError(
                f"unexpected {remaining.value!r} in expression {self._text!r}"
            )
        return node

    def _parse_expr(self) -> _Node:
        node = self._parse_term()
        while (token := self._peek()) is not None and token.value in ("+", "-"):
            op = self._advance().value
            node = _Binary(op=op, left=node, right=self._parse_term())
        return node

    def _parse_term(self) -> _Node:
        node = self._parse_factor()
        while (token := self._peek()) is not None and token.value in ("*", "/"):
            op = self._advance().value
            node = _Binary(op=op, left=node, right=self._parse_factor())
        return node

    def _parse_factor(self) -> _Node:
        # Every increase in grammar-nesting depth passes through _parse_factor
        # exactly once — a parenthesis (primary -> expr -> term -> factor) and a
        # unary operator (factor -> factor) each add one level — so tracking
        # depth here bounds BOTH the nested-paren and the unary-chain recursion
        # vectors with a single counter. Sequential (non-nested) factors in a
        # `a*b*c` term do not accumulate: the try/finally unwinds each. Past the
        # limit we raise a clean SketchExpressionError rather than let the
        # recursive descent run into a RecursionError (an uncaught 500).
        self._depth += 1
        try:
            if self._depth > _MAX_DEPTH:
                raise SketchExpressionError(
                    f"expression {self._text!r} nests deeper than {_MAX_DEPTH}; "
                    "simplify it"
                )
            token = self._peek()
            if token is not None and token.value in ("+", "-"):
                op = self._advance().value
                return _Unary(op=op, operand=self._parse_factor())
            return self._parse_primary()
        finally:
            self._depth -= 1

    def _parse_primary(self) -> _Node:
        token = self._peek()
        if token is None:
            raise SketchExpressionError(f"unexpected end of expression {self._text!r}")
        if token.kind == "num":
            self._advance()
            return _Num(value=float(token.value))
        if token.kind == "ident":
            self._advance()
            return _Ref(name=token.value)
        if token.value == "(":
            self._advance()
            node = self._parse_expr()
            closing = self._peek()
            if closing is None or closing.value != ")":
                raise SketchExpressionError(f"missing ')' in expression {self._text!r}")
            self._advance()
            return node
        raise SketchExpressionError(
            f"unexpected {token.value!r} in expression {self._text!r}"
        )


def parse_expression(text: str) -> _Node:
    """Parse a dimension expression into an AST (raises on syntax error).

    Exposed for unit testing; callers normally use
    :func:`evaluate_driving_dimensions`.
    """
    tokens = _tokenize(text)
    if not tokens:
        raise SketchExpressionError(f"empty expression {text!r}")
    return _Parser(tokens, text).parse()


# ---------------------------------------------------------------------------
# Dimension evaluation (the graph + topological order + cycle detection)
# ---------------------------------------------------------------------------


def _check_value(
    value: float, who: str, constraint: DimensionConstraint | None = None
) -> float:
    """A dimension must resolve to a finite value inside its own kind's range.

    Every dimension is positive (a distance, a radius, a diameter and an angle
    are all > 0). An ANGLE additionally has an upper bound: 180 degrees and
    beyond is the parallel degeneracy the ``parallel`` constraint owns, and the
    unsigned authored value cannot say which side of the first line the second
    sits on there. The literal case is already refused by the field bounds on
    :class:`~py_kit.schemas.sketch.AngleConstraint`; this is the EXPRESSION case,
    which those bounds cannot see (``expression="base*4"`` is a valid string
    holding an invalid angle) — without it the out-of-range value would reach
    planegcs and come back as a silently reinterpreted, wrapped angle.
    """
    if not math.isfinite(value):
        raise SketchExpressionError(f"dimension {who} evaluates to a non-finite value")
    if value <= 0.0:
        raise SketchExpressionError(
            f"dimension {who} evaluates to {value}; a dimension must be > 0"
        )
    if isinstance(constraint, AngleConstraint) and value >= 180.0:
        raise SketchExpressionError(
            f"dimension {who} evaluates to {value} degrees; an angle dimension "
            "must be < 180 (0 and 180 are the parallel degeneracies)"
        )
    return value


def evaluate_driving_dimensions(
    constraints: Sequence[SketchConstraint],
) -> dict[int, float]:
    """Evaluate every **driving** dimension to a concrete value.

    Each value is in its OWN dimension's unit — mm for distance/radius/diameter,
    DEGREES for an angle. An expression is plain arithmetic over other
    dimensions' names and carries no units, so a cross-unit reference
    (``angle="width/2"``) is arithmetic the author asked for, not an error this
    layer can diagnose.

    Returns a mapping ``constraint index -> value`` covering exactly the
    driving dimension constraints (driven dimensions are excluded — they are
    never fed to the solver). A literal driving dimension maps to its authored
    value unchanged (so a literal-only sketch feeds the solver bitwise
    what it always did); an expression dimension maps to its evaluated value.

    References resolve to other **driving** named dimensions; the resolver is
    memoized and carries the active reference chain, so:

    * an unknown name → :class:`SketchExpressionError`;
    * a reference to a driven dimension → :class:`SketchExpressionError`
      (a driven value is only known after the solve, so it cannot drive one);
    * a cycle (``a="b"``, ``b="a"``) → :class:`SketchExpressionError`, named,
      instead of unbounded recursion.
    """
    dims: list[tuple[int, DimensionConstraint]] = [
        (index, constraint)
        for index, constraint in enumerate(constraints)
        if isinstance(constraint, DimensionConstraint)
    ]

    #: name -> (index, dimension) for every NAMED dimension (driving or not);
    #: driven names are kept so a reference to one is a precise error, not a
    #: bare "unknown name". Uniqueness is enforced upstream (SketchDefinition).
    by_name: dict[str, tuple[int, DimensionConstraint]] = {
        constraint.name: (index, constraint)
        for index, constraint in dims
        if constraint.name is not None
    }

    node_cache: dict[int, _Node | None] = {}

    def node_for(index: int, constraint: DimensionConstraint) -> _Node | None:
        if index not in node_cache:
            node_cache[index] = (
                parse_expression(constraint.expression)
                if constraint.expression is not None
                else None
            )
        return node_cache[index]

    value_cache: dict[str, float] = {}

    def resolve(name: str, stack: tuple[str, ...]) -> float:
        if name in value_cache:
            return value_cache[name]
        if name in stack:
            chain = " -> ".join((*stack, name))
            raise SketchExpressionError(f"dimension expression cycle: {chain}")
        if name not in by_name:
            raise SketchExpressionError(
                f"unknown dimension name {name!r} in expression"
            )
        index, constraint = by_name[name]
        if not constraint.is_driving:
            raise SketchExpressionError(
                f"expression references driven dimension {name!r}; only driving "
                "dimensions can be referenced"
            )
        node = node_for(index, constraint)
        if node is None:
            value = constraint.value
        else:
            value = node.evaluate(lambda inner: resolve(inner, (*stack, name)))
        value = _check_value(value, repr(name), constraint)
        value_cache[name] = value
        return value

    result: dict[int, float] = {}
    for index, constraint in dims:
        if not constraint.is_driving:
            continue  # driven — excluded from the solver
        if constraint.name is not None:
            # Route named dims through resolve() so the cache + cycle detection
            # cover them (and a self-referential expression is caught).
            result[index] = resolve(constraint.name, ())
            continue
        node = node_for(index, constraint)
        if node is None:
            result[index] = _check_value(constraint.value, f"#{index}", constraint)
        else:
            value = node.evaluate(lambda inner: resolve(inner, ()))
            result[index] = _check_value(value, f"#{index}", constraint)
    return result


def measure_dimension(
    constraint: DimensionConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """Measure a **driven** dimension's value from solved geometry (mm).

    A driven dimension is excluded from the constraint system, so its displayed
    value is read back from the geometry it dimensions: a distance is the solved
    line's length; a radius is the solved circle's radius or the arc's
    ``|start - center|``; a diameter is twice that radius, so the readout is in
    the same unit the user typed. A driven dimension on the wrong entity kind (or an
    unknown entity) is a malformed definition — :class:`SketchDefinitionError`,
    mapped to ``sketch_invalid`` like any other bad reference.
    """
    match constraint:
        case DistanceConstraint():
            entity = entities_by_id.get(constraint.entity)
            if not isinstance(entity, SketchLine):
                raise SketchDefinitionError(
                    f"Driven 'distance' dimension requires a line entity; "
                    f"{constraint.entity!r} is not a known line"
                )
            return math.hypot(
                entity.end.x - entity.start.x, entity.end.y - entity.start.y
            )
        case RadiusConstraint():
            entity = entities_by_id.get(constraint.entity)
            if isinstance(entity, SketchCircle):
                return entity.radius
            if isinstance(entity, SketchArc):
                return math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
            raise SketchDefinitionError(
                f"Driven 'radius' dimension requires a circle or arc entity; "
                f"{constraint.entity!r} is neither"
            )
        case DiameterConstraint():
            entity = entities_by_id.get(constraint.entity)
            if isinstance(entity, SketchCircle):
                return 2.0 * entity.radius
            if isinstance(entity, SketchArc):
                return 2.0 * math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
            raise SketchDefinitionError(
                f"Driven 'diameter' dimension requires a circle or arc entity; "
                f"{constraint.entity!r} is neither"
            )
        case _:
            raise SketchDefinitionError(
                f"Cannot measure driven dimension of kind {constraint!r}"
            )


def measure_angle(
    constraint: AngleConstraint,
    entities_by_id: dict[str, SketchEntity],
    frame: AngleFrame | None,
) -> float:
    """Measure an angle dimension from solved geometry, in DEGREES.

    The angular twin of :func:`measure_dimension`, kept separate because its
    unit is not millimetres and because it needs the authoring convention
    (:class:`~geometry.sketch.angles.AngleFrame`) that says WHICH of the two
    supplementary angles the constraint names — a fact about the sketch as
    DRAWN, which solved geometry alone cannot supply.

    Both ids must be lines: an angle dimension on anything else is a malformed
    definition (:class:`SketchDefinitionError`, mapped to ``sketch_invalid``),
    the same treatment a radius dimension on a line gets.
    """
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    if not isinstance(a, SketchLine) or not isinstance(b, SketchLine):
        raise SketchDefinitionError(
            f"'angle' dimension requires two line entities; {constraint.a!r} "
            f"and {constraint.b!r} are not both known lines"
        )
    if frame is None:  # pragma: no cover — a two-line constraint always frames
        raise SketchDefinitionError(
            f"'angle' dimension between {constraint.a!r} and {constraint.b!r} "
            "has no measurable frame in the submitted sketch"
        )
    return measured_angle_deg(
        frame,
        (a.end.x - a.start.x, a.end.y - a.start.y),
        (b.end.x - b.start.x, b.end.y - b.start.y),
    )
