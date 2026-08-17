"""Entities package."""
from .config import TLangConfig
from .parser import Parser, ParseError, ParseResult
from .semantic import SemanticChecker, SemanticResult
from .ast_visitor import ASTVisitor
__all__ = [
    "TLangConfig",
    "Parser",
    "ParseError",
    "ParseResult",
    "SemanticChecker",
    "SemanticResult",
    "ASTVisitor",
]
