"""Loft's one expression language: sketch dimensions and part parameters.

A dimension, and later any numeric feature field or part parameter (Fusion's
Change Parameters, Onshape's Variables), may hold a FORMULA instead of a
number: ``width/2``, ``20*tan(15)``, ``0.5 in + 3``. This module is the whole
language. It is a hand-written tokenizer and recursive-descent parser, never
:func:`eval`: the grammar below is everything that exists, so a hostile or
malformed string can only ever be a typed :class:`ExpressionError`.

It is standard-library only (``re``, ``math``, ``dataclasses``, ``typing``)
so documents, geometry, the gateway and ``loft-script`` all evaluate the same
string to the same float. Decision record: RESEARCH §20.

Grammar (EBNF)::

    expr    := term   (('+' | '-') term)*
    term    := factor (('*' | '/') factor)*
    factor  := ('+' | '-') factor | primary
    primary := NUMBER [UNIT] | 'pi' | CALL | IDENT | '(' expr ')'
    CALL    := FUNCTION '(' expr (',' expr)* ')'

    NUMBER  := digits ['.' digits] | '.' digits     (ASCII; a leading '-' is
               the unary-minus OPERATOR; no exponent form)
    UNIT    := 'mm' | 'cm' | 'm' | 'in' | 'ft' | 'deg' | 'rad'
    IDENT   := [A-Za-z_][A-Za-z0-9_]*

Units. Every value has a KIND: ``length`` (held in mm), ``angle`` (held in
degrees) or ``unitless``. A bare number is unitless, and unitless is
compatible with both, so ``20`` in a length field is 20 mm and in an angle
field is 20 degrees. Adding a length to an angle, multiplying two lengths
(Loft has no area fields), dividing a number by a length, and feeding a length
to a trig function are :class:`ExpressionUnitError`. A length over a length is
a unitless ratio.

Functions (a fixed whitelist; any other call is an error):

* ``sin cos tan`` take DEGREES (an angle, or a unitless number read as
  degrees) and return a unitless number;
* ``asin acos atan`` take a unitless number and ``atan2(y, x)`` two values of
  one kind; all four return an ANGLE in degrees;
* ``sqrt`` takes a unitless number; ``abs round floor ceil`` keep their
  argument's kind (``round`` is half away from zero, as in a spreadsheet, not
  Python's banker's rounding); ``min max`` take one or more values of one kind;
* ``rad(x)`` turns degrees into a unitless number of radians and ``deg(x)``
  turns a unitless number of radians into an angle.

Limits: 256 characters, nesting depth 150, finite results only. A parameter
name matches ``^[A-Za-z_][A-Za-z0-9_]{0,63}$`` and is not a function, unit or
constant word.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Literal, Protocol, TypeGuard, runtime_checkable

# ---------------------------------------------------------------------------
# Kinds, limits, vocabulary
# ---------------------------------------------------------------------------

#: What a value measures. Lengths are held in mm and angles in degrees.
Kind = Literal["length", "angle", "unitless"]

LENGTH: Final[Kind] = "length"
ANGLE: Final[Kind] = "angle"
UNITLESS: Final[Kind] = "unitless"

#: The longest expression accepted, matching the wire field caps.
MAX_EXPRESSION_LENGTH: Final = 256

#: Deepest grammar nesting the parser and the evaluator descend before a clean
#: :class:`ExpressionLimitError`. A 256-character string reaches ~128 levels,
#: so this is defence in depth and far under Python's recursion limit.
MAX_DEPTH: Final = 150

#: Most parameters one part may define (PART-PARAMETERS).
MAX_PARAMETERS: Final = 200

#: An int field accepts a unitless value within this of an integer.
INT_TOLERANCE: Final = 1e-9

#: Identifier rule for a parameter name (reserved words are refused apart).
NAME_PATTERN: Final = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
_NAME_RE = re.compile(NAME_PATTERN, re.ASCII)

#: Unit suffix -> (factor to the kind's canonical unit, kind).
UNITS: Final[Mapping[str, tuple[float, Kind]]] = {
    "mm": (1.0, LENGTH),
    "cm": (10.0, LENGTH),
    "m": (1000.0, LENGTH),
    "in": (25.4, LENGTH),
    "ft": (304.8, LENGTH),
    "deg": (1.0, ANGLE),
    "rad": (180.0 / math.pi, ANGLE),
}

#: Named constants (unitless).
CONSTANTS: Final[Mapping[str, float]] = {"pi": math.pi}

#: Whitelisted function name -> (minimum, maximum) argument count; ``None``
#: maximum is variadic.
FUNCTIONS: Final[Mapping[str, tuple[int, int | None]]] = {
    "sin": (1, 1),
    "cos": (1, 1),
    "tan": (1, 1),
    "asin": (1, 1),
    "acos": (1, 1),
    "atan": (1, 1),
    "atan2": (2, 2),
    "sqrt": (1, 1),
    "abs": (1, 1),
    "min": (1, None),
    "max": (1, None),
    "round": (1, 1),
    "floor": (1, 1),
    "ceil": (1, 1),
    "rad": (1, 1),
    "deg": (1, 1),
}

#: Words no parameter or referenced dimension may be named.
RESERVED_WORDS: Final[frozenset[str]] = frozenset(
    {*UNITS.keys(), *CONSTANTS.keys(), *FUNCTIONS.keys()}
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExpressionError(ValueError):
    """Base of every expression failure. ``code`` is a stable machine id."""

    code: ClassVar[str] = "expression_invalid"


class ExpressionSyntaxError(ExpressionError):
    """The text is not in the grammar (including calls off the whitelist)."""

    code: ClassVar[str] = "expression_syntax"


class ExpressionLimitError(ExpressionError):
    """Longer than 256 characters, nested deeper than 150, or too many
    parameters."""

    code: ClassVar[str] = "expression_too_complex"


class ExpressionUnitError(ExpressionError):
    """Kinds that do not combine: ``10 mm + 5 deg``, ``a*b`` of two lengths,
    ``sin(10 mm)``, or a length where an angle is wanted."""

    code: ClassVar[str] = "expression_units"


class ExpressionDomainError(ExpressionError):
    """Arithmetic with no finite answer: division by zero, ``sqrt(-1)``,
    ``asin(2)``, ``tan(90)``, overflow, or an out-of-range result."""

    code: ClassVar[str] = "expression_domain"


class ExpressionReferenceError(ExpressionError):
    """A name that does not resolve, or may not be referenced."""

    code: ClassVar[str] = "expression_unknown_name"


class ExpressionCycleError(ExpressionError):
    """Names that depend on each other. ``chain`` is the loop, first name
    repeated last: ``("a", "b", "a")``."""

    code: ClassVar[str] = "expression_cycle"

    def __init__(self, message: str, chain: tuple[str, ...]) -> None:
        super().__init__(message)
        self.chain = chain


class ExpressionNameError(ExpressionError):
    """A parameter name that breaks the identifier rule, is reserved, or is
    defined twice."""

    code: ClassVar[str] = "expression_name_invalid"


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """A value and its kind: mm for a length, degrees for an angle."""

    value: float
    kind: Kind


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ExpressionDomainError("expression evaluates to a non-finite value")
    return value


def _a(kind: Kind) -> str:
    return f"an {kind}" if kind == ANGLE else f"a {kind}"


def _additive_kind(a: Kind, b: Kind, what: str) -> Kind:
    if a == b or b == UNITLESS:
        return a
    if a == UNITLESS:
        return b
    raise ExpressionUnitError(f"cannot {what} {_a(a)} and {_a(b)}")


def _multiply_kind(a: Kind, b: Kind) -> Kind:
    if b == UNITLESS:
        return a
    if a == UNITLESS:
        return b
    raise ExpressionUnitError(
        f"cannot multiply {_a(a)} by {_a(b)}; only one factor may carry a unit"
    )


def _divide_kind(a: Kind, b: Kind) -> Kind:
    if b == UNITLESS:
        return a
    if a == b:
        return UNITLESS
    raise ExpressionUnitError(f"cannot divide {_a(a)} by {_a(b)}")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    [ \t\r\n]*                            # ASCII whitespace only
    (?:
        (?P<num>[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>[-+*/(),])
    )
    """,
    re.VERBOSE | re.ASCII,
)

