"""
Meal Planner Agent for generating personalized meal plans based on user profile and CGM data.

This module provides the MealPlanner agent which is responsible for:
- Generating personalized meal plans based on user preferences
- Analyzing CGM data for dietary recommendations
- Providing nutritional guidance based on user health profile
"""

from typing import Any, Literal, TypedDict

from agents import Agent, function_tool

from aduro_agents.utils.database import DatabaseManager

# Constants
DEFAULT_DAYS = 7
MIN_READINGS = 3

# System Prompt
SYSTEM_PROMPT = """
You are a clinical dietitian assistant. Your main goal is to provide users with a personalized 3-meal plan.

To do this, you MUST use the 'generate_meal_plan' tool.
1. The 'user_id' for whom the plan is to be generated will be available in the 'context' provided to your run.
2. Call the 'generate_meal_plan' tool, providing this 'user_id'. By default, the tool plans for 7 days; if the user specifically requests a plan for a different duration (e.g., 1 day, 3 days), you can pass this as the 'days' argument to the tool. For a 24-hour plan, you might infer 'days=1'.

The 'generate_meal_plan' tool is designed to return a detailed meal plan that already:
- Matches the user's dietary_preference (e.g., vegetarian, vegan, non-vegetarian).
- Considers their medical_conditions and physical_limitations.
- Aims for an appropriate daily calorie target.
- Helps manage post-prandial CGM spikes.
- Includes per-meal macronutrient breakdowns (calories, carbohydrates, protein, fats).

Your responsibilities are:
1. Correctly invoke the 'generate_meal_plan' tool using the 'user_id' from the context and any user-specified 'days'.
2. Receive the meal plan data (or an error message) from the tool.
3. If a meal plan is successfully generated:
    - Present it to the user in a friendly and clear Markdown format.
    - Use headings for each meal (e.g., "## Breakfast", "## Lunch", "## Dinner").
    - List meal items using bullet points.
    - Include the per-meal and daily total nutritional information provided by the tool.
4. If the tool returns an error (e.g., user profile not found, insufficient data for planning):
    - Clearly and politely inform the user about the issue, based on the tool's response.

Always be helpful and ensure the user understands the provided meal plan or the reason why one could not be generated.
"""

# Type Definitions
DietaryPreference = Literal["vegetarian", "non-vegetarian", "vegan"]

class CGMReading(TypedDict):
    """Represents a single CGM reading with timestamp."""
    reading: float
    timestamp: str  # ISO format datetime string

class UserProfile(TypedDict):
    """Represents a user's profile information relevant to meal planning."""
    first_name: str
    last_name: str
    dietary_preference: DietaryPreference
    medical_conditions: str | None
    physical_limitations: str | None

class MealPlan(TypedDict):
    """Represents a generated meal plan for a user."""
    id: int
    user_id: int
    plan_date: str  # ISO format date string
    meals: dict[str, list[dict[str, Any]]]  # meal_type: [food_items]
    nutritional_info: dict[str, float]
    created_at: str  # ISO format datetime string

# Database Helper Functions
async def _get_user_profile(
    user_id: int,
    db_manager: DatabaseManager | None = None
) -> UserProfile | None:
    """
    Retrieve a user's profile from the database.

    Args:
        user_id: The ID of the user
        db_manager: Optional DatabaseManager instance for testing

    Returns:
        UserProfile if found, None otherwise
    """
    close_db = False
    if db_manager is None:
        db_manager = DatabaseManager()
        close_db = True

    try:
        query = """
            SELECT first_name, last_name, dietary_preference,
                   medical_conditions, physical_limitations
            FROM users
            WHERE id = ?
        """

        row = await db_manager.fetch_one(query, (user_id,))
        if not row:
            return None

        return dict(row)
    except Exception as e:
        print(f"Database error: {e}")
        return None
    finally:
        if close_db and db_manager:
            await db_manager.close()

