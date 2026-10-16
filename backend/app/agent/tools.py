import ast
import math
import operator

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalculationError(ValueError):
    pass


def calculate(expression: str) -> float:
    """Safely evaluate an arithmetic expression (numbers, + - * / ** %, parentheses)."""
    expression = expression.replace(",", "").replace("%", "").strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise CalculationError(f"invalid expression: {expression!r}") from e

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            if abs(node.value) > 1e15:  # financial figures never need more; blocks overflow tricks
                raise CalculationError("number too large")
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise CalculationError("exponent too large")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        raise CalculationError(f"unsupported expression: {expression!r}")

    try:
        result = ev(tree)
    except ZeroDivisionError as e:
        raise CalculationError("division by zero") from e
    except (
        ArithmeticError,
        ValueError,
        RecursionError,
        MemoryError,
    ) as e:  # OverflowError, huge literals...
        raise CalculationError("number too large or invalid") from e
    if not math.isfinite(result):
        raise CalculationError("result is not a finite number")
    return result