#: The tokenizer sketch dimensions shipped with before this module existed:
#: Unicode ``\s`` and ``\d`` (``float()`` reads any Unicode decimal digit).
#: Sketch text uses it so every stored expression tokenizes exactly as it did.
_LEGACY_TOKEN_RE = re.compile(
    r"""
    \s*
    (?:
        (?P<num>\d+\.\d*|\.\d+|\d+)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>[-+*/(),])
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Token:
    kind: str  # "num" | "ident" | "op"
    value: str


def _tokenize(text: str, legacy_text: bool = False) -> list[_Token]:
    pattern = _LEGACY_TOKEN_RE if legacy_text else _TOKEN_RE
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = pattern.match(text, pos)
        if match is None:
            rest = text[pos:].lstrip() if legacy_text else text[pos:].lstrip(" \t\r\n")
            if not rest:
                break
            raise ExpressionSyntaxError(
                f"invalid character {rest[0]!r} in expression {text!r}"
            )
        pos = match.end()
        kind = match.lastgroup
        assert kind is not None  # one alternative always captures
        tokens.append(_Token(kind=kind, value=match.group(kind)))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Num:
    quantity: Quantity


@dataclass(frozen=True)
class _Ref:
    name: str


@dataclass(frozen=True)
class _Unary:
    op: str
    operand: _Node


@dataclass(frozen=True)
class _Binary:
    op: str
    left: _Node
    right: _Node


@dataclass(frozen=True)
class _Call:
    name: str
    args: tuple[_Node, ...]


_Node = _Num | _Ref | _Unary | _Binary | _Call

#: Resolves a referenced name to its value.
Resolver = Callable[[str], Quantity]


def _degrees_in(fn: str, q: Quantity) -> float:
    if q.kind == LENGTH:
        raise ExpressionUnitError(f"{fn}() takes an angle in degrees, not a length")
    return math.radians(q.value)


def _unitless_in(fn: str, q: Quantity) -> float:
    if q.kind != UNITLESS:
        raise ExpressionUnitError(f"{fn}() takes a plain number, not {_a(q.kind)}")
    return q.value


def _round_half_away(value: float) -> float:
    magnitude = abs(value)
    whole = math.floor(magnitude)
    if magnitude - whole >= 0.5:
        whole += 1.0
    return math.copysign(whole, value) + 0.0


def _call(name: str, args: list[Quantity]) -> Quantity:
    """Apply one whitelisted function. Angles are degrees on both sides."""
    first = args[0]
    if name in ("sin", "cos", "tan"):
        radians = _degrees_in(name, first)
        if name == "tan" and abs(math.cos(radians)) < 1e-12:
            raise ExpressionDomainError(
                f"tan({first.value:g}) is undefined (an odd multiple of 90 degrees)"
            )
        fn = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name]
        return Quantity(fn(radians), UNITLESS)
    if name in ("asin", "acos"):
        x = _unitless_in(name, first)
        if not -1.0 <= x <= 1.0:
            raise ExpressionDomainError(f"{name}({x:g}) is undefined outside [-1, 1]")
        fn = math.asin if name == "asin" else math.acos
        return Quantity(math.degrees(fn(x)), ANGLE)
    if name == "atan":
        return Quantity(math.degrees(math.atan(_unitless_in(name, first))), ANGLE)
    if name == "atan2":
        y, x = args
        _additive_kind(y.kind, x.kind, "compare")
        if y.value == 0.0 and x.value == 0.0:
            raise ExpressionDomainError("atan2(0, 0) is undefined")
        return Quantity(math.degrees(math.atan2(y.value, x.value)), ANGLE)
    if name == "sqrt":
        x = _unitless_in(name, first)
        if x < 0.0:
            raise ExpressionDomainError(f"sqrt({x:g}) of a negative number")
        return Quantity(math.sqrt(x), UNITLESS)
    if name == "abs":
        return Quantity(abs(first.value), first.kind)
    if name in ("min", "max"):
        kind = first.kind
        for arg in args[1:]:
            kind = _additive_kind(kind, arg.kind, "compare")
        pick = min if name == "min" else max
        return Quantity(pick(arg.value for arg in args), kind)
    if name == "round":
        return Quantity(_round_half_away(first.value), first.kind)
    if name == "floor":
        return Quantity(float(math.floor(first.value)), first.kind)
    if name == "ceil":
        return Quantity(float(math.ceil(first.value)), first.kind)
    if name == "rad":
        return Quantity(_degrees_in(name, first), UNITLESS)
    assert name == "deg", name  # the whitelist is closed
    if first.kind != UNITLESS:
        raise ExpressionUnitError(
            f"deg() takes a plain number of radians, not a {first.kind}"
            if first.kind == LENGTH
            else "deg() takes a plain number of radians; this is already an angle"
        )
    return Quantity(math.degrees(first.value), ANGLE)


def _guard_depth(depth: int) -> None:
    # Interior nodes only, exactly where the pre-library evaluator guarded: a
    # leaf one level past the limit was always fine and must stay fine.
    if depth > MAX_DEPTH:
        raise ExpressionLimitError(f"expression nests deeper than {MAX_DEPTH}")


def _evaluate(node: _Node, resolve: Resolver, depth: int) -> Quantity:
    match node:
        case _Num():
            return node.quantity
        case _Ref():
            return resolve(node.name)
        case _Unary():
            _guard_depth(depth)
            q = _evaluate(node.operand, resolve, depth + 1)
            return Quantity(-q.value, q.kind) if node.op == "-" else q
        case _Binary():
            _guard_depth(depth)
            a = _evaluate(node.left, resolve, depth + 1)
            b = _evaluate(node.right, resolve, depth + 1)
            if node.op == "+":
                return Quantity(
                    a.value + b.value, _additive_kind(a.kind, b.kind, "add")
                )
            if node.op == "-":
                return Quantity(
                    a.value - b.value,
                    _additive_kind(a.kind, b.kind, "subtract"),
                )
            if node.op == "*":
                return Quantity(a.value * b.value, _multiply_kind(a.kind, b.kind))
            kind = _divide_kind(a.kind, b.kind)
            if b.value == 0.0:
                raise ExpressionDomainError("division by zero in expression")
            return Quantity(a.value / b.value, kind)
        case _Call():
            _guard_depth(depth)
            args = [_evaluate(arg, resolve, depth + 1) for arg in node.args]
            for arg in args:
                # math.sin(inf) raises ValueError, math.floor(inf) OverflowError.
                _finite(arg.value)
            return _call(node.name, args)


def _references(node: _Node, into: set[str]) -> None:
    # Iterative: a left-deep 128-term chain must not recurse per term here.
    stack: list[_Node] = [node]
    while stack:
        current = stack.pop()
        match current:
            case _Num():
                pass
            case _Ref():
                into.add(current.name)
            case _Unary():
                stack.append(current.operand)
            case _Binary():
                stack.extend((current.left, current.right))
            case _Call():
                stack.extend(current.args)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], text: str, names: frozenset[str]) -> None:
        self._tokens = tokens
        self._text = text
        self._names = names
        self._pos = 0
        self._depth = 0

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _error(self, message: str) -> ExpressionSyntaxError:
        return ExpressionSyntaxError(f"{message} in expression {self._text!r}")

    def parse(self) -> _Node:
        node = self._parse_expr()
        remaining = self._peek()
        if remaining is not None:
            raise self._error(f"unexpected {remaining.value!r}")
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
        # Every increase in nesting (a parenthesis, a call argument, a unary
        # operator) passes through here once, so one counter bounds them all.
        self._depth += 1
        try:
            if self._depth > MAX_DEPTH:
                raise ExpressionLimitError(
                    f"expression {self._text!r} nests deeper than {MAX_DEPTH}; "
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
            raise self._error("unexpected end")
        if token.kind == "num":
            self._advance()
            value = float(token.value)
            unit = self._peek()
            if unit is not None and unit.kind == "ident" and unit.value in UNITS:
                self._advance()
                factor, kind = UNITS[unit.value]
                return _Num(Quantity(value * factor, kind))
            return _Num(Quantity(value, UNITLESS))
        if token.kind == "ident":
            return self._parse_word(self._advance().value)
        if token.value == "(":
            self._advance()
            node = self._parse_expr()
            self._expect(")")
            return node
        raise self._error(f"unexpected {token.value!r}")

    def _parse_word(self, word: str) -> _Node:
        following = self._peek()
        calls = following is not None and following.value == "("
        if word in self._names and not calls:
            # A name in scope wins over a reserved word in reference position:
            # a stored sketch with a dimension called ``rad`` or ``pi`` keeps
            # meaning what it meant. A unit suffix (after a number) or a call
            # (before ``(``) never sat in that position in valid older text.
            return _Ref(name=word)
        if word in FUNCTIONS:
            if not calls:
                raise self._error(f"{word!r} is a function; write {word}(...)")
            return self._parse_call(word)
        if calls:
            raise self._error(f"unknown function {word!r}")
        if word in UNITS:
            raise self._error(f"unit {word!r} must follow a number, as in 10 {word}")
        if word in CONSTANTS:
            return _Num(Quantity(CONSTANTS[word], UNITLESS))
        return _Ref(name=word)

    def _parse_call(self, name: str) -> _Node:
        self._advance()  # '('
        args = [self._parse_expr()]
        while (token := self._peek()) is not None and token.value == ",":
            self._advance()
            args.append(self._parse_expr())
        self._expect(")")
        low, high = FUNCTIONS[name]
        if len(args) < low or (high is not None and len(args) > high):
            wanted = f"{low}" if low == high else f"at least {low}"
            raise self._error(f"{name}() takes {wanted} argument(s), got {len(args)}")
        return _Call(name=name, args=tuple(args))

    def _expect(self, value: str) -> None:
        token = self._peek()
        if token is None or token.value != value:
            raise self._error(f"missing {value!r}")
        self._advance()


# ---------------------------------------------------------------------------
# Public parse / evaluate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expression:
    """A parsed expression. Immutable; evaluate it as often as you like."""

    text: str
    _root: _Node
    #: Every identifier token in the text, reserved words included.
    words: frozenset[str]

    def references(self) -> frozenset[str]:
        """The names this expression reads (never constants, units or calls)."""
        names: set[str] = set()
        _references(self._root, names)
        return frozenset(names)

    def evaluate(self, resolve: Resolver) -> Quantity:
        """Evaluate with typed references; the result is finite. Raises
        :class:`ExpressionError`."""
        q = _evaluate(self._root, resolve, 0)
        _finite(q.value)
        return q

    def evaluate_number(self, resolve: Callable[[str], float]) -> float:
        """Evaluate with each reference read as a plain (unitless) number and
        return the bare value, in mm or degrees if the text carries units.

        Like the pre-library sketch evaluator it does NOT check the result is
        finite; the caller does (a sketch dimension must be finite and > 0).
        """
        return _evaluate(
            self._root, lambda name: Quantity(resolve(name), UNITLESS), 0
        ).value


def parse(
    text: str, *, names: frozenset[str] = frozenset(), legacy_text: bool = False
) -> Expression:
    """Parse ``text`` (raises :class:`ExpressionError`, never executes it).

    ``names`` are the names in scope: in reference position (not after a
    number, not before ``(``) such a name is a reference even if it is also a
    unit, function or ``pi``. ``legacy_text`` is for sketch dimensions: it
    accepts exactly the text the pre-library tokenizer did (Unicode digits and
    whitespace) and leaves the 256-character cap to the wire field, as before.
    """
    if not legacy_text and len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionLimitError(
            f"expression is {len(text)} characters; the limit is "
            f"{MAX_EXPRESSION_LENGTH}"
        )
    tokens = _tokenize(text, legacy_text)
    if not tokens:
        raise ExpressionSyntaxError(f"empty expression {text!r}")
    root = _Parser(tokens, text, names).parse()
    words = frozenset(t.value for t in tokens if t.kind == "ident")
    return Expression(text=text, _root=root, words=words)


def evaluate(text: str, names: Mapping[str, Quantity] | None = None) -> Quantity:
    """Parse and evaluate ``text`` against a fixed table of named values."""
    table = names or {}

    def resolve(name: str) -> Quantity:
        if name not in table:
            raise ExpressionReferenceError(f"unknown name {name!r} in expression")
        return table[name]

    return parse(text).evaluate(resolve)


def coerce(quantity: Quantity, target: Kind, who: str = "expression") -> float:
    """The value of ``quantity`` for a field of kind ``target``.

    A unitless value fits a length (mm) or an angle (degrees); a length never
    fits an angle field, nor the reverse; a unitless field takes only a
    unitless value.
    """
    if quantity.kind != target and quantity.kind != UNITLESS:
        raise ExpressionUnitError(
            f"{who} evaluates to {_a(quantity.kind)}; expected {_noun(target)}"
        )
    return _finite(quantity.value)


def coerce_int(quantity: Quantity, who: str = "expression") -> int:
    """The value for an integer field: unitless, within 1e-9 of an integer."""
    value = coerce(quantity, UNITLESS, who)
    nearest = round(value)
    if abs(value - nearest) > INT_TOLERANCE:
        raise ExpressionDomainError(
            f"{who} evaluates to {value!r}; this field needs a whole number"
        )
    return int(nearest)


def _noun(kind: Kind) -> str:
    return {LENGTH: "a length", ANGLE: "an angle", UNITLESS: "a plain number"}[kind]


def validate_name(name: str) -> str:
    """Return ``name`` if it may name a parameter, else raise
    :class:`ExpressionNameError`."""
    if not _NAME_RE.fullmatch(name):
        raise ExpressionNameError(
            f"{name!r} is not a valid name: start with a letter or _, then up to "
            "63 letters, digits or _"
        )
    if name in RESERVED_WORDS:
        raise ExpressionNameError(
            f"{name!r} is reserved (a function, unit or constant); choose another name"
        )
    return name


# ---------------------------------------------------------------------------
# Name graphs: ordering with cycle reports
# ---------------------------------------------------------------------------


def _dependency_order(
    roots: Sequence[str], deps: Callable[[str], frozenset[str]], label: str
) -> list[str]:
    """Post-order of everything reachable from ``roots``, ITERATIVELY (a
    200-long chain must not touch the recursion limit). ``deps`` raises for an
    unknown name; a loop raises :class:`ExpressionCycleError` with its chain."""
    order: list[str] = []
    done: set[str] = set()
    for root in roots:
        if root in done:
            continue
        path = [root]
        on_path = {root}
        stack = [iter(sorted(deps(root)))]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                finished = path.pop()
                on_path.discard(finished)
                done.add(finished)
                order.append(finished)
                continue
            if nxt in done:
                continue
            if nxt in on_path:
                chain = (*path[path.index(nxt) :], nxt)
                raise ExpressionCycleError(
                    f"{label} cycle: {' -> '.join(chain)}", chain
                )
            path.append(nxt)
            on_path.add(nxt)
            stack.append(iter(sorted(deps(nxt))))
    return order


@dataclass(frozen=True)
class NamedExpression:
    """One row of a parameter table: a name, its formula and its kind."""

    name: str
    expression: str
    kind: Kind


def evaluate_parameters(rows: Sequence[NamedExpression]) -> dict[str, Quantity]:
    """Evaluate a parameter table. Every row may reference any other row.

    Each value takes its row's declared kind (a unitless result in a length
    row is mm). Raises on a bad or duplicate name, more than
    :data:`MAX_PARAMETERS` rows, an unknown name, a cycle, or a unit clash.
    """
    if len(rows) > MAX_PARAMETERS:
        raise ExpressionLimitError(
            f"{len(rows)} parameters; a part may define at most {MAX_PARAMETERS}"
        )
    by_name: dict[str, NamedExpression] = {}
    for row in rows:
        validate_name(row.name)
        if row.name in by_name:
            raise ExpressionNameError(f"parameter {row.name!r} is defined twice")
        by_name[row.name] = row

    parsed: dict[str, Expression] = {}

    def deps(name: str) -> frozenset[str]:
        if name not in by_name:
            raise ExpressionReferenceError(f"unknown parameter {name!r} in expression")
        if name not in parsed:
            parsed[name] = parse(by_name[name].expression)
        return parsed[name].references()

    values: dict[str, Quantity] = {}
    for name in _dependency_order([row.name for row in rows], deps, "parameter"):
        row = by_name[name]
        q = parsed[name].evaluate(values.__getitem__)
        values[name] = Quantity(coerce(q, row.kind, f"parameter {name!r}"), row.kind)
    return {row.name: values[row.name] for row in rows}


# ---------------------------------------------------------------------------
# Sketch dimensions
# ---------------------------------------------------------------------------


@runtime_checkable
class DimensionLike(Protocol):
    """What :func:`evaluate_driving_dimensions` reads from a dimension
    constraint (``loft_wire.sketch.DimensionConstraint`` satisfies it; this
    module stays standard-library only)."""

    kind: str
    expression: str | None
    name: str | None

    @property
    def value(self) -> float: ...

    @property
    def is_driving(self) -> bool: ...


def _is_dimension(constraint: object) -> TypeGuard[DimensionLike]:
    return isinstance(constraint, DimensionLike)


def _check_dimension(value: float, who: str, is_angle: bool) -> float:
    """A dimension is finite and > 0; an angle is also < 180 degrees.

    180 and beyond is the parallel degeneracy the ``parallel`` constraint
    owns, and the literal case is refused by ``AngleConstraint``'s field
    bounds; an EXPRESSION (``base*4``) can reach it where those bounds cannot
    see, and planegcs would silently wrap it.
    """
    if not math.isfinite(value):
        raise ExpressionDomainError(f"dimension {who} evaluates to a non-finite value")
    if value <= 0.0:
        raise ExpressionDomainError(
            f"dimension {who} evaluates to {value}; a dimension must be > 0"
        )
    if is_angle and value >= 180.0:
        raise ExpressionDomainError(
            f"dimension {who} evaluates to {value} degrees; an angle dimension "
            "must be < 180 (0 and 180 are the parallel degeneracies)"
        )
    return value


def evaluate_driving_dimensions(constraints: Sequence[object]) -> dict[int, float]:
    """Evaluate every DRIVING dimension of a sketch to a concrete value.

    Returns ``constraint index -> value`` in the dimension's own unit (mm, or
    degrees for an angle), for exactly the driving dimensions. A literal maps
    to its authored value unchanged, so a literal-only sketch feeds the solver
    bitwise what it always did.

    A reference to another dimension reads that dimension's NUMBER, unitless:
    ``angle = "half*2"`` over a 20 mm ``half`` is 40 degrees, as it was before
    units existed, so every stored sketch evaluates as it did. Unit suffixes
    and functions are typed: ``30 deg`` in a distance is a unit error, and
    ``tan()`` reads degrees. A dimension's name wins over a reserved word in
    reference position (a dimension ``rad`` makes ``rad*2`` read it), and the
    text is tokenized as before (Unicode digits and whitespace). Unknown names,
    references to driven dimensions (known only after the solve) and cycles
    are :class:`ExpressionError`.
    """
    dims = [(i, c) for i, c in enumerate(constraints) if _is_dimension(c)]

    def key(index: int, dim: DimensionLike) -> str:
        # '#' cannot start an identifier, so an unnamed key is never referenced.
        return dim.name if dim.name is not None else f"#{index}"

    by_key = {key(i, c): (i, c) for i, c in dims}
    names = frozenset(c.name for _, c in dims if c.name is not None)
    parsed: dict[str, Expression | None] = {}

    def deps(name: str) -> frozenset[str]:
        if name not in by_key:
            raise ExpressionReferenceError(
                f"unknown dimension name {name!r} in expression"
            )
        _, dim = by_key[name]
        if not dim.is_driving:
            raise ExpressionReferenceError(
                f"expression references driven dimension {name!r}; only driving "
                "dimensions can be referenced"
            )
        if name not in parsed:
            parsed[name] = (
                None
                if dim.expression is None
                else parse(dim.expression, names=names, legacy_text=True)
            )
        node = parsed[name]
        return node.references() if node is not None else frozenset()

    roots = [key(i, c) for i, c in dims if c.is_driving]
    values: dict[str, float] = {}
    for name in _dependency_order(roots, deps, "dimension expression"):
        index, dim = by_key[name]
        node = parsed[name]
        who = repr(name) if dim.name is not None else f"#{index}"
        is_angle = dim.kind == "angle"
        if node is None:
            value = dim.value
        else:
            q = node.evaluate(lambda ref: Quantity(values[ref], UNITLESS))
            value = coerce(q, ANGLE if is_angle else LENGTH, f"dimension {who}")
        values[name] = _check_dimension(value, who, is_angle)
    return {i: values[key(i, c)] for i, c in dims if c.is_driving}
