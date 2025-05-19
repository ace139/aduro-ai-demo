"""
Meal Planner Agent for generating personalized meal plans based on user profile and CGM data.
"""

from datetime import datetime, date
from typing import Dict, List, Optional, TypedDict, Any
import sqlite3
from pathlib import Path

from agents import Agent, Runner, function_tool

@function_tool
async def generate_meal_plan(user_id: int) -> str:
    """
    Inserts a placeholder meal plan for the user.
    Args:
        user_id: The ID of the user
    Returns:
        A string containing the formatted meal plan
    """
    if not isinstance(user_id, int) or user_id <= 0:
        return "⚠️ Invalid user ID."
    return f"Class-based placeholder meal plan for user {user_id}. Args: user_id={user_id}"

# Constants
DB_PATH = Path("db/users.db")
DEFAULT_DAYS = 7
MIN_READINGS = 3

# Type Definitions
class CGMReading(TypedDict):
    reading: float
    timestamp: str  # Changed to string to avoid serialization issues

class UserProfile(TypedDict):
    first_name: str
    dietary_preference: str  # "vegetarian" | "non-vegetarian" | "vegan"
    medical_conditions: Optional[str]
    physical_limitations: Optional[str]
    date_of_birth: date
    created_at: datetime

# System Prompt
SYSTEM_PROMPT = """
You are a clinical dietitian assistant. You must produce a 3-meal plan (breakfast, lunch, dinner) for the next 24 hours that:
- Matches the user's dietary_preference (vegetarian/non-veg/vegan).
- Respects medical_conditions and physical_limitations.
- Targets a daily calorie goal of ±10% (derive from BMR if absent).
- Smooths post-prandial CGM spikes to keep readings ≤30 mg/dL above baseline.
- Includes per-meal macros: kcal, carbs, protein, fats.
- Presents output as Markdown with headings ("## Breakfast") and bullet details.
"""

class MealPlanner(Agent):
    """Agent for generating personalized meal plans based on user profile and CGM data."""

    def __init__(self):
        super().__init__(
            name="meal_planner",
            instructions=SYSTEM_PROMPT,
            tools=[generate_meal_plan],
        )


    @staticmethod
    def _get_db_connection() -> sqlite3.Connection:
        """Create and return a database connection."""
        # Ensure that date/datetime types are parsed correctly from the database
        return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)

    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """
        Fetch user profile from the database.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            Dict containing user profile information
            
        Raises:
            ValueError: If user not found or profile is incomplete
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT first_name, dietary_preference, medical_conditions, 
                       physical_limitations, date_of_birth, created_at
                FROM users 
                WHERE id = ?
                """,
                (user_id,)
            )
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"User with ID {user_id} not found")
                
            profile: UserProfile = { # Added type hint here for clarity
                "first_name": result[0],
                "dietary_preference": result[1].lower() if result[1] else None,
                "medical_conditions": result[2],
                "physical_limitations": result[3],
                "date_of_birth": result[4], # Expects date object
                "created_at": result[5]    # Expects datetime object
            }
            
            # Validate required fields
            if not profile["dietary_preference"] or profile["dietary_preference"] not in ["vegetarian", "non-vegetarian", "vegan"]:
                raise ValueError("Dietary preference is missing or invalid. Please update your profile.")
                
            return profile
        finally:
            conn.close()

    def get_recent_cgm(self, user_id: int, days: int = DEFAULT_DAYS) -> List[CGMReading]:
        """
        Fetch recent CGM readings for a user.
        
        Args:
            user_id: The ID of the user
            days: Number of days to look back for readings (default: 7)
            
        Returns:
            List of CGM readings with timestamps
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT reading, timestamp
                FROM cgm_readings
                WHERE user_id = ? 
                AND timestamp >= datetime('now', ? || ' days')
                ORDER BY timestamp ASC
                """,
                (user_id, f"-{days}")
            )
            return [
                {"reading": row[0], "timestamp": str(row[1])} # Ensure timestamp is string
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

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
            
            # Generate meal plan using the function tool
            response = await Runner.run(meal_planner, f"Generate a meal plan for me with user ID {user_id}")
            meal_plan = response.final_output
            print("\n" + "="*70)
            print(meal_plan)
            print("="*70)
            
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    
    # Run the async main function
    asyncio.run(main())
