from __future__ import annotations

import ast
import operator

from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, reply_embed


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_calculate(expression: str) -> float:
    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[type(node.op)](eval_node(node.operand))
        raise ValueError("Unsupported expression")

    parsed = ast.parse(expression, mode="eval")
    return eval_node(parsed)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="calc", aliases=["calculator"])
    async def calc(self, ctx: commands.Context, *, expression: str) -> None:
        try:
            result = safe_calculate(expression)
        except Exception:
            await reply_embed(
                ctx,
                title="Calculation Error",
                description="Use a safe numeric expression like `-calc (5+3)*2`.",
                color=ERROR,
            )
            return
        await reply_embed(
            ctx,
            title="Calculator Result",
            description=f"Expression evaluated successfully.",
            color=SUCCESS,
            fields=[("Expression", f"`{expression}`", False), ("Result", f"`{result}`", False)],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
