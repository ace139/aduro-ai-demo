"""
Aduro AI Demo Agents Package
"""

# Import OpenAI Agents SDK
from openai_agents import Agent as BaseAgent
from openai_agents import FunctionTool

# Re-export the necessary classes
class Agent(BaseAgent):
    """Base agent class for all Aduro AI agents."""
    pass

def function_tool(func):
    """Decorator for function tools."""
    # This is a wrapper around FunctionTool to make it work as a decorator
    return FunctionTool(func)

# Export these names
__all__ = ['Agent', 'function_tool']