async def _get_recent_cgm_readings(
    user_id: int,
    days: int = 7,
    db_manager: DatabaseManager | None = None
) -> list[dict[str, Any]]:
    """
    Retrieve recent CGM readings for a user.

    Args:
        user_id: The ID of the user
        days: Number of days of readings to retrieve
        db_manager: Optional DatabaseManager instance for testing

    Returns:
        List of CGM readings with timestamps
    """
    close_db = False
    if db_manager is None:
        db_manager = DatabaseManager()
        close_db = True

    try:
        query = """
            SELECT reading, timestamp, reading_type
            FROM cgm_readings
            WHERE user_id = ?
            AND timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp DESC
        """

        rows = await db_manager.fetch_all(query, (user_id, f"-{days}"))
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        if close_db and db_manager:
            await db_manager.close()

# Tool Definitions
@function_tool
async def generate_meal_plan(
    user_id: int,
    days: int = 7,
    dietary_preference: DietaryPreference | None = None,
    db_manager: DatabaseManager | None = None
) -> dict[str, Any]:
    """
    Generate a personalized meal plan for a user based on their profile and CGM data.

    Args:
        user_id: The ID of the user
        days: Number of days to generate the meal plan for (default: 7)
        dietary_preference: Optional override for dietary preference
        db_manager: Optional DatabaseManager instance for testing

    Returns:
        Dictionary containing the generated meal plan
    """
    close_db = False
    if db_manager is None:
        db_manager = DatabaseManager()
        close_db = True

    try:
        # Get user profile
        profile = await _get_user_profile(user_id, db_manager=db_manager)
        if not profile:
            return {"error": "User not found"}

        # Get recent CGM data
        cgm_data = await _get_recent_cgm_readings(
            user_id,
            days=min(days, 30),
            db_manager=db_manager
        )

        # Use provided dietary preference or get from profile
        diet_pref = dietary_preference or profile.get('dietary_preference')

        # Here you would typically call an LLM or other logic to generate the meal plan
        # For now, we'll return a simple response with the available data
        return {
            "user_id": user_id,
            "days": days,
            "dietary_preference": diet_pref,
            "cgm_readings_count": len(cgm_data),
            "medical_considerations": profile.get('medical_conditions'),
            "physical_limitations": profile.get('physical_limitations'),
            "message": "Meal plan generation logic will be implemented here"
        }
    except Exception as e:
        return {"error": f"Failed to generate meal plan: {e!s}"}
    finally:
        if close_db and db_manager:
            await db_manager.close()

