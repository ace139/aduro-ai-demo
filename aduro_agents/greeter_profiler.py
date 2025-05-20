"""
Greeter Profiler Agent for collecting and validating user profile information.

This module provides the GreeterProfiler agent which is responsible for:
- Greeting new users
- Collecting and validating profile information
- Guiding users through the profile completion process
- Updating user profiles in the database
"""

from typing import Any

from agents import Agent, function_tool

from aduro_agents.models import UserProfile
from aduro_agents.utils.database import DatabaseManager


async def _update_user_profile(
    user_id: int, updates: dict[str, Any], db_manager: DatabaseManager | None = None
) -> bool:
    """
    Update user profile in the database.

    Args:
        user_id: The ID of the user
        updates: Dictionary of fields to update
        db_manager: Optional DatabaseManager instance for testing

    Returns:
        bool: True if update was successful, False otherwise
    """
    if not updates:
        return False

    # Use provided db_manager or create a new one
    close_db = False
    if db_manager is None:
        db_manager = DatabaseManager()
        close_db = True

    try:
        # Build the SET clause dynamically based on provided updates
        set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
        values = list(updates.values())
        values.append(user_id)  # For the WHERE clause

        query = f"""
            UPDATE users
            SET {set_clause}
            WHERE id = ?
        """

        success = await db_manager.execute_query(query, values, commit=True)
        return success

    except Exception as e:
        print(f"Database error: {e}")
        return False
    finally:
        if close_db and db_manager:
            await db_manager.close()


async def _get_user_profile_from_db(
    user_id: int, db_manager: DatabaseManager | None = None
) -> UserProfile | None:
    """
    Internal function to fetch user profile from the database.

    Args:
        user_id: The ID of the user
        db_manager: Optional DatabaseManager instance for testing

    Returns:
        Dictionary containing user profile information or None if not found
    """
    close_db = False
    if db_manager is None:
        db_manager = DatabaseManager()
        close_db = True

    try:
        query = """
            SELECT first_name, last_name, city, email, date_of_birth,
                   dietary_preference, medical_conditions, physical_limitations
            FROM users
            WHERE id = ?
        """

        result = await db_manager.fetch_one(query, (user_id,))
        return UserProfile(**dict(result)) if result else None

    except Exception as e:
        print(f"Database error: {e}")
        return None
    finally:
        if close_db and db_manager:
            await db_manager.close()


@function_tool
async def get_user_profile(user_id: int) -> UserProfile:
    """
    Fetches the user profile from the database.

    Args:
        user_id: The ID of the user

    Returns:
        Dictionary containing user profile information with the following fields:
        {
            "first_name": str or None,
            "last_name": str or None,
            "city": str or None,
            "email": str or None,
            "date_of_birth": str or None (YYYY-MM-DD),
            "dietary_preference": str or None,
            "medical_conditions": str or None,
            "physical_limitations": str or None
        }
    """
    profile = await _get_user_profile_from_db(user_id)
    return profile if profile else UserProfile()


@function_tool
def get_missing_fields(profile: UserProfile) -> list[str]:
    """
    Identifies which required fields are missing from the user profile.

    Args:
        profile: Dictionary containing user profile data

    Returns:
        List of missing required field names
    """
    required_fields = [
        "first_name",
        "last_name",
        "city",
        "email",
        "date_of_birth",
        "dietary_preference",
    ]
    return [
        field
        for field in required_fields
        if not getattr(profile, field, None) or getattr(profile, field) == ""
    ]


class GreeterProfiler(Agent):
    """Agent responsible for greeting users and collecting profile information."""

    def __init__(self):
        super().__init__(
            name="greeter_profiler",
            instructions="""
            You are a friendly AI assistant responsible for greeting users and ensuring their profile information is complete. Your primary goal is to collect any missing required profile details.

            Follow these steps:
            1. Greet the user warmly and professionally.
            2. Use the 'get_user_profile' tool to fetch the user's current profile information using their user_id (available in the context).
            3. Use the 'get_missing_fields' tool, passing the profile data obtained from 'get_user_profile', to identify any required fields that are missing or empty.
            4. If there are missing fields:
                - Inform the user which fields are missing.
                - Politely ask the user to provide the information for these missing fields, one or two at a time to avoid overwhelming them.
                - Be conversational. For example, instead of just saying 'Missing: first_name', say 'I see we're missing your first name. Could you please provide it?'
            5. If the 'get_missing_fields' tool returns an empty list (meaning no required fields are missing):
                - Inform the user that their profile looks complete or up-to-date.
                - You can end with a positive note, for example, 'Thanks! Your profile is all set up.'

            Always be polite, concise, and helpful throughout the interaction.
            The required fields this system tracks are: first_name, last_name, city, email, date_of_birth, dietary_preference.
            """,
            model="gpt-4.1-mini",
            tools=[
                get_user_profile,
                get_missing_fields,
            ],  # Added get_missing_fields tool
            handoff_description="Specialist for greeting new users and collecting initial profile information.",
        )
        self._greeted_users = set()  # This set is for internal Python logic if ever needed, not directly for LLM use without a tool.

    async def process_input(
        self,
        user_input: str,  # This is the 'message' for self.run
        context: dict[str, Any],
        db_manager: DatabaseManager
        | None = None,  # Kept for compatibility, not used directly
        test_conn=None,  # Kept for backward compatibility, not used directly
    ) -> str:
        """
        Process user input using the agent's SDK capabilities.

        Args:
            user_input: The user's input text (message for the agent).
            context: Dictionary containing additional context (must include 'user_id').
            db_manager: Optional DatabaseManager instance (kept for test compatibility).

        Returns:
            str: The agent's response.

        Raises:
            ValueError: If user_id is missing from the context.
        """
        user_id = context.get("user_id")
        if not user_id or not isinstance(user_id, int):
            # For direct calls, this check is useful.
            # If invoked via SDK handoff, TriageAgent/SDK might handle context validation.
            raise ValueError("Authentication required. Please provide a valid user_id.")

        try:
            # The agent's instructions and tools (like get_user_profile)
            # will now handle profile checking, greeting, and prompting for info.
            run_context = {"user_id": user_id}
            # If other parts of the incoming 'context' from tests/direct calls are relevant
            # to the agent's operation as per its instructions, they should be added to 'run_context'.

            agent_response = await self.run(message=user_input, context=run_context)
            return str(agent_response.final_output)
        except Exception as e:
            # Consider adding logging here: import logging; logger = logging.getLogger(__name__); logger.error(f"Error: {e!s}")
            return f"Sorry, I encountered an issue while processing your request in GreeterProfiler: {e!s}"
