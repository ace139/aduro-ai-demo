"""
Triage Agent for the Aduro Health Assistant.

This agent acts as the main entry point for user interactions and routes
requests to the appropriate specialized agents based on the user's input.
"""

from enum import Enum
from types import SimpleNamespace
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from aduro_agents.cgm_collector import CGMCollector

# Import specialized agents
from aduro_agents.greeter_profiler import GreeterProfiler
from aduro_agents.meal_planner import MealPlanner
from aduro_agents.models import AduroConversationContext, UserIntent
from aduro_agents.profile_updater import ProfileUpdater


class IntentDetectionOutput(Enum):
    """Output format for intent detection."""

    INTENT = "intent"
    CONFIDENCE = "confidence"
    REASONING = "reasoning"


# Intent detection prompts
INTENT_DETECTION_PROMPT = """
Analyze the user's message and determine their intent. Choose from the following intents:

1. {greeting} - For greetings, hellos, or general conversation starters
2. {profile_query} - For questions about the user's profile
3. {profile_update} - For updating or modifying profile information
4. {cgm_query} - For asking about CGM readings or trends
5. {cgm_update} - For logging or updating CGM readings
6. {meal_query} - For asking about meals or nutrition
7. {meal_plan} - For requesting or discussing meal plans

Return a JSON object with the following fields:
- "intent": The detected intent (one of the options above)
- "confidence": Your confidence level (0.0 to 1.0)
- "reasoning": Brief explanation of your choice

User message: {message}"""


async def detect_intent(message: str | dict[str, Any]) -> dict[str, Any]:
    """
    Detect the user's intent from their message.

    Args:
        message: The user's message as a string or a dictionary with a 'text' key

    Returns:
        Dict containing intent, confidence, and reasoning
    """
    result = {
        IntentDetectionOutput.INTENT: UserIntent.UNKNOWN,
        IntentDetectionOutput.CONFIDENCE: 0.3,  # Default confidence for unknown
        IntentDetectionOutput.REASONING: "Could not determine specific intent from message",
    }

    # Handle different input types
    if isinstance(message, dict):
        message_text = message.get("text", "")
    else:
        message_text = str(message)

    # If message is empty after conversion, set specific reasoning and return
    if not message_text.strip():
        result[IntentDetectionOutput.CONFIDENCE] = 0.0
        result[IntentDetectionOutput.REASONING] = "Empty or invalid message"
        return result  # Early exit for empty message

    message_lower = message_text.lower()

    # Simple keyword matching for demonstration
    if any(word in message_lower for word in ["hello", "hi", "hey", "greetings"]):
        result[IntentDetectionOutput.INTENT] = UserIntent.GREETING
        result[IntentDetectionOutput.CONFIDENCE] = 0.9
        result[IntentDetectionOutput.REASONING] = (
            "Message contains common greeting words"
        )
    elif any(word in message_lower for word in ["profile", "my info", "my details"]):
        if "update" in message_lower or "change" in message_lower:
            result[IntentDetectionOutput.INTENT] = UserIntent.PROFILE_UPDATE
            result[IntentDetectionOutput.CONFIDENCE] = 0.8
            result[IntentDetectionOutput.REASONING] = (
                "User wants to update their profile information"
            )
        else:
            result[IntentDetectionOutput.INTENT] = UserIntent.PROFILE_QUERY
            result[IntentDetectionOutput.CONFIDENCE] = 0.7
            result[IntentDetectionOutput.REASONING] = (
                "User is asking about their profile"
            )
    elif any(word in message_lower for word in ["glucose", "sugar", "cgm", "blood"]):
        result[IntentDetectionOutput.INTENT] = UserIntent.CGM_DATA
        result[IntentDetectionOutput.CONFIDENCE] = 0.85
        result[IntentDetectionOutput.REASONING] = (
            "Message relates to CGM or blood sugar data"
        )
    elif any(word in message_lower for word in ["meal", "food", "diet", "eat"]):
        result[IntentDetectionOutput.INTENT] = UserIntent.MEAL_PLAN
        result[IntentDetectionOutput.CONFIDENCE] = 0.8
        result[IntentDetectionOutput.REASONING] = (
            "Message relates to meal planning or diet"
        )
    # No explicit "else" needed, as result is pre-populated with UNKNOWN if no conditions match.

    return result