class MealPlanner(Agent):
    """
    Agent for generating personalized meal plans based on user profile and CGM data.

    This agent helps users by:
    - Creating customized meal plans based on dietary preferences
    - Analyzing CGM data for personalized recommendations
    - Providing nutritional guidance and meal suggestions
    - Adapting plans based on user feedback and health data
    """

    def __init__(self):
        """Initialize the MealPlanner agent with its instructions and tools."""
        super().__init__(
            name="meal_planner",
            instructions=SYSTEM_PROMPT,
            model="gpt-4.1-mini",
            tools=[generate_meal_plan],
            handoff_description="Specialist for generating personalized meal plans based on profile and CGM data."
        )

    async def process_input(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        db_manager: DatabaseManager | None = None
    ) -> str:
        """
        Process user input and generate a response using the agent's tools.

        Args:
            message: The user's message
            context: Optional context dictionary (should contain 'user_id')
            db_manager: Optional DatabaseManager instance for testing

        Returns:
            The agent's response as a string
        """
        context = context or {}
        user_id = context.get('user_id')

        if not user_id or not isinstance(user_id, int):
            return "Error: Authentication required. Please provide a valid user_id."

        try:
            # Let the agent handle the message using its tools
            response = await self.run(message, context={"user_id": user_id})
            return str(response)
        except Exception as e:
            return f"Error generating meal plan: {e!s}"

    async def _get_db_connection(self, db_manager: DatabaseManager | None = None):
        """Get a database connection.

        Args:
            db_manager: Optional DatabaseManager instance

        Returns:
            DatabaseManager instance
        """
        if db_manager is None:
            db_manager = DatabaseManager()
        return db_manager

    def get_user_profile(self, user_id: int, db_manager: DatabaseManager | None = None) -> dict[str, Any]:
        """
        Fetch user profile from the database.

        Args:
            user_id: The ID of the user
            db_manager: Optional DatabaseManager instance for testing

        Returns:
            Dict containing user profile information

        Raises:
            ValueError: If user not found or profile is incomplete
        """
        close_db = False
        if db_manager is None:
            db_manager = DatabaseManager()
            close_db = True

        try:
            query = """
                SELECT first_name, dietary_preference, medical_conditions,
                       physical_limitations, date_of_birth, created_at
                FROM users
                WHERE id = ?
            """

            row = db_manager.fetch_one(query, (user_id,))
            if not row:
                raise ValueError(f"User with ID {user_id} not found")

            profile: UserProfile = { # Added type hint here for clarity
                "first_name": row[0],
                "dietary_preference": row[1].lower() if row[1] else None,
                "medical_conditions": row[2],
                "physical_limitations": row[3],
                "date_of_birth": row[4], # Expects date object
                "created_at": row[5]    # Expects datetime object
            }

            # Validate required fields
            if not profile["dietary_preference"] or profile["dietary_preference"] not in ["vegetarian", "non-vegetarian", "vegan"]:
                raise ValueError("Dietary preference is missing or invalid. Please update your profile.")

            return profile
        except Exception as e:
            print(f"Database error: {e}")
            return {}
        finally:
            if close_db and db_manager:
                db_manager.close()

    def get_recent_cgm(self, user_id: int, days: int = DEFAULT_DAYS, db_manager: DatabaseManager | None = None) -> list[CGMReading]:
        """
        Fetch recent CGM readings for a user.

        Args:
            user_id: The ID of the user
            days: Number of days to look back for readings (default: 7)
            db_manager: Optional DatabaseManager instance for testing

        Returns:
            List of CGM readings with timestamps
        """
        close_db = False
        if db_manager is None:
            db_manager = DatabaseManager()
            close_db = True

        try:
            query = """
                SELECT reading, timestamp
                FROM cgm_readings
                WHERE user_id = ?
                AND timestamp >= datetime('now', ? || ' days')
                ORDER BY timestamp ASC
            """

            rows = db_manager.fetch_all(query, (user_id, f"-{days}"))
            return [
                {"reading": row[0], "timestamp": str(row[1])} # Ensure timestamp is string
                for row in rows
            ]
        except Exception as e:
            print(f"Database error: {e}")
            return []
        finally:
            if close_db and db_manager:
                db_manager.close()

    @staticmethod
    def validate_meal_plan(meal_plan: str) -> bool:
        """
        Validate a personalized meal plan.

        Args:
            meal_plan: The meal plan to validate

        Returns:
            True if the meal plan is valid, False otherwise
        """
        # TO DO: implement meal plan validation logic
        return True

# Example usage
if __name__ == "__main__":
    import asyncio
    import os

    from dotenv import load_dotenv

    async def main():
        # Load environment variables
        load_dotenv()

        # Check for required environment variables
        if not os.getenv("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY environment variable is not set.")
            print("Please create a .env file with your OpenAI API key.")
            return

        try:
            # Initialize the agent
            print("Initializing Meal Planner agent...")
            meal_planner = MealPlanner()

            # Example usage with a test user ID
            user_id = 1  # Replace with actual user ID
            print(f"Generating meal plan for user ID: {user_id}")

            # Generate meal plan using the agent's process_input method
            response = await meal_planner.process_input(
                "Generate a meal plan for me",
                context={"user_id": user_id}
            )
            print("\n" + "="*70)
            print(response)
            print("="*70)

        except Exception as e:
            print(f"An error occurred: {e!s}")

    # Run the async main function
    asyncio.run(main())