class TriageAgent(Agent):
    """
    Triage agent that routes user requests to specialized agents.

    This agent acts as the main entry point for user interactions and routes
    requests to the appropriate specialized agents based on the user's input.
    """

    def __init__(
        self,
        db_path: str | None = None,
        greeter_profiler: Agent = None,
        profile_updater: Agent = None,
        cgm_collector: Agent = None,
        meal_planner: Agent = None,
    ):
        """
        Initialize the TriageAgent with specialized agents.

        Args:
            db_path: Path to the SQLite database file (optional).
            greeter_profiler: An instance of GreeterProfiler (optional).
            profile_updater: An instance of ProfileUpdater (optional).
            cgm_collector: An instance of CGMCollector (optional).
            meal_planner: An instance of MealPlanner (optional).
        """
        # Initialize the base Agent class with the expected name for tests
        super().__init__(
            name="aduro_triage_agent",
            instructions=f"""{RECOMMENDED_PROMPT_PREFIX}\n\n        You are the TriageAgent for the Aduro Health Assistant. Your job is to route
            user requests to the appropriate specialized agent based on the content of
            the message and the conversation context. You should be friendly, helpful,
            and provide clear guidance to users about what they can do with the system.

            You have access to the following specialized agents:
            - GreeterProfiler: For greeting new users and creating profiles
            - ProfileUpdater: For updating user profile information
            - CGMCollector: For collecting and analyzing CGM data
            - MealPlanner: For generating personalized meal plans

            The conversation context will provide you with information about:
            - The user's profile status (not_started, incomplete, complete)
            - Whether the user has CGM data
            - The user's last interaction

            Use this context to guide the conversation and ensure the user completes
            necessary steps in the right order.

            Always be polite, professional, and focused on the user's health and well-being.
            """,
            tools=[],  # No tools at the triage level
            handoffs=[],  # Will be populated with specialized agents
            handoff_description="""
            I'm the TriageAgent, your main point of contact with the Aduro Health Assistant.
            I'll help route your requests to the appropriate specialized agent based on your needs.
            Whether you're a new user, need to update your profile, track CGM data, or get meal planning
            assistance, I'll make sure you're connected with the right specialist.
            """,
        )

        # Store the input guardrail separately to avoid circular reference
        self._guardrail = input_guardrail(self._intent_guardrail)

        # Add the guardrail after initialization to avoid issues with self reference
        self.input_guardrails = [self._guardrail]

        # Store the database path for sub-agents
        self.db_path = db_path

        # Initialize specialized agents with provided instances or create new ones
        self.greeter_profiler = greeter_profiler or GreeterProfiler()
        self.profile_updater = profile_updater or ProfileUpdater()
        self.cgm_collector = cgm_collector or CGMCollector()
        self.meal_planner = meal_planner or MealPlanner()

        # Define agent name mappings (short names to attribute names)
        self._agent_name_mapping = {
            "greeter": "greeter_profiler",
            "profile": "profile_updater",
            "cgm": "cgm_collector",
            "meal": "meal_planner",
            # Add reverse mapping for direct attribute access
            "greeter_profiler": "greeter_profiler",
            "profile_updater": "profile_updater",
            "cgm_collector": "cgm_collector",
            "meal_planner": "meal_planner",
        }

        # Populate the handoffs list with specialized agents
        self.handoffs = [
            self.greeter_profiler,
            self.profile_updater,
            self.cgm_collector,
            self.meal_planner,
        ]

    def get_agent(self, name: str) -> Agent | None:
        """
        Get a specialized agent by name.

        Args:
            name: The name of the agent to retrieve (can be short name or full attribute name).

        Returns:
            The requested agent if found, None otherwise.
        """
        attr_name = self._agent_name_mapping.get(name)
        if attr_name and hasattr(self, attr_name):
            return getattr(self, attr_name)
        return None

    # Alias for get_agent to match test expectations
    get_specialized_agent = get_agent

    def add_specialized_agent(self, name: str, agent: Agent) -> None:
        """
        Add a new specialized agent to the triage agent.

        Args:
            name: The name to identify the agent by.
            agent: The agent instance to add.

        Raises:
            ValueError: If an agent with the given name already exists.
        """
        if name in self._agent_name_mapping:
            raise ValueError(f"An agent with name '{name}' already exists.")

        # Add the agent as an attribute
        attr_name = f"{name}_agent"
        setattr(self, attr_name, agent)

        # Update the name mapping
        self._agent_name_mapping[name] = attr_name
        self._agent_name_mapping[attr_name] = attr_name

        # Update handoffs list
        self.handoffs.append(agent)

    async def process_input(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> SimpleNamespace:
        """
        Process user input and route to the appropriate agent.

        Args:
            message: The user's input message.
            context: Optional context dictionary containing user_id and other metadata.

        Returns:
            A SimpleNamespace object with 'final_output' (the response string)
            and 'agent_name' (the name of the agent that handled the request).
        """
        if context is None:
            context = {}

        # Ensure user_id is present in context
        user_id = context.get("user_id")
        if not user_id:
            # For demo purposes, use a default user ID if not provided
            user_id = 1
            context["user_id"] = user_id

        try:
            # First, determine which agent should handle this message based on our routing logic
            agent_name, handling_agent = await self._determine_agent(message, context)

            # If no specific agent was determined, handle it with the triage agent
            if not handling_agent:
                # Process with the triage agent itself
                response = await self._process_with_agent(self, message, context)
                return SimpleNamespace(final_output=response, agent_name=self.name)

            # Process with the determined agent
            response = await self._process_with_agent(handling_agent, message, context)
            return SimpleNamespace(final_output=response, agent_name=agent_name)

        except Exception as e:
            # Log the error and provide a fallback response
            error_message = "I encountered an error while processing your request. Please try again later."
            print(f"Error processing message: {e!s}")

            return SimpleNamespace(final_output=error_message, agent_name=self.name)

    async def _intent_guardrail(
        self,
        ctx: RunContextWrapper[None],
        agent: Agent,
        input_data: str | list[TResponseInputItem],
    ) -> GuardrailFunctionOutput:
        """
        Guardrail to detect user intent from the input message.

        Args:
            ctx: The run context wrapper
            agent: The agent this guardrail is running for
            input_data: The input message or list of input items

        Returns:
            GuardrailFunctionOutput with the detected intent and metadata
        """
        # Extract text from input (handling both string and list of input items)
        if isinstance(input_data, list):
            message = " ".join(
                item.text for item in input_data if hasattr(item, "text")
            )
        else:
            message = input_data

        # Get the conversation context from the run context
        context = ctx.context or {}

        # Detect the intent from the message
        intent_result = await detect_intent(message)

        # Update the context with the detected intent
        context["detected_intent"] = intent_result

        # Update the conversation context if user_id is available
        if "user_id" in context and "conversation_context" not in context:
            # In a real app, you would load the conversation context from a database
            context["conversation_context"] = AduroConversationContext(
                user_id=context["user_id"]
            )

        return GuardrailFunctionOutput(
            output_info={
                "intent": intent_result[IntentDetectionOutput.INTENT],
                "confidence": intent_result[IntentDetectionOutput.CONFIDENCE],
                "reasoning": intent_result[IntentDetectionOutput.REASONING],
            },
            tripwire_triggered=False,  # We don't want to block any input, just analyze it
        )

    async def _determine_agent(
        self, message: str, context: dict[str, Any]
    ) -> tuple[str | None, Agent | None]:
        """
        Determine which agent should handle the message based on intent and context.

        Args:
            message: The user's input message.
            context: The current context, including detected intent.

        Returns:
            A tuple of (agent_name, agent) that should handle the message,
            or (None, None) if triage should handle it.
        """
        if not message or not message.strip():
            return None, None

        # Get the detected intent from the context (set by the guardrail)
        detected_intent = context.get("detected_intent", {})
        intent = detected_intent.get(IntentDetectionOutput.INTENT, UserIntent.UNKNOWN)

        # Map intents to agent names
        intent_to_agent = {
            UserIntent.GREETING: "greeter_profiler",
            UserIntent.PROFILE_UPDATE: "profile_updater",
            UserIntent.PROFILE_QUERY: "profile_updater",
            UserIntent.CGM_UPDATE: "cgm_collector",
            UserIntent.CGM_QUERY: "cgm_collector",
            UserIntent.MEAL_PLAN: "meal_planner",
            UserIntent.UNKNOWN: None,
        }

        # Get the agent name based on intent
        agent_name = intent_to_agent.get(intent)
        if not agent_name:
            return None, None

        # Get the agent instance
        agent = getattr(self, agent_name, None)
        if not agent:
            return None, None

        # Update conversation context if available
        conversation_context = context.get("conversation_context")
        if conversation_context:
            conversation_context.current_intent = intent

        return agent_name, agent

    async def _process_with_agent(
        self, agent: Agent, message: str, context: dict[str, Any]
    ) -> str:
        """
        Process a message with the specified agent.

        This is a helper method that can be used to process a message with a specific agent.
        In most cases, you should use process_input instead and let the SDK handle the routing.

        Args:
            agent: The agent to process the message with.
            message: The user's input message.
            context: The current context.

        Returns:
            The agent's response as a string.
        """
        response_text = "I'm not sure how to respond to that."  # Default fallback
        try:
            runner = Runner()
            result = await runner.run(agent, message, context=context)

            # Extract the response from the result
            if hasattr(result, "final_output") and result.final_output:
                response_text = result.final_output
            elif hasattr(result, "output") and result.output:
                response_text = result.output
            elif hasattr(result, "response") and result.response:
                response_text = result.response
            elif hasattr(result, "content") and result.content:
                if (
                    isinstance(result.content, list)
                    and result.content
                    and hasattr(result.content[0], "text")
                ):
                    response_text = result.content[0].text
                else:
                    response_text = str(result.content)
            elif (
                result
            ):  # If none of the specific attributes are found, but result exists
                response_text = str(result)

        except Exception as e:
            # Log the error and provide a fallback response
            print(f"Error processing with {agent.name}: {e!s}")
            response_text = (
                f"I had trouble with that request. Let me help you instead. {e!s}"
            )

        return response_text
